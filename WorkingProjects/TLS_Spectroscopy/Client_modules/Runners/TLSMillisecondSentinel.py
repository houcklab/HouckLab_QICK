"""Time-resolved q3 loss-flank sentinel, experiment-only.

The active run is deliberately gated by a fresh passive scout and static
profiles. QICK resident streaming pauses at data-memory bank handshakes, so
per-shot host completion times are acquired rather than inventing a uniform
global sample clock. No production TLS scan or reset default is modified.
"""

import math

import numpy as np
from scipy.optimize import curve_fit

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeWidePassiveScan as wide,
    TLSWeakAfterglowScreen as weak,
)


PREFERRED_A_GHZ = 4.0947


def select_sites(rows):
    """Return strong, bidirectional A/B loss lines and one quiet C site."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row for row in rows}
    expected = {round(3.8 + .002 * i, 3) for i in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("sentinel requires one complete 251-point wide scout")
    candidate_lines = []
    for center in sorted(indexed):
        if not 3.83 <= center <= 4.27:
            continue
        groups = {
            "center": [round(center + .002 * i, 3) for i in (-1, 0, 1)],
            "left": [round(center - .002 * i, 3) for i in (4, 5, 6)],
            "right": [round(center + .002 * i, 3) for i in (4, 5, 6)],
        }
        if any(f not in indexed for group in groups.values() for f in group):
            continue
        depths = {}
        for name, suffix in (("combined", ""), ("up", "_scan_up"),
                             ("down", "_scan_down")):
            values = {label: [weak._survival(indexed[f], 25, suffix)
                              for f in fs] for label, fs in groups.items()}
            if any(not math.isfinite(v) for vs in values.values() for v in vs):
                break
            if values["center"][1] >= min(values["center"][0],
                                             values["center"][2]):
                break
            depths[name] = min(float(np.median(values["left"])),
                               float(np.median(values["right"]))) - float(
                                   np.mean(values["center"]))
        if (len(depths) == 3 and depths["combined"] >= .12 and
                min(depths["up"], depths["down"]) >= .08):
            candidate_lines.append({"center_ghz": center, "depth": depths["combined"],
                                    "depth_scan_up": depths["up"],
                                    "depth_scan_down": depths["down"]})
    if not candidate_lines:
        raise ValueError("no qualified first loss line")
    near_preferred = [x for x in candidate_lines if
                      abs(x["center_ghz"] - PREFERRED_A_GHZ) <= .006]
    a = max(near_preferred or candidate_lines,
            key=lambda x: min(x["depth_scan_up"], x["depth_scan_down"]))
    alternatives = [x for x in candidate_lines if
                    abs(x["center_ghz"] - a["center_ghz"]) >= .020 - 1e-9]
    if not alternatives:
        raise ValueError("no qualified second loss line at least 20 MHz from first")
    b = max(alternatives,
            key=lambda x: min(x["depth_scan_up"], x["depth_scan_down"]))
    controls = []
    for center in sorted(indexed):
        if (not 3.83 <= center <= 4.27 or
                min(abs(center - x["center_ghz"]) for x in candidate_lines) < .010):
            continue
        neighbors = [round(center + .002 * i, 3) for i in (-1, 0, 1)]
        if any(f not in indexed for f in neighbors):
            continue
        values = [weak._survival(indexed[f], 25, suffix)
                  for f in neighbors for suffix in ("", "_scan_up", "_scan_down")]
        if all(math.isfinite(x) and x >= .75 for x in values):
            controls.append({"center_ghz": center, "min_survival": min(values)})
    if not controls:
        raise ValueError("no clean control at least 10 MHz from loss sites")
    c = min(controls, key=lambda x: (abs(x["center_ghz"] - 4.060),
                                     -x["min_survival"]))
    return {"A": a, "B": b, "C": c}


def _loss_lorentzian(frequency_mhz, background, depth, center_mhz, hwhm_mhz):
    return background - depth / (1.0 +
                                 ((np.asarray(frequency_mhz) - center_mhz) /
                                  hwhm_mhz) ** 2)


def fit_static_profile(frequency_mhz, survival):
    frequency = np.asarray(frequency_mhz, dtype=float)
    values = np.asarray(survival, dtype=float)
    if (frequency.ndim != 1 or values.shape != frequency.shape or
            frequency.size < 7 or not np.all(np.isfinite(values)) or
            not np.all(np.diff(frequency) > 0)):
        raise ValueError("static profile needs seven or more ordered finite points")
    center_guess = float(frequency[np.argmin(values)])
    try:
        params, covariance = curve_fit(
            _loss_lorentzian, frequency, values,
            p0=(float(max(values)), max(float(max(values)-min(values)), .01),
                center_guess, 2.0),
            bounds=([0, 0, float(min(frequency)), .2],
                    [1.5, 1.5, float(max(frequency)), 10.0]),
            maxfev=20000)
    except (RuntimeError, ValueError) as exc:
        raise ValueError("Lorentzian static profile fit failed") from exc
    background, depth, center, width = map(float, params)
    near = float(_loss_lorentzian(center, *params))
    flanks = [_loss_lorentzian(center + offset, *params) for offset in (-6, 6)]
    contrast = float(min(flanks) - near)
    rmse = float(np.sqrt(np.mean((values - _loss_lorentzian(frequency, *params))**2)))
    return {"background": background, "depth": depth,
            "center_mhz": center, "hwhm_mhz": width,
            "contrast_6mhz": contrast, "fit_rmse": rmse,
            "covariance": np.asarray(covariance).tolist()}


def profile_gate(profile):
    contrast = float(profile["contrast_6mhz"])
    width = float(profile["hwhm_mhz"])
    passed = bool(math.isfinite(contrast) and contrast >= .15 and
                  math.isfinite(width) and .2 <= width <= 10.0)
    return {"passed": passed, "contrast_6mhz": contrast,
            "minimum_contrast": .15}


def make_flanks(profile):
    center = float(profile["center_mhz"])
    width = float(profile["hwhm_mhz"])
    depth = float(profile["depth"])
    offset = width / math.sqrt(3)
    def derivative(target):
        delta = target - center
        return 2 * depth * width**2 * delta / (delta**2 + width**2)**2
    minus, plus = center - offset, center + offset
    return {"A_minus_mhz": minus, "A_plus_mhz": plus,
            "slope_minus_per_mhz": derivative(minus),
            "slope_plus_per_mhz": derivative(plus)}


def integer_dac_targets(target_mhz, inverse_gain):
    """Quantize each physical target and its ±0.5-MHz dithers independently."""
    result = {}
    for name, mhz in target_mhz.items():
        value = float(mhz)
        base = int(np.rint(inverse_gain(value)))
        low = int(np.rint(inverse_gain(value - .5)))
        high = int(np.rint(inverse_gain(value + .5)))
        if not all(-32768 <= gain <= 32767 for gain in (base, low, high)):
            raise ValueError(f"{name} target/dither exceeds signed DAC range")
        if low == high or not (min(low, high) <= base <= max(low, high)):
            raise ValueError(f"{name} dither collapses on integer DAC grid")
        result[name] = {"target_mhz": value, "gain_dac": base,
                        "dither_minus_dac": low-base,
                        "dither_plus_dac": high-base}
    return result
