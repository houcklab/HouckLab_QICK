import os
import sys

import numpy as np


REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import X90CandidateAudit as A


def record(block, freq, gain, quality, coherence, p4, eligible=True, passed=True):
    return {
        "block": block,
        "visit": block,
        "freq_mhz": freq,
        "gain": gain,
        "elapsed_s": 1.0,
        "passed": passed,
        "eligible": eligible,
        "quality": quality,
        "population_1x": 0.5,
        "population_4x": p4,
        "metrics": {
            "P_g": 0.05,
            "P_e": 0.80,
            "P_i": 0.50,
            "P_q": 0.50,
            "reference_contrast": 0.75,
            "ramsey_i": coherence,
            "ramsey_q": 0.0,
            "coherence_magnitude": coherence,
            "coherence_phase_rad": 0.0,
        },
    }


def test_candidate_order_visits_every_pair_once_per_block():
    candidates = [(1.0, gain) for gain in range(10)]
    orders = [A.candidate_order(candidates, block) for block in range(5)]
    assert all(sorted(order) == candidates for order in orders)
    assert orders[0] == list(reversed(orders[1]))
    assert orders[2] == list(reversed(orders[3]))
    assert orders[0] != orders[2]


def test_summary_prefers_complete_reproducible_candidate(monkeypatch):
    monkeypatch.setattr(A, "BLOCKS", 5)
    records = []
    for block, quality in enumerate([0.72, 0.70, 0.71, 0.69, 0.73]):
        records.append(record(block, 2534.55, 2750, quality, quality + 0.05, 0.05))
    records.append(record(0, 2534.50, 3000, 0.90, 0.95, 0.05))
    for block, quality in enumerate([0.62, 0.50, 0.75, 0.48, 0.64]):
        records.append(record(block, 2534.50, 2800, quality, quality + 0.08, 0.08))
    summary = A.summarize(records)
    assert summary[0]["freq_mhz"] == 2534.55
    assert summary[0]["gain"] == 2750
    assert summary[0]["blocks_completed"] == 5
    assert np.isclose(summary[0]["robust_score"], 0.70)
    assert summary[-1]["gain"] == 3000
    assert A.select_recommendation(summary) == summary[0]


def test_all_failed_candidates_have_no_recommendation(monkeypatch):
    monkeypatch.setattr(A, "BLOCKS", 3)
    records = [
        record(block, 2534.55, 2750, 0.2, 0.4, 0.2, passed=False)
        for block in range(3)
    ]
    summary = A.summarize(records)
    assert summary[0]["validation_pass_fraction"] == 0.0
    assert A.select_recommendation(summary) is None


def test_run_saves_outputs_and_recommends_reproducible_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "GAINS", [2700, 2750])
    monkeypatch.setattr(A, "FREQUENCIES_MHZ", [2534.50, 2534.55])
    monkeypatch.setattr(A, "BLOCKS", 3)
    monkeypatch.setattr(A, "SHOTS_PER_BLOCK", 20)
    monkeypatch.setattr(A, "RAMSEY_ROUNDS", 1)

    class FakeOptimize:
        def __init__(self, **kwargs):
            pass

        def _validate_x90(self, freq, gain):
            best = freq == 2534.55 and gain == 2750
            coherence = 0.84 if best else 0.62
            p4 = 0.04 if best else 0.13
            return {
                "passed": best,
                "shots": 20,
                "assignment_reference": {"P_g": 0.05, "P_e": 0.80},
                "population_1x": 0.51 if best else 0.58,
                "population_4x": p4,
                "metrics": {
                    "P_g": 0.05,
                    "P_e": 0.80,
                    "P_i": 0.50,
                    "P_q": 0.50,
                    "reference_contrast": 0.75,
                    "ramsey_i": coherence,
                    "ramsey_q": 0.0,
                    "coherence_magnitude": coherence,
                    "coherence_phase_rad": 0.0,
                },
            }

    monkeypatch.setattr(A, "QubitPulseOptimize", FakeOptimize)
    result = A.run(object(), object(), str(tmp_path))
    assert result["recommended"]["freq_mhz"] == 2534.55
    assert result["recommended"]["gain"] == 2750
    assert len(result["records"]) == 12
    assert all(os.path.exists(path) for path in result["paths"])
