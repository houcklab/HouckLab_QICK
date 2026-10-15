"""estimate_noise_floor replaces the two inline MAD noise floors (F05 part 1b) with identical numbers.

The legacy inline formulas of auto_coherence._spec_peak_snr and
zero_span_checks.contrast_from_sweeps are copied here verbatim and compared, bit for bit, with
the refactored functions on random traces (Gaussian, heavy-tailed, with peaks) and on the
degenerate traces that take each formula's zero-MAD fallback.
"""

import numpy as np
import pytest

from qicklab.analysis.fitting import estimate_noise_floor
from qicklab.analysis.zero_span_checks import contrast_from_sweeps
from qicklab.runs.auto_coherence import _spec_peak_snr


def _legacy_spec_peak_snr(avgamp0, peak_info):
    avgamp0 = np.asarray(avgamp0, dtype=float)
    if avgamp0.size == 0:
        return 0.0
    baseline = float(np.median(avgamp0))
    mad = float(np.median(np.abs(avgamp0 - baseline)))
    noise = 1.4826 * mad
    if noise < 1e-12:
        noise = float(np.std(avgamp0)) or 1e-12
    peak_vals = peak_info.get("peak_vals") if peak_info else None
    if peak_vals is not None and len(peak_vals) > 0:
        peak = float(np.max(peak_vals))
    else:
        peak = float(np.max(avgamp0))
    return (peak - baseline) / noise


def _legacy_contrast_snr(contrast):
    idx = int(np.argmax(contrast))
    med = float(np.median(contrast))
    mad = float(np.median(np.abs(contrast - med)))
    noise_floor = 1.4826 * mad if mad > 0 else (med if med > 0 else 1.0)
    return float(contrast[idx] / noise_floor) if noise_floor > 0 else np.inf


def _random_traces():
    rng = np.random.default_rng(5)
    for n in (1, 2, 3, 7, 50, 201, 1000):
        for scale in (1e-15, 1e-6, 1.0, 1e4):
            yield scale * rng.normal(size=n)
            yield scale * rng.standard_t(2, size=n)
            y = scale * rng.normal(size=n)
            y[rng.integers(0, n, size=max(1, n // 20))] += 30 * scale
            yield y


def _degenerate_traces():
    yield np.zeros(10)
    yield np.full(10, 3.5)
    yield np.r_[np.zeros(7), 1.0, 2.0, 5.0]  # MAD 0, std > 0
    yield np.r_[np.full(7, 2.0), 1.0, 2.5, 9.0]  # MAD 0, median > 0
    yield np.r_[np.zeros(6), 1e-14, 2e-14, 3e-14, 4e-14]  # MAD sigma 0, tiny std
    yield np.r_[1.0, 1.0 + 1e-13 * np.arange(1, 10)]  # 0 < MAD sigma < 1e-12


@pytest.mark.parametrize("kind", ["random", "degenerate"])
def test_spec_peak_snr_identical_to_inline_formula(kind):
    traces = list(_random_traces() if kind == "random" else _degenerate_traces())
    for y in traces:
        for peak_info in (None, {"peak_vals": y[:1]}, {"peak_vals": []}):
            old = _legacy_spec_peak_snr(y, peak_info)
            new = _spec_peak_snr(y, peak_info)
            assert new == old or (np.isnan(new) and np.isnan(old)), (y, old, new)


@pytest.mark.parametrize("kind", ["random", "degenerate"])
def test_contrast_snr_identical_to_inline_formula(kind):
    traces = list(_random_traces() if kind == "random" else _degenerate_traces())
    for y in traces:
        contrast = np.abs(y)
        freqs = np.arange(contrast.size, dtype=float)
        out = contrast_from_sweeps(freqs, contrast.astype(complex), np.zeros(contrast.size))
        assert out["contrast_snr"] == _legacy_contrast_snr(contrast), contrast


def test_estimate_noise_floor_matches_inline_mad():
    for y in _random_traces():
        baseline, sigma = estimate_noise_floor(y)
        mad = float(np.median(np.abs(y - np.median(y))))
        assert baseline == float(np.median(y))
        if mad > 0:
            assert sigma == 1.4826 * mad


def test_zero_mad_hook():
    y = np.r_[np.full(7, 2.0), 1.0, 2.5, 9.0]
    assert estimate_noise_floor(y)[1] == float(np.std(y))
    assert estimate_noise_floor(y, zero_mad=lambda b: 10 * b) == (2.0, 20.0)
    # the hook is used only when the MAD is zero
    z = np.arange(10.0)
    assert estimate_noise_floor(z, zero_mad=lambda b: -1.0) == estimate_noise_floor(z)
