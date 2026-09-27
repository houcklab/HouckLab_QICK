"""The first pump/probe run must survey the full band without stale overrides."""

import importlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeLocalizer"
RUNNERS = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners"
ROOT = Path(__file__).resolve().parents[1]


def localizer():
    assert importlib.util.find_spec(MODULE) is not None, "localizer runner is missing"
    return importlib.import_module(MODULE)


def test_plan_runs_without_hardware_or_nas_and_ignores_stale_scan_environment():
    localizer()
    result = subprocess.run(
        [sys.executable, "-m", MODULE, "--plan"], cwd=ROOT,
        env={**os.environ, "Q3_5PT_FREQ_MIN_GHZ": "4.13",
             "Q3_5PT_MAX_RUNS": "1000", "Q3_FLUXPRED_MODE": "neutral"},
        text=True, capture_output=True, check=True,
    )
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False
    assert plan["frequency_count"] == 801
    assert plan["parameters"]["freq_min_ghz"] == 3.9
    assert plan["parameters"]["freq_max_ghz"] == 4.3
    assert plan["parameters"]["max_runs"] == 3
    assert plan["parameters"]["decay_delays_us"] == [25.0, 60.0, 100.0]
    assert plan["parameters"]["shots_per_condition"] == 300


def test_environment_is_isolated_and_restored_even_on_acquisition_error(monkeypatch):
    module = localizer()
    original = {
        "Q3_5PT_EXECUTION_TEST": "passive",
        "Q3_5PT_PREDISTORTION": "off",
        "Q3_5PT_FREQ_MIN_GHZ": "4.13",
        "Q3_PROTOCOL_CROSSOVER_PHASE": "legacy_off",
        "Q3_FLUXPRED_MODE": "neutral",
        "Q3_FLUXPRED_MODEL_JSON": "old.json",
        "Q3_FLUX_TAIL_GAIN": "0.5",
        "UNRELATED_LOCALIZER_TEST_VALUE": "preserved",
    }
    for key, value in original.items():
        monkeypatch.setenv(key, value)
    before = dict(os.environ)
    with pytest.raises(RuntimeError, match="acquisition failed"):
        with module.scan_environment(Path("chosen.json")):
            assert "Q3_5PT_EXECUTION_TEST" not in os.environ
            assert "Q3_5PT_PREDISTORTION" not in os.environ
            assert "Q3_5PT_FREQ_MIN_GHZ" not in os.environ
            assert "Q3_PROTOCOL_CROSSOVER_PHASE" not in os.environ
            assert "Q3_FLUXPRED_MODEL_JSON" not in os.environ
            assert os.environ["Q3_FLUXPRED_MODE"] == "off"
            assert os.environ["Q3_FLUX_TAIL_GAIN"] == "1.0"
            assert os.environ["Q3_5PT_CORRECTION_JSON"] == "chosen.json"
            assert os.environ["UNRELATED_LOCALIZER_TEST_VALUE"] == "preserved"
            raise RuntimeError("acquisition failed")
    assert dict(os.environ) == before


def test_wrong_correction_is_rejected_before_importing_hardware(tmp_path):
    module = localizer()
    correction = tmp_path / "correction.json"
    correction.write_text("{}")
    with pytest.raises(RuntimeError, match="checksum"):
        module.run(data_root=tmp_path, correction_json=correction)


def test_missing_correction_is_rejected_before_importing_hardware(tmp_path):
    with pytest.raises(FileNotFoundError, match="correction"):
        localizer().run(data_root=tmp_path)


@pytest.mark.parametrize("overrides, expected_grid, expected_delays", [
    (None, (3.9, 4.3, 0.5), [25.0, 60.0, 100.0]),
    ({"freq_min_ghz": 4.085, "freq_max_ghz": 4.112, "freq_step_mhz": 0.25,
      "decay_delays_us": [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]},
     (4.085, 4.112, 0.25), [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]),
])
def test_run_delivers_scan_contract_to_existing_acquisition(
        tmp_path, monkeypatch, overrides, expected_grid, expected_delays):
    module = localizer()
    correction = tmp_path / "correction.json"
    correction.write_bytes(b"abc")
    monkeypatch.setattr(module, "CORRECTION_SHA256",
                        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    observed = {}
    runner = types.ModuleType(f"{RUNNERS}.FivePointApplesToApples")
    runner.P6_5PT_APPLES_TO_APPLES = {"max_runs": None, "sync_slot_s": 150.0}
    tls = types.ModuleType(f"{RUNNERS}.TLSSpectroscopy")
    tls.BaseConfig = {"ff_park_gain": -25146}

    def acquire():
        observed.update(parameters=dict(runner.P6_5PT_APPLES_TO_APPLES),
                        data_root=tls.outerFolder, qubit=tls.QUBIT,
                        set_yoko=tls.SET_YOKO,
                        correction=os.environ["Q3_5PT_CORRECTION_JSON"])
        return Path("/nas/one-stop.csv")

    runner.main = acquire
    package = importlib.import_module(RUNNERS)
    for name, stub in (("FivePointApplesToApples", runner), ("TLSSpectroscopy", tls)):
        monkeypatch.setitem(sys.modules, f"{RUNNERS}.{name}", stub)
        monkeypatch.setattr(package, name, stub, raising=False)
    monkeypatch.setenv("Q3_5PT_MAX_RUNS", "1000")
    result = module.run(data_root=tmp_path, correction_json=correction,
                        parameter_overrides=overrides)
    assert result == Path("/nas/one-stop.csv")
    p = observed["parameters"]
    assert (p["freq_min_ghz"], p["freq_max_ghz"], p["freq_step_mhz"]) == expected_grid
    assert p["decay_delays_us"] == expected_delays
    assert p["max_runs"] == 3 and p["wall_clock_duration_min"] == 30.0
    assert p["sync_enabled"] is False and p["reset_mode"] == "active"
    assert p["apply_flux_tail_compensation"] is True
    assert p["flux_predistortion_recovery_us"] == 40.0
    assert p["flux_predistortion_overlap_payload_readout"] is False
    assert p["output_suffix"] == "TLS_PumpProbe_Localizer"
    assert observed["data_root"] == str(tmp_path)
    assert observed["qubit"] == "q3" and observed["set_yoko"] is False
    assert observed["correction"] == str(correction)
    assert os.environ["Q3_5PT_MAX_RUNS"] == "1000"


def test_target_check_plan_has_early_times_and_both_observed_quiet_flanks():
    module = f"{RUNNERS}.TLSPumpProbeTargetCheck"
    assert importlib.util.find_spec(module) is not None, "target-check runner is missing"
    result = subprocess.run([sys.executable, "-m", module, "--plan"], cwd=ROOT,
                            text=True, capture_output=True, check=True)
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False
    assert plan["frequency_count"] == 109
    p = plan["parameters"]
    assert p["freq_min_ghz"] < 4.086 < 4.098 < 4.110 < p["freq_max_ghz"]
    assert p["decay_delays_us"] == [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
    assert p["reference_hold_us"] == 2.0
    assert p["shots_per_condition"] == 500
    assert p["max_runs"] == 3
    assert p["output_suffix"] == "TLS_PumpProbe_TargetCheck"
    assert plan["condition_count"] == 10
