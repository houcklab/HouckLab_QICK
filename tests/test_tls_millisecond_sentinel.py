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
