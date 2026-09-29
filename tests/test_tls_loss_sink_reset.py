"""A loss sink must cool e without heating g or hiding site drift."""

import importlib

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSLossSinkReset"


def experiment():
    return importlib.import_module(MODULE)


def scout_rows(*, early_loss=True):
    rows = []
    for index in range(251):
        frequency = round(3.8 + .002 * index, 3)
        late, early = .82, .91
        if frequency == 4.094:
            late, early = .28, .48 if early_loss else .88
        elif frequency in (4.092, 4.096):
            late, early = .53, .70 if early_loss else .89
        elif frequency == 4.276:
            late, early = .20, .73
        elif frequency in (4.274, 4.278):
            late, early = .48, .80
        values = {"target_frequency_ghz": str(frequency)}
        for suffix in ("", "_scan_up", "_scan_down"):
            values.update({f"P0{suffix}": ".1", f"P1{suffix}": ".9",
                           f"Ps_10us{suffix}": str(.1 + .8 * early),
                           f"Ps_25us{suffix}": str(.1 + .8 * late)})
        rows.append(values)
    return rows


def test_selects_early_loss_even_in_previously_excluded_band():
    selected = experiment().select_reset_candidate(scout_rows())
    assert selected["center_ghz"] == pytest.approx(4.094)
    assert selected["control_ghz"] == pytest.approx(4.108)
    assert selected["early_advantage"] > .30


def test_selector_requires_early_loss_not_only_deep_25us_trough():
    selected = experiment().select_reset_candidate(scout_rows(early_loss=False))
    assert selected["center_ghz"] == pytest.approx(4.276)
    with pytest.raises(ValueError, match="complete 251-point"):
        experiment().select_reset_candidate(scout_rows()[:-1])


def test_schedule_pairs_sites_preparations_and_two_dwells_per_shot():
    module = experiment()
    specs = module.program_specs(4.094, 4.108)
    assert len(specs) == 12
    assert [s["hold_us"] for s in specs[:6]] == [2, 5, 10, 20, 40, 60]
    assert [s["hold_us"] for s in specs[6:]] == [60, 40, 20, 10, 5, 2]
    assert all(s["shots"] == 800 and len(s["conditions"]) == 8 for s in specs)
    first = specs[0]["conditions"]
    assert {(c["site"], c["hold_us"], c["state"]) for c in first} == {
        (site, hold, state)
        for site in ("feature", "control") for hold in (.1, 2)
        for state in ("g", "e")}
    assert specs[-1]["order"] == list(reversed(specs[0]["order"]))


def test_score_distinguishes_cooling_from_ground_state_heating():
    module = experiment()
    fractions = {
        "feature_early_g": .10, "feature_early_e": .70,
        "control_early_g": .10, "control_early_e": .70,
        "feature_late_g": .12, "feature_late_e": .20,
        "control_late_g": .10, "control_late_e": .60,
    }
    score = module.score_reset(fractions)
    assert score["extra_excited_cooling"] == pytest.approx(.40)
    assert score["extra_ground_heating"] == pytest.approx(.02)
    assert score["cold_sink_candidate"] is True
    fractions["feature_late_g"] = .40
    heated = module.score_reset(fractions)
    assert heated["extra_excited_cooling"] == pytest.approx(.40)
    assert heated["cold_sink_candidate"] is False


def test_incremental_cooling_subtracts_short_hold_site_offset():
    fractions = {
        "feature_early_g": .10, "feature_early_e": .60,
        "control_early_g": .10, "control_early_e": .70,
        "feature_late_g": .12, "feature_late_e": .20,
        "control_late_g": .10, "control_late_e": .60,
    }
    score = experiment().score_reset(fractions)
    assert score["extra_excited_cooling"] == pytest.approx(.40)
    assert score["incremental_excited_cooling"] == pytest.approx(.30)


def test_science_specs_compile_through_existing_eight_arm_program(monkeypatch):
    module = experiment()
    entry = module.program_specs(4.094, 4.108)[-1]
    configs = module.confirm._condition_configs(
        {"sigma": .2, "ff_park_gain": -25146}, entry,
        {4.094: -15878, 4.108: -16111})
    assert {cfg["opx_swap_hold_us"] for cfg in configs} == {.1, 2.0}
    assert {cfg["ff_gain"] for cfg in configs} == {-15878, -16111}
    seen = []
    monkeypatch.setattr(module.resident.ResidentDriveProgram, "__init__",
                        lambda self, soccfg, cfg, payload, loop:
                        seen.append(dict(cfg)))
    program = module.confirm.EightSiteSwapHoldProgram(
        None, configs, None, None)
    assert program.conditions_per_shot == 8
    assert seen[0]["reps"] == 6400


def test_plan_is_hardware_free_and_reports_full_return(capsys):
    module = experiment()
    assert module.main(["--plan"]) == 0
    import json
    plan = json.loads(capsys.readouterr().out)
    assert plan["hardware_access"] is False
    assert plan["conditions_per_shot"] == 8
    assert plan["programs"] == 12
    assert plan["full_return_before_readout_us"] == 40.0
