import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import PulseFunctions
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd


def declare_ff(prog):
    prog.declare_gen(ch=prog.cfg["ff_ch"], nqz=prog.cfg.get("ff_nqz", 1))


def static_park_configured(cfg):
    return (cfg.get("ff_ch", None) is not None
            and "ff_park_gain" in cfg
            and cfg.get("ff_park_gain", None) is not None)


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


def build_ramp_hold_ramp(prog, hold_us, ff_gain, dt_play_us=5.0, ramp_us=0.02,
                         dt_def_us=0.002, compensation=None, distortion_model=None,
                         maxv=None, park_gain=None, name_prefix="ff"):
    cfg = prog.cfg
    if maxv is None:
        maxv = PulseFunctions.ff_maxv(prog, scaled=True)
    if park_gain is None:
        park_gain = cfg.get("ff_park_gain", 0)
    park_gain = float(np.clip(park_gain, -maxv, maxv))
    ff_gain = float(np.clip(ff_gain, -maxv, maxv))
    delta = ff_gain - park_gain
    hold_us = max(float(hold_us), dt_def_us)

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
    ramp_waveform = PulseFunctions.create_ff_ramp(
        prog, reversed=False, name=f"{name_prefix}_ramp", allow_steps=True)
    ramp_steps = (None if ramp_waveform
                  else ramp_staircase(prog, park_gain, first_level, ramp_us))
    cfg["ff_ramp_start"] = int(park_gain)
    cfg["ff_ramp_stop"] = int(last_level)
    reverse_waveform = PulseFunctions.create_ff_ramp(
        prog, reversed=True, name=f"{name_prefix}_ramp_reversed", allow_steps=True)
    reverse_steps = (None if reverse_waveform
                     else ramp_staircase(prog, last_level, park_gain, ramp_us))
    cfg["ff_ramp_start"] = int(park_gain)
    cfg["ff_ramp_stop"] = int(ff_gain)
    if (ramp_steps or reverse_steps) and not _STAIRCASE_NOTED:
        _STAIRCASE_NOTED.append(1)
        print(f"[ff_pulse] the flux generator cannot store every distinct "
              f"{ramp_us:g} us ramp this program needs, so ramps are played as "
              f"{len(ramp_steps or reverse_steps)}-step const staircases instead: "
              f"same endpoints and duration, quantised in between.")

    return {"hold_segs": hold_segs, "dt_def_us": dt_def_us, "ramp_us": ramp_us,
            "ff_gain": ff_gain, "park": int(park_gain),
            "ramp_waveform": ramp_waveform,
            "reverse_waveform": reverse_waveform,
            "ramp_steps": ramp_steps,
            "reverse_steps": reverse_steps}


STATE_SAFE_RAMP_US = 0.5
DEFAULT_FLUX_SETTLE_US = 0.5
_SWEEP_BASELINE_NOTED = set()

_MAX_CONST_LEN = 65000


FF_RAMP_MAX_STEPS = 32
_STAIRCASE_NOTED = []


def ramp_staircase(prog, start, stop, ramp_us, max_steps=FF_RAMP_MAX_STEPS):
    ch = prog.cfg["ff_ch"]
    total = max(int(prog.us2cycles(float(ramp_us), gen_ch=ch)), 3)
    n = int(max(1, min(int(max_steps), total // 3)))
    steps = []
    for k in range(1, n + 1):
        cycles = max(total * k // n - total * (k - 1) // n, 3)
        gain = int(round(float(start) + (float(stop) - float(start)) * k / n))
        steps.append((gain, cycles))
    return steps


def _play_staircase(prog, steps):
    ch = prog.cfg["ff_ch"]
    for gain, cycles in steps:
        prog.set_pulse_registers(ch=ch, freq=0, style='const', phase=0,
                                 stdysel='last', gain=int(gain), length=int(cycles))
        prog.pulse(ch=ch)


def play_ramp_up_hold(prog, segs, dt_play_us=None):
    cfg = prog.cfg
    if segs.get("ramp_steps"):
        _play_staircase(prog, segs["ramp_steps"])
    else:
        prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 stdysel='last',
                                 gain=PulseFunctions.ff_maxv(prog),
                                 waveform=segs.get("ramp_waveform", "ff_ramp"),
                                 outsel="input")
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
    if segs.get("reverse_steps"):
        _play_staircase(prog, segs["reverse_steps"])
    else:
        prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 stdysel='last',
                                 gain=PulseFunctions.ff_maxv(prog),
                                 waveform=segs.get("reverse_waveform",
                                                   "ff_ramp_reversed"),
                                 outsel="input")
        prog.pulse(ch=cfg["ff_ch"])
    prog.safe_regwi(ff_rp, ff_gain_reg, int(segs.get("park", 0)))


def assert_park(prog, segs, dt_us=0.1, force=False):
    park = int(segs.get("park", 0))
    if park == 0 and not force:
        return
    cfg = prog.cfg
    ramp_us = float(cfg.get("ff_ramp_length", 0.0) or 0.0)
    steps = 1
    if park != 0 and ramp_us > dt_us:
        steps = int(min(max(round(ramp_us / dt_us), 1), 32))
    step_us = (ramp_us / steps) if steps > 1 else dt_us
    length = max(int(prog.us2cycles(step_us, gen_ch=cfg["ff_ch"])), 3)
    for k in range(1, steps + 1):
        prog.set_pulse_registers(ch=cfg["ff_ch"], freq=0, style='const', phase=0,
                                 stdysel='last',
                                 gain=int(round(park * k / steps)), length=length)
        prog.pulse(ch=cfg["ff_ch"])


def sequence_hold_us(cfg, drive_us=0.0, readouts=1, extra_us=0.0):
    read = (float(cfg.get("read_length", 0.0))
            + float(cfg.get("adc_trig_offset", 0.0)) + 1.0)
    reset = 0.0
    if cfg.get("rot_reset") or str(cfg.get("reset_mode", "passive")) not in (
            "passive", "none", "None"):
        iters = int(cfg.get("reset_max_iters", 3) or 3)
        sigma = float(cfg.get("sigma", 0.0) or 0.0)
        reset = iters * (read + 4.0 * sigma
                         + float(cfg.get("reset_thermalization_us", 2.0) or 2.0) + 1.0)
    return reset + float(drive_us) + readouts * read + float(extra_us) + 2.0


def sweep_baseline(cfg, explicit=None):
    if explicit is not None:
        return float(explicit)
    inherited = float(cfg.get("ff_park_gain", 0) or 0)
    if inherited != 0:
        key = round(inherited)
        if key not in _SWEEP_BASELINE_NOTED:
            _SWEEP_BASELINE_NOTED.add(key)
            print(f"[ff_pulse] this experiment sweeps the flux itself, so the "
                  f"ff_park_gain={inherited:g} in your config is not an operating "
                  f"point here.  Sweeping from 0; pass park_gain=... to sweep from "
                  f"a deliberate baseline instead.")
    return 0.0


def park_hold_configured(cfg):
    return (static_park_configured(cfg)
            and int(cfg.get("ff_park_gain", 0) or 0) != 0)


def declare_park_hold(prog):
    prog.do_park_hold = bool(park_hold_configured(prog.cfg))
    if prog.do_park_hold:
        declare_ff(prog)


def build_park_hold(prog, hold_us):
    if not park_hold_configured(prog.cfg):
        return None
    cfg = prog.cfg
    return build_ramp_hold_ramp(
        prog, hold_us=float(hold_us),
        ff_gain=int(cfg.get("ff_park_gain", 0) or 0),
        dt_play_us=cfg.get("dt_pulseplay", 5.0),
        ramp_us=cfg.get("ff_ramp_length", STATE_SAFE_RAMP_US),
        dt_def_us=cfg.get("dt_pulsedef", 0.002),
        park_gain=0, name_prefix="ffpark")


def play_park_up(prog, segs, settle_us=None):
    if segs is None:
        return
    cfg = prog.cfg
    play_ramp_up_hold(prog, segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
    s = flux_settle_us(cfg) if settle_us is None else float(settle_us)
    if s > 0:
        prog.sync_all(prog.us2cycles(s))


def play_park_down(prog, segs):
    if segs is None:
        return
    play_ramp_down(prog, segs)


def drive_estimate_us(cfg):
    style = str(cfg.get("qubit_pulse_style", "const"))
    sigma = float(cfg.get("sigma", 0.0) or 0.0)
    if style == "arb":
        one = 4.0 * sigma
    elif style == "flat_top":
        one = 4.0 * sigma + float(cfg.get("flat_top_length") or 0.0)
    else:
        one = float(cfg.get("qubit_length", 0.0) or 0.0)
    n = max(int(cfg.get("n_pulses", 1) or 1), int(cfg.get("repeats", 1) or 1), 1)
    return one * n


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


_COMP_WARNED = set()


def _check_compensation_conditions(cfg, comp):
    meta = (comp or {}).get("metadata", {}) or {}
    src = str((comp or {}).get("source", "?"))
    now = {"fit_ff_ramp_length_us": float(cfg.get("ff_ramp_length",
                                                  STATE_SAFE_RAMP_US)),
           "fit_dt_pulseplay_us": float(cfg.get("dt_pulseplay", 5.0)),
           "fit_dt_pulsedef_us": float(cfg.get("dt_pulsedef", 0.002))}
    known = {k: meta[k] for k in now if k in meta}
    if not known:
        key = ("legacy", src)
        if key not in _COMP_WARNED:
            _COMP_WARNED.add(key)
            print(f"[flux] WARNING the compensation {src} does not record the flux-pulse "
                  f"conditions it was fitted under.  Its segment edges are only valid for "
                  f"the ramp it was measured with; applying it to a different "
                  f"ff_ramp_length lines the correction up against the wrong part of the "
                  f"waveform.  Re-run step 3a if the ramp has changed since.")
        return
    bad = {k: (known[k], now[k]) for k in known
           if abs(float(known[k]) - now[k]) > 1e-9}
    if bad:
        key = ("mismatch", src, tuple(sorted(bad)))
        if key not in _COMP_WARNED:
            _COMP_WARNED.add(key)
            detail = ", ".join(f"{k}: fitted at {a:g} us, now {b:g} us"
                               for k, (a, b) in sorted(bad.items()))
            print(f"[flux] WARNING the compensation {src} was fitted under different "
                  f"flux-pulse conditions ({detail}).  The segment edges no longer line "
                  f"up with the same features of the waveform.  Re-run step 3a.")


def load_compensation(cfg):
    comp = cfg.get("flux_tail_compensation", None)
    if comp is None:
        return None
    if isinstance(comp, str):
        comp = fpd.load_compensation_json(comp)
    if isinstance(comp, dict):
        _check_compensation_conditions(cfg, comp)
    return comp
