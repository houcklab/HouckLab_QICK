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
