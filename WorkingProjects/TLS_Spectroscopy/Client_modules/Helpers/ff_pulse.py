"""
Shared fast-flux (ff) pulse playback for the TLS FF experiments (steps 3, 4, 6).

This is the QICK stand-in for the QUA flux "step" (QUA used an OPX ``set_dc_offset``
staircase; QICK has no in-program DC primitive).  We synthesize the flux step as a
shaped pulse on a dedicated fast-flux DAC channel (``ff_ch``), exactly like the
escher FF stack (mFFRampHoldTest_wPulsePreDist): a linear ramp up, a
piecewise-constant HOLD streamed via ``safe_regwi`` on the ff gain register (so the
hold length is not bounded by arb-envelope memory), then a ramp down -- with the
whole thing PRE-DISTORTED to cancel the flux line's slow settling.

Two predistortion sources are supported (pick one):
  * ``compensation`` : the QUA-faithful piecewise-multiplier dict from step 3
    (flux_predistortion.calculate_piecewise_dc_correction / a loaded JSON).
  * ``distortion_model`` : an escher PulseFunctions.Simple*TailDistortion instance
    (recursive IIR inverse).  Its ``.predistort(waveform)`` is applied to the
    ideal sample array.

Usage (inside a QICK Program's initialize()/body()):
    from ...Helpers import ff_pulse
    # in initialize(): ff_pulse.declare_ff(self)
    # build once (in initialize or body-prep):
    segs = ff_pulse.build_ramp_hold_ramp(self, hold_us, ff_gain, dt_play_us=..,
                                         ramp_us=.., dt_def_us=.., compensation=..)
    # in body(): ff_pulse.play_ramp_hold_ramp(self, segs, dt_play_us=..)

The static DC baseline (QUA baseline_dc_offset / park) is set OUT of band by the
Yokogawa GS200 (see the runner); ``ff_gain`` here is the *additional* fast-flux
excursion in DAC-gain units on top of that DC bias.
"""

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import PulseFunctions
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd


def declare_ff(prog):
    """Declare the fast-flux generator (call once in initialize())."""
    prog.declare_gen(ch=prog.cfg["ff_ch"], nqz=prog.cfg.get("ff_nqz", 1))


def _avg_segs(seg, dt_def_us, dt_play_us):
    """Downsample a fine (dt_def) waveform to coarse (dt_play) staircase means.
    (Mirrors escher FFRampHoldTest.create_avg_segs.)"""
    seg = np.asarray(seg, dtype=float)
    if seg.size == 0:
        return np.array([])
    ppp = max(int(round(dt_play_us / dt_def_us)), 1)
    n = max(int(seg.size / ppp), 1)
    return np.array([seg[i * ppp:(i + 1) * ppp].mean() for i in range(n)])


def build_ramp_hold_ramp(prog, hold_us, ff_gain, dt_play_us=5.0, ramp_us=0.02,
                         dt_def_us=0.002, compensation=None, distortion_model=None,
                         maxv=None, park_gain=None):
    """Build (and register) a predistorted park -> target hold -> park fast-flux pulse.

    ``ff_gain`` is the absolute target DAC level of the hold; ``park_gain`` (default
    cfg['ff_park_gain'], else 0) is the static baseline the sequence starts and ends
    at.  Predistortion is applied to the STEP (target - park) relative to park, so a
    nonzero park behaves exactly like the QUA baseline_dc_offset.

    The HOLD is played as VARIABLE-WIDTH piecewise-constant segments -- exactly the QUA
    ``_hold_flux_step`` set_dc_offset staircase: when a ``compensation`` dict is present
    the segment edges are its ``segment_edges_ns`` (fine early: 500 ns/1 us, coarse
    late), each played for its EXACT width so (a) the total hold == the requested
    ``hold_us`` (on the tProc 4 ns grid, NOT floored to dt_play), and (b) the fast early
    correction segments are RESOLVED rather than averaged into dt_play bins.  Without
    compensation the hold is a single constant segment of exactly ``hold_us``.
    ``dt_play_us`` is used only for the coarse binning of the (optional) escher IIR
    ``distortion_model`` path.

    Returns {hold_segs: [(level_int, dur_us), ...], ...}.  Registers the two arb ramps.
    """
    cfg = prog.cfg
    if maxv is None:
        maxv = prog.soccfg['gens'][0]['maxv']
    if park_gain is None:
        park_gain = cfg.get("ff_park_gain", 0)
    park_gain = float(np.clip(park_gain, -maxv, maxv))
    ff_gain = float(np.clip(ff_gain, -maxv, maxv))
    delta = ff_gain - park_gain
    hold_us = max(float(hold_us), dt_def_us)

    def _lvl(mult):
        return int(np.clip(park_gain + float(mult) * delta, -maxv, maxv))

    if compensation is not None and distortion_model is None:
        # QUA-faithful piecewise staircase at the compensation segment edges.
        edges_us = np.asarray(compensation['segment_edges_ns'], dtype=float) / 1e3
        mult = np.asarray(compensation['multipliers'], dtype=float)
        bounds = sorted(set([0.0] + [float(e) for e in edges_us if 0.0 < e < hold_us - 1e-9]))
        hold_segs = []
        for k, b0 in enumerate(bounds):
            b1 = bounds[k + 1] if k + 1 < len(bounds) else hold_us
            dur = b1 - b0
            if dur <= 0:
                continue
            seg_i = (min(max(int(np.searchsorted(edges_us, b0 + 1e-12, side='right') - 1), 0),
                         mult.size - 1) if mult.size else 0)
            hold_segs.append((_lvl(mult[seg_i] if mult.size else 1.0), dur))
        if not hold_segs:
            hold_segs = [(int(ff_gain), hold_us)]
    elif distortion_model is not None:
        # escher IIR path: predistort the ideal step, coarse-bin the hold at dt_play,
        # extend the last bin so the total played hold == hold_us.
        total = 2 * ramp_us + hold_us + 4 * dt_play_us
        pb = PulseFunctions.PulseBuilder(dt_def_us, total)
        pb.add_trapezoid(start=dt_play_us, rise=ramp_us, flat=hold_us, fall=ramp_us, amp=delta)
        waveform = np.clip(park_gain + distortion_model.predistort(pb.waveform()), -maxv, maxv)
        i0 = int(round((dt_play_us + ramp_us) / dt_def_us))
        i1 = int(round((dt_play_us + ramp_us + hold_us) / dt_def_us))
        levels = _avg_segs(waveform[i0:i1], dt_def_us, dt_play_us)
        if levels.size == 0:
            levels = np.array([ff_gain])
        hold_segs = [(int(g), dt_play_us) for g in levels]
        last_dur = max(hold_us - dt_play_us * (len(hold_segs) - 1), dt_def_us)
        hold_segs[-1] = (hold_segs[-1][0], last_dur)
    else:
        hold_segs = [(int(ff_gain), hold_us)]      # plain constant hold, exact duration

    first_level, last_level = hold_segs[0][0], hold_segs[-1][0]

    # register the ramp arbs: park -> first hold level, last hold level -> park.
    # NOTE create_ff_ramp(reversed=True) plays ff_ramp_stop -> ff_ramp_start
    # (escher convention), so for the down-ramp: stop = FROM (hold end), start = TO (park).
    cfg["ff_ramp_style"] = "linear"
    cfg["ff_ramp_length"] = ramp_us
    cfg["ff_ramp_start"] = int(park_gain)
    cfg["ff_ramp_stop"] = int(first_level)
    PulseFunctions.create_ff_ramp(prog, reversed=False, name="ff_ramp")
    cfg["ff_ramp_start"] = int(park_gain)
    cfg["ff_ramp_stop"] = int(last_level)
    PulseFunctions.create_ff_ramp(prog, reversed=True, name="ff_ramp_reversed")
    cfg["ff_ramp_start"] = int(park_gain)
    cfg["ff_ramp_stop"] = int(ff_gain)

    return {"hold_segs": hold_segs, "dt_def_us": dt_def_us, "ramp_us": ramp_us,
            "ff_gain": ff_gain, "park": int(park_gain)}


def play_ramp_up_hold(prog, segs, dt_play_us=None):
    """Play ramp-up + the piecewise-constant hold (leaves flux held at target).
    Each hold segment is played for its EXACT width (QUA set_dc_offset staircase)."""
    cfg = prog.cfg
    prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                             gain=prog.soccfg['gens'][0]['maxv'], waveform="ff_ramp", outsel="input")
    prog.pulse(ch=cfg["ff_ch"])
    for g, dur_us in segs["hold_segs"]:
        length = max(prog.us2cycles(dur_us, gen_ch=cfg["ff_ch"]), 3)
        prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='const', phase=0,
                                 stdysel='last', gain=int(g), length=length)
        prog.pulse(ch=cfg["ff_ch"])


def play_ramp_down(prog, segs):
    """Play the ramp-down back to park and hold there (stdysel='last')."""
    cfg = prog.cfg
    ff_rp = prog.ch_page(cfg["ff_ch"])
    ff_gain_reg = prog.sreg(cfg["ff_ch"], "gain")
    prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                             gain=prog.soccfg['gens'][0]['maxv'], waveform="ff_ramp_reversed", outsel="input")
    prog.pulse(ch=cfg["ff_ch"])
    prog.safe_regwi(ff_rp, ff_gain_reg, int(segs.get("park", 0)))


def assert_park(prog, segs, dt_us=0.1):
    """Force the ff DAC to the park level (held via stdysel='last').

    Call at the top of body() when ff_park_gain != 0 so the first rep after a
    program load (when the DAC may sit at 0) starts from park like every other rep.
    No-op when park == 0.
    """
    park = int(segs.get("park", 0))
    if park == 0:
        return
    cfg = prog.cfg
    prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='const', phase=0,
                             stdysel='last', gain=park,
                             length=prog.us2cycles(dt_us, gen_ch=cfg["ff_ch"]))
    prog.pulse(ch=cfg["ff_ch"])


def play_ramp_hold_ramp(prog, segs, dt_play_us=5.0):
    """Play a full ramp -> predistorted hold -> ramp (built by build_ramp_hold_ramp)."""
    play_ramp_up_hold(prog, segs, dt_play_us=dt_play_us)
    play_ramp_down(prog, segs)


def make_distortion_model(prog):
    """Build an escher IIR distortion model from cfg (A_i, tau_i), or None.

    cfg keys: predist_taps = [[A1,tau1],[A2,tau2],...] (tau in us).  1/2/4 tails.
    ``x_val`` is the ff-DAC sample period (us) used by PulseFunctions' recursion.
    """
    taps = prog.cfg.get("predist_taps", None)
    if not taps:
        return None
    dt = prog.cfg.get("dt_pulsedef", 0.002)
    flat = [v for pair in taps for v in pair]
    if len(taps) == 1:
        return PulseFunctions.SimpleSingleTailDistortion(flat[0], flat[1], dt)
    if len(taps) == 2:
        return PulseFunctions.SimpleTwoTailDistortion(*flat, dt)
    if len(taps) == 4:
        return PulseFunctions.SimpleFourTailDistortion(*flat, dt)
    raise ValueError("predist_taps must have 1, 2, or 4 [A, tau] pairs")


def load_compensation(cfg):
    """Return the piecewise compensation dict from cfg, if present.

    cfg['flux_tail_compensation'] may be the dict itself or a path to a JSON.
    """
    comp = cfg.get("flux_tail_compensation", None)
    if comp is None:
        return None
    if isinstance(comp, str):
        return fpd.load_compensation_json(comp)
    return comp
