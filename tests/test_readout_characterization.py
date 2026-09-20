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


def test_rabi_amplitude_fit_recovers_pi_amplitude():
    import numpy as np
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
        readout_characterization as rc,
    )

    rng = np.random.default_rng(0)
    gains = np.linspace(500, 30000, 41)
    a_pi = 11800.0
    response = 0.2 + 0.45 * (1 - np.cos(np.pi * gains / a_pi)) + rng.normal(0, 0.01, gains.size)
    fit = rc.fit_rabi_amplitude(gains, response)
    assert abs(fit["rabi_pi_amplitude"] - a_pi) < 200.0
    assert fit["inside_swept_range"] is True
    assert fit["rabi_fit_contrast"] > 0.5


def test_sweet_spot_verdict_accepts_a_maximum_and_rejects_a_slope():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
        readout_characterization as rc,
    )

    extremum = [
        {"bias": -25946, "f_q_GHz": 4.365571}, {"bias": -25546, "f_q_GHz": 4.367042},
        {"bias": -25146, "f_q_GHz": 4.367522}, {"bias": -24746, "f_q_GHz": 4.367007},
        {"bias": -24346, "f_q_GHz": 4.365496},
    ]
    verdict = rc.sweet_spot_verdict(extremum, -25146)
    assert verdict["is_extremum"] is True
    assert verdict["all_flanking_same_side"] is True

    sloped = [dict(row) for row in extremum]
    sloped[3]["f_q_GHz"] = 4.368300
    off = rc.sweet_spot_verdict(sloped, -25146)
    assert off["is_extremum"] is False
    assert off["extremum_bias_observed"] == -24746


def test_step1b_report_keeps_unmeasured_fields_null():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
        readout_characterization as rc,
    )

    base = rc.step1_report(
        fr_ground_mhz=6933.288274, fr_excited_mhz=6932.817060,
        kappa_total_mhz=0.371187, fq_mhz=4366.958394, dc_coordinate=-25146,
        readout_gain_dac=472, lower_power_gain_dac=237,
        fr_lower_power_mhz=6933.297273, source="unit test", notes="",
    )
    report = rc.step1b_report(
        base_report=base, f_ef_ghz=None, fef_mode="two_photon_inconclusive",
        sweet_spot_evidence=[{"bias": -25146, "f_q_GHz": 4.366958}],
        sweet_spot_check={"is_extremum": True}, pi_calibration={"rabi_pi_amplitude": 11800.0},
    )
    assert report["f_ef_GHz"] is None
    assert report["f_two_photon_02_GHz"] is None
    assert report["kappa_external_MHz_FWHM"] is None
    assert report["dc_bias_V"] is None
    assert report["fef_mode"] == "two_photon_inconclusive"
    assert report["passes_linear_regime_check"] is True


def test_fit_dip_in_window_finds_a_narrow_line_in_a_narrow_window():
    import numpy as np
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
        readout_characterization as rc,
    )

    freq = np.arange(4268.3, 4288.3 + 0.25, 0.25)
    rng = np.random.default_rng(3)
    y = 1.40 + 0.0004 * (freq - 4278.3) + rng.normal(0, 0.010, freq.size)
    y -= 0.090 / (1.0 + ((freq - 4278.30) / 0.85) ** 2)
    fit = rc.fit_dip_in_window(freq, y, expected_mhz=4278.3)
    assert fit is not None
    assert abs(fit["centre_MHz"] - 4278.30) < 0.15
    assert fit["snr"] > 4.0
    assert fit["hwhm_MHz"] > 0.5
    assert fit["inside_window"] is True

    flat = 1.40 + rng.normal(0, 0.010, freq.size)
    weak = rc.fit_dip_in_window(flat, flat, expected_mhz=4278.3)
    assert weak is None or weak["snr"] < 4.0


def test_extrapolate_zero_power_removes_a_stark_shift():
    import numpy as np
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
        readout_characterization as rc,
    )

    gains = np.array([15000.0, 20000.0, 25000.0])
    centres = 4279.50 - 2.0e-9 * gains ** 2
    out = rc.extrapolate_zero_power(gains, centres)
    assert abs(out["zero_power_MHz"] - 4279.50) < 0.01
    assert out["n"] == 3
    single = rc.extrapolate_zero_power([25000.0], [4278.3])
    assert single["zero_power_MHz"] == 4278.3
    assert "note" in single
