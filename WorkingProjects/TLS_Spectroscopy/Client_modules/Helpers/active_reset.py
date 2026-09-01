import json
import os

import numpy as np


RESET_MODES = ("passive", "active", "feedback", "feedback_herald")
FEEDBACK_MODES = ("feedback", "feedback_herald")
HERALD_MODES = ("active", "feedback_herald")


def reset_mode_of(cfg_or_mode):
    mode = (cfg_or_mode.get("reset_mode", "passive")
            if hasattr(cfg_or_mode, "get") else cfg_or_mode)
    return str("passive" if mode is None else mode).strip().lower()


def uses_feedback(cfg_or_mode):
    return reset_mode_of(cfg_or_mode) in FEEDBACK_MODES


def uses_rotated(cfg):
    try:
        return bool(cfg.get("rot_reset"))
    except Exception:
        return False


def rotated_probe_record(rec):
    if not isinstance(rec, dict) or rec.get("use") != "rot":
        return False
    params = rec.get("rot_reset")
    return isinstance(params, dict) and all(
        key in params for key in ("c_int", "s_int", "excite_threshold"))


def feedback_runtime_from_probe(rec, max_iters=3, thermalization_us=25.0,
                                post_measure_delay_us=None):
    if not rotated_probe_record(rec):
        raise ValueError("a validated rotated reset probe record is required")
    runtime = {
        "reset_mode": "feedback",
        "reset_threshold_raw": int(rec["threshold_raw"]),
        "reset_oper": str(rec.get("oper", "lower")),
        "reset_ground_below": bool(rec.get("ground_below", True)),
        "reset_max_iters": int(max_iters),
        "reset_thermalization_us": float(thermalization_us),
        "rot_reset": dict(rec["rot_reset"]),
    }
    runtime["rot_reset"]["max_iters"] = int(max_iters)
    if post_measure_delay_us is not None:
        runtime["active_reset_post_measure_delay_us"] = float(
            post_measure_delay_us)
    return runtime


def heralds(cfg_or_mode):
    return reset_mode_of(cfg_or_mode) in HERALD_MODES


def herald_keep(i0, q0, calib_params):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
        discriminate_shots)
    herald_calib = dict(calib_params)
    herald_calib["threshold"] = calib_params.get("ground_threshold",
                                                 calib_params["threshold"])
    return np.asarray(discriminate_shots(i0, q0, herald_calib)) == 0


DEFAULT_PI_EFFICIENCY = 0.8


def reset_floor(p_e_given_g, p_g_given_e):
    peg = float(p_e_given_g)
    denom = peg + 1.0 - float(p_g_given_e)
    return peg / denom if denom > 1e-12 else float("nan")


def predicted_residuals(p_e_given_g, p_g_given_e, pi_efficiency, iters):
    peg = float(p_e_given_g)
    pge = float(p_g_given_e)
    span = peg + 1.0 - pge
    if span <= 1e-12:
        return 1.0, 0.0
    floor = peg / span
    decay = (1.0 - min(1.0, max(0.0, float(pi_efficiency)) * span)) ** int(iters)
    return floor + (1.0 - floor) * decay, floor * (1.0 - decay)


def infer_pi_efficiency(p_e_given_g, p_g_given_e, iters, residual_from_e):
    peg = float(p_e_given_g)
    span = peg + 1.0 - float(p_g_given_e)
    floor = reset_floor(peg, p_g_given_e)
    obs = float(residual_from_e)
    if not np.isfinite(obs) or span <= 1e-12 or not np.isfinite(floor):
        return float("nan")
    frac = (obs - floor) / (1.0 - floor)
    if frac <= 0.0:
        return 1.0
    if frac >= 1.0:
        return 0.0
    decay = frac ** (1.0 / max(1, int(iters)))
    return float(min(1.0, max(0.0, (1.0 - decay) / span)))


def _threshold_rates(ground, excited, threshold, ground_below):
    if ground_below:
        return (float(np.mean(ground >= threshold)),
                float(np.mean(excited < threshold)))
    return (float(np.mean(ground <= threshold)),
            float(np.mean(excited > threshold)))


def _threshold_candidates(ground, excited):
    values = np.unique(np.concatenate((np.asarray(ground, dtype=np.int64).ravel(),
                                       np.asarray(excited, dtype=np.int64).ravel())))
    return np.unique(np.concatenate((values, values + 1)))


def fit_assignment_threshold(ground, excited):
    ground = np.asarray(ground, dtype=np.int64).ravel()
    excited = np.asarray(excited, dtype=np.int64).ravel()
    best = None
    for ground_below in (True, False):
        for threshold in _threshold_candidates(ground, excited):
            peg, pge = _threshold_rates(ground, excited, threshold, ground_below)
            item = {"threshold_raw": int(threshold), "ground_below": bool(ground_below),
                    "fidelity": 1.0 - 0.5 * (peg + pge),
                    "p_e_given_g": peg, "p_g_given_e": pge}
            if best is None or item["fidelity"] > best["fidelity"]:
                best = item
    return best


def fit_reset_threshold(ground, excited, iters=3, pi_efficiency=DEFAULT_PI_EFFICIENCY):
    ground = np.asarray(ground, dtype=np.int64).ravel()
    excited = np.asarray(excited, dtype=np.int64).ravel()
    best = None
    for ground_below in (True, False):
        for threshold in _threshold_candidates(ground, excited):
            peg, pge = _threshold_rates(ground, excited, threshold, ground_below)
            r_e, r_g = predicted_residuals(peg, pge, pi_efficiency, iters)
            worst = max(r_e, r_g)
            if not np.isfinite(worst):
                continue
            item = {"threshold_raw": int(threshold), "ground_below": bool(ground_below),
                    "fidelity": 1.0 - 0.5 * (peg + pge),
                    "p_e_given_g": peg, "p_g_given_e": pge,
                    "reset_floor": reset_floor(peg, pge),
                    "predicted_residual_e": r_e, "predicted_residual_g": r_g,
                    "predicted_worst": worst}
            if best is None or worst < best["predicted_worst"]:
                best = item
    return best


MAX_RESIDUAL_ABOVE_FLOOR = 0.12
MAX_USABLE_FLOOR = 0.40
FUNCTIONAL_RESIDUAL_MAX = 0.45
FUNCTIONAL_BASELINE_BAND = (0.7, 1.3)


def reset_functional(residual):
    if not residual:
        return False
    worst = max(float(residual.get("reset_ground", float("nan"))),
                float(residual.get("reset_excited", float("nan"))))
    base = float(residual.get("baseline", float("nan")))
    return bool(np.isfinite(worst) and worst < FUNCTIONAL_RESIDUAL_MAX
                and np.isfinite(base)
                and FUNCTIONAL_BASELINE_BAND[0] <= base <= FUNCTIONAL_BASELINE_BAND[1])


def reset_verdict(p_e_given_g, p_g_given_e, residual_g, residual_e, baseline=None,
                  max_above_floor=MAX_RESIDUAL_ABOVE_FLOOR,
                  max_floor=MAX_USABLE_FLOOR):
    floor = reset_floor(p_e_given_g, p_g_given_e)
    rg, re_ = float(residual_g), float(residual_e)
    worst = max(abs(rg), abs(re_))
    above = worst - floor if np.isfinite(floor) else float("nan")
    reasons = []
    if not (np.isfinite(rg) and np.isfinite(re_)):
        reasons.append(f"the end-to-end residuals are not finite (|g>={rg}, |e>={re_}), "
                       f"so the reset was never actually verified -- refusing rather "
                       f"than assuming it works")
    if not np.isfinite(floor) or floor > float(max_floor):
        reasons.append(f"the readout leaves a reset floor of {floor:.3f}, above the "
                       f"{float(max_floor):.2f} at which conditional reset stops being "
                       f"worth doing")
    if np.isfinite(above) and above > float(max_above_floor):
        reasons.append(f"the reset sits {above:.3f} above its own floor of {floor:.3f}, "
                       f"more than the {float(max_above_floor):.2f} allowed -- the loop "
                       f"is not converging, which is a pi or feedback problem rather "
                       f"than a readout one")
    if baseline is not None and abs(float(baseline) - 1.0) > 0.35:
        reasons.append(f"the no-reset baseline is {float(baseline):+.3f} instead of ~1.0, "
                       f"so the prepared |e> or the projection is wrong")
    return {"ok": not reasons, "floor": floor, "worst": worst,
            "above_floor": above, "reasons": reasons}


def to_signed32(v):
    v = int(v) & 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


def feedback_channel(soccfg, ro_ch=0):
    try:
        return int(soccfg['readouts'][ro_ch]['tproc_ch'])
    except (KeyError, IndexError, TypeError, ValueError):
        return -1


def active_reset_supported(soccfg, ro_ch=0):
    return feedback_channel(soccfg, ro_ch) >= 0


_UID = [0]

TRACE_WORDS_PER_ITER = 2

DEFAULT_READ_DELAY_US = 2.0

MIN_READ_TO_PULSE_GAP_US = 1.0


def trace_word_count(max_iters):
    return 1 + TRACE_WORDS_PER_ITER * int(max_iters)


def _soccfg_section(prog, key):
    try:
        return list(prog.soccfg[key])
    except (KeyError, TypeError, IndexError, AttributeError):
        return []


def reserved_registers(prog, page):
    reserved = {0}
    if int(page) == 0:
        reserved.update({13, 14, 15, 31})
    for section, field in (("gens", "tproc_ch"), ("readouts", "tproc_ctrl")):
        for entry in _soccfg_section(prog, section):
            try:
                tproc_ch = entry.get(field) if hasattr(entry, "get") else entry[field]
            except (KeyError, TypeError, IndexError):
                continue
            if tproc_ch is None:
                continue
            try:
                tproc_ch = int(tproc_ch)
                if prog._ch_page_tproc(tproc_ch) != int(page):
                    continue
                for name in prog.pulse_registers:
                    reserved.add(prog._sreg_tproc(tproc_ch, name))
            except (TypeError, ValueError, AttributeError, KeyError):
                continue
    return reserved


def _assert_scratch_free(prog, page, named_regs):
    reserved = reserved_registers(prog, page)
    clashes = {name: reg for name, reg in named_regs.items() if int(reg) in reserved}
    if not clashes:
        return
    detail = ", ".join(f"{name}=r{reg}" for name, reg in sorted(clashes.items()))
    raise ValueError(
        f"active_reset_block scratch registers collide with reserved tProc registers on "
        f"page {int(page)}: {detail}.  Reserved on this page: "
        f"{sorted(reserved)}.  Writing a threshold or read value into a pulse register "
        f"silently retunes the drive (this caused the flat-line T1 artifact).  Pass "
        f"reg_val/reg_thr/reg_flag from the free scratch set "
        f"{sorted(set(range(1, 32)) - reserved)} instead.")


def active_reset_block(prog, ro_ch=0, res_ch=None, qubit_ch=None, threshold_raw=None,
                       ground_below=True, oper="lower", max_iters=3,
                       adc_trig_offset_us=None, settle_us=None, meas_syncdelay_us=None,
                       thermalization_us=None, page=None, reg_val=None, reg_thr=None,
                       read_delay_us=None, force_flip=None, trace_base_addr=None,
                       reg_flag=None, allow_legacy=False):
    try:
        rot_params = prog.cfg.get("rot_reset")
    except Exception:
        rot_params = None
    if rot_params:
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
            active_reset_rot)
        missing = [k for k in ("c_int", "s_int", "excite_threshold")
                   if k not in rot_params]
        if missing:
            raise ValueError(
                f"cfg['rot_reset'] engages the rotated reset but is missing "
                f"{missing}; calibrate it with probe_reset_params")
        return active_reset_rot.active_reset_rot_block(
            prog, ro_ch=ro_ch, res_ch=res_ch, qubit_ch=qubit_ch,
            c_int=rot_params["c_int"], s_int=rot_params["s_int"],
            excite_threshold=rot_params["excite_threshold"],
            max_iters=int(rot_params.get("max_iters", max_iters)),
            adc_trig_offset_us=adc_trig_offset_us, settle_us=settle_us,
            meas_syncdelay_us=meas_syncdelay_us,
            thermalization_us=thermalization_us, page=page,
            read_delay_us=read_delay_us, three_zone=False, use_latch=False)
    if not allow_legacy:
        raise RuntimeError(
            "feedback reset requires a validated cfg['rot_reset']; use passive "
            "reset when rotated calibration is unavailable")
    if threshold_raw is None:
        raise ValueError("active_reset_block needs threshold_raw (raw accumulator units); "
                         "calibrate it with Experiments/mActiveResetProbe.py.")
    cfg = prog.cfg
    if settle_us is None:
        settle_us = float(cfg.get("reset_settle_us", 0.05))
    if meas_syncdelay_us is None:
        meas_syncdelay_us = float(cfg.get("reset_meas_syncdelay_us", 4.0))
    if read_delay_us is None:
        read_delay_us = cfg.get("reset_read_delay_us", DEFAULT_READ_DELAY_US)
    if force_flip is None:
        force_flip = bool(cfg.get("reset_force_flip", False))
    if trace_base_addr is None:
        trace_base_addr = cfg.get("reset_trace_base_addr", None)
    res_ch = cfg["res_ch"] if res_ch is None else res_ch
    qubit_ch = cfg["qubit_ch"] if qubit_ch is None else qubit_ch
    tproc_ch = feedback_channel(prog.soccfg, ro_ch)
    if tproc_ch < 0:
        raise RuntimeError(
            f"Readout {ro_ch} does not feed back into the tProc (tproc_ch=-1): this "
            "firmware cannot do active reset.  Use reset_mode='passive'.")

    page = prog.ch_page(qubit_ch) if page is None else page
    reg_val = 1 if reg_val is None else reg_val
    reg_thr = 2 if reg_thr is None else reg_thr
    reg_flag = 6 if reg_flag is None else reg_flag
    named = {"reg_val": reg_val, "reg_thr": reg_thr}
    if trace_base_addr is not None:
        named["reg_flag"] = reg_flag
    if len(set(named.values())) != len(named):
        raise ValueError(f"active_reset_block scratch registers must be distinct: {named}")
    _assert_scratch_free(prog, page, named)
    off = (prog.us2cycles(cfg["adc_trig_offset"]) if adc_trig_offset_us is None
           else prog.us2cycles(adc_trig_offset_us))
    clear_us = (cfg.get("reset_thermalization_us", 25.0)
                if thermalization_us is None else thermalization_us)
    clear_us = float(clear_us)
    if clear_us < 0:
        raise ValueError("reset_thermalization_us must be non-negative")
    read_delay_cycles = (None if read_delay_us is None
                         else max(int(prog.us2cycles(float(read_delay_us))), 0))

    _UID[0] += 1
    ground_op = "<" if ground_below else ">"

    prog.regwi(page, reg_thr, int(threshold_raw), "active-reset threshold (raw)")
    if trace_base_addr is not None:
        prog.memwi(page, reg_thr, int(trace_base_addr))
    sync_cycles = prog.us2cycles(meas_syncdelay_us)
    gap_cycles = prog.us2cycles(MIN_READ_TO_PULSE_GAP_US)
    for i in range(int(max_iters)):
        prog.measure(pulse_ch=res_ch, adcs=[ro_ch], adc_trig_offset=off,
                     wait=True, syncdelay=None)
        adc_ts = getattr(prog, "_adc_ts", None)
        dac_ts = getattr(prog, "_dac_ts", None)
        if read_delay_cycles is not None and adc_ts is None and hasattr(prog, "waiti"):
            raise RuntimeError(
                "reset_read_delay_us was requested but this program exposes no _adc_ts "
                "timeline, so the read delay cannot be placed safely.  The tProc read "
                "register is one measurement stale without it.  Pass "
                "read_delay_us=None only if you accept that.")
        if read_delay_cycles is not None and adc_ts is not None:
            adc_end = int(max(adc_ts))
            pulse_at = int(max(list(dac_ts) + list(adc_ts))) + sync_cycles
            if adc_end + read_delay_cycles + gap_cycles > pulse_at:
                room = prog.cycles2us(max(pulse_at - adc_end - gap_cycles, 0))
                raise ValueError(
                    f"reset_read_delay_us={float(read_delay_us):g} leaves no room before "
                    f"the conditional pi: the ADC window closes at {adc_end} cycles and "
                    f"the pi is scheduled at {pulse_at}, so at most {room:.2f} us of read "
                    f"delay fits (keeping a {MIN_READ_TO_PULSE_GAP_US:g} us guard).  The "
                    f"tProc read register is one measurement stale unless it is given "
                    f"~0.1 us to settle, so raise reset_meas_syncdelay_us (currently "
                    f"{float(meas_syncdelay_us):g} us) rather than dropping the delay.")
            prog.waiti(0, adc_end + read_delay_cycles)
        prog.read(tproc_ch, page, oper, reg_val)
        prog.sync_all(sync_cycles)
        skip = f"AR_SKIP_{_UID[0]}_{i}"
        if trace_base_addr is not None:
            prog.regwi(page, reg_flag, 0)
        if not force_flip:
            prog.condj(page, reg_val, ground_op, reg_thr, skip)
        if trace_base_addr is not None:
            prog.regwi(page, reg_flag, 1)
        prog.pulse(ch=qubit_ch)
        if not force_flip:
            prog.label(skip)
        if trace_base_addr is not None:
            base = int(trace_base_addr) + 1 + TRACE_WORDS_PER_ITER * i
            prog.memwi(page, reg_val, base)
            prog.memwi(page, reg_flag, base + 1)
        prog.sync_all(prog.us2cycles(settle_us))
    if clear_us > 0:
        prog.sync_all(prog.us2cycles(clear_us))


def active_reset_readouts(cfg):
    if not uses_feedback(cfg):
        return 0
    return int(cfg.get("reset_max_iters", 3))


RESET_PROFILE_KEYS = ("read_pulse_freq", "read_pulse_gain", "read_length",
                      "qubit_pi_freq", "qubit_pi_gain", "sigma", "ff_park_gain",
                      "qubit_pulse_style")


def _profile_path(outer_folder, path):
    return os.path.join(str(outer_folder or "."), f"reset_profile_{path}.json")


def _profile_key(cfg):
    return {k: cfg.get(k) for k in RESET_PROFILE_KEYS}


def load_reset_profile(cfg, path="q", outer_folder=""):
    fname = _profile_path(outer_folder, path)
    try:
        with open(fname) as fh:
            saved = json.load(fh)
    except Exception:
        return None
    if saved.get("key") != _profile_key(cfg):
        print(f"[reset] cached profile {fname} was taken at different readout/pulse "
              f"settings; re-probing")
        return None
    rec = saved.get("record")
    if not rotated_probe_record(rec):
        return None
    print(f"[reset] reusing the validated reset profile from {fname}")
    return rec


def save_reset_profile(rec, cfg, path="q", outer_folder=""):
    if not rotated_probe_record(rec):
        return
    fname = _profile_path(outer_folder, path)
    try:
        os.makedirs(os.path.dirname(fname) or ".", exist_ok=True)
        with open(fname, "w") as fh:
            json.dump({"key": _profile_key(cfg), "record": rec}, fh, indent=2)
        print(f"[reset] saved the validated reset profile to {fname}")
    except Exception as exc:
        print(f"[reset] could not save the reset profile ({type(exc).__name__})")


def probe_reset_params(soc, soccfg, base_cfg, path="q", outer_folder="", shots=2000,
                       validate=True, min_raw_fidelity=0.60, min_raw_shots=200,
                       diagnostic_callback=None,
                       max_residual_above_floor=MAX_RESIDUAL_ABOVE_FLOOR,
                       max_usable_floor=MAX_USABLE_FLOOR,
                       reset_max_iters=None, gate_policy="best_effort",
                       allow_legacy_result=False):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
        ActiveResetProbe)
    cfg = dict(base_cfg)
    cfg["shots"] = int(shots)
    cfg["reps"] = int(shots)
    if reset_max_iters is not None:
        cfg["reset_max_iters"] = int(reset_max_iters)
    cfg["qubit_gain"] = int(cfg.get("qubit_pi_gain", cfg.get("qubit_gain", 0)))
    try:
        probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=path,
                                 outerFolder=outer_folder, suffix="Reset_Threshold", cfg=cfg)
        data = probe.acquire().get("data", {})
        if callable(diagnostic_callback):
            try:
                diagnostic_callback(getattr(probe, "raw_shots", None), data)
            except Exception:
                # Diagnostic persistence must never decide whether reset is usable.
                pass
    except Exception as exc:
        print(f"[reset] threshold probe failed ({exc}) -- falling back to passive relax.")
        return None
    if not data.get("supported") or not data.get("recommended"):
        print("[reset] no usable feedback discrimination -- falling back to passive relax.")
        return None
    results = data.get("results", {})
    try:
        lower = abs(int(results["excited"]["raw_lower"])
                    - int(results["ground"]["raw_lower"]))
        upper = abs(int(results["excited"]["raw_upper"])
                    - int(results["ground"]["raw_upper"]))
        purity_ok = max(lower, upper) >= 3 * max(1, min(lower, upper))
    except Exception:
        purity_ok = False
    if not purity_ok:
        print("[reset] discrimination is not concentrated on one raw accumulator "
              "half -- falling back to passive relax.")
        return None
    raw_fidelity = float(data.get("raw_assignment_fidelity", -float("inf")))
    try:
        buffered_shots = int(data.get("raw_assignment_shots", 0))
    except Exception:
        buffered_shots = 0
    if buffered_shots < int(min_raw_shots):
        print(f"[reset] only {buffered_shots} buffered threshold shots were available "
              f"(need {int(min_raw_shots)}) -- falling back to passive relax.")
        return None
    if not raw_fidelity >= float(min_raw_fidelity):
        print(f"[reset] raw held-shot assignment F={raw_fidelity:.3f} is below "
              f"{float(min_raw_fidelity):.3f} -- there is essentially no per-shot "
              "discrimination; falling back to passive relax.")
        return None
    if raw_fidelity < 0.80:
        print(f"[reset] NOTE raw assignment F={raw_fidelity:.3f} is modest.  That is not "
              f"by itself a reason to refuse active reset: the reset floor is set by "
              f"P(e|g)/(P(e|g)+1-P(g|e)), and the reset-optimal threshold deliberately "
              f"trades F away to lower it.  Judging on the floor below.")
    rec = dict(data["recommended"])
    rec["raw_assignment_fidelity"] = raw_fidelity
    rec["raw_assignment_errors"] = dict(data.get("raw_assignment_errors", {}))
    rec["raw_assignment_shots"] = buffered_shots
    legacy_ok = True
    legacy_residual = None
    rot_residual = None
    rot_params_kept = None
    if validate:
        try:
            residual = probe._residual_at(
                float(cfg.get("res_phase", 0.0)), int(rec["threshold_raw"]),
                bool(rec["ground_below"]), max(500, int(shots)), oper=rec["oper"])
        except Exception as exc:
            print(f"[reset] legacy end-to-end validation failed ({exc}) -- trying "
                  "the ROTATED scheme before giving up on active reset.")
            legacy_ok = False
        else:
            legacy_residual = residual
            errs = rec.get("raw_assignment_errors", {})
            verdict = reset_verdict(errs.get("p_e_given_g", float("nan")),
                                    errs.get("p_g_given_e", float("nan")),
                                    residual.get("reset_ground", float("nan")),
                                    residual.get("reset_excited", float("nan")),
                                    baseline=residual.get("baseline", None),
                                    max_above_floor=max_residual_above_floor,
                                    max_floor=max_usable_floor)
            print(f"[reset] legacy residual {verdict['worst']:.3f} against a floor of "
                  f"{verdict['floor']:.3f} ({verdict['above_floor']:+.3f} above it)")
            if not verdict["ok"]:
                for reason in verdict["reasons"]:
                    print(f"[reset] {reason}")
                print("[reset] the LEGACY reset failed its end-to-end gate -- trying "
                      "the ROTATED scheme before falling back to passive.")
                legacy_ok = False
            else:
                rec["validation"] = residual
                rec["verdict"] = verdict
    rec["use"] = "legacy" if legacy_ok and allow_legacy_result else None
    raw_shots = getattr(probe, "raw_shots", None)
    if raw_shots and "ground" in raw_shots and "excited" in raw_shots:
        try:
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
                active_reset_rot)
            eta = (data.get("reset_threshold_tuning") or {}).get("pi_efficiency")
            if eta is None or not np.isfinite(eta) or eta <= 0:
                eta = DEFAULT_PI_EFFICIENCY
            iters = int(cfg.get("reset_max_iters", 3))
            fit = active_reset_rot.fit_raw_calibration(
                raw_shots["ground"]["lower"], raw_shots["ground"]["upper"],
                raw_shots["excited"]["lower"], raw_shots["excited"]["upper"],
                iters, float(min(1.0, eta)))
            rot_params = active_reset_rot.reset_params_from_fit(fit, iters)
            rep = fit["report"]
            print(f"[reset] rotated projection: theta={np.rad2deg(fit['theta']):+.1f} deg, "
                  f"separation {rep['sep_best_single']:.0f} (best single) -> "
                  f"{rep['sep_rotated']:.0f} (rotated), gain "
                  f"{rep['gain_vs_best_single']:.2f}x")
            if validate:
                rot_residual = probe._residual_at(
                    float(cfg.get("res_phase", 0.0)), int(rec["threshold_raw"]),
                    bool(rec["ground_below"]), max(500, int(shots)),
                    oper=rec["oper"], rot_reset=rot_params)
                tp = fit["two_proj"]
                rot_verdict = reset_verdict(
                    tp["p_fire_given_g"], 1.0 - tp["p_fire_given_e"],
                    rot_residual.get("reset_ground", float("nan")),
                    rot_residual.get("reset_excited", float("nan")),
                    baseline=rot_residual.get("baseline", None),
                    max_above_floor=max_residual_above_floor,
                    max_floor=max_usable_floor)
                print(f"[reset] rotated residual {rot_verdict['worst']:.3f} against a "
                      f"floor of {rot_verdict['floor']:.3f} "
                      f"({rot_verdict['above_floor']:+.3f} above it)")
                rot_params_kept = rot_params
                if rot_verdict["ok"]:
                    rec["rot_reset"] = rot_params
                    rec["rot_validation"] = rot_residual
                    rec["rot_verdict"] = rot_verdict
                    rec["use"] = "rot"
                else:
                    for reason in rot_verdict["reasons"]:
                        print(f"[reset] rotated: {reason}")
                    if legacy_ok:
                        if allow_legacy_result:
                            print("[reset] the ROTATED reset failed its own end-to-end "
                                  "check; the validated LEGACY reset stays in charge "
                                  "for this diagnostic session.")
                        else:
                            print("[reset] the ROTATED reset failed its own end-to-end "
                                  "check; production reset will use passive relax.")
                    else:
                        print("[reset] the ROTATED reset failed its end-to-end "
                              "check as well.")
            else:
                rec["rot_reset"] = rot_params
                rec["use"] = "rot"
        except Exception as exc:
            suffix = ("the legacy reset stays in charge for this diagnostic session."
                      if allow_legacy_result else
                      "production reset will use passive relax.")
            print(f"[reset] rotated calibration failed ({exc}); {suffix}")
    if rec["use"] is None and str(gate_policy) == "best_effort":
        candidates = []
        if reset_functional(rot_residual) and rot_params_kept:
            worst = max(rot_residual["reset_ground"], rot_residual["reset_excited"])
            candidates.append((worst, "rot", rot_residual))
        if allow_legacy_result and reset_functional(legacy_residual):
            worst = max(legacy_residual["reset_ground"],
                        legacy_residual["reset_excited"])
            candidates.append((worst, "legacy", legacy_residual))
        if candidates:
            candidates.sort(key=lambda c: c[0])
            worst, scheme, resid = candidates[0]
            rec["use"] = scheme
            rec["degraded"] = True
            rec["degraded_residuals"] = dict(resid)
            if scheme == "rot":
                rec["rot_reset"] = rot_params_kept
            print(f"[reset] no scheme met the validated bar, but the {scheme} reset "
                  f"IS functional (measured residuals |g> "
                  f"{resid['reset_ground']:+.3f}, |e> {resid['reset_excited']:+.3f}) "
                  f"-- running it BEST-EFFORT rather than dropping to passive.")
            print("[reset] rationale: a mediocre active reset at ~0.1 ms/shot beats "
                  "a 2 ms passive relax ~20x in throughput, and the matched-"
                  "reference 3-point method cancels the reset residual to first "
                  "order.  Recalibrate the pi when convenient; pass "
                  "gate_policy='strict' to restore the hard gate.")
    if rec["use"] is None:
        print("[reset] no functional reset at all (residuals near or above "
              f"{FUNCTIONAL_RESIDUAL_MAX:g}, or the no-reset baseline is broken) "
              "-- falling back to passive relax.  This means the feedback loop is "
              "not resetting, not merely resetting poorly; check the pi and the "
              "feedback path.")
        return None
    if rec["use"] == "rot":
        print("[reset] the ROTATED reset is calibrated, hardware-validated, and "
              "selected; res_phase alignment is no longer load-bearing.")
        if not legacy_ok:
            print("[reset] NOTE: the legacy parameters in this calibration did NOT "
                  "pass validation; they remain recorded but are not a trusted "
                  "fallback this session.")
    print(f"[reset] fresh discrimination: oper={rec['oper']} threshold_raw={rec['threshold_raw']} "
          f"ground_below={rec['ground_below']}")
    return rec


DRIFT_PI_SPAN_MHZ = 6.0
DRIFT_PI_STEP_MHZ = 0.75


def reset_cfg_from_record(cfg, rec, max_iters=None, thermalization_us=None):
    out = dict(cfg)
    rp = rec.get("rot_reset") or {}
    out["reset_threshold_raw"] = int(rec["threshold_raw"])
    out["reset_oper"] = str(rec["oper"])
    out["reset_ground_below"] = bool(rec["ground_below"])
    if rp:
        out["rot_reset"] = dict(rp)
        out["rot_c_int"] = rp["c_int"]
        out["rot_s_int"] = rp["s_int"]
        out["rot_excite_threshold"] = rp["excite_threshold"]
    if max_iters is not None:
        out["reset_max_iters"] = int(max_iters)
    if thermalization_us is not None:
        out["reset_thermalization_us"] = float(thermalization_us)
    return out


def _drift_shots(soc, soccfg, cfg):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
        FFT1Program)
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
        suppress_stdout)
    with suppress_stdout():
        i0, q0, i1, q1 = FFT1Program(soccfg, cfg).acquire(soc, load_pulses=True,
                                                          progress=False)
    return np.column_stack([np.asarray(i1, float), np.asarray(q1, float)])


def calibrate_drift_pi(soc, soccfg, base_cfg, rec, shots=2000,
                       passive_relax_us=1500.0, feedback_relax_us=25.0,
                       delay_us=1.0,
                       span_mhz=DRIFT_PI_SPAN_MHZ, step_mhz=DRIFT_PI_STEP_MHZ,
                       max_iters=None, thermalization_us=0.0, verbose=True):
    park = float(base_cfg.get("ff_park_gain", 0) or 0)
    if park == 0:
        return None
    qf = float(base_cfg.get("qubit_pi_freq", base_cfg["qubit_freq"]))
    common = dict(base_cfg)
    common.update({"shots": int(shots), "reps": int(shots),
                   "relax_delay": float(passive_relax_us),
                   "ff_gain": park, "ff_hold": float(delay_us), "do_ff": True})

    def passive(do_pi):
        c = dict(common)
        c.update({"reset_mode": "passive", "do_pi": bool(do_pi)})
        return _drift_shots(soc, soccfg, c)

    g, e = passive(False), passive(True)
    axis = e.mean(axis=0) - g.mean(axis=0)
    u = axis / max(float(np.hypot(*axis)), 1e-12)
    pg, pe = g @ u, e @ u
    grid = np.linspace(min(pg.min(), pe.min()), max(pg.max(), pe.max()), 400)
    thr = float(grid[int(np.argmax(0.5 * ((pg[:, None] < grid).mean(axis=0)
                                          + (pe[:, None] >= grid).mean(axis=0))))])
    base_contrast = float((pe >= thr).mean()) - float((pg >= thr).mean())
    if base_contrast <= 0.2:
        if verbose:
            print(f"[reset] drift-pi calibration skipped: passive contrast is only "
                  f"{base_contrast:.3f}; fix the pi pulse first")
        return None

    def contrast(reset_off, post_off):
        c = reset_cfg_from_record(common, rec, max_iters, thermalization_us)
        c.update({"reset_mode": "feedback",
                  "relax_delay": float(feedback_relax_us),
                  "reset_pi_freq": qf + float(reset_off),
                  "reset_pi_gain": int(base_cfg["qubit_pi_gain"]),
                  "post_reset_pi_freq": qf + float(post_off)})
        c["do_pi"] = False
        r_g = float((_drift_shots(soc, soccfg, c) @ u >= thr).mean())
        c["do_pi"] = True
        r_e = float((_drift_shots(soc, soccfg, c) @ u >= thr).mean())
        return r_e - r_g, r_g

    offs = np.arange(-step_mhz, float(span_mhz) + 1e-9, float(step_mhz))
    if verbose:
        print(f"[reset] calibrating the drift-compensated pi at park {park:g}: "
              f"passive contrast {base_contrast:.3f} at {passive_relax_us:g} us relax, "
              f"scoring feedback at the {feedback_relax_us:g} us relax the run uses")
    scan = [(o,) + contrast(0.0, o) for o in offs]
    post_off = max(scan, key=lambda r: r[1])[0]
    scan2 = [(o,) + contrast(o, post_off) for o in offs]
    reset_off, best_c, resid = max(scan2, key=lambda r: r[1])
    if verbose:
        print(f"[reset] drift-compensated pi: reset {reset_off:+.2f} MHz, "
              f"post-reset {post_off:+.2f} MHz -> contrast {best_c:.3f} "
              f"({best_c / base_contrast * 100:.0f}% of passive), residual {resid:.3f}")
    out = {"reset_pi_offset_mhz": float(reset_off),
           "post_reset_pi_offset_mhz": float(post_off),
           "qubit_pi_freq": qf, "ff_park_gain": park,
           "feedback_relax_us": float(feedback_relax_us),
           "reset_max_iters": (None if max_iters is None else int(max_iters)),
           "reset_thermalization_us": float(thermalization_us),
           "contrast": float(best_c), "passive_contrast": float(base_contrast),
           "residual": float(resid)}
    rec["drift_pi"] = out
    return out


def drift_pi_matches(d, cfg, feedback_relax_us, max_iters, thermalization_us):
    if not isinstance(d, dict):
        return False
    want = (("qubit_pi_freq", float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))),
            ("ff_park_gain", float(cfg.get("ff_park_gain", 0) or 0)),
            ("feedback_relax_us", float(feedback_relax_us)),
            ("reset_thermalization_us", float(thermalization_us)))
    for key, value in want:
        if key not in d or d[key] is None:
            return False
        if abs(float(d[key]) - value) > 1e-6:
            return False
    if max_iters is not None and d.get("reset_max_iters") is not None:
        return int(d["reset_max_iters"]) == int(max_iters)
    return True


def apply_drift_pi(cfg, rec):
    d = (rec or {}).get("drift_pi")
    if not d:
        return cfg
    qf = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))
    if abs(qf - float(d.get("qubit_pi_freq", qf))) > 1e-6:
        return cfg
    if abs(float(cfg.get("ff_park_gain", 0) or 0)
           - float(d.get("ff_park_gain", 0))) > 1e-6:
        return cfg
    cfg["reset_pi_freq"] = qf + float(d["reset_pi_offset_mhz"])
    cfg["reset_pi_gain"] = int(cfg["qubit_pi_gain"])
    cfg["post_reset_pi_freq"] = qf + float(d["post_reset_pi_offset_mhz"])
    return cfg
