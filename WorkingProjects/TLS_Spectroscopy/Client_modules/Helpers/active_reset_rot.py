import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar


INT32_MAX = 2 ** 31 - 1
DEFAULT_HEADROOM = 4.0
LATCH_RESERVE = 4.0
DEFAULT_MAX_SHIFT = 20

_UID = [0]


def projection_angle(lower_g, upper_g, lower_e, upper_e):
    d_lower = float(np.median(lower_e)) - float(np.median(lower_g))
    d_upper = float(np.median(upper_e)) - float(np.median(upper_g))
    return float(np.arctan2(d_upper, d_lower))


def _gain(theta):
    return abs(float(np.cos(theta))) + abs(float(np.sin(theta)))


def fixed_point_coeffs(theta, max_abs_raw, headroom=DEFAULT_HEADROOM,
                       max_shift=DEFAULT_MAX_SHIFT):
    max_abs = float(max_abs_raw)
    if not np.isfinite(max_abs) or max_abs <= 0:
        raise ValueError(f"max_abs_raw must be positive and finite, got {max_abs_raw!r}")
    budget = INT32_MAX / (float(headroom) * (1.0 + LATCH_RESERVE))
    shift = int(np.floor(np.log2(budget / (_gain(theta) * max_abs))))
    shift = max(0, min(int(max_shift), shift))
    c_int = int(round(float(np.cos(theta)) * (2 ** shift)))
    s_int = int(round(float(np.sin(theta)) * (2 ** shift)))
    return shift, c_int, s_int


def max_projection(shift, theta, max_abs_raw):
    return float((2 ** int(shift)) * _gain(theta) * float(max_abs_raw))


def latch_offset(shift, theta, max_abs_raw, excited_above=True):
    sink = max(int(round(LATCH_RESERVE * max_projection(shift, theta, max_abs_raw))), 1)
    return -sink if excited_above else sink


def check_headroom(shift, theta, max_abs_raw):
    proj = max_projection(shift, theta, max_abs_raw)
    worst = proj + abs(latch_offset(shift, theta, max_abs_raw))
    return worst <= INT32_MAX, worst


def project(lower, upper, c_int, s_int):
    return (int(c_int) * np.asarray(lower, dtype=np.int64)
            + int(s_int) * np.asarray(upper, dtype=np.int64))


def asm_plan(c_int, s_int):
    """Express the projection using only NON-NEGATIVE multiply immediates.

    qick's convert_immediate maps a negative immediate to 2**31 + val rather than
    to two's complement, so `mathi(reg, '*', negative)` is not a pattern this repo
    has ever verified on hardware -- the only precedent is `* -1`.  regwi with a
    negative value IS verified: the production reset runs a negative threshold_raw
    every day.  So keep the multiplies non-negative and carry the sign in the
    combine operator and the comparison sense, which uses only verified patterns.

        acc = |c|*I  (+/-) |s|*Q          <- what the tProc computes
        proj = sign(c) * acc              <- the quantity we actually mean

    Since theta is fitted from the g->e vector, proj_e > proj_g always, so the
    excited blob is above in `acc` exactly when c_int >= 0.
    """
    c_int, s_int = int(c_int), int(s_int)
    same_sign = (c_int >= 0) == (s_int >= 0)
    return {"c_abs": abs(c_int), "s_abs": abs(s_int),
            "combine_op": '+' if same_sign else '-',
            "excited_above": c_int >= 0}


def project_acc(lower, upper, plan):
    """The value the tProc register actually holds, given asm_plan()."""
    lo = np.asarray(lower, dtype=np.int64)
    up = np.asarray(upper, dtype=np.int64)
    term = int(plan["s_abs"]) * up
    return int(plan["c_abs"]) * lo + (term if plan["combine_op"] == '+' else -term)


def thresholds_to_acc(thr, plan):
    """Convert thresholds fitted in projection space into tProc register space.

    choose_thresholds() works on `proj`, where the excited blob is above by
    construction.  The register holds `acc = sign(c) * proj`, so both thresholds
    flip sign when c_int < 0; the block's comparison operators flip with them.
    """
    sign = 1 if plan["excited_above"] else -1
    out = dict(thr)
    out["excite_threshold"] = sign * float(thr["excite_threshold"])
    if thr.get("ground_threshold") is not None:
        out["ground_threshold"] = sign * float(thr["ground_threshold"])
    return out


def separation_report(lower_g, upper_g, lower_e, upper_e, c_int=None, s_int=None,
                      theta=None):
    lg = np.asarray(lower_g, dtype=np.int64)
    ug = np.asarray(upper_g, dtype=np.int64)
    le = np.asarray(lower_e, dtype=np.int64)
    ue = np.asarray(upper_e, dtype=np.int64)
    sep_lower = abs(float(np.median(le)) - float(np.median(lg)))
    sep_upper = abs(float(np.median(ue)) - float(np.median(ug)))
    best_single = max(sep_lower, sep_upper)
    if theta is None:
        theta = projection_angle(lg, ug, le, ue)
    if c_int is None or s_int is None:
        max_abs = float(np.max(np.abs(np.concatenate([lg, ug, le, ue]))))
        _, c_int, s_int = fixed_point_coeffs(theta, max_abs)
    scale = float(np.hypot(c_int, s_int)) or 1.0
    pg = project(lg, ug, c_int, s_int) / scale
    pe = project(le, ue, c_int, s_int) / scale
    sep_rot = abs(float(np.median(pe)) - float(np.median(pg)))
    return {"theta": float(theta), "sep_lower": sep_lower, "sep_upper": sep_upper,
            "sep_best_single": best_single, "sep_rotated": sep_rot,
            "gain_vs_best_single": (sep_rot / best_single) if best_single > 0 else np.nan,
            "proj_g": pg * scale, "proj_e": pe * scale,
            "c_int": int(c_int), "s_int": int(s_int)}


def _rates(proj_g, proj_e, thr):
    return (float(np.mean(np.asarray(proj_g) >= thr)),
            float(np.mean(np.asarray(proj_e) < thr)))


def simulate_reset(a_g, b_g, a_e, b_e, pi_efficiency, iters, start="g"):
    """Residual P(|e>) after `iters` rounds of the three-zone loop.

    a_* is P(latch), b_* is P(fire the pi), both conditioned on the true state.
    States are (g live, e live, g latched, e latched); the latched ones absorb.
    With a_g = a_e = 0 this reduces to the two-zone Markov chain in active_reset.
    """
    eta = float(pi_efficiency)
    gl, el = (1.0, 0.0) if str(start).lower().startswith("g") else (0.0, 1.0)
    gz, ez = 0.0, 0.0
    for _ in range(int(iters)):
        gl_n = gl * (1.0 - a_g - b_g * eta) + el * (b_e * eta)
        el_n = el * (1.0 - a_e - b_e * eta) + gl * (b_g * eta)
        gz += gl * a_g
        ez += el * a_e
        gl, el = gl_n, el_n
    return float(el + ez)


def choose_thresholds(proj_g, proj_e, iters=3, pi_efficiency=ar.DEFAULT_PI_EFFICIENCY,
                      n_candidates=121, three_zone=True):
    pg = np.asarray(proj_g, dtype=np.float64)
    pe = np.asarray(proj_e, dtype=np.float64)
    lo = float(min(pg.min(), pe.min()))
    hi = float(max(pg.max(), pe.max()))
    cands = np.linspace(lo, hi, int(n_candidates))
    best = None
    for excite_thr in cands:
        b_g, b_e = float(np.mean(pg >= excite_thr)), float(np.mean(pe >= excite_thr))
        ground_options = ([g for g in cands if g <= excite_thr] if three_zone
                          else [None])
        for ground_thr in ground_options:
            if ground_thr is None:
                a_g = a_e = 0.0
            else:
                a_g, a_e = float(np.mean(pg < ground_thr)), float(np.mean(pe < ground_thr))
            r_g = simulate_reset(a_g, b_g, a_e, b_e, pi_efficiency, iters, start="g")
            r_e = simulate_reset(a_g, b_g, a_e, b_e, pi_efficiency, iters, start="e")
            worst = max(r_g, r_e)
            if not np.isfinite(worst):
                continue
            if best is None or worst < best["predicted_worst"]:
                p_e_given_g, p_g_given_e = _rates(pg, pe, excite_thr)
                best = {"excite_threshold": float(excite_thr),
                        "ground_threshold": (None if ground_thr is None
                                             else float(ground_thr)),
                        "p_e_given_g": p_e_given_g, "p_g_given_e": p_g_given_e,
                        "p_latch_given_g": a_g, "p_latch_given_e": a_e,
                        "p_fire_given_g": b_g, "p_fire_given_e": b_e,
                        "floor": ar.reset_floor(p_e_given_g, p_g_given_e),
                        "predicted_residual_g": r_g, "predicted_residual_e": r_e,
                        "predicted_worst": worst}
    if best is None:
        raise RuntimeError("no usable threshold: the projected blobs do not separate")
    return best


def scratch_registers(base=1):
    names = ("reg_i", "reg_q", "reg_ground", "reg_excite", "reg_latch")
    return {name: base + i for i, name in enumerate(names)}


def active_reset_rot_block(prog, ro_ch=0, res_ch=None, qubit_ch=None,
                           c_int=None, s_int=None, excite_threshold=None,
                           ground_threshold=None, latch_sink=None, max_iters=3,
                           use_latch=True, three_zone=True, regs=None,
                           adc_trig_offset_us=None, settle_us=None,
                           meas_syncdelay_us=None, thermalization_us=None,
                           page=None, read_delay_us=None, trace_base_addr=None):
    if c_int is None or s_int is None:
        raise ValueError("active_reset_rot_block needs c_int/s_int from "
                         "fixed_point_coeffs(); calibrate with Runners/ResetRotationDev.py")
    if excite_threshold is None:
        raise ValueError("active_reset_rot_block needs excite_threshold (projected units)")
    if use_latch and not three_zone:
        raise ValueError("use_latch=True requires three_zone=True: the latch is set in "
                         "the confident-ground zone, which only exists when there are "
                         "three zones.  Use three_zone=False, use_latch=False for the "
                         "rotated two-zone control arm.")
    if three_zone and ground_threshold is None:
        raise ValueError("three_zone=True needs ground_threshold (projected units)")
    if three_zone:
        _plan = asm_plan(c_int, s_int)
        _ok = (float(ground_threshold) <= float(excite_threshold)
               if _plan["excited_above"] else
               float(ground_threshold) >= float(excite_threshold))
        if not _ok:
            raise ValueError(
                f"ground_threshold ({ground_threshold}) is on the wrong side of "
                f"excite_threshold ({excite_threshold}) for excited_above="
                f"{_plan['excited_above']}: the confident-ground zone must sit on the "
                f"opposite side of the excited zone.")
    cfg = prog.cfg
    if settle_us is None:
        settle_us = float(cfg.get("reset_settle_us", 0.05))
    if meas_syncdelay_us is None:
        meas_syncdelay_us = float(cfg.get("reset_meas_syncdelay_us", 4.0))
    if read_delay_us is None:
        read_delay_us = cfg.get("reset_read_delay_us", ar.DEFAULT_READ_DELAY_US)
    res_ch = cfg["res_ch"] if res_ch is None else res_ch
    qubit_ch = cfg["qubit_ch"] if qubit_ch is None else qubit_ch
    tproc_ch = ar.feedback_channel(prog.soccfg, ro_ch)
    if tproc_ch < 0:
        raise RuntimeError(
            f"Readout {ro_ch} does not feed back into the tProc (tproc_ch=-1): this "
            "firmware cannot do active reset.  Use reset_mode='passive'.")

    page = prog.ch_page(qubit_ch) if page is None else page
    regs = dict(scratch_registers() if regs is None else regs)
    if not three_zone:
        regs.pop("reg_ground", None)
    if not use_latch:
        regs.pop("reg_latch", None)
    if len(set(regs.values())) != len(regs):
        raise ValueError(f"active_reset_rot_block scratch registers must be distinct: {regs}")
    ar._assert_scratch_free(prog, page, regs)
    r_i, r_q, r_excite = regs["reg_i"], regs["reg_q"], regs["reg_excite"]
    r_ground = regs.get("reg_ground")
    r_latch = regs.get("reg_latch")

    off = (prog.us2cycles(cfg["adc_trig_offset"]) if adc_trig_offset_us is None
           else prog.us2cycles(adc_trig_offset_us))
    clear_us = float(cfg.get("reset_thermalization_us", 25.0)
                     if thermalization_us is None else thermalization_us)
    if clear_us < 0:
        raise ValueError("reset_thermalization_us must be non-negative")
    read_delay_cycles = (None if read_delay_us is None
                         else max(int(prog.us2cycles(float(read_delay_us))), 0))
    if use_latch and latch_sink is None:
        raise ValueError("use_latch=True needs latch_sink from latch_offset()")

    plan = asm_plan(c_int, s_int)
    if plan["excited_above"]:
        skip_pi_op, not_ground_op, sink_sign = '<', '>=', -1
    else:
        skip_pi_op, not_ground_op, sink_sign = '>', '<=', +1
    if use_latch and np.sign(latch_sink) not in (0, sink_sign):
        raise ValueError(
            f"latch_sink has the wrong sign for this projection: excited_above="
            f"{plan['excited_above']} needs a {'negative' if sink_sign < 0 else 'positive'} "
            f"sink so a latched shot lands in the confident-ground zone, got {latch_sink}.  "
            f"Use latch_offset(shift, theta, max_abs, excited_above=...).")

    _UID[0] += 1
    uid = _UID[0]
    sync_cycles = prog.us2cycles(meas_syncdelay_us)
    gap_cycles = prog.us2cycles(ar.MIN_READ_TO_PULSE_GAP_US)

    prog.regwi(page, r_excite, int(round(excite_threshold)), "rot reset excite threshold")
    if three_zone:
        prog.regwi(page, r_ground, int(round(ground_threshold)), "rot reset ground threshold")
    if use_latch:
        prog.regwi(page, r_latch, 0, "rot reset latch (0 = live)")

    for i in range(int(max_iters)):
        prog.measure(pulse_ch=res_ch, adcs=[ro_ch], adc_trig_offset=off,
                     wait=True, syncdelay=None)
        adc_ts = getattr(prog, "_adc_ts", None)
        dac_ts = getattr(prog, "_dac_ts", None)
        if read_delay_cycles is not None and adc_ts is None and hasattr(prog, "waiti"):
            raise RuntimeError(
                "reset_read_delay_us was requested but this program exposes no _adc_ts "
                "timeline, so the read delay cannot be placed safely.  The tProc read "
                "register is one measurement stale without it.")
        if read_delay_cycles is not None and adc_ts is not None:
            adc_end = int(max(adc_ts))
            pulse_at = int(max(list(dac_ts) + list(adc_ts))) + sync_cycles
            if adc_end + read_delay_cycles + gap_cycles > pulse_at:
                room = prog.cycles2us(max(pulse_at - adc_end - gap_cycles, 0))
                raise ValueError(
                    f"reset_read_delay_us={float(read_delay_us):g} leaves no room before "
                    f"the conditional pi: at most {room:.2f} us fits.  Raise "
                    f"reset_meas_syncdelay_us (currently {float(meas_syncdelay_us):g} us).")
            prog.waiti(0, adc_end + read_delay_cycles)
        prog.read(tproc_ch, page, "lower", r_i)
        prog.read(tproc_ch, page, "upper", r_q)
        prog.mathi(page, r_i, r_i, '*', int(plan["c_abs"]))
        prog.mathi(page, r_q, r_q, '*', int(plan["s_abs"]))
        prog.math(page, r_i, r_i, plan["combine_op"], r_q)
        if use_latch:
            prog.math(page, r_i, r_i, '+', r_latch)
        prog.sync_all(sync_cycles)

        done = f"ARR_DONE_{uid}_{i}"
        nopi = f"ARR_NOPI_{uid}_{i}"
        prog.condj(page, r_i, skip_pi_op, r_excite, nopi)
        prog.pulse(ch=qubit_ch)
        if three_zone:
            prog.condj(page, r_excite, '>=', r_excite, done)
            prog.label(nopi)
            prog.condj(page, r_i, not_ground_op, r_ground, done)
            if use_latch:
                prog.regwi(page, r_latch, int(latch_sink))
            prog.label(done)
        else:
            prog.label(nopi)
        if trace_base_addr is not None:
            prog.memwi(page, r_i, int(trace_base_addr) + 1 + i)
        prog.sync_all(prog.us2cycles(settle_us))
    if clear_us > 0:
        prog.sync_all(prog.us2cycles(clear_us))
