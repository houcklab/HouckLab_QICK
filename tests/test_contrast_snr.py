"""Stage-1/2 contrast SNR from per-point standard errors (F45).

Before F45 stage 1's contrast_snr was the peak of |Z_on - Z_off| over the MAD of the
contrast curve itself (a shape ratio: a noiseless Lorentzian scored > 3) and no stage kept
an error bar. Now every point's mean complex response carries batch-means standard errors
of I and Q (and their covariance) from contiguous blocks of its time-ordered record;
contrast_snr = |Z_on - Z_off| / (se of the difference along its own direction), and the
largest per-point SNR is compared with the alpha threshold for a maximum over N points.
Synthetic data only.
"""

import json
import os

import h5py
import numpy as np
from scipy import stats

from qicklab.analysis.zero_span_checks import (
    complex_response_stats,
    contrast_from_sweeps,
    max_contrast_snr_threshold,
)
from qicklab.runs.zero_span_validation import (
    _mean_complex_response,
    run_contrast_vs_qubit_freq,
    run_static_contrast,
)

N_REPS = 2000
N_POINTS = 41


def _record(rng, z, sigma, n=N_REPS):
    return z.real + rng.normal(0, sigma, n), z.imag + rng.normal(0, sigma, n)


def _sweep(rng, z_on, z_off, sigma, n_blocks=20):
    """Per-point stats of drive-on and drive-off records -> contrast_from_sweeps."""
    stats = {"on": [], "off": []}
    for zon, zoff in zip(z_on, z_off):
        stats["on"].append(complex_response_stats(*_record(rng, zon, sigma), n_blocks=n_blocks))
        stats["off"].append(complex_response_stats(*_record(rng, zoff, sigma), n_blocks=n_blocks))

    def col(side, k):
        return np.array([s[k] for s in stats[side]])

    nb = min(col("on", 4).min(), col("off", 4).min())
    return contrast_from_sweeps(
        np.arange(len(z_on), dtype=float),
        col("on", 0),
        col("off", 0),
        se_on=col("on", 1) + 1j * col("on", 2),
        se_off=col("off", 1) + 1j * col("off", 2),
        cov_on=col("on", 3),
        cov_off=col("off", 3),
        dof=nb - 1,
    )


# --- complex_response_stats ---


def test_stats_mean_and_iid_se():
    rng = np.random.default_rng(1)
    I, Q = _record(rng, 1.0 - 2.0j, 0.8)
    z, se_I, se_Q, cov, n_b = complex_response_stats(I, Q)
    assert z == complex(np.mean(I), np.mean(Q))
    assert n_b == 20
    naive = 0.8 / np.sqrt(N_REPS)
    # 19-dof estimate of an iid se: within ~3 sigma of its ~16 % scatter
    assert 0.55 * naive < se_I < 1.45 * naive and 0.55 * naive < se_Q < 1.45 * naive
    assert abs(cov) < 0.5 * naive**2


def test_stats_correlated_record_se_exceeds_naive():
    """AR(1), phi = 0.9 (correlation time 10 samples, 100-sample blocks): the true se of
    the mean is sqrt((1 + phi) / (1 - phi)) = 4.4x the iid std/sqrt(N); batch means sees
    it, std/sqrt(N) would not."""
    rng = np.random.default_rng(2)
    phi, n = 0.9, N_REPS
    se_true = np.sqrt((1 + phi) / (1 - phi)) / np.sqrt(n)
    ratios = []
    for _ in range(40):
        e = rng.normal(0, np.sqrt(1 - phi**2), n)
        x = np.empty(n)
        x[0] = rng.normal()
        for k in range(1, n):
            x[k] = phi * x[k - 1] + e[k]
        _, se_I, _, _, _ = complex_response_stats(x, np.zeros(n))
        ratios.append(se_I / se_true)
        naive = np.std(x, ddof=1) / np.sqrt(n)
        assert se_I > 2.0 * naive
    # 100-sample blocks over a 10-sample correlation time: biased low by ~5 %
    assert 0.8 < np.sqrt(np.mean(np.square(ratios))) < 1.1


def test_stats_telegraph_on_a_diagonal_gives_iq_covariance():
    rng = np.random.default_rng(3)
    n = N_REPS
    flips = rng.random(n) < 1.0 / 50  # mean dwell 50 samples, blocks of 100
    s = np.cumsum(flips) % 2
    I = s + rng.normal(0, 0.1, n)
    Q = s + rng.normal(0, 0.1, n)
    _, se_I, se_Q, cov, _ = complex_response_stats(I, Q)
    assert cov / (se_I * se_Q) > 0.9


def test_stats_few_reps_fall_back_then_nan():
    rng = np.random.default_rng(4)
    I, Q = rng.normal(size=11), rng.normal(size=11)
    z, se_I, se_Q, cov, n_b = complex_response_stats(I, Q, n_blocks=20)
    assert n_b == 5 and np.isfinite(se_I) and np.isfinite(se_Q) and np.isfinite(cov)
    z, se_I, se_Q, cov, n_b = complex_response_stats(I[:3], Q[:3])
    assert np.isfinite(z) and np.isnan(se_I) and np.isnan(se_Q) and np.isnan(cov)
    z, se_I, _, _, n_b = complex_response_stats([], [])
    assert np.isnan(z.real) and np.isnan(se_I) and n_b == 0


def test_mean_complex_response_is_one_acquire():
    class _Exp:
        calls = 0

        def acquire(self, progress=False):
            self.calls += 1
            return {"I": np.array([1.0, 3.0]), "Q": np.array([2.0, 2.0])}

    e = _Exp()
    assert _mean_complex_response(e) == 2.0 + 2.0j and e.calls == 1


# --- threshold ---


def test_threshold_values_and_false_alarm_rate():
    # exact sigma: max of 41 Rayleigh draws exceeds 3.66 5 % of the time
    thr = max_contrast_snr_threshold(N_POINTS, 0.05)
    assert abs(thr - 3.656) < 0.01, thr
    assert max_contrast_snr_threshold(N_POINTS, 0.05, dof=19) > thr
    # sigma on 19 dof: snr^2 / 2 is F(2, 19)
    p = 1 - 0.95 ** (1 / N_POINTS)
    t19 = np.sqrt(2 * stats.f.isf(p, 2, 19))
    assert np.isclose(max_contrast_snr_threshold(N_POINTS, 0.05, dof=19), t19)
    assert max_contrast_snr_threshold(N_POINTS, 0.05, dof=1e6) - thr < 1e-3
    rng = np.random.default_rng(5)
    r = np.abs(rng.normal(size=(20000, N_POINTS)) + 1j * rng.normal(size=(20000, N_POINTS)))
    assert abs(np.mean(r.max(axis=1) > thr) - 0.05) < 0.01
    assert np.isnan(max_contrast_snr_threshold(0))


# --- contrast_from_sweeps ---


def test_pure_noise_sweep_is_not_significant():
    """No signal: contrast_snr_max is the max of 41 Rayleigh-like draws (~2-3.5), and the
    5 % flag fires on about 5 % of sweeps (more than nominal from the 19-dof ses only
    slightly, since the threshold uses those dof)."""
    rng = np.random.default_rng(6)
    z = np.full(N_POINTS, 0.3 + 0.1j)
    flags, maxes = [], []
    for _ in range(40):
        c = _sweep(rng, z, z, sigma=1.0)
        assert c["contrast_snr_method"] == "standard_error"
        flags.append(c["contrast_significant"])
        maxes.append(c["contrast_snr_max"])
    assert 2.0 < np.median(maxes) < 3.5, np.median(maxes)
    assert np.mean(flags) <= 0.15, np.mean(flags)


def test_injected_signal_snr_matches_truth():
    """True SNR = |signal| / sqrt(2 sigma^2 / N). Single sweeps scatter by the contrast noise
    (~13 % at the peak here) and the 19-dof se (~11 %), so check the average over sweeps at
    best_freq, and the se itself."""
    rng = np.random.default_rng(7)
    sigma = 1.0
    f = np.arange(N_POINTS, dtype=float)
    amp = 0.25
    sig = amp / (1 + 1j * (f - 20) / 3.0)
    z_off = np.full(N_POINTS, 0.5 + 0.0j)
    true_se = np.sqrt(2 * sigma**2 / N_REPS)
    true_snr = np.abs(sig) / true_se
    at_best, se_ratio = [], []
    for _ in range(10):
        c = _sweep(rng, z_off + sig, z_off, sigma)
        assert abs(c["best_freq"] - 20) <= 3
        assert c["contrast_significant"] is True
        assert c["contrast_snr_max"] > c["contrast_snr_threshold"]
        at_best.append(c["contrast_snr"] / true_snr[int(c["best_freq"])])
        se_ratio.append(np.median(c["contrast_se"]) / true_se)
    assert abs(np.mean(at_best) - 1) < 0.2, at_best
    assert abs(np.mean(se_ratio) - 1) < 0.1, se_ratio


def test_projection_uses_iq_covariance():
    """Noise along the 45-degree diagonal, difference along it: the diagonal-only se would
    be sqrt(2) too small."""
    z_on, z_off = np.array([1.0 + 1.0j]), np.array([0j])
    se = np.array([0.1 + 0.1j])
    with_cov = contrast_from_sweeps(
        [0.0], z_on, z_off, se_on=se, se_off=se, cov_on=[0.01], cov_off=[0.01]
    )
    no_cov = contrast_from_sweeps([0.0], z_on, z_off, se_on=se, se_off=se)
    assert np.isclose(with_cov["contrast_se"][0], np.sqrt(0.04))
    assert np.isclose(no_cov["contrast_se"][0], np.sqrt(0.02))
    assert np.isclose(with_cov["contrast_snr"], np.sqrt(2) / 0.2)


def test_scalar_baseline_se_broadcasts():
    c = contrast_from_sweeps(
        [0.0, 1.0], np.array([1.0, 0.0j]), np.zeros(2), se_on=np.array([0.1, 0.1]), se_off=0.1
    )
    assert np.isclose(c["contrast_se"][0], np.sqrt(0.02))


def test_without_se_the_value_is_flagged_peak_to_mad():
    f = np.linspace(99.0, 101.0, 201)
    z_off = 1.0 / (1 + 1j * (f - 100.0) / 0.05)
    z_on = 1.0 / (1 + 1j * (f - 100.05) / 0.05)
    c = contrast_from_sweeps(f, z_on, z_off)
    assert c["contrast_snr_method"] == "peak_to_mad"
    assert c["contrast_snr"] == c["contrast_peak_to_mad"] > 3.0
    assert c["contrast_significant"] is None and np.isnan(c["contrast_snr_max"])


# --- stage 1 / 2 sidecars and acquisition counts ---


class _CountingExp:
    def __init__(self, out_dir, n=200):
        self.cfg = {
            "qubit_gain": 200,
            "reps_per_chunk": n,
            "reps": n,
            "sample_period_us": 20.0,
            "read_pulse_freq": 100.0,
            "parity_drive_freq": 4000.0,
            "device": "TEST",
            "mode": "strobe",
        }
        self.n = n
        self.calls = 0
        self.rng = np.random.default_rng(8)
        self.fname = os.path.join(out_dir, "fake.h5")

    def set_qubit_gain(self, gain):
        self.cfg["qubit_gain"] = gain

    def acquire(self, progress=False):
        self.calls += 1
        level = 1.0 if self.cfg["qubit_gain"] > 0 else 0.0
        level *= np.exp(-((self.cfg["read_pulse_freq"] - 100.0) ** 2))
        return {
            "I": level + self.rng.normal(0, 0.8, self.n),
            "Q": self.rng.normal(0, 0.8, self.n),
            "t_us": np.arange(self.n) * 20.0,
        }


def _sidecar(d, stage):
    js = [f for f in os.listdir(d) if f.startswith(stage) and f.endswith(".json")]
    with open(os.path.join(d, js[0])) as fh:
        meta = json.load(fh)
    h5 = os.path.join(d, js[0].replace(".json", ".h5"))
    with h5py.File(h5, "r") as f:
        arrays = {k: f[k][()] for k in f.keys()}
    return meta["scalars"], arrays


def test_stage1_sidecar_has_se_and_same_acquire_count(tmp_path):
    d = str(tmp_path)
    exp = _CountingExp(d)
    freqs = np.linspace(98.0, 102.0, 11)
    res = run_static_contrast(exp, freqs, qubit_gain_on=200, out_dir=d)
    assert exp.calls == 2 * freqs.size
    sc, arr = _sidecar(d, "1_static_contrast")
    for k in (
        "Z_on_se_real",
        "Z_on_se_imag",
        "Z_off_se_real",
        "Z_off_se_imag",
        "Z_on_cov_IQ",
        "Z_off_cov_IQ",
        "contrast_se",
        "contrast_snr_per_point",
    ):
        assert arr[k].shape == (freqs.size,) and np.all(np.isfinite(arr[k])), k
    assert sc["contrast_snr_method"] == "standard_error"
    assert sc["n_blocks"] == 20 and sc["n_batches_min"] == 20
    assert np.isclose(
        sc["contrast_snr"], res["contrast_snr_per_point"][int(np.argmax(res["contrast"]))]
    )
    # the signal (1.0 over se ~ 0.08) is many sigma; the threshold uses 19 dof
    assert sc["contrast_snr"] > 8 and sc["contrast_significant"] == 1.0
    assert np.isclose(
        sc["contrast_snr_threshold"], max_contrast_snr_threshold(freqs.size, 0.05, 19)
    )
    assert exp.cfg["qubit_gain"] == 200


def test_stage2_sidecar_has_se_and_same_acquire_count(tmp_path):
    d = str(tmp_path)
    exp = _CountingExp(d)
    qf = np.linspace(3995.0, 4005.0, 9)
    res = run_contrast_vs_qubit_freq(exp, qf, out_dir=d)
    assert exp.calls == 1 + qf.size
    sc, arr = _sidecar(d, "2_contrast_vs_qubit_freq")
    for k in (
        "z_on_se_real",
        "z_on_se_imag",
        "z_on_cov_IQ",
        "contrast_se",
        "contrast_snr_per_point",
    ):
        assert arr[k].shape == (qf.size,) and np.all(np.isfinite(arr[k])), k
    for k in ("z_off_se_real", "z_off_se_imag", "z_off_cov_IQ"):
        assert np.isfinite(sc[k]), k
    np.testing.assert_allclose(res["contrast_snr_per_point"], res["contrast"] / res["contrast_se"])
