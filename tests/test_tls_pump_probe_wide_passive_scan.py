import importlib
import json
import subprocess
import sys


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeWidePassiveScan"


def test_plan_is_one_descending_pump_off_pass_without_active_reset():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan"],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    p = plan["parameters"]
    assert plan["hardware_access"] is False
    assert plan["microwave_pump_enabled"] is False
    assert plan["frequency_count"] == 251
    assert plan["condition_count"] == 5
    assert plan["total_measurements"] == 313_750
    assert plan["scan_direction"] == "4.300 to 3.800 GHz"
    assert (p["freq_min_ghz"], p["freq_max_ghz"], p["freq_step_mhz"]) == (3.8, 4.3, 2.0)
    assert p["dc_min"] == -20550 and p["dc_max"] == -11800
    assert p["reset_mode"] == "passive" and p["max_runs"] == 1
    assert p["wall_clock_duration_min"] == 2.0
    assert p["sync_enabled"] is False
    assert p["reference_hold_us"] == 0.1
    assert p["decay_delays_us"] == [2.0, 10.0, 25.0]
    assert p["shots_per_condition"] == 250
    assert p["output_suffix"] == "TLS_PumpProbe_Wide_Passive_3p8_4p3"


def test_run_delegates_isolated_parameters_to_existing_five_point_path(
        tmp_path, monkeypatch):
    module = importlib.import_module(MODULE)
    observed = {}
    def fake_run(**kwargs):
        observed.update(kwargs)
    monkeypatch.setattr(module.localizer, "run", fake_run)
    assert module.main(["--run", "--data-root", str(tmp_path)]) == 0
    assert observed["data_root"] == tmp_path
    assert observed["correction_json"] is None
    assert observed["parameter_overrides"] == module.parameters()
