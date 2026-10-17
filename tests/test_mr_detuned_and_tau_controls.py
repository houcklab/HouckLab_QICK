"""
drive_detuned and tau_offset Modified-Ramsey controls (F39). Hardware-free.

drive_detuned at the default +df adds a common phase 2*pi*df*tau = k*pi (k odd) to both
branches: it INVERTS the parity -> state mapping at about full contrast (a second flip
control), it does not degrade it. A tau off the pi condition by 25% keeps most of the
contrast, so it is no null either. tau_offset therefore defaults to the even harmonic
tau = (k+1)/(2 df) next to the programmed k/(2 df), a predicted null; in the symmetric
scheme the finite pulses move the null a few % below it, so the predicted zero is solved
for. Any explicit fraction applies to the programmed tau (it respects k).
compare_parity_controls judges a predicted inversion like flip_final_pi2 (unless the
active-reset pi at the detuned drive is predicted to fail) and a predicted tau null like
echo_null.
"""

import numpy as np
import pytest

from qicklab.analysis.modified_ramsey import compare_parity_controls
from qicklab.experiments.modified_ramsey import (
    DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO,
    DRIVE_DETUNED_MIN_RESET_PI_TRANSFER,
    ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO,
    build_control_variants,
    predict_parity_mapping,
    predict_pi_transfer,
)

DF = 2.7


def _base(sigma, k, symmetric, df=DF, reset=False):
    return {
        "use_active_reset": reset,
        "f_ge": 4186.7,
        "df": df,
        "sigma": sigma,
        "symmetric_ramsey": symmetric,
        "ramsey_tau_us": k / (2 * df),
        "max_drive_bandwidth_ratio": 1.4,
        "pi2_gain": 1200,
        "pi_gain": 2400,
    }


def _variants(base, **kw):
    include = ("parity", "tau_offset", "drive_detuned")
    return {v["control_type"]: v for v in build_control_variants(base, include=include, **kw)}


@pytest.mark.parametrize(
    "df, sigma, k, symmetric, expected_ratio",
    [
        (1.0, 0.04, 1, True, -0.972),  # main 0.995, detuned 0.967 inverted
        (1.0, 0.04, 1, False, -0.972),  # standard: 0.988 -> 0.961 inverted
        (0.5, 0.1, 3, False, -0.966),
        (DF, 0.1, 5, False, -1.000),
    ],
)
def test_drive_detuned_default_is_an_inverted_mapping(df, sigma, k, symmetric, expected_ratio):
    by = _variants(_base(sigma, k, symmetric, df=df))
    det = by["drive_detuned"]
    main = by["parity"]["predicted_mapping"]
    pred = det["predicted_mapping"]
    ratio = (pred["p_e_upper"] - pred["p_e_lower"]) / (main["p_e_upper"] - main["p_e_lower"])
    assert abs(ratio - expected_ratio) < 2e-3, ratio
    assert det["inverted_mapping_expected"] is True
    assert det["cfg"]["mr_inverted_mapping_expected"] is True
    assert abs(det["cfg"]["mr_predicted_contrast_ratio"] - ratio) < 1e-12
    assert f"a common phase {float(k):.2f} pi" in det["expected"]
    assert "inverted mapping at near-full contrast" in det["expected"]
    assert "degraded" not in det["expected"]
    assert det["inverted_mapping_reason"] == ""
    assert "mr_predicted_reset_pi_transfer" not in det["cfg"]  # no active reset
    # drive_detuned is no null: it never carries a null verdict
    assert det["null_control_valid"] is None and "mr_null_control_valid" not in det["cfg"]


def test_drive_detuned_bandwidth_starved_is_informational():
    # sigma 0.1 us, df 2.7 MHz, k = 5, symmetric: the detuned branches cannot be rotated,
    # the predicted contrast collapses (+0.05x), so it is no clean inversion.
    det = _variants(_base(0.1, 5, True))["drive_detuned"]
    assert det["inverted_mapping_expected"] is False
    assert abs(det["cfg"]["mr_predicted_contrast_ratio"]) < 0.1
    assert "not a clean inversion" in det["expected"]
    assert det["inverted_mapping_reason"].startswith("not predicted to invert")
    assert det["cfg"]["mr_predicted_contrast_ratio"] > -DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO


def test_drive_detuned_custom_detuning_follows_the_common_phase():
    # det = df/2 at k = 1 adds pi/2: no inversion, roughly no contrast in one quadrature.
    base = _base(0.04, 1, False, df=1.0)
    det = _variants(base, detuning_mhz=0.5)["drive_detuned"]
    assert "a common phase 0.50 pi" in det["expected"]
    assert det["inverted_mapping_expected"] is False
    # det = 2 df adds 2 pi: the mapping is back to the parity run's sign
    det = _variants(base, detuning_mhz=2.0)["drive_detuned"]
    assert det["cfg"]["mr_predicted_contrast_ratio"] > 0


def test_tau_offset_default_is_the_even_harmonic_null():
    # Standard scheme, k = 3: tau = 4/(2 df), predicted residual 0.04x the parity contrast.
    by = _variants(_base(0.04, 3, False))
    tau = by["tau_offset"]
    assert abs(tau["cfg"]["ramsey_tau_us"] - 4 / (2 * DF)) < 1e-12
    assert abs(tau["cfg"]["mr_control_tau_offset_frac"] - 1 / 3) < 1e-12
    assert tau["null_control_valid"] is True and tau["null_invalid_reason"] == ""
    assert tau["cfg"]["mr_null_control_valid"] is True
    ratio = tau["cfg"]["mr_predicted_residual_ratio"]
    assert ratio < ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO and abs(ratio - 0.040) < 2e-3
    assert "even harmonic" in tau["expected"] and "(k = 3)" in tau["expected"]
    # base cfg without ramsey_tau_us: k = 1, tau = 2/(2 df)
    base = _base(0.04, 1, False)
    del base["ramsey_tau_us"]
    tau = _variants(base)["tau_offset"]
    assert abs(tau["cfg"]["ramsey_tau_us"] - 2 / (2 * DF)) < 1e-12
    assert tau["null_control_valid"] is True


@pytest.mark.parametrize(
    "df, sigma, k, tau_solved_us, even_ratio",
    [
        (DF, 0.04, 3, 0.7109, 0.259),
        (DF, 0.05, 5, 1.0756, 0.311),
        (DF, 0.1, 5, 1.0623, 0.439),
        (1.0, 0.04, 1, 0.9676, 0.102),
        (0.5, 0.1, 1, 1.9195, 0.127),
    ],
)
def test_tau_offset_symmetric_solves_the_predicted_null(df, sigma, k, tau_solved_us, even_ratio):
    # Symmetric: the finite pulses lengthen the effective phase time, so the even harmonic
    # (k+1)/(2 df) keeps 0.1-0.45x the parity contrast (informational above 0.2x, e.g. at the
    # CSTQ03 df = 2.7 MHz). The solved zero a few % below it is a predicted null everywhere.
    base = _base(sigma, k, True, df=df)
    base["max_drive_bandwidth_ratio"] = 1e9
    tau = _variants(base)["tau_offset"]
    cfg = tau["cfg"]
    assert abs(cfg["ramsey_tau_us"] - tau_solved_us) < 5e-4, cfg["ramsey_tau_us"]
    assert cfg["ramsey_tau_us"] < (k + 1) / (2 * df)
    assert cfg["mr_predicted_residual_ratio"] < 1e-3
    assert tau["null_control_valid"] is True and cfg["mr_null_control_valid"] is True
    assert "predicted zero of the parity contrast" in tau["expected"]
    # the even harmonic itself, at the same settings, is what the solve replaces
    off = -df / 2
    main_c = predict_parity_mapping(df, sigma, k / (2 * df), off, final_pi2_phase_deg=90)
    even_c = predict_parity_mapping(df, sigma, (k + 1) / (2 * df), off, final_pi2_phase_deg=90)
    assert abs(even_c["contrast"] / main_c["contrast"] - even_ratio) < 2e-3
    # robustness: a 1% df error keeps the solved tau well inside the 0.2x null limit
    df_err = 1.01 * df
    off_err = -df_err / 2
    main_err = predict_parity_mapping(df_err, sigma, k / (2 * df), off_err, final_pi2_phase_deg=90)
    null_err = predict_parity_mapping(
        df_err, sigma, cfg["ramsey_tau_us"], off_err, final_pi2_phase_deg=90
    )
    assert null_err["contrast"] / main_err["contrast"] < 0.11
    # an explicit fraction is not solved for
    assert "predicted zero" not in _variants(base, tau_offset_frac=0.25)["tau_offset"]["expected"]


def test_predict_pi_transfer():
    assert abs(predict_pi_transfer(0.04, 0.0) - 1.0) < 1e-9
    # 1 and 2 MHz off a sigma = 0.04 us pi: the standard drive_detuned branches at df = 1
    assert abs(predict_pi_transfer(0.04, -1.0) - 0.945) < 2e-3
    assert abs(predict_pi_transfer(0.04, -2.0) - 0.795) < 2e-3
    assert abs(predict_pi_transfer(0.04, 2.0) - predict_pi_transfer(0.04, -2.0)) < 1e-12


@pytest.mark.parametrize(
    "df, sigma, k, symmetric, transfer, decisive",
    [
        (1.0, 0.04, 1, False, 0.795, False),  # branches 1 and 2 MHz off the reset pi
        (1.0, 0.04, 1, True, 0.880, False),  # 0.5 and 1.5 MHz off
        (0.5, 0.1, 3, False, 0.696, False),
        (0.5, 0.04, 1, True, 0.969, True),  # short pulses: the reset pi still works
    ],
)
def test_drive_detuned_with_active_reset_needs_a_working_reset_pi(
    df, sigma, k, symmetric, transfer, decisive
):
    # With use_active_reset the corrective pi plays at the detuned drive; when it is
    # predicted to fail, carryover could fail the flip-like checks for non-parity reasons,
    # so the control stays informational even though the mapping is predicted inverted.
    det = _variants(_base(sigma, k, symmetric, df=df, reset=True))["drive_detuned"]
    cfg = det["cfg"]
    assert cfg["mr_predicted_contrast_ratio"] <= -DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO
    assert abs(cfg["mr_predicted_reset_pi_transfer"] - transfer) < 2e-3
    assert det["inverted_mapping_expected"] is decisive
    assert cfg["mr_inverted_mapping_expected"] is decisive
    if decisive:
        assert det["inverted_mapping_reason"] == ""
    else:
        assert transfer < DRIVE_DETUNED_MIN_RESET_PI_TRANSFER
        assert det["inverted_mapping_reason"].startswith("the active-reset pi plays at the detuned")
        assert "reset pi is off-resonant" in det["expected"]
        # the comparison reports why it is informational
        d = _rec("drive_detuned", seed=2, occ1=0.8, rate=100.0)
        d["inverted_mapping_expected"] = False
        d["inverted_mapping_reason"] = det["inverted_mapping_reason"]
        e = compare_parity_controls(_rec(seed=1, occ1=0.8, rate=100.0), [d])["controls"][0]
        assert e["checked"] is None and e["note"].startswith("the active-reset pi")
    # without active reset the same settings are decisive
    plain = _variants(_base(sigma, k, symmetric, df=df))["drive_detuned"]
    assert plain["inverted_mapping_expected"] is True


def test_tau_offset_fraction_respects_k():
    # Before F39 the offset was applied to 1/(2 df), ignoring k.
    base = _base(0.04, 3, False)
    tau = _variants(base, tau_offset_frac=0.25)["tau_offset"]
    assert abs(tau["cfg"]["ramsey_tau_us"] - 1.25 * 3 / (2 * DF)) < 1e-12
    assert abs(tau["cfg"]["mr_control_tau_offset_frac"] - 0.25) < 1e-12
    # At k = 1 a 25% offset (phase 1.25 pi) keeps most of the contrast (0.72x): not a null.
    tau = _variants(_base(0.04, 1, False), tau_offset_frac=0.25)["tau_offset"]
    assert abs(tau["cfg"]["ramsey_tau_us"] - 1.25 / (2 * DF)) < 1e-12
    assert tau["null_control_valid"] is False
    main = predict_parity_mapping(DF, 0.04, 1 / (2 * DF), 0.0, final_pi2_phase_deg=180)
    assert tau["cfg"]["mr_predicted_contrast"] > 0.5 * main["contrast"]


def _rec(control_type=None, lag=1.0, seed=0, hmm=None, occ1=0.5, amplitude=0.5, rate=None):
    boot = np.random.default_rng(seed).normal(lag, 0.05, 1000)
    if hmm is None:
        hmm = {"identifiable": True}
        if rate is not None:
            hmm.update(gamma01_hz=rate, gamma10_hz=rate, gamma01_err_hz=5.0, gamma10_err_hz=5.0)
    d = {
        "label": control_type or "parity",
        "hmm": hmm,
        "acf": {
            "amplitude": amplitude,
            "lag_covariance_sum": {
                "available": True,
                "value": lag,
                "boot": boot,
                "max_lag": 10,
                "reason": "",
            },
        },
        "occupancy_state1": occ1,
    }
    if control_type:
        d["control_type"] = control_type
    return d


def test_compare_judges_predicted_inversion_like_flip():
    main = _rec(seed=1, occ1=0.8, rate=100.0)
    det = _rec("drive_detuned", seed=2, occ1=0.2, rate=100.0)
    det["inverted_mapping_expected"] = True
    out = compare_parity_controls(main, [det])
    (entry,) = out["controls"]
    assert entry["checked"] is True and entry["verdict"] == "passed", entry
    assert out["decisive_controls"] == ["drive_detuned"] and out["all_expected"]

    # occupancy not inverted: fails
    bad = _rec("drive_detuned", seed=2, occ1=0.8, rate=100.0)
    bad["inverted_mapping_expected"] = True
    assert compare_parity_controls(main, [bad])["controls"][0]["checked"] is False
    # telegraph gone (amplitude ratio 0.1 < 0.25): fails
    gone = _rec("drive_detuned", seed=2, occ1=0.2, rate=100.0, amplitude=0.05)
    gone["inverted_mapping_expected"] = True
    assert compare_parity_controls(main, [gone])["controls"][0]["checked"] is False

    # without the prediction (older records) or predicted not inverted: informational
    for flag in (None, False):
        d = _rec("drive_detuned", seed=2, occ1=0.8, rate=100.0)
        if flag is not None:
            d["inverted_mapping_expected"] = flag
        e = compare_parity_controls(main, [d])["controls"][0]
        assert e["checked"] is None and e["verdict"] == "informational"
        assert ("not predicted to invert" in e["note"]) is (flag is False)


def test_compare_judges_predicted_tau_null_like_echo():
    main = _rec(seed=1)
    null = _rec("tau_offset", lag=0.02, seed=2)
    null["null_control_valid"] = True
    out = compare_parity_controls(main, [null])
    (entry,) = out["controls"]
    assert entry["checked"] is True and entry["verdict"] == "passed", entry
    # the note names the predicted null, which is the even harmonic only in the standard scheme
    assert "predicted-null tau" in entry["note"] and "solved zero" in entry["note"]
    # tau_offset never sets the echo-specific summary flag
    assert out["null_control_valid"] is None and out["notes"] == []

    survived = _rec("tau_offset", lag=0.8, seed=2)
    survived["null_control_valid"] = True
    entry = compare_parity_controls(main, [survived])["controls"][0]
    assert entry["checked"] is False and "survived the predicted-null tau" in entry["note"]

    # not a predicted null, or no prediction: informational, even with a surviving telegraph
    for flag in (None, False):
        d = _rec("tau_offset", lag=0.8, seed=2)
        if flag is not None:
            d["null_control_valid"] = flag
            d["null_invalid_reason"] = "not a null at these settings: predicted ..."
        e = compare_parity_controls(main, [d])["controls"][0]
        assert e["checked"] is None and e["verdict"] == "informational"
        assert e["note"].startswith("not a null at these settings") is (flag is False)
