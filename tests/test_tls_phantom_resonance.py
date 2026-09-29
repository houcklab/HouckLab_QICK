"""The square-hop pilot must distinguish a spectral line from its endpoints."""

import importlib
import json

import numpy as np
import pytest


phantom = importlib.import_module(
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPhantomResonance"
)


def _scout(*, occupied_endpoint=False):
    rows = []
    for mhz in range(3800, 4301, 2):
        survival = .85
        if abs(mhz - 4100) <= 2:
            survival = .30
        if abs(mhz - 4200) <= 2:
            survival = .35
        if occupied_endpoint and abs(mhz - 4180) <= 2:
            survival = .25
        row = {"target_frequency_ghz": f"{mhz / 1000:.3f}"}
        for suffix in ("", "_scan_up", "_scan_down"):
            row.update({"P0" + suffix: ".10", "P1" + suffix: ".90",
                        "Ps_10us" + suffix: str(.1 + .8 * survival),
                        "Ps_25us" + suffix: str(.1 + .8 * survival)})
        rows.append(row)
    return rows


def test_selector_rejects_a_line_with_loss_at_a_hop_endpoint():
    selected = phantom.select_candidate(_scout(occupied_endpoint=True))
    assert selected["center_ghz"] == pytest.approx(4.100)
    assert min(selected["endpoint_survival"].values()) >= .65


def test_selector_skips_ten_mhz_hop_when_that_endpoint_is_occupied():
    rows = _scout()
    for row in rows:
        if abs(float(row["target_frequency_ghz"]) - 4.110) <= .002001:
            for suffix in ("", "_scan_up", "_scan_down"):
                row["Ps_25us" + suffix] = str(.1 + .8 * .25)
    selected = phantom.select_candidate(rows)
    assert selected["center_ghz"] == pytest.approx(4.100)
    assert selected["eligible_amplitudes_mhz"] == [20, 40]


def test_selector_includes_ten_mhz_hop_when_both_endpoints_are_quiet():
    selected = phantom.select_candidate(_scout())
    assert selected["eligible_amplitudes_mhz"] == [10, 20, 40]


def test_stability_allows_two_scout_steps_of_recentered_line_motion():
    pre = {"center_ghz": 4.152, "depth": .18}
    moved = {"center_ghz": 4.156, "depth": .16}
    farther = {"center_ghz": 4.158, "depth": .16}
    assert phantom.site_stable(pre, moved)
    assert not phantom.site_stable(pre, farther)


def test_selector_rejects_a_slow_line_without_ten_microsecond_loss():
    rows = _scout()
    for row in rows:
        if abs(float(row["target_frequency_ghz"]) - 4.100) <= .002001:
            for suffix in ("", "_scan_up", "_scan_down"):
                row["Ps_10us" + suffix] = str(.1 + .8 * .84)
    selected = phantom.select_candidate(rows)
    assert selected["center_ghz"] == pytest.approx(4.200)
    assert selected["early_depth"] >= .1


def test_waveform_spends_equal_time_at_static_endpoints_and_never_commands_center():
    samples, report = phantom.square_waveform(
        pattern="hop20", segments=[(1.0, 1.6)], park_gain=0,
        center_gain=0, endpoint_gains={-40: -200, -20: -100, -10: -50,
                                       10: 50, 20: 100, 40: 200},
        sample_rate_mhz=1000, fabric_rate_mhz=250, cycles=400,
        max_gain=1000)
    assert len(samples) == 1600
    assert set(np.unique(samples)) == {-100, 100}
    assert np.count_nonzero(samples == -100) == 800
    assert np.count_nonzero(samples == 100) == 800
    assert report["full_cycles"] == 32
    assert report["actual_hop_mhz"] == pytest.approx(20)
    assert report["ideal_carrier_weight"] == pytest.approx(.4052847)
    ten, ten_report = phantom.square_waveform(
        pattern="hop10", segments=[(1.0, 1.6)], park_gain=0,
        center_gain=0, endpoint_gains={-40: -200, -20: -100, -10: -50,
                                       10: 50, 20: 100, 40: 200},
        sample_rate_mhz=1000, fabric_rate_mhz=250, cycles=400,
        max_gain=1000)
    assert set(np.unique(ten)) == {-50, 50}
    assert ten_report["ideal_carrier_weight"] == pytest.approx(.810569,
                                                                 abs=1e-6)


def test_static_waveform_uses_the_same_corrected_hold_as_square_waveform():
    kwargs = dict(segments=[(1.02, .8), (1.03, .8)], park_gain=-25000,
                  center_gain=-20000,
                  endpoint_gains={-40: -20700, -20: -20350,
                                  -10: -20175, 10: -19825,
                                   20: -19650, 40: -19300},
                  sample_rate_mhz=1000, fabric_rate_mhz=250, cycles=400,
                  max_gain=32767)
    center, _ = phantom.square_waveform(pattern="center", **kwargs)
    plus, _ = phantom.square_waveform(pattern="plus20", **kwargs)
    minus, _ = phantom.square_waveform(pattern="minus20", **kwargs)
    hop, _ = phantom.square_waveform(pattern="hop20", **kwargs)
    hop_reversed, _ = phantom.square_waveform(pattern="hop20",
                                              start_high=False, **kwargs)
    assert np.all(plus - center == np.where(np.arange(1600) < 800,
                                            357, 360))
    assert np.array_equal(hop[:25], plus[:25])
    assert np.all((hop == plus) | (hop == minus))
    assert np.all((hop_reversed == plus) | (hop_reversed == minus))
    assert np.array_equal(hop + hop_reversed, plus + minus)


def test_waveform_rejects_nonintegral_hops_and_dac_clipping():
    args = dict(pattern="hop20", segments=[(1.0, 1.6)],
                park_gain=0, center_gain=0,
                endpoint_gains={-40: -200, -20: -100, -10: -50,
                                10: 50, 20: 100, 40: 200},
                sample_rate_mhz=1000, fabric_rate_mhz=250,
                cycles=400, max_gain=1000)
    with pytest.raises(ValueError, match="whole square-wave cycles"):
        phantom.square_waveform(**{**args, "cycles": 390})
    with pytest.raises(ValueError, match="DAC range"):
        phantom.square_waveform(**{**args, "max_gain": 90})


def test_schedule_pairs_each_hop_with_center_and_reverses_order():
    specs = phantom.program_specs(4.100, shots=20)
    assert len(specs) == 24
    for repeat in (0, 1):
        group = [row for row in specs if row["repeat"] == repeat]
        assert {row["hold_us"] for row in group} == {.4, 3.6}
        assert {tuple(row["patterns"]) for row in group} == {
            ("center", "hop10"), ("minus10", "plus10"),
            ("center", "hop20"), ("minus20", "plus20"),
            ("center", "hop40"), ("minus40", "plus40")}
        for row in group:
            assert len(row["conditions"]) == 4
            assert len(set(row["order"])) == 4
            assert row["order"] == ([condition["name"] for condition in
                                      row["conditions"]])
    first = next(row for row in specs if row["repeat"] == 0 and
                 row["hold_us"] == .4 and row["patterns"] ==
                 ["center", "hop20"])
    second = next(row for row in specs if row["repeat"] == 1 and
                  row["hold_us"] == .4 and row["patterns"] ==
                  ["center", "hop20"])
    assert second["order"] == list(reversed(first["order"]))


def test_schedule_can_omit_occupied_ten_mhz_endpoint():
    specs = phantom.program_specs(4.100, shots=20, amplitudes=(20, 40))
    assert len(specs) == 16
    assert not any("10" in pattern for spec in specs
                   for pattern in spec["patterns"])


def test_score_uses_excess_decay_rate_above_quiet_endpoints():
    contrasts = {
        "center": {.4: .80, 3.6: .40},
        "minus10": {.4: .80, 3.6: .72},
        "plus10": {.4: .80, 3.6: .72},
        "hop10": {.4: .80, 3.6: .48},
        "minus20": {.4: .80, 3.6: .72},
        "plus20": {.4: .80, 3.6: .72},
        "hop20": {.4: .80, 3.6: .58},
        "minus40": {.4: .80, 3.6: .72},
        "plus40": {.4: .80, 3.6: .72},
        "hop40": {.4: .80, 3.6: .72},
    }
    report = phantom.score_contrasts(contrasts)
    assert report["hop10_excess"] > report["hop20_excess"]
    assert report["hop10_fraction_of_center"] > report["hop20_fraction_of_center"]
    assert report["center_excess"] == pytest.approx(.183683, abs=.00001)
    assert report["hop20_excess"] == pytest.approx(.067570, abs=.00001)
    assert report["hop20_fraction_of_center"] == pytest.approx(.36786,
                                                                abs=.0001)
    assert report["hop40_excess"] == pytest.approx(0)


def test_each_hop_fraction_uses_its_own_static_endpoint_background():
    contrasts = {pattern: {.4: .8, 3.6: long} for pattern, long in {
        "center": .4, "minus10": .68, "plus10": .68, "hop10": .48,
        "minus20": .72, "plus20": .72, "hop20": .58,
        "minus40": .76, "plus40": .76, "hop40": .70,
    }.items()}
    report = phantom.score_contrasts(contrasts)
    for amplitude in (10, 20, 40):
        background = report[f"background{amplitude}_per_us"]
        expected = report[f"hop{amplitude}_excess"] / (
            report["rates_per_us"]["center"] - background)
        assert report[f"hop{amplitude}_fraction_of_center"] == pytest.approx(
            expected)


def test_score_can_omit_ten_mhz_arms():
    contrasts = {pattern: {.4: .8, 3.6: .6} for pattern in
                 ("center", "minus20", "plus20", "hop20",
                  "minus40", "plus40", "hop40")}
    report = phantom.score_contrasts(contrasts)
    assert "hop10_excess" not in report
    assert "hop20_excess" in report


def test_program_rejects_a_missing_ground_or_excited_endpoint_arm():
    configs = []
    for pattern, state in (("center", "g"), ("center", "e"),
                           ("hop20", "g"), ("hop20", "g")):
        configs.append({"ff_gain": -18000, "ff_park_gain": -25146,
                        "opx_resident_pre_us": .05,
                        "opx_resident_post_us": 1.6,
                        "opx_resident_preparation_state": state,
                        "opx_resident_gain": 0,
                        "opx_phantom_pattern": pattern,
                        "shots": 20, "reps": 20})
    with pytest.raises(ValueError, match="pattern/preparation coverage"):
        phantom.PhantomProgram(None, configs, None, None,
                               endpoint_gains={-40: -18700, -20: -18350,
                                               -10: -18175, 10: -17825,
                                               20: -17650, 40: -17300})


def test_two_long_waveforms_fit_q3_generator_with_park_ramps():
    q3_sample_mhz = 6881.28
    q3_fabric_mhz = 430.08
    long_samples = round(3.6 * q3_fabric_mhz) * 16
    parked_ramps = 2 * 6880
    assert (2 * long_samples + parked_ramps) < 65536
    assert (2 * round(5.6 * q3_fabric_mhz) * 16 + parked_ramps) > 65536


def test_program_compiles_two_real_grid_waveforms_with_memory_guard(monkeypatch):
    monkeypatch.setattr(phantom.alternating.ShotAlternatingResidentProgram,
                        "_declare_experiment", lambda self: None)
    monkeypatch.setattr(phantom.modulated, "_target_segments",
                        lambda _correction, *, pre_us, hold_us, recovery_us:
                        ([(1.0, pre_us)], [(1.0, hold_us + .01)],
                         [(1.0, recovery_us)]))
    monkeypatch.setattr(phantom, "ff_maxv", lambda *_a, **_kw: 32767)
    monkeypatch.setattr(phantom, "ff_envelope_samples", lambda *_a: 65536)
    program = object.__new__(phantom.PhantomProgram)
    program.cfg = {"ff_ch": 0, "ff_gain": -15000,
                   "ff_park_gain": -25146, "opx_resident_post_us": 3.6}
    program.soccfg = {"gens": [{"fs": 6881.28, "f_fabric": 430.08}]}
    program.patterns = ("center", "hop20")
    program.endpoint_gains = {-40: -15700, -20: -15350,
                              -10: -15175, 10: -14825,
                              20: -14650, 40: -14300}
    program.start_high = True
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.
    program._ff_ramp_cache = {(0, "up", 0, 6880),
                              (0, "down", 0, 6880)}
    program.us2cycles = lambda hold, **_kw: round(hold * 430.08)
    added = []
    program.add_pulse = lambda **kw: added.append(kw)
    program._declare_experiment()
    assert {row["name"] for row in added} == {"q3_phantom_center",
                                              "q3_phantom_hop20"}
    assert program.ff_envelope_report["total_samples"] == 63296
    assert program.ff_envelope_report["total_samples"] < 65536
    assert program.waveform_reports["hop20"]["full_cycles"] == 72
    assert program.waveform_reports["hop20"]["commanded_center_samples"] == 0


def test_program_plays_square_hold_then_complete_corrected_return(monkeypatch):
    monkeypatch.setattr(phantom.modulated, "_target_segments",
                        lambda _correction, *, pre_us, hold_us, recovery_us:
                        ([(1.0, pre_us)], [(1.0, hold_us)],
                         [(1.0, recovery_us)]))
    events = []
    monkeypatch.setattr(phantom.ff_pulse,
                        "play_relative_compensation_segments",
                        lambda _program, _park, _target, segments:
                        events.append(("segments", segments)))
    monkeypatch.setattr(phantom.ff_pulse, "play_hard_step",
                        lambda _program, gain: events.append(("park", gain)))
    monkeypatch.setattr(phantom, "ff_maxv", lambda *_a, **_kw: 32767)
    program = object.__new__(phantom.PhantomProgram)
    program.cfg = {"ff_ch": 0, "ff_park_gain": -25146,
                   "ff_gain": -15000, "opx_resident_pre_us": .05,
                   "opx_resident_post_us": 3.6,
                   "opx_phantom_pattern": "hop20"}
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.
    program.set_pulse_registers = lambda **kw: events.append(("registers", kw))
    program.pulse = lambda **kw: events.append(("pulse", kw))
    program.sync_all = lambda *_a: events.append(("barrier",))
    program._resident_excursion()
    assert events[1][1]["waveform"] == "q3_phantom_hop20"
    assert events[-3] == ("segments", [(1.0, 40.)])
    assert events[-2] == ("park", -25146.)
    assert events[-1] == ("barrier",)


def test_plan_is_silent_hardware_free_and_declares_bounded_pilot(capsys):
    assert phantom.main(["--plan"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["hardware_access"] is False
    assert report["full_cycle_hop_mhz"] == 20
    assert report["holds_us"] == [.4, 3.6]
    assert report["patterns"] == list(phantom.PATTERNS)
    assert report["programs"] == 24
    assert report["commanded_peak_excursions_mhz"] == [10, 20, 40]
    assert report["delivered_square_wave_verified"] is False
