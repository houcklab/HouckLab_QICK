"""Contracts for the experiment-only two-readout q3 pump/probe pilot."""

import importlib
from types import SimpleNamespace

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeHeralded"


def experiment():
    return importlib.import_module(MODULE)


def test_paired_decoder_preserves_signed_raw_iq_and_rejects_truncation():
    module = experiment()
    records = module.decode_paired_iq([0xFFFFFFFF, 2, 3, 0xFFFFFFFC], 1)
    assert records == [module.PairedIQ(-1, 2, 3, -4)]
    with pytest.raises(ValueError, match="four words"):
        module.decode_paired_iq([1, 2, 3], 1)


def test_shot_emits_pump_readout_guard_then_probe_readout_without_feedback():
    module = experiment()
    program = object.__new__(module.HeraldedPumpProbeProgram)
    program.cfg = {"qubit_ch": 1, "ff_gain": -17200,
                   "opx_herald_probe_gain": -17000,
                   "opx_herald_pump_state": "e", "opx_herald_probe_state": "g",
                   "opx_herald_pump_us": 20.0, "opx_herald_probe_us": 2.0}
    program.reset_config = SimpleNamespace(read_delay_us=10.0,
                                           inter_shot_delay_us=500.0,
                                           hard_flux_steps=True)
    program.reset_page = 0
    program.reset_regs = {"i": 1, "q": 2, "address": 3}
    events = []
    program._shot_park_callbacks = lambda: (
        lambda: events.append("park_up"), lambda: events.append("park_down"))
    program._set_payload_pulse = lambda **kw: events.append(("set_pi", kw.get("gain", 13500)))
    program.pulse = lambda **kw: events.append("pi")
    program._wait_t1_payload = lambda hold: events.append(("target", hold, program.cfg["ff_gain"]))
    program._measure_raw = lambda: events.append("readout")
    program.memw = lambda *_: events.append("save")
    program.mathi = lambda *_: None
    program.us2cycles = lambda us, **_: us
    program.sync_all = lambda us: events.append(("wait", us))

    program._emit_body()

    assert events == ["park_up", ("set_pi", None), "pi", ("wait", 0.01),
                      ("target", 20.0, -17200), "readout", "save", "save",
                      ("wait", 20.0), ("set_pi", 0), "pi", ("wait", 0.01),
                      ("target", 2.0, -17000), "readout", "save", "save",
                      "park_down", ("wait", 500.0)]
    assert program.cfg["ff_gain"] == -17200


def test_off_target_pump_control_changes_only_first_excursion():
    module = experiment()
    arms = module.science_arms(center_ghz=4.134, flank_ghz=4.120)
    hot = next(arm for arm in arms if arm["name"] == "hot_on_g")
    off = next(arm for arm in arms if arm["name"] == "hot_off_g")
    cold = next(arm for arm in arms if arm["name"] == "cold_on_g")
    assert hot["pump_state"] == off["pump_state"] == "e"
    assert hot["pump_ghz"] == cold["pump_ghz"] == 4.134
    assert off["pump_ghz"] == 4.120
    assert {arm["probe_ghz"] for arm in arms} == {4.134}
    assert cold["pump_state"] == "g"


def test_confident_herald_rule_rejects_excited_tail_and_accepts_ground():
    module = experiment()
    ground = np.tile(np.array([-4, -3, -2, -2, -1], dtype=float), 20)
    excited = np.tile(np.array([1, 2, 2, 3, 4], dtype=float), 20)
    fit = module.fit_readout_axis(ground + 0j, excited + 0j)
    assert fit["fidelity"] == 1.0
    assert module.confident_ground(ground + 0j, fit).all()
    assert not module.confident_ground(excited + 0j, fit).any()


def test_overlapping_herald_reference_aborts_instead_of_reporting_a_signal():
    module = experiment()
    with pytest.raises(RuntimeError, match="reference contrast"):
        module.fit_readout_axis(np.zeros(100), np.zeros(100))


def test_herald_threshold_uses_allowed_false_ground_budget_to_keep_clean_shots():
    module = experiment()
    ground = np.array([-10.0] * 15 + [3.0] * 40 + [20.0] * 45)
    excited = np.arange(100, dtype=float)
    axis = module.fit_readout_axis(ground, excited)
    assert axis["ground_accept"] == 0.55
    assert axis["false_ground"] == 0.05
    assert module.confident_ground(ground, axis).sum() == 55


def test_false_ground_budget_holds_for_small_conditioned_reference():
    module = experiment()
    axis = module.fit_readout_axis(np.full(187, -1.0),
                                   np.arange(187, dtype=float))
    assert axis["false_ground"] <= 0.05
    assert axis["ground_accept"] == 1.0


def test_second_readout_reference_uses_ground_heralded_pi_arm():
    module = experiment()
    arms = module.reference_arms(4.134, phase="pre")
    assert [(a["name"], a["pump_state"], a["probe_state"]) for a in arms] == [
        ("ref_g_pre", "g", "g"),
        ("ref_e_pre", "e", "g"),
        ("ref_final_e_pre", "g", "e"),
    ]
    g = [module.PairedIQ(-2, 0, -2, 0)] * 100
    first_e = [module.PairedIQ(2, 0, -2, 0)] * 100
    final_e = [module.PairedIQ(-2, 0, 2, 0)] * 100
    axes = module.calibrate_pair(g, first_e, final_e)
    assert axes["herald"]["fidelity"] == 1.0
    assert axes["final"]["fidelity"] == 1.0
    assert all(report["valid"] for report in axes["herald_holdout"])


def test_frozen_axis_rejects_independent_false_ground_drift():
    module = experiment()
    axis = {"theta_rad": 0.0, "threshold": 0.0, "ground_limit": -1.0}
    ground = np.full(100, -2.0)
    excited = np.r_[np.full(20, -2.0), np.full(80, 2.0)]
    report = module.evaluate_reference_axis(axis, ground, excited)
    assert report["false_ground"] == 0.20
    assert report["valid"] is False


def test_post_references_score_pre_axis_without_refitting():
    module = experiment()
    g = [module.PairedIQ(-2, 0, -2, 0)] * 100
    e = [module.PairedIQ(2, 0, -2, 0)] * 100
    final_e = [module.PairedIQ(-2, 0, 2, 0)] * 100
    axes = module.calibrate_pair(g, e, final_e)
    post_e = [module.PairedIQ(-2, 0, -2, 0)] * 20 + e[:80]
    report = module.validate_pair_against_axes(axes, g, post_e, final_e)
    assert report["herald"]["false_ground"] == 0.20
    assert report["valid"] is False


def test_failed_herald_holdout_can_be_flagged_without_discarding_raw_science():
    module = experiment()
    ground = [module.PairedIQ(-5, 0, -5, 0)] * 400
    even = [-4] * 10 + [-1] * 15 + [2] * 175
    odd = [-4] * 2 + [-1] * 8 + [2] * 190
    first_e = [module.PairedIQ(value, 0, -5, 0)
               for pair in zip(even, odd) for value in pair]
    final_e = [module.PairedIQ(-5, 0, 2, 0)] * 400
    with pytest.raises(RuntimeError, match="independent herald reference rejected"):
        module.calibrate_pair(ground, first_e, final_e)
    axes = module.calibrate_pair(ground, first_e, final_e,
                                 enforce_holdout=False)
    assert axes["herald"]["fidelity"] > 0.9
    assert any(not report["valid"] for report in axes["herald_holdout"])
    assessment = module.assess_pre_references(ground, first_e, final_e)
    assert assessment["axes"] is not None
    assert assessment["valid"] is False
    assert assessment["error"] is None


def test_final_readout_failure_invalidates_every_conditional_arm_summary():
    module = experiment()
    arms = [{"name": "hot_on_g", "summary": {
        "final_excited_given_ground": 0.7,
        "interpretation_valid": True}},
        {"name": "cold_on_g", "summary": {
            "final_excited_given_ground": 0.2,
            "interpretation_valid": True}}]
    module.finalize_arm_summaries(arms, controls_valid=False)
    assert all(a["summary"]["interpretation_valid"] is False for a in arms)
    assert all(a["summary"]["final_excited_given_ground"] is None for a in arms)


def test_excited_references_prepare_after_each_flux_return():
    module = experiment()
    refs = {a["name"]: a for a in module.reference_arms(4.124, phase="pre")}
    assert refs["ref_e_pre"]["pump_prepare_after_return"] is True
    assert refs["ref_final_e_pre"]["probe_prepare_after_return"] is True
    assert all(a["pump_prepare_after_return"] and a["probe_prepare_after_return"]
               for a in refs.values())
    assert all(not a["pump_prepare_after_return"] and
               not a["probe_prepare_after_return"]
               for a in module.science_arms(center_ghz=4.124, flank_ghz=4.110))

    program = object.__new__(module.HeraldedPumpProbeProgram)
    program.cfg = {"qubit_ch": 1, "ff_gain": -17000,
                   "opx_herald_probe_gain": -17000,
                   "opx_herald_pump_state": "e", "opx_herald_probe_state": "e",
                   "opx_herald_pump_us": 0.1, "opx_herald_probe_us": 0.1,
                   "opx_herald_pump_prepare_after_return": True,
                   "opx_herald_probe_prepare_after_return": True}
    program.reset_config = SimpleNamespace(read_delay_us=10.0,
                                           inter_shot_delay_us=500.0)
    program.reset_page, program.reset_regs = 0, {"i": 1, "q": 2, "address": 3}
    events = []
    program._shot_park_callbacks = lambda: (lambda: None, lambda: None)
    program._set_payload_pulse = lambda **kw: events.append(("prep_gain", kw.get("gain")))
    program.pulse = lambda **_: None
    program._wait_t1_payload = lambda us: events.append(("excursion", us))
    program._measure_raw = lambda: events.append("readout")
    program.memw = program.mathi = lambda *_: None
    program.us2cycles = lambda us, **_: us
    program.sync_all = lambda *_: None
    program._emit_body()
    assert events == [("prep_gain", 0), ("excursion", 0.1),
                      ("prep_gain", None), "readout",
                      ("prep_gain", 0), ("excursion", 0.1),
                      ("prep_gain", None), "readout"]


def test_two_mhz_feature_shift_marks_run_uncertain():
    module = experiment()
    assert module.feature_stability({"center_ghz": 4.134},
                                    {"center_ghz": 4.135})["stable"] is True
    shifted = module.feature_stability({"center_ghz": 4.134},
                                       {"center_ghz": 4.136})
    assert shifted == {"center_shift_mhz": 2.0, "stable": False}
