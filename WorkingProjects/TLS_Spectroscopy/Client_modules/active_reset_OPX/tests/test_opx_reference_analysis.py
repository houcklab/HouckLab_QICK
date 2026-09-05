import ast
import importlib.util
from pathlib import Path
import tokenize

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.opx_reference_analysis import (
    build_interleaved_schedule,
    fit_method_decays,
    make_comparison,
    normalize_classifier,
    summarize_block_timings,
    summarize_shots,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "opx_reference_t1.py"


def test_schedule_is_deterministic_and_balanced_within_each_round():
    methods = ("passive_1000", "active_25", "active_100")
    schedule = build_interleaved_schedule(4, methods, 5, 123)
    assert schedule == build_interleaved_schedule(4, methods, 5, 123)
    assert schedule != build_interleaved_schedule(4, methods, 5, 124)
    assert len(schedule) == 4 * 3 * 5
    for round_index in range(4):
        observed = {
            (method_index, delay_index)
            for current_round, method_index, delay_index in schedule
            if current_round == round_index
        }
        assert observed == {(method_index, delay_index) for method_index in range(3) for delay_index in range(5)}


def test_shot_reduction_preserves_overall_round_and_shot_order_views():
    methods = ("passive_1000", "active_25")
    delays = np.asarray([1.0, 10.0])
    records = []
    timestamp = 0
    for round_index in range(2):
        for method_code in range(2):
            for delay_index in range(2):
                for shot_index in range(3):
                    records.append(
                        {
                            "round": round_index,
                            "method_code": method_code,
                            "delay_index": delay_index,
                            "shot_index": shot_index,
                            "state": int(method_code == 0 or shot_index == 0),
                            "reset_attempts": method_code * (shot_index + 1),
                            "timestamp_ns": timestamp,
                        }
                    )
                    timestamp += 100
    reduced = summarize_shots(records, methods, delays)
    assert len(reduced["overall"]) == 4
    assert len(reduced["rounds"]) == 8
    assert len(reduced["shot_order"]) == 12
    active = next(row for row in reduced["overall"] if row["method"] == "active_25" and row["delay_index"] == 0)
    assert active["shots"] == 6
    assert active["excited_fraction"] == 1 / 3
    assert active["reset_attempt_mean"] == 2.0
    assert active["reset_attempt_max"] == 3
    assert active["elapsed_ns"] == 1500


def test_fit_comparison_reports_within_chip_ratios():
    methods = ("passive_1000", "active_25")
    times = np.asarray([1.0, 30.0, 100.0, 250.0, 750.0])
    rows = []
    for method, tau, p0, p1 in (
        ("passive_1000", 100.0, 0.02, 0.9),
        ("active_25", 80.0, 0.03, 0.84),
    ):
        for delay_index, delay in enumerate(times):
            population = p0 + (p1 - p0) * np.exp(-delay / tau)
            rows.append(
                {
                    "method": method,
                    "delay_index": delay_index,
                    "delay_us": delay,
                    "shots": 100000,
                    "excited_fraction": population,
                }
            )
    fitted = fit_method_decays(rows, methods)
    assert fitted["errors"] == {}
    comparison = make_comparison(fitted["fits"], "passive_1000")
    active = next(row for row in comparison if row["method"] == "active_25")
    assert np.isclose(active["tau_ratio_to_passive"], 0.8, atol=1e-5)
    assert np.isclose(active["P0_difference_from_passive"], 0.01, atol=1e-5)
    assert np.isclose(active["P1_difference_from_passive"], -0.06, atol=1e-5)


def test_block_timing_reports_per_shot_speedup_to_passive():
    records = []
    for block_index, method_code, start in ((0, 0, 0), (1, 1, 1000), (2, 0, 1600)):
        for shot_index in range(2):
            records.append(
                {
                    "block_index": block_index,
                    "method_code": method_code,
                    "shot_index": shot_index,
                    "timestamp_ns": start + 100 * shot_index,
                }
            )
    rows = summarize_block_timings(records, ("passive_1000", "active_25"), "passive_1000")
    passive = next(row for row in rows if row["method"] == "passive_1000")
    active = next(row for row in rows if row["method"] == "active_25")
    assert passive["median_ns_per_shot"] == 500.0
    assert active["median_ns_per_shot"] == 300.0
    assert np.isclose(active["speedup_to_passive"], 5 / 3)


def test_classifier_normalization_corrects_negative_scale_ground_threshold():
    normalized = normalize_classifier(
        {
            "scale_factor": -1,
            "threshold": -2.0,
            "ground_threshold": 5.0,
        }
    )
    assert normalized == {
        "scale_factor": -1.0,
        "threshold": -2.0,
        "ground_threshold": -5.0,
    }


def test_runner_is_portable_and_contains_true_unbounded_reset_contract():
    assert RUNNER.exists()
    source = RUNNER.read_text()
    tree = ast.parse(source)
    top_level_modules = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "qm" not in top_level_modules
    assert "LabCode" not in top_level_modules
    assert "with while_(I_reset > ground_confidence_threshold):" in source
    assert "active_25" in source
    assert "active_100" in source
    assert "active_400" in source
    assert "active_1000" in source
    assert 'save_all("reset_attempts")' in source
    assert 'save_all("timestamp_ns")' in source
    assert source.count('block_stream.save_all("block_index")') == 1
    assert "stream_processing" in source
    assert "schedule_rounds = declare(int, value=" in source
    assert "with for_(block, 0, block < len(schedule), block + 1):" in source
    assert "for block_index, (round_index, method_code, delay_index) in enumerate(schedule):" not in source
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert ast.get_docstring(node, clean=False) is None
    with RUNNER.open("rb") as handle:
        assert not any(token.type == tokenize.COMMENT for token in tokenize.tokenize(handle.readline))


def test_runner_module_imports_without_qua_or_opx_repository():
    spec = importlib.util.spec_from_file_location("opx_reference_t1_contract", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEFAULT_METHODS["active_25"] == ("active", 25.0)
