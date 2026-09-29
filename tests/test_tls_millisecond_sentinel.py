"""Experiment-only contracts for q3's time-resolved loss-flank sentinel."""

import importlib

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSMillisecondSentinel"


def subject():
    return importlib.import_module(MODULE)


def wide_rows(*, second=True):
    rows = []
    for index in range(251):
        ghz = round(3.8 + .002 * index, 3)
        survival = .83
        for center, depth in ((4.094, .31), (4.132, .23) if second else (5.0, 0)):
            survival -= depth / (1 + ((ghz - center) / .0025) ** 2)
        row = {"target_frequency_ghz": str(ghz)}
        for suffix in ("", "_scan_up", "_scan_down"):
            row.update({f"P0{suffix}": ".1", f"P1{suffix}": ".9",
                        f"Ps_25us{suffix}": str(.1 + .8 * survival)})
        rows.append(row)
    return rows


def test_site_selector_finds_two_separated_lines_and_clean_control():
    selected = subject().select_sites(wide_rows())
    assert selected["A"]["center_ghz"] == pytest.approx(4.094)
    assert selected["B"]["center_ghz"] == pytest.approx(4.132)
    assert abs(selected["A"]["center_ghz"] - selected["B"]["center_ghz"]) >= .020
    assert selected["C"]["center_ghz"] == pytest.approx(4.060)
    assert selected["C"]["min_survival"] >= .75


def test_site_selector_stops_without_second_line_or_complete_scout():
    with pytest.raises(ValueError, match="second"):
        subject().select_sites(wide_rows(second=False))
    with pytest.raises(ValueError, match="251-point"):
        subject().select_sites(wide_rows()[:-1])


def test_quiet_control_survives_one_directional_low_outlier():
    model = subject()
    rows = wide_rows()
    # A single direction's low-count outlier should not veto an otherwise
    # flat 11-frequency control window.
    row = next(row for row in rows if float(row["target_frequency_ghz"]) == 4.060)
    row["Ps_25us_scan_up"] = str(.1 + .8*.65)
    selected = model.select_sites(rows)
    assert selected["C"]["center_ghz"] == pytest.approx(4.060)
    assert len(model.select_null_sites(rows, selected)) == 3


def test_site_selector_allows_two_mhz_directional_minimum_shift():
    rows = wide_rows()
    # On a bidirectional scan, the same broad line may have its lowest
    # directional bin one grid point away while combined loss stays centered.
    center = next(row for row in rows
                  if float(row["target_frequency_ghz"]) == 4.132)
    right = next(row for row in rows
                 if float(row["target_frequency_ghz"]) == 4.134)
    center["Ps_25us_scan_down"] = str(.1 + .8*.64)
    right["Ps_25us_scan_down"] = str(.1 + .8*.62)
    selected = subject().select_sites(rows)
    assert selected["A"]["center_ghz"] == pytest.approx(4.094)
    assert selected["B"]["center_ghz"] == pytest.approx(4.132)


def test_static_profile_recovers_center_width_and_signed_flanks():
    model = subject()
    frequency_mhz = np.arange(4088., 4102.1, 2.)
    survival = .86 - .35 / (1 + ((frequency_mhz - 4094.7) / 2.3) ** 2)
    fit = model.fit_static_profile(frequency_mhz, survival)
    assert fit["center_mhz"] == pytest.approx(4094.7, abs=.15)
    assert fit["hwhm_mhz"] == pytest.approx(2.3, abs=.2)
    assert fit["contrast_6mhz"] >= .15
    assert model.profile_gate(fit)["passed"] is True
    flanks = model.make_flanks(fit)
    assert flanks["A_minus_mhz"] == pytest.approx(4094.7 - 2.3 / np.sqrt(3), abs=.2)
    assert flanks["A_plus_mhz"] == pytest.approx(4094.7 + 2.3 / np.sqrt(3), abs=.2)
    assert flanks["slope_minus_per_mhz"] < 0 < flanks["slope_plus_per_mhz"]


def test_static_profile_gate_rejects_weak_contrast():
    model = subject()
    frequency_mhz = np.arange(4088., 4102.1, 2.)
    survival = .80 - .04 / (1 + ((frequency_mhz - 4094.7) / 2.3) ** 2)
    fit = model.fit_static_profile(frequency_mhz, survival)
    assert model.profile_gate(fit)["passed"] is False


def test_profile_gate_uses_measured_scan_edges_when_fit_center_moves_one_bin():
    model = subject()
    frequency = np.arange(4106., 4118.1, 2.)
    # Seven actual scanner bins remain the measurement, even if fitting
    # places the continuous center between the last two interior bins.
    survival = np.array([.577, .629, .353, .265, .278, .285, .466])
    fit = model.fit_static_profile(frequency, survival)
    assert 4113. < fit["center_mhz"] < 4114.
    assert fit["measured_contrast_6mhz"] >= .15
    assert model.profile_gate(fit)["passed"] is True


def test_static_profile_gate_uses_measured_not_only_fitted_contrast():
    model = subject()
    profile = {"contrast_6mhz": .25, "measured_contrast_6mhz": .08,
               "hwhm_mhz": 2., "fit_rmse": .015,
               "center_mhz": 4094., "profile_min_mhz": 4088.,
               "profile_max_mhz": 4100.}
    assert model.profile_gate(profile)["passed"] is False


def test_pooled_dither_gate_accepts_noisy_chunks_with_strong_aggregate():
    model = subject()
    reports = []
    for index in range(12):
        sign = 1 if index % 2 else -1
        reports.append({"readout_score": {"valid": True},
                        "fractions": {"A_minus_m": .5 + sign*.03,
                                      "A_minus_p": .4 + sign*.03,
                                      "A_plus_m": .4 + sign*.03,
                                      "A_plus_p": .5 + sign*.03,
                                      "B_m": .5 + sign*.03,
                                      "B_p": .4 + sign*.03}})
    result = model.pooled_dither_gate(reports, shots_per_calibration=100)
    assert result["valid"] is True
    assert result["slopes_per_mhz"]["A_minus"] == pytest.approx(.1)


def test_host_clock_marks_same_poll_burst_unresolved():
    model = subject()
    times = iter([5_000_000, 10_000_000, 10_000_500, 15_000_000,
                  20_000_000])
    clock = model.ShotClock(5, wall_start_ns=0, monotonic_start_ns=0,
                            now_ns=lambda: next(times))
    for done in range(1, 6):
        clock(done, 5)
    report = clock.finish()
    assert report["median_shot_period_ns"] == pytest.approx(5_000_000,
                                                               abs=1000)
    assert report["valid"][1:3] == [False, False]


def test_dac_targets_keep_sub_mhz_offsets_integer_and_bounded():
    model = subject()
    def fake_inverse(mhz):
        return -18000 + (mhz - 4094.0) * 40
    targets = model.integer_dac_targets(
        {"A_minus": 4093.4, "A_plus": 4096.0}, fake_inverse)
    assert targets["A_minus"]["gain_dac"] == -18024
    assert targets["A_minus"]["dither_minus_dac"] == -20
    assert targets["A_minus"]["dither_plus_dac"] == 20
    assert isinstance(targets["A_plus"]["gain_dac"], int)


def test_science_conditions_are_palindromic_and_keep_matching_dwells():
    model = subject()
    targets = {name: {"target_mhz": frequency, "gain_dac": gain}
               for name, frequency, gain in (("A_minus", 4093.4, -18024),
                                             ("A_plus", 4096.0, -17920),
                                             ("B", 4130.7, -16532),
                                             ("C", 4060.0, -19360))}
    arms = model.sentinel_conditions(targets)
    assert [arm["site"] for arm in arms] == [
        "A_minus", "A_plus", "B", "C", "C", "B", "A_plus", "A_minus"]
    assert [arm["position"] for arm in arms] == list(range(8))
    assert all(arm["state"] == "e" and arm["hold_us"] == 25.0 for arm in arms)
    assert arms[0]["gain_dac"] == arms[-1]["gain_dac"] == -18024


def test_completed_shot_clock_retains_real_gaps_and_rejects_duplicate_poll_times():
    model = subject()
    ticks = iter((1000000, 6000000, 11000000, 11000000, 25000000))
    clock = model.ShotClock(5, wall_start_ns=1000000000000,
                            monotonic_start_ns=0, now_ns=lambda: next(ticks))
    for count in range(1, 6):
        clock(count, 5)
    result = clock.finish()
    assert result["observed_utc_ns"][0] == 1000001000000
    assert result["observed_utc_ns"][-1] == 1000025000000
    assert result["valid"][3] is False
    assert result["gap_after_previous"][4] is True
    assert result["median_shot_period_ns"] == pytest.approx(5000000)
    with pytest.raises(ValueError, match="incomplete"):
        model.ShotClock(2, wall_start_ns=0, monotonic_start_ns=0,
                        now_ns=lambda: 1).finish()


def test_qick_program_has_eight_records_and_saves_one_boundary_per_shot(monkeypatch):
    model = subject()
    captured = {}
    monkeypatch.setattr(model.swap.SwapHoldProgram, "__init__",
                        lambda _self, _soc, cfg, _payload, _loop: captured.update(cfg))
    cfgs = [{"ff_gain": -18000 + 20 * i, "ff_park_gain": -25146,
             "shots": 10, "reps": 10, "opx_swap_hold_us": 25.0,
             "opx_resident_preparation_state": "e"} for i in range(8)]
    program = model.SentinelProgram(None, cfgs, None, None)
    assert captured["reps"] == 80
    assert program.logical_shots == 10
    assert program.conditions_per_shot == 8


def test_dump_reset_is_emitted_only_after_readout(monkeypatch):
    model = subject()
    program = object.__new__(model.SentinelProgram)
    program.cfg = {"ff_gain": -18000, "qubit_ch": 1,
                   "opx_resident_preparation_state": "e",
                   "opx_resident_reference_state": None}
    program.reset_config = type("Config", (), {"inter_shot_delay_us": 0})()
    program.reset_page = 0
    program.reset_regs = {"i": 1, "q": 2, "address": 3}
    events = []
    program._shot_park_callbacks = lambda: (lambda: None, lambda: None)
    program._set_payload_pulse = lambda **kw: events.append("prepare")
    program._resident_excursion = lambda: events.append("visit")
    program._measure_raw = lambda: events.append("measure")
    program.memw = program.mathi = lambda *_: None
    program._wait_t1_payload = lambda us: events.append(("dump", us, program.cfg["ff_gain"]))
    program.sync_all = lambda *_: None
    program.us2cycles = lambda us: us
    monkeypatch.setattr(model, "_pulse_pi_and_align", lambda _p: None)
    program.reset_mode = "dump"
    program.dump_gain_dac = -17000
    program._emit_body()
    assert events.index("measure") < events.index(("dump", 60.0, -17000))
    assert program.cfg["ff_gain"] == -18000


def test_profile_has_seven_sites_plus_control_and_reverses_order():
    model = subject()
    target = {"target_mhz": 4060.0, "gain_dac": -19000}
    forward = model.profile_conditions(4094.0, target,
                                       inverse_gain=lambda f: -18000 + 40*(f-4094),
                                       reverse=False)
    reverse = model.profile_conditions(4094.0, target,
                                       inverse_gain=lambda f: -18000 + 40*(f-4094),
                                       reverse=True)
    assert len(forward) == 8
    assert [arm["target_mhz"] for arm in forward[:7]] == [
        4088., 4090., 4092., 4094., 4096., 4098., 4100.]
    assert forward[-1]["site"] == "C"
    assert [arm["name"] for arm in reverse] == [arm["name"] for arm in reversed(forward)]


def test_calibration_dithers_all_three_flanks_and_brackets_readout():
    model = subject()
    targets = {site: {"target_mhz": f, "gain_dac": gain,
                      "dither_minus_dac": -20, "dither_plus_dac": 20}
               for site, f, gain in (("A_minus", 4093.4, -18024),
                                     ("A_plus", 4096.0, -17920),
                                     ("B", 4130.7, -16532),
                                     ("C", 4060.0, -19360))}
    cal = model.calibration_conditions(targets)
    assert [arm["name"] for arm in cal] == [
        "A_minus_m", "A_minus_p", "A_plus_m", "A_plus_p",
        "B_m", "B_p", "ref_g", "ref_e"]
    assert cal[0]["gain_dac"] == -18044
    assert cal[5]["gain_dac"] == -16512
    assert cal[-1]["reference_state"] == "e"


def test_null_sites_are_quiet_and_distinct_from_science_sites():
    model = subject()
    selected = model.select_sites(wide_rows())
    nulls = model.select_null_sites(wide_rows(), selected)
    assert len(nulls) == 3
    assert len(set(nulls.values())) == 3
    for value in nulls.values():
        assert abs(value-selected["A"]["center_ghz"]) >= .010
        assert abs(value-selected["B"]["center_ghz"]) >= .010
        assert abs(value-selected["C"]["center_ghz"]) >= .010


def test_null_window_excludes_a_stray_loss_eight_mhz_away():
    model = subject()
    rows = wide_rows()
    for target in (3.906, 3.908, 3.910):
        stray = next(row for row in rows if float(row["target_frequency_ghz"]) == target)
        for suffix in ("", "_scan_up", "_scan_down"):
            stray[f"Ps_25us{suffix}"] = ".42"
    selected = model.select_sites(rows)
    nulls = model.select_null_sites(rows, selected)
    assert all(abs(ghz-3.908) >= .010-1e-9 for ghz in nulls.values())


def test_failed_lorentzian_fit_is_a_recorded_gate_not_a_hardware_failure():
    model = subject()
    result = model.fit_or_reject_profile([4088., 4090., 4092., 4094.,
                                          4096., 4098., 4100.],
                                         [float("nan")]*7)
    assert result["gate"]["passed"] is False
    assert "finite" in result["gate_error"]


def test_chunk_saves_raw_iq_by_shot_and_nonuniform_host_times(tmp_path):
    model = subject()
    records = [model.resident.SingleIQ(i, -i) for i in range(8*3)]
    ticks = iter((5_000_000, 10_000_000, 30_000_000))
    def fake_acquire(_soc, _program, _timeout, _cfg, *, total_shots, progress):
        assert total_shots == 3
        for done in (1, 2, 3):
            progress(done, 3)
        return records
    path = tmp_path / "chunk.npz"
    result = model.acquire_chunk(None, object(), {}, shots=3, path=path,
                                 order=[f"x{i}" for i in range(8)],
                                 run_program=fake_acquire,
                                 wall_start_ns=1_000_000_000,
                                 monotonic_start_ns=0,
                                 now_ns=lambda: next(ticks))
    data = np.load(path)
    assert data["iq"].shape == (3, 8, 2)
    assert data["observed_utc_ns"].tolist() == [1_005_000_000,
                                                 1_010_000_000, 1_030_000_000]
    assert data["gap_after_previous"].tolist() == [False, False, True]
    assert result["timing_method"].startswith("host progress")


def test_plan_is_hardware_free_and_default_reset_is_passive(capsys):
    model = subject()
    assert model.main(["--plan"]) == 0
    import json
    info = json.loads(capsys.readouterr().out)
    assert info["reset_mode"] == "passive"
    assert info["science_chunks"] == 12
    assert info["null_chunks"] == 3
    assert info["conditions_per_shot"] == 8
    assert info["hardware_access"] is False


def test_failed_site_gate_retains_scout_manifest_before_hardware(monkeypatch, tmp_path):
    model = subject()
    correction = tmp_path / "correction.json"
    correction.write_text("{}")
    scout = tmp_path / "scout.csv"
    scout.write_text("header\n")
    monkeypatch.setattr(model.localizer, "checked_correction",
                        lambda _root, _path: correction)
    monkeypatch.setattr(model.localizer, "run", lambda **_kw: scout)
    monkeypatch.setattr(model.swap, "read_wide_scout", lambda _path: wide_rows(second=False))
    manifest_path = model.run(data_root=tmp_path, correction_json=correction)
    import json
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "stopped_site_gate"
    assert manifest["pre_scout_csv"] == str(scout)
    assert "second" in manifest["gate_error"]
