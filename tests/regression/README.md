# Hardware-free regression harness

A golden-master snapshot of what the CSTQ03 runner sends to the hardware. It
exists so the coming refactor can be checked against the pre-refactor code
without a fridge, a board or a yoko.

```
python -m pytest tests/regression -q                       # compare against the golden (~5 min)
REGRESSION_LABELS=RunT1,RunT2 python -m pytest tests/regression -q   # just some runs
REGRESSION_UPDATE=1 python -m pytest tests/regression -q   # rewrite the golden from current code
python -m tests.regression.driver_legacy                   # same as UPDATE, without pytest
python -m tests.regression.driver_legacy RunT1             # dry run, golden untouched
```

Run from the repo root (`pyproject.toml` / `tests/conftest.py` put it on `sys.path`).

## Files

| File | Role |
|---|---|
| `capture.py` | Layout-agnostic core: fakes, instrumentation, normalisation. Reused unchanged after the refactor. |
| `driver_legacy.py` | Replays every dispatch of `Runners/CSTQ03_BFC.py`. |
| `golden_cstq03.json` | The snapshot, keyed by run label. |
| `test_golden.py` | Re-captures in memory and diffs per label. `DRIVER` at the top selects the driver. |

## What one capture contains

The driver executes the runner's sections 1-2 (parameters, flags, param dicts)
verbatim, then parses section 3 (EXECUTE). For every `if <Flag>: ...` line it
runs, with only that flag set: the unconditional statements before it
(`build_context`, and `rebuild_singleshot_config` for single-shot-regime
flags), the body, and the unconditional statements after it (`ctx.yoko.close()`).
Every flag is exercised whatever its value in the file. `RunZeroSpanParity`
runs twice: once as configured, once (`RunZeroSpanParity[validate]`) with every
`Validate_*` / `Build_*` sub-flag on.

Per run label the golden holds:

* `outcome`: `completed`, `stopped_at_budget`, or `raised` (type, message, traceback tail).
* `yoko_writes`: every `OPEN`/`W`/`Q`/`CLOSE` on the voltage source, in order.
* `experiments`: every `ExperimentClass` instantiation, in order, with
  * `cls`, `path`, `outerFolder`, `fname` (data root and timestamps masked);
  * `cfg`: the full config dict right after `ExperimentClass.__init__`;
  * `methods`: `acquire`/`display`/`save_data`/`save_config`/`analyze` calls with
    their non-data kwargs (identical consecutive calls run-length encoded);
  * `hw`: what that experiment sent to the board while its `acquire` ran: call
    counts, number of (unique) tProc programs, and a sha256 over the ordered
    stream of compiled binaries, pulse envelopes, nyquist/readout/buffer
    configuration and readout requests.
* `hw_outside_experiments`: board calls made outside any `acquire` (e.g. `reset_gens`).

## How the hardware is faked

| Real | Fake |
|---|---|
| `makeProxy()` (Pyro4) | `(FakeSoc(), FakeSocCfg())`, patched in `socProxy` and every module that star-imported it. |
| `QickConfig` | A genuine `QickConfig` over `SYNTHETIC_SOCCFG`: tProc v1 at 430.08 MHz, 7 mixer-less `axis_signal_gen_v6` gens (fabric 430.08 MHz), 2 `axis_readout_v2` readouts at 307.2 MHz, `avg_maxlen` 16384. Every program compiles through real QICK code. |
| `QickSoc` | `FakeSoc`: records every call; answers readout requests with seeded two-blob IQ data of exactly the shape QICK returns. |
| `pyvisa.ResourceManager` | `FakeYoko` that tracks its level, so `ramp_to` terminates. |
| `time.sleep`, `plt.show`, `plt.pause`, `Figure.savefig` | No-ops. |
| `datetime` in project modules | Virtual clock, +1 s per `now()`, reset each run (otherwise back-to-back experiments with sleeps disabled would share an h5 filename). |

Experiments run their **real** `acquire()` against `FakeSoc`, so the synthetic
data always has the shape the code expects and every program the code builds is
compiled. `display()` is a no-op (kwargs are still logged). `save_data` and
`save_config` run for real into a throw-away temp dir, because downstream
analysis (`analyze_parity_run`) reads the saved file back. Each run is capped at
12 instantiations: the 13th raises `StopCapture` (a `BaseException`, so the code
under test cannot swallow it) and the run is recorded as `stopped_at_budget`.
RNGs are seeded from the run label, so runs are independent of order.

## What a passing test proves

For the CSTQ03 parameters in the runner, and for each flag:

* the same experiment classes are created in the same order, with the same
  `path`/`outerFolder` and an identical `cfg` (every key; `int` vs `float`
  compared strictly, floats to a relative 1e-9);
* the same experiment methods are called with the same arguments;
* the board receives byte-identical tProc binaries, envelopes and channel
  configuration, in the same order;
* the yoko receives the same command sequence.

## What it cannot prove

* **Data-dependent control flow is only tested on synthetic data.** Everything
  downstream of an acquisition (peak finding, fits, sweet-spot searches, which
  voltage a search walks to, how many cycles a loop runs before a criterion is
  met) follows the seeded noise, not physics. Branches that this data never
  takes are not covered.
* **tProc programs are compiled and fingerprinted but never executed.** Any
  change to a program body shows up as a digest change, but whether a program is
  *correct* (timing, conditional reset, loop counts) still rests on code review,
  and on `verify_ModifiedRamsey_timing.py` against the board.
* **The board is synthetic.** The tProc, gen-fabric and readout clocks and
  `avg_maxlen` match what the lab's RFSoC reports; channel count, refclk, DDS
  widths and buffer sizes are invented. Digests prove "same as before", not
  "right for the board".
* **`display()` is not exercised**: plotting and any fit done only inside
  `display()` are untested, and attributes it would set do not exist.
* **Only the first 12 instantiations per run** are captured; later loop
  iterations are assumed to repeat the same pattern.
* **Only the CSTQ03 parameter set** in the runner is exercised.
* `traceback` entries are diagnostic only and excluded from the comparison
  (their line numbers move with any edit).

## Run labels (golden at commit time)

31 labels: 30 runner flags plus the `[validate]` variant. Every label but one
reaches at least one experiment. Full capture takes ~5 min, mostly
`RunUndrivenSingleShot` (~85 s: the real 1e6-shot GMM analysis inside its
`acquire`), `SingleShot_QubitOptimize` (~45 s) and `RunZeroSpanParity[validate]` (~30 s).

| Run label | Outcome | Experiments | Classes (count) | tProc programs |
|---|---|---|---|---|
| `Constant2Tone` | stopped_at_budget | 12 | ConstantTwoTone x12 | 12 |
| `ConstantTone` | completed | 1 | SingleTone x1 | 100 |
| `RunTransmissionSweep` | completed | 1 | CavitySpecFF x1 | 201 |
| `RunTransmissionSweeps` | completed | 1 | CavitySpecFF x1 | 201 |
| `Run2ToneSpec` | completed | 1 | QubitSpecSliceFF x1 | 1 |
| `RunSpecGainLengthSweep` | stopped_at_budget | 12 | QubitSpecSliceFF x12 | 12 |
| `RunChiShift` | completed | 1 | ChiShift x1 | 202 |
| `Run2ToneChargeDispersionQuasiCW` | stopped_at_budget | 12 | QubitSpecSliceFF x8, ChargeDispersionQuasiCW x4 | 12 |
| `RunModifiedRamsey` | stopped_at_budget | 12 | SingleShotProgramFFMUX x5, ModifiedRamsey x7 | 17 |
| `RunModifiedRamsey_Control` | stopped_at_budget | 12 | QubitSpecSliceFF x12 | 12 |
| `RunChargeDispersionQuasiCW` | completed | 1 | ChargeDispersionQuasiCW x1 | 1 |
| `RunChargeDispersionRamsey` | raised (KeyError 'df') | 0 | - | 0 |
| `RunAmplitudeRabi` | completed | 1 | AmplitudeRabiFF x1 | 1 |
| `RunT1` | stopped_at_budget | 12 | T1FF x12 | 12 |
| `RunT1T2E` | stopped_at_budget | 12 | T1FF x6, T2EMUX x6 | 12 |
| `RunT1T2RT2E` | stopped_at_budget | 12 | T1FF x4, T2EMUX x4, T2R x4 | 12 |
| `RunT2` | stopped_at_budget | 12 | T2R x12 | 12 |
| `RunT2E` | stopped_at_budget | 12 | T2EMUX x12 | 12 |
| `RunTrans_QubitSpec` | stopped_at_budget | 12 | QubitSpecSliceFF x12 | 12 |
| `RunChargeSweep` | completed | 10 | QubitSpecSliceFF x10 | 10 |
| `RunChargeTransmissionSweep` | completed | 10 | CavitySpecFF x10 | 2010 |
| `RunActiveResetVerify` | completed | 9 | SingleShotProgramFFMUX x3, ActiveResetVerify x6 | 12 |
| `RunInterleavedCoherence` | stopped_at_budget | 12 | UndrivenSingleShot x4, T1FF x4, T2R x4 | 12 |
| `SingleShot` | completed | 1 | SingleShotProgramFFMUX x1 | 2 |
| `RunUndrivenSingleShot` | stopped_at_budget | 12 | UndrivenSingleShot x12 | 12 |
| `RunT1SS` | stopped_at_budget | 12 | SingleShotProgramFFMUX x6, T1_SS x6 | 612 |
| `SingleShot_ReadoutOptimize` | completed | 1 | ReadOpt_wSingleShotFF x1 | 294 |
| `SingleShot_QubitOptimize` | completed | 1 | QubitPulseOpt_wSingleShotFF x1 | 882 |
| `RunAutoCoherence` | stopped_at_budget | 12 | AmplitudeRabiFF x1, SingleShotProgramFFMUX x11 | 23 |
| `RunZeroSpanParity` | completed | 3 | QubitSpecSliceFF x1, SingleShotProgramFFMUX x1, ZeroSpanParity x1 | 63 |
| `RunZeroSpanParity[validate]` | completed | 3 | QubitSpecSliceFF x1, SingleShotProgramFFMUX x1, ZeroSpanParity x1 | 257 |

**`RunChargeDispersionRamsey` raises before any capture, and that is a real
legacy bug, not a harness artefact.** `run_charge_dispersion_ramsey` reads
`ChargeDispersion_params["df"]`, but the runner's `ChargeDispersion_params` has
no `"df"` key (`upper_freq`, `lower_freq`, `probe_freq`, `relax_delay`,
`repetitions`). It would raise the same `KeyError` on hardware. The golden
records the raise so the refactor has to decide on it deliberately.

Other things the golden records as-is: `RunModifiedRamsey_Control` spends its
whole budget in the sweet-spot search (the synthetic spectra never satisfy the
acceptance criterion), and `RunAutoCoherence` spends its budget in the
readout-gain optimisation (`ss_gain_pts` 100), so later stages are not reached.

Checked before committing: two full captures in separate processes are
byte-identical; each label captured alone in a fresh process equals its entry
in the full-sequence golden (no state leaks between runs); changing one
`BaseConfig` value, or adding one `sync_all` to `T1Program.body` while leaving
the cfg untouched, both fail `RunT1` (the latter only through `hw.digest` /
`hw.first_program`).

## After the refactor

Write `driver_qicklab.py` exposing `capture_all(labels=None)` with the same
output shape, built on `capture.install_mocks(<new ExperimentClass>,
make_proxy_targets=[...], pyvisa_targets=[...])` and `capture.begin_run` /
`end_run`, then point `DRIVER` in `test_golden.py` at it. Run labels must stay
the legacy flag names so the golden still keys correctly. Differences that are
intentional must be justified one by one before the golden is regenerated.

## Existing offline scripts

Run with the venv Python from the repo root on 2026-10-13:

| Script | Result | Needs hardware? |
|---|---|---|
| `Experiments/test_ModifiedRamseyParity_offline.py` | 131 passed, 0 failed (exit 0, ~45 s) | No |
| `Experiments/verify_ModifiedRamsey_timing.py` | 42 passed, 0 failed (exit 0, ~4 s) | **Yes.** It connects over Pyro4 to `myqick` at `192.168.0.103:8888` and checks programs against the board's real `QickConfig`. Run without `--acquire`, it only reads the config and compiles; nothing plays. Off the lab network it fails at `locateNS`. |
