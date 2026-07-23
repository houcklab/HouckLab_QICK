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
                       page=None, reg_val=None, reg_thr=None):
    """Emit a QUA-style feedback reset into ``prog`` (a QICK tProc-v1 program).

    Bounded loop, ``max_iters`` passes:  measure -> read accumulator I -> if the qubit is
    ground, jump out; else play one X180 and repeat.  This is the exact QUA
    ``while_(I_reset > thr): play('X180')`` intent, bounded (tProc-friendly, and a hedge
    against an infinite loop if discrimination is marginal).

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


def active_reset_readouts(cfg):
    """Number of readout triggers an active reset ADDS per shot (0 if not feedback mode).
    Add this to an AveragerProgram's readouts_per_experiment when reset_mode=='feedback'."""
    if str(cfg.get("reset_mode", "passive")).strip().lower() != "feedback":
        return 0
    return int(cfg.get("reset_max_iters", 3))


def probe_reset_params(soc, soccfg, base_cfg, path="q", outer_folder="", shots=2000):
    """Measure a FRESH active-reset discrimination (raw threshold, quadrature half, sign).

    The raw |g>/|e> accumulator reads on this readout drift between sessions -- enough to
    move the threshold severalfold and even swap which side |g> sits on -- so a threshold
    saved in the config goes stale, and a stale sign makes the feedback play X180 when the
    qubit is ALREADY in |g>, pumping it the wrong way.  Re-measuring live at the start of a
    run (intra-run drift is small) keeps it correct.

    Returns the recommended dict {'oper','threshold_raw','ground_below'}, or None if the
    firmware has no feedback path or the readout cannot discriminate -- in which case the
    caller must fall back to passive relax rather than trust a bad threshold."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
        ActiveResetProbe)
    cfg = dict(base_cfg)
    cfg["shots"] = int(shots)
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
    rec = data["recommended"]
    print(f"[reset] fresh discrimination: oper={rec['oper']} threshold_raw={rec['threshold_raw']} "
          f"ground_below={rec['ground_below']}")
    return rec
