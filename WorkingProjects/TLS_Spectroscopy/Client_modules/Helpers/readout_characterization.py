"""Pure helpers for the raw-value Step-1 readout characterisation report.

The helpers deliberately do not infer Purcell, chi, coupling, attenuation, or
anharmonicity.  Those require measurements or conventions beyond Step 1.
"""

from __future__ import annotations


def low_power_check(*, fr_ground_mhz: float, fr_lower_power_mhz: float,
                    kappa_total_mhz: float) -> dict:
    """Return the documented 6 dB linear-regime check in ordinary MHz."""
    shift = abs(float(fr_lower_power_mhz) - float(fr_ground_mhz))
    threshold = 0.1 * abs(float(kappa_total_mhz))
    return {
        "power_check_6dB_shift_MHz": shift,
        "power_check_limit_MHz": threshold,
        "passes_linear_regime_check": bool(shift < threshold),
    }


def step1_report(*, fr_ground_mhz: float, fr_excited_mhz: float,
                 kappa_total_mhz: float, fq_mhz: float, dc_coordinate: float,
                 readout_gain_dac: int, lower_power_gain_dac: int,
                 fr_lower_power_mhz: float | None = None, source: str | None = None,
                 notes: str = "") -> dict:
    """Build a unit-explicit raw report without fabricating unavailable values."""
    report = {
        "f_r_ground_GHz": round(float(fr_ground_mhz) / 1e3, 9),
        "f_r_excited_GHz": round(float(fr_excited_mhz) / 1e3, 9),
        "kappa_total_MHz_FWHM": abs(float(kappa_total_mhz)),
        "kappa_external_MHz_FWHM": None,
        "kappa_internal_MHz_FWHM": None,
        "f_q_GHz": round(float(fq_mhz) / 1e3, 9),
        "f_ef_GHz": None,
        "dc_bias_V": None,
        "dc_bias_coordinate_DAC": float(dc_coordinate),
        "readout_power_dBm": None,
        "readout_attenuation_dB": None,
        "readout_gain_DAC": int(readout_gain_dac),
        "readout_gain_6dB_lower_DAC": int(lower_power_gain_dac),
        "source": source,
        "notes": notes,
    }
    if fr_lower_power_mhz is not None:
        report.update(low_power_check(
            fr_ground_mhz=fr_ground_mhz,
            fr_lower_power_mhz=fr_lower_power_mhz,
            kappa_total_mhz=kappa_total_mhz,
        ))
    else:
        report.update({
            "power_check_6dB_shift_MHz": None,
            "power_check_limit_MHz": None,
            "passes_linear_regime_check": None,
        })
    return report


def fit_rabi_amplitude(gains, response):
    import numpy as np
    from scipy.optimize import curve_fit

    a = np.asarray(gains, dtype=float)
    y = np.asarray(response, dtype=float)
    good = np.isfinite(a) & np.isfinite(y)
    a, y = a[good], y[good]
    if a.size < 6:
        raise ValueError("rabi amplitude fit needs at least 6 usable points")

    def model(x, offset, contrast, a_pi, phase):
        return offset + 0.5 * contrast * (1.0 - np.cos(np.pi * (x - phase) / a_pi))

    span = float(a.max() - a.min())
    guesses = [float(a.max()), 0.5 * span, 0.25 * span]
    best = None
    for a_pi0 in guesses:
        try:
            p, cov = curve_fit(
                model, a, y,
                p0=[float(np.min(y)), float(np.ptp(y)), a_pi0, 0.0],
                bounds=([-np.inf, 0.0, 0.05 * span, -0.25 * span],
                        [np.inf, np.inf, 10.0 * span, 0.25 * span]),
                maxfev=40000,
            )
        except Exception:
            continue
        resid = float(np.sqrt(np.mean((y - model(a, *p)) ** 2)))
        if best is None or resid < best[2]:
            best = (p, cov, resid)
    if best is None:
        raise RuntimeError("rabi amplitude fit did not converge")
    p, cov, resid = best
    a_pi = float(p[2] + p[3])
    err = float(np.sqrt(abs(cov[2, 2]))) if cov is not None and np.all(np.isfinite(cov)) else None
    denom = float(np.ptp(y))
    return {
        "rabi_pi_amplitude": a_pi,
        "rabi_pi_amplitude_error": err,
        "rabi_fit_contrast": float(p[1]),
        "rabi_fit_offset": float(p[0]),
        "rabi_fit_rms_residual": resid,
        "rabi_fit_relative_residual": None if denom == 0 else resid / denom,
        "inside_swept_range": bool(a.min() <= a_pi <= a.max()),
    }


def sweet_spot_verdict(evidence, centre_bias):
    import numpy as np

    rows = [r for r in evidence if r.get("f_q_GHz") is not None]
    if len(rows) < 3:
        return {"is_extremum": None, "reason": "fewer than three usable bias points"}
    bias = np.asarray([float(r["bias"]) for r in rows])
    freq = np.asarray([float(r["f_q_GHz"]) for r in rows])
    order = np.argsort(bias)
    bias, freq = bias[order], freq[order]
    centre = int(np.argmin(np.abs(bias - float(centre_bias))))
    flanking = [i for i in range(len(bias)) if i != centre]
    shifts = {float(bias[i]): 1e3 * float(freq[i] - freq[centre]) for i in flanking}
    below = all(v < 0 for v in shifts.values())
    above = all(v > 0 for v in shifts.values())
    argext = int(np.argmax(freq)) if below else int(np.argmin(freq)) if above else None
    return {
        "is_extremum": bool(argext == centre) if argext is not None else False,
        "centre_bias": float(bias[centre]),
        "centre_f_q_GHz": float(freq[centre]),
        "flanking_shifts_MHz": shifts,
        "all_flanking_same_side": bool(below or above),
        "extremum_bias_observed": float(bias[int(np.argmax(freq))]),
        "max_abs_flanking_shift_MHz": float(max(abs(v) for v in shifts.values())),
        "reason": ("centre is the extremum and both flanks fall on one side"
                   if (below or above) and argext == centre
                   else "flanking points do not bracket the centre as an extremum"),
    }


def step1b_report(*, base_report, f_ef_ghz, fef_mode, sweet_spot_evidence,
                  sweet_spot_check, pi_calibration, excited_population_estimate=None,
                  two_photon_ghz=None, ef_candidates=None):
    report = dict(base_report)
    report["f_ef_GHz"] = None if f_ef_ghz is None else round(float(f_ef_ghz), 9)
    report["fef_mode"] = fef_mode
    report["f_two_photon_02_GHz"] = (None if two_photon_ghz is None
                                     else round(float(two_photon_ghz), 9))
    report["ef_candidate_peaks"] = ef_candidates
    report["sweet_spot_evidence"] = sweet_spot_evidence
    report["sweet_spot_check"] = sweet_spot_check
    report["pi_calibration"] = pi_calibration
    report["excited_population_estimate"] = excited_population_estimate
    return report
