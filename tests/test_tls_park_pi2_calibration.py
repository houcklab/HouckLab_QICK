"""Pure analysis checks for the park-only pi/2 calibration."""

import importlib
import math

import pytest


cal = importlib.import_module(
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSParkPi2Calibration")


def test_choose_frequency_uses_largest_repeatable_iq_displacement():
    rows = [
        {"offset_mhz": -2., "gain": 6000, "mean_i": 100., "mean_q": 0.},
        {"offset_mhz": -2., "gain": 12000, "mean_i": 900., "mean_q": 0.},
        {"offset_mhz": 0., "gain": 6000, "mean_i": 400., "mean_q": 0.},
        {"offset_mhz": 0., "gain": 12000, "mean_i": 2100., "mean_q": 100.},
    ]
    result = cal.choose_frequency(rows, baseline=0j)
    assert result["offset_mhz"] == 0.
    assert result["gain"] == 12000
    assert result["valid"]


def test_rabi_fit_from_normalized_iq_finds_pi_and_pi2():
    rows = [{"gain": gain,
             "response": math.sin(math.pi * gain / (2 * 13500)) ** 2}
            for gain in range(0, 30001, 1500)]
    result = cal.fit_rabi_iq(rows)
    assert result["valid"]
    assert result["pi_gain"] == pytest.approx(13500, abs=1500)
    assert result["pi2_gain"] == pytest.approx(6750, abs=1500)


def test_plan_omits_t1_scout_and_echo_map():
    p = cal.plan()
    assert p["fresh_t1_scan"] is False
    assert p["wide_echo_map"] is False
    assert p["bias"] == "q3 park"
