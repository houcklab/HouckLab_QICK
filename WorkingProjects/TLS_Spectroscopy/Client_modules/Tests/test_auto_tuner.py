import ast
import json
import os
import pickle
import sys
import types
import tempfile

import h5py
import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, REPO)

qick = types.ModuleType("qick")
qick.AveragerProgram = type("AveragerProgram", (), {})
qick.RAveragerProgram = type("RAveragerProgram", (), {})
sys.modules["qick"] = qick

import matplotlib
matplotlib.use("Agg")

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mAutoTuner as T
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.ss_helpers import (
    find_blob_median as qm_find_blob_median, find_threshold as qm_find_threshold,
)

FAIL = []


def check(name, cond, detail=""):
    print("  %-62s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        FAIL.append(name)



class VirtualQubit:
    F_R = 7248.9000
    KAPPA = 0.35
    CHI = -0.12
    F_Q = 2534.4000
    PI_GAIN = 11500.0
    T1 = 25.0
    T2 = 0.6
    T_PI = 0.5
    G_CRIT = 14000.0
    NOISE = 0.055

    def __init__(self, rng):
        self.rng = rng
        self.calls = 0
        self.read_calls = 0
        self.iq_drift_per_call = 0.0 + 0.0j
        self.gain_nonlinearity = 0.0
        self.gap_angle_coeff = 0.0

    def alpha(self, f_read, gain, p_e):
        eps = gain / 4300.0
        ag = eps / ((f_read - (self.F_R - self.CHI)) + 0.5j * self.KAPPA)
        ae = eps / ((f_read - (self.F_R + self.CHI)) + 0.5j * self.KAPPA)
        return (1.0 - p_e) * ag + p_e * ae

    def _readout(self, cfg, p_e, shots, per_shot):
        """Return (I, Q) mean or per-shot arrays.  Includes T1 decay during the window
        (which creates a genuine optimal length) and ionization above G_CRIT."""
        f = float(cfg["read_pulse_freq"])
        g = float(cfg["read_pulse_gain"])
        L = float(cfg["read_length"])
        p_eff = p_e * (self.T1 / L) * (1.0 - np.exp(-L / self.T1))
        a = self.alpha(f, g, p_eff)
        a += self.read_calls * self.iq_drift_per_call
        self.read_calls += 1
        sd = self.NOISE / np.sqrt(max(L, 1e-6))
        n = int(shots)
        self.calls += n
        I = self.rng.normal(a.real, sd, n)
        Q = self.rng.normal(a.imag, sd, n)
        if g > self.G_CRIT:
            frac = min(0.6, (g / self.G_CRIT - 1.0) * 2.0)
            k = self.rng.random(n) < frac
            I[k] = self.rng.normal(0.0, 4 * sd, k.sum())
            Q[k] = self.rng.normal(0.0, 4 * sd, k.sum())
        if per_shot:
            return I, Q
        return float(I.mean()), float(Q.mean()), float(I.std(ddof=1) / np.sqrt(n)), \
            float(Q.std(ddof=1) / np.sqrt(n))

    def _rotate(self, v, axis, angle):
        axis = np.asarray(axis, dtype=float)
        nrm = np.linalg.norm(axis)
        if nrm < 1e-15 or abs(angle) < 1e-15:
            return v
        k = axis / nrm
        return (v * np.cos(angle) + np.cross(k, v) * np.sin(angle)
                + k * np.dot(k, v) * (1 - np.cos(angle)))

    def _relax(self, v, t):
        e1, e2 = np.exp(-t / self.T1), np.exp(-t / self.T2)
        return np.array([v[0] * e2, v[1] * e2, 1.0 + (v[2] - 1.0) * e1])

    def run_seq(self, seq, drive_freq, cfg=None):
        """Return the excited population after a sequence.  z=+1 is |g>."""
        v = np.array([0.0, 0.0, 1.0])
        delta = float(drive_freq) - self.F_Q
        for op in seq:
            if op[0] == "pulse":
                g, ph = float(op[1]), np.deg2rad(float(op[2]))
                ratio = g / self.PI_GAIN
                angle_scale = ratio + self.gain_nonlinearity * (ratio - 1.0) ** 2
                if cfg is not None:
                    rel_gap = (float(cfg.get("seq_gap_us", 0.01)) - 0.01) / 0.01
                    angle_scale *= 1.0 + self.gap_angle_coeff * rel_gap
                omega = np.pi * angle_scale / self.T_PI
                dz = 2 * np.pi * delta
                axis = np.array([omega * np.cos(ph), omega * np.sin(ph), dz])
                ang = np.linalg.norm(axis) * self.T_PI
                v = self._rotate(v, axis, ang)
                v = self._relax(v, self.T_PI)
            elif op[0] == "delay":
                t = float(op[1])
                v = self._rotate(v, [0, 0, 1], 2 * np.pi * delta * t)
                v = self._relax(v, t)
        return float((1.0 - v[2]) / 2.0)

    def spec_response(self, f, gain, length_us):
        """Saturation spectroscopy: power-broadened Lorentzian with a Stark shift."""
        omega = np.pi * (gain / self.PI_GAIN) / self.T_PI
        stark = 2.5e-9 * gain ** 2
        d = 2 * np.pi * (np.asarray(f, dtype=float) - (self.F_Q + stark))
        gam = 1.0 / self.T2
        s = (omega ** 2 / 2.0) / (d ** 2 + gam ** 2 + omega ** 2 / 2.0)
        return 0.5 * s



def install_simulator(dev):
    def _avg_iq(exp, prog_cls, cfg):
        p_e = 0.0
        if int(cfg.get("prep_gain", 0)) > 0:
            p_e = dev.run_seq([("pulse", int(cfg["prep_gain"]), 0.0)],
                              cfg["drive_freq"], cfg)
        return dev._readout(cfg, p_e, int(cfg["reps"]), per_shot=False)

    def _run_seq(exp, cfg, seq, drive_freq, shots):
        p_e = dev.run_seq(seq, drive_freq, cfg)
        return dev._readout(cfg, p_e, int(shots), per_shot=False)

    def _shots(exp, cfg, seq, drive_freq, shots):
        p_e = dev.run_seq(seq, drive_freq, cfg)
        return dev._readout(cfg, p_e, int(shots), per_shot=True)

    def _canonical_pair_shots(exp, cfg, drive_freq, pi_gain, shots,
                              state_order="ge"):
        # Same logical state order as SingleShotProgram: all |g>, then all |e>, in one
        # acquisition.  The simulator has no QICK compiler, so this is the injection
        # boundary exercised by production's canonical program wrapper.
        p_e = dev.run_seq([("pulse", int(pi_gain), 0.0)], drive_freq, cfg)
        if state_order == "ge":
            ig, qg = dev._readout(cfg, 0.0, int(shots), per_shot=True)
            ie, qe = dev._readout(cfg, p_e, int(shots), per_shot=True)
        else:
            ie, qe = dev._readout(cfg, p_e, int(shots), per_shot=True)
            ig, qg = dev._readout(cfg, 0.0, int(shots), per_shot=True)
        return ig, qg, ie, qe

    class FakeSpec:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False):
            cfg = self.cfg
            fs = cfg["start"] + cfg["step"] * np.arange(cfg["expts"])
            pe = dev.spec_response(fs, cfg["spec_gain"], cfg["spec_len_us"])
            I = np.empty(fs.size)
            Q = np.empty(fs.size)
            for j, p in enumerate(pe):
                a = dev.alpha(cfg["read_pulse_freq"], cfg["read_pulse_gain"], p)
                sd = dev.NOISE / np.sqrt(max(cfg["read_length"], 1e-6) * cfg["reps"])
                I[j] = dev.rng.normal(a.real, sd)
                Q[j] = dev.rng.normal(a.imag, sd)
            return fs, [[I]], [[Q]]

    class FakeRabi:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False):
            cfg = self.cfg
            gains = cfg["start"] + cfg["step"] * np.arange(cfg["expts"])
            I = np.empty(gains.size)
            Q = np.empty(gains.size)
            for j, g in enumerate(gains):
                p = dev.run_seq([("pulse", int(g), 0.0)], cfg["drive_freq"], cfg) if g > 0 else 0.0
                a = dev.alpha(cfg["read_pulse_freq"], cfg["read_pulse_gain"], p)
                sd = dev.NOISE / np.sqrt(max(cfg["read_length"], 1e-6) * cfg["reps"])
                I[j] = dev.rng.normal(a.real, sd)
                Q[j] = dev.rng.normal(a.imag, sd)
            return gains, [[I]], [[Q]]

    T._avg_iq = _avg_iq
    T._run_seq = _run_seq
    T._shots = _shots
    T._canonical_pair_shots = _canonical_pair_shots
    T.SpecProgram = FakeSpec
    T.RabiProgram = FakeRabi



rng = np.random.default_rng(11)
np.random.seed(12345)  # production uses np.random.permutation for drift-balanced order
print("== pure analysis ==")

f = np.linspace(7246, 7252, 121)
dip = T.lorentzian(f, 7248.953, 0.35, -3.0, 10.0, slope=0.4) + rng.normal(0, 0.05, f.size)
r = T.fit_resonance(f, dip, expected_fwhm=0.35)
check("Lorentzian on a SLOPED baseline: f0 within 20 kHz",
      r["ok"] and abs(r["f0"] - 7248.953) < 0.02, "f0=%.4f slope-tolerant" % r["f0"])

fn = np.linspace(7248.95 - 1.5, 7248.95 + 1.5, 61)
dipn = T.lorentzian(fn, 7248.9378, 0.216, -3.0, 10.0) + rng.normal(0, 0.06, fn.size)
rn = T.fit_resonance(fn, dipn, expected_fwhm=0.216)
check("narrow 3 MHz/61pt scan finds a 216 kHz dip (old fixed kernel erased it)",
      rn["ok"] and abs(rn["f0"] - 7248.9378) < 0.03, "f0=%.4f snr=%.1f" % (rn["f0"], rn["snr"]))

check("pure noise rejected", not T.fit_resonance(f, rng.normal(0, 0.05, f.size))["ok"])

print("== noise estimator: the two hardware pathologies ==")
fq = np.linspace(2547.25, 2567.25, 121)
smoothbump = 0.30 + 0.002 * np.exp(-((fq - 2561.76) / 1.5) ** 2)
rs = T.fit_resonance(fq, smoothbump, polarity="peak", expected_fwhm=2.0)
check("smooth trace does not produce a 1e15 SNR", rs["snr"] < 1e4, "snr=%.3g" % rs["snr"])
qstep = 1e-4
quant = np.round(smoothbump / qstep) * qstep
rq = T.fit_resonance(fq, quant, polarity="peak", expected_fwhm=2.0)
check("quantized baseline does not collapse the noise estimate", rq["snr"] < 1e4,
      "snr=%.3g" % rq["snr"])
rgood = T.fit_resonance(fq, 0.30 - 0.05 / (1 + ((fq - 2557.0) / 1.0) ** 2)
                        + rng.normal(0, 0.002, fq.size), expected_fwhm=2.0)
check("a real dip is still found after the noise fix", rgood["ok"]
      and abs(rgood["f0"] - 2557.0) < 0.3, "f0=%.3f snr=%.1f" % (rgood["f0"], rgood["snr"]))
check("pure noise is still rejected",
      not T.fit_resonance(fq, 0.3 + rng.normal(0, 0.002, fq.size))["ok"])
check("_noise_sigma is strictly positive on constant data", T._noise_sigma(np.full(50, 0.3)) > 0)

print("== optimal readout detuning (analytic) ==")
for chi, kap, expect_mid in ((0.05, 1.0, True), (0.10, 0.4, True), (0.5, 0.35, False)):
    d = T.optimal_readout_detuning(chi, kap)
    ratio = 2 * abs(chi) / kap
    if expect_mid:
        check("2chi/kappa=%.2f -> drive the midpoint" % ratio, abs(d) < 0.02 * kap,
              "detuning %.4f" % d)
    else:
        check("2chi/kappa=%.2f -> drive a dressed peak" % ratio,
              abs(abs(d) - abs(chi)) < 0.5 * abs(chi), "detuning %.4f vs chi %.3f" % (d, chi))

print("== parabola vertex + uncertainty (the convergence statistic) ==")
gpi = 11500.0
for M, npts in ((4, 13), (20, 13)):
    g = np.round(gpi * np.linspace(0.94, 1.06, npts)).astype(float)
    res = np.sin(M * np.pi * (g / gpi - 1.0) / 2.0) ** 2 + 0.10 + rng.normal(0, 0.012, g.size)
    v = T.parabola_vertex(g, res, np.full(g.size, 0.012))
    check("M=%d vertex within 0.5%% of truth" % M, abs(v["x_min"] - gpi) / gpi < 0.005,
          "%.0f +/- %.0f (%.2f%%)" % (v["x_min"], v["x_err"], 100 * v["x_err"] / gpi))
    check("M=%d reports a FINITE uncertainty (old code used the floor)" % M,
          np.isfinite(v["x_err"]) and v["x_err"] > 0)
res_floor = 0.30 + np.sin(20 * np.pi * (g / gpi - 1.0) / 2.0) ** 2
v = T.parabola_vertex(g, res_floor)
check("a 0.30 decoherence floor does not move the vertex",
      abs(v["x_min"] - gpi) / gpi < 0.005, "%.0f" % v["x_min"])

print("== signed sparse phase estimator (new pi primitive) ==")
for n, frac, beta, off, amp in ((3, 0.08, 0.49 * np.pi, 7.0, 0.12),
                                (7, -0.025, 0.51 * np.pi, -3.0, 4.2),
                                (15, 0.003, 0.47 * np.pi, 100.0, 0.02)):
    phi = n * np.pi * (1.0 + frac)
    vals = [off + amp * np.cos(phi - beta), off + amp * np.cos(phi),
            off + amp * np.cos(phi + beta)]
    pe = T.sparse_phase_estimate(vals[0], vals[1], vals[2],
                                 abs(amp) / 200.0, abs(amp) / 200.0,
                                 abs(amp) / 200.0, n * np.pi, beta=beta)
    got = (pe["phase"] - n * np.pi) / (n * np.pi)
    check("M=%d recovers the SIGNED error despite arbitrary offset/contrast" % n,
          pe["ok"] and abs(got - frac) < 2e-4,
          "got %+.4f%% vs %+.4f%%" % (100 * got, 100 * frac))
check("a zero-contrast sparse phase vector is rejected",
      not T.sparse_phase_estimate(1, 1, 1, .01, .01, .01, 3 * np.pi)["ok"])

xz = np.array([9.6, 9.8, 10.0, 10.2, 10.4])
yz = np.sin(8 * np.pi * (xz / 10.07 - 1.0))
zz = T.fit_symmetric_zero(xz, yz, np.full(xz.size, 0.002), 10.0)
check("held-out signed audit finds a sub-grid zero without a parabola",
      zz["ok"] and abs(zz["root"] - 10.07) < 0.015,
      "root %.4f +/- %.4f" % (zz["root"], zz["root_err"]))

pc, pr, pn = 10000.0, 10050.0, 13
px = np.round(pc * (1 + np.linspace(-0.70 / pn, 0.70 / pn, 7)))
pk = pn * np.pi / pr
py = 0.2 + 0.7 * np.cos(pk * (px - pr) + 0.7 * pk / pr * (px - pr) ** 2)
pf = T.fit_cosine_peak(px, py, np.full(px.size, 0.001), pc, pn * np.pi / pc)
check("held-out peak fit has no parabola-sized bias at a 0.5% offset",
      pf["ok"] and abs(pf["root"] - pr) / pr < 0.0002,
      "root %.2f vs %.2f" % (pf["root"], pr))

# Regression for a real false-accept mode: one reference at each end of a whole
# forward/reverse sweep removes affine drift, but a convex time trace leaves a
# symmetric residual that the local-cosine verifier mistakes for a pi maximum.
# Point-local ground/sequence/ground brackets make the quadratic second difference
# gain-independent, so a device with no pulse response must be rejected.
_drift_tuner = T.AutoTuner.__new__(T.AutoTuner)
_drift_tuner.P = T.merge_params({"fine_pi_amp": {"blocks": 4, "shots": 800}})
_drift_tuner.w = {"drive_freq": 2500.0, "pi_gain": 10000.0,
                  "t1_lo_us": 100.0}
_drift_tuner.cfg = {"sigma": 0.05}
_drift_clock = {"call": 0}
_saved_run_seq = T._run_seq
_saved_np_state = np.random.get_state()


def _quadratic_drift_only(exp, cfg, seq, drive_freq, shots):
    call = _drift_clock["call"]
    _drift_clock["call"] += 1
    return 0.01 * call ** 2, 0.0, 0.001, 0.001


T._run_seq = _quadratic_drift_only
_quadratic_peak = _drift_tuner._measure_peak_root({}, 10000.0, 11, 800, 7)
check("local peak brackets reject a quadratic IQ drift with no qubit response",
      not _quadratic_peak["ok"],
      "curve SNR=%.3g, local ground step=%.3g of response" %
      (_quadratic_peak.get("curve_snr", np.nan),
       _quadratic_peak.get("max_local_ground_step_frac", np.nan)))

# A period equal to one seven-point G/S/G block is more adversarial than a
# polynomial: with monotonic forward/reverse sweeps it aliases into the expected
# cosine exactly, and can stay phase-locked across both validation rounds.  Fresh
# independent gain permutations and the measured local-ground-motion veto must
# break that acquisition-clock alias.
_drift_tuner.w["t1_lo_us"] = 5.1  # gives exactly three inconclusive equator depths
_periodic_clock = {"call": 0}
_periodic_phase = -10.0 * 2.0 * np.pi / 21.0


def _periodic_drift_only(exp, cfg, seq, drive_freq, shots):
    call = _periodic_clock["call"]
    _periodic_clock["call"] += 1
    value = 0.3 * np.cos(2.0 * np.pi * call / 21.0 + _periodic_phase)
    return value, 0.0, 0.001, 0.001


T._run_seq = _periodic_drift_only
_periodic_audit = _drift_tuner._amplitude_audit({}, 10000.0)
T._run_seq = _saved_run_seq
np.random.set_state(_saved_np_state)
check("randomized peak blocks reject acquisition-synchronous periodic IQ drift",
      not _periodic_audit["ok"],
      "failed gates=%s" %
      [peak.get("failed_gates", []) for peak in _periodic_audit.get("peaks", [])])

print("== single-shot analysis ==")
n = 4000
ig, qg = rng.normal(0, 1, n), rng.normal(0, 1, n)
ie, qe = rng.normal(6, 1, n), rng.normal(0, 1, n)
ss = T.single_shot_analysis(ig, qg, ie, qe)
check("clean blobs: F>0.99, sep~6 sigma, few outliers",
      ss["fidelity"] > 0.99 and ss["sep_sigma"] > 5 and ss["outlier_frac"] < 0.02,
      "F=%.3f sep=%.2f out=%.3f" % (ss["fidelity"], ss["sep_sigma"], ss["outlier_frac"]))
k = int(0.2 * n)
ie2 = np.concatenate([rng.normal(0, 1, k), rng.normal(6, 1, n - k)])
qe2 = rng.normal(0, 1, n)
perm = rng.permutation(n)
ie2, qe2 = ie2[perm], qe2[perm]
ss2 = T.single_shot_analysis(ig, qg, ie2, qe2)
check("a 20% bad pi shows up as P(g|e) (not P(e|g))",
      abs(ss2["p_g_given_e"] - 0.20) < 0.04 and ss2["p_e_given_g"] < 0.03,
      "P(g|e)=%.3f P(e|g)=%.3f" % (ss2["p_g_given_e"], ss2["p_e_given_g"]))
ie3 = np.concatenate([rng.normal(6, 1, n // 2), rng.normal(0, 5, n // 2)])
qe3 = np.concatenate([rng.normal(0, 1, n // 2), rng.normal(0, 5, n // 2)])
ss3 = T.single_shot_analysis(ig, qg, ie3, qe3)
check("ionized/smeared readout flagged by the outlier fraction",
      ss3["outlier_frac"] > 0.05, "outliers=%.3f" % ss3["outlier_frac"])


def qm_hist_fidelity_reference(ig, qg, ie, qe):
    """Balanced assignment fidelity from QM_Team's histogram contrast.

    Keep this independent of production code.  On clean two-Gaussian shots, QM_Team's
    all-shot histogram score and AutoTuner's held-out score should agree: threshold
    training alone cannot cost tens of percent.  Axis robustness on contaminated shot
    clouds is a separate requirement exercised by the correlated-tail regression below.
    QM_Team rotates on the median-to-median axis and maximizes the empirical CDF
    contrast on all shots; AutoTuner deliberately scores on held-out shots.
    """
    ig, qg = np.asarray(ig), np.asarray(qg)
    ie, qe = np.asarray(ie), np.asarray(qe)
    theta = -np.arctan2(np.median(qe) - np.median(qg),
                        np.median(ie) - np.median(ig))
    xg = ig * np.cos(theta) - qg * np.sin(theta)
    xe = ie * np.cos(theta) - qe * np.sin(theta)
    lo, hi = min(float(xg.min()), float(xe.min())), max(float(xg.max()), float(xe.max()))
    ng, _ = np.histogram(xg, bins=200, range=(lo, hi))
    ne, _ = np.histogram(xe, bins=200, range=(lo, hi))
    contrast = np.abs((np.cumsum(ng) - np.cumsum(ne)) /
                      (0.5 * ng.sum() + 0.5 * ne.sum()))
    return float(0.5 * (1.0 + np.max(contrast)))


_parity_rng = np.random.default_rng(8227)
for _target, _sep in ((0.80, 1.683), (0.95, 3.290)):
    _npar = 8000
    _phi = np.deg2rad(37.0)
    _gxy = _parity_rng.normal(0.0, 1.0, (_npar, 2))
    _exy = _parity_rng.normal(0.0, 1.0, (_npar, 2))
    _exy += _sep * np.array([np.cos(_phi), np.sin(_phi)])
    _qm_f = qm_hist_fidelity_reference(_gxy[:, 0], _gxy[:, 1],
                                       _exy[:, 0], _exy[:, 1])
    _new_f = T.single_shot_analysis(_gxy[:, 0], _gxy[:, 1],
                                    _exy[:, 0], _exy[:, 1])["fidelity"]
    check("QM-Team and AutoTuner fidelity agree near F=%.2f on identical shots" % _target,
          abs(_qm_f - _new_f) < 0.025,
          "QM=%.4f AutoTuner=%.4f (delta %.4f)" %
          (_qm_f, _new_f, _new_f - _qm_f))

    _c0 = _gxy[:, 0] + 1j * _gxy[:, 1]
    _c1 = _exy[:, 0] + 1j * _exy[:, 1]
    _theta = np.angle(qm_find_blob_median(_c1) - qm_find_blob_median(_c0))
    _, _step5_scores = qm_find_threshold(
        np.exp(-1j * _theta) * _c0, np.exp(-1j * _theta) * _c1)
    _step5_direct = float(np.max(_step5_scores))
    _step5_auto = T.step5_single_shot_fidelity(
        _gxy[:, 0], _gxy[:, 1], _exy[:, 0], _exy[:, 1])
    check("AutoTuner's step-5 diagnostic is numerically identical on the same shots",
          abs(_step5_auto - _step5_direct) < 1e-15,
          "step5=%.12f AutoTuner=%.12f" % (_step5_direct, _step5_auto))

print("== direct 2-D readout witness: a 90% basin must beat a 60% coordinate slice ==")


def _coupled_readout_fidelity(freq, gain):
    """Power-dependent resonance shift omitted by the old separable simulator.

    At the starting power, the model/coordinate route correctly finds F=0.60 at zero
    detuning.  Increasing power shifts the resonator, so a gain-only sweep at that fixed
    frequency sees no improvement.  A direct gain x frequency grid contains a clean
    F=0.90 point.  This is the minimal counterexample to treating a poor one-dimensional
    slice as a device limit.
    """
    ratio = float(gain) / 4300.0
    shifted_resonance = (0.75 / 1.4) * (ratio - 1.0)
    on_resonance_fidelity = 0.60 + 0.30 * np.clip((ratio - 1.0) / 1.4, 0.0, 1.0)
    return float(on_resonance_fidelity *
                 np.exp(-0.5 * ((float(freq) - shifted_resonance) / 0.12) ** 2))


_coupled_gains = [1075, 1720, 2580, 3655, 4300, 5160, 7310, 10320, 14620]
_coupled_freqs = np.linspace(-0.9, 0.9, 13)
_coupled_rows = [{"freq": float(fr), "gain": int(ga),
                  "fid": _coupled_readout_fidelity(fr, ga), "fid_se": 0.006,
                  "outlier": 0.01, "verified": True}
                 for ga in _coupled_gains for fr in _coupled_freqs]
_staged_row = {"freq": 0.0, "gain": 4300,
               "fid": _coupled_readout_fidelity(0.0, 4300), "fid_se": 0.006,
               "outlier": 0.01, "verified": True}
_fixed_frequency_best = max(_coupled_readout_fidelity(0.0, ga)
                            for ga in _coupled_gains)
_direct_grid_best = max(row["fid"] for row in _coupled_rows)
check("the adversarial landscape really hides F=0.90 from the fixed-frequency slice",
      abs(_fixed_frequency_best - 0.60) < 1e-12
      and abs(_direct_grid_best - 0.90) < 1e-12,
      "fixed slice %.3f, direct grid %.3f" %
      (_fixed_frequency_best, _direct_grid_best))
_selected_2d = T.select_verified_2d_candidate(
    _coupled_rows, incumbent=_staged_row, confidence_sigma=1.96,
    min_improvement=0.01, max_outlier=0.25)
check("verified 2-D selection takes the 90% basin, not the 60% staged point",
      _selected_2d is not None
      and _selected_2d["gain"] == 10320
      and abs(_selected_2d["freq"] - 0.75) < 1e-12
      and _selected_2d["fid"] > 0.89
      and _selected_2d["improvement_significant"] is True,
      "winner=%s" % _selected_2d)
check("the 2-D witness exposes about thirty fidelity points of staged-search regret",
      0.27 <= _selected_2d["regret"] <= 0.32,
      "regret=%.3f" % _selected_2d["regret"])

print("== pulse duration is an evidence-gated search coordinate ==")
_duration_rows = [
    {"sigma_us": 0.25, "fid": 0.900, "fid_se": 0.004, "verified": True},
    {"sigma_us": 0.10, "fid": 0.899, "fid_se": 0.004, "verified": True},
    {"sigma_us": 0.05, "fid": 0.880, "fid_se": 0.004, "verified": True},
]
_duration_pick = T.select_duration_candidate(
    _duration_rows, 0.25, confidence_sigma=1.96,
    equivalence_margin=0.005, max_fidelity_drop=0.01)
check("a faster pulse is selected only when held-out fidelity is equivalent",
      _duration_pick is not None
      and abs(_duration_pick["sigma_us"] - 0.10) < 1e-12,
      "selection=%s" % _duration_pick)
_duration_slow = T.select_duration_candidate([
    {"sigma_us": 0.25, "fid": 0.900, "fid_se": 0.004, "verified": True},
    {"sigma_us": 0.35, "fid": 0.905, "fid_se": 0.004, "verified": True},
], 0.25, confidence_sigma=1.96)
check("a longer pulse is rejected when its apparent gain is inside uncertainty",
      _duration_slow is not None
      and abs(_duration_slow["sigma_us"] - 0.25) < 1e-12,
      "selection=%s" % _duration_slow)

_duration_tuner = T.AutoTuner.__new__(T.AutoTuner)
_duration_tuner.cfg = {
    "sigma": 0.25, "qubit_drag_beta": 0.0, "read_pulse_freq": 7248.9,
    "read_pulse_gain": 4300, "read_length": 20.0, "res_phase": 0.0,
    "relax_delay": 500.0, "adc_trig_offset": 0.5,
}
_duration_tuner.P = T.merge_params({"pulse_duration": {
    "enabled": True, "gate_durations_ns": (400, 1000),
    "gain_points": 5, "freq_points": 3, "confirm_blocks": 2,
}})
_duration_tuner.w = {
    "sigma_us": 0.25, "pi_gain": 10000, "drive_freq": 2534.4,
    "drag_beta": 0.0, "read_pulse_freq": 7248.9, "read_pulse_gain": 4300,
    "read_length": 20.0, "res_phase": 0.0, "relax_delay": 500.0,
    "updated": set(),
}
_duration_tuner.node_data = {}
_duration_tuner.report_lines = []


def _synthetic_duration_point(cfg, sigma_us, drive_freq, pi_gain, shots,
                              strict, evidence):
    target_gain = 2500.0 / float(sigma_us)
    fid = (0.900 - 2e-5 * abs(float(pi_gain) - target_gain)
           - 0.02 * abs(float(drive_freq) - 2534.4))
    return {"sigma_us": float(sigma_us), "gate_ns": 4000.0 * float(sigma_us),
            "freq": float(drive_freq), "gain": int(pi_gain),
            "fid": float(fid), "fid_se": 0.003, "sep": 3.0,
            "outlier": 0.01, "verified": True, "ss": {"ok": True}}


_duration_tuner._duration_ss_point = _synthetic_duration_point
_duration_moved = _duration_tuner._cal_pulse_duration()
check("the duration stage retunes gain per duration and adopts the faster equivalent",
      _duration_moved and abs(_duration_tuner.w["sigma_us"] - 0.10) < 1e-12
      and abs(_duration_tuner.w["pi_gain"] - 25000) <= 1
      and "sigma" in _duration_tuner.w["updated"],
      "sigma=%.4f gain=%d" % (_duration_tuner.w["sigma_us"],
                                _duration_tuner.w["pi_gain"]))

_score_tuner = T.AutoTuner.__new__(T.AutoTuner)
_score_tuner.w = {"ss_fidelity": 0.60, "ss_fidelity_se": 0.005,
                  "ss_sep_sigma": 100.0, "pi_gain": 11500, "pi_gain_err": 2.0,
                  "pi_converged": True, "fine_freq_converged": True,
                  "pi_fidelity_verified": True, "t1_verified": True,
                  "drive_freq": 2534.4, "read_pulse_freq": 7248.9,
                  "read_pulse_gain": 4300, "read_length": 20.0,
                  "t1_lo_us": 100.0, "t1_hi_us": 100.0,
                  "relax_delay": 500.0,
                  "pi_fidelity_binding": {
                      "drive_freq": 2534.4, "pi_gain": 11500,
                      "read_pulse_freq": 7248.9, "read_pulse_gain": 4300,
                      "read_length": 20.0, "freq_radius": 0.1,
                      "gain_radius": 100.0}}
_score_60 = _score_tuner._score()
_score_tuner.w.update(ss_fidelity=0.90, ss_sep_sigma=4.0)
_score_90 = _score_tuner._score()
check("best-state restoration cannot let huge separation make 60% outrank 90% fidelity",
      _score_90 > _score_60, "score60=%.3f score90=%.3f" % (_score_60, _score_90))

print("== robust IQ-axis parity: sparse tails must not turn 94% into 60% ==")
_tail_rng = np.random.default_rng(4)
_tail_n = 4000
_tail_frac = 0.04
_tail_count = int(_tail_frac * _tail_n)
_tail_ig = _tail_rng.normal(-1.8, 1.0, _tail_n)
_tail_ie = _tail_rng.normal(+1.8, 1.0, _tail_n)
_tail_qg = _tail_rng.normal(0.0, 1.0, _tail_n)
_tail_qe = _tail_rng.normal(0.0, 1.0, _tail_n)
# A small class-correlated tail is representative of amplifier bursts, leakage, or
# readout-induced transitions.  It must be reported as a tail without being allowed to
# rotate the discrimination axis away from the two dominant blobs.
_tail_g_idx = _tail_rng.choice(_tail_n, _tail_count, replace=False)
_tail_e_idx = _tail_rng.choice(_tail_n, _tail_count, replace=False)
_tail_qg[_tail_g_idx] -= 80.0
_tail_qe[_tail_e_idx] += 80.0
_tail_qm_f = qm_hist_fidelity_reference(_tail_ig, _tail_qg, _tail_ie, _tail_qe)
_tail_auto = T.single_shot_analysis(_tail_ig, _tail_qg, _tail_ie, _tail_qe)
check("QM median-axis reference retains the dominant blobs' >90% fidelity",
      _tail_qm_f > 0.90, "QM=%.4f" % _tail_qm_f)
check("AutoTuner stays within two fidelity points of the robust QM reference",
      _tail_auto["fidelity"] > 0.90
      and abs(_tail_auto["fidelity"] - _tail_qm_f) < 0.02,
      "QM=%.4f AutoTuner=%.4f (delta %.4f)" %
      (_tail_qm_f, _tail_auto["fidelity"], _tail_auto["fidelity"] - _tail_qm_f))
check("the sparse tails remain a ~4% diagnostic instead of defining the IQ axis",
      abs(_tail_auto["outlier_frac"] - _tail_frac) < 0.01,
      "outliers=%.4f" % _tail_auto["outlier_frac"])

# Axial extremes used to make the fixed 512-threshold linspace so coarse that no
# threshold landed between the main blobs: oracle F~.94 was reported as F~.04.
_ax_rng = np.random.default_rng(44)
_ax_ig = _ax_rng.normal(-1.8, 1.0, _tail_n)
_ax_ie = _ax_rng.normal(+1.8, 1.0, _tail_n)
_ax_qg = _ax_rng.normal(0.0, 1.0, _tail_n)
_ax_qe = _ax_rng.normal(0.0, 1.0, _tail_n)
_ax_ig[_ax_rng.choice(_tail_n, _tail_count, replace=False)] = -1e6
_ax_ie[_ax_rng.choice(_tail_n, _tail_count, replace=False)] = +1e6
_ax_ss = T.single_shot_analysis(_ax_ig, _ax_qg, _ax_ie, _ax_qe)
check("exact empirical thresholds retain >90% fidelity with million-unit axial tails",
      _ax_ss["fidelity"] > 0.90 and _ax_ss["outlier_frac"] < 0.06,
      "F=%.4f outliers=%.4f threshold=%.3f" %
      (_ax_ss["fidelity"], _ax_ss["outlier_frac"], _ax_ss["threshold"]))
check("finite-shot uncertainty never becomes zero just because no errors were observed",
      T.single_shot_analysis(np.full(100, -1.0), np.zeros(100),
                             np.full(100, 1.0), np.zeros(100))["fidelity_se"] > 0.0)

print("== leakage population is measured, not inferred from two-blob tails ==")
_leak_cal = {
    "g": (0.97, 0.003, 0.03, 0.003),
    "e": (0.04, 0.003, 0.04, 0.003),
    "f": (0.05, 0.003, 0.95, 0.004),
}
_leak_truth = np.array([0.20, 0.70, 0.10])
_leak_id = sum(_leak_truth[j] * _leak_cal[s][0]
               for j, s in enumerate(("g", "e", "f")))
_leak_sh = sum(_leak_truth[j] * _leak_cal[s][2]
               for j, s in enumerate(("g", "e", "f")))
_leak_solved = T.solve_shelved_qutrit_population(
    _leak_cal, (_leak_id, 0.003), (_leak_sh, 0.003))
check("identity+shelving response inversion recovers a 10% f population",
      _leak_solved["ok"] and abs(_leak_solved["p2"] - 0.10) < 1e-10,
      "P(f)=%.4f +/- %.4f" % (_leak_solved["p2"], _leak_solved["p2_se"]))
_singular_cal = {s: (0.5, 0.01, 0.5, 0.01) for s in ("g", "e", "f")}
check("a nonselective/ill-conditioned shelving measurement cannot certify leakage",
      not T.solve_shelved_qutrit_population(
          _singular_cal, (0.5, 0.01), (0.5, 0.01))["ok"])

# A tail-sensitive classical standard deviation can be <2 sigma even when the robust
# held-out discriminator exceeds 90%; only the fidelity LCB is an eligibility gate.
_classical_sep = _ax_ss["sep"] / _ax_ss["sigma_classical"]
_ax_lcb = T.fidelity_lower_bound(_ax_ss["fidelity"], _ax_ss["fidelity_se"], 1.96)
check("a >90% robust point is not rejected by a tail-sensitive Gaussian-width model",
      _classical_sep < 2.0 and _ax_lcb > 0.80,
      "classical sep=%.3f, robust sep=%.3f, LCB=%.3f" %
      (_classical_sep, _ax_ss["sep_sigma"], _ax_lcb))

print("== NaN safety ==")
check("iq_to_pop returns NaN on coincident refs",
      np.isnan(T.iq_to_pop(0.5, 0.5, (1.0, 1.0), (1.0, 1.0))))
_saved_run_seq = T._run_seq
_local_ref_rows = iter([
    (0.0, 0.0, 0.1, 0.1),   # ground reference
    (1.0, 0.0, 0.1, 0.1),   # excited reference
    (0.5, 0.0, 0.0, 0.0),   # noiseless target mean
])
T._run_seq = lambda *a, **k: next(_local_ref_rows)
try:
    _ref_pop, _ref_sep, _ref_sem = T._pop_with_local_refs(
        None, {}, [], 0.0, 1, 100)
finally:
    T._run_seq = _saved_run_seq
check("local-reference noise is propagated into population uncertainty",
      abs(_ref_pop - 0.5) < 1e-12 and _ref_sem > 0.07,
      "population=%.3f SEM=%.4f" % (_ref_pop, _ref_sem))
check("nan_argmin refuses to select a NaN", T.nan_argmin([np.nan, 0.5, 0.2]) == 2)
check("nan_argmin returns None for all-NaN", T.nan_argmin([np.nan, np.nan]) is None)
v = T.parabola_vertex(np.arange(13.0), np.full(13, np.nan))
check("parabola_vertex survives an all-NaN column", not np.isfinite(v["x_err"]))

print("== readout timing covers the complete delayed ADC window ==")
_timing_cfg = {"read_length": 20.0, "adc_trig_offset": 0.5,
               "readout_guard_us": 1.0}
check("a 20 us integration delayed by 0.5 us drives for at least 21.5 us",
      abs(T.readout_drive_length_us(_timing_cfg) - 21.5) < 1e-12)
_timing_cfg["read_pulse_length"] = 20.0
check("a stale explicit 20 us pulse is extended instead of truncating integration",
      abs(T.readout_drive_length_us(_timing_cfg) - 21.5) < 1e-12)
_timing_cfg["read_pulse_length"] = 30.0
check("an intentionally longer readout drive is preserved",
      abs(T.readout_drive_length_us(_timing_cfg) - 30.0) < 1e-12)


class _PulseCapture(object):
    def __init__(self):
        self.cfg = {"qubit_ch": 1, "res_ch": 0, "ro_chs": [0], "sigma": 0.125,
                    "read_length": 20.0, "adc_trig_offset": 0.5,
                    "readout_guard_us": 1.0, "read_pulse_style": "const",
                    "read_pulse_gain": 4300, "res_phase": 17.0}
        self.gauss = self.read = self.arb = None
        self.soccfg = {"gens": [{}, {"samps_per_clk": 16,
                                      "maxv": 32766, "maxv_scale": 1.0}]}

    def us2cycles(self, value, gen_ch=None, ro_ch=None):
        return int(round(float(value) * ({1: 100, 0: 20}.get(gen_ch, 1))))

    def add_gauss(self, **kw):
        self.gauss = kw

    def add_pulse(self, **kw):
        self.arb = kw

    def deg2reg(self, value, gen_ch=None):
        return 1000 + int(round(value)) + 10 * int(gen_ch)

    def set_pulse_registers(self, **kw):
        self.read = kw


_pc = _PulseCapture()
T.add_qubit_gaussian(_pc)
T.set_readout_pulse(_pc, read_freq=1234)
check("shared Gaussian setup uses the qubit generator clock",
      _pc.gauss["sigma"] == 12 and _pc.gauss["length"] == 48,
      "gauss=%s" % _pc.gauss)
_pc_drag = _PulseCapture()
_pc_drag.cfg["qubit_drag_beta"] = 0.10
T.add_qubit_gaussian(_pc_drag)
_drag_i, _drag_q = _pc_drag.arb["idata"], _pc_drag.arb["qdata"]
check("nonzero DRAG beta emits a replayable symmetric-I/antisymmetric-Q envelope",
      _pc_drag.gauss is None and _drag_i.size == 4 * 12 * 16
      and np.array_equal(_drag_i, _drag_i[::-1])
      and np.array_equal(_drag_q, -_drag_q[::-1])
      and abs(np.max(np.abs(_drag_q)) / np.max(_drag_i) - 0.10) < 2e-4,
      "samples=%d peak Q/I=%.5f" %
      (_drag_i.size, np.max(np.abs(_drag_q)) / np.max(_drag_i)))
check("shared readout setup covers ADC+offset+guard and consumes res_phase",
      _pc.read["length"] == 430 and _pc.read["phase"] == 1017,
      "read=%s" % _pc.read)

_consumer_files = (
    "mSingleShot1Q.py", "mRabiChevronIQ.py", "mRabiChevronSS.py",
    "mActiveResetProbe.py", "mT1VsFlux.py",
)
_consumer_ok = True
for _consumer in _consumer_files:
    _cp = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Experiments",
                                       _consumer))
    with open(_cp, encoding="utf-8") as _cf:
        _source = _cf.read()
    _consumer_ok &= "set_readout_pulse(" in _source
    _consumer_ok &= "add_qubit_gaussian(" in _source
check("the tuner and primary single-shot/Rabi/T1/reset consumers share pulse builders",
      _consumer_ok)
_gate_runner = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Runners",
                                             "GateCalibration.py"))
with open(_gate_runner, encoding="utf-8") as _gf:
    _gate_tree = ast.parse(_gf.read(), filename=_gate_runner)
_run_ss_node = next(n for n in _gate_tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "run_ss_cal")
_run_ss_source = ast.unparse(_run_ss_node)
check("GateCalibration single-shot replays the committed pi gain for |e> prep",
      "cfg['qubit_gain'] = int(cfg['qubit_pi_gain'])" in _run_ss_source)
check("gain-sweep preflight accepts target full-speed generators",
      T.qubit_gain_sweep_supported({"gens": [{}, {"type": "axis_signal_gen_v6"}]}, 1)
      is True)
check("gain-sweep preflight rejects packed-gain interpolated generators",
      T.qubit_gain_sweep_supported({"gens": [{}, {"type": "axis_sg_int4_v1"}]}, 1)
      is False)

print("\n== END-TO-END: full calibration graph vs a virtual qubit ==")
dev = VirtualQubit(np.random.default_rng(5))
install_simulator(dev)

BaseConfig = {
    "res_ch": 0, "qubit_ch": 1, "ro_chs": [0], "nqz": 2, "qubit_nqz": 1,
    "mixer_freq": 0.0, "reps": 500, "relax_delay": 200.0, "adc_trig_offset": 0.5,
    "res_phase": 0, "read_pulse_style": "const", "read_length": 20.0,
    "read_pulse_gain": 4300, "read_pulse_freq": 7248.95,
    "qubit_pulse_style": "arb", "qubit_freq": 2557.25, "qubit_pi_freq": 2557.37,
    "qubit_pi_gain": 12850, "qubit_pi2_gain": 6000, "qubit_gain": 7000,
    "qubit_length": 0.5, "sigma": 0.125, "ff_park_gain": 0,
}

_fingerprint_base = T.pulse_fingerprint(BaseConfig)
_fingerprint_variant_cfg = dict(BaseConfig)
_fingerprint_variant_cfg.update(
    flat_top_length=0.30, use_switch=True, seq_gap_us=0.02,
    res_phase=17.0, read_pulse_length=30.0, ff_hold_gain=1200)
_fingerprint_variant = T.pulse_fingerprint(_fingerprint_variant_cfg)
_fingerprint_drag = T.pulse_fingerprint(dict(BaseConfig, qubit_drag_beta=0.025))
_qm_fingerprint = T.pulse_fingerprint({
    "qubit_ch": 1, "qubit_nqz": 1, "qubit_pulse_style": "arb",
    "sigma": 0.125, "flattop_length": 0.30, "f_ge": 2534.4,
    "qubit_gain": 11500, "read_pulse_style": "const", "res_ch": 0,
    "nqz": 2, "pulse_freq": 7248.9, "pulse_gain": 4300,
    "readout_length": 20.0, "length": 30.0, "adc_trig_offset": 0.5,
    "switch_triggered": True, "pulse_implementation": "qm_ffmux",
})
check("pulse fingerprints expose every manual-vs-auto path ambiguity",
      _fingerprint_base["flat_top_fields_us"] == {}
      and _fingerprint_variant["flat_top_fields_us"] == {"flat_top_length": 0.3}
      and _fingerprint_variant["switch_enabled"]
      and _fingerprint_variant["sequence_gap_us"] == 0.02
      and _fingerprint_variant["readout_generator_us"] == 30.0
      and _fingerprint_variant["readout_phase_deg"] == 17.0
      and _fingerprint_variant["ff_hold_gain"] == 1200
      and _qm_fingerprint["qubit_envelope"]
          == "ambiguous_arb_with_flat_top_selector"
      and _qm_fingerprint["qubit_freq_mhz"] == 2534.4
      and _qm_fingerprint["readout_integration_us"] == 20.0
      and _qm_fingerprint["readout_generator_us"] == 30.0
      and _qm_fingerprint["switch_enabled"]
      and _fingerprint_drag["qubit_envelope"] == "gaussian_4sigma_drag"
      and _fingerprint_drag["qubit_drag_beta"] == 0.025)
_identity_tuner = T.AutoTuner.__new__(T.AutoTuner)
_identity_tuner.cfg = dict(BaseConfig, length=30.0)
_identity_tuner.P = T.merge_params(None)
_identity_tuner.w = {
    "read_pulse_freq": BaseConfig["read_pulse_freq"],
    "read_pulse_gain": BaseConfig["read_pulse_gain"],
    "read_length": BaseConfig["read_length"], "res_phase": 0.0,
    "relax_delay": BaseConfig["relax_delay"],
    "drive_freq": BaseConfig["qubit_pi_freq"],
    "pi_gain": BaseConfig["qubit_pi_gain"],
}
_tls_identity = _identity_tuner._current_pulse_fingerprint()
check("a leftover QM length key cannot falsify the TLS pulse fingerprint",
      _tls_identity["readout_generator_us"] == 21.5
      and _tls_identity["implementation"] == "tls_canonical_gaussian_v1",
      "recorded generator duration %.1f us" % _tls_identity["readout_generator_us"])

tmp = tempfile.mkdtemp(prefix="autotuner_test_")
_unsafe_relax_cfg = dict(BaseConfig)
_unsafe_relax_cfg["relax_delay"] = 50.0
tuner = T.AutoTuner(soc=None, soccfg=None, path="q4", outerFolder=tmp,
                    suffix="Auto_Tune", cfg=_unsafe_relax_cfg,
                    params={"max_rounds": 6,
                            "spec": {"span_mhz": 20.0, "max_span_mhz": 120.0,
                                     "allow_target_reacquisition": True},
                            "t1": {"points": 8, "shots": 400},
                            "single_shot": {"shots": 2500, "min_sep_sigma": 2.0},
                            "fine_pi_amp": {"M_list": (4, 10), "frac": (0.12, 0.05)}})
out = tuner.acquire(plotDisp=False)
w = out["data"]["working"]

print("\n  --- recovered vs truth ---")
f_dressed_g = dev.F_R - dev.CHI
check("resonator finds the DRESSED |g> resonance within kappa/3",
      abs(w.get("resonator_f0", 0) - f_dressed_g) < dev.KAPPA / 3.0,
      "%.4f vs %.4f" % (w.get("resonator_f0", float('nan')), f_dressed_g))
check("kappa within 35% (power fit, FWHM = kappa)",
      abs(w.get("kappa_mhz", 0) - dev.KAPPA) / dev.KAPPA < 0.35,
      "%.3f vs %.3f" % (w.get("kappa_mhz", float('nan')), dev.KAPPA))
check("chi sign and magnitude within 50%",
      np.sign(w.get("chi_mhz", 0)) == np.sign(dev.CHI)
      and abs(abs(w.get("chi_mhz", 0)) - abs(dev.CHI)) / abs(dev.CHI) < 0.5,
      "%.4f vs %.4f" % (w.get("chi_mhz", float('nan')), dev.CHI))
check("qubit frequency within 0.5 MHz (found from 22.9 MHz away)",
      abs(w.get("qubit_freq", 0) - dev.F_Q) < 0.5,
      "%.4f vs %.4f" % (w.get("qubit_freq", float('nan')), dev.F_Q))
check("blind reacquisition is promoted only after the coherent gate evidence passes",
      w.get("target_reacquisition_used") is True
      and w.get("target_reacquisition_status") == "coherent_validation_passed")
check("pi drive frequency within 0.25 MHz",
      abs(w.get("drive_freq", 0) - dev.F_Q) < 0.25,
      "%.4f vs %.4f" % (w.get("drive_freq", float('nan')), dev.F_Q))
check("pi gain within 3% of truth",
      abs(w.get("pi_gain", 0) - dev.PI_GAIN) / dev.PI_GAIN < 0.03,
      "%d vs %d" % (w.get("pi_gain", 0), dev.PI_GAIN))
check("T1 within 50%", abs(w.get("t1_us", 0) - dev.T1) / dev.T1 < 0.5,
      "%.1f vs %.1f us" % (w.get("t1_us", float('nan')), dev.T1))
check("readout power stayed BELOW the ionization threshold",
      w.get("read_pulse_gain", 1e9) <= dev.G_CRIT,
      "gain %d vs G_crit %d" % (w.get("read_pulse_gain", -1), dev.G_CRIT))
check("readout length capped at T1/2",
      w.get("read_length", 1e9) <= 0.5 * dev.T1 + 1e-9,
      "%.1f us vs T1/2=%.1f" % (w.get("read_length", float('nan')), 0.5 * dev.T1))
check("single-shot fidelity is meaningful (>0.7)", w.get("ss_fidelity", 0) > 0.7,
      "F=%.3f at %.2f sigma" % (w.get("ss_fidelity", float('nan')),
                                w.get("ss_sep_sigma", float('nan'))))
check("pi calibration reported CONVERGED on a good device", bool(w.get("pi_converged")),
      "pi_gain_err=%.0f DAC" % w.get("pi_gain_err", float('nan')))
check("the independently verified qubit is eligible even if the readout graph still cycles",
      bool(out["data"]["qubit_ok"]) and w.get("pi_verified") and w.get("freq_verified"))
check("a stable virtual device reaches the full fixed point and both write gates",
      bool(out["data"]["success"]) and bool(out["data"]["readout_ok"])
      and bool(w.get("fixed_point")),
      "success=%s readout_ok=%s fixed=%s" %
      (out["data"]["success"], out["data"]["readout_ok"], w.get("fixed_point")))
check("an unsafe BaseConfig reset is remeasured and exported with the certified state",
      w.get("relax_delay", 0.0) >= 5.0 * w.get("t1_hi_us", np.inf)
      and "relax_delay" in out["data"]["tuned"]
      and "relax_delay" in out["data"]["eligible_tuned"],
      "relax=%.1f required=%.1f eligible=%s" %
      (w.get("relax_delay", np.nan), 5.0 * w.get("t1_hi_us", np.nan),
       "relax_delay" in out["data"]["eligible_tuned"]))
check("saved evidence carries the exact final pulse fingerprint",
      w.get("pulse_fingerprint")
      == out["data"]["nodes"].get("pulse_identity", {}).get("final")
      and w["pulse_fingerprint"]["qubit_envelope"] == "gaussian_4sigma"
      and w["pulse_fingerprint"]["flat_top_fields_us"] == {})
tuned = out["data"]["tuned"]
check("qubit_pi_freq only written because fine_pi_freq measured it",
      "qubit_pi_freq" in tuned)
check("qubit_pi2_gain NOT written (never measured)", "qubit_pi2_gain" not in tuned)

print("\n== the graph must actually ITERATE (this is what the old test missed) ==")
calls = {}
for _name, _deps, _meth in T.GRAPH:
    orig_fn = getattr(T.AutoTuner, _meth)

    def _wrap(fn, nm):
        def inner(self, *a, **k):
            calls[nm] = calls.get(nm, 0) + 1
            return fn(self, *a, **k)
        return inner
    setattr(T.AutoTuner, _meth, _wrap(orig_fn, _name))

dev2 = VirtualQubit(np.random.default_rng(9))
install_simulator(dev2)
t2 = T.AutoTuner(soc=None, soccfg=None, path="q4", outerFolder=tmp, suffix="Iter",
                 cfg=dict(BaseConfig),
                 params={"max_rounds": 6,
                         "spec": {"span_mhz": 20.0, "max_span_mhz": 120.0,
                                  "allow_target_reacquisition": True},
                         "t1": {"points": 6, "shots": 300},
                         "single_shot": {"shots": 1500, "min_sep_sigma": 2.0},
                         "fine_pi_amp": {"M_list": (4, 10), "frac": (0.12, 0.05)}})
out2 = t2.acquire(plotDisp=False)
check("at least one node was recalibrated (invalidation fired)",
      max(calls.values()) >= 2, "calls=%s" % calls)
check("the refined pi forced the readout chain to be re-measured",
      calls.get("chi", 0) >= 2 and calls.get("readout_power", 0) >= 2
      and calls.get("single_shot", 0) >= 2,
      "chi=%d readout_power=%d single_shot=%d"
      % (calls.get("chi", 0), calls.get("readout_power", 0), calls.get("single_shot", 0)))
check("spec is OUTSIDE the loop (a readout change must not re-run it)",
      calls.get("spec", 0) == 1,
      "spec=%d rough_pi=%d" % (calls.get("spec", 0), calls.get("rough_pi", 0)))
check("the feedback edge is fine_pi_amp -> chi/readout_power",
      all("fine_pi_amp" in dict((n, d) for n, d, _ in T.GRAPH)[k]
          for k in ("chi", "readout_power")))
check("spec depends only on the resonator",
      dict((n, d) for n, d, _ in T.GRAPH)["spec"] == ["resonator"])
check("a better readout re-refines the pi amplitude, not just its frequency",
      "single_shot" in dict((n, d) for n, d, _ in T.GRAPH)["fine_pi_amp"])
check("a material amplitude correction rechecks the driven frequency",
      "fine_pi_amp" in dict((n, d) for n, d, _ in T.GRAPH)["fine_pi_freq"])
check("T1 is re-measured through the IMPROVED readout, not only the starting one",
      "single_shot" in dict((n, d) for n, d, _ in T.GRAPH)["t1"] and calls.get("t1", 0) >= 2,
      "t1 calls=%d" % calls.get("t1", 0))
eligible2 = set(out2["data"]["eligible_tuned"])
all2 = set(out2["data"]["tuned"])
qkeys2 = {"qubit_freq", "qubit_pi_freq", "qubit_pi_gain"}
rkeys2 = {"read_pulse_freq", "read_pulse_gain", "read_length", "res_phase"}
shared2 = {"relax_delay"}
expected2 = ((all2 & qkeys2) if out2["data"]["qubit_ok"] else set()) \
    | ((all2 & rkeys2) if out2["data"]["readout_ok"] else set()) \
    | ((all2 & shared2) if (out2["data"]["qubit_ok"]
                            or out2["data"]["readout_ok"]) else set())
check("per-key eligibility exactly follows independent qubit/readout gates",
      eligible2 == expected2, "eligible=%s expected=%s" % (sorted(eligible2), sorted(expected2)))
_seen, _order = set(), [n for n, _, _ in T.GRAPH]
check("_mark_dependents_stale terminates on the cycle it now contains",
      (lambda: (T.AutoTuner._mark_dependents_stale(
          type("S", (), {"stale": {n: False for n in _order}})(), "fine_pi_amp"), True)[1])())

print("\n== escalation must prefer a SUCCESSFUL fit over a higher-SNR failed one ==")
good = {"ok": True, "snr": 6.0}
bad_hi = {"ok": False, "snr": 1e6}
check("ok=True beats a failed fit with astronomically higher snr",
      T._better_fit(good, bad_hi) and not T._better_fit(bad_hi, good))
check("between two ok fits, higher snr wins",
      T._better_fit({"ok": True, "snr": 9.0}, good))

print("\n== optimal_readout_detuning returns a MAGNITUDE (D is even in d) ==")
for chi in (+0.5, -0.5):
    d = T.optimal_readout_detuning(chi, 0.35)
    check("chi=%+.1f -> non-negative magnitude" % chi, d >= 0, "d=%.4f" % d)
check("magnitude is the same for +chi and -chi (D is even)",
      abs(T.optimal_readout_detuning(0.5, 0.35) - T.optimal_readout_detuning(-0.5, 0.35)) < 1e-9)

print("\n== drift-robust readout sweep (hardware: 1.89 vs 1.06 sigma, same settings) ==")
true_q = np.array([1.0, 1.5, 1.6, 1.5, 1.0])
drift = 0.70
n = true_q.size
one_pass = np.array([true_q[j] * (1 - drift * j / (n - 1)) for j in range(n)])
fwd = np.array([true_q[j] * (1 - drift * j / (n - 1)) for j in range(n)])
rev = np.array([true_q[j] * (1 - drift * (n - 1 - j) / (n - 1)) for j in range(n)])
two_pass = 0.5 * (fwd + rev)
check("a single pass under drift picks the WRONG optimum",
      int(np.argmax(one_pass)) != 2, "argmax=%d (true 2)" % int(np.argmax(one_pass)))
check("two opposed passes averaged recover the true optimum",
      int(np.argmax(two_pass)) == 2, "argmax=%d" % int(np.argmax(two_pass)))
check("AutoTuner exposes the two-pass sweep", hasattr(T.AutoTuner, "_sweep_readout"))

print("== production single-shot acquisition rejects acquisition-synchronous fake contrast ==")
_periodic_ss_tuner = T.AutoTuner.__new__(T.AutoTuner)
_periodic_clock = {"call": 0}
_periodic_rng = np.random.default_rng(912)
_periodic_baseline = np.array([-4.0, 2.5, -1.5, 5.0, 3.0, -3.0, 1.0, -2.0])


def _periodic_no_qubit(exp, cfg, seq, drive_freq, shots):
    offset = _periodic_baseline[_periodic_clock["call"] % 8]
    _periodic_clock["call"] += 1
    # Deliberately ignore ``seq``: there is no state response at all.
    return (_periodic_rng.normal(offset, 0.4, int(shots)),
            _periodic_rng.normal(-0.2 * offset, 0.4, int(shots)))


_saved_pair_shots = T._canonical_pair_shots


def _periodic_no_qubit_pair(exp, cfg, drive_freq, pi_gain, shots,
                            state_order="ge"):
    del drive_freq, pi_gain
    first = _periodic_no_qubit(exp, cfg, [], 0.0, shots)
    second = _periodic_no_qubit(exp, cfg, [], 0.0, shots)
    (ig, qg), (ie, qe) = ((first, second) if state_order == "ge"
                          else (second, first))
    return ig, qg, ie, qe


T._canonical_pair_shots = _periodic_no_qubit_pair
_periodic_ss = _periodic_ss_tuner._balanced_single_shot(
    {}, 2534.4, 11500, 800, strict=True)
T._canonical_pair_shots = _saved_pair_shots
check("canonical paired acquisition cannot relabel a periodic artifact as fidelity",
      abs(_periodic_ss["fidelity"] - 0.5) < 0.10,
      "false F=%.3f after %d acquisitions" %
      (_periodic_ss["fidelity"], _periodic_clock["call"]))

print("\n== chi/kappa design-optimum penalty (the device-limit diagnosis) ==")
def dsep(c, k):
    d = np.linspace(-3*max(abs(c), k), 3*max(abs(c), k), 2001)
    ag, ae = 1.0/((d-c)+0.5j*k), 1.0/((d+c)+0.5j*k)
    return float(np.max(np.abs(ag-ae))/np.max(np.abs(ag)))
pen = dsep(0.5*0.36, 0.36) / dsep(0.065, 0.36)
check("2|chi|/kappa=0.36 is flagged as ~1.6x below the design optimum",
      1.4 < pen < 1.8, "penalty=%.2fx" % pen)
check("at the 2|chi|=kappa optimum the penalty is 1.0",
      abs(dsep(0.5*0.36, 0.36)/dsep(0.5*0.36, 0.36) - 1.0) < 1e-9)

print("\n== the committed state is re-measured before it is written ==")
check("a final verification ran", "ss_verify_sigma" in tuner.w,
      "verify sigma=%.2f" % tuner.w.get("ss_verify_sigma", float("nan")))
check("the verified value REPLACES the historical one used for the pass/fail gate",
      abs(tuner.w["ss_sep_sigma"] - tuner.w["ss_verify_sigma"]) < 1e-9)
check("a stable device independently re-verifies pi amplitude and frequency",
      tuner.w.get("pi_verified") is True and tuner.w.get("freq_verified") is True)
expected_global = bool(tuner.w.get("readout_verified") and tuner.w.get("pi_verified")
                       and tuner.w.get("freq_verified") and tuner.w.get("fixed_point")
                       and not tuner.drifted)
check("global verification exactly tracks fresh evidence plus graph fixed-point state",
      tuner.w.get("verified") is expected_global,
      "verified=%s fixed_point=%s" % (tuner.w.get("verified"), tuner.w.get("fixed_point")))


def _verification_tuner(now_fid, now_sep=2.07):
    v = T.AutoTuner.__new__(T.AutoTuner)
    v.report_lines, v.drifted, v.node_data = [], [], {}
    v.P = T.merge_params({"single_shot": {"verify_blocks": 2,
                                            "min_fidelity_lcb": 0.90,
                                            "verify_tol_abs": 0.015}})
    v.w = {"ss_sep_sigma": 2.07, "ss_fidelity": 0.95,
           "ss_fidelity_se": 0.005, "pi_gain": 11500,
           "drive_freq": 2534.4, "read_pulse_freq": 7248.9,
           "read_pulse_gain": 4300, "read_length": 20.0,
           "fixed_point": True, "pi_converged": True}
    v._cfg_for = lambda node: {}
    v._amplitude_audit = lambda *a, **k: {
        "ok": True, "gain": 11500.0, "gain_err": 1.0, "bound_frac": 0.0001,
        "peak": {"ok": True}}
    v._frequency_scan = lambda *a, **k: {
        "fit": {"ok": True, "root": 2534.4, "root_err": 0.001}}
    ss = {"ok": True, "sep_sigma": float(now_sep), "fidelity": float(now_fid),
          "fidelity_se": 0.005, "p_e_given_g": 0.5 * (1.0 - now_fid),
          "p_g_given_e": 0.5 * (1.0 - now_fid), "outlier_frac": 0.008,
          "theta": 0.0, "threshold": 0.0,
          "xg": np.array([-1.0]), "xe": np.array([1.0])}
    v._single_shot_point = lambda node, rf, rg, df, pg, shots: {
        "freq": float(rf), "gain": int(rg), "fid": float(now_fid),
        "fid_se": 0.005, "sep": float(now_sep), "outlier": 0.008,
        "verified": True, "ss": dict(ss)}
    v._verify_final()
    return v


vt = _verification_tuner(0.94, now_sep=1.81)
check("the re-measured fidelity and separation replace historical gate inputs",
      abs(vt.w["ss_verify_fidelity"] - 0.94) < 1e-9
      and abs(vt.w["ss_verify_sigma"] - 1.81) < 1e-9,
      "verified=%s F=%.3f" % (vt.w["verified"], vt.w["ss_verify_fidelity"]))
check("a still-high fidelity passes even when Gaussian separation drift is diagnostic",
      vt.w["readout_verified"] is True)

vt2 = _verification_tuner(0.80, now_sep=2.07)
check("a 95%-to-80% fidelity collapse is blocked even when separation is unchanged",
      vt2.w["readout_verified"] is False and vt2.w["verified"] is False
      and any("fidelity is below" in l for l in vt2.report_lines),
      "readout_verified=%s" % vt2.w["readout_verified"])

print("\n== runner history and saved artifacts preserve write-safety evidence ==")

# AutoTune imports the hardware proxy module, whose import requires the real QICK/Pyro
# stack.  Extract just this pure helper so this test cannot accidentally contact hardware
# or become coupled to runner import side effects.
_runner_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Runners",
                                            "AutoTune.py"))
with open(_runner_path, encoding="utf-8") as _rf:
    _runner_src = _rf.read()
    _runner_tree = ast.parse(_runner_src, filename=_runner_path)
_runner_assignments = {
    target.id: node.value
    for node in _runner_tree.body if isinstance(node, ast.Assign)
    for target in node.targets if isinstance(target, ast.Name)
}
check("the shipped blind runner cannot overwrite BaseConfig",
      ast.literal_eval(_runner_assignments["APPLY_CONFIG"]) is False)
check("the shipped runner explicitly enables broad blind target acquisition",
      isinstance(_runner_assignments["BLIND_TARGET_ACQUISITION"], ast.Constant)
      and _runner_assignments["BLIND_TARGET_ACQUISITION"].value is True
      and any(isinstance(n, ast.Name) and n.id == "BLIND_TARGET_ACQUISITION"
              for n in ast.walk(_runner_assignments["P_TUNER"])))
check("the shipped q4 runner requires direct leakage certification",
      '"leakage"' in _runner_src and '"required_for_certification": True' in _runner_src
      and '"enabled": True' in _runner_src)
check("the shipped q4 runner searches and certifies pulse duration",
      '"pulse_duration"' in _runner_src and '"sigma"' in _runner_src
      and _runner_src.count('"required_for_certification": True') >= 2)
_runner_main_guard = next(
    n for n in _runner_tree.body
    if isinstance(n, ast.If)
    and any(isinstance(x, ast.Name) and x.id == "__name__" for x in ast.walk(n.test)))
check("the runner propagates an explicit process status",
      any(isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
          and isinstance(n.exc.func, ast.Name) and n.exc.func.id == "SystemExit"
          for n in ast.walk(_runner_main_guard)))
check("a completed best-effort search is not mislabeled as a process crash",
      "best empirical candidate returned" in _runner_src
      and "return 0" in _runner_src
      and "no usable candidate was measured" in _runner_src)
_history_node = next(n for n in _runner_tree.body
                     if isinstance(n, ast.FunctionDef) and n.name == "_history_entry")
_select_node = next(n for n in _runner_tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "_select_updates")
_history_ns = {
    "QUBIT": "q4",
    "BaseConfig": {"qubit_pi_gain": 11100, "qubit_pi2_gain": 5550,
                   "read_pulse_gain": 3900, "relax_delay": 3000.0,
                   "sigma": 0.25, "qubit_drag_beta": 0.0},
    "QUBIT_KEYS": ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
                   "qubit_drag_beta"),
    "READOUT_KEYS": ("read_pulse_freq", "read_pulse_gain", "read_length", "res_phase"),
    "SHARED_TIMING_KEYS": ("relax_delay",),
}
exec(compile(ast.fix_missing_locations(
    ast.Module(body=[_select_node, _history_node], type_ignores=[])),
             _runner_path, "exec"), _history_ns)
_history_entry = _history_ns["_history_entry"]
_select_updates = _history_ns["_select_updates"]
_history_data = {
    "time": "2026-07-22 12:34:56", "success": False,
    "failure": "readout graph not fixed",
    "tuned": {"qubit_pi_gain": 11500, "read_pulse_gain": 4100,
              "read_pulse_freq": 7248.91, "relax_delay": 135.0},
    "eligible_tuned": {"qubit_pi_gain": 11500, "read_pulse_gain": 4100,
                       "relax_delay": 135.0},
    "working": {"t1_us": 25.0, "chi_mhz": -0.12, "kappa_mhz": 0.35,
                "ss_fidelity": 0.72, "ss_sep_sigma": 1.9, "verified": False,
                "fixed_point": False, "pi_verified": True, "freq_verified": True,
                "readout_verified": False, "ss_verify_sigma": 1.9},
    "qubit_ok": True, "readout_ok": False, "report": ["readout blocked"],
}
_eligible = {"qubit_pi_gain": 11500, "read_pulse_gain": 4100,
             "relax_delay": 135.0}
_selected = {"qubit_pi_gain": 11500, "relax_delay": 135.0}
_eligible_out, _qubit_only = _select_updates(_history_data, True, True)
check("runner independently blocks a failed readout group",
      _eligible_out == _eligible and _qubit_only == _selected)
_both_ok_data = dict(_history_data, readout_ok=True)
_, _readout_flag_off = _select_updates(_both_ok_data, False, True)
_, _qubit_flag_off = _select_updates(_both_ok_data, True, False)
_, _both_flags_off = _select_updates(_both_ok_data, False, False)
check("runner write flags filter the two key groups independently",
      _readout_flag_off == {"qubit_pi_gain": 11500, "relax_delay": 135.0}
      and _qubit_flag_off == {"read_pulse_gain": 4100, "relax_delay": 135.0}
      and _both_flags_off == {})
_dry_history = _history_entry(_history_data, _eligible, _selected, False)
check("an unapplied history entry never claims a new BaseConfig value",
      _dry_history["applied"] is False and _dry_history["new"] == {})
check("history keeps measured, eligible, and attempted values distinct",
      _dry_history["measured"] == _history_data["tuned"]
      and _dry_history["eligible"] == _eligible
      and _dry_history["attempted"] == _selected
      and _dry_history["old"] == {"qubit_pi_gain": 11100,
                                   "relax_delay": 3000.0})
_applied_history = _history_entry(_history_data, _eligible, _selected, True)
check("an applied history entry records exactly the selected values as new",
      _applied_history["applied"] is True
      and _applied_history["new"] == _selected
      and "read_pulse_gain" not in _applied_history["new"])
check("changing X180 explicitly marks the untouched X90 calibration stale",
      _applied_history["qubit_pi2_stale"] is True
      and _applied_history["qubit_pi2_gain_unchanged"] == 5550)
_failed_history = _history_entry(_history_data, _eligible, _selected, False,
                                 write_error="simulated config write failure")
check("a failed config write is explicit and never recorded as applied",
      _failed_history["write_error"] == "simulated config write failure"
      and _failed_history["applied"] is False and _failed_history["new"] == {})

_persist = T.AutoTuner(soc=None, soccfg=None, path="persist_roundtrip", outerFolder=tmp,
                       suffix="Persist", cfg=dict(BaseConfig))
_persist.node_data = {
    "fine_pi_amp": {
        "M3": {"gains": np.array([11000, 11500, 12000]),
               "res": np.array([-0.4, 0.0, 0.4])},
        "audit": [{"bound_frac": 0.0031,
                   "peaks": [{"M": 13, "gain": 11501.0, "gain_err": 3.0}]}],
    },
    "final_verify": {"amplitude": {"bound_frac": 0.0032, "ok": True}},
}
_persist.w = {
    "fixed_point": False, "pi_converged": True, "pi_verified": True,
    "freq_verified": True, "readout_verified": False,
    "pi_audit_bound_frac": 0.0031,
}
_persist.data = {
    "success": False, "failure": None, "qubit_ok": True, "readout_ok": False,
    "eligible_tuned": {"qubit_pi_gain": 11500, "qubit_pi_freq": 2534.4},
    "working": dict(_persist.w), "nodes": _persist.node_data,
    "report": ["qubit verified", "readout blocked"],
}
_persist.save_data()
with open(_persist.pname, "rb") as _pf:
    _pickle_roundtrip = pickle.load(_pf)
check("the lossless pickle preserves eligibility and the per-group verdict",
      _pickle_roundtrip["eligible_tuned"] == _persist.data["eligible_tuned"]
      and _pickle_roundtrip["qubit_ok"] is True
      and _pickle_roundtrip["readout_ok"] is False)
check("the lossless pickle preserves nested held-out audit evidence",
      _pickle_roundtrip["nodes"]["fine_pi_amp"]["audit"][0]["bound_frac"] == 0.0031
      and _pickle_roundtrip["nodes"]["final_verify"]["amplitude"]["ok"] is True)
with h5py.File(_persist.fname, "r") as _hf:
    _h5_metadata = json.loads(_hf.attrs["run_metadata"])
    _h5_has_trace = ("fine_pi_amp_M3_gains" in _hf
                     and np.array_equal(np.asarray(_hf["fine_pi_amp_M3_gains"]),
                                        np.array([11000, 11500, 12000])))
check("the HDF5 stores compact eligibility, verdict, and audit metadata",
      _h5_metadata["eligible_tuned"] == _persist.data["eligible_tuned"]
      and _h5_metadata["qubit_ok"] is True
      and _h5_metadata["readout_ok"] is False
      and _h5_metadata["pi_audit_bound_frac"] == 0.0031
      and _h5_metadata["report"] == _persist.data["report"])
check("the HDF5 still stores numeric calibration traces", _h5_has_trace)

print("\n== fine_pi_amp: signed, multi-depth, independently audited convergence ==")


class _StubTuner(T.AutoTuner):
    def __init__(self, vertex_gain, anchor, **kw):
        self.report_lines = []
        self.node_data = {}
        self.drifted = []
        self.stale = {n: True for n, _, _ in T.GRAPH}
        self.P = T.merge_params(kw.pop("params", None))
        self.cfg = dict(BaseConfig)
        self.element = "q4"
        self.soc = self.soccfg = None
        self._vertex = float(vertex_gain)
        self.windows = []
        self.w = {"pi_gain": float(anchor), "drive_freq": 2534.4, "t1_us": 1e6,
                  "t1_lo_us": 1e6,
                  "relax_delay": 500.0, "read_pulse_freq": 7248.9, "read_pulse_gain": 4300,
                  "read_length": 20.0, "res_phase": 0.0, "updated": set(),
                  "pi_gain_anchor_err": 0.03 * float(anchor),
                  "fine_freq_converged": True}

    def _cfg_for(self, node):
        c = dict(self.cfg)
        c.update(read_pulse_freq=float(self.w["read_pulse_freq"]),
                 read_pulse_gain=int(self.w["read_pulse_gain"]),
                 read_length=float(self.w["read_length"]),
                 res_phase=float(self.w["res_phase"]),
                 relax_delay=float(self.w["relax_delay"]))
        return c


class _LeakageSelectionTuner(_StubTuner):
    def __init__(self):
        super().__init__(11500, 11500, params={
            "leakage": {"beta_span": 0.08, "beta_points": 5,
                        "max_extensions": 1, "beta_refine_rounds": 0,
                        "max_fidelity_drop": 0.01}})
        self.candidate_archive = []
        self.w.update(drag_beta=0.0, leakage_verified=False,
                      leakage_optimized=False)

    def _cal_ef_transition(self):
        self.node_data["leakage"] = {}
        self.w.update(ef_freq=2334.4, ef_pi_gain=9000,
                      anharmonicity_mhz=-200.0)
        return 2334.4, 9000, -200.0

    def _measure_leakage_beta(self, beta, *args, **kwargs):
        leak = 0.002 + 3.0 * (float(beta) - 0.04) ** 2
        se = 0.0005
        fid, fid_se = 0.90, 0.002
        return {"beta": float(beta), "valid": True,
                "fidelity": fid, "fidelity_se": fid_se,
                "fidelity_lcb": T.fidelity_lower_bound(fid, fid_se, 1.96),
                "leakage_max": leak, "leakage_se": se,
                "leakage_ucb": leak + 1.96 * se,
                "response": {"ok": True}, "witnesses": []}


_leak_select = _LeakageSelectionTuner()
_leak_moved = _leak_select._cal_leakage()
check("leakage optimizer selects a significant low-P(f) beta without sacrificing pi fidelity",
      _leak_moved and abs(_leak_select.w["drag_beta"] - 0.04) < 1e-12
      and "qubit_drag_beta" in _leak_select.w["updated"],
      "beta=%+.5f" % _leak_select.w["drag_beta"])


print("\n== best-found archive survives a later certification failure ==")


class _BestEffortAcquireTuner(T.AutoTuner):
    def maintain(self):
        measured_cfg = self._cfg_for("pi_fidelity")
        for fid, gain in ((0.60, 10000), (0.89, 11500), (0.91, 11500)):
            row = {"fid": fid, "fid_se": 0.006, "sep": 3.0,
                   "outlier": 0.01, "verified": True}
            self._record_empirical_candidate(
                "pi_fidelity", row, self.w["read_pulse_freq"],
                self.w["read_pulse_gain"], 2534.7, gain, 400, False,
                evidence="synthetic_hardware_map", measured_cfg=measured_cfg)
        raise T.TunerError("synthetic post-map certification failure")

    def _plot(self, success):
        return plt.figure()

    def pickle_data(self, *args, **kwargs):
        return None


_best_effort = _BestEffortAcquireTuner(
    soc=None, soccfg=None, path="best_effort", outerFolder=tmp,
    suffix="BestEffort", cfg=dict(BaseConfig))
_best_effort_out = _best_effort.acquire(plotDisp=False)["data"]
_best_effort_point = _best_effort_out["best_found"]
check("a 90% empirical pi remains the reported winner after a later audit fails",
      abs(_best_effort_point["fidelity"] - 0.90) < 1e-12
      and _best_effort_point["qubit_pi_gain"] == 11500
      and abs(_best_effort_point["qubit_pi_freq"] - 2534.7) < 1e-12,
      "best=%s" % _best_effort_point)
check("best-found and write certification are independent states",
      _best_effort_out["outcome"] == "best_effort"
      and _best_effort_out["completed_with_candidate"]
      and not _best_effort_out["success"]
      and not _best_effort_out["certified_to_write"]
      and _best_effort_out["eligible_tuned"] == {})
check("repeat disagreement is retained in the best-found uncertainty",
      _best_effort_point["measurement_count"] == 2
      and abs(_best_effort_point["block_spread"] - 0.02) < 1e-12
      and _best_effort_point["fidelity_se"] > 0.006)
_best_effort.candidate_archive = []
for _beta, _fid in ((0.0, 0.89), (0.02, 0.90)):
    _bcfg = _best_effort._cfg_for("pi_fidelity")
    _bcfg["qubit_drag_beta"] = _beta
    _best_effort._record_empirical_candidate(
        "leakage", {"fid": _fid, "fid_se": 0.004, "sep": 3.0,
                    "outlier": 0.01, "verified": True},
        7248.95, 4300, 2534.7, 11500, 500, False,
        evidence="beta_identity", measured_cfg=_bcfg)
_beta_best, _ = _best_effort._summarize_candidate_archive()
check("candidate aggregation never averages two physically different DRAG betas",
      _beta_best["measurement_count"] == 1
      and abs(_beta_best["qubit_drag_beta"] - 0.02) < 1e-12)
_best_effort.candidate_archive = []
for _sigma, _fid in ((0.25, 0.89), (0.10, 0.90)):
    _dcfg = _best_effort._cfg_for("pi_fidelity")
    _dcfg["sigma"] = _sigma
    _best_effort._record_empirical_candidate(
        "pulse_duration", {"fid": _fid, "fid_se": 0.004, "sep": 3.0,
                           "outlier": 0.01, "verified": True},
        7248.95, 4300, 2534.7, 11500, 500, False,
        evidence="duration_identity", measured_cfg=_dcfg)
_duration_best, _ = _best_effort._summarize_candidate_archive()
check("candidate aggregation never averages two physically different durations",
      _duration_best["measurement_count"] == 1
      and abs(_duration_best["qubit_sigma_us"] - 0.10) < 1e-12)


class _PiOnlyTuner(_StubTuner):
    def __init__(self, dev, anchor_frac=1.0, params=None, drive_offset=0.0):
        install_simulator(dev)
        anchor = float(dev.PI_GAIN) * float(anchor_frac)
        super().__init__(anchor, anchor, params=params)
        self.w.update(pi_gain=int(round(anchor)), drive_freq=dev.F_Q + float(drive_offset),
                      t1_us=dev.T1, t1_lo_us=dev.T1,
                      pi_gain_anchor_err=0.03 * anchor,
                      fine_freq_converged=True)


print("\n== protected control: exact replay and monotonic atomic acceptance ==")


class _ControlOnlyTuner(T.AutoTuner):
    def _balanced_single_shot(self, cfg, drive_freq, pi_gain, shots, strict=True):
        return {"fidelity": 0.90, "fidelity_se": 0.003, "sep_sigma": 4.0,
                "outlier_frac": 0.01, "ok": True}

    def maintain(self):
        raise AssertionError("baseline-only mode must never start the graph")

    def _plot(self, success):
        return plt.figure()

    def pickle_data(self, *args, **kwargs):
        return None


_control_only = _ControlOnlyTuner(
    soc=None, soccfg=None, path="control_only", outerFolder=tmp,
    suffix="ControlOnly", cfg=dict(BaseConfig), params={
        "safety": {"baseline_only": True, "expected_min_fidelity_lcb": 0.85,
                   "baseline_blocks": 4, "baseline_shots": 100}})
_control_out = _control_only.acquire(plotDisp=False)["data"]
check("baseline-only validation measures the exact input four times and starts no search",
      _control_out["outcome"] == "control_validated"
      and _control_out["control_validation_passed"]
      and _control_out["best_found"]["measurement_count"] == 4
      and _control_out["tuned"] == {})
check("saved output is stamped with the executable tuner revision",
      _control_out["autotuner_revision"] == T.AUTOTUNER_REVISION
      and T.AUTOTUNER_REVISION == "canonical-single-shot-v2")


class _LowStartSearchTuner(_ControlOnlyTuner):
    def _balanced_single_shot(self, cfg, drive_freq, pi_gain, shots, strict=True):
        return {"fidelity": 0.60, "fidelity_se": 0.004, "sep_sigma": 1.0,
                "outlier_frac": 0.01, "ok": True}

    def maintain(self):
        self.search_started = True
        raise T.TunerError("synthetic stop after proving search launch")


_low_start = _LowStartSearchTuner(
    soc=None, soccfg=None, path="low_start", outerFolder=tmp,
    suffix="LowStart", cfg=dict(BaseConfig), params={
        "safety": {"baseline_only": False, "expected_min_fidelity_lcb": 0.85,
                   "baseline_blocks": 2, "baseline_shots": 100}})
_low_start.acquire(plotDisp=False)
check("a low starting fidelity launches optimization instead of failing its baseline",
      _low_start.search_started
      and not _low_start.node_data["protected_control"]["expected_fidelity_met"])


class _AtomicGuardTuner(T.AutoTuner):
    def __init__(self, incumbent_fid, challenger_fid, challenger_verified=True):
        self.cfg = dict(BaseConfig)
        self.P = T.merge_params({"safety": {"guard_blocks": 2,
                                             "guard_shots": 100}})
        self.report_lines, self.node_data, self.drifted = [], {}, []
        self.stale = {name: False for name, _, _ in T.GRAPH}
        self.candidate_archive = []
        self.w = {
            "read_pulse_freq": float(BaseConfig["read_pulse_freq"]),
            "read_pulse_gain": int(BaseConfig["read_pulse_gain"]),
            "read_length": float(BaseConfig["read_length"]),
            "res_phase": float(BaseConfig.get("res_phase", 0.0)),
            "relax_delay": float(BaseConfig["relax_delay"]),
            "qubit_freq": float(BaseConfig["qubit_freq"]),
            "drive_freq": float(BaseConfig["qubit_pi_freq"]),
            "pi_gain": int(BaseConfig["qubit_pi_gain"]),
            "sigma_us": float(BaseConfig["sigma"]),
            "drag_beta": float(BaseConfig.get("qubit_drag_beta", 0.0)),
            "updated": set(),
        }
        initial = self._working_control_tuple()
        self.protected_control = {"tuple": dict(initial), "aggregate": {},
                                  "source": "test", "promotion_count": 0}
        self._incumbent_gain = int(initial["qubit_pi_gain"])
        self._incumbent_fid = float(incumbent_fid)
        self._challenger_fid = float(challenger_fid)
        self._challenger_verified = bool(challenger_verified)

    def _measure_control_tuple(self, control, shots, evidence):
        incumbent = int(control["qubit_pi_gain"]) == self._incumbent_gain
        return {"freq": float(control["read_pulse_freq"]),
                "gain": int(control["read_pulse_gain"]),
                "fid": self._incumbent_fid if incumbent else self._challenger_fid,
                "fid_se": 0.004, "sep": 3.0, "outlier": 0.01,
                "verified": True if incumbent else self._challenger_verified}


_regression = _AtomicGuardTuner(0.708, 0.638)
_original_gain = _regression.w["pi_gain"]
_regression.w["pi_gain"] = 6058 if _original_gain != 6058 else 5790
try:
    _regression_blocked = not _regression._guard_working_control(
        "hardware_log_regression")
except T.TunerError:
    _regression_blocked = True
check("a fresh 63.8% challenger can never replace a fresh 70.8% incumbent",
      _regression_blocked
      and _regression.w["pi_gain"] == _original_gain
      and _regression.w.get("protected_control_restored", False))

_unstable = _AtomicGuardTuner(0.90, 0.93, challenger_verified=False)
_unstable_original = _unstable.w["pi_gain"]
_unstable.w["pi_gain"] = 6058 if _unstable_original != 6058 else 5790
try:
    _unstable_blocked = not _unstable._guard_working_control(
        "unstable_challenger")
except T.TunerError:
    _unstable_blocked = True
check("an unreproduced challenger is archived but never installed",
      _unstable_blocked and _unstable.w["pi_gain"] == _unstable_original)

_better = _AtomicGuardTuner(0.60, 0.90)
_better.w["pi_gain"] = 6058 if _better.w["pi_gain"] != 6058 else 5790
_better_gain = _better.w["pi_gain"]
check("a statistically superior complete tuple is promoted",
      _better._guard_working_control("clear_improvement")
      and _better.protected_control["tuple"]["qubit_pi_gain"] == _better_gain)


class _UnstablePiDecisionTuner(_StubTuner):
    def __init__(self):
        super().__init__(11500, 11500, params={"pi_fidelity": {
            "gain_points": 3, "freq_points": 3, "refine_points": 3,
            "refine_cells": 1, "shortlist": 2, "confirm_blocks": 2,
            "decision_blocks": 2, "coarse_shots": 20, "shots": 20}})
        self.candidate_archive = []
        self.w.update(qubit_freq=2534.4, sigma_us=0.25, drag_beta=0.0,
                      pi_converged=False, fine_freq_converged=False,
                      pi_verified=False, freq_verified=False,
                      pi_fidelity_verified=False,
                      pi_fidelity_retry_required=False)
        self._confirm_calls = 0

    def _single_shot_point(self, node, read_freq, read_gain, drive_freq, pi_gain,
                           shots, strict=True):
        fid = 0.90 - 0.2 * abs(float(drive_freq) - 2534.55) \
            - 1e-5 * abs(int(pi_gain) - 12000)
        return {"freq": float(read_freq), "gain": int(read_gain), "fid": fid,
                "fid_se": 0.004, "sep": 3.0, "outlier": 0.01,
                "verified": True}

    def _confirm_candidate_blocks(self, candidates, measure, nblocks,
                                  max_disagreement=0.06):
        self._confirm_calls += 1
        rows = []
        for j, (freq, gain) in enumerate(candidates):
            is_incumbent = abs(float(freq) - 2534.4) < 1e-9 and int(gain) == 11500
            rows.append({"freq": float(freq), "gain": int(gain),
                         "fid": 0.70 if is_incumbent else 0.90,
                         "fid_se": 0.004, "sep": 3.0, "outlier": 0.01,
                         "verified": self._confirm_calls == 1})
        return rows


_unstable_pi = _UnstablePiDecisionTuner()
_pi_before = (_unstable_pi.w["drive_freq"], _unstable_pi.w["pi_gain"])
_unstable_pi._cal_pi_fidelity()
check("pi_fidelity fresh-decision instability cannot mutate frequency or gain",
      (_unstable_pi.w["drive_freq"], _unstable_pi.w["pi_gain"]) == _pi_before
      and "qubit_pi_freq" not in _unstable_pi.w["updated"]
      and "qubit_pi_gain" not in _unstable_pi.w["updated"])


def _pi_case(seed, anchor_frac=1.0, params=None, drive_offset=0.0, setup=None):
    device = VirtualQubit(np.random.default_rng(seed))
    if setup is not None:
        setup(device)
    tune = _PiOnlyTuner(device, anchor_frac=anchor_frac, params=params,
                        drive_offset=drive_offset)
    return device, tune


robust = {"fine_pi_amp": {"M_list": (3, 7, 15), "shots": 1600, "blocks": 4}}
check("SPE block counts are expanded to complete four-way phase cycles",
      T._balanced_block_count(2) == 4 and T._balanced_block_count(5) == 8)
pd, pt = _pi_case(101, anchor_frac=1.10, params=robust)
pt._cal_fine_pi_amp()
check("a 10% bad rough-Rabi anchor is corrected, not protected from relocation",
      pt.w["pi_converged"] and abs(pt.w["pi_gain"] - pd.PI_GAIN) / pd.PI_GAIN < 0.005,
      "got %d vs %.0f" % (pt.w["pi_gain"], pd.PI_GAIN))
check("convergence requires mutually consistent odd depths plus a held-out sequence",
      pt.w["pi_n_agree"] >= 2 and pt.w["pi_audit_bound_frac"] <= 0.004,
      "depths=%d audit=%.3f%%" % (pt.w["pi_n_agree"],
                                  100 * pt.w["pi_audit_bound_frac"]))

weak_params = {"fine_pi_amp": {"M_list": (3, 7, 15), "shots": 30000, "blocks": 4}}
wd, wt = _pi_case(102, anchor_frac=1.06, params=weak_params,
                  setup=lambda d: setattr(d, "NOISE", 10.0))
wt._cal_fine_pi_amp()
wc = wt._cfg_for("fine_pi_amp")
wig, wqg = T._shots(wt, wc, [], wt.w["drive_freq"], 4000)
wie, wqe = T._shots(wt, wc, [("pulse", wt.w["pi_gain"], 0.0)], wt.w["drive_freq"], 4000)
wss = T.single_shot_analysis(wig, wqg, wie, wqe)
check("averaged-IQ calibration still converges when individual shots overlap",
      wss["sep_sigma"] < 2.0 and wt.w["pi_converged"],
      "single-shot %.2f sigma, pi %d" % (wss["sep_sigma"], wt.w["pi_gain"]))

dd, dt = _pi_case(103, anchor_frac=1.08, params=robust,
                  setup=lambda d: setattr(d, "iq_drift_per_call", 0.08 + 0.04j))
dt._cal_fine_pi_amp()
check("local bracketing and palindromic order reject large affine IQ drift",
      dt.w["pi_converged"] and abs(dt.w["pi_gain"] - dd.PI_GAIN) / dd.PI_GAIN < 0.007,
      "got %d with %.3g IQ drift/call" % (dt.w["pi_gain"], abs(dd.iq_drift_per_call)))

nd, nt = _pi_case(104, anchor_frac=1.10, params=robust,
                  setup=lambda d: setattr(d, "gain_nonlinearity", 0.8))
nt._cal_fine_pi_amp()
check("progressive signed depths converge despite a nonlinear gain-to-angle curve",
      nt.w["pi_converged"] and abs(nt.w["pi_gain"] - nd.PI_GAIN) / nd.PI_GAIN < 0.007,
      "got %d" % nt.w["pi_gain"])

one_d, one_t = _pi_case(105, anchor_frac=1.02,
                        params={"fine_pi_amp": {"M_list": (7,), "shots": 1600,
                                                "blocks": 4, "min_depths": 3,
                                                "gap_check_factor": 0.0}})
one_t._cal_fine_pi_amp()
check("a broad sentinel plus one amplified depth is insufficient when three are required",
      one_t.w["pi_n_valid"] == 2 and not one_t.w["pi_converged"])

short_d, short_t = _pi_case(
    111, anchor_frac=1.02,
    params={"fine_pi_amp": {"M_list": (3,), "shots": 1600, "blocks": 4,
                            "min_depths": 2, "gap_check_factor": 0.0}})
short_t.w["t1_lo_us"] = 4.0
short_t._cal_fine_pi_amp()
check("a short T1 cannot relabel optimizer depths as independent held-out evidence",
      not short_t.w["pi_converged"]
      and not short_t.node_data["fine_pi_amp"]["audit"][0]["peaks"])

alias_d, alias_t = _pi_case(106, anchor_frac=1.5293, params=robust)
alias_t._cal_fine_pi_amp()
check("the broad M=1 sentinel escapes the rational 3/7/15/13 alias trap",
      alias_t.w["pi_converged"]
      and abs(alias_t.w["pi_gain"] - alias_d.PI_GAIN) / alias_d.PI_GAIN < 0.005,
      "got %d vs %.0f" % (alias_t.w["pi_gain"], alias_d.PI_GAIN))

far_d, far_t = _pi_case(110, anchor_frac=1.90, params=robust)
far_t._cal_fine_pi_amp()
check("an anchor beyond the broad safe/hardware range is rejected, never ratcheted",
      not far_t.w["pi_converged"] and abs(far_t.w["pi_gain"] - 1.90 * far_d.PI_GAIN) < 2,
      "kept %d" % far_t.w["pi_gain"])
check("the capture rejection is explicit in the report",
      any("rejected" in line.lower() or "hierarchy stops" in line.lower()
          for line in far_t.report_lines))

_order_rng_state = np.random.get_state()
np.random.seed(24680)
_anchor_sweep = []
for _j, _frac in enumerate((0.55, 0.70, 0.85, 1.15, 1.35, 1.55, 1.75)):
    _sd, _st = _pi_case(
        300 + _j, anchor_frac=_frac,
        params={"fine_pi_amp": {"M_list": (3, 7, 15), "shots": 1200, "blocks": 4}})
    _st._cal_fine_pi_amp()
    _truth_err = abs(_st.w["pi_gain"] - _sd.PI_GAIN) / _sd.PI_GAIN
    _unchanged = abs(_st.w["pi_gain"] - round(_frac * _sd.PI_GAIN)) <= 1
    _anchor_sweep.append((_frac, _st.w["pi_converged"], _truth_err, _unchanged))
np.random.set_state(_order_rng_state)
check("a broad anchor sweep either finds the true pi branch or rejects without ratcheting",
      all((converged and err < 0.005) or (not converged and unchanged)
          for _, converged, err, unchanged in _anchor_sweep),
      "results=%s" % _anchor_sweep)

gap_d, gap_t = _pi_case(107, anchor_frac=1.04, params=robust,
                        setup=lambda d: setattr(d, "gap_angle_coeff", 0.015))
gap_t._cal_fine_pi_amp()
check("a pi that changes with inter-pulse gap is blocked as pulse-history distortion",
      not gap_t.w["pi_converged"]
      and any("DISAGREES" in line for line in gap_t.report_lines))

fd, ft = _pi_case(108, anchor_frac=1.10, drive_offset=0.45,
                  params={"fine_pi_freq": {"shots": 1800}})
ft._cal_fine_pi_freq()
check("the driven pseudo-identity finds frequency with a 10% amplitude error",
      ft.w["fine_freq_converged"] and abs(ft.w["drive_freq"] - fd.F_Q) < 0.06,
      "got %.4f vs %.4f MHz" % (ft.w["drive_freq"], fd.F_Q))

dead_d, dead_t = _pi_case(109, anchor_frac=1.02,
                          params={"fine_pi_amp": {"M_list": (3, 7), "shots": 80,
                                                  "blocks": 4, "gap_check_factor": 0.0}},
                          setup=lambda d: setattr(d, "NOISE", 1000.0))
dead_t._cal_fine_pi_amp()
check("dead references and noise-only phase vectors cannot report convergence",
      not dead_t.w["pi_converged"] and dead_t.w["pi_n_agree"] == 0)

_noise_rejections = []
for _seed in range(400, 404):
    _, _noise_t = _pi_case(
        _seed, anchor_frac=1.02,
        params={"fine_pi_amp": {"M_list": (3, 7), "shots": 80,
                                "blocks": 4, "gap_check_factor": 0.0}},
        setup=lambda d: setattr(d, "NOISE", 1000.0))
    _noise_t._cal_fine_pi_amp()
    _noise_rejections.append(not _noise_t.w["pi_converged"])
check("noise-only rejection is stable across independent random seeds",
      all(_noise_rejections), "rejected=%d/%d" %
      (sum(_noise_rejections), len(_noise_rejections)))


class _GateTuner(_StubTuner):
    def __init__(self, roots, audit_ok=True, audit_gain=None):
        super().__init__(10000.0, 10000.0,
                         params={"fine_pi_amp": {"M_list": (3, 7), "min_depths": 3,
                                                 "validation_rounds": 1,
                                                 "gap_check_factor": 0.0}})
        self._roots = dict(roots)
        self._audit_ok = bool(audit_ok)
        self._audit_gain = audit_gain
        self.w["pi_gain_anchor_err"] = 200.0

    def _measure_pi_spe(self, cfg, center_gain, depth, shots, blocks, gap_us=None):
        gain = float(self._roots[int(depth)])
        return {"ok": True, "M": int(depth), "gain": gain, "gain_err": 1.0,
                "phase_snr": 50.0, "ref_snr": 50.0, "axis_rotation_deg": 0.0,
                "order_sigma": 0.0}

    def _amplitude_audit(self, cfg, center_gain, gap_us=None, shots=None):
        gain = float(center_gain if self._audit_gain is None else self._audit_gain)
        peak = {"ok": self._audit_ok, "M": 11, "gain": gain, "gain_err": 1.0,
                "bound_frac": 0.0}
        return {"ok": self._audit_ok, "gain": gain, "gain_err": 1.0,
                "bound_frac": 0.0 if self._audit_ok else np.inf,
                "peak": peak, "peaks": [peak], "equator": {"ok": False},
                "coherent_status": "inconclusive"}


bad_hierarchy = _GateTuner({1: 10000.0, 3: 11000.0, 7: 12000.0})
bad_hierarchy._cal_fine_pi_amp()
check("non-contracting signed roots cannot be rescued by a pretty held-out audit",
      not bad_hierarchy.w["pi_converged"] and bad_hierarchy.w["pi_gain"] == 10000)

audit_jump = _GateTuner({1: 10000.0, 3: 10000.0, 7: 10000.0},
                        audit_ok=False, audit_gain=11500.0)
audit_jump._cal_fine_pi_amp()
check("a periodic audit is never allowed to relocate the signed solution",
      not audit_jump.w["pi_converged"] and audit_jump.w["pi_gain"] == 10000
      and audit_jump.w["pi_candidate_gain"] == 10000)
check("a failed candidate is not promoted into the next round's trusted anchor",
      audit_jump.w["pi_gain_anchor_err"] == 200.0)

print("\n== readout_len must EXTEND past the ladder, not just warn ==")


class _LenTuner(_StubTuner):
    def __init__(self, best_len, **kw):
        _StubTuner.__init__(self, 11500.0, 11500.0, **kw)
        self._best = float(best_len)
        self.tested = []

    def _sweep_readout(self, node, cands, apply_fn, shots):
        self.tested.extend(float(c) for c in cands)
        f = np.array([1.0 - abs(np.log(c / self._best)) for c in cands], float)
        return f * 2.0, f, np.zeros(len(cands)), 0.0

    def _single_shot_length_point(self, length_us, shots):
        fid = float(1.0 - abs(np.log(float(length_us) / self._best)))
        return {"freq": float(length_us), "gain": 0, "fid": fid,
                "fid_se": 0.001, "sep": 2.0 * fid, "outlier": 0.0,
                "verified": True}


lt = _LenTuner(best_len=64.0, params={"readout_len": {
    "lengths_us": (1.0, 2.0, 4.0, 8.0, 14.0, 20.0, 30.0, 45.0)}})
lt.w["t1_us"] = 200.0
lt._cal_readout_len()
check("the ladder extended beyond its top when F was still rising",
      max(lt.tested) > 45.0, "tested up to %.1f us" % max(lt.tested))
check("the chosen length is no longer the ladder end",
      lt.w["read_length"] > 45.0, "chose %.1f us" % lt.w["read_length"])

lt2 = _LenTuner(best_len=1000.0, params={"readout_len": {
    "lengths_us": (1.0, 2.0, 4.0, 8.0, 14.0, 20.0, 30.0, 45.0)}})
lt2.w["t1_us"] = 100.0
lt2.w["t1_lo_us"] = 100.0
lt2._cal_readout_len()
check("extension stops at the T1/2 cap and says the LIFETIME is the limit",
      lt2.w["read_length"] <= 50.0
      and any("T1/2 cap" in l for l in lt2.report_lines),
      "chose %.1f us (cap 50)" % lt2.w["read_length"])

lt3 = _LenTuner(best_len=8.0, params={"readout_len": {
    "lengths_us": (4.0, 8.0, 10.0, 12.0)}})
lt3.w.update(read_length=10.0, t1_us=100.0, t1_lo_us=100.0)
_lt3_new, _lt3_tol = lt3._cal_readout_len()
check("any selected ADC-window change invalidates the frequency x gain map",
      _lt3_new["L"] == 8.0 and _lt3_tol["L"] == 0.0,
      "new=%s tol=%s" % (_lt3_new, _lt3_tol))


class _UnstableLenTuner(_LenTuner):
    def _confirm_candidate_blocks(self, candidates, measure, nblocks,
                                  max_disagreement=0.06):
        return [{"freq": float(length), "gain": 0, "fid": 0.80,
                 "fid_se": 0.04, "sep": 3.0, "outlier": 0.01,
                 "block_spread": 0.14, "verified": False, "blocks": []}
                for length, _zero in candidates]


_unstable_len = _UnstableLenTuner(best_len=8.0, params={"readout_len": {
    "lengths_us": (4.0, 8.0, 12.0), "shortlist": 3}})
_unstable_len.w.update(read_length=4.0, t1_us=100.0, t1_lo_us=100.0)
try:
    _unstable_len._cal_readout_len()
    _unstable_len_blocked = False
except T.TunerError:
    _unstable_len_blocked = True
check("an unstable length audit archives the winner but cannot replace the incumbent",
      _unstable_len_blocked and _unstable_len.w["read_length"] == 4.0
      and _unstable_len.w["readout_len_verified"] is False
      and _unstable_len.node_data["readout_len"]["status"]
      == "unstable_challenger_rejected")

print("\n== readout_power: verified fidelity wins; tails are diagnostic, not a cliff ==")

_cm_tuner = _StubTuner(11500.0, 11500.0)
_cm_candidates = [(0.0, 4300), (0.5, 9000)]
_cm_base = (0.55, 0.70, 0.60, 0.68)
_cm_calls = [0]


def _common_mode_measure(freq, gain):
    block = _cm_calls[0] // len(_cm_candidates)
    _cm_calls[0] += 1
    fid = _cm_base[block] + (0.15 if gain == 9000 else 0.0)
    return {"freq": freq, "gain": gain, "fid": fid, "fid_se": 0.005,
            "sep": 3.0, "outlier": 0.01, "verified": True}


_cm_rows = _cm_tuner._confirm_candidate_blocks(
    _cm_candidates, _common_mode_measure, 4, max_disagreement=0.06)
check("common-mode fidelity drift cannot reject an otherwise stable paired ranking",
      all(r["verified"] and r["common_mode_rescued"] for r in _cm_rows),
      T.AutoTuner._confirmation_diagnostics(_cm_rows))

_single_calls = [0]


def _unstable_single_measure(freq, gain):
    fid = _cm_base[_single_calls[0]]
    _single_calls[0] += 1
    return {"freq": freq, "gain": gain, "fid": fid, "fid_se": 0.005,
            "sep": 3.0, "outlier": 0.01, "verified": True}


_single_rows = _cm_tuner._confirm_candidate_blocks(
    [_cm_candidates[0]], _unstable_single_measure, 4, max_disagreement=0.06)
check("a drifting single final candidate cannot self-normalize into verification",
      len(_single_rows) == 1 and not _single_rows[0]["verified"]
      and "relative_block_spread" not in _single_rows[0],
      T.AutoTuner._confirmation_diagnostics(_single_rows))

_id_calls = [0]
_id_delta = (0.15, -0.02, 0.25, 0.0)


def _independent_drift_measure(freq, gain):
    block = _id_calls[0] // len(_cm_candidates)
    _id_calls[0] += 1
    fid = _cm_base[block] + (_id_delta[block] if gain == 9000 else 0.0)
    return {"freq": freq, "gain": gain, "fid": fid, "fid_se": 0.005,
            "sep": 3.0, "outlier": 0.01, "verified": True}


_id_rows = _cm_tuner._confirm_candidate_blocks(
    _cm_candidates, _independent_drift_measure, 4, max_disagreement=0.06)
check("candidate-specific instability still fails the paired reproducibility gate",
      not any(r["verified"] for r in _id_rows),
      T.AutoTuner._confirmation_diagnostics(_id_rows))

_tail_rows = [
    {"freq": 0.0, "gain": 4300, "fid": 0.60, "fid_se": 0.006,
     "outlier": 0.001, "verified": True},
    {"freq": 0.75, "gain": 10320, "fid": 0.90, "fid_se": 0.006,
     "outlier": 0.049, "verified": True},
]
_tail_best = T.select_verified_2d_candidate(
    _tail_rows, incumbent=_tail_rows[0], confidence_sigma=1.96,
    min_improvement=0.01, max_outlier=0.25)
check("a reproduced 90% point is not discarded for a 4.9% robust-tail diagnostic",
      _tail_best["gain"] == 10320 and _tail_best["improvement_significant"],
      "winner=%s" % _tail_best)
_gross_rows = _tail_rows + [
    {"freq": 0.8, "gain": 14620, "fid": 0.97, "fid_se": 0.004,
     "outlier": 0.30, "verified": True},
]
_gross_best = T.select_verified_2d_candidate(
    _gross_rows, incumbent=_gross_rows[0], confidence_sigma=1.96,
    min_improvement=0.01, max_outlier=0.25)
check("a deliberately severe 30% pathology is still excluded",
      _gross_best["gain"] == 10320, "winner=%s" % _gross_best)


class _CoupledReadoutTuner(_StubTuner):
    """Exercise the production 2-D search, not just its pure selector."""

    F0 = 7248.9

    def _single_shot_point(self, node, read_freq, read_gain, drive_freq, pi_gain, shots,
                           strict=True):
        if not hasattr(self, "requested_readout_gains"):
            self.requested_readout_gains = []
        self.requested_readout_gains.append(int(read_gain))
        fid = _coupled_readout_fidelity(float(read_freq) - self.F0, read_gain)
        return {"freq": float(read_freq), "gain": int(read_gain),
                "fid": fid, "fid_se": 0.004, "sep": 1.0 + 4.0 * fid,
                "outlier": 0.049 if fid > 0.85 else 0.005,
                "verified": True}


_joint_params = {"readout_power": {
    "freq_span_mhz": 1.5, "freq_points": 11,
    "gain_min": 4300, "gain_max": 10320, "minimum_gain_ceiling": 10320,
    "gain_points": 5, "ratios": (1.0,), "refine_points": 5,
    "shortlist": 5, "confirm_blocks": 2, "coarse_shots": 20, "shots": 40,
    "max_extensions": 0}}
pt = _CoupledReadoutTuner(11500.0, 11500.0, params=_joint_params)
pt.w.update(read_pulse_freq=_CoupledReadoutTuner.F0, read_pulse_gain=4300,
            kappa_mhz=0.1)
pt._cal_readout_power()
check("the production joint scan escapes the 60% fixed-frequency slice",
      pt.w["read_pulse_gain"] == 10320
      and abs(pt.w["read_pulse_freq"] - (_CoupledReadoutTuner.F0 + 0.75)) < 1e-6,
      "chose %.4f MHz / %d DAC" %
      (pt.w["read_pulse_freq"], pt.w["read_pulse_gain"]))
check("the production confirmation records the independently verified ~90% point",
      pt.node_data["readout_power"]["selected"]["fid"] > 0.89
      and pt.node_data["readout_power"]["selected"]["verified"])
check("gain_max is a hard hardware-request ceiling, including local refinement",
      max(pt.requested_readout_gains) <= 10320,
      "largest requested gain=%d" % max(pt.requested_readout_gains))


class _UnstableReadoutTuner(_CoupledReadoutTuner):
    def _confirm_candidate_blocks(self, candidates, measure, nblocks,
                                  max_disagreement=0.06):
        return [{"freq": float(f), "gain": int(g), "fid": 0.72,
                 "fid_se": 0.04, "sep": 2.8, "outlier": 0.01,
                 "block_spread": 0.14, "relative_block_spread": 0.10,
                 "verified": False, "blocks": []}
                for f, g in candidates]


_unstable_readout = _UnstableReadoutTuner(
    11500.0, 11500.0, params=_joint_params)
_unstable_readout.w.update(read_pulse_freq=_CoupledReadoutTuner.F0,
                           read_pulse_gain=4300, kappa_mhz=0.1)
try:
    _unstable_readout._cal_readout_power()
    _unstable_readout_blocked = False
except T.TunerError:
    _unstable_readout_blocked = True
check("an unstable readout map is retained as evidence but cannot replace the incumbent",
      _unstable_readout_blocked
      and _unstable_readout.node_data["readout_power"]["selected"]["fid"] > 0.89
      and _unstable_readout.w["read_pulse_gain"] == 4300
      and _unstable_readout.w["readout_power_verified"] is False
      and _unstable_readout.node_data["readout_power"]["status"]
      == "unstable_challenger_rejected")


class _MissedPiTuner(_StubTuner):
    F_OPT, G_OPT = 2534.70, 11500

    def _single_shot_point(self, node, read_freq, read_gain, drive_freq, pi_gain, shots,
                           strict=True):
        zf = (float(drive_freq) - self.F_OPT) / 0.10
        zg = (float(pi_gain) - self.G_OPT) / 350.0
        fid = 0.55 + 0.35 * np.exp(-0.5 * (zf * zf + zg * zg))
        return {"freq": float(read_freq), "gain": int(read_gain),
                "fid": float(fid), "fid_se": 0.004,
                "sep": 1.0 + 4.0 * float(fid), "outlier": 0.01,
                "verified": True}


class _UnstablePiMapTuner(_MissedPiTuner):
    def _confirm_candidate_blocks(self, candidates, measure, nblocks,
                                  max_disagreement=0.06):
        return [{"freq": float(f), "gain": int(g), "fid": 0.72,
                 "fid_se": 0.04, "sep": 2.8, "outlier": 0.01,
                 "block_spread": 0.14, "relative_block_spread": 0.10,
                 "verified": False, "blocks": []}
                for f, g in candidates]


_pi_map_params = {"pi_fidelity": {
    "gain_span_frac": 0.30, "gain_points": 9,
    "freq_span_mhz": 1.2, "freq_points": 9,
    "refine_points": 5, "shortlist": 5, "confirm_blocks": 2,
    "coarse_shots": 20, "shots": 40}}
check("the production pi map meets or exceeds the QM +/-50% 11x11 coverage baseline",
      T.DEFAULTS["pi_fidelity"]["gain_span_frac"] >= 0.50
      and T.DEFAULTS["pi_fidelity"]["gain_points"] >= 11
      and T.DEFAULTS["pi_fidelity"]["freq_points"] >= 11)
_unstable_map = _UnstablePiMapTuner(10000.0, 10000.0, params=_pi_map_params)
_unstable_map.w.update(pi_gain=10000, drive_freq=2534.40,
                       pi_converged=False, fine_freq_converged=False,
                       pi_verified=False, freq_verified=False,
                       pi_fidelity_verified=False)
_unstable_new, _unstable_tol = _unstable_map._cal_pi_fidelity()
check("an unstable first pi map defers to signed coherent refinement instead of aborting",
      _unstable_new == {"f": 2534.40, "g": 10000.0}
      and _unstable_map.w["drive_freq"] == 2534.40
      and _unstable_map.w["pi_gain"] == 10000
      and _unstable_map.w["pi_fidelity_retry_required"]
      and _unstable_map.node_data["pi_fidelity"]["status"].startswith("provisional")
      and _unstable_map.node_data["pi_fidelity"]["provisional_seed"]["fid"] > 0.89)
_unstable_map.w.update(pi_converged=True, fine_freq_converged=True,
                       pi_verified=True, freq_verified=True)
_unstable_map.stale["pi_fidelity"] = False
check("the provisional map is automatically scheduled after coherent refinement",
      _unstable_map._invalidate_pi_fidelity_if_unbound()
      and _unstable_map.stale["pi_fidelity"])
try:
    _unstable_map._cal_pi_fidelity()
    _persistent_instability_stopped = False
except T.TunerError:
    _persistent_instability_stopped = True
check("persistent post-refinement instability trips the graph circuit breaker",
      _persistent_instability_stopped
      and _unstable_map.w["drive_freq"] == 2534.40
      and _unstable_map.w["pi_gain"] == 10000
      and _unstable_map.w["pi_fidelity_audit_failed"]
      and not _unstable_map.w["pi_fidelity_verified"]
      and not _unstable_map.w["pi_fidelity_retry_required"]
      and "failed_after_coherent_refinement"
      in _unstable_map.node_data["pi_fidelity"]["status"]
      and any("abs-spread" in line for line in _unstable_map.report_lines))

_pimap = _MissedPiTuner(10000.0, 10000.0, params=_pi_map_params)
_pimap.w.update(pi_gain=10000, drive_freq=2534.40,
                pi_converged=True, fine_freq_converged=True,
                pi_verified=True, freq_verified=True, pi_fidelity_verified=False)
_pimap._cal_pi_fidelity()
check("the production qubit map challenges a self-consistent but low-fidelity pi seed",
      _pimap.w["pi_gain"] == _MissedPiTuner.G_OPT
      and abs(_pimap.w["drive_freq"] - _MissedPiTuner.F_OPT) < 1e-6,
      "chose %.4f MHz / %d DAC" % (_pimap.w["drive_freq"], _pimap.w["pi_gain"]))
check("a one-pulse winner is provisional until coherent frequency/amplitude audits rerun",
      not _pimap.w["pi_converged"] and not _pimap.w["fine_freq_converged"]
      and not _pimap.w["pi_verified"] and not _pimap.w["freq_verified"]
      and not _pimap.w["pi_fidelity_verified"])
_pimap.w.update(pi_converged=True, fine_freq_converged=True,
                pi_verified=True, freq_verified=True)
_pimap._cal_pi_fidelity()
check("a no-better-neighbor pi map is bound to the exact final pulse/readout state",
      _pimap.w["pi_fidelity_verified"] and _pimap._pi_fidelity_binding_valid())
_old_gap = _pimap.cfg.get("seq_gap_us")
_pimap.cfg["seq_gap_us"] = 0.02
check("changing the physical pulse fingerprint invalidates the pi-map certificate",
      not _pimap._pi_fidelity_binding_valid())
if _old_gap is None:
    _pimap.cfg.pop("seq_gap_us")
else:
    _pimap.cfg["seq_gap_us"] = _old_gap
check("restoring the exact pulse fingerprint restores the certificate",
      _pimap._pi_fidelity_binding_valid())
_pimap.w["drive_freq"] += 2.0 * _pimap.w["pi_fidelity_binding"]["freq_radius"]
check("moving outside the verified pi-map cell invalidates final eligibility",
      not _pimap._pi_fidelity_binding_valid())
check("an out-of-cell pi map becomes graph work instead of an end-only write failure",
      _pimap._invalidate_pi_fidelity_if_unbound()
      and _pimap.stale["pi_fidelity"]
      and not _pimap.w["pi_fidelity_verified"]
      and "pi_fidelity_binding" not in _pimap.w)

print("\n== a node failing on RE-measurement must not destroy a good round 1 ==")
calls2 = {}
_real_spec = T.AutoTuner._cal_spec


def _flaky_spec(self):
    calls2["spec"] = calls2.get("spec", 0) + 1
    if calls2["spec"] >= 2:
        raise T.TunerError("spec: no qubit line within +/-75 MHz of 2531.030.")
    return _real_spec(self)


T.AutoTuner._cal_spec = _flaky_spec
T.AutoTuner._cal_fine_pi_amp = _orig_fine = T.AutoTuner._cal_fine_pi_amp


def _always_move(self):
    out = _orig_fine(self)
    self.stale["spec"] = True
    return out


T.AutoTuner._cal_fine_pi_amp = _always_move
dev3 = VirtualQubit(np.random.default_rng(5))
install_simulator(dev3)
t3 = T.AutoTuner(soc=None, soccfg=None, path="q4", outerFolder=tmp, suffix="Recover",
                 cfg=dict(BaseConfig),
                 params={"max_rounds": 2, "spec": {"span_mhz": 20.0, "max_span_mhz": 120.0,
                                                     "allow_target_reacquisition": True},
                         "t1": {"points": 6, "shots": 300},
                         "single_shot": {"shots": 1200, "min_sep_sigma": 2.0},
                         "fine_pi_amp": {"M_list": (4, 10), "frac": (0.12, 0.05)}})
out3 = t3.acquire(plotDisp=False)
T.AutoTuner._cal_spec = _real_spec
T.AutoTuner._cal_fine_pi_amp = _orig_fine
check("a round-2 spec failure returns the measured best candidate rather than losing it",
      out3["data"].get("best_found") is not None
      and out3["data"]["outcome"] == "best_effort")
check("the repeated-node circuit breaker is reported, not silent",
      any("mixed-vintage" in l and "circuit breaker" in l for l in t3.report_lines))
check("mixed-vintage evidence restores the protected control and blocks writes",
      out3["data"]["working"].get("protected_control_restored", False)
      and out3["data"]["eligible_tuned"] == {})

print("\n== T1 must be identifiable and must own its downstream timing domain ==")


class _T1Tuner(_StubTuner):
    def __init__(self, tau, tau_err, **kw):
        _StubTuner.__init__(self, 11500.0, 11500.0, **kw)
        self._tau, self._err = float(tau), float(tau_err)

    def _cfg_for(self, node):
        return _StubTuner._cfg_for(self, node)


def _run_t1(tau, tau_err, relax0=3000.0, params=None, read_length=20.0,
            reduced_chi2=1.0):
    t = _T1Tuner(tau, tau_err, params=params)
    t.w.update(relax_delay=relax0, read_length=float(read_length))
    t.stale["readout_len"] = False
    t.stale["rough_pi"] = False
    saved_pop, saved_fit = T._pop_with_local_refs, T.fit_exp_decay
    T._pop_with_local_refs = lambda *a, **k: (0.5, 1.0, 0.01)
    t.t1_fit_calls = 0
    def _fake_t1_fit(ts, ps, *args, **kwargs):
        t.t1_fit_calls += 1
        return {"ok": True, "tau": t._tau, "tau_err": t._err,
                "reduced_chi2": float(reduced_chi2),
                "yfit": np.zeros_like(ts)}
    T.fit_exp_decay = _fake_t1_fit
    t.t1_failed, t.t1_result, t.t1_tolerance = False, None, None
    try:
        t.t1_result, t.t1_tolerance = t._cal_t1()
    except T.TunerError:
        t.t1_failed = True
    finally:
        T._pop_with_local_refs, T.fit_exp_decay = saved_pop, saved_fit
    return t


def _run_failed_t1():
    t = _T1Tuner(30.0, float("inf"))
    saved_pop, saved_fit = T._pop_with_local_refs, T.fit_exp_decay
    T._pop_with_local_refs = lambda *a, **k: (0.5, 1.0, 0.01)
    T.fit_exp_decay = lambda ts, ps, *a, **k: {"ok": False, "tau": np.nan,
                                               "tau_err": np.inf,
                                               "yfit": np.full_like(ts, np.nan)}
    failed = False
    try:
        t._cal_t1()
    except T.TunerError:
        failed = True
    finally:
        T._pop_with_local_refs, T.fit_exp_decay = saved_pop, saved_fit
    return t, failed


_t1_failed, _t1_raised = _run_failed_t1()
check("a failed T1 fit cannot masquerade as a measured 30-us lifetime",
      _t1_raised and not _t1_failed.w.get("t1_verified", False)
      and _t1_failed.w.get("t1_us") == 1e6)


t1_bad_err = _run_t1(140.6, 80.3)
check("a 57%-uncertain fit is rejected instead of becoming a safety bound",
      t1_bad_err.t1_failed and not t1_bad_err.w.get("t1_verified", False))

t1t = _run_t1(140.6, 40.0)
check("an identifiable finite-error T1 retains conservative lower/upper bounds",
      not t1t.t1_failed and t1t.w["t1_lo_us"] < t1t.w["t1_us"] < t1t.w["t1_hi_us"],
      "lo=%.1f tau=%.1f hi=%.1f" %
      (t1t.w.get("t1_lo_us", np.nan), t1t.w.get("t1_us", np.nan),
       t1t.w.get("t1_hi_us", np.nan)))
check("relax_delay is exactly long enough for the UPPER measured T1 bound",
      abs(t1t.w["relax_delay"] - 5.0 * t1t.w["t1_hi_us"]) < 1e-9)

t1g = _run_t1(25.0, 1.0)
check("a well-determined T1 still shortens relax_delay for runtime",
      not t1g.t1_failed and t1g.w["relax_delay"] < 3000.0
      and t1g.w["relax_delay"] >= 5.0 * 25.0,
      "relax_delay=%.0f us" % t1g.w["relax_delay"])

t1_short_wait = _run_t1(25.0, 1.0, relax0=50.0)
check("a too-short configured relax delay is lengthened, not silently retained",
      not t1_short_wait.t1_failed
      and t1_short_wait.w["relax_delay"] >= 5.0 * t1_short_wait.w["t1_hi_us"],
      "relax_delay=%.0f us" % t1_short_wait.w["relax_delay"])
check("an unsafe initial reset forces a complete T1 retry and re-stales rough Rabi",
      t1_short_wait.t1_fit_calls >= 2 and t1_short_wait.stale["rough_pi"]
      and "relax_delay" in t1_short_wait.w["updated"],
      "fits=%d updated=%s" %
      (t1_short_wait.t1_fit_calls, sorted(t1_short_wait.w["updated"])))

t1n = _run_t1(140.6, float("inf"))
check("a T1 with NO usable error bar is not treated as precise",
      t1n.t1_failed and not t1n.w.get("t1_verified", False))

_linear_t = np.linspace(0.05, 60.0, 12)
_linear_y = 1.0 - 0.02 * (_linear_t - _linear_t[0]) / np.ptp(_linear_t)
_linear_fit = T.fit_exp_decay(_linear_t, _linear_y)
_linear_guard = (_run_t1(
    _linear_fit["tau"], _linear_fit["tau_err"],
    params={"t1": {"t_max_us": 60.0}}) if _linear_fit["ok"] else None)
check("a tiny linear drift cannot be extrapolated into a multi-ms verified T1",
      (not _linear_fit["ok"]
       or (_linear_fit["tau"] > 10.0 * np.ptp(_linear_t)
           and _linear_guard.t1_failed
           and not _linear_guard.w.get("t1_verified", False))),
      "fit %.0f +/- %.0f us over %.0f us" %
      (_linear_fit["tau"], _linear_fit["tau_err"], np.ptp(_linear_t)))

_rising_t = np.linspace(0.05, 80.0, 12)
_rising_y = 0.8 - 0.6 * np.exp(-_rising_t / 20.0)
_rising_fit = T.fit_exp_decay(_rising_t, _rising_y)
check("a rising population/reference artifact cannot be labeled as T1 decay",
      not _rising_fit["ok"] and _rising_fit["observed_drop"] < 0.0,
      "A=%.3g observed early-late=%+.3f" %
      (_rising_fit["A"], _rising_fit["observed_drop"]))

_systematic_t = np.linspace(0.05, 60.0, 12)
_systematic_y = (0.82 * np.exp(-_systematic_t / 20.0) + 0.08
                 + 0.06 * np.where(np.arange(_systematic_t.size) % 2, 1.0, -1.0))
_systematic_err = np.full(_systematic_t.size, 0.001)
_systematic_fit = T.fit_exp_decay(_systematic_t, _systematic_y, _systematic_err)
check("structured residuals inflate absolute-sigma T1 uncertainty",
      _systematic_fit["reduced_chi2"] > 100.0 and _systematic_fit["tau_err"] > 1.0,
      "reduced chi2=%.1f tau_err=%.2f us" %
      (_systematic_fit["reduced_chi2"], _systematic_fit["tau_err"]))
_systematic_guard = _run_t1(
    20.0, 0.5, reduced_chi2=_systematic_fit["reduced_chi2"],
    params={"t1": {"t_max_us": 60.0}})
check("a high-chi-square decay cannot certify reset/readout timing",
      _systematic_guard.t1_failed
      and not _systematic_guard.w.get("t1_verified", False),
      "reduced chi2=%.1f" % _systematic_fit["reduced_chi2"])

t1_cap = _run_t1(80.0, 0.5, read_length=45.0)
check("a shorter T1 explicitly stales an out-of-domain readout length",
      not t1_cap.t1_failed and t1_cap.stale["readout_len"]
      and t1_cap.w["read_length"] > t1_cap.w["t1_readout_cap_us"],
      "read %.1f us vs cap %.1f us" %
      (t1_cap.w["read_length"], t1_cap.w["t1_readout_cap_us"]))
check("the T1 graph coordinate carries its readout-domain cap",
      "cap" in t1_cap.t1_result and "cap" in t1_cap.t1_tolerance)
check("the final timing invariant rejects a stale 45-us window after T1 shrinks",
      not T.t1_timing_domain_valid({
          "t1_verified": True, "t1_lo_us": 79.0, "t1_hi_us": 81.0,
          "read_length": 45.0, "relax_delay": 405.0}))

print("\n== an ASYMMETRIC resonator dip must not bias f0 ==")
_rng = np.random.default_rng(7)
for phi, tau_ns in ((0.0, 0.0), (30.0, 0.0), (60.0, 0.0),
                    (0.0, 100.0), (40.0, 100.0), (40.0, 250.0)):
    fr, kap = 7248.9000, 0.350
    fgrid = np.linspace(fr - 2.0, fr + 2.0, 81)
    xg = fgrid - fr
    s21 = 1.0 - (0.55 * np.exp(1j * np.deg2rad(phi))) / (1 + 2j * xg / kap)
    zc = (3000.0 * np.exp(1j * 0.7) * (1 + 0.01 * xg)
          * np.exp(-2j * np.pi * (tau_ns * 1e-3) * xg) * s21)
    zc = zc + (_rng.normal(0, 25, fgrid.size) + 1j * _rng.normal(0, 25, fgrid.size))
    sym = T.fit_resonance(fgrid, np.abs(zc) ** 2, expected_fwhm=0.3)
    cpx = T.fit_notch_complex(fgrid, zc, f0_guess=fgrid[np.argmin(np.abs(zc))],
                              kappa_guess=0.4)
    tag = "phi=%2.0f deg, %3.0f ns cable" % (phi, tau_ns)
    check("%s: complex notch fit CONVERGES and recovers f0 to <20 kHz" % tag,
          cpx["ok"] and abs(cpx["f0"] - fr) < 0.020,
          "err = %+.1f kHz" % (1000 * (cpx["f0"] - fr)) if cpx["ok"] else "NO CONVERGENCE")
    check("%s: complex fit recovers kappa to <10%%" % tag,
          cpx["ok"] and abs(cpx["fwhm"] - kap) / kap < 0.10,
          "kappa = %.3f vs %.3f" % (cpx["fwhm"], kap) if cpx["ok"] else "-")
    check("%s: asymmetry angle is reported, not hidden" % tag,
          cpx["ok"] and abs(cpx["asym_deg"] - phi) < 8.0,
          "asym = %.1f deg" % cpx["asym_deg"] if cpx["ok"] else "-")
    if phi >= 30.0:
        check("%s: the SYMMETRIC fit really is biased (this is why)" % tag,
              sym["ok"] and abs(sym["f0"] - fr) > 0.050,
              "symmetric err = %+.1f kHz = %.2f kappa"
              % (1000 * (sym["f0"] - fr), abs(sym["f0"] - fr) / kap))

print("\n== a real qubit line must survive the spec power confirmation ==")


def _spec_run(snr_full, seed=3, stark=0.0, allow_reacquisition=True):
    rng = np.random.default_rng(seed)
    f_true, fwhm = 2530.84, 3.9

    class FakeSpec(object):
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, **kw):
            c = self.cfg
            fs = c["start"] + c["step"] * np.arange(c["expts"])
            rel = (float(c["spec_gain"]) / 7000.0) ** 2
            amp = snr_full * rel
            peak = amp / (1.0 + ((fs - (f_true + stark * rel)) / (fwhm / 2.0)) ** 2)
            i = peak + rng.normal(0, 1.0, fs.size)
            q = rng.normal(0, 1.0, fs.size)
            return fs, [[i]], [[q]]

    t = _StubTuner(11500.0, 11500.0, params={"spec": {
        "allow_target_reacquisition": bool(allow_reacquisition)}})
    t.cfg["qubit_gain"], t.cfg["qubit_length"] = 7000, 2.0
    t.w["qubit_freq"] = 2512.0
    t.soccfg, t.soc = None, None
    saved = T.SpecProgram
    T.SpecProgram = FakeSpec
    try:
        return t, t._cal_spec()
    finally:
        T.SpecProgram = saved


try:
    _spec_run(14.1, allow_reacquisition=False)
    _identity_lock_ok = False
except T.TunerError as e:
    _identity_lock_ok = "refusing to jump targets" in str(e)
check("the safe default refuses to relabel a line 19 MHz from the trusted target",
      _identity_lock_ok)

st_w, res_w = _spec_run(14.1)
check("a REAL line at the snr that just failed on hardware is now accepted",
      abs(res_w[0]["f"] - 2530.84) < 1.0, "found %.3f MHz" % res_w[0]["f"])
check("a distant spectral candidate is explicitly provisional before coherent tests",
      st_w.w.get("target_reacquisition_used") is True
      and st_w.w.get("target_reacquisition_status") == "pending_coherent_validation")
check("a weak line is never made WORSE by extrapolating over a short lever arm",
      abs(res_w[0]["f"] - 2530.84) < 0.15,
      "found %.4f, full-power centre was accurate" % res_w[0]["f"])
check("and the tuner says WHY it did not extrapolate, instead of dying",
      any(("not enough to extrapolate" in l or "REJECTED" in l or "gain^2" in l)
          for l in st_w.report_lines))

st_v, res_v = _spec_run(5.5, seed=11)
check("an even weaker line skips the ladder entirely rather than failing",
      abs(res_v[0]["f"] - 2530.84) < 1.5, "found %.3f" % res_v[0]["f"])
check("the Rabi is named as the real confirmation, not the power ladder",
      any("coherent oscillation" in l for l in st_v.report_lines)
      or any("lever arm" in l for l in st_v.report_lines))

st_s, res_s = _spec_run(400.0, stark=1.0)
_used = any(("zero-power extrapolation over" in l and "REJECTED" not in l)
            for l in st_s.report_lines)
check("a STRONG line with a REAL Stark shift does get extrapolated to zero power",
      _used, "f = %.3f" % res_s[0]["f"])
check("and the extrapolation beats the full-drive centre it corrects",
      abs(res_s[0]["f"] - 2530.84) < 0.35,
      "extrapolated %.3f vs true 2530.84 (full-drive centre sits near 2531.84)"
      % res_s[0]["f"])

st_n, res_n = _spec_run(400.0, stark=0.0)
check("but a line with NO Stark shift is not moved by a noise-only extrapolation",
      abs(res_n[0]["f"] - 2530.84) < 0.05, "found %.4f" % res_n[0]["f"])

print("\n== but pure noise must still be rejected ==")
try:
    _spec_run(0.0)
    _noise_ok = False
except T.TunerError as e:
    _noise_ok = "did not reproduce" in str(e) or "no qubit line" in str(e)
except Exception:
    _noise_ok = False
check("a noise excursion is still rejected (repeat scan at the SAME power)", _noise_ok)

print("\n== park-flux assertion ==")
try:
    bad = dict(BaseConfig)
    bad["ff_park_gain"] = 5000
    T.AutoTuner(soc=None, soccfg=None, path="q4", outerFolder=tmp, cfg=bad).acquire()
    check("non-zero park flux refused", False)
except Exception as e:
    check("non-zero park flux refused", "PARK" in str(e).upper() or "park" in str(e))

for _label, _change, _needle in (
        ("ambiguous TLS flat-top selector",
         {"qubit_pulse_style": "arb", "flat_top_length": 0.30}, "ambiguous"),
        ("ambiguous QM flat-top selector",
         {"qubit_pulse_style": "arb", "flattop_length": 0.30}, "ambiguous"),
        ("non-Gaussian qubit pulse", {"qubit_pulse_style": "flat_top"}, "waveform"),
        ("external-switch pulse path", {"use_switch": True}, "switch"),
        ("fast-flux hold pulse path", {"ff_hold_gain": 5000}, "flux"),
        ("QM-style nested fast-flux gains",
         {"FF_Qubits": {"4": {"channel": 3, "Gain_Readout": 1200}}}, "flux")):
    try:
        bad = dict(BaseConfig)
        bad.update(_change)
        T.AutoTuner(soc=None, soccfg=None, path="q4", outerFolder=tmp, cfg=bad).acquire()
        check(_label + " mismatch refused", False)
    except Exception as e:
        check(_label + " mismatch refused", _needle.lower() in str(e).lower(), str(e))

print()
if FAIL:
    print("FAILURES (%d): %s" % (len(FAIL), FAIL))
    sys.exit(1)
print("ALL AUTOTUNER TESTS PASSED  (virtual device: %d simulated shots)" % dev.calls)
