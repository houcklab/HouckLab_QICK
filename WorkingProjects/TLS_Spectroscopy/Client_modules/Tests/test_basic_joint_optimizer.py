
from __future__ import annotations

import os
import sys

import numpy as np


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.basic_joint_optimizer import (
    CandidateArchive,
    PulseCandidate,
    duration_stratified_shortlist,
    latency_pareto_frontier,
    propose_trust_region_candidates,
    select_shortest_noninferior,
    validate_structured_coverage,
)


def candidate(read_length=20.0, sigma=0.25, read_gain=5000,
              pi_gain=5800, read_freq=7249.1, qubit_freq=2534.7):
    return {
        "read_pulse_freq": float(read_freq),
        "read_pulse_gain": int(read_gain),
        "read_length": float(read_length),
        "qubit_freq": float(qubit_freq),
        "qubit_pi_freq": float(qubit_freq),
        "qubit_pi_gain": int(pi_gain),
        "sigma": float(sigma),
        "qubit_drag_beta": 0.0,
    }


def measured(**changes):
    fidelity = float(changes.pop("fidelity", 0.90))
    se = float(changes.pop("se", 0.003))
    row = candidate(**changes)
    row.update({
        "fidelity": fidelity,
        "fidelity_se": se,
        "fidelity_lcb_95": fidelity - 1.96 * se,
        "crossfit_fidelity": fidelity,
        "crossfit_fidelity_se": se,
        "crossfit_fidelity_lcb_95": fidelity - 1.96 * se,
    })
    return row


def test_candidate_is_complete_immutable_and_latency_is_physical_chain():
    value = PulseCandidate.from_mapping(candidate(read_length=10.0, sigma=0.15))
    assert value.chain_latency_us() == 10.6
    assert value.duration_key() == (10.0, 0.15)
    changed = value.changed(read_pulse_gain=6000, qubit_pi_freq=2535.0)
    assert value.read_pulse_gain == 5000
    assert changed.read_pulse_gain == 6000
    assert changed.qubit_freq == changed.qubit_pi_freq == 2535.0


def test_duration_stratification_survives_global_false_maximum():
    rows = []
    for read_length in (4.0, 10.0, 20.0):
        for sigma in (0.10, 0.25):
            for gain in (3000, 5000, 7000):
                fidelity = (0.99 - gain * 1e-8
                            if (read_length, sigma) == (4.0, 0.10)
                            else 0.82 + 1e-6 * gain)
                rows.append(measured(
                    read_length=read_length, sigma=sigma,
                    read_gain=gain, fidelity=fidelity, se=0.01))
    selected = duration_stratified_shortlist(
        rows, per_stratum=1, global_count=3, maximum=9)
    durations = {PulseCandidate.from_mapping(row).duration_key()
                 for row in selected}
    assert durations == {
        (4.0, 0.10), (4.0, 0.25), (10.0, 0.10),
        (10.0, 0.25), (20.0, 0.10), (20.0, 0.25),
    }


def test_structured_coverage_detects_one_missing_duration_pair():
    rows = [measured(read_length=length, sigma=sigma)
            for length in (4.0, 20.0) for sigma in (0.10, 0.25)
            if (length, sigma) != (20.0, 0.25)]
    audit = validate_structured_coverage(rows, (4.0, 20.0), (0.10, 0.25))
    assert audit == {
        "complete": False,
        "expected_strata": 4,
        "measured_strata": 3,
        "missing_strata": [(20.0, 0.25)],
    }


def test_trust_region_is_deterministic_bounded_and_cannot_invent_duration():
    rows = []
    for read_length in (4.0, 10.0, 20.0):
        for sigma in (0.10, 0.25):
            for read_gain in (3000, 5000, 7000):
                for pi_gain in (4000, 6000, 8000):
                    fidelity = 0.55 + 0.40 * np.exp(-(
                        ((read_gain - 5600) / 2200) ** 2
                        + ((pi_gain - 6300) / 1800) ** 2
                        + ((read_length - 10.0) / 12.0) ** 2
                        + ((sigma - 0.25) / 0.18) ** 2))
                    rows.append(measured(
                        read_length=read_length, sigma=sigma,
                        read_gain=read_gain, pi_gain=pi_gain,
                        fidelity=fidelity, se=0.006))
    limits = {
        "read_pulse_freq": (7248.7, 7249.5),
        "read_pulse_gain": (1000, 10000),
        "read_length": (4.0, 20.0),
        "qubit_pi_freq": (2534.0, 2535.4),
        "qubit_pi_gain": (1, 20000),
        "sigma": (0.10, 0.25),
    }
    first = propose_trust_region_candidates(
        rows, rng=np.random.default_rng(19), count=12,
        proposal_limits=limits, trust_regions=4, pool_size=800)
    second = propose_trust_region_candidates(
        rows, rng=np.random.default_rng(19), count=12,
        proposal_limits=limits, trust_regions=4, pool_size=800)
    assert first == second
    assert len(first) == 12
    measured_durations = {
        PulseCandidate.from_mapping(row).duration_key() for row in rows}
    for row in first:
        value = PulseCandidate.from_mapping(row)
        assert value.duration_key() in measured_durations
        assert limits["read_pulse_freq"][0] <= value.read_pulse_freq <= limits[
            "read_pulse_freq"][1]
        assert limits["qubit_pi_freq"][0] <= value.qubit_pi_freq <= limits[
            "qubit_pi_freq"][1]
        assert limits["read_pulse_gain"][0] <= value.read_pulse_gain <= limits[
            "read_pulse_gain"][1]


def test_shortest_selection_uses_noninferiority_not_fidelity_per_time():
    reference = measured(read_length=20.0, sigma=0.25,
                         fidelity=0.930, se=0.0008)
    short_good = measured(read_length=10.0, sigma=0.15,
                          fidelity=0.928, se=0.0008)
    short_bad = measured(read_length=1.0, sigma=0.05,
                         fidelity=0.600, se=0.003)
    selected, diagnostics = select_shortest_noninferior(
        [reference, short_good, short_bad], reference,
        max_loss=0.005, confidence_z=1.96,
        minimum_mean=0.85, minimum_lcb=0.82)
    assert PulseCandidate.from_mapping(selected).key() == \
        PulseCandidate.from_mapping(short_good).key()
    bad_diagnostic = next(row for row in diagnostics
                          if np.isclose(row["latency_us"], 1.2))
    assert bad_diagnostic["accepted"] is False


def test_latency_frontier_removes_slow_dominated_points():
    rows = [
        measured(read_length=4.0, sigma=0.10, fidelity=0.80),
        measured(read_length=10.0, sigma=0.10, fidelity=0.90),
        measured(read_length=20.0, sigma=0.25, fidelity=0.89),
        measured(read_length=30.0, sigma=0.25, fidelity=0.94),
    ]
    frontier = latency_pareto_frontier(rows)
    latencies = [PulseCandidate.from_mapping(row).chain_latency_us()
                 for row in frontier]
    assert latencies == [4.4, 10.4, 31.0]


def test_archive_is_append_only_and_labels_drift_epoch():
    sink = []
    archive = CandidateArchive(sink)
    first = archive.append(measured(), stage="coarse",
                           fidelity_level="low", epoch=0)
    second = archive.append(measured(read_gain=6000), stage="medium",
                            fidelity_level="medium", epoch=1)
    assert sink == [first, second]
    assert first["archive_serial"] == 0
    assert second["archive_serial"] == 1
    assert second["drift_epoch"] == 1


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("ALL JOINT OPTIMIZER TESTS PASSED")


if __name__ == "__main__":
    main()
