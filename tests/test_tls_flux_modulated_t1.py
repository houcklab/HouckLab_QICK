"""Contracts for an interleaved AC-flux loss comparison at q3."""

import importlib

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFluxModulatedT1"


def experiment():
    return importlib.import_module(MODULE)


def test_six_microsecond_waveform_follows_the_corrected_dc_bias():
    module = experiment()
    waveform, report = module.compensated_ac_waveform(
        segments=[(1.0, 2.0), (0.98, 4.0)],
        park_gain=-25000, target_gain=-17000,
        amplitude_gain=800, modulation_mhz=30.0,
        sample_rate_mhz=6880.0, fabric_rate_mhz=430.0,
        cycles=2580, max_gain=32767)
    assert waveform.dtype == np.int16
    assert len(waveform) == 41280
    assert waveform[0] == -17000
    assert int(waveform[3 * 6880]) == -17160
    assert report["cycles_per_waveform"] == 180
    assert report["actual_modulation_mhz"] == pytest.approx(30.0)
    assert report["dc_level_count"] == 2


def test_ac_waveform_rejects_dac_clipping():
    module = experiment()
    with pytest.raises(ValueError, match="DAC range"):
        module.compensated_ac_waveform(
            segments=[(1.0, 6.0)], park_gain=-25000,
            target_gain=-32000, amplitude_gain=1600,
            modulation_mhz=30.0, sample_rate_mhz=6880.0,
            fabric_rate_mhz=430.0, cycles=2580, max_gain=32767)


def test_conditions_put_short_and_long_on_off_hot_cold_in_each_shot():
    module = experiment()
    forward = module.conditions(4.136, amplitude_dac=1600)
    reverse = module.conditions(4.136, amplitude_dac=1600, reverse=True)
    assert len(forward) == 8
    assert {x["name"] for x in forward} == {
        f"{hold}_{drive}_{state}" for hold in ("short", "long")
        for drive in ("off", "on") for state in ("g", "e")}
    assert [x["name"] for x in reverse] == [x["name"] for x in reversed(forward)]
    assert all(x["modulation_amplitude_dac"] == 0 for x in forward
               if "_off_" in x["name"])
    assert all(x["modulation_amplitude_dac"] == 1600 for x in forward
               if "_on_" in x["name"])


def test_effect_subtracts_early_pulse_artifact_and_flank_change():
    module = experiment()
    def row(short_off, short_on, long_off, long_on):
        return {f"{hold}_{drive}_{state}": value
                for hold, drive, g, e in (
                    ("short", "off", 0.1, short_off+0.1),
                    ("short", "on", 0.1, short_on+0.1),
                    ("long", "off", 0.1, long_off+0.1),
                    ("long", "on", 0.1, long_on+0.1))
                for state, value in (("g", g), ("e", e))}
    feature = module.score_conditions(row(.25, .23, .12, .20))
    flank = module.score_conditions(row(.40, .38, .38, .36))
    assert feature["modulation_survival_change"] == pytest.approx(.10)
    assert flank["modulation_survival_change"] == pytest.approx(0.0)
    assert module.feature_specific_effect(feature, flank) == pytest.approx(.10)


def test_plan_uses_matched_return_and_within_shot_controls():
    plan = experiment().plan()
    assert plan["modulation_amplitudes_dac"] == [800, 1600]
    assert plan["holds_us"] == [0.1, 6.0]
    assert plan["conditions_per_shot"] == 8
    assert plan["programs"] == 8
    assert plan["full_return_before_readout_us"] == 40.0


def test_park_ramps_and_both_ac_holds_fit_the_q3_envelope_memory():
    plan = experiment().plan()
    # q3's FF generator has 6,881.28 samples/us and 65,536 samples total.
    requested = (2 * plan["park_ramp_us"] + sum(plan["holds_us"])) * 6881.28
    assert requested < 65536


def test_focused_specs_use_only_calibrated_high_amplitude_and_retrack_second_pair():
    module = experiment()
    specs = module.program_specs(4.131, amplitudes=(1600,), shots=8000)
    assert [s["name"] for s in specs] == [
        "r0_feature_a1600", "r0_flank_a1600",
        "r1_flank_a1600", "r1_feature_a1600"]
    assert [s["flux_ghz"] for s in specs] == [4.131, 4.117, 4.117, 4.131]
    assert all(s["shots"] == 8000 for s in specs)
    module.recenter_repeat(specs, center=4.127, repeat=1)
    assert [s["flux_ghz"] for s in specs] == [4.131, 4.117, 4.113, 4.127]
    for spec in specs[2:]:
        assert {c["flux_ghz"] for c in spec["conditions"]} == {spec["flux_ghz"]}
        assert [c["name"] for c in spec["conditions"]] == spec["order"]


def test_focused_block_stability_requires_each_pair_to_stay_near_its_own_scout():
    module = experiment()
    pre = {"center_ghz": 4.131, "depth": 0.3}
    mid = {"center_ghz": 4.127, "depth": 0.3}
    post = {"center_ghz": 4.127, "depth": 0.3}
    assert module.block_stability(pre, mid, post) == {
        "r0": False, "r1": True}


def test_focused_plan_halves_programs_and_scans_between_pairs():
    plan = experiment().plan(focused=True)
    assert plan["modulation_amplitudes_dac"] == [1600]
    assert plan["programs"] == 4
    assert plan["shots_per_program"] == 8000
    assert plan["midpoint_feature_scout"] is True


def test_direct_floquet_plan_visits_loss_without_long_unmodulated_predwell():
    module = experiment()
    plan = module.plan(floquet_direct=True)
    assert plan["site"] == "fresh 3.992-GHz loss feature and clean upper flank"
    assert plan["holds_us"] == [1.6, 5.6]
    assert plan["pre_target_hold_us"] == pytest.approx(.05)
    assert plan["modulation_amplitudes_dac"] == [1000, 1600]
    assert plan["programs"] == 8
    assert plan["midpoint_feature_scout"] is True
    assert (2 * plan["park_ramp_us"] + sum(plan["holds_us"])) * 6881.28 < 65536


def test_direct_floquet_specs_use_upper_flank_and_retarget_repeat():
    module = experiment()
    specs = module.program_specs(
        3.992, amplitudes=(1000, 1600), shots=6000,
        control_ghz=4.006, holds_us=(1.6, 5.6), pre_us=.05)
    assert len(specs) == 8
    assert [s["flux_ghz"] for s in specs] == [
        3.992, 3.992, 4.006, 4.006,
        4.006, 4.006, 3.992, 3.992]
    for spec in specs:
        expected = ([1.6] * 4 + [5.6] * 4 if spec["repeat"] == 0 else
                    [5.6] * 4 + [1.6] * 4)
        assert [c["post_drive_us"] for c in spec["conditions"]] == expected
    assert all(c["pre_drive_us"] == .05 for s in specs
               for c in s["conditions"])
    module.recenter_repeat(
        specs, center=3.994, control_ghz=4.008, repeat=1,
        holds_us=(1.6, 5.6), pre_us=.05)
    assert [s["flux_ghz"] for s in specs[4:]] == [4.008, 4.008, 3.994, 3.994]


def test_direct_floquet_waveforms_follow_early_changing_correction():
    module = experiment()
    waveform, report = module.compensated_ac_waveform(
        segments=[(1.025, 5504/6881.28), (1.035, 5504/6881.28)],
        park_gain=-25146, target_gain=-16000,
        amplitude_gain=1000, modulation_mhz=30.0,
        sample_rate_mhz=6881.28, fabric_rate_mhz=430.08,
        cycles=688, max_gain=32767)
    assert report["cycles_per_waveform"] == 48
    assert len(waveform) == 11008
    assert waveform[0] == round(-25146 + 1.025 * 9146)
    # Half the 48-cycle waveform is exactly a zero crossing at the DC step.
    assert waveform[5504] == round(-25146 + 1.035 * 9146)
