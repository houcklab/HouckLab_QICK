import importlib
import json
import subprocess
import sys

import numpy as np


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeParkPiSweep"


def test_plan_sweeps_park_pi_frequency_and_brackets_center_without_pumping():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan"],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False
    assert plan["microwave_pump_enabled"] is False
    assert plan["changes_production_settings"] is False
    assert plan["shots_per_state_per_context"] == 500
    assert plan["total_reference_shots"] == 44_000
    offsets = [p["offset_mhz"] for p in plan["points"]]
    assert offsets == [0.0, -2.0, 2.0, -4.0, 4.0, -6.0, 6.0,
                       -8.0, 8.0, -10.0, 10.0, -12.0, 12.0,
                       -14.0, 14.0, -16.0, 16.0, -18.0, 18.0,
                       -20.0, 20.0, 0.0]
    assert plan["points"][0]["pi_frequency_mhz"] == 4367.292
    assert plan["points"][-1]["pi_frequency_mhz"] == 4367.292
    assert len({p["name"] for p in plan["points"]}) == 22


def test_reference_config_changes_only_park_pi_frequency_from_common_baseline():
    m = importlib.import_module(MODULE)
    base = {"ff_park_gain": -25146, "read_pulse_gain": 1880,
            "qubit_pi_freq": 4367.292, "reset_pi_freq": 4367.292,
            "qubit_pi_gain": 13500, "read_pulse_freq": 6933.026}
    center = m.reference_config(base, 4367.292)
    shifted = m.reference_config(base, 4373.292)
    assert base["read_pulse_gain"] == 1880
    assert center["read_pulse_gain"] == shifted["read_pulse_gain"] == 940
    assert center["ff_park_gain"] == shifted["ff_park_gain"] == -25146
    assert shifted["qubit_pi_freq"] == shifted["reset_pi_freq"] == 4373.292
    assert shifted["qubit_pi_gain"] == center["qubit_pi_gain"] == 13500
    assert shifted["read_pulse_freq"] == center["read_pulse_freq"] == 6933.026
    for key in set(center) | set(shifted):
        if key not in {"qubit_pi_freq", "reset_pi_freq"}:
            assert center.get(key) == shifted.get(key)


def test_raw_iq_is_saved_and_degenerate_fit_is_recorded_without_stopping_sweep(tmp_path):
    m = importlib.import_module(MODULE)
    def raw(excited_i):
        pattern = (np.arange(100, dtype=np.int64) % 21 - 10) if excited_i else np.zeros(100, dtype=np.int64)
        return {context: {state: {"i": pattern + value,
                                  "q": np.zeros(100, dtype=np.int64)}
                          for state, value in (("ground", 0), ("excited", excited_i))}
                for context in ("payload", "loop")}
    options = {"ground_confidence_fidelity": 0.7, "qua_threshold_steps": 100}
    bad = m.fit_saved_reference(tmp_path / "bad", {"qubit_pi_freq": 4357.292},
                                raw(0), options, {"point": "bad"})
    assert bad["accepted"] is False
    assert "fit" in bad["rejection_reason"].lower()
    assert (tmp_path / "bad" / "fit_failure.json").is_file()
    with np.load(tmp_path / "bad" / "calibration_raw.npz") as saved:
        assert saved["loop_excited_i"].tolist() == [0] * 100
    good = m.fit_saved_reference(tmp_path / "good", {"qubit_pi_freq": 4367.292},
                                 raw(100), options, {"point": "good"})
    assert good["accepted"] is True
    assert (tmp_path / "good" / "calibration_raw.npz").is_file()
    assert (tmp_path / "good" / "calibration.json").is_file()
