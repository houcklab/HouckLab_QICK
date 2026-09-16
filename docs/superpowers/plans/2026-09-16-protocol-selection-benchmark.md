# Protocol Selection Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build independent QICK/q3 and QUA/q5 temporary runners that acquire the same crash-safe 17-pass 3pt/5pt/7pt ON/OFF benchmark and save directly comparable raw data, diagnostics, and summary figures.

**Architecture:** Each repository gets one hardware-free `protocol_selection_benchmark.py` module containing the canonical plan, manifest/checkpoint code, schema normalization, metrics, and plots, plus one `ProtocolSelectionBenchmark.py` hardware adapter. The adapters reuse the existing true 3-point and variable-delay n-point experiment classes, perform one calibration per suite, and inject either the accepted neutral correction or a unity table with identical timing. The repositories share a fixed canonical JSON document and SHA-256 fingerprint but do not synchronize at runtime.

**Tech Stack:** Python 3, NumPy, Matplotlib, standard-library `csv`/`json`/`hashlib`/`dataclasses`, pytest, existing QICK active-reset stack, existing QUA/QOP experiment stack, existing `fluxpred.production` neutral-model renderer.

**Spec:** `docs/superpowers/specs/2026-09-16-protocol-selection-benchmark-design.md`

## Global Constraints

- The full benchmark is exactly 17 ordered passes and 801 descending frequencies from 4.3000 to 3.9000 GHz at 0.5 MHz spacing.
- The canonical full-plan SHA-256 is `9102ce376f93ef790f43fbafb7e7c9ae25ea8cdb56e7785424b53267e10746bb` using sorted compact JSON with `allow_nan=False`.
- QICK and QUA execute independently; do not import or instantiate any synchronizer and do not create sync files.
- Use active reset and readout at park for every pass.
- Perform one controller-native readout/reset calibration at suite startup and reuse it for all passes.
- Acquire 3pt data with the real 3-condition path and 5pt/7pt data with the real n-point path; never down-select one protocol from another protocol's acquisition.
- ON uses the accepted controller-neutral model and exact production stateful outbound/return lifecycle.
- OFF uses a unity-multiplier table with the same segment edges, 40 us recovery occupancy, and readout placement as ON.
- Save and checksum each pass before starting the next pass.
- Restore the flux line to park after every pass and after every exception.
- A failed pass exits nonzero after recording failure state; it is not silently skipped.
- Do not change the behavior or defaults of the existing three-, five-, seven-point, or seven-day runners.
- Do not refit a predistortion model in this benchmark.
- The temporary smoke mode must exercise 3pt, 5pt, and 7pt in both ON and OFF modes but must have a distinct fingerprint and artifact stem from the full benchmark.

## File Structure

### QICK repository

- Create `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/protocol_selection_benchmark.py` — canonical plan, fingerprints, checkpointing, normalization, metrics, and plotting; no hardware imports.
- Create `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/ProtocolSelectionBenchmark.py` — q3 hardware adapter and CLI entry point.
- Create `tests/test_protocol_selection_benchmark.py` — pure-plan, analysis, orchestration, and q3 adapter tests.

### QUA repository

- Create `LabCode/Control/Flux_Tunable/protocol_selection_benchmark.py` — same public pure interfaces and canonical serialization as QICK.
- Create `LabCode/Control/Flux_Tunable/ProtocolSelectionBenchmark.py` — q5 hardware adapter and CLI entry point.
- Create `tests/test_protocol_selection_benchmark.py` — pure-plan, analysis, orchestration, and q5 adapter tests.

The pure modules intentionally have matching public APIs. They remain local copies because the Windows measurement PCs pull different repositories and cannot depend on a third shared package.

---

### Task 1: Define and lock the canonical QICK benchmark plan

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/protocol_selection_benchmark.py`
- Create: `tests/test_protocol_selection_benchmark.py`

**Interfaces:**
- Produces: `BenchmarkPass`, `BenchmarkPlan`, `full_plan()`, `smoke_plan()`, `canonical_document(plan)`, `plan_fingerprint(plan)`, and `frequency_grid_ghz(plan)`.
- Consumes: only the Python standard library and NumPy; importing this module must not connect to QICK, Pyro, QOP, or the NAS.

- [ ] **Step 1: Write the failing canonical-plan tests**

```python
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    protocol_selection_benchmark as benchmark,
)


def test_full_plan_is_the_approved_17_pass_matrix():
    plan = benchmark.full_plan()
    assert len(plan.passes) == 17
    assert [item.pass_id for item in plan.passes] == [
        "p00_3pt_ts100_300_off",
        "p01_3pt_ts100_300_on",
        "p02_3pt_ts100_500_on",
        "p03_3pt_ts100_500_off",
        "p04_3pt_ts50_300_off",
        "p05_3pt_ts50_300_on",
        "p06_3pt_ts50_500_on",
        "p07_3pt_ts50_500_off",
        "p08_5pt_180_off",
        "p09_5pt_180_on",
        "p10_5pt_300_on",
        "p11_5pt_300_off",
        "p12_7pt_128_off",
        "p13_7pt_128_on",
        "p14_7pt_214_on",
        "p15_7pt_214_off",
        "p16_3pt_ts100_300_off_sentinel",
    ]
    assert plan.passes[0].role == "primary_and_anchor"
    assert plan.passes[-1].role == "drift_sentinel"


def test_equal_budget_pairs_are_encoded_exactly():
    plan = benchmark.full_plan()
    totals = [p.condition_count * p.shots_per_condition for p in plan.passes[:16]]
    assert totals == [900, 900, 1500, 1500, 900, 900, 1500, 1500,
                      900, 900, 1500, 1500, 896, 896, 1498, 1498]


def test_full_plan_grid_and_fingerprint_are_fixed():
    plan = benchmark.full_plan()
    grid = benchmark.frequency_grid_ghz(plan)
    assert grid.shape == (801,)
    assert grid[0] == 4.3
    assert grid[-1] == 3.9
    assert benchmark.plan_fingerprint(plan) == (
        "9102ce376f93ef790f43fbafb7e7c9ae25ea8cdb56e7785424b53267e10746bb"
    )


def test_plan_has_no_synchronization_fields():
    encoded = benchmark.canonical_json(benchmark.full_plan())
    assert "sync" not in encoded.lower()
    assert "handshake" not in encoded.lower()


def test_smoke_plan_exercises_every_protocol_and_mode_without_matching_full_hash():
    smoke = benchmark.smoke_plan()
    assert [(p.protocol, p.predistortion) for p in smoke.passes] == [
        ("3pt_ts100", "off"), ("3pt_ts100", "on"),
        ("5pt", "off"), ("5pt", "on"),
        ("7pt", "off"), ("7pt", "on"),
    ]
    assert smoke.frequency_count == 11
    assert all(p.shots_per_condition == 4 for p in smoke.passes)
    assert benchmark.plan_fingerprint(smoke) != benchmark.plan_fingerprint(
        benchmark.full_plan()
    )
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run:

```bash
cd /Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral
pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: collection fails because `protocol_selection_benchmark` does not exist.

- [ ] **Step 3: Implement immutable plan types and exact serialization**

Use these public shapes:

```python
@dataclass(frozen=True)
class BenchmarkPass:
    index: int
    protocol: str
    delays_us: tuple[float, ...]
    shots_per_condition: int
    condition_count: int
    predistortion: str
    role: str = "primary"

    @property
    def pass_id(self) -> str:
        base = (
            f"p{self.index:02d}_{self.protocol}_"
            f"{self.shots_per_condition}_{self.predistortion}"
        )
        return base + ("_sentinel" if self.role == "drift_sentinel" else "")


@dataclass(frozen=True)
class BenchmarkPlan:
    schema: str
    frequency_start_ghz: float
    frequency_stop_ghz: float
    frequency_step_mhz: float
    frequency_count: int
    reset_mode: str
    readout_location: str
    calibration_policy: str
    passes: tuple[BenchmarkPass, ...]
    mode: str = "full"
```

`canonical_document(full_plan())` must contain exactly these shared keys for the full-plan hash:

```python
{
    "schema": "houcklab.protocol-selection-benchmark.v1",
    "frequency_grid_ghz": {
        "start": 4.3,
        "stop": 3.9,
        "step_mhz": 0.5,
        "count": 801,
        "order": "descending",
    },
    "reset_mode": "active",
    "readout_location": "park",
    "calibration_policy": "once",
    "passes": [
        {
            "index": item.index,
            "protocol": item.protocol,
            "delays_us": list(item.delays_us),
            "shots_per_condition": item.shots_per_condition,
            "condition_count": item.condition_count,
            "predistortion": item.predistortion,
            "role": item.role,
        }
        for item in plan.passes
    ],
}
```

Serialize with:

```python
json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
```

Validate protocol/delay consistency, sequential indices, increasing positive delays, `predistortion in {"on", "off"}`, exact frequency-count arithmetic, and expected condition count `2 + len(delays_us)`.

- [ ] **Step 4: Run the canonical-plan tests**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit the QICK canonical plan**

```bash
git add WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/protocol_selection_benchmark.py tests/test_protocol_selection_benchmark.py
git commit -m "test: define q3 protocol benchmark matrix"
```

---

### Task 2: Add checkpoint, artifact, and analysis primitives to QICK

**Files:**
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/protocol_selection_benchmark.py`
- Modify: `tests/test_protocol_selection_benchmark.py`

**Interfaces:**
- Produces: `session_stem()`, `artifact_paths()`, `sha256_file()`, `atomic_write_json()`, `new_manifest()`, `load_resume_manifest()`, `record_pass_started()`, `record_pass_complete()`, `record_pass_failed()`, `pending_passes()`, `normalize_experiment_data()`, `summarize_pass()`, `write_pass_csv()`, `write_summary_csv()`, and `render_comparison_figure()`.
- Consumes: `BenchmarkPlan`, `BenchmarkPass`, experiment output dictionaries, target/realized frequency arrays, and controller/model provenance dictionaries.

- [ ] **Step 1: Write failing manifest and resume tests**

```python
def test_pass_is_complete_only_after_both_artifacts_and_checksums_exist(tmp_path):
    plan = benchmark.smoke_plan()
    manifest_path = tmp_path / "q3_smoke_manifest.json"
    manifest = benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc123",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    )
    benchmark.atomic_write_json(manifest_path, manifest)
    raw_path, metadata_path = benchmark.artifact_paths(
        tmp_path, "q3_smoke", plan.passes[0]
    )
    raw_path.write_text("frequency_ghz,gamma1_per_us\n4.05,0.01\n")
    metadata_path.write_text("{}")
    completed = benchmark.record_pass_complete(
        manifest_path, 0, raw_path=raw_path, metadata_path=metadata_path,
        ended_at="2026-09-16T12:00:00-04:00", duration_s=1.2,
    )
    assert completed["passes"][0]["status"] == "complete"
    assert completed["passes"][0]["artifacts"]["raw_csv"]["sha256"]
    assert benchmark.pending_passes(completed, plan) == plan.passes[1:]


def test_resume_refuses_plan_model_device_or_calibration_mismatch(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = benchmark.new_manifest(
        benchmark.smoke_plan(), device="q3", controller="qick",
        code_commit="abc123", model_provenance={"sha256": "1" * 64},
        calibration_id="cal-1",
    )
    benchmark.atomic_write_json(path, manifest)
    with pytest.raises(ValueError, match="model"):
        benchmark.load_resume_manifest(
            path, benchmark.smoke_plan(), device="q3", controller="qick",
            model_sha256="2" * 64, calibration_id="cal-1",
        )


def test_failed_pass_is_recorded_but_remains_pending(tmp_path):
    plan = benchmark.smoke_plan()
    path = tmp_path / "manifest.json"
    benchmark.atomic_write_json(path, benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    ))
    failed = benchmark.record_pass_failed(
        path, 0, error_type="RuntimeError", error_message="hardware stopped",
        traceback_text="trace", failed_at="2026-09-16T12:00:00-04:00",
    )
    assert failed["passes"][0]["status"] == "failed"
    assert benchmark.pending_passes(failed, plan)[0].index == 0
```

- [ ] **Step 2: Write failing normalization and scientific-metric tests**

```python
def test_normalization_preserves_raw_populations_and_directional_diagnostics():
    spec = benchmark.full_plan().passes[8]
    data = fake_five_point_data(points=801)
    rows = benchmark.normalize_experiment_data(
        spec,
        data,
        target_frequency_ghz=np.linspace(4.3, 3.9, 801),
        realized_frequency_ghz=np.linspace(4.3, 3.9, 801),
        flux_coordinate=np.arange(801),
    )
    assert len(rows) == 801
    assert {"P0", "P1", "Ps_40us", "Ps_80us", "Ps_200us"} <= rows[0].keys()
    assert {"gamma1_per_us", "gamma1_err_per_us", "valid",
            "fit_deviance", "scan_direction_delta"} <= rows[0].keys()


def test_summary_flags_nan_region_direction_shift_and_linewidth_shift():
    clean = synthetic_rows(valid_fraction=1.0, direction_offset=0.0)
    corrupt = synthetic_rows(valid_fraction=0.95, direction_offset=0.02)
    clean_metrics = benchmark.summarize_pass(clean)
    corrupt_metrics = benchmark.summarize_pass(corrupt)
    assert clean_metrics["valid_fraction"] == pytest.approx(1.0)
    assert corrupt_metrics["valid_fraction"] < 0.99
    assert corrupt_metrics["median_abs_direction_delta"] > clean_metrics[
        "median_abs_direction_delta"
    ]


def test_opening_and_closing_sentinels_report_drift_in_sigma_units():
    opening = synthetic_rows(gamma_offset=0.0, gamma_error=0.001)
    closing = synthetic_rows(gamma_offset=0.004, gamma_error=0.001)
    result = benchmark.compare_sentinels(opening, closing)
    assert result["median_abs_delta_per_us"] == pytest.approx(0.004)
    assert result["median_abs_delta_sigma"] > 2.0
```

Use deterministic helpers inside the test file; do not read NAS data in unit tests.

- [ ] **Step 3: Run the new tests and verify the functions are absent**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: failures identify the missing checkpoint and analysis functions.

- [ ] **Step 4: Implement atomic manifests and exact resume validation**

Implement atomic writes with a sibling temporary file, `flush()`, `os.fsync()`, and `os.replace()`. Store one manifest entry per canonical pass with `pending`, `running`, `complete`, or `failed` status. `record_pass_complete()` must verify both paths exist before hashing them. `load_resume_manifest()` must verify schema, plan fingerprint, device, controller, model hash, calibration ID, and checksums of all previously complete passes.

Expose deterministic file names:

```python
def artifact_paths(output_dir, stem, item):
    base = output_dir / f"{stem}_{item.pass_id}"
    return (
        base.with_name(base.name + "_raw.csv"),
        base.with_name(base.name + "_metadata.json"),
    )
```

- [ ] **Step 5: Implement normalization, pass metrics, CSV output, and figures**

Normalize existing experiment keys rather than refitting when the experiment class already produced a fit. Map 3pt keys (`inv_T1_3pt_per_us`, `T1_3pt_us`, `ref_contrast_3pt`) and n-point keys (`inv_T1_{N}pt_per_us`, `T1_{N}pt_us`, `ref_contrast_{N}pt`) into common columns. Preserve every raw P0/P1/Ps and scan-direction column.

The summary must calculate:

```python
{
    "valid_fraction": finite_valid_count / frequency_count,
    "longest_invalid_run": longest_contiguous_false(valid),
    "median_reference_contrast": nanmedian(abs(P1 - P0)),
    "median_gamma1_err_per_us": nanmedian(gamma1_err),
    "p90_gamma1_err_per_us": nanpercentile(gamma1_err, 90),
    "median_abs_direction_delta": nanmedian(abs(scan_direction_delta)),
    "median_fit_deviance": nanmedian(fit_deviance),
    "median_local_roughness": nanmedian(abs(diff(gamma1, n=2))),
    "duration_s": duration_s,
}
```

`render_comparison_figure()` must make a 4-by-4 map grid for passes 0–15, a sentinel-difference panel, a metrics table, and representative linecuts with uncertainty bands. Invalid values must be visibly masked and counted in each title.

- [ ] **Step 6: Run focused tests and static import check**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
python3 -c "from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import protocol_selection_benchmark as b; print(b.plan_fingerprint(b.full_plan()))"
```

Expected: tests pass and the printed hash is `9102ce376f93ef790f43fbafb7e7c9ae25ea8cdb56e7785424b53267e10746bb`.

- [ ] **Step 7: Commit QICK checkpointing and analysis**

```bash
git add WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/protocol_selection_benchmark.py tests/test_protocol_selection_benchmark.py
git commit -m "feat: add q3 benchmark checkpoints and analysis"
```

---

### Task 3: Implement the QICK q3 hardware adapter and orchestrator

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/ProtocolSelectionBenchmark.py`
- Modify: `tests/test_protocol_selection_benchmark.py`
- Reuse without changing defaults: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/FivePointApplesToApples.py:275-312`
- Reuse without changing defaults: `WorkingProjects/TLS_Spectroscopy/Client_modules/Experiments/mT1VsFlux.py:916-1234`
- Reuse without changing defaults: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/integration.py:214-547`

**Interfaces:**
- Produces: `QickBenchmarkBackend`, `unity_timing_table()`, `runtime_settings()`, `run_benchmark()`, and `main()`.
- Consumes: Task 1/2 pure module, `FivePointApplesToApples.install_scan_calibration`, `resolve_neutral_selection`, `render_neutral_scan_compensation`, `prepare_reset_session`, `T13PointVsFlux`, and `T15PointVsFlux`.

- [ ] **Step 1: Write failing QICK adapter tests with a fake backend**

```python
def test_qick_orchestrator_calibrates_once_dispatches_real_paths_and_restores_park(tmp_path):
    backend = FakeBackend()
    result = runner.run_benchmark(
        backend=backend,
        plan=benchmark.smoke_plan(),
        output_dir=tmp_path,
        stem="q3_smoke",
        resume_manifest=None,
    )
    assert backend.calibration_calls == 1
    assert [call.protocol_path for call in backend.calls] == [
        "three_point", "three_point", "n_point", "n_point", "n_point", "n_point"
    ]
    assert [call.predistortion for call in backend.calls] == [
        "off", "on", "off", "on", "off", "on"
    ]
    assert backend.restore_park_calls == 6
    assert result["status"] == "complete"


def test_qick_off_uses_same_edges_and_all_unity_multipliers():
    on = {"segment_edges_ns": [0.0, 4_000.0, 40_000.0],
          "multipliers": [1.03, 1.01, 1.0]}
    off = runner.unity_timing_table(on)
    assert off["segment_edges_ns"] == on["segment_edges_ns"]
    assert off["multipliers"] == [1.0, 1.0, 1.0]


def test_qick_failure_records_manifest_restores_park_and_reraises(tmp_path):
    backend = FakeBackend(fail_on_pass=2)
    with pytest.raises(RuntimeError, match="synthetic acquisition failure"):
        runner.run_benchmark(
            backend=backend, plan=benchmark.smoke_plan(), output_dir=tmp_path,
            stem="q3_smoke", resume_manifest=None,
        )
    assert backend.restore_park_calls == 3
    saved = json.loads((tmp_path / "q3_smoke_manifest.json").read_text())
    assert saved["passes"][2]["status"] == "failed"


def test_qick_runtime_settings_default_to_full_and_accept_explicit_resume():
    full = runner.runtime_settings({})
    assert full["mode"] == "full"
    assert full["resume_manifest"] is None
    smoke = runner.runtime_settings({
        "Q3_PROTOCOL_BENCHMARK_MODE": "smoke",
        "Q3_PROTOCOL_BENCHMARK_RESUME_MANIFEST": "Z:/resume.json",
    })
    assert smoke == {"mode": "smoke", "resume_manifest": Path("Z:/resume.json")}
```

- [ ] **Step 2: Run the tests and verify the runner is missing**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: import or attribute failures for the new runner.

- [ ] **Step 3: Implement the timing-equivalent ON/OFF waveform contract**

Resolve the accepted q3 neutral selection once and render it for the maximum 200 us hold plus 40 us recovery. Preserve every key in the ON source table. Build OFF with copied segment edges and all multipliers equal to `1.0`; add metadata keys `benchmark_predistortion_mode="timing_matched_unity"` and `source_model_sha256` without changing the coefficient arrays consumed by existing helpers.

For both modes, set:

```python
base.update({
    "apply_flux_tail_compensation": True,
    "flux_tail_compensation": selected_table,
    "flux_predistortion_recovery_us": 40.0,
    "flux_settle_time_us": 0.5,
    "opx_t1_3pt_gain_lookup": True,
})
```

This is intentional: OFF must still enter the stateful scheduling path.

- [ ] **Step 4: Implement one-calibration QICK backend setup**

In `QickBenchmarkBackend.__init__`:

1. import hardware modules lazily so pure imports remain offline-safe;
2. call `install_scan_calibration(tls)`;
3. call `tls._set_yoko_if_requested()` and `tls.makeProxy()`;
4. build the shared 801-point target and integer-DAC grids using `_target_frequency_grid_ghz` and `_integer_dc_grid`;
5. resolve the neutral model and render the ON/OFF tables;
6. call `prepare_reset_session(p["reset_mode"], outer_folder=tls.outerFolder, qubit=tls.QUBIT, base_cfg=tls.BaseConfig, soc=soc, soccfg=soccfg, purpose="ProtocolSelectionBenchmark")` exactly once;
7. apply `apply_verified_feedback_timing()` to the shared base config;
8. retain the calibration output path and SHA-256 of `calibration.json` as `calibration_id`.

When resuming, load the exact saved bundle with `active_reset_OPX.calibration.load_calibration()` and reconstruct `ProductionResetSession.active()` using the method frequency recorded in the manifest. Do not acquire a new calibration during resume. Add a fake-backend test proving an interrupted run plus resume still has exactly one calibration acquisition and that changing the calibration file checksum is rejected.

Do not carry over `GlobalSlotSynchronizer`, wall-clock duration, or automatic recalibration logic from the production runner.

- [ ] **Step 5: Implement real protocol dispatch**

`QickBenchmarkBackend.acquire_pass(item, progress)` must:

- create `T13PointVsFlux` for `item.protocol.startswith("3pt")`, with `Ts_ns=int(item.delays_us[0] * 1000)`, `shots=item.shots_per_condition`, active reset, the selected timing table, shared reset session, and `write_outputs=False`;
- create `T15PointVsFlux` for 5pt and 7pt with `decay_delays_us=item.delays_us`, `shots=item.shots_per_condition`, active reset, selected timing table, and `write_outputs=False`;
- call `exp.acquire(progress=True)` once;
- attach target/realized frequency, correction mode, plan fingerprint, neutral provenance, calibration ID, and code commit to `exp.data`;
- return normalized rows plus pass metadata through the pure module.

For 7pt, rely on `acquire_t1_5pt_iq` chunking already present at `active_reset_OPX/integration.py:325-415`; do not build one oversized tProcessor program.

- [ ] **Step 6: Implement orchestration, progress, checkpoint, cleanup, and CLI**

`run_benchmark()` must be hardware-agnostic enough for `FakeBackend`. Wrap each pass as:

```python
benchmark.record_pass_started(
    manifest_path,
    item.index,
    started_at=clock.now_iso(),
)
started = monotonic()
try:
    payload = backend.acquire_pass(item, progress=progress)
    benchmark.write_pass_csv(raw_path, payload.rows)
    atomic_write_json(metadata_path, payload.metadata)
    benchmark.record_pass_complete(
        manifest_path,
        item.index,
        raw_path=raw_path,
        metadata_path=metadata_path,
        ended_at=clock.now_iso(),
        duration_s=monotonic() - started,
    )
except BaseException as exc:
    benchmark.record_pass_failed(
        manifest_path,
        item.index,
        error_type=type(exc).__name__,
        error_message=str(exc),
        traceback_text=traceback.format_exc(),
        failed_at=clock.now_iso(),
    )
    raise
finally:
    backend.restore_park()
```

Always call `backend.close()` in an outer `finally`. Print pass progress as `[pass 03/17]`, and calculate benchmark ETA only from completed-pass monotonic durations. After pass 16, write summary CSV and comparison PNG, update manifest status to `complete`, and print absolute artifact paths.

Supported environment variables are exactly:

```text
Q3_PROTOCOL_BENCHMARK_MODE=full|smoke
Q3_PROTOCOL_BENCHMARK_RESUME_MANIFEST=<absolute manifest path>
Q3_FLUXPRED_MODE=neutral
Q3_FLUXPRED_MODEL_JSON=<accepted neutral JSON path>
Q3_CODE_COMMIT=<git commit>
```

- [ ] **Step 7: Run QICK focused and regression tests**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
pytest -q tests/test_five_point_protocol.py tests/test_protocol_crossover.py tests/test_seven_point_runner.py tests/test_predistortion_production.py
```

Expected: all tests pass without `pynq`, Pyro, or NAS access.

- [ ] **Step 8: Commit the QICK hardware runner**

```bash
git add WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/ProtocolSelectionBenchmark.py tests/test_protocol_selection_benchmark.py
git commit -m "feat: add q3 protocol selection benchmark"
```

---

### Task 4: Port the canonical pure module to QUA and enforce cross-repository parity

**Files:**
- Create: `LabCode/Control/Flux_Tunable/protocol_selection_benchmark.py`
- Create: `tests/test_protocol_selection_benchmark.py`

**Interfaces:**
- Produces: the same pure public API as Tasks 1 and 2.
- Consumes: no QOP client or hardware module at import time.

- [ ] **Step 1: Write the QUA parity tests before adding the module**

Copy the Task 1 and Task 2 pure tests with the QUA import:

```python
from LabCode.Control.Flux_Tunable import protocol_selection_benchmark as benchmark
```

Add an explicit frozen-document assertion:

```python
def test_q5_canonical_full_plan_matches_the_cross_repo_contract():
    plan = benchmark.full_plan()
    assert benchmark.plan_fingerprint(plan) == (
        "9102ce376f93ef790f43fbafb7e7c9ae25ea8cdb56e7785424b53267e10746bb"
    )
    assert benchmark.canonical_document(plan)["passes"][12] == {
        "index": 12,
        "protocol": "7pt",
        "delays_us": [40.0, 80.0, 120.0, 160.0, 200.0],
        "shots_per_condition": 128,
        "condition_count": 7,
        "predistortion": "off",
        "role": "primary",
    }
```

- [ ] **Step 2: Run the QUA test and verify the module is missing**

Run:

```bash
cd /Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral
pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: collection fails because the QUA module does not exist.

- [ ] **Step 3: Port the pure module without controller-specific changes**

Copy the plan, fingerprint, checkpointing, normalization, metrics, and plotting implementation from QICK. Only package import paths and the device name supplied by the hardware adapter may differ. Preserve canonical serialization byte-for-byte.

- [ ] **Step 4: Compare the two modules' canonical output directly**

Run from a shell with both repo roots available:

```bash
PYTHONPATH=/Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral:/Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral python3 - <<'PY'
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import protocol_selection_benchmark as qick
from LabCode.Control.Flux_Tunable import protocol_selection_benchmark as qua
assert qick.canonical_json(qick.full_plan()) == qua.canonical_json(qua.full_plan())
assert qick.plan_fingerprint(qick.full_plan()) == qua.plan_fingerprint(qua.full_plan())
print(qick.plan_fingerprint(qick.full_plan()))
PY
```

Expected: `9102ce376f93ef790f43fbafb7e7c9ae25ea8cdb56e7785424b53267e10746bb`.

- [ ] **Step 5: Run QUA pure tests**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: all pure tests pass.

- [ ] **Step 6: Commit the QUA pure module**

```bash
git add LabCode/Control/Flux_Tunable/protocol_selection_benchmark.py tests/test_protocol_selection_benchmark.py
git commit -m "test: define q5 protocol benchmark matrix"
```

---

### Task 5: Implement the QUA q5 hardware adapter and orchestrator

**Files:**
- Create: `LabCode/Control/Flux_Tunable/ProtocolSelectionBenchmark.py`
- Modify: `tests/test_protocol_selection_benchmark.py`
- Modify: `LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py:1972-2463`
- Modify: `tests/test_five_point_protocol.py`
- Reuse without changing defaults: `LabCode/Control/Flux_Tunable/FivePointApplesToApples.py:215-253`
- Reuse without changing defaults: `LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py:1176-1955`
- Reuse without changing defaults: `LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py:1972-2465`

**Interfaces:**
- Produces: `QuaBenchmarkBackend`, `unity_timing_table()`, `runtime_settings()`, `run_benchmark()`, and `main()`.
- Consumes: Task 4 pure module, `FivePointApplesToApples.install_scan_calibration`, `resolve_neutral_selection`, `render_neutral_scan_compensation`, `T13PointVsFlux`, `T15PointVsFlux`, `precompile_t13_point`, and `precompile_t15_point`.

- [ ] **Step 1: Write failing QUA adapter and orchestration tests**

Use the same fake-backend tests as Task 3 with QUA imports. Add compile-dispatch assertions:

```python
def test_q5_backend_precompiles_each_real_protocol_with_shared_calibration(monkeypatch):
    calls = []
    dependencies = FakeQuaDependencies(
        on_compile_3pt=lambda **kw: calls.append(("3pt", kw)),
        on_compile_npt=lambda **kw: calls.append(("npt", kw)),
    )
    backend = runner.QuaBenchmarkBackend.from_dependencies(
        dependencies, plan=benchmark.smoke_plan(), output_dir=Path("Z:/fake")
    )
    calibration = backend.calibrate()
    for item in benchmark.smoke_plan().passes:
        backend.acquire_pass(item, calibration=calibration, progress=lambda *_: None)
    assert dependencies.single_shot_calibration_calls == 1
    assert [kind for kind, _ in calls] == ["3pt", "3pt", "npt", "npt", "npt", "npt"]
    assert calls[0][1]["Ts_ns"] == 100_000
    assert calls[4][1]["decay_delays_us"] == (40.0, 80.0, 120.0, 160.0, 200.0)
```

Also assert that the fake quantum machine is closed on success and failure and that `restore_park()` is called once per attempted pass.

- [ ] **Step 2: Run the QUA tests and verify the runner is missing**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: import or attribute failures for `ProtocolSelectionBenchmark`.

- [ ] **Step 3: Implement ON/OFF source and applied tables**

Resolve q5 neutral selection once. Render the maximum-duration ON table through `render_neutral_scan_compensation(choice, params, _coerce_flux_tail_compensation)`. Build OFF from the source ON edges with all multipliers equal to `1.0`, then pass it through `_coerce_flux_tail_compensation` so both modes have identical QUA clock-quantized edges.

Unit-test both source and applied equality:

```python
assert off_source["segment_edges_ns"] == on_source["segment_edges_ns"]
assert off_applied["segment_edges_clk"] == on_applied["segment_edges_clk"]
assert set(off_applied["multipliers"]) == {1.0}
```

Pass `flux_predistortion_recovery_us=40.0` in both modes.

- [ ] **Step 4: Extend the real QUA 3-point path to the production stateful return lifecycle**

`T13PointVsFlux` currently accepts a compensation table but gives the return step only `flux_settle_time_ns`; that is not the 40 us stateful lifecycle used by `T15PointVsFlux`. Add `flux_predistortion_recovery_us=40.0` to `T13PointVsFlux.__init__` and `precompile_t13_point`. Include it in the precompile fingerprint and data telemetry.

Replace the two independent `_hold_flux_step()` calls in `T13PointVsFlux.make_prog()` with the same primitives used by `T15PointVsFlux`:

```python
outbound, recovery = _stateful_flux_round_trip_segments(
    self.flux_tail_compensation,
    target_hold_clk,
    recovery_clk=_ns_to_clk(1e3 * self.flux_predistortion_recovery_us),
)
recovery_prefix, recovery_tail = _split_flux_segments(
    recovery,
    prefix_clk=_ns_to_clk(self.flux_settle_time_ns),
)
```

Play `outbound`, then the return prefix, then start readout at park while the return tail continues on the flux element, exactly as the 5pt code does. Preserve the existing 3pt P0/P1 reference policy and estimator; this change affects only the Ps flux round trip.

Add regression tests that assert:

- ON and timing-matched OFF compile the same segment durations;
- OFF commands are unity-scaled;
- readout begins after the same 0.5 us return prefix in both modes;
- the remaining 39.5 us tail stays on the flux line;
- `precompile_t13_point` fingerprints differ when recovery duration or coefficients differ;
- `None` compensation retains the legacy hard-step behavior for existing callers.

- [ ] **Step 5: Implement one-calibration QUA backend setup**

In the backend startup:

1. import `TLSSpectroscopy` and the QUA experiment classes lazily;
2. call `install_scan_calibration(tls)`;
3. close any stale QMs using the existing guarded helper, then call `_set_yoko_if_requested()`;
4. create the q5 meta dictionary and standard output directory;
5. calculate the shared target and voltage grids using `_target_frequency_grid_ghz` and `_voltage_grid`;
6. call `run_step5_single_shot_cal()` exactly once;
7. freeze the returned calibration parameters and calibrated metadata for the suite;
8. create the config and set both LOs once;
9. resolve/render neutral ON and timing-matched OFF tables once.

Persist the calibration parameters and calibrated measurement metadata atomically as `<stem>_calibration.json`, checksum that file, and use its checksum as `calibration_id`. On resume, reload this exact file instead of running `run_step5_single_shot_cal()` again. Add a test proving a resumed fake session reuses the saved calibration and refuses a modified checksum.

Do not use `_run_series`, `GlobalSlotSynchronizer`, or the automatic recalibration closure from the production runner.

- [ ] **Step 6: Implement real QUA protocol dispatch**

For each pass:

- call `precompile_t13_point` and construct `T13PointVsFlux` for 3pt, passing the exact `Ts_ns`, shots, active reset, shared calibration, selected compensation, `write_outputs=False`, and the returned precompiled bundle;
- call `precompile_t15_point` and construct `T15PointVsFlux` for 5pt/7pt, passing the exact delay tuple, shots, active reset, shared calibration, selected compensation, `flux_predistortion_recovery_us=40.0`, `write_outputs=False`, and the returned precompiled bundle;
- attach target/realized frequency, correction mode, plan fingerprint, neutral provenance, calibration ID, and code commit to `experiment.data`;
- normalize and return the payload;
- close the pass-specific QM after data are fetched, without invalidating the frozen calibration used to build the next config.

If QUA construction performs acquisition in `__init__`, do not call a second acquisition method.

- [ ] **Step 7: Reuse the tested orchestrator contract and add the q5 CLI**

Port the QICK `run_benchmark()` control flow exactly, changing only package imports and environment prefixes. Supported variables are:

```text
Q5_PROTOCOL_BENCHMARK_MODE=full|smoke
Q5_PROTOCOL_BENCHMARK_RESUME_MANIFEST=<absolute manifest path>
Q5_FLUXPRED_MODE=neutral
Q5_FLUXPRED_MODEL_JSON=<accepted neutral JSON path>
Q5_CODE_COMMIT=<git commit>
```

The module command is:

```text
python -m LabCode.Control.Flux_Tunable.ProtocolSelectionBenchmark
```

- [ ] **Step 8: Run QUA focused and regression tests**

Run:

```bash
pytest -q tests/test_protocol_selection_benchmark.py
pytest -q tests/test_five_point_protocol.py tests/test_protocol_crossover.py tests/test_predistortion_production.py
```

Expected: all tests pass without connecting to QOP.

- [ ] **Step 9: Commit the QUA hardware runner**

```bash
git add LabCode/Control/Flux_Tunable/ProtocolSelectionBenchmark.py LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py tests/test_protocol_selection_benchmark.py tests/test_five_point_protocol.py
git commit -m "feat: add q5 protocol selection benchmark"
```

---

### Task 6: Add cross-repository schema and visualization regression fixtures

**Files:**
- Modify: QICK `tests/test_protocol_selection_benchmark.py`
- Modify: QUA `tests/test_protocol_selection_benchmark.py`
- Create: QICK `tests/fixtures/protocol_selection_pass_rows.json`
- Create: QUA `tests/fixtures/protocol_selection_pass_rows.json`

**Interfaces:**
- Consumes: identical synthetic pass rows in both repos.
- Produces: identical metric keys, compatible CSV headers, and deterministic figure layout expectations.

- [ ] **Step 1: Create one explicit synthetic fixture**

The JSON fixture contains 21 descending frequencies with:

- smooth baseline Gamma1;
- one Lorentzian-like peak;
- finite uncertainty;
- P0/P1 and all five 7pt survival populations;
- scan-up/scan-down values;
- three deliberately invalid values;
- one deliberate direction offset and one non-exponential deviance outlier.

Keep the fixture identical in both repositories and assert its SHA-256 in both tests.

- [ ] **Step 2: Write failing parity tests**

```python
def test_fixture_produces_stable_summary_schema_and_values(tmp_path):
    rows = json.loads(FIXTURE.read_text())
    summary = benchmark.summarize_pass(rows, duration_s=125.0)
    assert list(summary) == benchmark.SUMMARY_COLUMNS
    assert summary["valid_fraction"] == pytest.approx(18 / 21)
    assert summary["longest_invalid_run"] == 2
    assert summary["duration_s"] == 125.0


def test_comparison_figure_contains_sixteen_primary_panels_and_sentinel_panel(tmp_path):
    output = tmp_path / "comparison.png"
    figure_metadata = benchmark.render_comparison_figure(
        synthetic_complete_session(), output
    )
    assert output.exists() and output.stat().st_size > 10_000
    assert figure_metadata["primary_map_panels"] == 16
    assert figure_metadata["sentinel_panels"] >= 1
```

- [ ] **Step 3: Run each repository's focused tests and confirm any schema mismatch**

Run the QICK and QUA focused test commands from Tasks 3 and 5. Expected before fixes: any accidental column naming or metric differences fail visibly.

- [ ] **Step 4: Align both pure modules to one stable schema**

Use these required common columns, in this order before protocol-specific population columns:

```text
pass_index,pass_id,protocol,predistortion,shots_per_condition,
condition_count,target_frequency_ghz,realized_frequency_ghz,flux_coordinate,
gamma1_per_us,gamma1_err_per_us,t1_us,t1_err_us,valid,reference_contrast,
fit_success,fit_deviance,scan_direction_delta
```

After the common columns, write `P0`, `P1`, each ordered `Ps_*`, and their scan-up/scan-down variants. Missing protocol-inapplicable values are blank/NaN, never fabricated.

- [ ] **Step 5: Run parity and rendering tests**

Run:

```bash
cd /Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral && pytest -q tests/test_protocol_selection_benchmark.py
cd /Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral && pytest -q tests/test_protocol_selection_benchmark.py
```

Expected: both pass and report the same fixture checksum, summary schema, and panel counts.

- [ ] **Step 6: Commit fixture coverage in each repository**

QICK:

```bash
git add tests/test_protocol_selection_benchmark.py tests/fixtures/protocol_selection_pass_rows.json
git commit -m "test: lock q3 benchmark artifact schema"
```

QUA:

```bash
git add tests/test_protocol_selection_benchmark.py tests/fixtures/protocol_selection_pass_rows.json
git commit -m "test: lock q5 benchmark artifact schema"
```

---

### Task 7: Verify both repositories before measurement-PC deployment

**Files:**
- Verify only; modify code only if a failing test exposes a benchmark defect.

**Interfaces:**
- Consumes: all implementation tasks.
- Produces: evidence that the temporary runners are import-safe, canonical-plan compatible, and regression-safe.

- [ ] **Step 1: Run complete QICK benchmark-related suites**

```bash
cd /Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral
pytest -q \
  tests/test_protocol_selection_benchmark.py \
  tests/test_five_point_protocol.py \
  tests/test_protocol_crossover.py \
  tests/test_seven_point_runner.py \
  tests/test_predistortion_production.py \
  tests/test_flux_ramsey_cryoscope_runner.py
```

Expected: all pass.

- [ ] **Step 2: Run complete QUA benchmark-related suites**

```bash
cd /Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral
pytest -q \
  tests/test_protocol_selection_benchmark.py \
  tests/test_five_point_protocol.py \
  tests/test_protocol_crossover.py \
  tests/test_predistortion_production.py \
  tests/test_flux_ramsey_cryoscope_runner.py
```

Expected: all pass.

- [ ] **Step 3: Run cross-repository canonical parity check**

```bash
PYTHONPATH=/Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral:/Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral python3 - <<'PY'
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import protocol_selection_benchmark as qick
from LabCode.Control.Flux_Tunable import protocol_selection_benchmark as qua
qick_json = qick.canonical_json(qick.full_plan())
qua_json = qua.canonical_json(qua.full_plan())
assert qick_json == qua_json
assert qick.plan_fingerprint(qick.full_plan()) == "9102ce376f93ef790f43fbafb7e7c9ae25ea8cdb56e7785424b53267e10746bb"
assert qick.plan_fingerprint(qick.full_plan()) == qua.plan_fingerprint(qua.full_plan())
print("canonical protocol benchmark parity PASS")
PY
```

- [ ] **Step 4: Verify clean worktrees and review both diffs**

```bash
cd /Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral && git status --short && git log -6 --oneline
cd /Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral && git status --short && git log -6 --oneline
```

Expected: no uncommitted changes and a short sequence of benchmark commits in each repository.

- [ ] **Step 5: Push each development result to its measurement-PC production branch**

After review, push the QICK HEAD to `tls-spectroscopy` and the QUA HEAD to `marty-branch` using explicit source:destination refs. Do not force push:

```bash
cd /Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral
git push origin HEAD:tls-spectroscopy

cd /Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral
git push origin HEAD:marty-branch
```

Record both resulting short commit hashes for the measurement commands.

---

### Task 8: Run measurement-PC smoke gates before the full benchmark

**Files:**
- No source changes unless a hardware-only defect is reproduced and fixed with a regression test.

**Interfaces:**
- Consumes: pushed Task 7 commits and accepted neutral model JSON files.
- Produces: six-pass q3 and q5 smoke manifests proving every protocol/mode dispatch works on hardware.

- [ ] **Step 1: Run the q3/QICK smoke suite**

On the QICK measurement PC:

```bash
cd ~/Documents/GitHub/HouckLab_QICK && \
git pull --ff-only origin tls-spectroscopy && \
git rev-parse --short HEAD && \
env \
Q3_PROTOCOL_BENCHMARK_MODE=smoke \
Q3_FLUXPRED_MODE=neutral \
Q3_FLUXPRED_MODEL_JSON="Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3/q3_2026_09_15/q3_22_45_58_Flux_Ramsey_Cryoscope_joint_neutral_candidate.json" \
Q3_CODE_COMMIT="$(git rev-parse --short HEAD)" \
c:/Users/escher/Documents/GitHub/HouckLab_QICK/.venv/Scripts/python.exe \
-m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ProtocolSelectionBenchmark
```

Expected: one calibration, six completed passes, progress for each pass, a completed manifest, and flux restored to park after each pass.

- [ ] **Step 2: Run the q5/QUA smoke suite**

On the QUA measurement PC:

```bash
cd ~/Documents/GitHub/Houck-Lab-Qua && \
git pull --ff-only origin marty-branch && \
git rev-parse --short HEAD && \
env \
Q5_PROTOCOL_BENCHMARK_MODE=smoke \
Q5_FLUXPRED_MODE=neutral \
Q5_FLUXPRED_MODEL_JSON="Z:/FluxTeam/Data/FTT02_SiOxJJ_2026_08_28/OPX/q5/q5_2026_09_15/q5_21_12_16_Flux_Ramsey_Cryoscope_joint_neutral_candidate.json" \
Q5_CODE_COMMIT="$(git rev-parse --short HEAD)" \
c:/Users/ece-houck-j409/Documents/GitHub/Houck-Lab-Qua/qua-env/Scripts/python.exe \
-m LabCode.Control.Flux_Tunable.ProtocolSelectionBenchmark
```

Expected: the same six logical passes and a completed q5 smoke manifest.

- [ ] **Step 3: Inspect smoke manifests from the mounted NAS**

On the development machine, find the newest smoke manifests:

```bash
find /Volumes/ourphoton/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3 -name '*Protocol_Selection_Benchmark_SMOKE_manifest.json' -print | sort | tail -1
find /Volumes/ourphoton/FluxTeam/Data/FTT02_SiOxJJ_2026_08_28/OPX/q5 -name '*Protocol_Selection_Benchmark_SMOKE_manifest.json' -print | sort | tail -1
```

Verify both say `status: complete`, contain six checksummed passes, record one calibration ID, and show the accepted neutral-model SHA-256. Do not start the full suite if either smoke run has invalid dimensions, incomplete artifacts, or a cleanup failure.

---

### Task 9: Run the independent full suites and analyze the result

**Files:**
- No source changes for acquisition.
- Generated NAS artifacts only.

**Interfaces:**
- Consumes: successful Task 8 smoke gates.
- Produces: 17 maps per qubit, summary CSVs, comparison PNGs, and an evidence-based production recommendation.

- [ ] **Step 1: Start q3/QICK full benchmark independently**

```bash
cd ~/Documents/GitHub/HouckLab_QICK && \
env \
Q3_PROTOCOL_BENCHMARK_MODE=full \
Q3_FLUXPRED_MODE=neutral \
Q3_FLUXPRED_MODEL_JSON="Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3/q3_2026_09_15/q3_22_45_58_Flux_Ramsey_Cryoscope_joint_neutral_candidate.json" \
Q3_CODE_COMMIT="$(git rev-parse --short HEAD)" \
c:/Users/escher/Documents/GitHub/HouckLab_QICK/.venv/Scripts/python.exe \
-m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ProtocolSelectionBenchmark
```

- [ ] **Step 2: Start q5/QUA full benchmark independently**

```bash
cd ~/Documents/GitHub/Houck-Lab-Qua && \
env \
Q5_PROTOCOL_BENCHMARK_MODE=full \
Q5_FLUXPRED_MODE=neutral \
Q5_FLUXPRED_MODEL_JSON="Z:/FluxTeam/Data/FTT02_SiOxJJ_2026_08_28/OPX/q5/q5_2026_09_15/q5_21_12_16_Flux_Ramsey_Cryoscope_joint_neutral_candidate.json" \
Q5_CODE_COMMIT="$(git rev-parse --short HEAD)" \
c:/Users/ece-houck-j409/Documents/GitHub/Houck-Lab-Qua/qua-env/Scripts/python.exe \
-m LabCode.Control.Flux_Tunable.ProtocolSelectionBenchmark
```

No start order matters and neither process waits for the other.

- [ ] **Step 3: Resume only from an exact manifest after an interruption**

Use the absolute manifest emitted by the interrupted controller:

```bash
Q3_BENCHMARK_MANIFEST="$(find Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3 -name '*TLS_Protocol_Selection_Benchmark_manifest.json' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)" && \
test -n "$Q3_BENCHMARK_MANIFEST" && \
env Q3_PROTOCOL_BENCHMARK_MODE=full \
Q3_PROTOCOL_BENCHMARK_RESUME_MANIFEST="$Q3_BENCHMARK_MANIFEST" \
Q3_FLUXPRED_MODE=neutral \
Q3_FLUXPRED_MODEL_JSON="Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3/q3_2026_09_15/q3_22_45_58_Flux_Ramsey_Cryoscope_joint_neutral_candidate.json" \
c:/Users/escher/Documents/GitHub/HouckLab_QICK/.venv/Scripts/python.exe \
-m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ProtocolSelectionBenchmark
```

For QUA, resolve `Q5_BENCHMARK_MANIFEST` under `Z:/FluxTeam/Data/FTT02_SiOxJJ_2026_08_28/OPX/q5`, set `Q5_PROTOCOL_BENCHMARK_RESUME_MANIFEST="$Q5_BENCHMARK_MANIFEST"`, and run `LabCode.Control.Flux_Tunable.ProtocolSelectionBenchmark`. The runner must refuse a mismatched model, plan, device, controller, or calibration rather than combining sessions.

- [ ] **Step 4: Inspect the summary tables before looking only at colormaps**

For each qubit, verify:

1. all 17 passes have checksummed raw and metadata artifacts;
2. primary validity is at least 99% or the failing frequency intervals are explicitly listed;
3. opening/closing sentinel drift is small relative to reported uncertainty;
4. ON/OFF comparison at equal protocol and budget does not show systematic centroid displacement;
5. linewidth changes are interpreted alongside reference contrast and directional disagreement;
6. vertical streaks correlate, or do not correlate, with scan-direction disagreement and reference contrast;
7. the high-shot budget improves uncertainty by a plausible amount rather than merely changing the mean map;
8. 5pt/7pt residual deviance supports or rejects the single-exponential model where 3pt cannot diagnose it;
9. measured runtime supports the required long-scan cadence.

- [ ] **Step 5: Make the production choice explicitly**

Recommend one protocol, shot budget, and predistortion mode separately for q3 and q5 if the evidence differs. Do not automatically choose the same mode for both controllers. Only after the user approves that recommendation should a separate bounded change update the long-scan runner defaults.
