from dataclasses import replace
import csv
import importlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest


@pytest.fixture
def qick_runner():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ProtocolSelectionBenchmark"
    )


class FakeBenchmarkBackend:
    device = "q3"
    controller = "qick"
    code_commit = "test-commit"
    model_provenance = {"sha256": "accepted-model", "coordinate": {"park": -25146}}

    def __init__(self, tmp_path, fail_on_pass=None):
        self.calibration_path = tmp_path / "calibration.json"
        self.calibration_calls = 0
        self.load_calls = 0
        self.restore_park_calls = 0
        self.close_calls = 0
        self.calls = []
        self.fail_on_pass = fail_on_pass

    def calibrate(self):
        self.calibration_calls += 1
        benchmark.atomic_write_json(self.calibration_path, {"calibration": "fixed"})
        self.calibration_id = benchmark.sha256_file(self.calibration_path)
        self.calibration_provenance = {
            "path": str(self.calibration_path.resolve()), "sha256": self.calibration_id,
            "method_frequency_mhz": 4200.0,
        }

    def load_calibration(self, manifest):
        self.load_calls += 1
        self.calibration_provenance = manifest["calibration"]
        self.calibration_id = benchmark.sha256_file(self.calibration_provenance["path"])

    def acquire_pass(self, item, progress):
        from types import SimpleNamespace
        self.calls.append(item)
        if item.index == self.fail_on_pass:
            raise RuntimeError("synthetic acquisition failure")
        rows = synthetic_rows()
        for row in rows:
            row.update(pass_index=item.index, pass_id=item.pass_id, protocol=item.protocol,
                       predistortion=item.predistortion, shots_per_condition=item.shots_per_condition,
                       condition_count=item.condition_count)
        return SimpleNamespace(rows=rows, metadata={"protocol": item.protocol})

    def restore_park(self):
        self.restore_park_calls += 1

    def close(self):
        self.close_calls += 1


def test_qick_orchestrator_calibrates_once_and_checkpoints_all_passes(tmp_path, qick_runner):
    backend = FakeBenchmarkBackend(tmp_path)
    result = qick_runner.run_benchmark(backend=backend, plan=benchmark.smoke_plan(),
                                      output_dir=tmp_path, stem="q3_smoke")
    assert backend.calibration_calls == 1
    assert [(item.protocol, item.predistortion) for item in backend.calls] == [
        ("3pt_ts100", "off"), ("3pt_ts100", "on"), ("5pt", "off"),
        ("5pt", "on"), ("7pt", "off"), ("7pt", "on"),
    ]
    assert backend.restore_park_calls == 6
    assert backend.close_calls == 1
    assert result["status"] == "complete"
    assert all(entry["duration_s"] >= 0 for entry in result["passes"])
    assert (tmp_path / "q3_smoke_summary.csv").is_file()
    assert (tmp_path / "q3_smoke_comparison.png").is_file()
    rows = list(csv.DictReader((tmp_path / "q3_smoke_p00_3pt_ts100_4_off_raw.csv").open()))
    assert rows[0]["pass_started_at"] and rows[0]["pass_ended_at"]


def test_qick_failure_records_and_resume_reuses_single_calibration(tmp_path, qick_runner):
    backend = FakeBenchmarkBackend(tmp_path, fail_on_pass=2)
    with pytest.raises(RuntimeError, match="synthetic acquisition failure"):
        qick_runner.run_benchmark(backend=backend, plan=benchmark.smoke_plan(),
                                 output_dir=tmp_path, stem="q3_smoke")
    assert backend.restore_park_calls == 3
    assert backend.close_calls == 1
    manifest_path = tmp_path / "q3_smoke_manifest.json"
    saved = json.loads(manifest_path.read_text())
    assert saved["passes"][2]["status"] == "failed"
    assert "RuntimeError" in saved["passes"][2]["error"]["traceback"]
    resumed = FakeBenchmarkBackend(tmp_path)
    result = qick_runner.run_benchmark(backend=resumed, plan=benchmark.smoke_plan(),
                                      output_dir=tmp_path, stem="ignored", resume_manifest=manifest_path)
    assert backend.calibration_calls + resumed.calibration_calls == 1
    assert resumed.load_calls == 1
    assert [item.index for item in resumed.calls] == [2, 3, 4, 5]
    assert result["status"] == "complete"


def test_qick_resume_refuses_modified_calibration_before_acquisition(tmp_path, qick_runner):
    backend = FakeBenchmarkBackend(tmp_path, fail_on_pass=0)
    with pytest.raises(RuntimeError):
        qick_runner.run_benchmark(backend=backend, plan=benchmark.smoke_plan(), output_dir=tmp_path, stem="run")
    backend.calibration_path.write_text("modified")
    resumed = FakeBenchmarkBackend(tmp_path)
    with pytest.raises(ValueError, match="calibration.*(checksum|mismatch)"):
        qick_runner.run_benchmark(backend=resumed, plan=benchmark.smoke_plan(), output_dir=tmp_path,
                                 stem="run", resume_manifest=tmp_path / "run_manifest.json")
    assert resumed.calibration_calls == 0
    assert resumed.calls == []
    assert resumed.close_calls == 1


def test_qick_off_retains_timing_source_metadata_and_does_not_mutate_on(qick_runner):
    on = {"segment_edges_ns": [0.0, 4000.0, 40000.0], "multipliers": [1.03, 1.01, 1.0],
          "lifecycle_conditions": [{"hold_ns": 2500.0,
              "edges_ns": [0.0, 500.0, 2500.0, 3000.0, 42500.0],
              "values": [1.2, 1.1, -0.3, -0.1], "terminal_tail_bound": 0.02}],
          "model_sha256": "accepted", "nested": {"arbitrary": [1]}}
    off = qick_runner.unity_timing_table(on)
    assert off["segment_edges_ns"] == on["segment_edges_ns"]
    assert off["multipliers"] == [1.0, 1.0, 1.0]
    assert off["lifecycle_conditions"][0]["values"] == [1.0, 1.0, 0.0, 0.0]
    assert off["lifecycle_conditions"][0]["terminal_tail_bound"] == 0.0
    assert off["source_model_sha256"] == "accepted"
    assert off["benchmark_predistortion_mode"] == "timing_matched_unity"
    off["nested"]["arbitrary"].append(2)
    assert on["nested"] == {"arbitrary": [1]}
    assert on["multipliers"] == [1.03, 1.01, 1.0]
    assert on["lifecycle_conditions"][0]["values"] == [1.2, 1.1, -0.3, -0.1]


def test_qick_runtime_settings_and_offline_import(qick_runner):
    import ast
    import subprocess
    assert qick_runner.runtime_settings({}) == {
        "mode": "full", "resume_manifest": None,
        "overlap_payload_readout": True,
    }
    assert qick_runner.runtime_settings({"Q3_PROTOCOL_BENCHMARK_MODE": "smoke",
        "Q3_PROTOCOL_BENCHMARK_RESUME_MANIFEST": "Z:/resume.json"}) == {
            "mode": "smoke", "resume_manifest": Path("Z:/resume.json"),
            "overlap_payload_readout": True}
    assert qick_runner.runtime_settings({
        "Q3_PROTOCOL_BENCHMARK_MODE": "five_point_ab",
        "Q3_PROTOCOL_BENCHMARK_WAIT_FOR_RETURN": "1",
    }) == {
        "mode": "five_point_ab", "resume_manifest": None,
        "overlap_payload_readout": False,
    }
    with pytest.raises(ValueError, match="MODE"):
        qick_runner.runtime_settings({"Q3_PROTOCOL_BENCHMARK_MODE": "bad"})
    source = Path(qick_runner.__file__).read_text()
    tree = ast.parse(source)
    top_imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not any("qick" in ast.unparse(node).lower() or "TLSSpectroscopy" in ast.unparse(node)
                   for node in top_imports)
    code = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if any(part in name.lower() for part in ("pyro", "pynq", "qick", "tlsspectroscopy", "fivepointapplestoapples")):
        raise AssertionError("hardware import: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import ProtocolSelectionBenchmark as runner
backend = runner.QickBenchmarkBackend(plan=runner.benchmark.smoke_plan(), environ={})
assert backend.soc is None
'''
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


@pytest.fixture
def fake_qick_hardware(tmp_path, monkeypatch, qick_runner):
    from types import SimpleNamespace
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import calibration, production
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import json_safe
    classifier = dict(schema_version=1, context="payload", theta_rad=0.0, shift=1,
                      c_int=1, s_int=0, ground_threshold=0, excited_threshold=1,
                      max_abs_raw=100, holdout={})
    bundle = calibration.CalibrationBundle.from_dict({
        "schema_version": 1, "payload": classifier, "loop": {**classifier, "context": "loop"},
        "reference_axis": dict(ground_i=0., ground_q=0., delta_i=1., delta_q=0., denominator=1.),
        "metadata": {"qubit": "q3", "purpose": "ProtocolSelectionBenchmark", "method_frequency_mhz": 4200.},
    })
    calibration.save_calibration(tmp_path / "calibration.json", bundle)
    state = SimpleNamespace(events=[], experiments=[], bundle=bundle, calibration_path=tmp_path / "calibration.json")
    state.tls = SimpleNamespace(BaseConfig={"ff_park_gain": -25146, "ff_ch": 4}, QUBIT="q3",
                               outerFolder=str(tmp_path), FLUX_FIT_PARAMS=[1, 2, 3],
                               _baseline_dc_offset=lambda: -25146,
                               _set_yoko_if_requested=lambda: state.events.append("yoko"),
                               makeProxy=lambda: (SimpleNamespace(_pyroRelease=lambda: state.events.append("release")), object()))
    def prepare(mode, **kwargs):
        assert mode == "active"
        assert kwargs["purpose"] == "ProtocolSelectionBenchmark"
        state.events.append("calibrate")
        return production.ProductionResetSession.active(bundle.to_dict(), 4200., tmp_path)
    def selection(tls, environ):
        state.events.append("select")
        return {"mode": "neutral", "model_sha256": "accepted", "document": {"acceptance": {
            "software": True, "scientific": True, "hardware": True}}}
    def render(choice, params):
        assert max(params["decay_delays_us"]) == 200.
        assert params["flux_settle_us"] == .5
        assert params["flux_predistortion_return_prefix_us"] == 24.
        assert params["flux_predistortion_recovery_us"] == 40.
        assert params["flux_predistortion_recovery_scale"] == .25
        return {"multipliers": [1.03, 1.01, 1.], "segment_edges_ns": [0., 4000., 240500.],
                "model_sha256": "accepted"}
    class Experiment:
        protocol_path = "n_point"
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.data = {}
            state.experiments.append(self)
        def acquire(self, progress):
            assert progress is True
            count = len(self.kwargs["dc_vec"])
            conditions = 3 if self.protocol_path == "three_point" else 2 + len(self.kwargs["decay_delays_us"])
            self.data.update({"P0": np.zeros(count), "P1": np.ones(count),
                              f"inv_T1_{conditions}pt_per_us": np.full(count, .01)})
    class ThreePoint(Experiment):
        protocol_path = "three_point"
    def load(path):
        state.events.append("load")
        return calibration.load_calibration(path)
    state.dependencies = SimpleNamespace(
        tls=state.tls,
        five=SimpleNamespace(install_scan_calibration=lambda tls: state.events.append("install"),
            resolve_neutral_selection=selection, render_neutral_scan_compensation=render,
            apply_verified_feedback_timing=lambda cfg: cfg.update(opx_feedback_read_timing="official_wait_all")),
        grid=SimpleNamespace(_target_frequency_grid_ghz=lambda p: np.linspace(p["freq_max_ghz"], p["freq_min_ghz"], 11),
            _integer_dc_grid=lambda p, target, tls_module: (np.arange(len(target)) - 20000, target - .00001)),
        prepare_reset_session=prepare, ProductionResetSession=production.ProductionResetSession,
        load_calibration=load, T13PointVsFlux=ThreePoint, T15PointVsFlux=Experiment,
        provenance=lambda choice, **kwargs: {"model_sha256": choice["model_sha256"], "coordinate": {"park": -25146}},
        json_safe=json_safe,
    )
    monkeypatch.setattr(qick_runner, "_load_hardware", lambda: state.dependencies, raising=False)
    return state


def test_qick_backend_dispatches_true_protocols_and_same_timing(tmp_path, qick_runner, fake_qick_hardware):
    backend = qick_runner.QickBenchmarkBackend(plan=benchmark.smoke_plan(), environ={
        "Q3_CODE_COMMIT": "abc",
        "Q3_PROTOCOL_BENCHMARK_WAIT_FOR_RETURN": "1",
    })
    assert fake_qick_hardware.events == []
    backend.calibrate()
    assert fake_qick_hardware.events.count("calibrate") == 1
    results = [backend.acquire_pass(item, progress=True) for item in benchmark.smoke_plan().passes]
    experiments = fake_qick_hardware.experiments
    assert [exp.protocol_path for exp in experiments] == ["three_point"] * 2 + ["n_point"] * 4
    assert experiments[0].kwargs["Ts_ns"] == 100000
    assert experiments[4].kwargs["decay_delays_us"] == (40., 80., 120., 160., 200.)
    for exp in experiments:
        assert exp.kwargs["shots"] == 4
        assert exp.kwargs["write_outputs"] is False
        cfg = exp.kwargs["cfg"]
        assert cfg["reset_mode"] == "opx_unbounded"
        assert cfg["opx_reset_calibration"] == fake_qick_hardware.bundle.to_dict()
        assert cfg["apply_flux_tail_compensation"] is True
        assert cfg["flux_predistortion_round_trip_mode"] == "stateful"
        assert cfg["flux_predistortion_recovery_us"] == 40.
        assert cfg["flux_predistortion_return_prefix_us"] == 24.
        assert cfg["flux_predistortion_overlap_payload_readout"] is False
        assert cfg["flux_settle_time_us"] == .5
        assert cfg["opx_t1_3pt_gain_lookup"] is True
        assert cfg["opx_feedback_read_timing"] == "official_wait_all"
        assert exp.data["code_commit"] == "abc"
        assert exp.data["calibration_id"] == benchmark.sha256_file(fake_qick_hardware.calibration_path)
    off, on = [exp.kwargs["flux_tail_compensation"] for exp in experiments[:2]]
    assert off["segment_edges_ns"] == on["segment_edges_ns"]
    assert off["multipliers"] == [1., 1., 1.]
    assert on["multipliers"] == [1.03, 1.01, 1.]
    assert results[4].rows[0]["gamma1_per_us"] == .01
    assert results[4].metadata["protocol_path"] == "n_point"
    json.dumps(results[4].metadata, allow_nan=False)
    with pytest.raises(RuntimeError, match="already"):
        backend.calibrate()


def test_qick_backend_resume_loads_exact_saved_bundle(tmp_path, qick_runner, fake_qick_hardware):
    first = qick_runner.QickBenchmarkBackend(plan=benchmark.smoke_plan(), environ={"Q3_CODE_COMMIT": "abc"})
    first.calibrate()
    manifest = benchmark.new_manifest(benchmark.smoke_plan(), device="q3", controller="qick", code_commit="abc",
        model_provenance=first.model_provenance, calibration_id=first.calibration_id)
    manifest["calibration"] = first.calibration_provenance
    resumed = qick_runner.QickBenchmarkBackend(plan=benchmark.smoke_plan(), environ={"Q3_CODE_COMMIT": "abc"})
    resumed.load_calibration(manifest)
    assert fake_qick_hardware.events.count("calibrate") == 1
    assert fake_qick_hardware.events.count("load") == 1
    assert resumed.base["opx_reset_calibration"] == first.base["opx_reset_calibration"]
    assert resumed.base["reset_pi_freq"] == 4200.
    manifest["calibration"]["method_frequency_mhz"] = 4100.
    invalid = qick_runner.QickBenchmarkBackend(plan=benchmark.smoke_plan(), environ={"Q3_CODE_COMMIT": "abc"})
    with pytest.raises(ValueError, match="calibration.*provenance"):
        invalid.load_calibration(manifest)


def test_qick_cli_selects_smoke_and_propagates_failures(monkeypatch, qick_runner):
    calls = []
    monkeypatch.setenv("Q3_PROTOCOL_BENCHMARK_MODE", "smoke")
    monkeypatch.delenv("Q3_PROTOCOL_BENCHMARK_RESUME_MANIFEST", raising=False)
    def run(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("acquisition failed")
    monkeypatch.setattr(qick_runner, "run_benchmark", run)
    with pytest.raises(RuntimeError, match="acquisition failed"):
        qick_runner.main()
    assert calls[0]["plan"].mode == "smoke"
    assert calls[0]["resume_manifest"] is None


def test_qick_cleanup_stops_running_readout_before_restoring_nonzero_park(monkeypatch, qick_runner):
    from types import SimpleNamespace
    events = []
    backend = qick_runner.QickBenchmarkBackend(plan=benchmark.smoke_plan(), environ={})
    backend.soc = SimpleNamespace(
        streamer=SimpleNamespace(readout_running=lambda: True, stop_readout=lambda: events.append("stop")),
        _pyroRelease=lambda: events.append("release"),
    )
    backend.soccfg = object()
    backend.base = {"ff_park_gain": -25146}
    def park(soc, soccfg, cfg):
        assert cfg["ff_park_gain"] == -25146
        events.append("park")
    monkeypatch.setattr(qick_runner, "_restore_park", park)
    backend.restore_park()
    assert events == ["stop", "park"]
    backend.close()
    assert events[-1] == "release"
    assert backend.soc is None


def test_qick_cleanup_failure_preserves_acquisition_failure(tmp_path, qick_runner):
    backend = FakeBenchmarkBackend(tmp_path, fail_on_pass=0)
    def restore():
        raise ValueError("restore failed")
    backend.restore_park = restore
    with pytest.raises(RuntimeError, match="synthetic acquisition failure"):
        qick_runner.run_benchmark(backend=backend, plan=benchmark.smoke_plan(), output_dir=tmp_path, stem="run")
    saved = json.loads((tmp_path / "run_manifest.json").read_text())
    assert saved["passes"][0]["error"]["type"] == "RuntimeError"
    assert "restore failed" in saved["passes"][0]["error"]["traceback"]
    assert backend.close_calls == 1


def test_qick_checkpoint_start_failure_still_restores_park(tmp_path, monkeypatch, qick_runner):
    backend = FakeBenchmarkBackend(tmp_path)
    def fail(*args, **kwargs):
        raise OSError("checkpoint unavailable")
    monkeypatch.setattr(benchmark, "record_pass_started", fail)
    with pytest.raises(OSError, match="checkpoint unavailable"):
        qick_runner.run_benchmark(backend=backend, plan=benchmark.smoke_plan(), output_dir=tmp_path, stem="run")
    assert backend.calls == []
    assert backend.restore_park_calls == 1
    assert backend.close_calls == 1

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    assert totals == [
        900,
        900,
        1500,
        1500,
        900,
        900,
        1500,
        1500,
        900,
        900,
        1500,
        1500,
        896,
        896,
        1498,
        1498,
    ]


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
        ("3pt_ts100", "off"),
        ("3pt_ts100", "on"),
        ("5pt", "off"),
        ("5pt", "on"),
        ("7pt", "off"),
        ("7pt", "on"),
    ]
    assert smoke.frequency_count == 11
    assert all(p.shots_per_condition == 4 for p in smoke.passes)
    assert benchmark.plan_fingerprint(smoke) != benchmark.plan_fingerprint(
        benchmark.full_plan()
    )


def test_five_point_ab_plan_is_the_focused_counterbalanced_matrix():
    plan = benchmark.five_point_ab_plan()
    assert plan.mode == "five_point_ab"
    assert plan.frequency_count == 801
    assert [(item.protocol, item.shots_per_condition, item.predistortion)
            for item in plan.passes] == [
        ("5pt", 180, "off"),
        ("5pt", 180, "on"),
        ("5pt", 300, "on"),
        ("5pt", 300, "off"),
    ]
    assert all(item.delays_us == (40.0, 80.0, 200.0) for item in plan.passes)
    assert all(item.condition_count == 5 for item in plan.passes)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            {"protocol": "unknown"},
            "unknown benchmark protocol",
        ),
        (
            {"delays_us": (100.0, 50.0), "condition_count": 4},
            "canonical definition",
        ),
        (
            {"index": 2},
            "indices must be sequential",
        ),
        (
            {"predistortion": "invalid"},
            "predistortion",
        ),
        (
            {"condition_count": 99},
            "condition count",
        ),
    ],
)
def test_canonical_document_rejects_invalid_pass_contract(replacement, message):
    valid = benchmark.full_plan()
    original = valid.passes[1]
    invalid_pass = benchmark.BenchmarkPass(
        index=replacement.get("index", original.index),
        protocol=replacement.get("protocol", original.protocol),
        delays_us=replacement.get("delays_us", original.delays_us),
        shots_per_condition=replacement.get(
            "shots_per_condition", original.shots_per_condition
        ),
        condition_count=replacement.get("condition_count", original.condition_count),
        predistortion=replacement.get("predistortion", original.predistortion),
        role=original.role,
    )
    invalid_plan = benchmark.BenchmarkPlan(
        **{**valid.__dict__, "passes": (valid.passes[0], invalid_pass, *valid.passes[2:])}
    )

    with pytest.raises(ValueError, match=message):
        benchmark.canonical_document(invalid_plan)


def test_canonical_document_rejects_frequency_count_that_does_not_match_grid():
    valid = benchmark.full_plan()
    invalid_plan = benchmark.BenchmarkPlan(
        **{**valid.__dict__, "frequency_count": 800}
    )

    with pytest.raises(ValueError, match="frequency count"):
        benchmark.canonical_document(invalid_plan)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("index", 1.5, "integer"),
        ("index", True, "integer"),
        ("shots_per_condition", 1.5, "integer"),
        ("shots_per_condition", float("nan"), "integer"),
        ("shots_per_condition", True, "integer"),
        ("condition_count", 3.0, "integer"),
        ("condition_count", True, "integer"),
        ("delays_us", (float("nan"),), "finite"),
    ],
)
def test_canonical_document_rejects_invalid_pass_numbers(field, value, message):
    plan = benchmark.full_plan()
    invalid_pass = replace(plan.passes[1], **{field: value})
    invalid_plan = replace(
        plan, passes=(plan.passes[0], invalid_pass, *plan.passes[2:])
    )

    with pytest.raises(ValueError, match=message):
        benchmark.canonical_document(invalid_plan)


@pytest.mark.parametrize("value", [801.0, True])
def test_canonical_document_rejects_non_integer_frequency_count(value):
    invalid_plan = replace(benchmark.full_plan(), frequency_count=value)

    with pytest.raises(ValueError, match="frequency count must be a positive integer"):
        benchmark.canonical_document(invalid_plan)


def fake_five_point_data(points):
    frequency_index = np.arange(points, dtype=float)
    p0 = 0.10 + frequency_index * 0.0001
    p1 = 0.90 - frequency_index * 0.0001
    gamma = 0.010 + frequency_index * 0.00001
    return {
        "P0": p0,
        "P1": p1,
        "Ps_40us": 0.70 - frequency_index * 0.0001,
        "Ps_80us": 0.50 - frequency_index * 0.0001,
        "Ps_200us": 0.25 - frequency_index * 0.0001,
        "P0_scan_up": p0 + 0.001,
        "P0_scan_down": p0 - 0.001,
        "inv_T1_5pt_per_us": gamma,
        "inv_T1_5pt_err_per_us": np.full(points, 0.0002),
        "T1_5pt_us": 1.0 / gamma,
        "T1_5pt_err_us": np.full(points, 2.0),
        "ref_contrast_5pt": p1 - p0,
        "T1_5pt_valid_mask": np.ones(points, dtype=bool),
        "T1_5pt_fit_success": np.ones(points, dtype=bool),
        "T1_5pt_fit_deviance": np.full(points, 0.01),
        "inv_T1_5pt_per_us_scan_up": gamma + 0.0005,
        "inv_T1_5pt_per_us_scan_down": gamma - 0.0005,
        "inv_T1_5pt_per_us_scan_direction_delta": np.full(points, 0.001),
    }


def synthetic_rows(
    *, valid_fraction=1.0, direction_offset=0.0, gamma_offset=0.0,
    gamma_error=0.001,
):
    rows = []
    for index in range(20):
        valid = index < int(20 * valid_fraction)
        rows.append({
            "pass_index": 0,
            "pass_id": "p00_3pt_ts100_300_off",
            "protocol": "3pt_ts100",
            "predistortion": "off",
            "shots_per_condition": 300,
            "condition_count": 3,
            "target_frequency_ghz": 4.3 - index * 0.0005,
            "realized_frequency_ghz": 4.3 - index * 0.0005,
            "flux_coordinate": index,
            "gamma1_per_us": 0.010 + gamma_offset if valid else np.nan,
            "gamma1_err_per_us": gamma_error,
            "t1_us": 100.0,
            "t1_err_us": 1.0,
            "valid": valid,
            "reference_contrast": 0.8,
            "fit_success": valid,
            "fit_deviance": 0.01,
            "scan_direction_delta": direction_offset,
            "P0": 0.1,
            "P1": 0.9,
            "Ps": 0.5,
        })
    return rows


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
    with pytest.raises(FileNotFoundError, match="artifacts"):
        benchmark.record_pass_complete(
            manifest_path, 0, raw_path=raw_path, metadata_path=metadata_path,
            ended_at="2026-09-16T12:00:00-04:00", duration_s=1.2,
        )
    raw_path.write_text("frequency_ghz,gamma1_per_us\n4.05,0.01\n")
    metadata_path.write_text("{}")
    completed = benchmark.record_pass_complete(
        manifest_path, 0, raw_path=raw_path, metadata_path=metadata_path,
        ended_at="2026-09-16T12:00:00-04:00", duration_s=1.2,
    )
    assert completed["passes"][0]["status"] == "complete"
    assert completed["passes"][0]["artifacts"]["raw_csv"]["sha256"]
    assert completed["plan"] == benchmark.canonical_document(plan)
    assert benchmark.pending_passes(completed, plan) == plan.passes[1:]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"plan": benchmark.full_plan()}, "plan"),
        ({"device": "q5"}, "device"),
        ({"controller": "qua"}, "controller"),
        ({"model_sha256": "2" * 64}, "model"),
        ({"calibration_id": "cal-2"}, "calibration"),
    ],
)
def test_resume_refuses_provenance_mismatches(tmp_path, override, message):
    plan = benchmark.smoke_plan()
    path = tmp_path / "manifest.json"
    benchmark.atomic_write_json(path, benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc123",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    ))
    arguments = {
        "plan": plan,
        "device": "q3",
        "controller": "qick",
        "model_sha256": "1" * 64,
        "calibration_id": "cal-1",
    }
    arguments.update(override)
    with pytest.raises(ValueError, match=message):
        benchmark.load_resume_manifest(path, **arguments)


def test_resume_rechecks_both_completed_artifact_checksums(tmp_path):
    plan = benchmark.smoke_plan()
    path = tmp_path / "manifest.json"
    benchmark.atomic_write_json(path, benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    ))
    raw_path, metadata_path = benchmark.artifact_paths(tmp_path, "q3", plan.passes[0])
    raw_path.write_text("raw version one")
    metadata_path.write_text('{"metadata": 1}')
    benchmark.record_pass_complete(
        path, 0, raw_path=raw_path, metadata_path=metadata_path,
        ended_at="2026-09-16T12:00:00-04:00", duration_s=1.2,
    )
    metadata_path.write_text('{"metadata": 2}')
    with pytest.raises(ValueError, match="checksum"):
        benchmark.load_resume_manifest(
            path, plan, device="q3", controller="qick",
            model_sha256="1" * 64, calibration_id="cal-1",
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


def test_pending_passes_rejects_a_forged_complete_entry_without_artifacts():
    plan = benchmark.smoke_plan()
    manifest = benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    )
    manifest["passes"][0]["status"] = "complete"

    with pytest.raises(ValueError, match="artifacts"):
        benchmark.pending_passes(manifest, plan)


def test_pending_passes_rejects_checksum_valid_artifacts_from_a_different_plan(tmp_path):
    plan = benchmark.smoke_plan()
    manifest_path = tmp_path / "manifest.json"
    manifest = benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    )
    benchmark.atomic_write_json(manifest_path, manifest)
    raw_path, metadata_path = benchmark.artifact_paths(tmp_path, "q3", plan.passes[0])
    raw_path.write_text("raw")
    metadata_path.write_text("{}")
    completed = benchmark.record_pass_complete(
        manifest_path, 0, raw_path=raw_path, metadata_path=metadata_path,
        ended_at="2026-09-16T12:00:00-04:00", duration_s=1.0,
    )
    shifted_plan = replace(
        plan, frequency_start_ghz=4.305, frequency_stop_ghz=4.3
    )

    with pytest.raises(ValueError, match="plan"):
        benchmark.pending_passes(completed, shifted_plan)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda manifest: manifest.__setitem__("plan_fingerprint", "forged"), "plan fingerprint"),
        (lambda manifest: manifest["passes"][0].__setitem__("pass_id", "forged"), "pass list"),
        (lambda manifest: manifest["passes"][0].__setitem__("status", "forged"), "pass status"),
    ],
)
def test_pending_passes_validates_manifest_fingerprint_identity_and_status(mutate, message):
    plan = benchmark.smoke_plan()
    manifest = benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    )
    mutate(manifest)

    with pytest.raises(ValueError, match=message):
        benchmark.pending_passes(manifest, plan)


def test_normalization_preserves_raw_populations_and_directional_diagnostics():
    spec = benchmark.full_plan().passes[8]
    data = fake_five_point_data(points=801)
    rows = benchmark.normalize_experiment_data(
        spec,
        data,
        target_frequency_ghz=np.linspace(4.3, 3.9, 801),
        realized_frequency_ghz=np.linspace(4.3, 3.9, 801),
        flux_coordinate=np.arange(801),
        requested_flux_coordinate=np.arange(801) + 10,
        realized_flux_coordinate=np.arange(801) + 10.25,
        delays_us=(40.0, 80.0, 200.0),
        pass_started_at="2026-09-16T12:00:00-04:00",
        pass_ended_at="2026-09-16T12:02:00-04:00",
        normalization_denominator=np.full(801, 0.8),
        residual_deviance=np.full(801, 0.02),
        non_exponential_diagnostic=np.full(801, 0.03),
    )
    assert len(rows) == 801
    assert {"P0", "P1", "Ps_40us", "Ps_80us", "Ps_200us", "P0_scan_up"} <= rows[0].keys()
    assert {"gamma1_per_us", "gamma1_err_per_us", "valid", "fit_deviance", "scan_direction_delta"} <= rows[0].keys()
    assert rows[0]["gamma1_per_us"] == pytest.approx(0.01)
    assert rows[0]["scan_direction_delta"] == pytest.approx(0.001)
    assert rows[0]["flux_coordinate"] == 0
    assert rows[0]["requested_flux_coordinate"] == 10
    assert rows[0]["realized_flux_coordinate"] == pytest.approx(10.25)
    assert rows[0]["delays_us"] == [40.0, 80.0, 200.0]
    assert rows[0]["pass_started_at"] == "2026-09-16T12:00:00-04:00"
    assert rows[0]["pass_ended_at"] == "2026-09-16T12:02:00-04:00"
    assert rows[0]["normalization_denominator"] == pytest.approx(0.8)
    assert rows[0]["residual_deviance"] == pytest.approx(0.02)
    assert rows[0]["non_exponential_diagnostic"] == pytest.approx(0.03)
    assert {
        "requested_flux_coordinate", "realized_flux_coordinate", "delays_us",
        "pass_started_at", "pass_ended_at", "normalization_denominator",
        "residual_deviance", "non_exponential_diagnostic",
    } <= set(benchmark.PASS_ROW_COLUMNS)


def test_three_point_normalization_keeps_unknown_uncertainty_unavailable(tmp_path):
    item = benchmark.full_plan().passes[0]
    points = 3
    rows = benchmark.normalize_experiment_data(
        item,
        {
            "P0": np.full(points, 0.1),
            "P1": np.full(points, 0.9),
            "Ps": np.full(points, 0.5),
            "inv_T1_3pt_per_us": np.full(points, 0.01),
            "T1_3pt_us": np.full(points, 100.0),
            "T1_3pt_valid_mask": np.ones(points, dtype=bool),
        },
        target_frequency_ghz=np.linspace(4.3, 4.2, points),
        realized_frequency_ghz=np.linspace(4.3, 4.2, points),
        flux_coordinate=np.arange(points),
    )
    assert all(np.isnan(row["gamma1_err_per_us"]) for row in rows)
    output = tmp_path / "three_point.png"
    result = benchmark.render_comparison_figure(
        {"passes": [{"index": 0, "rows": rows}, {"index": 16, "rows": rows}]},
        output,
    )
    assert output.exists()
    assert result["uncertainty_band_series"] == 0
    assert result["uncertainty_unavailable_series"] >= 1


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
    assert corrupt_metrics["longest_invalid_run"] == 1


def test_opening_and_closing_sentinels_report_drift_in_sigma_units():
    opening = synthetic_rows(gamma_offset=0.0, gamma_error=0.001)
    closing = synthetic_rows(gamma_offset=0.004, gamma_error=0.001)
    result = benchmark.compare_sentinels(opening, closing)
    assert result["median_abs_delta_per_us"] == pytest.approx(0.004)
    assert result["median_abs_delta_sigma"] > 2.0


def test_sentinel_comparison_rejects_misaligned_frequency_coordinates():
    opening = synthetic_rows()
    closing = synthetic_rows(gamma_offset=0.004)
    closing[2]["realized_frequency_ghz"] -= 0.001

    with pytest.raises(ValueError, match="realized frequency"):
        benchmark.compare_sentinels(opening, closing)


def test_sentinel_comparison_excludes_invalid_values_and_unknown_uncertainty():
    opening = synthetic_rows(gamma_error=np.nan)
    closing = synthetic_rows(gamma_offset=0.004, gamma_error=np.nan)
    for row in opening + closing:
        row["valid"] = False
    result = benchmark.compare_sentinels(opening, closing)
    assert result["finite_count"] == 0
    assert result["sigma_finite_count"] == 0
    assert np.isnan(result["median_abs_delta_per_us"])
    assert np.isnan(result["median_abs_delta_sigma"])


def test_csv_summary_and_linecut_figure_artifacts_are_written(tmp_path):
    rows = synthetic_rows()
    raw_path = tmp_path / "pass_raw.csv"
    summary_path = tmp_path / "summary.csv"
    figure_path = tmp_path / "comparison.png"
    assert benchmark.write_pass_csv(raw_path, rows) == raw_path
    assert benchmark.write_summary_csv(summary_path, [benchmark.summarize_pass(rows)]) == summary_path
    with raw_path.open(newline="") as stream:
        written = list(csv.DictReader(stream))
    assert written[0]["gamma1_per_us"] == "0.01"
    assert "median_local_roughness" in summary_path.read_text()

    primary = {index: [dict(row, pass_index=index, pass_id=f"p{index:02d}") for row in rows] for index in range(16)}
    session = {
        "plan_fingerprint": "f" * 64,
        "model_provenance": {"sha256": "a" * 64},
        "passes": [{"index": index, "rows": pass_rows} for index, pass_rows in primary.items()],
    }
    session["passes"].append({"index": 16, "rows": synthetic_rows(gamma_offset=0.002)})
    metadata = benchmark.render_comparison_figure(session, figure_path)
    assert figure_path.exists() and figure_path.stat().st_size > 2_000
    assert metadata["primary_map_panels"] == 16
    assert metadata["sentinel_panels"] >= 1
    assert metadata["sentinel_linecut_panels"] == 2
    assert metadata["plan_fingerprint"] == "f" * 64
    assert metadata["model_sha256"] == "a" * 64
    assert metadata["metrics_table_columns"] == [
        "pass", "valid", "uncertainty", "direction", "runtime", "contrast"
    ]


def test_comparison_figure_labels_each_condition_and_marks_invalid_nonprimary_points(
    tmp_path, monkeypatch,
):
    import matplotlib.pyplot as plt

    captured = []
    original_close = plt.close
    monkeypatch.setattr(plt, "close", lambda figure: captured.append(figure))
    off_rows = synthetic_rows(valid_fraction=0.95)
    on_rows = [dict(row, predistortion="on") for row in synthetic_rows(valid_fraction=0.95)]
    session = {
        "passes": [
            {"index": 0, "rows": off_rows},
            {"index": 1, "rows": on_rows},
            {"index": 16, "rows": [dict(row, gamma1_per_us=row["gamma1_per_us"] + 0.002) for row in off_rows]},
        ]
    }
    benchmark.render_comparison_figure(session, tmp_path / "labels.png")
    figure = captured[0]
    primary_title = figure.axes[0].get_title()
    difference_axis = next(axis for axis in figure.axes if "sentinel difference" in axis.get_title())
    overlay_axis = next(axis for axis in figure.axes if axis.get_title() == "matched-budget Gamma1 comparisons")
    overlay_labels = [text.get_text() for text in overlay_axis.get_legend().get_texts()]
    original_close(figure)

    assert "3pt_ts100" in primary_title
    assert "300 shots/condition" in primary_title
    assert "900 shots" in primary_title
    assert "OFF" in primary_title
    assert "invalid 1/20" in difference_axis.get_title()
    assert any("invalid 1/20" in label for label in overlay_labels)
    assert any("3pt_ts100" in label and "900 shots" in label and "ON" in label for label in overlay_labels)
    assert difference_axis.collections
    assert overlay_axis.collections


def _full_session_with_shifted_realization():
    def rows_for(item, gamma_offset=0.0):
        rows = []
        for point, target_frequency in enumerate((4.3, 4.2, 4.1)):
            valid = point != 2
            rows.append({
                "pass_index": item.index,
                "pass_id": item.pass_id,
                "protocol": item.protocol,
                "predistortion": item.predistortion,
                "shots_per_condition": item.shots_per_condition,
                "condition_count": item.condition_count,
                "target_frequency_ghz": target_frequency,
                "realized_frequency_ghz": target_frequency + 0.025,
                "gamma1_per_us": 0.01 + gamma_offset if valid else np.nan,
                "gamma1_err_per_us": 0.001,
                "valid": valid,
                "P0": 0.1,
                "P1": 0.9,
                "scan_direction_delta": 0.0,
                "fit_deviance": 0.01,
            })
        return rows

    plan = benchmark.full_plan()
    return {
        "passes": [
            {"index": item.index, "rows": rows_for(item)}
            for item in plan.passes[:16]
        ] + [{"index": 16, "rows": rows_for(plan.passes[16], gamma_offset=0.002)}]
    }


def test_full_matrix_overlay_has_only_six_low_cost_series_and_no_marker_legend_duplicates(
    tmp_path, monkeypatch,
):
    import matplotlib.pyplot as plt

    captured = []
    original_close = plt.close
    monkeypatch.setattr(plt, "close", lambda figure: captured.append(figure))
    benchmark.render_comparison_figure(
        _full_session_with_shifted_realization(), tmp_path / "full.png"
    )
    figure = captured[0]
    overlay_axis = next(axis for axis in figure.axes if axis.get_title() == "matched-budget Gamma1 comparisons")
    overlay_labels = [text.get_text() for text in overlay_axis.get_legend().get_texts()]
    original_close(figure)

    assert len(overlay_labels) == 6
    assert not any("masked invalid" in label for label in overlay_labels)
    assert all("invalid 1/3" in label for label in overlay_labels)
    assert {"3pt_ts100", "5pt", "7pt"} == {
        next(protocol for protocol in ("3pt_ts100", "5pt", "7pt") if protocol in label)
        for label in overlay_labels
    }
    assert not any("1500 shots" in label or "1498 shots" in label for label in overlay_labels)


def test_nonprimary_panels_plot_shifted_realized_frequency(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    captured = []
    original_close = plt.close
    monkeypatch.setattr(plt, "close", lambda figure: captured.append(figure))
    benchmark.render_comparison_figure(
        _full_session_with_shifted_realization(), tmp_path / "realized.png"
    )
    figure = captured[0]
    sentinel_axis = next(axis for axis in figure.axes if "sentinel difference" in axis.get_title())
    overlay_axis = next(axis for axis in figure.axes if axis.get_title() == "matched-budget Gamma1 comparisons")
    sentinel_x = sentinel_axis.lines[0].get_xdata()
    overlay_x = overlay_axis.lines[0].get_xdata()
    original_close(figure)

    np.testing.assert_allclose(sentinel_x, [4.325, 4.225])
    np.testing.assert_allclose(overlay_x, [4.325, 4.225])
    assert sentinel_axis.get_xlabel() == "realized frequency (GHz)"
    assert overlay_axis.get_xlabel() == "realized frequency (GHz)"
