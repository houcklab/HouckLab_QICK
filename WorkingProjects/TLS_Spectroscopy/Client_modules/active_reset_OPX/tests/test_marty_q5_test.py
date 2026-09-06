import importlib.util
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "test.py"


def load_script():
    spec = importlib.util.spec_from_file_location("marty_q5_active_reset_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schedule_balances_every_method_and_delay_in_each_round():
    module = load_script()
    methods = {"passive": ("passive", 2000.0), "active": ("active", 50.0)}
    first = module.build_schedule(3, methods, 4, 91)
    second = module.build_schedule(3, methods, 4, 91)
    assert first == second
    assert len(first) == 24
    for round_index in range(3):
        observed = {
            (method_code, delay_index)
            for current_round, method_code, delay_index in first
            if current_round == round_index
        }
        assert observed == {(method_code, delay_index) for method_code in range(2) for delay_index in range(4)}


def test_methods_include_configured_active_wait_without_duplicates():
    module = load_script()
    methods = module.build_methods(5000.0, 20.0, (20.0, 25.0, 50.0))
    assert methods == {
        "passive_5000": ("passive", 5000.0),
        "active_20": ("active", 20.0),
        "active_25": ("active", 25.0),
        "active_50": ("active", 50.0),
    }


def test_summary_preserves_population_attempts_and_shot_index():
    module = load_script()
    methods = {"passive": ("passive", 2000.0), "active": ("active", 50.0)}
    records = []
    for round_index in range(2):
        for shot_index in range(3):
            records.append(
                {
                    "round": round_index,
                    "method_code": 1,
                    "delay_index": 0,
                    "shot_index": shot_index,
                    "block_index": round_index,
                    "state": int(shot_index == 0),
                    "reset_attempts": shot_index,
                    "timestamp_ns": round_index * 1000 + shot_index * 100,
                }
            )
    summary = module.summarize_records(records, methods, np.asarray([10.0]))
    assert summary["overall"] == [
        {
            "method": "active",
            "method_code": 1,
            "delay_index": 0,
            "delay_us": 10.0,
            "shots": 6,
            "excited_count": 2,
            "excited_fraction": 1 / 3,
            "mean_reset_attempts": 1.0,
            "max_reset_attempts": 2,
        }
    ]
    assert [row["excited_fraction"] for row in summary["shot_order"]] == [1.0, 0.0, 0.0]


def test_timing_uses_only_within_block_payload_intervals():
    module = load_script()
    methods = {"passive": ("passive", 2000.0), "active": ("active", 50.0)}
    records = []
    for block_index, method_code, start, spacing in ((0, 0, 0, 1000), (1, 1, 10000, 250)):
        for shot_index in range(4):
            records.append(
                {
                    "block_index": block_index,
                    "method_code": method_code,
                    "shot_index": shot_index,
                    "timestamp_ns": start + spacing * shot_index,
                }
            )
    timing = module.summarize_timing(records, methods, "passive")
    passive = next(row for row in timing if row["method"] == "passive")
    active = next(row for row in timing if row["method"] == "active")
    assert passive["median_ns_per_shot"] == 1000.0
    assert active["median_ns_per_shot"] == 250.0
    assert active["speedup_to_passive"] == 4.0


def test_fit_reports_active_to_passive_t1_ratio():
    module = load_script()
    methods = {"passive": ("passive", 2000.0), "active": ("active", 50.0)}
    times = np.asarray([1.0, 50.0, 200.0, 800.0, 2000.0])
    rows = []
    for method, tau in (("passive", 800.0), ("active", 720.0)):
        for delay_index, delay_us in enumerate(times):
            rows.append(
                {
                    "method": method,
                    "delay_index": delay_index,
                    "delay_us": delay_us,
                    "shots": 100000,
                    "excited_fraction": 0.02 + 0.88 * np.exp(-delay_us / tau),
                }
            )
    result = module.fit_methods(rows, methods, "passive")
    assert result["errors"] == {}
    active = next(row for row in result["comparison"] if row["method"] == "active")
    assert np.isclose(active["T1_ratio_to_passive"], 0.9, atol=1e-5)
    assert np.isclose(active["P1_difference_from_passive"], 0.0, atol=1e-5)


def test_classifier_normalizes_negative_single_shot_orientation():
    module = load_script()
    assert module.normalize_classifier(
        {"scale_factor": -1, "threshold": -2.0, "ground_threshold": 4.0}
    ) == (-1.0, -2.0, -4.0)
