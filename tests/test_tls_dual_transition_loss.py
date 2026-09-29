"""Regression tests for the q3 two-transition loss experiment."""

import importlib
from types import SimpleNamespace

import numpy as np
import pytest


dual = importlib.import_module(
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSDualTransitionLoss"
)


def test_eligible_scout_selects_bidirectional_low_line_not_high_line():
    rows = []
    for mhz in range(3800, 4301, 2):
        frequency = mhz / 1000
        survival = 0.82
        if abs(mhz - 4100) <= 2:
            survival = 0.36
        if abs(mhz - 4200) <= 2:
            survival = 0.20
        row = {"target_frequency_ghz": f"{frequency:.3f}"}
        for suffix in ("", "_scan_up", "_scan_down"):
            row.update({"P0" + suffix: "0.10", "P1" + suffix: "0.90",
                        "Ps_25us" + suffix: str(.1 + .8 * survival)})
        rows.append(row)
    chosen = dual.select_eligible_feature(rows, anharmonicity_mhz=-180)
    assert chosen["center_ghz"] == pytest.approx(4.1)
    assert chosen["ef_bias_ghz"] == pytest.approx(4.28)


def test_ef_calibration_rejects_nonreturning_pulse():
    baseline = np.zeros(100, dtype=complex)
    pi = np.ones(100, dtype=complex)
    two_pi = np.full(100, .7 + 0j)
    with pytest.raises(ValueError, match="2π return"):
        dual.validate_ef_audit(baseline, pi, two_pi)


def test_schedule_interleaves_transitions_and_reverses_offsets():
    arms = dual.science_schedule(4.1, -180)
    assert arms[0]["transition"] == "ge"
    assert arms[1]["transition"] == "ef"
    assert arms[0]["transition_frequency_ghz"] == pytest.approx(4.1)
    assert arms[1]["bias_ge_ghz"] == pytest.approx(4.28)
    assert arms[-1]["pass"] == 1
    first_offsets = [a["offset_mhz"] for a in arms if a["pass"] == 0
                     and a["transition"] == "ge"]
    second_offsets = [a["offset_mhz"] for a in arms if a["pass"] == 1
                      and a["transition"] == "ge"]
    assert second_offsets == list(reversed(first_offsets))


def test_f_reference_must_be_resolved_from_both_lower_states():
    rng = np.random.default_rng(12)
    g = rng.normal(0, .2, 300) + 1j * rng.normal(0, .2, 300)
    e = rng.normal(2, .2, 300) + 1j * rng.normal(0, .2, 300)
    f = rng.normal(4, .2, 300) + 1j * rng.normal(0, .2, 300)
    report = dual.validate_site_references(g, e, f)
    assert report["valid"]
    assert report["f_vs_e_fidelity"] > .9
    with pytest.raises(ValueError, match="f readout"):
        dual.validate_site_references(g, e, e)


def test_long_dwell_ground_drift_is_removed_from_target_loss():
    assert dual.differential_loss(.88, .55, .04, .08) == pytest.approx(.37)


def test_local_classifier_finds_f_population_separately_from_e():
    report = {"centroids": [[0, 0], [2, 0], [4, 0]]}
    sample = np.array([3.9 + 0j] * 80 + [2.1 + 0j] * 20)
    assert dual.target_fraction(sample, report, "f") == pytest.approx(.8)


def test_f_is_prepared_at_park_and_read_before_return_tail_barrier():
    program = object.__new__(dual.DualTransitionProgram)
    program.cfg = {"dual_state": "f", "dual_mode": "science",
                   "dual_hold_us": 10., "qubit_ch": 1}
    program.reset_config = SimpleNamespace(inter_shot_delay_us=500.)
    program.reset_page = 0
    program.reset_regs = {"i": 1, "q": 2, "address": 3}
    events = []
    program._shot_park_callbacks = lambda: (
        lambda: events.append("park_up"), lambda: events.append("park_down"))
    program._set_payload_pulse = lambda **_: events.append("set_ge")
    program.pulse = lambda **_: events.append("ge")
    program._ef_pulse = lambda: events.append("ef")
    program._wait_t1_payload = lambda **kw: events.append(("visit", kw["hold_us"]))
    program._measure_raw = lambda: events.append("readout")
    program.memw = program.mathi = lambda *_: None
    program.us2cycles = lambda us: us
    program.sync_all = lambda us: events.append(("barrier", us))
    program._emit_body()
    assert events.index("ge") < events.index("ef") < events.index(("visit", 10.))
    assert events.index(("visit", 10.)) < events.index("readout")
    assert events.index("readout") < events.index(("barrier", 0))
    assert events.index(("barrier", 0)) < events.index("park_down")


def test_summary_compares_two_transitions_in_same_frequency_coordinate():
    points = []
    for repeat in (0, 1):
        for transition in ("ge", "ef"):
            for offset in dual.OFFSETS_MHZ:
                points.append({"pass": repeat, "transition": transition,
                               "offset_mhz": offset, "status": "complete",
                               "differential_loss": .3 if offset == 2 else .05})
    result = dual.summarize_science(points)
    assert result["peak_offset_mhz"] == {"ge": 2, "ef": 2}
    assert result["peak_separation_mhz"] == 0
