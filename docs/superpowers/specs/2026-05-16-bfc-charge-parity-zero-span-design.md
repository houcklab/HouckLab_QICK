# Zero-Span Two-Tone Charge-Parity Measurement on QICK / RFSoC

**Spec date:** 2026-05-16
**Author:** brainstormed with Claude Code
**Status:** design approved by user; awaiting implementation plan
**Target devices:** test_BTQ_BFC (first), CSTQ03 (production target)
**Edit scope:** `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/` only

## Problem statement

Detect charge-parity switching events on a transmon-style qubit with high temporal resolution by parking a readout drive at the cavity frequency that maximises dispersive contrast and parking a qubit drive at one of the two charge-parity-doublet peaks of f₀₁. When the qubit's parity switches, the qubit frequency shifts; the parked qubit drive becomes detuned, the qubit's steady-state |e⟩ population changes, and the cavity's dispersive response shifts. The resulting IQ time-trace shows bimodal jumps that mark parity transitions. The goal is to measure (a) baseline quasiparticle tunneling rates and (b) elevated rates during high-energy impact events, with temporal resolution beyond what a PNAX zero-span sweep can achieve.

## Scope summary

- **v1 — Path A (strobe):** rep-based pattern, ~10–30 μs/sample, effectively unbounded record length. Measures baseline parity rate and burst envelopes.
- **v2 — Path B (decimated):** `acquire_decimated()` pattern, sub-μs/sample, ~ms record per shot. Resolves intra-burst tunneling.
- Both modes support `start_src="internal"` (spontaneous long runs) and `start_src="external"` (triggered captures).
- Companion offline-analysis module classifies the raw IQ trace into parity bits, computes a sliding-window switch rate, detects bursts, and reports dwell-time statistics.
- One qubit at a time (MUX deferred). Classification done offline (no live state plotting in v1).

---

## §1 — File layout

All new files inside `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/`.

### Device-agnostic — built once, reused on every device

```
mZeroSpanParity.py            # Acquisition. Contains:
                              #   ZeroSpanParityProgStrobe       (Path A, QICK AveragerProgram)
                              #   ZeroSpanParityProgDecimated    (Path B, QICK AveragerProgram)
                              #   ZeroSpanParity                 (ExperimentClass dispatching on cfg["mode"])

analyze_ZeroSpanParity.py     # Offline analysis. Contains:
                              #   classify_parity_trace(I, Q, separator, method)
                              #   sliding_window_switch_rate(bits, t_us, window_us, step_us, gap_indices)
                              #   detect_bursts(rate, window_t, baseline, k_sigma, min_duration_us)
                              #   dwell_time_statistics(bits, t_us, gap_indices)
                              #   analyze_parity_run(h5_path, separator, window_us, k_sigma, save_plots, out_dir)
```

### Device-specific orchestrators — one per device

```
test_BTQ_BFC.py               # NEW: test device, first target. Skeleton patterned after
                              # CSTQ02_BFC.py:
                              #   - imports, makeProxy, yoko setup, Qubit_Parameters skeleton
                              #     (values left as TODO until device is characterized)
                              #   - transmission + spec calibration blocks
                              #   - coherence-benchmark block (T1FF, T2R, T2EFF,
                              #     optionally mAutoCoherence) — standard step on every
                              #     new device, see memory feedback_coherence_benchmark.md
                              #   - single-shot readout calibration
                              #   - zero-span parity block (this spec)
                              # Does NOT clone every CSTQ02-specific block verbatim;
                              # additional blocks pulled over from CSTQ02_BFC.py during
                              # device characterization as needed.

CSTQ03_BFC.py                 # CREATED LATER: clone of test_BTQ_BFC.py once parity
                              # measurement is validated on the test device. Not in
                              # scope for this spec — add via a follow-up phase/spec
                              # when CSTQ03 is ready.
```

### Shared helpers added to existing `utils.py` (no new helper file)

- `pick_parity_drive_freq(spec_data, which="lower" | "higher")` — wrapper around the existing `choose_two_tone_freqs_from_lorentz_or_peaks` that returns one of the two parity-doublet peaks plus the other for traceability.
- `chunked_acquire(experiment, n_chunks, **kwargs)` — runs the experiment's `acquire()` N times back-to-back for long records, stitching `prog.di_buf`/`prog.dq_buf` per chunk into a contiguous IQ trace with a recorded `gap_indices` list marking each chunk boundary.

### Classifier strategy

- **Primary (`method="apriori"`):** project each sample's (I, Q) onto a g→e separator obtained from a single-shot pi-pulse calibration done before the trace. Reuses `get_apriori_separator_from_singleshot` already implemented in `CSTQ02_BFC.py`. Threshold at midpoint → binary parity bits.
- **Fallback (`method="kmeans"`):** KMeans(n_clusters=2) clustered on the trace itself. `sklearn.cluster.KMeans` already imported in the orchestrator.

### Burst detection metric

- Bits → switch indicator `s_i = |b_i − b_{i−1}|`
- Sliding-window sum over `window_us` → switches per window → switch rate in Hz
- Burst = contiguous region where rate exceeds `baseline_rate + k·σ`, with robust baseline (median) and σ from MAD so the burst itself doesn't inflate the threshold.

### Out of scope for this spec

- Live / online parity plotting during acquisition (v1 plots after run completes)
- Live / online burst detection / alerting
- Multi-qubit MUX simultaneous parity measurement
- Triggering external hardware on detected bursts
- CSTQ03_BFC.py orchestrator (separate phase when CSTQ03 is ready)

---

## §2 — Acquisition architecture (QICK program design)

### Shared initialization

Private helper called from both programs' `initialize()`:

```python
def _setup_two_tones(self):
    cfg = self.cfg
    self.declare_gen(ch=cfg["res_ch"],   nqz=cfg["nqz"],       mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
    self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
    for ch in cfg["ro_chs"]:
        self.declare_readout(ch=ch,
                             length=self.us2cycles(cfg["read_length"]),
                             freq=cfg["read_pulse_freq"],
                             gen_ch=cfg["res_ch"])
    f_res = self.freq2reg(cfg["read_pulse_freq"],   gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
    f_qub = self.freq2reg(cfg["parity_drive_freq"], gen_ch=cfg["qubit_ch"])
    return f_res, f_qub
```

`parity_drive_freq` is one of the two parity-doublet peaks (picked by `pick_parity_drive_freq` at the orchestrator level). `read_pulse_freq` reuses the already-tuned single-shot readout frequency from `Qubit_Parameters[i]['Readout']['Frequency']`.

### Path A — `ZeroSpanParityProgStrobe` (v1)

Both tones held on for the full duration of each rep, reps run back-to-back with no `relax_delay` → ~95%+ duty cycle ≈ effective CW from the qubit's perspective.

```python
class ZeroSpanParityProgStrobe(AveragerProgram):
    def initialize(self):
        f_res, f_qub = self._setup_two_tones()
        cfg = self.cfg
        period_cyc_q = self.us2cycles(cfg["sample_period_us"], gen_ch=cfg["qubit_ch"])
        period_cyc_r = self.us2cycles(cfg["sample_period_us"], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=f_qub, phase=0,
                                 gain=cfg["qubit_gain"], length=period_cyc_q)
        self.set_pulse_registers(ch=cfg["res_ch"],   style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"], length=period_cyc_r)

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=0)
```

`reps` = number of time samples per `acquire()` call. ExperimentClass `acquire()` extracts `prog.di_buf[ro_ch]` and `prog.dq_buf[ro_ch]` (per-rep raw IQ), builds a time axis `t = np.arange(reps) * sample_period_us`, and returns `{'I', 'Q', 't_us', 'wall_clock_start'}`.

**Long-record support via `chunked_acquire`**: when `reps × sample_period > avg_maxlen × sample_period`, the orchestrator calls `acquire()` N times back-to-back, stitching IQ/t arrays. Small inter-call gaps (~ms, from Python/tProc overhead) are recorded as `gap_indices` so the analysis module can avoid counting spurious switches across them.

### Path B — `ZeroSpanParityProgDecimated` (v2)

```python
class ZeroSpanParityProgDecimated(AveragerProgram):
    def initialize(self):
        f_res, f_qub = self._setup_two_tones()
        cfg = self.cfg
        capture_cyc_q = self.us2cycles(cfg["capture_length_us"], gen_ch=cfg["qubit_ch"])
        capture_cyc_r = self.us2cycles(cfg["capture_length_us"], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=f_qub, phase=0,
                                 gain=cfg["qubit_gain"], length=capture_cyc_q)
        self.set_pulse_registers(ch=cfg["res_ch"],   style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"], length=capture_cyc_r)

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=0)
```

`reps=1`. ExperimentClass `acquire()` calls `prog.acquire_decimated(self.soc, soft_avgs=cfg.get("soft_avgs",1), start_src=cfg["start_src"], progress=progress)` instead of `prog.acquire()`. Returns `{'I': dec[:,0], 'Q': dec[:,1], 't_us': np.arange(N)/decimated_fs_MHz, 'decimated_fs_MHz': ...}`.

### ExperimentClass dispatcher

```python
class ZeroSpanParity(ExperimentClass):
    def acquire(self, progress=False):
        mode = self.cfg.get("mode", "strobe")
        if mode == "strobe":
            return self._acquire_strobe(progress=progress)
        if mode == "decimated":
            return self._acquire_decimated(progress=progress)
        raise ValueError(f"Unknown mode: {mode}")
```

External-trigger support is just passing `cfg["start_src"]` (`"internal"` or `"external"`) through to the underlying `acquire`/`acquire_decimated` calls.

### Key constraints surfaced in the design

1. **Sample-period floor:** `sample_period_us ≥ adc_trig_offset + read_length + ~1 μs tProc overhead`. Validated in `__init__`; fail fast.
2. **Pulse-length cap:** const-pulse `length` must fit in 16-bit cycles (`< 65535`). For typical clocks this caps `sample_period_us` and `capture_length_us` at a few hundred μs. `chunked_acquire` absorbs this for long records.
3. **Buffer caps:** Path A capped at `avg_maxlen` reps per `acquire()` call; Path B capped at `buf_maxlen` decimated samples per call. Both read from `soccfg['readouts'][ch]` at runtime and validated before launching the program.
4. **Drive-on duty cycle:** the const pulse is re-issued every rep, leaving a small inter-rep gap (~tens of cycles). As long as `qubit_T1, T_Rabi >> gap`, the drive is effectively CW. Will be measured empirically during v1 validation and documented.
5. **No readout ringdown between samples:** the readout const pulse covers the entire sample period, so the cavity is always driven — no transient ringdown between samples (unlike normal pulsed readouts). This is exactly what zero-span needs.

---

## §3 — Offline analysis (`analyze_ZeroSpanParity.py`)

Five functions. Each callable independently for re-analysis with different parameters (different sliding-window length, different burst threshold, etc.).

### 3.1 `classify_parity_trace(I, Q, separator=None, method="apriori")`

- `method="apriori"`: uses `separator` dict `{g_center, e_center, normal, midpoint}` from a prior single-shot pi-pulse calibration. Projects each sample along `normal`, thresholds at 0. Same math as `classify_and_average_iq` in `utils.py` — that projection step is extracted into a small primitive and reused here.
- `method="kmeans"`: fits `KMeans(n_clusters=2)` on (I, Q). Labels remapped so label 0 = cluster with the lower projection on the e-g axis.

Returns `{binary_states, scores, separator_used, method}`.

### 3.2 `sliding_window_switch_rate(binary_states, t_us, window_us, step_us=None, gap_indices=None)`

- `s_i = |b_i − b_{i−1}|`
- Per window of duration `window_us`: `rate_Hz = sum(s in window) / (window_us × 1e-6)`
- `step_us` default = `window_us // 2` (50% overlap). Use `step_us = window_us` for non-overlapping (statistical independence).
- `gap_indices` (from `chunked_acquire`) — diffs across these indices are zeroed so a chunk boundary doesn't masquerade as a transition.

Returns `{window_t_us, rate_Hz, switches_per_window, window_us, step_us}`.

### 3.3 `detect_bursts(rate_Hz, window_t_us, baseline_rate=None, k_sigma=5, min_duration_us=None)`

- `baseline_rate`: defaults to `median(rate_Hz)`.
- `sigma`: robust = `1.4826 * MAD(rate_Hz)`.
- `threshold = baseline_rate + k_sigma * sigma`.
- Contiguous-windows-above-threshold; optionally filtered by `min_duration_us`.

Returns list of dicts: `{t_start_us, t_end_us, duration_us, peak_rate_Hz, mean_rate_Hz, integrated_excess_switches, baseline_rate_Hz, threshold_Hz}`.

### 3.4 `dwell_time_statistics(binary_states, t_us, gap_indices=None)`

Lengths of contiguous runs in state 0 and state 1, in μs. Runs spanning `gap_indices` are split, not joined.

Returns `{dwell_0_us, dwell_1_us, mean_0, mean_1, n_runs_0, n_runs_1, exp_fit_0, exp_fit_1}`. Exponential fits return `{tau_us, A}` (or `{tau: nan, A: nan}` if fit fails). Two reasons to track this: (a) the parity-tunneling rate is `1 / mean_dwell` per state; (b) large asymmetric dwell between state 0 and 1 is diagnostic of a miscalibrated parking frequency.

### 3.5 `analyze_parity_run(h5_path, separator=None, window_us=1000, k_sigma=5, save_plots=True, out_dir=None)`

Top-level orchestrator. Loads the raw `.h5`, calls 3.1–3.4 in order, saves all plots, writes a sidecar `_analysis.h5` with all derived arrays and a `_analysis.json` with scalar results.

Plot outputs (same naming convention as `save_two_tone_plot` in `utils.py`):

- `*_iq_scatter.png` — I vs Q colored by classified state, separator drawn
- `*_parity_vs_time.png` — binary raster (downsampled for traces > 10⁵ samples)
- `*_switch_rate_vs_time.png` — rate(t) with baseline + threshold + burst shading
- `*_dwell_histograms.png` — log-y histograms of dwell times with exponential fits

### Performance and correctness guards

- **Plot downsampling:** parity-vs-time plot with > 100k samples rendered via `np.histogram2d` (time bin × state bin) so PNG generation stays under ~1 s even for 10M-sample runs.
- **Chunk gaps respected:** `gap_indices` propagates into 3.2 and 3.4.
- **Empty / degenerate inputs:** all functions return sensible structures (zero rates, empty burst list, nan exponential fits) without exceptions.
- **Pure functions:** 3.1–3.4 take arrays and return dicts; no file I/O. Only 3.5 touches disk. Testable on synthetic data.

---

## §4 — Orchestrator (`test_BTQ_BFC.py`)

Follows your `CSTQ02_BFC.py` style: top-level boolean flags + per-experiment parameter dicts + linear execution. Reuses existing helpers (`makeProxy`, yoko ramp, `get_apriori_separator_from_singleshot`, `choose_two_tone_freqs_from_lorentz_or_peaks`).

The orchestrator includes blocks for:

1. **Imports + hardware setup** (mirrors CSTQ02_BFC.py)
2. **`Qubit_Parameters` dict** — values TODO until test_BTQ_BFC is characterized
3. **Transmission + spec calibration block** (`CavitySpecFF`, `QubitSpecSliceFF`)
4. **Coherence-benchmark block** (`T1FF`, `T2R`, `T2EFF`, optionally `mAutoCoherence`) — standard step on every new device; see memory `feedback_coherence_benchmark.md`
5. **Single-shot readout calibration**
6. **Zero-span parity block** (this spec — see §4.2/§4.3 below)

### §4.1 Top-level structure (parity block only)

```python
from utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import analyze_parity_run
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX

soc, soccfg = makeProxy()
# (yoko, Qubit_Parameters, calibration blocks omitted here — see CSTQ02_BFC.py for pattern)
```

### §4.2 Per-run flags (the "what to do this run" section)

```python
Qubit_Target              = 1                                    # which row of Qubit_Parameters
outerFolder               = Qubit_Parameters[str(Qubit_Target)]['outerfoldername'] + "ZeroSpanParity/"

RecalibrateParityFreqs    = True
RecalibrateSeparator      = True

ParityFreqs_Cached = {"lower_peak_MHz": None, "higher_peak_MHz": None, "which_to_park": "lower"}
Separator_Cached   = {"g_center": None, "e_center": None, "normal": None, "midpoint": None}

RunMode  = "strobe"             # "strobe" | "decimated"
StartSrc = "internal"           # "internal" | "external"

StrobeParams = {
    "sample_period_us": 20, "reps_per_chunk": 50000, "n_chunks": 12,
    "read_length": 5, "adc_trig_offset": 0.488,
}
DecimatedParams = {
    "capture_length_us": 1000, "soft_avgs": 1, "n_captures": 1,
    "read_length": 1000, "adc_trig_offset": 0.488,
}
DriveParams = {
    "qubit_gain": Qubit_Parameters[str(Qubit_Target)]["Qubit"]["Gain"],
    "pulse_gain": Qubit_Parameters[str(Qubit_Target)]["Readout"]["Gain"],
    "res_phase":  0,
}
AnalysisParams = {
    "classifier_method": "apriori",
    "window_us": 1000, "k_sigma": 5,
    "min_burst_duration_us": None, "save_plots": True,
}
```

### §4.3 Execution flow

1. **Optional pre-calibration of parity-doublet freqs** — runs a narrow `QubitSpecSliceFF`, fits two Lorentzians via `find_two_tone_peaks` / `choose_two_tone_freqs_from_lorentz_or_peaks`, parks at chosen peak.
2. **Optional g/e separator calibration** — runs `SingleShotProgramFFMUX` with a pi-pulse via your existing `get_apriori_separator_from_singleshot`.
3. **Build `zsp_cfg`** by merging `BaseConfig`, `Qubit_Parameters[Qubit_Target]`, the mode-specific param block, `DriveParams`, and the picked drive frequency.
4. **Run** `ZeroSpanParity` directly, or via `chunked_acquire` when `RunMode == "strobe"` and `n_chunks > 1`.
5. **Persist** raw data + config via the standard `ExperimentClass.save_data` / `save_config` machinery.
6. **Analyze** by calling `analyze_parity_run(h5_path=exp.fname, separator=Separator_Cached, ...)`.

The script raises immediately if cached values are `None` and the corresponding `Recalibrate*` flag is `False` — no silent fall-through.

---

## §5 — Configuration contract

### §5.1 Once-per-setup prerequisites (already in place)

| Prerequisite | Where | Why |
|---|---|---|
| QICK Pyro4 server at `192.168.1.7:8888` | RFSoC board | `makeProxy()` succeeds |
| Yoko on `GPIB1::9::INSTR` | lab GPIB bus | flux bias (matches CSTQ02_BFC.py) |
| `Qubit_Parameters[str(Qubit_Target)]` populated with `Readout.Frequency`, `Readout.Gain`, `Qubit.Frequency`, `Qubit.Gain`, `Qubit.sigma`, `outerfoldername` | top of orchestrator | drive/readout gains, parking frequencies, save path |
| `BaseConfig` defines `res_ch`, `qubit_ch`, `ro_chs`, `nqz`, `qubit_nqz`, `mixer_freq` | `Calib/initialize4Q.py` | hardware channel routing |

### §5.2 Per-run parameters

**Always required:** `Qubit_Target`, `RunMode`, `StartSrc`, `RecalibrateParityFreqs`, `RecalibrateSeparator`, `ParityFreqs_Cached["which_to_park"]`.

**Required if `RecalibrateParityFreqs=False`:** `ParityFreqs_Cached["lower_peak_MHz"]` or `["higher_peak_MHz"]` (whichever matches `which_to_park`).

**Required if `RecalibrateSeparator=False`:** all four `Separator_Cached` fields as `np.ndarray` shape (2,).

**Required if `RunMode="strobe"`:** `sample_period_us`, `reps_per_chunk`, `n_chunks`, `read_length`, `adc_trig_offset`.

**Required if `RunMode="decimated"`:** `capture_length_us`, `soft_avgs`, `n_captures`, `read_length`, `adc_trig_offset`.

**Drive (mode-independent):** `qubit_gain`, `pulse_gain`, `res_phase`.

**Analysis:** `classifier_method`, `window_us`, `k_sigma`, `min_burst_duration_us`, `save_plots`.

### §5.3 Validation rules (fail-fast in `ZeroSpanParity.__init__`)

1. `sample_period_us ≥ adc_trig_offset + read_length + 1.0` (μs) — otherwise reads overlap.
2. `us2cycles(sample_period_us, gen_ch=qubit_ch) ≤ 65535` and same for `res_ch`.
3. `us2cycles(capture_length_us, …) ≤ 65535` for decimated mode.
4. `reps_per_chunk ≤ soccfg['readouts'][ro_ch]['avg_maxlen']`.
5. `us2cycles(capture_length_us) × decimated_fs ≤ soccfg['readouts'][ro_ch]['buf_maxlen']`.
6. If `RecalibrateParityFreqs=False`, the cached freq selected by `which_to_park` must be a finite float.
7. If `RecalibrateSeparator=False` AND `classifier_method="apriori"`, all four `Separator_Cached` fields must be `np.ndarray` of shape `(2,)`.
8. `parity_drive_freq` must lie inside the qubit channel's DDS band `[-f_dds/2, +f_dds/2]` (QICK's `freq2reg` valid range), read from `soccfg['gens'][qubit_ch]['f_dds']`. NOT `[0, f_dds]`.
9. `capture_length_us ≥ adc_trig_offset + read_length` (decimated mode) — the const pulse must cover the entire readout window, otherwise the pulse ends before the readout closes.

**Enforcement layer.** Rules 1–5, 8, and 9 validate cfg keys present at construction and are enforced fail-fast in `ZeroSpanParity.__init__` (via `_validate_cfg`). Rules 6–7 validate *orchestrator* state — the `Recalibrate*` flags and the cached parking freq / separator — that is resolved **before** `cfg` is built: by the time `ZeroSpanParity` is constructed, the picked frequency is already a plain `parity_drive_freq` (re-checked by rule 8) and the separator is an analysis-time argument that never enters `cfg`. Rules 6–7 are therefore enforced in the orchestrator (see §4.3), not in `__init__`.

Errors include the rule number and the offending value vs. the violated bound. Example:

```
RuntimeError: [ZeroSpanParity §5.3 rule 1] sample_period_us=0.5 us is below floor
(adc_trig_offset + read_length + 1.0 = 6.488 us). Increase sample_period_us or
shorten read_length.
```

### §5.4 Minimum-effort run

After the first calibrated run, typical follow-up runs only edit 1–3 lines:

- Change `Qubit_Target` for a different qubit.
- Set both `Recalibrate*=False`, ensure cached values populated.
- Adjust `n_chunks` for longer record, or `sample_period_us` for different cadence.
- Optionally flip `StartSrc` to `"external"`.

Everything else stays.

### §5.5 Where the contract lives in the code

1. **`test_BTQ_BFC.py` module docstring** — condensed §5.2 + §5.3 + §5.4 as a triple-quoted block at the top of the file, mentioning the canonical spec path as the full reference.
2. **Per-section comment headers** above each `*Params` dict in the orchestrator.
3. **`ZeroSpanParity` class docstring** in `mZeroSpanParity.py` — lists every cfg key the class consumes, with required/optional + default + constraint.
4. **Validation errors** include `§5.3 rule N` tag + offending value + bound.
5. **This spec** at `docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md` remains canonical; param additions must update spec §5 and all three code locations together.

---

## §6 — Validation & test plan

### §6.1 Offline unit tests for `analyze_ZeroSpanParity.py` (no hardware)

Under `if __name__ == "__main__":` in the analysis file (no `tests/` directory in this project).

| Test | Synthetic input | Assertion |
|---|---|---|
| `classify_parity_trace` apriori | Two Gaussian IQ clouds at known centers; 50/50 mix | accuracy > 99% |
| `classify_parity_trace` kmeans fallback | Same clouds, no separator | accuracy > 99%, label remap deterministic |
| `sliding_window_switch_rate` | Random bits with known switch probability per sample | recovered rate within ±2σ; gaps zero diffs correctly |
| `detect_bursts` | Baseline 100 Hz, injected 10 kHz burst lasting 1 ms | one burst returned, edges within ±1 stride |
| `dwell_time_statistics` | Markov chain with known τ₀, τ₁ | fitted `tau_0`, `tau_1` within ±5% |
| `analyze_parity_run` end-to-end | Synthetic .h5 | all 4 PNGs created, scalars in `_analysis.json` match |

Run time: <5 s total. Pass before hardware.

### §6.2 Hardware-loopback smoke test (RFSoC, no qubit)

DAC → ADC loopback cable (your existing `Calibrate_loopback.py` setup). Run `ZeroSpanParity` with a placeholder `parity_drive_freq` and tiny `pulse_gain`.

| Check | How | Pass criterion |
|---|---|---|
| Strobe shape | `reps_per_chunk=1000, n_chunks=1` | `data["I"].shape == (1000,)`, `data["t_us"].shape == (1000,)` |
| `chunked_acquire` stitching | `n_chunks=5, reps_per_chunk=1000` | Total `(5000,)`; `gap_indices == [1000, 2000, 3000, 4000]`; no dupes |
| Time axis | inspect `data["t_us"]` | strictly increasing; `mean(diff) == sample_period_us ± 1 cycle` |
| Decimated length | `RunMode="decimated", capture_length_us=500` | `shape == (500 * decimated_fs_MHz,)`; rate matches `soccfg['readouts'][ro_ch]['f_output']` |
| §5.3 validation rules | feed bad config | each raises `RuntimeError` naming the rule + bound |

Run time: <30 s total. Pass before real qubit.

### §6.3 Physics-level validation on a real qubit (test_BTQ_BFC, then CSTQ03)

**Prerequisite:** the qubit is in a regime where the parity measurement is meaningful — T1 substantially longer than `sample_period_us`, T2 long enough that the dispersive shift is resolved during `read_length`. **Coherence times (T1, T2R, T2E) must be measured before the parity validation stages**, both as a sanity check and as the per-device performance benchmark archived alongside the parity dataset.

**Stage 1 — Drive parks correctly.** Park qubit drive at one parity peak. Run ~1 s strobe trace. **Pass:** clearly bimodal IQ scatter. Two separated clusters confirm drive on-resonance with one parity AND parity switching during the run. Fails point to wrong parking freq, drive too weak, or parity switching faster than `sample_period`.

**Stage 2 — Bimodality vanishes off-doublet.** Park drive between peaks or several MHz away. Re-run. **Pass:** unimodal scatter. Confirms Stage 1 bimodality came from parity.

**Stage 3 — Switching rate consistent with reference.** Run `analyze_parity_run` on the Stage-1 trace. Compare baseline rate to (a) literature for similar transmons and (b) a same-day PNAX zero-span on the same qubit at the same flux. **Pass:** agreement within a factor of 2 between methods, within published range for the qubit family.

**Stage 4 — Dwell-time symmetry diagnostic.** Check `dwell_time_statistics`. **Pass:** dwells in state 0 and 1 within ~2× when parking on one peak. Large asymmetry → recalibrate parking frequency.

**Stage 5 — Burst detection (impact source).** With a particle source or scintillator coincidence, run with `StartSrc="external"` triggered on the scintillator. **Pass:** `detect_bursts` returns a burst within ±1 window stride of the trigger time, elevated rate above baseline. **Deferrable to v2** if no source available.

### §6.4 v1 acceptance criteria

- All §6.1 offline tests pass
- All §6.2 loopback tests pass
- §6.3 Stages 1–4 pass on at least one qubit on test_BTQ_BFC (Stage 5 deferred to v2)
- A reference long-run (≥ 1 minute trace, `sample_period_us = 20`) saved with `_analysis.h5` + plots, archived as known-good baseline
- §5 configuration contract mirrored in all three code locations from §5.5

### §6.5 v2 acceptance criteria

- §6.2 loopback tests pass for `RunMode="decimated"`
- §6.3 Stage 1 reproduces bimodality in the decimated trace (expect to need digital low-pass smoothing for visualization)
- §6.3 Stage 5 passes with at least one externally-triggered impact
- Side-by-side v1 strobe vs. v2 decimated on the same qubit shows consistent burst times and rates within statistical agreement

### §6.6 Phasing for device-blocked validation

**Executable immediately (no device required):**

- All of §6.1 (offline unit tests on synthetic data)
- All of §6.2 (RFSoC loopback smoke tests)
- Full implementation of `mZeroSpanParity.py`, `analyze_ZeroSpanParity.py`, `utils.py` additions
- `test_BTQ_BFC.py` skeleton with the parity block ready to invoke

**Blocked on test_BTQ_BFC cooldown and characterization:**

- §6.3 Stage 1–4 (physics validation)
- First real long-record dataset

**Blocked on CSTQ03 cooldown:**

- §6.3 Stage 5 (impact source) — may run on test_BTQ_BFC instead if a source is available there
- Full repeat of §6.3 on the production chip
- `CSTQ03_BFC.py` orchestrator (new spec / phase when CSTQ03 is ready)

**Resume-work entry point when test_BTQ_BFC is ready:**

1. Confirm offline + loopback still pass after any QICK changes
2. Characterize the device via transmission / spec / single-shot
3. **Measure T1 / T2 / T2E coherence times — the device benchmark**
4. Fill `Qubit_Parameters` in `test_BTQ_BFC.py`
5. Run §6.3 Stages 1–4 in order
6. Archive the baseline trace per §6.4 alongside the measured coherence values for the same qubit

---

## §7 — Implementation notes (post-spec changes)

The implementation has been adjusted from the spec sketch in §2/§3/§5 during
review. These changes are deliberate and treated as part of the
contract from here on; the spec sections above remain authoritative for the
architecture, but the specifics below override the example code in §2 and
the parameter list in §5 where they conflict.

### §7.1 — Strobe I/Q normalization (Path A)

`ZeroSpanParity._acquire_strobe` divides the raw `prog.di_buf` /
`prog.dq_buf` accumulated values by `us2cycles(read_length, ro_ch=ro_ch)`
before returning. This puts I/Q in per-cycle units, matching the scale
returned by `mSingleShotProgramFFMUX.collect_shots` so an apriori separator
calibrated from single-shot data classifies the strobe trace correctly.

Persisted in the .h5: `ro_norm_cycles` (the divisor actually applied),
`read_length_us`, `adc_trig_offset_us`.

### §7.2 — Decimated soft_avgs gate and `n_captures` stitching (Path B)

- `soft_avgs > 1` averages across independent parity captures and destroys
  the time-resolved trajectory. `_acquire_decimated` now rejects this unless
  the caller explicitly sets `cfg["allow_soft_avgs"] = True`.
- `n_captures` (optional, default 1) runs the decimated acquisition outer
  loop N times back-to-back. Captures are concatenated with `gap_indices`
  marking the boundaries, mirroring `chunked_acquire` semantics for strobe
  mode. Per-capture wall-clock starts are saved as `chunk_wall_clock_starts`.

### §7.3 — Decimated time-axis caveat

`t_us` is built from `soccfg["readouts"][ro_ch]["f_output"]`. Loopback
checks empirically observed that this is not necessarily the true firmware
decimation rate. The acquisition therefore persists:

- `decimated_fs_MHz` — the value read from soccfg
- `decimated_fs_source` — `"soccfg.f_output_unverified"` provenance tag
- `samples_per_capture` — actual returned sample count per capture
- `read_length_us`, `capture_length_us`, `adc_trig_offset_us`

This is sufficient to reconstruct a corrected time axis post-hoc after a
hardware-loopback rate calibration. Until that calibration is performed,
`t_us` should be treated as nominal.

### §7.4 — Analysis binning is opt-in (not auto)

`analyze_parity_run(analysis_bin_us=...)` no longer auto-bins decimated
traces by `read_length_us`. Auto-binning was incorrect because a real
decimated capture covers exactly one `read_length` end-to-end — auto-binning
by the full read_length would collapse each capture to a single point. The
analysis function now defaults to no binning; callers that need integrated
bins to match an apriori single-shot separator's SNR pass an explicit
`analysis_bin_us` smaller than `read_length_us`.

The analysis sidecar records `analysis_bin_us`, `raw_sample_period_us`,
`n_raw_samples`, `n_binned_samples`, `n_samples_dropped_by_binning`, and
`mode` so post-hoc readers can disambiguate raw rate from analysis rate.

### §7.5 — Validation rule 5 caveat

Rule 5 estimates the decimated buffer occupancy as
`read_length_us * f_output_MHz` decimated samples. The actual buffer length
depends on QICK's internal conversion of `us2cycles(read_length)` (called
without `ro_ch`) into readout-clock cycles, then decimation. On firmware
where tProc and readout clocks differ, the exact returned sample count may
disagree by O(1) sample. The pre-flight check is still a sufficient bound,
just not an exact one; hardware loopback should confirm the actual count.

### §7.6 — Cfg keys added by implementation

Beyond the §5.2 list:

- `allow_soft_avgs` (optional, decimated mode) — bool, opt-in to
  `soft_avgs > 1`.
- `n_captures` (optional, decimated mode) — int, outer-loop count.

These are documented in `mZeroSpanParity.py`'s module docstring and
`test_BTQ_BFC.py`'s `DecimatedParams` comment block.

---

## Glossary

- **Parity doublet:** the two charge-dispersion peaks of a transmon's f₀₁ separated by `ε₀₁`; the qubit's frequency hops between them on charge-parity tunneling events.
- **Zero-span:** measurement at fixed frequencies vs. time (no frequency sweep). PNAX terminology, repurposed here for QICK.
- **Strobe / Path A:** stroboscopic rep-based acquisition; each rep yields one integrated IQ sample.
- **Decimated / Path B:** raw decimated-ADC waveform via `acquire_decimated()`.
- **BFC:** Broadband Flux Control — the user's active project context.
- **MAD:** median absolute deviation; robust scale estimate, σ ≈ 1.4826 × MAD.

## Related files

- Existing experiment closest to v1: `mChargeDispersionQuasiCW.py`
- Existing two-tone CW driver (no acquisition): `mConstantTwoTone.py`
- Shared analysis primitives: `utils.py` (`classify_and_average_iq`, `choose_two_tone_freqs_from_lorentz_or_peaks`, `find_two_tone_peaks`, `save_two_tone_plot`)
- Single-shot calibration helper: `get_apriori_separator_from_singleshot` in `CSTQ02_BFC.py`
- QICK acquisition base: `.venv/Lib/site-packages/qick/qick_asm.py:2040` (`acquire_decimated`)
- QICK streamer (for future continuous-streaming work): `.venv/Lib/site-packages/qick/streamer.py`
