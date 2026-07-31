import os
import sys

import numpy as np


REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import X90PulseTrainAudit as A


def fake_record(stage, block, candidate, populations, rmse, passed):
    return {
        "stage": stage,
        "block": block,
        "visit": 0,
        **candidate,
        "shots": 100,
        "assignment": {"P_g": 0.05, "P_e": 0.80, "contrast": 0.75},
        "populations": {
            str(count): {
                "measured": value,
                "corrected": value,
                "ideal": A.ideal_population(count),
            } for count, value in populations.items()
        },
        "x180_population": {
            "measured": 0.95, "corrected": 0.95, "ideal": 1.0,
        },
        "rmse": rmse,
        "passed": passed,
        "elapsed_s": 1.0,
    }


def test_build_candidates_scales_gain_with_inverse_sigma(monkeypatch):
    monkeypatch.setattr(A, "SIGMAS_US", [0.25, 0.10])
    monkeypatch.setattr(A, "FREQUENCIES_MHZ", [2534.55])
    monkeypatch.setattr(A, "GAIN_SCALES", [1.0])
    candidates = A.build_candidates({"sigma": 0.25, "qubit_pi2_gain": 2750})
    assert candidates == [
        {"sigma_us": 0.25, "freq_mhz": 2534.55,
         "x90_gain": 2750, "x180_gain": 5500},
        {"sigma_us": 0.10, "freq_mhz": 2534.55,
         "x90_gain": 6875, "x180_gain": 13750},
    ]


def test_ideal_x90_train_pattern():
    assert np.allclose(
        [A.ideal_population(count) for count in range(1, 9)],
        [0.5, 1.0, 0.5, 0.0, 0.5, 1.0, 0.5, 0.0])


def test_fine_summary_prefers_reproducible_complete_candidate(monkeypatch):
    monkeypatch.setattr(A, "FINE_BLOCKS", 3)
    good = {"sigma_us": 0.10, "freq_mhz": 2534.55,
            "x90_gain": 6875, "x180_gain": 13750}
    weak = {"sigma_us": 0.25, "freq_mhz": 2534.55,
            "x90_gain": 2750, "x180_gain": 5500}
    ideal = {count: A.ideal_population(count) for count in range(1, 9)}
    records = []
    for block, rmse in enumerate([0.08, 0.09, 0.07]):
        records.append(fake_record("fine", block, good, ideal, rmse, True))
    for block, rmse in enumerate([0.25, 0.31, 0.22]):
        values = {count: 0.5 for count in range(1, 9)}
        records.append(fake_record("fine", block, weak, values, rmse, False))
    summary = A.fine_summary(records)
    assert summary[0]["sigma_us"] == 0.10
    assert summary[0]["blocks_completed"] == 3
    assert np.isclose(summary[0]["robust_rmse"], 0.09)
    assert A.select_recommendation(summary) == summary[0]


def test_failed_pulse_sets_have_no_recommendation(monkeypatch):
    monkeypatch.setattr(A, "FINE_BLOCKS", 3)
    candidate = {"sigma_us": 0.25, "freq_mhz": 2534.55,
                 "x90_gain": 2750, "x180_gain": 5500}
    values = {count: 0.5 for count in range(1, 9)}
    records = [fake_record("fine", block, candidate, values, 0.3, False)
               for block in range(3)]
    assert A.select_recommendation(A.fine_summary(records)) is None


def test_run_completes_survey_fine_scan_and_outputs(monkeypatch, tmp_path):
    good = {"sigma_us": 0.10, "freq_mhz": 2534.55,
            "x90_gain": 6875, "x180_gain": 13750}
    weak = {"sigma_us": 0.10, "freq_mhz": 2534.50,
            "x90_gain": 6500, "x180_gain": 13000}
    monkeypatch.setattr(A, "SIGMAS_US", [0.10])
    monkeypatch.setattr(A, "FINE_PER_SIGMA", 1)
    monkeypatch.setattr(A, "FINE_BLOCKS", 2)
    monkeypatch.setattr(A, "build_candidates", lambda: [weak, good])
    monkeypatch.setattr(
        A, "acquire_reference",
        lambda *args: ({"threshold": 0.0},
                       {"P_g": 0.05, "P_e": 0.80, "contrast": 0.75}))

    def measure(*args):
        stage, block, visit, candidate, counts = args[3:8]
        if candidate["freq_mhz"] == 2534.55:
            values = {count: A.ideal_population(count) for count in counts}
            return fake_record(stage, block, candidate, values, 0.05, True)
        values = {count: 0.5 for count in counts}
        return fake_record(stage, block, candidate, values, 0.30, False)

    monkeypatch.setattr(A, "measure_candidate", measure)
    result = A.run(object(), object(), str(tmp_path))
    assert result["recommended"]["sigma_us"] == 0.10
    assert result["recommended"]["freq_mhz"] == 2534.55
    assert result["recommended"]["x90_gain"] == 6875
    assert all(os.path.exists(path) for path in result["paths"])
