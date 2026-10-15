"""
Hardware-free tests for qicklab.runs.zero_span_validation.

Ported from the legacy inline self-test (validate_ZeroSpanParity.py
``if __name__ == "__main__":`` block, L442-590) with the same assertions, one test per
legacy block. Fake experiments stand in for ZeroSpanParity; no RFSoC, no Pyro4.
"""

import json
import os

import numpy as np

from qicklab.analysis.zero_span_checks import (
    batch_means_se,
    branch_response_test,
    critical_value,
    level_shift_null,
    verify_modulation,
)
from qicklab.runs.zero_span_validation import (
    ANALYSIS_VERSION,
    CrossRunComparison,
    _preserve_cfg,
    build_evidence_report,
    run_contrast_vs_qubit_freq,
    run_control_suite,
    run_modulation_check,
    run_static_contrast,
)


class _StrobeFakeExp:
    """Fake ZeroSpanParity: acquire() returns a single IQ cloud shifted to
    level 5.0 when driven (gain>0), a cloud at 0.0 when off. Models the
    drive-on/off mean-response contrast used by the modulation and static-
    contrast stages — NOT parity telegraph (see _ParityFakeExp for that)."""

    def __init__(self, n, sp_us, out_dir):
        self.cfg = {
            "qubit_gain": 200,
            "reps_per_chunk": n,
            "reps": n,
            "sample_period_us": sp_us,
            "read_pulse_freq": 100.0,
            "parity_drive_freq": 4000.0,
            "device": "TEST",
            "mode": "strobe",
            "pulse_gain": 300,
        }
        self._n = n
        self._sp = sp_us
        self._rng = np.random.default_rng(0)
        self.fname = os.path.join(out_dir, "fake.h5")

    def set_qubit_gain(self, gain):
        self.cfg["qubit_gain"] = gain

    def acquire(self, progress=False):
        g = self.cfg["qubit_gain"]
        level = 5.0 if g > 0 else 0.0
        I = level + self._rng.normal(0, 0.8, self._n)
        Q = self._rng.normal(0, 0.8, self._n)
        t = np.arange(self._n) * self._sp
        return {
            "I": I,
            "Q": Q,
            "t_us": t,
            "mode": "strobe",
            "sample_period_us": self._sp,
            "read_length_us": 5.0,
            "wall_clock_start": "2026-01-01T00:00:00",
        }


class _SpecFakeExp(_StrobeFakeExp):
    def acquire(self, progress=False):
        g = self.cfg["qubit_gain"]
        fq = self.cfg["parity_drive_freq"]
        # two "branches" at 3998 and 4002 -> larger response near them when driven
        resp = 0.0
        if g > 0:
            resp = 5.0 * (np.exp(-((fq - 3998.0) ** 2) / 0.5) + np.exp(-((fq - 4002.0) ** 2) / 0.5))
        I = resp + self._rng.normal(0, 0.5, self._n)
        Q = self._rng.normal(0, 0.5, self._n)
        t = np.arange(self._n) * self._sp
        return {
            "I": I,
            "Q": Q,
            "t_us": t,
            "mode": "strobe",
            "sample_period_us": self._sp,
            "read_length_us": 5.0,
            "wall_clock_start": "2026-01-01T00:00:00",
        }


class _ParityFakeExp(_StrobeFakeExp):
    """Bimodal-telegraph fake: driving ON at a parity-doublet peak
    (3998/4002 MHz) yields a 50/50 mix of the g-cloud (0,0) and e-cloud
    (5,0) — the two separated states run_control_suite's separation_snr is
    meant to detect. Drive OFF or detuned off the peaks -> single g-cloud.
    This is what the drive-off (A) vs on-peak (D) control comparison needs;
    the plain _StrobeFakeExp only shifts a unimodal cloud and cannot
    exercise the ordering."""

    PEAKS = (3998.0, 4002.0)

    def acquire(self, progress=False):
        g = self.cfg["qubit_gain"]
        fq = self.cfg["parity_drive_freq"]
        on_peak = g > 0 and min(abs(fq - p) for p in self.PEAKS) < 0.5
        if on_peak:
            labels = self._rng.random(self._n) < 0.5
            I = np.where(labels, 5.0, 0.0) + self._rng.normal(0, 0.5, self._n)
            Q = self._rng.normal(0, 0.5, self._n)
        else:
            I = self._rng.normal(0, 0.5, self._n)
            Q = self._rng.normal(0, 0.5, self._n)
        t = np.arange(self._n) * self._sp
        return {
            "I": I,
            "Q": Q,
            "t_us": t,
            "mode": "strobe",
            "sample_period_us": self._sp,
            "read_length_us": 5.0,
            "wall_clock_start": "2026-01-01T00:00:00",
        }


def test_run_modulation_check(tmp_path):
    d = str(tmp_path)
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
    exp = _StrobeFakeExp(500, 20.0, d)
    res = run_modulation_check(exp, separator=sep, modulation_freq_hz=50.0, n_periods=4, out_dir=d)
    assert res["correlation"] > 0.8, res["correlation"]
    assert res["modulation_depth"] > 2.0, res["modulation_depth"]
    # sidecar written
    sidecars = [
        f for f in os.listdir(d) if f.startswith("3_modulation_check") and f.endswith(".json")
    ]
    assert sidecars, "no modulation sidecar json written"
    with open(os.path.join(d, sidecars[0])) as fh:
        meta = json.load(fh)
    assert meta["stage"] == "3_modulation_check"
    assert meta["mode"] == "strobe"


class _RepsFakeExp(_StrobeFakeExp):
    """Like ZeroSpanParity: set_qubit_gain re-syncs cfg["reps"] from cfg["reps_per_chunk"]
    and the program returns cfg["reps"] samples per acquire()."""

    def set_qubit_gain(self, gain):
        self.cfg["qubit_gain"] = gain
        self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
        self._n = self.cfg["reps"]


def _modulation_sidecar(d):
    sidecars = [
        f for f in os.listdir(d) if f.startswith("3_modulation_check") and f.endswith(".json")
    ]
    assert len(sidecars) == 1, sidecars
    with open(os.path.join(d, sidecars[0])) as fh:
        return json.load(fh)


def test_run_modulation_check_blocks_use_reps_per_block(tmp_path):
    # 50 Hz at 20 us/sample -> 500 samples per half-period, although the main record's
    # chunk (reps_per_chunk) is 2000; the chunk size is restored afterwards
    d = str(tmp_path)
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
    exp = _RepsFakeExp(2000, 20.0, d)
    res = run_modulation_check(exp, separator=sep, modulation_freq_hz=50.0, n_periods=4, out_dir=d)
    assert res["acq"]["I"].size == 8 * 500
    assert res["acq"]["gap_indices"] == [500 * k for k in range(1, 8)]
    assert exp.cfg["reps_per_chunk"] == 2000 and exp.cfg["reps"] == 2000
    # measured (transitions + 1 half-periods over n samples) equals nominal exactly
    assert res["nominal_modulation_freq_hz"] == 50.0
    assert np.isclose(res["injected_freq_hz"], 50.0), res["injected_freq_hz"]
    meta = _modulation_sidecar(d)
    assert meta["reps_per_block"] == 500 and meta["modulation_freq_hz"] == 50.0
    assert meta["scalars"]["nominal_modulation_freq_hz"] == 50.0
    assert np.isclose(meta["scalars"]["injected_freq_hz"], 50.0)


def test_run_modulation_check_keeps_measured_freq_separate(tmp_path):
    # A program that ignores the requested block length (1000 samples per block instead of
    # 500) must show up as a measured 25 Hz next to the nominal 50 Hz, not be overwritten.
    d = str(tmp_path)
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
    exp = _StrobeFakeExp(1000, 20.0, d)
    res = run_modulation_check(exp, separator=sep, modulation_freq_hz=50.0, n_periods=4, out_dir=d)
    assert res["nominal_modulation_freq_hz"] == 50.0
    assert np.isclose(res["injected_freq_hz"], 25.0), res["injected_freq_hz"]
    meta = _modulation_sidecar(d)
    assert meta["scalars"]["nominal_modulation_freq_hz"] == 50.0
    assert np.isclose(meta["scalars"]["injected_freq_hz"], 25.0)


def test_verify_modulation_injected_freq_counts_whole_half_periods():
    # 3 whole periods of 4-sample half-periods at 1 us: f = 1 / (8 us) = 125 kHz exactly
    ref = np.tile([1.0] * 4 + [0.0] * 4, 3)
    t = np.arange(ref.size, dtype=float)
    vm = verify_modulation(5.0 * ref, t, ref)
    assert np.isclose(vm["injected_freq_hz"], 125e3), vm["injected_freq_hz"]


def test_run_static_contrast(tmp_path):
    d = str(tmp_path)
    exp = _StrobeFakeExp(200, 20.0, d)
    freq_list = np.linspace(95.0, 105.0, 11)
    res = run_static_contrast(exp, freq_list, qubit_gain_on=200, out_dir=d)
    assert res["contrast"].shape == (freq_list.size,), res["contrast"].shape
    assert np.all(np.isfinite(res["Z_on"])) and np.all(np.isfinite(res["Z_off"]))
    files = [f for f in os.listdir(d) if f.startswith("1_static_contrast")]
    assert any(f.endswith(".png") for f in files), "no contrast plot"
    assert any(f.endswith(".json") for f in files), "no contrast sidecar"


def test_run_contrast_vs_qubit_freq(tmp_path):
    d = str(tmp_path)
    exp = _SpecFakeExp(200, 20.0, d)
    qf = np.linspace(3995.0, 4005.0, 51)
    res = run_contrast_vs_qubit_freq(exp, qf, out_dir=d)
    assert res["contrast"].shape == (qf.size,), res["contrast"].shape
    # the two branches should be the two strongest contrast points
    top2 = qf[np.argsort(res["contrast"])[-2:]]
    assert min(abs(top2 - 3998.0).min(), abs(top2 - 4002.0).min()) < 0.5, top2


def test_cross_run_comparison(tmp_path):
    cmp = CrossRunComparison(param_name="power_dB")
    cmp.add(
        -10,
        {
            "switch_rate": 100.0,
            "separation_snr": 5.0,
            "mean_dwell": 2000.0,
            "mean_signal_level": 4.0,
        },
    )
    cmp.add(
        -5,
        {
            "switch_rate": 200.0,
            "separation_snr": 4.0,
            "mean_dwell": 1000.0,
            "mean_signal_level": 4.1,
        },
    )
    tbl = cmp.table()
    assert tbl["power_dB"] == [-10, -5], tbl
    assert tbl["switch_rate"] == [100.0, 200.0], tbl
    p = cmp.plot(os.path.join(str(tmp_path), "env.png"))
    assert os.path.exists(p)


def test_run_control_suite(tmp_path):
    d = str(tmp_path)
    exp = _ParityFakeExp(2000, 20.0, d)
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
    res = run_control_suite(
        exp,
        separator=sep,
        variants=("A", "D"),
        detune_mhz=50.0,
        parity_freqs={"lower": 3998.0, "higher": 4002.0},
        out_dir=d,
    )
    assert "A" in res["variants"] and "D" in res["variants"], res["variants"]
    # control A (drive off, unimodal) separation must be well below the
    # on-peak driven branch D (bimodal telegraph -> large separation).
    assert res["variants"]["A"]["separation_snr"] < res["variants"]["D"]["separation_snr_lower"], (
        res["variants"]["A"]["separation_snr"],
        res["variants"]["D"]["separation_snr_lower"],
    )
    # the sign statistic is gone (it could not be True for a genuine signal), and the
    # outputs were renamed so an old sidecar is not misread
    D = res["variants"]["D"]
    assert D["label"] == "both_branches"
    for old in ("branch_sign_flip", "sign_lower", "sign_higher"):
        assert old not in D, D
    assert "both_branches_respond" in D and "branch_ratio" in D, D


def test_build_evidence_report(tmp_path):
    d = str(tmp_path)
    for stage, sc in [
        ("1_static_contrast", {"best_freq": 100.05, "contrast_snr": 8.0}),
        ("3_modulation_check", {"correlation": 0.95, "modulation_depth": 4.0}),
    ]:
        with open(os.path.join(d, f"{stage}_2026_01_01_00_00_00.json"), "w") as fh:
            json.dump(
                {
                    "stage": stage,
                    "timestamp": "t",
                    "mode": "strobe",
                    "analysis_version": ANALYSIS_VERSION,
                    "scalars": sc,
                },
                fh,
            )
    report = build_evidence_report(d, os.path.join(d, "EVIDENCE.md"))
    assert os.path.exists(report)
    with open(report) as fh:
        text = fh.read()
    assert "1_static_contrast" in text and "3_modulation_check" in text
    assert "correlation" in text


# ---------------------------------------------------------------------------------------
# Stage 8 statistics (F19): synthetic parity telegraphs, batch-means standard errors
# ---------------------------------------------------------------------------------------

SP_US = 20.0
DWELL_US = 2500.0
SEP = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
E_MINUS_G = 25.0  # projected |e - g| in score units: |e_center - g_center|^2


def _telegraph(n, rng, dwell_us=DWELL_US, p_odd=0.5, sp_us=SP_US):
    """Parity record (1 = odd) with exponential dwells of mean dwell_us. p_odd sets the
    asymmetry: mean odd dwell = 2 * p_odd * dwell_us, mean even = 2 * (1 - p_odd) * dwell_us."""
    out = np.empty(n, dtype=int)
    state = int(rng.random() < p_odd)
    i = 0
    while i < n:
        mean = 2.0 * (p_odd if state else 1.0 - p_odd) * dwell_us
        k = max(1, int(round(rng.exponential(mean) / sp_us)))
        out[i : i + k] = state
        state ^= 1
        i += k
    return out


def _record(parity, branch, rng, pe=0.5, sp_us=SP_US, noise=0.5, time_averaged=False):
    """Classified record when driving `branch` ("odd", "even" or None = off/null).

    Projective (default): samples in the driven parity are e with probability pe.
    time_averaged: they sit at pe * (e - g), the time average over the near-CW drive."""
    n = parity.size
    if branch is None:
        x = np.zeros(n)
    else:
        driven = parity == (1 if branch == "odd" else 0)
        x = (pe * driven) if time_averaged else (driven & (rng.random(n) < pe)).astype(float)
    I = 5.0 * x + rng.normal(0, noise, n)
    scores = (I - 2.5) * 5.0  # projection onto e - g about the midpoint
    return {"scores": scores, "t_us": np.arange(n) * sp_us}


def test_batch_means_se_exceeds_naive_se_for_telegraph():
    rng = np.random.default_rng(1)
    x = _telegraph(20000, rng).astype(float)
    t = np.arange(x.size) * SP_US
    _, se, n_b = batch_means_se(x, t, batch_us=10000.0)
    assert n_b == 40
    naive = np.std(x) / np.sqrt(x.size)
    assert se > 3 * naive, (se, naive)
    # too few batches -> undefined
    _, se_short, n_short = batch_means_se(x[:1000], t[:1000], batch_us=10000.0)
    assert n_short == 2 and np.isnan(se_short)


def test_critical_value_is_student_t_for_few_batches():
    # 4 batches per record: Welch dof ~3-6, so the 3-sigma tail needs a much larger |z|
    assert critical_value(3.0, 3.0) > 9.0
    assert 4.5 < critical_value(3.0, 6.0) < 5.5
    assert 3.1 < critical_value(3.0, 38.0) < 3.3  # 20 batches per record
    assert abs(critical_value(3.0, np.inf) - 3.0) < 1e-12
    assert abs(critical_value(3.0, 1e6) - 3.0) < 1e-3
    assert np.isnan(critical_value(3.0, np.nan))


def test_null_false_alarm_rate_at_four_batches():
    # white-noise null, two drive-off records of exactly 4 batches (40 ms at 20 us): the
    # t critical value keeps the false-alarm rate near the nominal 0.27 % (it was ~2 %
    # with a normal threshold on the 3-dof se)
    rng = np.random.default_rng(11)
    n, trials = 2000, 2000
    t = np.arange(n) * SP_US
    fails = 0
    for _ in range(trials):
        a = {"scores": rng.normal(0, 1, n), "t_us": t}
        b = {"scores": rng.normal(0, 1, n), "t_us": t}
        r = level_shift_null(a, b, batch_us=10000.0)
        assert r["n_batches"] == 4 and r["null_ok"] is not None
        fails += not r["null_ok"]
    assert fails / trials < 0.01, fails


def test_branch_response_both_branches_respond_with_expected_ratio():
    rng = np.random.default_rng(2)
    n = 50000  # 1 s at 20 us
    p_odd = 0.7  # here the lower peak is the odd parity's transition: P_lower = 0.7
    # every record is its own stretch of the telegraph (separate acquisitions)
    lo = _record(_telegraph(n, rng, p_odd=p_odd), "odd", rng)
    hi = _record(_telegraph(n, rng, p_odd=p_odd), "even", rng)
    off = _record(_telegraph(n, rng, p_odd=p_odd), None, rng)
    r = branch_response_test(lo, hi, off, batch_us=10000.0, e_minus_g=E_MINUS_G)
    assert r["both_branches_respond"] is True and not r["insufficient_batches"], r
    assert r["delta_lower"] > 0 and r["delta_higher"] > 0
    # expected P_lower pe / (P_higher pe) = 0.7 / 0.3
    assert abs(r["branch_ratio"] - p_odd / (1 - p_odd)) < 3 * r["branch_ratio_se"] + 0.1, r
    # complementarity: (delta_lo + delta_hi) / (pe |e-g|) ~ P_lower + P_higher = 1
    assert abs(r["complementarity_z"]) < 3, r
    assert abs(r["complementarity"] - 1.0) < 0.1, r


def test_complementarity_is_linear_in_pe_for_time_averaged_samples():
    # near-CW drive: a driven sample may be a time average at pe * (e - g), near the
    # threshold; a bright-fraction statistic is then a threshold artifact, the mean level
    # is not
    for pe in (0.4, 0.5, 0.6):
        rng = np.random.default_rng(int(pe * 100))
        n = 50000
        lo = _record(_telegraph(n, rng), "odd", rng, pe=pe, time_averaged=True)
        hi = _record(_telegraph(n, rng), "even", rng, pe=pe, time_averaged=True)
        off = _record(_telegraph(n, rng), None, rng)
        r = branch_response_test(lo, hi, off, batch_us=10000.0, e_minus_g=E_MINUS_G, pe_drive=pe)
        assert abs(r["complementarity_z"]) < 3 and abs(r["complementarity"] - 1.0) < 0.15, (pe, r)


def test_branch_response_drive_off_is_false():
    rng = np.random.default_rng(3)
    n = 20000
    recs = [_record(_telegraph(n, rng), None, rng) for _ in range(3)]
    r = branch_response_test(recs[0], recs[1], recs[2], batch_us=10000.0, e_minus_g=E_MINUS_G)
    assert r["both_branches_respond"] is False, r
    assert abs(r["delta_lower_z"]) < 4 and abs(r["delta_higher_z"]) < 4


def test_branch_response_one_branch_only_is_false():
    rng = np.random.default_rng(4)
    n = 20000
    lo = _record(_telegraph(n, rng), "odd", rng)
    hi = _record(_telegraph(n, rng), None, rng)  # higher branch does not respond
    off = _record(_telegraph(n, rng), None, rng)
    r = branch_response_test(lo, hi, off, batch_us=10000.0, e_minus_g=E_MINUS_G)
    assert r["delta_lower_z"] > r["t_crit_lower"] and r["both_branches_respond"] is False, r


def test_branch_response_short_record_is_undetermined():
    rng = np.random.default_rng(8)
    recs = [_record(_telegraph(1000, rng), b, rng) for b in ("odd", "even", None)]
    r = branch_response_test(*recs, batch_us=10000.0, e_minus_g=E_MINUS_G)
    assert r["both_branches_respond"] is None and r["insufficient_batches"], r


def test_branch_ratio_and_complementarity_se_match_monte_carlo_spread():
    # Pins the error propagation: median(se) / spread(estimate) over repeated synthetic
    # runs must be ~1. White readout noise dominates every record (also the drive-off
    # reference) and the dwell (200 us) is short against the 10 ms batches, so the
    # batch-means se is unbiased and the shared-reference terms matter: a wrong sign of
    # the ratio's covariance term gives ~1.5, a -1 instead of -2 coefficient on the
    # reference in complementarity gives ~0.72.
    rng = np.random.default_rng(13)
    n, trials, p_lower = 25000, 200, 0.6
    est = {"branch_ratio": [], "complementarity": []}
    se = {"branch_ratio": [], "complementarity": []}
    for _ in range(trials):
        lo, hi, off = (
            _record(_telegraph(n, rng, dwell_us=200.0, p_odd=p_lower), b, rng, noise=10.0)
            for b in ("odd", "even", None)
        )
        r = branch_response_test(lo, hi, off, batch_us=10000.0, e_minus_g=E_MINUS_G)
        for k in est:
            est[k].append(r[k])
            se[k].append(r[f"{k}_se"])
    assert abs(np.mean(est["branch_ratio"]) - p_lower / (1 - p_lower)) < 0.08, est
    assert abs(np.mean(est["complementarity"]) - 1.0) < 0.03, est
    for k in est:
        q = np.median(se[k]) / np.std(est[k], ddof=1)
        assert 0.8 < q < 1.25, (k, q)


def test_welch_dof_for_equal_batch_variances():
    # lower / higher are the drive-off record shifted by a constant: all three have the
    # same batch-mean variance v, so every shift has Welch dof 2 (n_b - 1), and so does
    # complementarity (coefficients 1, 1, -2: (6v)^2 / ((1 + 1 + 16) v^2 / (n_b - 1)))
    rng = np.random.default_rng(14)
    t = np.arange(10000) * SP_US
    off = {"scores": rng.normal(0, 1, t.size), "t_us": t}
    lo = {"scores": off["scores"] + 2.0, "t_us": t}
    hi = {"scores": off["scores"] + 1.0, "t_us": t}
    r = branch_response_test(lo, hi, off, batch_us=10000.0, e_minus_g=E_MINUS_G)
    n_b = r["n_batches"]
    assert n_b == 20
    for k in ("delta_lower_dof", "delta_higher_dof", "complementarity_dof"):
        assert abs(r[k] - 2 * (n_b - 1)) < 1e-9, (k, r[k])
    assert abs(r["t_crit_lower"] - critical_value(3.0, 2 * (n_b - 1))) < 1e-12
    assert abs(r["branch_ratio"] - 2.0) < 1e-12
    assert abs(level_shift_null(lo, off, batch_us=10000.0)["delta_dof"] - 2 * (n_b - 1)) < 1e-9


def test_old_sign_statistic_is_false_on_genuine_signal():
    # Regression pin for the dropped branch_sign_flip: driving either branch moves the
    # mean level the same way (toward e), so sign(lvl_lo - off) == sign(lvl_hi - off)
    # and the old "assignment reverses" statistic was False on a genuine parity signal.
    rng = np.random.default_rng(5)
    n = 20000
    lo = _record(_telegraph(n, rng), "odd", rng)
    hi = _record(_telegraph(n, rng), "even", rng)
    off = _record(_telegraph(n, rng), None, rng)
    off_level = np.mean(off["scores"])
    sgn_lo = int(np.sign(np.mean(lo["scores"]) - off_level))
    sgn_hi = int(np.sign(np.mean(hi["scores"]) - off_level))
    assert sgn_lo == sgn_hi == 1
    r = branch_response_test(lo, hi, off, batch_us=10000.0, e_minus_g=E_MINUS_G)
    assert r["both_branches_respond"] is True


def test_level_shift_null_passes_for_midpoint_and_fails_for_branch():
    rng = np.random.default_rng(6)
    n = 20000
    off = _record(_telegraph(n, rng), None, rng)
    mid = _record(_telegraph(n, rng), None, rng)  # midpoint drive excites neither parity
    assert level_shift_null(mid, off, batch_us=10000.0)["null_ok"] is True
    on = _record(_telegraph(n, rng), "odd", rng)
    assert level_shift_null(on, off, batch_us=10000.0)["null_ok"] is False
    # too short for batch means -> se undefined -> undetermined, not a null violation
    short = {k: v[:500] for k, v in mid.items()}
    r = level_shift_null(short, off, batch_us=10000.0)
    assert r["null_ok"] is None and r["insufficient_batches"], r


class _BuildFakeExp:
    """Fake ZeroSpanParity whose cfg changes take effect only on a rebuild
    (set_qubit_gain), like the real compiled program. Records every build and the built
    cfg of every acquisition. Driving at a parity branch with gain > 0 excites the samples
    in that parity (pe = 0.5) of a telegraph record; probe off-resonance moves both clouds
    to a background point. fail_at: raise on that acquisition (0-based)."""

    BRANCHES = {3998.0: "odd", 4002.0: "even"}

    def __init__(self, out_dir, n=10000, cfg_extra=None, fail_at=None):
        self.cfg = {
            "qubit_gain": 200,
            "reps_per_chunk": n,
            "reps": n,
            "sample_period_us": SP_US,
            "read_pulse_freq": 100.0,
            "parity_drive_freq": 3998.0,
            "mode": "strobe",
        }
        self.cfg.update(cfg_extra or {})
        self._rng = np.random.default_rng(7)
        self.fname = os.path.join(out_dir, "fake.h5")
        self.builds = []
        self.acquired = []
        self.fail_at = fail_at
        self.set_qubit_gain(self.cfg["qubit_gain"])

    def set_qubit_gain(self, gain):
        self.cfg["qubit_gain"] = gain
        if "reps_per_chunk" in self.cfg:
            self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
        self._built = dict(self.cfg)
        self.builds.append(dict(self.cfg))

    def acquire(self, progress=False):
        if self.fail_at is not None and len(self.acquired) == self.fail_at:
            raise RuntimeError("acquire failed")
        b = self._built
        self.acquired.append(b)
        n = int(b["reps"])
        branch = None
        fq = b.get("parity_drive_freq")
        if b["qubit_gain"] > 0 and fq is not None:
            branch = next((v for f, v in self.BRANCHES.items() if abs(fq - f) < 0.5), None)
        rec = _record(_telegraph(n, self._rng), branch, self._rng)
        I = rec["scores"] / 5.0 + 2.5
        if b.get("read_pulse_freq") != 100.0:
            I = np.full(n, 1.0) + self._rng.normal(0, 0.5, n)
        return {"I": I, "Q": self._rng.normal(0, 0.5, n), "t_us": rec["t_us"]}


def test_control_suite_rebuilds_after_every_frequency_change(tmp_path):
    exp = _BuildFakeExp(str(tmp_path))
    res = run_control_suite(
        exp,
        separator=SEP,
        detune_mhz=50.0,
        parity_freqs={"lower": 3998.0, "higher": 4002.0},
        out_dir=str(tmp_path),
    )
    got = [(a["qubit_gain"], a["parity_drive_freq"], a["read_pulse_freq"]) for a in exp.acquired]
    assert got == [
        (0, 3998.0, 100.0),  # drive-off reference
        (0, 3998.0, 100.0),  # A
        (200, 4048.0, 100.0),  # B detuned
        (200, 3998.0, 150.0),  # C probe off-resonance (before the fix: B's program)
        (200, 3998.0, 100.0),  # D lower
        (200, 4002.0, 100.0),  # D higher (before the fix: still the lower program)
        (200, 4000.0, 100.0),  # D midpoint null
    ], got
    # restored and rebuilt at the base point
    assert exp.builds[-1]["parity_drive_freq"] == 3998.0
    assert exp.builds[-1]["read_pulse_freq"] == 100.0 and exp.builds[-1]["qubit_gain"] == 200
    v = res["variants"]
    assert v["A"]["null_ok"] is True and v["B"]["null_ok"] is True
    assert v["D"]["both_branches_respond"] is True, v["D"]
    assert v["D"]["midpoint_null_ok"] is True, v["D"]
    with open(res["sidecar"]) as fh:
        meta = json.load(fh)
    assert meta["analysis_version"] == ANALYSIS_VERSION
    assert meta["variants"]["D"]["both_branches_respond"] is True
    assert meta["k_sigma"] == 3.0 and meta["blocks_per_record"] == 1


def test_control_suite_rebuilds_base_program_on_exception(tmp_path):
    # the acquire fails in C (probe off-resonance): cfg is restored and the base program
    # rebuilt, not left at C's detuned probe
    exp = _BuildFakeExp(str(tmp_path), fail_at=3)
    try:
        run_control_suite(
            exp,
            separator=SEP,
            parity_freqs={"lower": 3998.0, "higher": 4002.0},
            out_dir=str(tmp_path),
        )
    except RuntimeError as ex:
        assert "acquire failed" in str(ex)
    else:
        raise AssertionError("the acquire error was swallowed")
    assert exp.builds[-2]["read_pulse_freq"] == 150.0  # C's program
    assert exp.cfg["read_pulse_freq"] == 100.0 and exp.cfg["qubit_gain"] == 200
    last = exp.builds[-1]
    assert (last["qubit_gain"], last["parity_drive_freq"], last["read_pulse_freq"]) == (
        200,
        3998.0,
        100.0,
    )


def test_evidence_report_shows_stage8_variants(tmp_path):
    exp = _BuildFakeExp(str(tmp_path), n=2000)
    run_control_suite(
        exp,
        separator=SEP,
        variants=("A", "D"),
        parity_freqs={"lower": 3998.0, "higher": 4002.0},
        out_dir=str(tmp_path),
    )
    d = str(tmp_path)
    with open(build_evidence_report(d, os.path.join(d, "EVIDENCE.md"))) as fh:
        text = fh.read()
    assert "## 8_control_suite" in text
    assert "| A | null_ok | True |" in text, text
    assert "| D | both_branches_respond | True |" in text, text
    for k in ("branch_ratio", "branch_ratio_se", "complementarity_se", "midpoint_null_ok"):
        assert f"| D | {k} |" in text, k


def test_control_suite_stitches_blocks_to_min_record(tmp_path):
    # stage 1 leaves reps_per_chunk = 2000 (40 ms at 20 us = 4 batches): each control
    # record is stitched from ceil(200 ms / 40 ms) = 5 acquisitions -> 20 batches
    exp = _BuildFakeExp(str(tmp_path), n=2000)
    res = run_control_suite(
        exp,
        separator=SEP,
        variants=("A", "D"),
        parity_freqs={"lower": 3998.0, "higher": 4002.0},
        out_dir=str(tmp_path),
    )
    assert len(exp.acquired) == 5 * 5  # off, A, D lower/higher/midpoint
    assert all(a["reps"] == 2000 for a in exp.acquired)
    v = res["variants"]
    assert v["A"]["n_batches"] == 20 and v["D"]["n_batches"] == 20
    assert v["A"]["null_ok"] is True and v["D"]["both_branches_respond"] is True, v
    with open(res["sidecar"]) as fh:
        meta = json.load(fh)
    assert meta["blocks_per_record"] == 5 and meta["record_us"] >= 199000.0


def test_control_suite_parity_freqs_none_does_not_raise(tmp_path):
    for pf in (None, {"lower": None, "higher": None}):
        exp = _BuildFakeExp(str(tmp_path), n=2000)
        res = run_control_suite(
            exp, separator=SEP, variants=("D",), parity_freqs=pf, out_dir=str(tmp_path)
        )
        assert "skipped" in res["variants"]["D"], res["variants"]["D"]
        assert exp.cfg["parity_drive_freq"] == 3998.0


def test_control_suite_unset_frequencies_skip_and_stay_absent(tmp_path):
    exp = _BuildFakeExp(str(tmp_path), n=2000)
    del exp.cfg["parity_drive_freq"]
    del exp.cfg["read_pulse_freq"]
    res = run_control_suite(exp, separator=SEP, variants=("B", "C"), out_dir=str(tmp_path))
    assert "skipped" in res["variants"]["B"] and "skipped" in res["variants"]["C"]
    # no control driven at 0 + detune, and no None written into the absent keys
    assert all("parity_drive_freq" not in a for a in exp.acquired)
    assert "parity_drive_freq" not in exp.cfg and "read_pulse_freq" not in exp.cfg


def test_preserve_cfg_does_not_write_none_into_absent_keys():
    class E:
        cfg = {"qubit_gain": 5}

    e = E()
    with _preserve_cfg(e, "qubit_gain", "parity_drive_freq"):
        e.cfg["qubit_gain"] = 0
        e.cfg["parity_drive_freq"] = 123.0
    assert e.cfg == {"qubit_gain": 5}


def test_modulation_check_restores_drive_gain(tmp_path):
    exp = _BuildFakeExp(str(tmp_path), n=2000)
    run_modulation_check(
        exp, separator=SEP, modulation_freq_hz=50.0, n_periods=2, out_dir=str(tmp_path)
    )
    # schedule ends at gain 0; the drive gain and its program are restored afterwards
    assert exp.cfg["qubit_gain"] == 200
    assert exp.builds[-1]["qubit_gain"] == 200 and exp.builds[-1]["reps"] == 2000
    assert [a["qubit_gain"] for a in exp.acquired] == [200, 0, 200, 0]


def test_modulation_check_restores_drive_gain_on_exception(tmp_path):
    # the acquisition fails in the second (gain 0) block of the schedule
    exp = _BuildFakeExp(str(tmp_path), n=2000, fail_at=1)
    try:
        run_modulation_check(
            exp, separator=SEP, modulation_freq_hz=50.0, n_periods=2, out_dir=str(tmp_path)
        )
    except RuntimeError as ex:
        assert "acquire failed" in str(ex)
    else:
        raise AssertionError("the acquire error was swallowed")
    assert exp.builds[-2]["qubit_gain"] == 0  # modulated_strobe_acquire's own rebuild
    assert exp.cfg["qubit_gain"] == 200
    assert exp.builds[-1]["qubit_gain"] == 200 and exp.builds[-1]["reps"] == 2000
