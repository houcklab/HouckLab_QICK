import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import PulseFunctions
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd


def declare_ff(prog):
    prog.declare_gen(ch=prog.cfg["ff_ch"], nqz=prog.cfg.get("ff_nqz", 1))


def static_park_configured(cfg):
    return (cfg.get("ff_ch", None) is not None
            and "ff_park_gain" in cfg
            and cfg.get("ff_park_gain", None) is not None)


def declare_static_park(prog):
    prog.do_static_ff_park = bool(static_park_configured(prog.cfg))
    if prog.do_static_ff_park:
        declare_ff(prog)


def _avg_segs(seg, dt_def_us, dt_play_us):
    seg = np.asarray(seg, dtype=float)
    if seg.size == 0:
        return np.array([])
    ppp = max(int(round(dt_play_us / dt_def_us)), 1)
    n = max(int(seg.size / ppp), 1)
    return np.array([seg[i * ppp:(i + 1) * ppp].mean() for i in range(n)])


def flux_settle_us(cfg):
    if "flux_settle_time" in cfg:
        legacy = cfg["flux_settle_time"]
        raise ValueError(
            f"cfg['flux_settle_time'] = {legacy} is the old NANOSECOND key and is no "
            f"longer read.  Rename it to 'flux_settle_time_us' and convert the value: "
            f"{legacy} ns -> {float(legacy) / 1000.0:g} us.  Leaving it in place would "
            f"silently apply a 1000x longer settle.")
    return float(cfg.get("flux_settle_time_us", DEFAULT_FLUX_SETTLE_US))


def _warn_slew(delta, ramp_us):
    if abs(delta) < 1e-9 or ramp_us <= 0:
        return
    slew = abs(delta) / float(ramp_us)
    if slew <= MAX_SAFE_SLEW_DAC_PER_US:
        return
    key = (round(abs(delta)), round(float(ramp_us), 4))
    if key in _SLEW_WARNED:
        return
    _SLEW_WARNED.add(key)
    print(f"[ff_pulse] flux slew {slew:.0f} DAC/us "
          f"({abs(delta):.0f} DAC in {ramp_us:g} us) exceeds the measured state-safe "
          f"limit of {MAX_SAFE_SLEW_DAC_PER_US:.0f} DAC/us.")
    print(f"[ff_pulse]   On q4 a 20 ns ramp to 8000 destroyed the excited state "
          f"(blob separation 0.04x); 0.5 us kept 0.88x.")
    print(f"[ff_pulse]   Intentional for step-response characterisation; for any "
          f"experiment that must PRESERVE the qubit state, raise ff_ramp_length.")


def build_ramp_hold_ramp(prog, hold_us, ff_gain, dt_play_us=5.0, ramp_us=0.02,
                         dt_def_us=0.002, compensation=None, distortion_model=None,
                         maxv=None, park_gain=None):
    cfg = prog.cfg
    if maxv is None:
        maxv = prog.soccfg['gens'][0]['maxv']
    if park_gain is None:
        park_gain = cfg.get("ff_park_gain", 0)
    park_gain = float(np.clip(park_gain, -maxv, maxv))
    ff_gain = float(np.clip(ff_gain, -maxv, maxv))
    delta = ff_gain - park_gain
    hold_us = max(float(hold_us), dt_def_us)
    _warn_slew(delta, ramp_us)

    def _lvl(mult):
        return int(np.clip(park_gain + float(mult) * delta, -maxv, maxv))

    if compensation is not None and distortion_model is None:
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
        hold_segs = [(int(ff_gain), hold_us)]

    first_level, last_level = hold_segs[0][0], hold_segs[-1][0]

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


STATE_SAFE_RAMP_US = 0.5
DEFAULT_FLUX_SETTLE_US = 0.5
MAX_SAFE_SLEW_DAC_PER_US = 20000.0
_SLEW_WARNED = set()

_MAX_CONST_LEN = 65000


def play_ramp_up_hold(prog, segs, dt_play_us=None):
    cfg = prog.cfg
    prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                             gain=prog.soccfg['gens'][0]['maxv'], waveform="ff_ramp", outsel="input")
    prog.pulse(ch=cfg["ff_ch"])
    for g, dur_us in segs["hold_segs"]:
        total = max(int(prog.us2cycles(dur_us, gen_ch=cfg["ff_ch"])), 3)
        n_chunks = max(1, (total + _MAX_CONST_LEN - 1) // _MAX_CONST_LEN)
        base, extra = divmod(total, n_chunks)
        for c in range(n_chunks):
            length = max(base + (1 if c < extra else 0), 3)
            prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='const', phase=0,
                                     stdysel='last', gain=int(g), length=int(length))
            prog.pulse(ch=cfg["ff_ch"])


def play_ramp_down(prog, segs):
    cfg = prog.cfg
    ff_rp = prog.ch_page(cfg["ff_ch"])
    ff_gain_reg = prog.sreg(cfg["ff_ch"], "gain")
    prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                             gain=prog.soccfg['gens'][0]['maxv'], waveform="ff_ramp_reversed", outsel="input")
    prog.pulse(ch=cfg["ff_ch"])
    prog.safe_regwi(ff_rp, ff_gain_reg, int(segs.get("park", 0)))


def assert_park(prog, segs, dt_us=0.1, force=False):
    park = int(segs.get("park", 0))
    if park == 0 and not force:
        return
    cfg = prog.cfg
    prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='const', phase=0,
                             stdysel='last', gain=park,
                             length=prog.us2cycles(dt_us, gen_ch=cfg["ff_ch"]))
    prog.pulse(ch=cfg["ff_ch"])


def play_static_park(prog, settle_us=0.05):
    if not getattr(prog, "do_static_ff_park", False):
        return
    assert_park(
        prog, {"park": int(prog.cfg.get("ff_park_gain", 0) or 0)},
        force=True,
    )
    settle_us = max(float(settle_us), 0.0)
    if settle_us > 0:
        prog.sync_all(prog.us2cycles(settle_us))


def play_ramp_hold_ramp(prog, segs, dt_play_us=5.0):
    play_ramp_up_hold(prog, segs, dt_play_us=dt_play_us)
    play_ramp_down(prog, segs)


def make_distortion_model(prog):
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
    comp = cfg.get("flux_tail_compensation", None)
    if comp is None:
        return None
    if isinstance(comp, str):
        return fpd.load_compensation_json(comp)
    return comp
