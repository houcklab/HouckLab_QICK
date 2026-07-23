def to_signed32(v):
    """Interpret a 32-bit word as a SIGNED int.  The tProc readout accumulator is signed, but
    soc.tproc.single_read / read_dmem hand the word back UNSIGNED, so a small negative like
    -1402 comes out as 4294965894 (== -1402 + 2**32).  The tProc's own condj comparison is
    signed, so the threshold must be compared in signed units -- always pass raw reads through
    this before thresholding or reporting them."""
    v = int(v) & 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


def feedback_channel(soccfg, ro_ch=0):
    """tProc input channel the readout buffer drives, from soccfg.  >= 0 => the firmware
    routes this readout into the tProc (feedback / active reset possible).  -1 => it does
    not (active reset impossible on this firmware; use passive relax).  This is the single
    authoritative capability check."""
    try:
        return int(soccfg['readouts'][ro_ch]['tproc_ch'])
    except (KeyError, IndexError, TypeError, ValueError):
        return -1


def active_reset_supported(soccfg, ro_ch=0):
    return feedback_channel(soccfg, ro_ch) >= 0


_UID = [0]


def active_reset_block(prog, ro_ch=0, res_ch=None, qubit_ch=None, threshold_raw=None,
                       ground_below=True, oper="lower", max_iters=3,
                       adc_trig_offset_us=None, settle_us=0.05, meas_syncdelay_us=0.2,
                       thermalization_us=None, page=None, reg_val=None, reg_thr=None):
    """Emit a QUA-style feedback reset into ``prog`` (a QICK tProc-v1 program).

    Fixed-count bounded loop, ``max_iters`` passes: measure -> read one accumulator
    half -> play X180 only when classified excited.  Every pass is still measured so
    QICK returns a deterministic number of buffers per repetition; later ground results
    simply skip their correction pulses.  This implements the QUA conditional-reset
    intent without an unbounded loop or variable buffer shape.

    Requires ``feedback_channel(prog.soccfg, ro_ch) >= 0`` (verify with the probe).

    Parameters
    ----------
    threshold_raw : int
        Discrimination threshold in RAW accumulator units (NOT the host calib_params
        threshold).  Calibrate with mActiveResetProbe.  Required.
    ground_below : bool
        True if the ground-state raw read value is BELOW threshold (excited above).  The
        probe tells you the sign; flip if the blobs are inverted.
    oper : {"lower", "upper"}
        Which 32-bit half of the tProc input is the discrimination quadrature.  Default
        "lower" (assumed I); the probe confirms.
    max_iters : int
        Max feedback passes (each: measure + conditional X180).
    thermalization_us : float, optional
        Photon-clearing wait after the final feedback measurement.  ``None`` reads
        ``cfg['reset_thermalization_us']`` and defaults to 25 us.  This belongs in
        the reset primitive rather than individual experiments: without it, a drive
        can see residual measurement photons and a reset implementation can appear
        to change the calibrated qubit frequency or pulse fidelity.
    page, reg_val, reg_thr : int, optional
        tProc register page + two scratch registers.  Defaults use page of qubit_ch and
        high register numbers unlikely to collide with the sweep registers.
    """
    if threshold_raw is None:
        raise ValueError("active_reset_block needs threshold_raw (raw accumulator units); "
                         "calibrate it with Experiments/mActiveResetProbe.py.")
    cfg = prog.cfg
    res_ch = cfg["res_ch"] if res_ch is None else res_ch
    qubit_ch = cfg["qubit_ch"] if qubit_ch is None else qubit_ch
    tproc_ch = feedback_channel(prog.soccfg, ro_ch)
    if tproc_ch < 0:
        raise RuntimeError(
            f"Readout {ro_ch} does not feed back into the tProc (tproc_ch=-1): this "
            "firmware cannot do active reset.  Use reset_mode='passive'.")

    page = prog.ch_page(qubit_ch) if page is None else page
    reg_val = 20 if reg_val is None else reg_val
    reg_thr = 21 if reg_thr is None else reg_thr
    off = (prog.us2cycles(cfg["adc_trig_offset"]) if adc_trig_offset_us is None
           else prog.us2cycles(adc_trig_offset_us))
    clear_us = (cfg.get("reset_thermalization_us", 25.0)
                if thermalization_us is None else thermalization_us)
    clear_us = float(clear_us)
    if clear_us < 0:
        raise ValueError("reset_thermalization_us must be non-negative")

    _UID[0] += 1
    ground_op = "<" if ground_below else ">"

    prog.regwi(page, reg_thr, int(threshold_raw), "active-reset threshold (raw)")
    for i in range(int(max_iters)):
        prog.measure(pulse_ch=res_ch, adcs=[ro_ch], adc_trig_offset=off,
                     wait=True, syncdelay=prog.us2cycles(meas_syncdelay_us))
        prog.read(tproc_ch, page, oper, reg_val)
        skip = f"AR_SKIP_{_UID[0]}_{i}"
        prog.condj(page, reg_val, ground_op, reg_thr, skip)
        prog.pulse(ch=qubit_ch)
        prog.label(skip)
        prog.sync_all(prog.us2cycles(settle_us))
    if clear_us > 0:
        prog.sync_all(prog.us2cycles(clear_us))


def active_reset_readouts(cfg):
    """Number of readout triggers an active reset ADDS per shot (0 if not feedback mode).
    Add this to an AveragerProgram's readouts_per_experiment when reset_mode=='feedback'."""
    if str(cfg.get("reset_mode", "passive")).strip().lower() != "feedback":
        return 0
    return int(cfg.get("reset_max_iters", 3))


def probe_reset_params(soc, soccfg, base_cfg, path="q", outer_folder="", shots=2000,
                       validate=True, min_raw_fidelity=0.80, min_raw_shots=200):
    """Measure and, by default, end-to-end validate fresh active-reset parameters.

    The raw |g>/|e> accumulator reads on this readout drift between sessions -- enough to
    move the threshold severalfold and even swap which side |g> sits on -- so a threshold
    saved in the config goes stale, and a stale sign makes the feedback play X180 when the
    qubit is ALREADY in |g>, pumping it the wrong way.  Re-measuring live at the start of a
    run (intra-run drift is small) keeps it correct.

    Returns the recommended dict or ``None`` if the firmware has no feedback path, the
    raw separation is split across both accumulator halves, or the conditional reset
    does not reduce a prepared excited reference below the validation bound.  A caller
    must fall back to passive relaxation rather than trust a merely plausible threshold.
    """
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
              f"{float(min_raw_fidelity):.3f} -- falling back to passive relax.")
        return None
    rec = dict(data["recommended"])
    rec["raw_assignment_fidelity"] = raw_fidelity
    rec["raw_assignment_errors"] = dict(data.get("raw_assignment_errors", {}))
    rec["raw_assignment_shots"] = buffered_shots
    if validate:
        try:
            residual = probe._residual_at(
                float(cfg.get("res_phase", 0.0)), int(rec["threshold_raw"]),
                bool(rec["ground_below"]), max(500, int(shots)))
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
