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


def trace_word_count(max_iters):
    return 1 + TRACE_WORDS_PER_ITER * int(max_iters)


def reserved_registers(prog, page):
    reserved = {0}
    if int(page) == 0:
        reserved.update({13, 14, 15, 31})
    for gencfg in prog.soccfg['gens']:
        try:
            tproc_ch = int(gencfg['tproc_ch'])
        except (KeyError, TypeError, ValueError):
            continue
        if prog._ch_page_tproc(tproc_ch) != int(page):
            continue
        for name in prog.pulse_registers:
            reserved.add(prog._sreg_tproc(tproc_ch, name))
    for rocfg in prog.soccfg['readouts']:
        tproc_ctrl = rocfg.get('tproc_ctrl') if hasattr(rocfg, 'get') else None
        if tproc_ctrl is None:
            continue
        try:
            tproc_ctrl = int(tproc_ctrl)
        except (TypeError, ValueError):
            continue
        if prog._ch_page_tproc(tproc_ctrl) != int(page):
            continue
        for name in prog.pulse_registers:
            reserved.add(prog._sreg_tproc(tproc_ctrl, name))
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
                       reg_flag=None):
    if threshold_raw is None:
        raise ValueError("active_reset_block needs threshold_raw (raw accumulator units); "
                         "calibrate it with Experiments/mActiveResetProbe.py.")
    cfg = prog.cfg
    if settle_us is None:
        settle_us = float(cfg.get("reset_settle_us", 0.05))
    if meas_syncdelay_us is None:
        meas_syncdelay_us = float(cfg.get("reset_meas_syncdelay_us", 4.0))
    if read_delay_us is None:
        read_delay_us = cfg.get("reset_read_delay_us", None)
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
    for i in range(int(max_iters)):
        prog.measure(pulse_ch=res_ch, adcs=[ro_ch], adc_trig_offset=off,
                     wait=True, syncdelay=None)
        if read_delay_cycles is not None:
            prog.waiti(0, int(max(prog._adc_ts)) + read_delay_cycles)
        prog.read(tproc_ch, page, oper, reg_val)
        prog.sync_all(prog.us2cycles(meas_syncdelay_us))
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
    if str(cfg.get("reset_mode", "passive")).strip().lower() != "feedback":
        return 0
    return int(cfg.get("reset_max_iters", 3))


def probe_reset_params(soc, soccfg, base_cfg, path="q", outer_folder="", shots=2000,
                       validate=True, min_raw_fidelity=0.80, min_raw_shots=200,
                       diagnostic_callback=None):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
        ActiveResetProbe)
    cfg = dict(base_cfg)
    cfg["shots"] = int(shots)
    cfg["reps"] = int(shots)
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
              f"{float(min_raw_fidelity):.3f} -- per-shot discrimination too marginal for "
              "clean active reset; falling back to passive relax.")
        return None
    rec = dict(data["recommended"])
    rec["raw_assignment_fidelity"] = raw_fidelity
    rec["raw_assignment_errors"] = dict(data.get("raw_assignment_errors", {}))
    rec["raw_assignment_shots"] = buffered_shots
    if validate:
        try:
            residual = probe._residual_at(
                float(cfg.get("res_phase", 0.0)), int(rec["threshold_raw"]),
                bool(rec["ground_below"]), max(500, int(shots)), oper=rec["oper"])
        except Exception as exc:
            print(f"[reset] end-to-end validation failed ({exc}) -- falling back to "
                  "passive relax.")
            return None
        if not residual.get("works", False):
            print("[reset] conditional reset did not pass its prepared-|e> residual "
                  "check -- falling back to passive relax.")
            return None
        rec["validation"] = residual
    print(f"[reset] fresh discrimination: oper={rec['oper']} threshold_raw={rec['threshold_raw']} "
          f"ground_below={rec['ground_below']}")
    return rec
