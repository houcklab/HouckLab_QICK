"""
tProc-v1 active (feedback) reset for QICK 0.2.133 -- the faithful analog of the QUA
active reset  ``while_(I_reset > thr): play('X180')``.

STATUS: the tProc-v1 primitives are CONFIRMED present in qick 0.2.133 -- ``read`` (reads a
readout accumulator half into a tProc register; opcode 0b01010011, args ``read ch, p, oper
$r`` with oper in {lower, upper}), ``condj`` (conditional branch to a label), and
``label`` -- all callable via QickProgram.__getattr__.  What CANNOT be confirmed off the
board:
  (1) whether THIS board's firmware routes the readout buffer into a tProc input port
      (the feedback path).  This is firmware-dependent: the QICK docs call the 4 feedback
      input channels an "updated tProcessor" feature, and qick.py sets the buffer's
      ``tproc_ch = -1`` when "this buffer doesn't feed back into the tProc".  RUNTIME CHECK:
      ``feedback_channel(soccfg, ro_ch) >= 0``.
  (2) which accumulator half (lower/upper) is I, the raw-accumulator threshold value, and
      the discrimination axis.  The tProc ``read`` returns the RAW accumulator (not the
      host-side rotated/divided I), so the threshold must be in raw units and the readout
      phase must be set so ground/excited separate along the read axis.

=> Run ``Experiments/mActiveResetProbe.py`` FIRST.  It (a) reports feedback_channel, and
   (b) if >=0, measures the raw ``read`` value for prepared ground vs excited states,
   confirming the read works and giving you the raw threshold to pass here.  Until then,
   passive relax remains the default everywhere (this module is opt-in).

References: qick_demos 03_Conditional_logic (condj) + 04_Reading_Math_Writing; QICK papers
(conditional-logic feedback latency ~42 ns).
"""


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


# unique-label counter so multiple reset blocks in one program don't collide
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
    reg_val = 20 if reg_val is None else reg_val      # scratch: read value
    reg_thr = 21 if reg_thr is None else reg_thr      # scratch: threshold
    off = (prog.us2cycles(cfg["adc_trig_offset"]) if adc_trig_offset_us is None
           else prog.us2cycles(adc_trig_offset_us))

    _UID[0] += 1
    done = f"AR_DONE_{_UID[0]}"
    # ground state satisfies (value <op> threshold) -> we jump OUT of the loop.
    ground_op = "<" if ground_below else ">"

    prog.regwi(page, reg_thr, int(threshold_raw), "active-reset threshold (raw)")
    for _ in range(int(max_iters)):
        # measure: play the readout pulse, trigger the ADC, wait for the accumulation
        prog.measure(pulse_ch=res_ch, adcs=[ro_ch], adc_trig_offset=off,
                     wait=True, syncdelay=prog.us2cycles(meas_syncdelay_us))
        # pull the accumulator half into a register and branch out if the qubit is ground
        prog.read(tproc_ch, page, oper, reg_val)
        prog.condj(page, reg_val, ground_op, reg_thr, done)
        # excited -> apply a pi pulse, then loop back to re-measure
        prog.pulse(ch=qubit_ch)
        prog.sync_all(prog.us2cycles(settle_us))
    prog.label(done)
    prog.sync_all(prog.us2cycles(settle_us))
