"""Regression tests for the q3 two-transition loss experiment."""

import importlib
import json
from types import SimpleNamespace
from datetime import datetime, timezone

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
                        "Ps_10us" + suffix: str(.1 + .8 * survival),
                        "Ps_25us" + suffix: str(.1 + .8 * survival)})
        rows.append(row)
    chosen = dual.select_eligible_feature(rows, anharmonicity_mhz=-180)
    assert chosen["center_ghz"] == pytest.approx(4.1)
    assert chosen["ef_bias_ghz"] == pytest.approx(4.28)


def test_selector_avoids_ge_loss_at_the_shifted_ef_bias():
    rows = []
    for mhz in range(3800, 4301, 2):
        survival = .9
        if abs(mhz - 4020) <= 2:
            survival = .35
        if abs(mhz - 4076) <= 2:
            survival = .48
        # A second g-e feature at the 4.020-GHz line's e-f matching bias.
        if abs(mhz - 4204) <= 2:
            survival = .28
        row = {"target_frequency_ghz": f"{mhz / 1000:.3f}"}
        for suffix in ("", "_scan_up", "_scan_down"):
            row.update({"P0" + suffix: ".1", "P1" + suffix: ".9",
                        "Ps_10us" + suffix: str(.1 + .8 * survival),
                        "Ps_25us" + suffix: str(.1 + .8 * survival)})
        rows.append(row)
    chosen = dual.select_eligible_feature(rows, anharmonicity_mhz=-180)
    assert chosen["center_ghz"] == pytest.approx(4.076)
    assert chosen["shifted_bias_min_10us_survival"] >= .65


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


def test_ensemble_reference_passes_despite_overlapping_single_shot_clouds():
    rng = np.random.default_rng(91)
    ground = rng.normal(0, 2.2, 500) + 0j
    excited = rng.normal(1.0, 2.2, 500) + 0j
    report = dual.validate_site_references(ground, excited)
    assert report["valid"]
    assert report["ge_fidelity"] < .7
    assert report["ge_mean_contrast_snr"] >= 5


def test_long_dwell_ground_drift_is_removed_from_target_loss():
    assert dual.differential_loss(.88, .55, .04, .08) == pytest.approx(.37)


def test_mean_iq_loss_uses_local_preparation_axis_and_ground_control():
    short_g = np.full(100, 1 + 0j)
    short_e = np.full(100, 5 + 0j)
    long_g = np.full(100, 1.4 + 0j)
    long_e = np.full(100, 3.4 + 0j)
    measured = dual.projected_differential_loss(
        short_g, short_e, long_g, long_e, baseline_iq=short_g)
    assert measured["value"] == pytest.approx(.5)


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


def test_shelved_readout_maps_states_after_return_prefix_before_readout():
    program = object.__new__(dual.DualTransitionProgram)
    program.cfg = {"dual_state": "f", "dual_mode": "science",
                   "dual_readout_map": "shelved", "dual_hold_us": 10.,
                   "dual_ef_gain": 11250, "qubit_ch": 1, "sigma": .03}
    program.reset_config = SimpleNamespace(inter_shot_delay_us=500.)
    program.reset_page = 0
    program.reset_regs = {"i": 1, "q": 2, "address": 3}
    events = []
    program._shot_park_callbacks = lambda: (lambda: None, lambda: None)
    program._set_payload_pulse = lambda **_: events.append("set_ge")
    program._set_ef_pulse = lambda **_: events.append("set_ef")
    program.pulse = lambda **_: events.append("ge")
    program._ef_pulse = lambda **kw: events.append("ef")
    program._wait_t1_payload = lambda **kw: events.append("visit")
    program._measure_raw = lambda: events.append("readout")
    program.memw = program.mathi = lambda *_: None
    program.us2cycles = lambda us: us
    program.sync_all = lambda us: events.append("barrier")
    program.synci = lambda us: events.append("fixed_delay")
    program._emit_body()
    assert events.count("ef") == 1
    visit = events.index("visit")
    readout = events.index("readout")
    assert events[visit + 1:readout] == ["set_ef", "ge", "set_ge",
                                        "ge", "fixed_delay"]
    assert "barrier" not in events[visit + 1:readout]


def test_prompt_readout_overrides_five_point_pre_measure_sync():
    cfg = {"opx_feedback_pre_measure_sync": True,
           "opx_feedback_flush_mode": "off",
           "flux_predistortion_overlap_payload_readout": True}
    dual.configure_prompt_readout(cfg)
    assert cfg["opx_feedback_pre_measure_sync"] is False
    assert cfg["opx_feedback_flush_mode"] == "off"


def test_science_program_rejects_a_return_tail_sync_before_readout():
    cfg = {"opx_reset_scheme": "none", "opx_hard_flux_steps": True,
           "opx_persistent_park": True, "dual_state": "f",
           "dual_mode": "science",
           "flux_predistortion_overlap_payload_readout": True,
           "opx_feedback_pre_measure_sync": True}
    with pytest.raises(ValueError, match="pre-measure sync"):
        dual.DualTransitionProgram(None, cfg, None, None)


def test_shelved_readout_resolves_f_when_direct_centroids_are_collinear():
    rng = np.random.default_rng(123)
    direct = {state: rng.normal(center, .3, 300) + 0j
              for state, center in (("g", 0), ("e", 1), ("f", 2))}
    mapped = {"g": rng.normal(1, .3, 300) + 0j,
              "e": rng.normal(2, .3, 300) + 0j,
              "f": rng.normal(0, .3, 300) + 0j}
    references = {"identity": direct, "shelved": mapped}
    report = dual.validate_shelved_references(references)
    assert report["condition"] < 5
    observed = {"identity": .35 * direct["e"] + .65 * direct["f"],
                "shelved": .35 * mapped["e"] + .65 * mapped["f"]}
    fit = dual.shelved_population(references, observed)
    assert fit["f"] == pytest.approx(.65, abs=.03)
    assert fit["e"] == pytest.approx(.35, abs=.03)


def test_shelved_readout_rejects_unresolved_second_axis():
    rng = np.random.default_rng(22)
    direct = {s: rng.normal(c, .3, 300) + 0j
              for s, c in (("g", 0), ("e", 1), ("f", 2))}
    with pytest.raises(ValueError, match="shelved response"):
        dual.validate_shelved_references({"identity": direct,
                                          "shelved": direct})


def test_shelved_fit_removes_a_matched_ground_iq_shift():
    arrays = {"identity": {"g": np.zeros(200), "e": np.ones(200),
                            "f": np.full(200, 2.)},
              "shelved": {"g": np.ones(200), "e": np.full(200, 2.),
                          "f": np.zeros(200)}}
    long_ground = {name: arrays[name]["g"] + 3.0 for name in arrays}
    long_f = {name: .4 * arrays[name]["e"] +
             .6 * arrays[name]["f"] + 3.0 for name in arrays}
    fit = dual.shelved_population(arrays, long_f, ground_shift=long_ground)
    assert fit["f"] == pytest.approx(.6)
    assert fit["e"] == pytest.approx(.4)


def test_shelved_schedule_reverses_offsets_and_omits_ge_science():
    rows = dual.shelved_schedule(3.95, -180.)
    assert len(rows) == 2 * len(dual.OFFSETS_MHZ)
    assert {row["transition"] for row in rows} == {"ef"}
    assert rows[0]["bias_ge_ghz"] == pytest.approx(4.13)
    assert [r["offset_mhz"] for r in rows if r["pass"] == 1] == list(
        reversed(dual.OFFSETS_MHZ))


def test_shelved_summary_does_not_promote_a_single_pass_peak():
    points = []
    for repeat in (0, 1):
        for offset in dual.OFFSETS_MHZ:
            points.append({"pass": repeat, "offset_mhz": offset,
                           "status": "complete", "f_loss": .5 if offset == 4
                           else .2, "e_control_f": .01})
    result = dual.summarize_shelved_science(points)
    peak = next(row for row in result["profile"] if row["offset_mhz"] == 4)
    assert peak["passes"] == 2
    assert peak["f_loss_mean"] == pytest.approx(.5)
    assert peak["e_control_f_mean"] == pytest.approx(.01)


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


def test_summary_records_one_missing_reference_without_discarding_other_pass():
    points = []
    for repeat in (0, 1):
        for transition in ("ge", "ef"):
            for offset in dual.OFFSETS_MHZ:
                status = ("unresolved_reference" if repeat == 1 and
                          transition == "ge" and offset == 0 else "complete")
                points.append({"pass": repeat, "transition": transition,
                               "offset_mhz": offset, "status": status,
                               "differential_loss": .25 if offset == 2 else .05})
    result = dual.summarize_science(points)
    center = next(row for row in result["profiles"]["ge"]
                  if row["offset_mhz"] == 0)
    assert center["completed_passes"] == 1
    assert result["unresolved_points"] == 1


def test_reuse_accepts_recent_passed_ef_calibration_from_failed_science(tmp_path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = tmp_path / "q3" / f"q3_tls_dual_transition_loss_{stamp}_12345678"
    folder.mkdir(parents=True)
    path = folder / "manifest.json"
    path.write_text(json.dumps({
        "schema": "q3.tls-dual-transition-loss.v1", "status": "failed",
        "correction_sha256": dual.localizer.CORRECTION_SHA256,
        "calibration": {"status": "passed", "park_ge_mhz": 4367.292,
                        "ef_frequency_mhz": 4187.292, "ef_pi_gain": 11250},
    }))
    result = dual.recent_ef_calibration(tmp_path)
    assert result["ef_frequency_mhz"] == 4187.292
    assert result["ef_pi_gain"] == 11250
    assert result["source_manifest"] == str(path)
