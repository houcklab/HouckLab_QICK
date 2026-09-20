from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import readout_characterization as rc


def test_q3_step1_runner_defaults_to_a_4p1ghz_operating_point():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import ReadoutCharacterization as runner
    settings = runner.runtime_settings({})
    assert settings["target_frequency_ghz"] == 4.1
    assert settings["target_gain_dac"] is None
    assert settings["readout_shots"] == 300
    assert settings["qubit_spec_points"] == 161
    assert settings["fef_mode"] == "unmeasured"
    assert runner.qubit_spec_drive_config(settings) == {
        "qubit_pulse_style": "const",
        "qubit_gain": 10000,
        "qubit_length": 1.0,
    }


def test_step1_report_keeps_unmeasured_quantities_explicitly_null():
    report = rc.step1_report(
        fr_ground_mhz=6933.100,
        fr_excited_mhz=6932.400,
        kappa_total_mhz=1.25,
        fq_mhz=4100.0,
        dc_coordinate=-15933.0,
        readout_gain_dac=1880,
        lower_power_gain_dac=940,
    )
    assert report["f_r_ground_GHz"] == 6.9331
    assert report["f_r_excited_GHz"] == 6.9324
    assert report["kappa_total_MHz_FWHM"] == 1.25
    assert report["kappa_external_MHz_FWHM"] is None
    assert report["kappa_internal_MHz_FWHM"] is None
    assert report["f_ef_GHz"] is None
    assert report["dc_bias_V"] is None
    assert report["readout_power_dBm"] is None
    assert report["dc_bias_coordinate_DAC"] == -15933.0


def test_step1_power_check_requires_shift_smaller_than_tenth_linewidth():
    passing = rc.low_power_check(fr_ground_mhz=6933.000, fr_lower_power_mhz=6933.100,
                                 kappa_total_mhz=1.10)
    failing = rc.low_power_check(fr_ground_mhz=6933.000, fr_lower_power_mhz=6933.111,
                                 kappa_total_mhz=1.10)
    assert passing["passes_linear_regime_check"] is True
    assert failing["passes_linear_regime_check"] is False
