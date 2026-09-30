import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSEchoFocusedTrace as focused,
)


def test_sites_bracket_old_4212_peak_and_include_two_controls():
    assert {4.204, 4.208, 4.212, 4.216}.issubset(focused.SITES_GHZ)
    assert {4.232, 4.284}.issubset(focused.SITES_GHZ)
    assert len(focused.DELAYS_US) >= 6
    assert min(focused.DELAYS_US) < .3
    assert max(focused.DELAYS_US) > 1.8


def test_reverse_block_changes_site_delay_and_phase_order():
    first = focused.schedule(0)
    second = focused.schedule(1)
    assert first[0]["frequency_ghz"] == min(focused.SITES_GHZ)
    assert second[0]["frequency_ghz"] == max(focused.SITES_GHZ)
    assert first[0]["echo_arms"][0] == (min(focused.DELAYS_US), 0)
    assert second[0]["echo_arms"][0] == (max(focused.DELAYS_US), 270)


def test_local_one_pulse_turnover_gate_requires_half_and_twice_pi():
    assert focused.rabi_gate(.46, .04)["valid"]
    assert not focused.rabi_gate(.85, .04)["valid"]
    assert not focused.rabi_gate(.46, .7)["valid"]


def test_trace_report_fits_decay_but_flags_revival():
    delays = focused.DELAYS_US
    cycles = {delay: {0: .5 + .4 * math.exp(-delay),
                      90: .5, 180: .5 - .4 * math.exp(-delay),
                      270: .5} for delay in delays}
    report = focused.trace_report(cycles)
    assert report["rate_per_us"] == pytest.approx(1.)
    assert report["revival_count"] == 0
    cycles[delays[-1]] = {0: .8, 90: .5, 180: .2, 270: .5}
    assert focused.trace_report(cycles)["revival_count"] >= 1


def test_single_point_schedule_reverses_four_blocks_at_4284():
    assert focused.SINGLE_SITE_GHZ == 4.284
    assert focused.SINGLE_DELAYS_US[0] < .15
    assert focused.SINGLE_DELAYS_US[-1] >= 4.
    first = focused.schedule(0, sites=(4.284,),
                             delays=focused.SINGLE_DELAYS_US)
    last = focused.schedule(3, sites=(4.284,),
                            delays=focused.SINGLE_DELAYS_US)
    assert first[0]["echo_arms"][0] == (focused.SINGLE_DELAYS_US[0], 0)
    assert last[0]["echo_arms"][0] == (focused.SINGLE_DELAYS_US[-1], 270)


def test_short_echo_sentinel_requires_repeatable_visibility_and_phase():
    first = {0: .9, 90: .5, 180: .1, 270: .5}
    repeat = {0: .87, 90: .5, 180: .13, 270: .5}
    wrong = {0: .1, 90: .5, 180: .9, 270: .5}
    assert focused.short_echo_gate(first, repeat)["valid"]
    assert not focused.short_echo_gate(first, wrong)["valid"]


def test_single_point_plan_has_no_t1_scout_and_four_repeats():
    plan = focused.plan(single_point=True)
    assert plan["sites_ghz"] == [4.284]
    assert plan["reversed_blocks"] == 4
    assert plan["t1_scans"] is None


def test_single_point_source_requires_two_valid_4284_blocks():
    site = {"frequency_ghz": 4.284, "status": "valid_controls",
            "rabi_gate": {"valid": True}, "control_gate": {"valid": True},
            "trace": {"rate_per_us": .5}}
    source = {"schema": "q3.echo-focused-trace.v1", "status": "complete",
              "session_id": focused.SINGLE_SOURCE_SESSION,
              "code_commit": "f7c12262" + "0" * 32,
              "correction_sha256": focused.localizer.CORRECTION_SHA256,
              "blocks": [{"sites": [site]}, {"sites": [site]}]}
    focused.validate_single_point_source(source)
    source["blocks"][1] = {"sites": [{**site, "status": "unresolved_local_control"}]}
    with pytest.raises(ValueError):
        focused.validate_single_point_source(source)


def test_single_point_assessment_requires_repeated_consistent_echo():
    blocks = [{"sites": [{"status": "valid_controls",
                          "trace": {"status": "fit", "rate_per_us": rate,
                                    "log_fit_rms": .1, "revival_count": 0}}]}
              for rate in (.45, .49, .47, .46)]
    assert focused.assess_single_point(blocks)["repeatable"]
    blocks[2]["sites"][0]["trace"]["rate_per_us"] = 1.4
    assert not focused.assess_single_point(blocks)["repeatable"]


def test_one_over_e_crossing_accepts_repeatable_nonexponential_decay():
    delays = (.08, .5, 1.2, 1.8, 2.6, 4.)
    values = (1., .9, .84, .66, .39, .1)
    report = focused.one_over_e_crossing(dict(zip(delays, values)))
    assert report["valid"]
    assert 2.6 < report["time_us"] < 2.8
    rebound = focused.one_over_e_crossing(dict(zip(delays,
                                                 (1., .9, .3, .7, .2, .1))))
    assert not rebound["valid"]
    assert not focused.one_over_e_crossing(dict(zip(
        delays, (1., .9, .8, .7, .6, .5))))["valid"]


def test_local_map_plan_stays_small_and_brackets_validated_sites():
    plan = focused.plan(local_map=True)
    assert plan["sites_ghz"] == [4.280, 4.284, 4.288, 4.292, 4.296]
    assert plan["reversed_blocks"] == 3
    assert plan["t1_scans"] is None
    assert plan["metric"] == "interpolated 1/e echo visibility crossing"


def test_local_map_assessment_uses_crossings_not_exponential_fit():
    sites = focused.LOCAL_MAP_SITES_GHZ
    blocks = []
    for index, crossing in enumerate((2.5, 2.7, 2.6)):
        blocks.append({"index": index, "sites": [
            {"frequency_ghz": frequency, "status": "valid_controls",
             "trace": {"one_over_e": {"valid": True, "time_us": crossing},
                       "log_fit_rms": .4}}
            for frequency in sites]})
    report = focused.assess_local_map(blocks)
    assert report["resolved_sites"] == len(sites)
    assert report["sites"]["4.288"]["mean_crossing_us"] == pytest.approx(2.6)
    blocks[0]["sites"][2]["status"] = "unresolved_local_control"
    blocks[1]["sites"][2]["status"] = "unresolved_local_control"
    assert focused.assess_local_map(blocks)["sites"]["4.288"]["status"] == "unresolved"
    blocks[0]["sites"][2]["status"] = "valid_controls"
    blocks[1]["sites"][2]["status"] = "valid_controls"
    blocks[2]["sites"][2]["trace"]["one_over_e"]["time_us"] = 3.9
    assert focused.assess_local_map(blocks)["sites"]["4.288"]["status"] == "unresolved"


def test_population_schedule_pairs_each_echo_with_survival_and_reverses_all_arms():
    first = focused.population_schedule(0)
    second = focused.population_schedule(1)
    assert second == list(reversed(first))
    assert len(first) == 30
    for delay in (.08, .3, .5, .8, 1.2):
        arms = [arm for arm in first if arm[1] == delay]
        assert sorted(phase for kind, _, phase in arms if kind == "echo") == [0, 90, 180, 270]
        assert [kind for kind, _, _ in arms if kind != "echo"] == ["pop_g", "pop_e"]
    assert [arm[0] for arm in first[:6]] == ["pop_g", "pop_e"] + ["echo"] * 4
    assert [arm[0] for arm in first[6:12]] == ["echo"] * 4 + ["pop_g", "pop_e"]


@pytest.mark.parametrize("delay,post,hold", [(.08, .29, 30.3907), (1.2, 1.41, 31.5107)])
def test_population_pulse_keeps_full_rotation_and_matches_echo_total_visit(delay, post, hold):
    original = {"ff_hold": 99., "opx_resident_post_us": 99.}
    for kind, gain in (("pop_g", 0), ("pop_e", 30000)):
        cfg = focused.population_config(original, kind, delay)
        assert cfg["fast_pulse_us"] == pytest.approx(.0907)
        assert cfg["fast_second_phase_deg"] is None
        assert cfg["opx_resident_gain"] == gain
        assert cfg["opx_resident_post_us"] == pytest.approx(post)
        assert cfg["ff_hold"] == pytest.approx(hold)
        assert 30. + cfg["fast_pulse_us"] + .01 + cfg["opx_resident_post_us"] == pytest.approx(hold)
    assert original["ff_hold"] == 99.
    with pytest.raises(ValueError):
        focused.population_config(original, "pop_e", 1.8)


def test_population_correction_rejects_any_science_window_command_change():
    correction = {"segment_edges_ns": [0., 30000., 32000., 40000.],
                  "multipliers": [1.03, 1.02, 1.01, 1.]}
    report = focused.validate_population_correction(correction)
    assert report["window_start_us"] == pytest.approx(30.5)
    assert report["window_end_us"] == pytest.approx(31.9107)
    correction["segment_edges_ns"][2] = 31500.
    with pytest.raises(ValueError, match="constant"):
        focused.validate_population_correction(correction)


def test_population_benchmark_recovers_relative_relaxation_only_echo():
    delays = focused.POPULATION_DELAYS_US
    # Fixed preparation/readout factors cancel at the first delay. For T1=2 us,
    # population contrast decays twice as fast as relaxation-only coherence.
    populations = {delay: {"g": .1, "e": .1 + .9 * math.exp(-delay / 2.)}
                   for delay in delays}
    cycles = {delay: {0: .5 + .4 * math.exp(-delay / 4.), 90: .5,
                      180: .5 - .4 * math.exp(-delay / 4.), 270: .5}
              for delay in delays}
    report = focused.population_report(cycles, populations)
    assert report["valid"]
    row = report["by_delay_us"][1.2]
    assert row["population_contrast"] == pytest.approx(.9 * math.exp(-.6))
    assert row["relative_population_contrast"] == pytest.approx(math.exp(-.56))
    assert row["relative_echo_visibility"] == pytest.approx(math.exp(-.28))
    assert row["relaxation_only_echo_ratio"] == pytest.approx(math.exp(-.28))
    assert "gamma_phi" not in report


@pytest.mark.parametrize("short_contrast,last_contrast", [(.1, .7), (.9, -.1), (.9, math.nan)])
def test_population_benchmark_flags_weak_negative_or_nonfinite_contrast(short_contrast, last_contrast):
    delays = focused.POPULATION_DELAYS_US
    populations = {delay: {"g": .1, "e": .9} for delay in delays}
    populations[delays[0]]["e"] = .1 + short_contrast
    populations[delays[-1]]["e"] = .1 + last_contrast
    cycles = {delay: {0: .9, 90: .5, 180: .1, 270: .5} for delay in delays}
    report = focused.population_report(cycles, populations)
    assert not report["valid"]
    assert report["by_delay_us"][delays[-1]]["relaxation_only_echo_ratio"] is None


def test_population_plan_is_bounded_and_modes_reject_before_hardware_import(capsys):
    plan = focused.plan(population_check=True)
    assert plan["sites_ghz"] == [4.288]
    assert plan["delays_us"] == [.08, .3, .5, .8, 1.2]
    assert plan["shots_per_arm"] == 1600
    assert plan["reversed_blocks"] == 3
    assert plan["t1_scans"] is None
    for kwargs in ({"single_point": True}, {"local_map": True}):
        with pytest.raises(ValueError):
            focused.run(population_check=True, **kwargs)
    with pytest.raises(SystemExit) as exc:
        focused.main(["--run", "--local-map", "--population-check"])
    assert exc.value.code == 2
    assert focused.main(["--plan", "--population-check"]) == 0
    assert json.loads(capsys.readouterr().out)["sites_ghz"] == [4.288]


def test_acquisition_metadata_serializer_preserves_numpy_and_paths():
    value = {"path": Path("measured.json"), "gains": np.array([1, 2]),
             "time": np.float64(.08), "missing": np.float64(math.nan),
             "iq": np.complex128(1 + 2j)}
    saved = json.loads(json.dumps(focused.json_safe(value), allow_nan=False))
    assert saved == {"path": "measured.json", "gains": [1, 2], "time": .08,
                     "missing": None, "iq": {"__complex__": [1., 2.]}}


def test_source_hashes_identify_actual_file_bytes(tmp_path):
    source = tmp_path / "runner.py"
    source.write_bytes(b"abc")
    assert focused.source_file_sha256([source]) == {
        str(source): "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}


@pytest.mark.parametrize("mode,lower_band", [
    ("population_check", False), ("refocus_check", False),
    ("refocus_decay", False), ("refocus_map", False), ("refocus_map", True),
])
def test_audited_run_saves_every_arm_and_exact_config_without_scouts(tmp_path, monkeypatch, mode, lower_band):
    """Replace hardware boundaries; exercise the real run, analysis, and files."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSDualTransitionLoss

    package = sys.modules[focused.__package__]
    correction = {"segment_edges_ns": [0., 30000., 32000., 80000.],
                  "multipliers": [1.03, 1.02, 1.01, 1.]}
    correction_path = tmp_path / "correction.json"
    correction_path.write_text(json.dumps(correction))
    source = tmp_path / "q3" / focused.square.SOURCE_SESSION / "manifest.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}")
    monkeypatch.setattr(focused.localizer, "checked_correction", lambda *_: correction_path)
    monkeypatch.setattr(focused.square, "validate_source", lambda _: None)
    monkeypatch.setattr(focused.localizer, "run", lambda **_: pytest.fail("population mode ran a T1 scout"))

    def install(name, **attributes):
        module = ModuleType(name)
        module.__file__ = str(Path(focused.__file__).with_name(name.rsplit(".", 1)[1] + ".py"))
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
        if name.rsplit(".", 1)[0] == focused.__package__:
            monkeypatch.setattr(package, name.rsplit(".", 1)[1], module, raising=False)

    class HardwareBoundary:
        def __init__(self, soccfg, cfg, payload, loop):
            self.cfg = {**cfg, "compiled_marker": np.int64(7)}

    def arm_config(base, arm, dc):
        return {**base, "ff_gain": dc[arm["flux_ghz"]],
                "opx_resident_pre_us": arm["pre_drive_us"],
                "opx_resident_post_us": arm["post_drive_us"],
                "opx_resident_freq_mhz": arm["drive_mhz"],
                "opx_resident_gain": arm["gain"],
                "shots": arm["shots"], "reps": arm["shots"]}

    def acquire(_soc, program, _timeout, cfg, *, total_shots):
        assert total_shots == 1600
        if cfg.get("refocus_sequence") == "late_control":
            response = .5 + .45 * math.cos(math.radians(cfg["echo_phase_deg"]))
        elif "refocus_elapsed_us" in cfg:
            response = .5 + .49 * math.exp(-cfg["refocus_elapsed_us"] / 2) * math.cos(
                math.radians(cfg["echo_phase_deg"]))
        elif "echo_delay_us" in cfg:
            response = .5 + .45 * math.exp(-cfg["echo_delay_us"]) * math.cos(
                math.radians(cfg["echo_phase_deg"]))
        elif cfg["opx_resident_gain"] == 0:
            response = 0.
        elif cfg["opx_resident_post_us"] > .100001:
            response = .9 * math.exp(-(cfg["opx_resident_post_us"] - .21) / 2.)
        elif cfg["fast_second_phase_deg"] is not None:
            response = .5 + .45 * math.cos(math.radians(cfg["fast_second_phase_deg"]))
        else:
            response = {focused.PI_US: 1., focused.PI2_US: .5, focused.TWO_PI_US: 0.}[cfg["fast_pulse_us"]]
        return np.full(total_shots, round(response * 10000), dtype=complex)

    install(f"{focused.__package__}.FivePointApplesToApples",
            install_scan_calibration=lambda _: None,
            apply_verified_feedback_timing=lambda _: None)
    install(f"{focused.__package__}.TLSPumpProbeResidentDrive",
            ResidentDriveProgram=HardwareBoundary, arm_config=arm_config,
            record_iq=np.asarray)
    install(f"{focused.__package__}.TLSPumpProbeWidePassiveScan", parameters=lambda: {})
    install(f"{focused.__package__}.TLSSpectroscopy",
            BaseConfig={"ff_park_gain": -25146}, FLUX_FIT_PARAMS=[],
            _load_correction=lambda *_: correction,
            makeProxy=lambda: (SimpleNamespace(get_cfg=lambda: {"clock_mhz": np.float64(384.)}), {}))
    install(f"{focused.__package__}.ThreePointApplesToApples",
            _integer_dc_grid=lambda _p, sites, _tls: (
                np.array([-20130 + round((frequency - 4.288) * 100000)
                          for frequency in sites]), sites))
    prefix = "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX"
    install(f"{prefix}.integration", _run_program=acquire,
            _block_timeout_s=lambda *_: 30.,
            runtime_bundle=lambda _: SimpleNamespace(payload=None, loop=None))
    install(f"{prefix}.production", ProductionResetSession=SimpleNamespace(
        passive=lambda: SimpleNamespace(apply=dict)))

    options = {mode: True}
    if lower_band:
        options["lower_band"] = True
    path = focused.run(data_root=tmp_path, **options)
    manifest = json.loads(path.read_text())
    assert manifest["status"] == "complete_" + mode
    sites = ([4.260, 4.264, 4.268, 4.272, 4.276, 4.288] if lower_band else
             [4.280, 4.284, 4.288, 4.292, 4.296] if mode == "refocus_map" else [4.288])
    assert manifest["valid_site_blocks"] == 3 * len(sites)
    metadata = json.loads(Path(manifest["acquisition_metadata_json"]).read_text())
    assert metadata["board_configuration"] == {"clock_mhz": 384.}
    assert len(metadata["source_file_sha256"]) == (5 if mode == "population_check" else 6)
    assert metadata["effective_base_config"]["opx_inter_shot_delay_us"] == 500.
    expected_acquisitions = {"population_check": 144, "refocus_check": 258,
                             "refocus_decay": 294, "refocus_map": 1470}[mode]
    if lower_band:
        expected_acquisitions = 1764
    assert len(metadata["acquisitions"]) == expected_acquisitions
    if mode == "refocus_map":
        assessment = manifest["refocus_map_assessment"]
        assert assessment["total_site_blocks"] == (18 if lower_band else 15)
        assert manifest["plan"]["sites_ghz"] == sites
        assert manifest["plan"]["grid_band"] == ("lower" if lower_band else "validated")
        if lower_band:
            assert manifest["plan"]["anchor_frequency_ghz"] == 4.288
        assert not assessment["intrinsic_pure_dephasing_inferred"]
        assert set(assessment["sites"]) == {f"{frequency:.3f}" for frequency in sites}
        assert all(site["total_blocks"] == 3 and
                   site["valid_blocks_by_sequence"] == {"hahn_y": 3, "cpmg2_y": 3}
                   for site in assessment["sites"].values())
        assert "refocus_assessment" not in manifest
    config_paths = [arm["program_config_json"] for arm in metadata["acquisitions"]]
    assert len(set(config_paths)) == expected_acquisitions
    assert len(list((path.parent / "program_configs").glob("*.json"))) == expected_acquisitions
    assert len(list(path.parent.glob("block*_*.npz"))) == 3 * len(sites)
    for block in manifest["blocks"]:
        assert [site["frequency_ghz"] for site in block["sites"]] == (
            sites if block["index"] % 2 == 0 else list(reversed(sites)))
        for site in block["sites"]:
            with np.load(site["raw_npz"]) as raw:
                assert len(raw.files) == {"population_check": 96, "refocus_check": 172,
                                          "refocus_decay": 196, "refocus_map": 196}[mode]
                assert all(raw[key].shape == (1600,) for key in raw.files)
                if mode == "population_check":
                    assert len(raw["pop_e_1200ns_i"]) == 1600
                else:
                    assert len(raw["cpmg2_y_1350ns_270_i"]) == 1600
            if mode == "population_check":
                assert site["population_comparison"]["valid"]
            else:
                assert all(site["sequence_valid"].values())
                assert len(site["refocus_comparison"]["by_requested_elapsed_us"]) == (
                    8 if mode in ("refocus_decay", "refocus_map") else 5)
    if mode in ("refocus_decay", "refocus_map"):
        for block in manifest["blocks"]:
            for site in block["sites"]:
                assert site["late_control_gate"]["valid"]
                assert all(g["valid"] for g in site["bridge_gates"].values())
        assert sum(a["kind"].startswith("bridge_") for a in metadata["acquisitions"]) == 24 * len(sites)
        assert sum(a["kind"] == "late_control" for a in metadata["acquisitions"]) == 12 * len(sites)
    for arm in metadata["acquisitions"]:
        assert arm["status"] == "complete"
        assert arm["started_at_utc"] <= arm["finished_at_utc"]
        cfg = json.loads(Path(arm["program_config_json"]).read_text())
        assert cfg["compiled_marker"] == 7
        assert cfg["opx_resident_freq_mhz"] == pytest.approx(1000 * arm["frequency_ghz"] + 2.5)
        assert cfg["ff_gain"] == -20130 + round((arm["frequency_ghz"] - 4.288) * 100000)
        if arm["kind"] in ("pop_g", "pop_e", "echo"):
            assert cfg["ff_hold"] == pytest.approx(30.3107 + arm["delay_us"])
        if mode in ("refocus_check", "refocus_decay", "refocus_map") and arm["kind"] in focused.refocus.SEQUENCES:
            assert cfg["refocus_elapsed_us"] == arm["delay_us"]
            assert cfg["refocus_sequence"] == arm["kind"]
            assert cfg["echo_phase_deg"] == arm["phase_deg"]


def test_refocus_plan_stays_at_validated_point_and_has_no_scout(capsys):
    p = focused.plan(refocus_check=True)
    assert p['sites_ghz'] == [4.288]
    assert p['sequences'] == ['hahn_x', 'hahn_y', 'cpmg2_y']
    assert p['t1_scans'] is None
    assert p['matched_pi2_center_elapsed_time']
    assert p['shots_per_arm'] == 1600
    for mode in ('single_point', 'local_map', 'population_check'):
        with pytest.raises(ValueError):
            focused.run(refocus_check=True, **{mode: True})
    assert focused.main(['--plan', '--refocus-check']) == 0
    assert json.loads(capsys.readouterr().out)['sequences'] == p['sequences']


def test_refocus_schedule_interleaves_protocols_and_balances_order():
    schedules = [focused.refocus_schedule(b) for b in range(3)]
    assert len(schedules[0]) == 60
    assert len(set(schedules[0])) == 60
    assert set(schedules[0]) == set(schedules[1]) == set(schedules[2])
    # Every phase/delay group tests all three protocols consecutively.
    for schedule in schedules:
        for i in range(0, len(schedule), 3):
            group = schedule[i:i+3]
            assert len({(t, p) for _, t, p in group}) == 1
            assert {s for s, _, _ in group} == {'hahn_x', 'hahn_y', 'cpmg2_y'}
    assert schedules[0][0][1] < schedules[1][0][1]
    assert [schedule[0][0] for schedule in schedules] == ['hahn_x','hahn_y','cpmg2_y']


def test_refocus_report_retains_raw_visibility_to_expose_pulse_penalty():
    times = (.35, .455, .65, .95, 1.35)
    amplitudes = {'hahn_x': .85, 'hahn_y': .80, 'cpmg2_y': .60}
    cycles = {name: {t: {0: .5+a*math.exp(-t)/2, 90: .5,
                        180: .5-a*math.exp(-t)/2, 270: .5}
                     for t in times} for name,a in amplitudes.items()}
    report = focused.refocus_report(cycles)
    row = report['by_requested_elapsed_us'][times[-1]]
    assert row['cpmg2_minus_hahn_y_visibility'] < 0
    assert row['normalized']['cpmg2_y'] == pytest.approx(row['normalized']['hahn_y'])
    assert row['visibility']['cpmg2_y'] == pytest.approx(.6*math.exp(-1.35))
    assert 'intrinsic_t2' not in report


def test_decay_plan_extends_one_validated_site_without_scout(capsys):
    p = focused.plan(refocus_decay=True)
    assert p['sites_ghz'] == [4.288]
    assert p['sequences'] == ['hahn_y', 'cpmg2_y']
    assert p['requested_pi2_center_elapsed_us'][-1] == 4.2
    assert p['t1_scans'] is None
    assert p['concurrent_flux_correction']
    assert p['late_projection_control']
    with pytest.raises(ValueError):
        focused.run(refocus_check=True, refocus_decay=True)
    assert focused.main(['--plan', '--refocus-decay']) == 0
    assert json.loads(capsys.readouterr().out)['concurrent_flux_correction']


def test_refocus_map_repeats_full_paired_traces_at_five_fixed_sites_without_scout(capsys):
    p = focused.plan(refocus_map=True)
    assert p['sites_ghz'] == [4.280, 4.284, 4.288, 4.292, 4.296]
    assert p['sequences'] == ['hahn_y', 'cpmg2_y']
    assert p['requested_pi2_center_elapsed_us'] == [.35, .65, .95, 1.35, 1.8, 2.4, 3.2, 4.2]
    assert p['shots_per_arm'] == 1600
    assert p['reversed_blocks'] == 3
    assert p['t1_scans'] is None
    assert p['concurrent_flux_correction']
    assert p['late_projection_control']
    assert p['legacy_playback_overlap_us'] == 1.35
    for other_mode in ('single_point', 'local_map', 'population_check', 'refocus_check', 'refocus_decay'):
        with pytest.raises(ValueError):
            focused.run(refocus_map=True, **{other_mode: True})
    assert focused.main(['--plan', '--refocus-map']) == 0
    assert json.loads(capsys.readouterr().out)['sites_ghz'] == p['sites_ghz']


def test_lower_refocus_map_extends_frequency_grid_and_preserves_anchor_and_protocol(capsys):
    p = focused.plan(refocus_map=True, lower_band=True)
    assert p['sites_ghz'] == [4.260, 4.264, 4.268, 4.272, 4.276, 4.288]
    assert p['grid_band'] == 'lower'
    assert p['anchor_frequency_ghz'] == 4.288
    assert p['sequences'] == ['hahn_y', 'cpmg2_y']
    assert p['requested_pi2_center_elapsed_us'] == [.35, .65, .95, 1.35, 1.8, 2.4, 3.2, 4.2]
    assert p['shots_per_arm'] == 1600
    assert p['reversed_blocks'] == 3
    assert p['t1_scans'] is None
    assert p['concurrent_flux_correction']
    assert p['controls_at_every_site']
    assert p['late_projection_control']
    assert p['legacy_playback_overlap_us'] == 1.35
    assert focused.main(['--plan', '--refocus-map', '--lower-band']) == 0
    assert json.loads(capsys.readouterr().out) == p
    # An opt-in extension must not silently change the previously validated grid.
    original = focused.plan(refocus_map=True)
    assert original['sites_ghz'] == [4.280, 4.284, 4.288, 4.292, 4.296]
    assert original['grid_band'] == 'validated'


@pytest.mark.parametrize('mode', [None, 'single_point', 'local_map',
                                 'population_check', 'refocus_check', 'refocus_decay'])
def test_lower_band_rejects_nonmap_modes_before_hardware_import(mode, capsys):
    options = {} if mode is None else {mode: True}
    with pytest.raises(ValueError):
        focused.plan(lower_band=True, **options)
    with pytest.raises(ValueError):
        focused.run(lower_band=True, **options)
    cli = ['--run', '--lower-band']
    if mode:
        cli.append('--' + mode.replace('_', '-'))
    with pytest.raises(SystemExit) as exc:
        focused.main(cli)
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert '--lower-band' in error and '--refocus-map' in error


def test_lower_band_cli_runs_the_requested_map(monkeypatch, tmp_path):
    called = []

    def run_boundary(**kwargs):
        called.append(kwargs)
        return tmp_path / 'manifest.json'

    monkeypatch.setattr(focused, 'run', run_boundary)
    assert focused.main(['--run', '--refocus-map', '--lower-band']) == 0
    assert len(called) == 1
    assert called[0]['refocus_map'] is True
    assert called[0]['lower_band'] is True


def test_decay_schedule_keeps_legacy_overlap_next_to_new_sequence():
    for block in range(3):
        schedule = focused.decay_schedule(block)
        assert len(schedule) == 72
        assert len(set(schedule)) == 72
        for i, (kind,t,phase) in enumerate(schedule):
            if kind.startswith('bridge_'):
                assert t == 1.35
                assert schedule[i-1] == (kind.removeprefix('bridge_'),t,phase)
        assert {t for kind,t,phase in schedule if not kind.startswith('bridge_')} == {.35,.65,.95,1.35,1.8,2.4,3.2,4.2}


def test_bridge_gate_compares_same_filter_not_hahn_to_cpmg():
    current = {0: .7, 90: .5, 180: .3, 270: .5}
    old = {0: .71, 90: .5, 180: .29, 270: .5}
    assert focused.bridge_gate(current, old)['valid']
    assert not focused.bridge_gate(current, {0:.55,90:.5,180:.45,270:.5})['valid']
    assert not focused.bridge_gate(current, {0:.3,90:.5,180:.7,270:.5})['valid']
