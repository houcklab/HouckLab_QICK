import importlib
import json
import subprocess
import sys
from collections import Counter
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest


PREFIX = "WorkingProjects.TLS_Spectroscopy.Client_modules"
MODULE = f"{PREFIX}.Runners.TLSPumpProbeConfirmed"


def runner():
    return importlib.import_module(MODULE)


def test_plan_is_hardware_free_and_every_test_has_local_shams():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False
    assert plan["acquisition_blocks"] == 144
    assert plan["pump_probe_shots"] == 57_600
    assert plan["reference_shots"] == 32_000
    p = plan["parameters"]
    assert p["target_frequency_ghz"] == [4.110]
    assert p["probe_states"] == ["g"]
    assert p["probe_holds_us"] == [0.1]
    assert p["probe_locations"] == ["target", "park"]
    points = runner().pilot.schedule(p)
    assert len(points) == 144
    comparisons = {}
    for entry in points:
        comparisons.setdefault(entry["comparison_id"], []).append(entry)
    assert len(comparisons) == 48
    for triplet in comparisons.values():
        assert [x["control_position"] for x in triplet] == ["before", "test", "after"]
        assert triplet[0]["pump_mode"] == triplet[2]["pump_mode"] == "sham"
        assert {x["pump_detuning_mhz"] for x in triplet} in ({8.0}, {-20.0})
        assert len({(x["repeat"], x["probe_state"], x["probe_us"],
                     x["probe_location"]) for x in triplet}) == 1
    counts = Counter((x["probe_location"], x["test_condition"])
                     for x in points if x["control_position"] == "test")
    assert counts == Counter({(location, condition): 8 for location in ("target", "park")
                              for condition in ("plus8", "minus20", "null")})


def test_transfer_plan_probes_both_directions_at_two_microseconds():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan", "--transfer-check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False and plan["transfer_check"]
    assert plan["acquisition_blocks"] == 288
    assert plan["pump_probe_shots"] == 115_200
    p = plan["parameters"]
    assert p["target_frequency_ghz"] == [4.110]
    assert p["probe_states"] == ["g", "e"]
    assert p["probe_holds_us"] == [2.0]
    points = runner().pilot.schedule(p)
    assert len({x["comparison_id"] for x in points}) == 96
    tests = [x for x in points if x["control_position"] == "test"]
    assert Counter((x["probe_state"], x["probe_location"], x["test_condition"])
                   for x in tests) == Counter({(state, location, condition): 8
                                               for state in ("g", "e")
                                               for location in ("target", "park")
                                               for condition in ("plus8", "minus20", "null")})


def test_relocalize_plan_scans_broad_band_in_both_directions_without_microwave_pump():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan", "--relocalize"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False and plan["relocalize"]
    assert plan["acquisition_blocks"] == 1206
    assert plan["pump_probe_shots"] == 301_500
    p = plan["parameters"]
    assert p["target_frequency_ghz"][0] == 3.9
    assert p["target_frequency_ghz"][-1] == 4.3
    assert len(p["target_frequency_ghz"]) == 201
    assert p["freq_step_mhz"] == 2.0 and p["shots"] == 250
    points = runner().scan_schedule(p)
    assert len(points) == 1206
    assert {x["pump_mode"] for x in points} == {"sham"}
    assert {x["probe_location"] for x in points} == {"target"}
    assert all(x["pump_gain"] == 0 for x in points)
    assert [x["target_index"] for x in points[::3]][:201] == list(range(201))
    assert [x["target_index"] for x in points[::3]][201:] == list(reversed(range(201)))
    for start in range(0, len(points), 3):
        group = points[start:start + 3]
        assert len({x["comparison_id"] for x in group}) == 1
        assert {(x["probe_state"], x["probe_us"]) for x in group} == {
            ("e", 2.0), ("e", 10.0), ("g", 10.0)}


def test_fine_localize_plan_resolves_new_candidate_with_repeated_reverse_passes():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan", "--fine-localize"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False and plan["fine_localize"]
    assert not plan["microwave_pump_enabled"]
    assert plan["acquisition_blocks"] == 444
    assert plan["pump_probe_shots"] == 177_600
    p = plan["parameters"]
    assert p["target_frequency_ghz"][0] == 4.036
    assert p["target_frequency_ghz"][-1] == 4.054
    assert len(p["target_frequency_ghz"]) == 37
    assert p["freq_step_mhz"] == 0.5 and p["shots"] == 400
    assert p["repeats"] == 4
    points = runner().scan_schedule(p)
    assert len(points) == 444
    assert [x["target_index"] for x in points[::3]][:37] == list(range(37))
    assert [x["target_index"] for x in points[::3]][37:74] == list(reversed(range(37)))
    assert [x["target_index"] for x in points[::3]][74:111] == list(range(37))
    assert [x["target_index"] for x in points[::3]][111:] == list(reversed(range(37)))
    assert {x["pump_mode"] for x in points} == {"sham"}


def test_secondary_localize_plan_checks_other_broadband_feature_without_pumping():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan", "--secondary-localize"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False and plan["secondary_localize"]
    assert not plan["microwave_pump_enabled"]
    assert plan["acquisition_blocks"] == 348
    assert plan["pump_probe_shots"] == 139_200
    p = plan["parameters"]
    assert p["target_frequency_ghz"][0] == 4.108
    assert p["target_frequency_ghz"][-1] == 4.122
    assert len(p["target_frequency_ghz"]) == 29
    assert p["freq_step_mhz"] == 0.5 and p["shots"] == 400
    assert p["repeats"] == 4
    points = runner().scan_schedule(p)
    assert len(points) == 348
    assert [x["target_index"] for x in points[::3]][:29] == list(range(29))
    assert [x["target_index"] for x in points[::3]][29:58] == list(reversed(range(29)))
    assert {x["pump_mode"] for x in points} == {"sham"}


def test_drift_track_plan_revisits_both_loss_flanks_over_twelve_passes():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan", "--drift-track"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False and plan["drift_track"]
    assert not plan["microwave_pump_enabled"]
    assert plan["acquisition_blocks"] == 1044
    assert plan["pump_probe_shots"] == 261_000
    p = plan["parameters"]
    assert p["target_frequency_ghz"][0] == 4.094
    assert p["target_frequency_ghz"][-1] == 4.122
    assert len(p["target_frequency_ghz"]) == 29
    assert p["freq_step_mhz"] == 1.0 and p["shots"] == 250
    assert p["repeats"] == 12
    points = runner().scan_schedule(p)
    assert len(points) == 1044
    target_order = [x["target_index"] for x in points[::3]]
    for repeat in range(12):
        expected = list(range(29)) if repeat % 2 == 0 else list(reversed(range(29)))
        assert target_order[repeat * 29:(repeat + 1) * 29] == expected
    assert {x["pump_mode"] for x in points} == {"sham"}


def test_guarded_scout_brackets_short_pump_off_scan_with_periodic_references():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan", "--guarded-scout"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False and plan["guarded_scout"]
    assert plan["microwave_pump_enabled"] is False
    assert plan["acquisition_blocks"] == 174
    assert plan["pump_probe_shots"] == 43_500
    assert plan["checkpoint_references"] == 10
    assert plan["reference_shots"] == 112_000
    p = plan["parameters"]
    assert p["target_frequency_ghz"] == [round(4.094 + 0.001 * i, 3)
                                          for i in range(29)]
    assert p["repeats"] == 2 and p["shots"] == 250
    schedule = runner().scan_schedule(p, reference_interval_targets=10)
    data = [x for x in schedule if x.get("kind") != "reference"]
    checks = [x for x in schedule if x.get("kind") == "reference"]
    assert len(data) == 174
    assert [(x["repeat"], x["after_targets"], x["reference_type"])
            for x in checks] == [(repeat, target_count, role)
                                 for repeat, target_count in ((0, 10), (0, 20),
                                                               (0, 29), (1, 10),
                                                               (1, 20))
                                 for role in ("decision", "probe")]
    assert [x["target_index"] for x in data[::3]][:29] == list(range(29))
    assert [x["target_index"] for x in data[::3]][29:] == list(reversed(range(29)))


def test_confirmed_program_requires_loop_and_restores_half_gain(monkeypatch):
    module = importlib.import_module(f"{PREFIX}.Runners.TLSPumpProbeConfirmedProgram")
    programs = importlib.import_module(f"{PREFIX}.active_reset_OPX.programs")
    pulse_setup = importlib.import_module(f"{PREFIX}.Helpers.pulse_setup")
    obj = object.__new__(module.ConfirmedPumpProbeProgram)
    obj.cfg = {"qubit_ch": 1, "read_pulse_gain": 940,
               "opx_diagnostic_probe_readout_gain": 1880}
    obj.payload_calibration, obj.loop_calibration = "decision_payload", "decision_loop"
    obj.reset_page, obj.reset_regs = 0, {"i": 1}
    obj.reset_config = SimpleNamespace(read_delay_us=10., loop_recovery_us=20.,
                                       feedback_syncdelay_us=8.)
    events = []
    obj._set_reset_pulse = lambda: events.append("reset_pulse")
    obj._wait_reset_ringdown = lambda: events.append("ringdown")
    obj._measure_raw = lambda: events.append("raw_probe_iq")
    obj.pulse = lambda **kw: events.append(("pi", kw))
    obj.sync_all = lambda t: events.append(("sync", t))
    obj.us2cycles = lambda t: t
    monkeypatch.setattr(module, "emit_unbounded_reset_state_machine",
                        lambda *a, **kw: (events.append(("state_machine", kw["require_loop_readout"],
                                                         kw["label_prefix"])), kw["measure_next"]()))
    monkeypatch.setattr(programs.OPXResetTLSSaturationProgram, "_measure_project",
                        lambda self, cal, context: events.append(("measure", cal, context)))
    monkeypatch.setattr(programs.OPXResetTLSSaturationProgram, "_wait_saturation_probe",
                        lambda self: events.append("probe_flux_return"))
    monkeypatch.setattr(pulse_setup, "set_readout_pulse",
                        lambda self, gain=None: events.append(("readout_gain", self.cfg["read_pulse_gain"]
                                                               if gain is None else gain)))
    obj._reset_saturation_qubit("pre")
    obj._reset_saturation_qubit("post")
    obj._wait_saturation_probe()
    obj._measure_project(obj.payload_calibration, "payload")
    obj._measure_project(obj.loop_calibration, "loop")
    assert events == [
        "reset_pulse", ("measure", "decision_payload", "payload"),
        ("state_machine", True, "pre"), ("measure", "decision_loop", "loop"), ("sync", 20.),
        "reset_pulse", ("measure", "decision_payload", "payload"),
        ("state_machine", True, "post"), ("measure", "decision_loop", "loop"), ("sync", 20.),
        "probe_flux_return", ("readout_gain", 1880),
        "raw_probe_iq", ("readout_gain", 940),
        ("measure", "decision_loop", "loop"),
    ]


@pytest.mark.parametrize("decision,probe,periodic", [
    (940, 0, False), (940, 32768, False), (1880, 1880, False),
    (0, 1880, False), (940, 1880, True),
])
def test_confirmed_program_rejects_invalid_gain_before_hardware(decision, probe, periodic):
    module = importlib.import_module(f"{PREFIX}.Runners.TLSPumpProbeConfirmedProgram")
    with pytest.raises(ValueError):
        module.ConfirmedPumpProbeProgram(None, {
            "read_pulse_gain": decision,
            "opx_diagnostic_probe_readout_gain": probe,
            "ro_mode_periodic": periodic,
        }, None, None)


@pytest.mark.parametrize("ending_accepted", [True, False])
@pytest.mark.parametrize("stage", ["short", "transfer", "relocalize", "fine", "secondary", "drift", "scout"])
def test_full_mocked_run_uses_separate_frozen_classifiers_and_final_references(
        tmp_path, monkeypatch, ending_accepted, stage):
    m = runner()
    transfer_check, relocalize, fine_localize, secondary_localize, drift_track = (
        stage == "transfer", stage == "relocalize", stage == "fine",
        stage == "secondary", stage == "drift")
    guarded_scout = stage == "scout"
    scan_mode = relocalize or fine_localize or secondary_localize or drift_track or guarded_scout
    package = importlib.import_module(f"{PREFIX}.Runners")
    calibration = importlib.import_module(f"{PREFIX}.active_reset_OPX.calibration")
    grid = SimpleNamespace(_integer_dc_grid=lambda p, frequencies: (
        np.arange(-16000, -16000 + len(frequencies)), np.asarray(frequencies)))
    monkeypatch.setitem(sys.modules, f"{PREFIX}.Runners.ThreePointApplesToApples", grid)

    class Fit:
        excited_threshold = 0

        def __init__(self, label):
            self.label = label

        def project(self, i, q):
            if self.label == "decision":
                raise AssertionError("decision classifier used on full-gain probe IQ")
            return np.asarray(i)

    class Bundle:
        def __init__(self, label):
            self.payload = self.loop = Fit(label)
            self.label = label

        def to_dict(self):
            return {"label": self.label}

    base = {"ff_park_gain": -25146, "qubit_pi_freq": 4367.292,
            "read_pulse_gain": 1880, "read_length": 3.5, "ro_chs": [0]}
    fake_tls = SimpleNamespace(BaseConfig=base, makeProxy=lambda: (object(), object()),
                               _load_correction=lambda *a: {"segments": []}, FLUX_FIT_PARAMS=[])
    monkeypatch.setattr(package, "TLSSpectroscopy", fake_tls, raising=False)
    monkeypatch.setattr(package, "FivePointApplesToApples",
                        SimpleNamespace(install_scan_calibration=lambda tls: None), raising=False)
    monkeypatch.setattr(m.localizer, "checked_correction", lambda *a: tmp_path / "correction.json")
    monkeypatch.setattr(m.localizer, "scan_environment", lambda *a: nullcontext())
    monkeypatch.setenv("Q3_CODE_COMMIT", "mock-test")
    p = m.parameters(transfer_check=transfer_check, relocalize=relocalize,
                     fine_localize=fine_localize,
                     secondary_localize=secondary_localize,
                     drift_track=drift_track, guarded_scout=guarded_scout)
    p.update(repeats=2 if scan_mode else 1, shots=4)
    if scan_mode:
        p["target_frequency_ghz"] = [4.094, 4.096, 4.098]
    monkeypatch.setattr(m, "parameters", lambda **kwargs: p)
    references = []

    def fake_reference(soc, soccfg, cfg, **kwargs):
        references.append(cfg["read_pulse_gain"])
        return Bundle("decision" if cfg["read_pulse_gain"] == 940 else "probe"), {}

    monkeypatch.setattr(calibration, "acquire_calibration", fake_reference)
    monkeypatch.setattr(calibration, "save_calibration", lambda path, b: path.write_text(b.label))
    monkeypatch.setattr(calibration, "save_raw_calibration", lambda path, raw: path.write_text("raw"))
    monkeypatch.setattr(calibration, "validate_confident_calibration", lambda b: b)
    monkeypatch.setattr(m.reference, "calibration_report",
                        lambda b: {"accepted": ending_accepted or len(references) < 4})
    point_cfgs = []

    def fake_acquire(soc, soccfg, cfg):
        point_cfgs.append(cfg)
        records = [SimpleNamespace(final_i=i, final_q=0) for i in (-10, -10, 10, 10)]
        return records, {"read_length_cycles": 10, "reset_reference_guard_us": 20.}

    monkeypatch.setattr(m, "acquire_records", fake_acquire)
    if ending_accepted:
        path = m.run(data_root=tmp_path, transfer_check=transfer_check,
                     relocalize=relocalize, fine_localize=fine_localize,
                     secondary_localize=secondary_localize,
                     drift_track=drift_track, guarded_scout=guarded_scout)
    else:
        with pytest.raises(RuntimeError, match=("Checkpoint" if guarded_scout else "Final") +
                           " calibration reference rejected"):
            m.run(data_root=tmp_path, transfer_check=transfer_check,
                  relocalize=relocalize, fine_localize=fine_localize,
                  secondary_localize=secondary_localize,
                  drift_track=drift_track, guarded_scout=guarded_scout)
        path = next((tmp_path / "q3").glob("*/manifest.json"))
    manifest = json.loads(path.read_text())
    blocks = 36 if transfer_check else 18
    assert manifest["transfer_check"] == transfer_check
    assert manifest["relocalize"] == relocalize
    assert manifest["fine_localize"] == fine_localize
    assert manifest["secondary_localize"] == secondary_localize
    assert manifest["drift_track"] == drift_track
    assert manifest["guarded_scout"] == guarded_scout
    assert manifest["status"] == ("complete" if ending_accepted else "failed")
    if guarded_scout and not ending_accepted:
        assert manifest["checkpoint_references_accepted"] is False
        assert "final_references_accepted" not in manifest
        assert references == [940, 1880, 940, 1880]
        assert len(point_cfgs) == 9
    else:
        assert manifest["final_references_accepted"] == ending_accepted
        assert references == ([940, 1880] * 3 if guarded_scout else
                              [940, 1880, 940, 1880])
        assert len(point_cfgs) == blocks
    assert {c["opx_saturation_probe_state"] for c in point_cfgs} == (
        {"g", "e"} if transfer_check or scan_mode else {"g"})
    assert {c["opx_saturation_probe_us"] for c in point_cfgs} == (
        {2.0, 10.0} if scan_mode else {2.0} if transfer_check else {0.1})
    if scan_mode:
        assert {c["opx_saturation_arm"] for c in point_cfgs} == {"no_pump"}
        assert {c["ff_gain"] for c in point_cfgs} == {-16000, -15999, -15998}
        assert manifest["dc_gain"] == [-16000, -15999, -15998]
    assert all(c["read_pulse_gain"] == 940 and c["opx_diagnostic_probe_readout_gain"] == 1880
               and c["opx_loop_recovery_us"] == 20 for c in point_cfgs)
    assert all(c["opx_reset_calibration"] == {"label": "decision"} for c in point_cfgs)
    assert all(entry["result"]["P_excited"] == 0.5 for entry in manifest["points"]
               if entry.get("kind") != "reference" and entry["status"] == "complete")
    if guarded_scout and not ending_accepted:
        assert [e["status"] for e in manifest["points"]] == (
            ["complete"] * 10 + ["failed"] + ["pending"] * 11)
        assert manifest["points"][10]["result"]["accepted"] is False
    else:
        assert [entry["status"] for entry in manifest["points"]] == (
            ["complete"] * (blocks + (4 if guarded_scout else 2)) if ending_accepted
            else ["complete"] * (blocks + 1) + ["failed"])
    if not ending_accepted and not guarded_scout:
        assert manifest["points"][-1]["result"] == {"accepted": False,
                                                    "output": str(path.parent / "final_probe_reference")}
    assert sum(1 for _ in (path.parent / "summary.csv").open()) == (
        10 if guarded_scout and not ending_accepted else blocks + 1)
    with np.load(path.parent / "point_0000.npz") as raw:
        assert raw["i_raw"].tolist() == [-10, -10, 10, 10]
        assert raw["read_length_cycles"].item() == 10
    assert base["read_pulse_gain"] == 1880


def test_partial_timeout_saves_raw_iq_with_actual_read_cycles(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import acquisition, integration
    m = runner()
    fit = SimpleNamespace(project=lambda i, q: np.asarray(i), excited_threshold=0)
    bundle = SimpleNamespace(payload=fit, loop=fit)
    monkeypatch.setattr(integration, "runtime_bundle", lambda cfg: bundle)
    program_module = importlib.import_module(f"{PREFIX}.Runners.TLSPumpProbeConfirmedProgram")

    class Program:
        def __init__(self, soccfg, cfg, payload, loop):
            self._saturation_reset_guard_us = 20.

        def us2cycles(self, *a, **kw):
            return 1075

    monkeypatch.setattr(program_module, "ConfirmedPumpProbeProgram", Program)
    def timeout(*a, **kw):
        raise acquisition.AcquisitionTimeout("watchdog", completed_shots=2,
                                             partial_records=[SimpleNamespace(final_i=1, final_q=2)] * 2)
    monkeypatch.setattr(integration, "_run_program", timeout)
    with pytest.raises(acquisition.AcquisitionTimeout) as error:
        m.acquire_records(object(), object(), {"opx_saturation_shots": 4,
                                                "read_length": 3.5, "ro_chs": [0]})
    assert error.value.read_length_cycles == 1075
    m.save_probe_iq(tmp_path / "partial.npz", error.value.partial_records,
                    error.value.read_length_cycles, bundle)
    with np.load(tmp_path / "partial.npz") as raw:
        assert raw["i_raw"].tolist() == [1, 1]
        assert raw["i"].tolist() == [1 / 1075, 1 / 1075]
