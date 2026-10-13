"""
Hardware-free tests for qicklab.runs.zero_span_validation.

Ported from the legacy inline self-test (validate_ZeroSpanParity.py
``if __name__ == "__main__":`` block, L442-590) with the same assertions, one test per
legacy block. Fake experiments stand in for ZeroSpanParity; no RFSoC, no Pyro4.
"""

import json
import os

import numpy as np

from qicklab.runs.zero_span_validation import (
    ANALYSIS_VERSION,
    CrossRunComparison,
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
    assert "branch_sign_flip" in res["variants"]["D"], res["variants"]["D"]


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
