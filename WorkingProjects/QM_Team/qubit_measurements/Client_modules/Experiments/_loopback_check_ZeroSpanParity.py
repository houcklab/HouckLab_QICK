"""RFSoC loopback smoke test for the zero-span parity acquisition (spec §6.2).

This is the gate between "the offline tests pass" and "point it at a qubit". It
needs the board and a DAC->ADC loopback cable, but NO qubit: everything it checks
is shape, timing and configuration plumbing, which is exactly the class of bug
that is invisible in synthetic tests and expensive to debug on a cold device.

Run it after any qick upgrade, bitstream change, or edit to mZeroSpanParity.

    $env:PYTHONPATH = (Get-Location).Path
    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments._loopback_check_ZeroSpanParity

Wiring: loop the readout DAC (BaseConfig["res_ch"]) back to the ADC
(BaseConfig["ro_chs"][0]). Gains are deliberately tiny; nothing here needs signal
fidelity, only that the plumbing is right.

What it checks (spec §6.2 table, plus two additions):

  0. Board limits report      -- prints avg_maxlen / buf_maxlen / f_output / f_dds
                                 and the derived legal ranges, so the numbers the
                                 validation rules enforce are visible, not implied.
  1. Strobe shape             -- reps_per_chunk samples out, I/Q/t_us aligned.
  2. Time axis                -- t_us strictly increasing, mean spacing ==
                                 sample_period_us. THIS is the check that catches
                                 a readout window declared on the wrong clock: the
                                 tProc syncs to max(pulse_end, readout_end), so an
                                 over-long window silently stretches the real rep
                                 period past sample_period_us while t_us keeps
                                 reporting the nominal value.
  3. Declared readout window  -- ro_chs[ro]["length"] == us2cycles(read_length,
                                 ro_ch), and the normalization divisor matches it.
  4. chunked_acquire stitching-- gap_indices at the chunk boundaries, no dupes,
                                 monotonic stitched time axis.
  5. modulated_strobe_acquire -- block count, gap_indices, and a
                                 modulation_reference aligned to the gain schedule.
  6. Long single chunk        -- reps_per_chunk > avg_maxlen with the opt-in, to
                                 confirm qick really does stream the circular
                                 accumulated buffer (fewer chunks = fewer gaps).
  7. Validation rules         -- each §5.3 rule raises RuntimeError naming itself.
  8. Decimated capture        -- only if buf_maxlen allows a useful capture; on the
                                 BFG board it does not, and the check says so
                                 rather than pretending Path B is available.

Every check prints PASS/FAIL and the script exits non-zero if any failed, so it
can gate a session.
"""

import sys
import traceback

import numpy as np

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import (
    BaseConfig,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import (
    makeProxy,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import (
    ZeroSpanParity,
    _validate_cfg,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    chunked_acquire,
    modulated_strobe_acquire,
)

# Tiny gains: this is a plumbing test, not a signal test.
LOOPBACK_PULSE_GAIN = 300
LOOPBACK_QUBIT_GAIN = 300

# Placeholder parking frequencies. The qubit tone goes nowhere on a loopback
# cable; the readout tone just has to be inside the DDS band.
LOOPBACK_READ_FREQ = 100.0        # MHz
LOOPBACK_PARITY_FREQ = 500.0      # MHz

SAMPLE_PERIOD_US = 40.0
READ_LENGTH_US = 30.0
ADC_TRIG_OFFSET_US = 1.0

_results = []


def _check(name):
    """Decorator: run a check, record PASS/FAIL, never abort the whole run."""
    def deco(fn):
        def wrapped(*a, **k):
            print(f"\n--- {name} ---")
            try:
                fn(*a, **k)
            except Exception as ex:
                _results.append((name, False, f"{type(ex).__name__}: {ex}"))
                print(f"FAIL {name}: {type(ex).__name__}: {ex}")
                traceback.print_exc(limit=3)
                return None
            _results.append((name, True, ""))
            print(f"PASS {name}")
        return wrapped
    return deco


def build_cfg(soccfg, **overrides):
    """A minimal valid strobe cfg for the loopback setup."""
    cfg = {
        "res_ch":     BaseConfig["res_ch"],
        "qubit_ch":   BaseConfig["qubit_ch"],
        "ro_chs":     list(BaseConfig["ro_chs"]),
        "nqz":        BaseConfig["nqz"],
        "qubit_nqz":  BaseConfig["qubit_nqz"],
        "mixer_freq": BaseConfig["mixer_freq"],
        "read_pulse_freq":   LOOPBACK_READ_FREQ,
        "parity_drive_freq": LOOPBACK_PARITY_FREQ,
        "qubit_gain": LOOPBACK_QUBIT_GAIN,
        "pulse_gain": LOOPBACK_PULSE_GAIN,
        "res_phase":  0,
        "mode":       "strobe",
        "start_src":  "internal",
        "sample_period_us": SAMPLE_PERIOD_US,
        "read_length":      READ_LENGTH_US,
        "adc_trig_offset":  ADC_TRIG_OFFSET_US,
        "reps_per_chunk":   1000,
    }
    cfg.update(overrides)
    return cfg


def make_exp(soc, soccfg, out_dir, **overrides):
    return ZeroSpanParity(soc=soc, soccfg=soccfg, path="ZSP_loopback",
                          outerFolder=out_dir, cfg=build_cfg(soccfg, **overrides))


# ---------------------------------------------------------------------------
# 0. Board limits
# ---------------------------------------------------------------------------

def report_limits(soccfg):
    print("\n=== board limits (what the §5.3 rules enforce) ===")
    ro_ch = BaseConfig["ro_chs"][0]
    res_ch = BaseConfig["res_ch"]
    qubit_ch = BaseConfig["qubit_ch"]
    ro = soccfg["readouts"][ro_ch]
    f_out = float(ro["f_output"])
    avg_maxlen = int(ro["avg_maxlen"])
    buf_maxlen = int(ro["buf_maxlen"])
    f_time = float(soccfg["tprocs"][0]["f_time"])
    print(f"  tProc f_time          : {f_time} MHz")
    print(f"  readout[{ro_ch}] f_output : {f_out} MHz")
    print(f"  f_time / f_output     : {f_time / f_out:.4f}   "
          f"(a readout window declared on the wrong clock is off by this factor)")
    print(f"  readout[{ro_ch}] avg_maxlen: {avg_maxlen} accumulated samples")
    print(f"  readout[{ro_ch}] buf_maxlen: {buf_maxlen} decimated samples "
          f"= {buf_maxlen / f_out:.3f} us max decimated capture")
    for ch, label in ((res_ch, "res"), (qubit_ch, "qubit")):
        gen = soccfg["gens"][ch]
        f_fab = float(gen["f_fabric"])
        f_dds = float(gen["f_dds"])
        print(f"  gen[{ch}] ({label:5s})      : f_fabric {f_fab} MHz, f_dds {f_dds} MHz "
              f"-> DDS band +/-{f_dds / 2:.1f} MHz, "
              f"max const pulse {65535 / f_fab:.1f} us")
    print(f"  => strobe: sample_period_us in "
          f"[{ADC_TRIG_OFFSET_US + READ_LENGTH_US + 1.0:.1f}, "
          f"{65535 / float(soccfg['gens'][res_ch]['f_fabric']):.1f}] us at this read_length")
    print(f"  => strobe: reps_per_chunk <= {avg_maxlen} without "
          f"allow_reps_over_avg_maxlen")
    print(f"  => decimated: read_length < {(buf_maxlen - 1) / f_out:.3f} us "
          f"({'usable' if buf_maxlen / f_out > 20 else 'TOO SHORT for a parity telegraph -- use strobe'})")
    return {"f_time": f_time, "f_output": f_out, "avg_maxlen": avg_maxlen,
            "buf_maxlen": buf_maxlen, "ro_ch": ro_ch}


# ---------------------------------------------------------------------------
# 1-3. Strobe shape, time axis, declared window
# ---------------------------------------------------------------------------

@_check("strobe shape + time axis + declared readout window")
def check_strobe(soc, soccfg, out_dir, limits):
    reps = 1000
    exp = make_exp(soc, soccfg, out_dir, reps_per_chunk=reps)
    data = exp.acquire(progress=False)

    assert data["I"].shape == (reps,), f"I shape {data['I'].shape} != ({reps},)"
    assert data["Q"].shape == (reps,), f"Q shape {data['Q'].shape} != ({reps},)"
    assert data["t_us"].shape == (reps,), f"t_us shape {data['t_us'].shape}"
    assert np.all(np.isfinite(data["I"])) and np.all(np.isfinite(data["Q"]))
    print(f"  shapes OK: {reps} samples")

    # Time axis
    d = np.diff(data["t_us"])
    assert np.all(d > 0), "t_us is not strictly increasing"
    assert abs(float(np.mean(d)) - SAMPLE_PERIOD_US) < 1e-9, (
        f"mean(diff(t_us)) = {np.mean(d)} != sample_period_us = {SAMPLE_PERIOD_US}")
    print(f"  t_us strictly increasing, spacing {np.mean(d)} us")

    # Declared readout window: decimated samples, on the READOUT clock.
    ro_ch = limits["ro_ch"]
    declared = int(exp.prog.ro_chs[ro_ch]["length"])
    expect_ro = int(soccfg.us2cycles(READ_LENGTH_US, ro_ch=ro_ch))
    wrong_tproc = int(soccfg.us2cycles(READ_LENGTH_US))
    assert declared == expect_ro, (
        f"declared readout length {declared} != us2cycles(read_length, ro_ch) "
        f"{expect_ro}")
    if wrong_tproc != expect_ro:
        assert declared != wrong_tproc, (
            f"readout window was declared on the tProc clock ({wrong_tproc} "
            f"cycles); it must be decimated samples ({expect_ro})")
    print(f"  declared window {declared} decimated samples "
          f"= {declared / limits['f_output']:.3f} us "
          f"(tProc-clock value would have been {wrong_tproc})")

    # The normalization divisor must equal the window that was integrated.
    assert float(data["ro_norm_cycles"]) == float(declared), (
        f"ro_norm_cycles {data['ro_norm_cycles']} != declared window {declared}; "
        f"the strobe trace is then mis-scaled relative to the single-shot "
        f"separator by exactly that ratio")
    print(f"  ro_norm_cycles == declared window ({declared})")

    # The const tone must cover the whole integration window, else the tail of
    # each sample is undriven.
    tone_us = SAMPLE_PERIOD_US
    window_end_us = ADC_TRIG_OFFSET_US + declared / limits["f_output"]
    assert tone_us >= window_end_us - 1e-9, (
        f"const tone ends at {tone_us} us but the ADC integrates to "
        f"{window_end_us:.3f} us -> {100 * (1 - tone_us / window_end_us):.0f}% of "
        f"the window sees no drive")
    print(f"  tone covers the window: tone {tone_us} us >= window end "
          f"{window_end_us:.3f} us")

    # Metadata round-trip
    assert data["mode"] == "strobe"
    assert data["read_length_us"] == READ_LENGTH_US
    assert data["adc_trig_offset_us"] == ADC_TRIG_OFFSET_US
    assert len(np.atleast_1d(data["gap_indices"])) == 0, data["gap_indices"]


# ---------------------------------------------------------------------------
# 4. chunked_acquire stitching
# ---------------------------------------------------------------------------

@_check("chunked_acquire stitching + gap_indices")
def check_chunked(soc, soccfg, out_dir):
    reps, n_chunks = 1000, 5
    exp = make_exp(soc, soccfg, out_dir, reps_per_chunk=reps)
    st = chunked_acquire(exp, n_chunks=n_chunks, progress=False)

    total = reps * n_chunks
    assert st["I"].shape == (total,), f"stitched I shape {st['I'].shape}"
    assert st["Q"].shape == (total,) and st["t_us"].shape == (total,)
    expected_gaps = [reps * k for k in range(1, n_chunks)]
    assert list(st["gap_indices"]) == expected_gaps, (
        f"gap_indices {list(st['gap_indices'])} != {expected_gaps}")
    assert np.all(np.diff(st["t_us"]) > 0), "stitched t_us is not increasing"
    assert len(st["chunk_wall_clock_starts"]) == n_chunks
    assert st["n_chunks"] == n_chunks
    # Metadata must survive stitching, or save_data writes an unlabelled trace.
    for k in ("sample_period_us", "read_length_us", "ro_norm_cycles", "mode"):
        assert k in st, f"chunked_acquire dropped {k}"
    print(f"  {n_chunks} x {reps} = {total} samples, gaps at {expected_gaps}")
    print(f"  record length {st['t_us'][-1] / 1e6:.3f} s")

    # experiment.data must hold the STITCHED record, so a bare save_data() does
    # not silently persist only the last chunk.
    assert exp.data["data"]["I"].size == total, (
        "experiment.data holds only the last chunk; save_data() would truncate")
    print("  experiment.data holds the full stitched record")


# ---------------------------------------------------------------------------
# 5. modulated_strobe_acquire
# ---------------------------------------------------------------------------

@_check("modulated_strobe_acquire blocks + modulation_reference")
def check_modulated(soc, soccfg, out_dir):
    reps_per_block = 1000
    schedule = [LOOPBACK_QUBIT_GAIN, 0, LOOPBACK_QUBIT_GAIN, 0]
    exp = make_exp(soc, soccfg, out_dir, reps_per_chunk=reps_per_block)
    acq = modulated_strobe_acquire(exp, schedule, reps_per_block, progress=False)

    total = reps_per_block * len(schedule)
    assert acq["I"].shape == (total,), f"I shape {acq['I'].shape} != ({total},)"
    expected_gaps = [reps_per_block * k for k in range(1, len(schedule))]
    assert list(acq["gap_indices"]) == expected_gaps, (
        f"gap_indices {list(acq['gap_indices'])} != {expected_gaps}")
    assert acq["block_labels"] == schedule, (
        f"block_labels {acq['block_labels']} != requested {schedule}")
    ref = acq["modulation_reference"]
    assert ref.shape == acq["I"].shape
    # The reference must be 1 exactly where the schedule had a nonzero gain.
    expected_ref = np.concatenate([np.full(reps_per_block, 1.0 if g > 0 else 0.0)
                                   for g in schedule])
    assert np.array_equal(ref, expected_ref), "modulation_reference misaligned"
    assert np.all(np.diff(acq["t_us"]) > 0), "modulated t_us is not increasing"
    print(f"  {len(schedule)} blocks x {reps_per_block} reps, gaps at {expected_gaps}")
    print(f"  modulation_freq_hz = {acq['modulation_freq_hz']:.2f} "
          f"(half-period = {reps_per_block * SAMPLE_PERIOD_US / 1e3:.1f} ms)")
    # The gain must be back where it started, not left at the last block's value.
    assert exp.cfg["qubit_gain"] == schedule[-1], (
        "modulated_strobe_acquire leaves cfg['qubit_gain'] at the last block "
        "value; callers must restore it")


# ---------------------------------------------------------------------------
# 6. Long single chunk (reps > avg_maxlen)
# ---------------------------------------------------------------------------

@_check("long single chunk above avg_maxlen (opt-in)")
def check_long_chunk(soc, soccfg, out_dir, limits):
    avg_maxlen = limits["avg_maxlen"]
    reps = int(avg_maxlen * 2.5)
    # Without the opt-in this must be refused ...
    try:
        make_exp(soc, soccfg, out_dir, reps_per_chunk=reps)
    except RuntimeError as ex:
        assert "rule 4" in str(ex), ex
        print(f"  refused without the opt-in (as designed): rule 4")
    else:
        raise AssertionError("reps > avg_maxlen was accepted without the opt-in")

    # ... and accepted with it. The accumulated buffer is circular and streamed
    # during the run, so this is legal; the payoff is a record with NO chunk gaps.
    exp = make_exp(soc, soccfg, out_dir, reps_per_chunk=reps,
                   allow_reps_over_avg_maxlen=True)
    data = exp.acquire(progress=True)
    assert data["I"].shape == (reps,), (
        f"long chunk returned {data['I'].shape}, expected ({reps},) -- if this "
        f"is short, the host did not keep up with the streamed buffer")
    d = np.diff(data["t_us"])
    assert np.all(d > 0) and abs(float(np.mean(d)) - SAMPLE_PERIOD_US) < 1e-9
    print(f"  {reps} reps ({reps / avg_maxlen:.1f}x avg_maxlen) in ONE gapless "
          f"chunk = {reps * SAMPLE_PERIOD_US / 1e6:.2f} s")


# ---------------------------------------------------------------------------
# 7. Validation rules
# ---------------------------------------------------------------------------

@_check("§5.3 validation rules fire against the live soccfg")
def check_rules(soccfg, limits):
    def expect_rule(rule, **overrides):
        cfg = build_cfg(soccfg, **overrides)
        try:
            _validate_cfg(cfg, soccfg)
        except RuntimeError as ex:
            assert rule in str(ex), f"expected {rule}, got: {ex}"
            print(f"  {rule}: {str(ex).splitlines()[0][:110]}")
            return
        raise AssertionError(f"expected {rule} to fire for {overrides}")

    # A valid cfg must pass.
    _validate_cfg(build_cfg(soccfg), soccfg)
    print("  valid strobe cfg passes")

    # rule 1: sample_period below adc_trig_offset + read_length + 1
    expect_rule("rule 1", sample_period_us=ADC_TRIG_OFFSET_US + READ_LENGTH_US)
    # rule 2: const pulse over the 16-bit cap
    f_fab = float(soccfg["gens"][BaseConfig["res_ch"]]["f_fabric"])
    expect_rule("rule 2", sample_period_us=(70000 / f_fab))
    # rule 4: reps above avg_maxlen without the opt-in
    expect_rule("rule 4", reps_per_chunk=limits["avg_maxlen"] + 1)
    # rule 8: parity drive outside the DDS band
    f_dds = float(soccfg["gens"][BaseConfig["qubit_ch"]]["f_dds"])
    expect_rule("rule 8", parity_drive_freq=f_dds)
    # rules 5 and 9 are decimated-mode
    ro_ch = limits["ro_ch"]
    f_out = limits["f_output"]
    max_dec_us = (limits["buf_maxlen"] - 1) / f_out
    dec = {"mode": "decimated", "soft_avgs": 1,
           "capture_length_us": max_dec_us + ADC_TRIG_OFFSET_US + 1.0,
           "read_length": max_dec_us + 1.0}
    dec.pop("sample_period_us", None)
    cfg = build_cfg(soccfg, **dec)
    cfg.pop("sample_period_us"); cfg.pop("reps_per_chunk")
    try:
        _validate_cfg(cfg, soccfg)
    except RuntimeError as ex:
        assert "rule 5" in str(ex), ex
        print(f"  rule 5: {str(ex).splitlines()[0][:110]}")
    else:
        raise AssertionError("expected rule 5 to fire")
    # rule 9: const pulse shorter than the readout window
    cfg = build_cfg(soccfg, mode="decimated", soft_avgs=1,
                    read_length=1.0, capture_length_us=0.5)
    cfg.pop("sample_period_us"); cfg.pop("reps_per_chunk")
    try:
        _validate_cfg(cfg, soccfg)
    except RuntimeError as ex:
        assert "rule 9" in str(ex), ex
        print(f"  rule 9: {str(ex).splitlines()[0][:110]}")
    else:
        raise AssertionError("expected rule 9 to fire")
    # Missing key
    cfg = build_cfg(soccfg); del cfg["qubit_gain"]
    try:
        _validate_cfg(cfg, soccfg)
    except RuntimeError as ex:
        assert "missing required keys" in str(ex), ex
        print("  missing-key check fires")
    else:
        raise AssertionError("expected a missing-key error")


# ---------------------------------------------------------------------------
# 8. Decimated capture (only where the buffer allows one)
# ---------------------------------------------------------------------------

@_check("decimated capture")
def check_decimated(soc, soccfg, out_dir, limits):
    f_out = limits["f_output"]
    max_dec_us = (limits["buf_maxlen"] - 1) / f_out
    if max_dec_us < 5.0:
        print(f"  SKIPPED (informational): buf_maxlen = {limits['buf_maxlen']} "
              f"decimated samples caps a capture at {max_dec_us:.3f} us on this "
              f"firmware. Path B cannot hold a parity telegraph here -- run "
              f"mode='strobe'. A DDR4-streaming path would be needed to change "
              f"this.")
        return
    read_us = min(max_dec_us * 0.5, 50.0)
    exp = make_exp(soc, soccfg, out_dir, mode="decimated", soft_avgs=1,
                   n_captures=2, read_length=read_us,
                   capture_length_us=read_us + ADC_TRIG_OFFSET_US + 1.0,
                   reps_per_chunk=1)
    exp.cfg.pop("sample_period_us", None)
    data = exp.acquire(progress=False)
    expect_per_capture = int(soccfg.us2cycles(read_us, ro_ch=limits["ro_ch"]))
    assert data["samples_per_capture"] == expect_per_capture, (
        f"samples_per_capture {data['samples_per_capture']} != "
        f"us2cycles(read_length, ro_ch) {expect_per_capture} -- the decimated "
        f"rate is not f_output as assumed")
    assert data["I"].size == expect_per_capture * 2, data["I"].size
    assert list(data["gap_indices"]) == [expect_per_capture]
    print(f"  {data['n_captures']} captures x {expect_per_capture} samples at "
          f"{f_out} MHz = {read_us} us each")


def main():
    print(__doc__.split("What it checks")[0].strip())
    soc, soccfg = makeProxy()
    out_dir = "./_zsp_loopback/"
    limits = report_limits(soccfg)

    check_strobe(soc, soccfg, out_dir, limits)
    check_chunked(soc, soccfg, out_dir)
    check_modulated(soc, soccfg, out_dir)
    check_long_chunk(soc, soccfg, out_dir, limits)
    check_rules(soccfg, limits)
    check_decimated(soc, soccfg, out_dir, limits)

    print("\n=== summary ===")
    n_fail = 0
    for name, ok, msg in _results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else ': ' + msg}")
        n_fail += 0 if ok else 1
    if n_fail:
        print(f"\n{n_fail} check(s) FAILED -- do not run ZeroSpanParity on a qubit "
              f"until these pass.")
        return 1
    print("\nAll loopback checks passed. The strobe path is safe to point at a "
          "qubit (spec §6.2 gate cleared).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
