"""
End-to-end verification of the AutoTuner calibration graph against a SIMULATED qubit
with known ground truth.

This is the strongest check available without hardware: a virtual device with a
dispersive resonator (chi, kappa), a transmon (true pi gain, true frequency, T1, T2*),
realistic shot noise, T1 decay during readout, and ionization above a critical readout
power.  The tuner is then run against it and must recover the true parameters.

Run:  python WorkingProjects/TLS_Spectroscopy/Client_modules/Tests/test_auto_tuner.py
"""

import os
import sys
import types
import tempfile

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, REPO)

# ---- mock qick before importing the tuner ----
qick = types.ModuleType("qick")
qick.AveragerProgram = type("AveragerProgram", (), {})
qick.RAveragerProgram = type("RAveragerProgram", (), {})
sys.modules["qick"] = qick

import matplotlib
matplotlib.use("Agg")

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mAutoTuner as T

FAIL = []


def check(name, cond, detail=""):
    print("  %-62s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        FAIL.append(name)


# ======================================================================================
# Virtual device
# ======================================================================================

class VirtualQubit:
    F_R = 7248.9000          # bare resonator (MHz)
    KAPPA = 0.35             # linewidth (MHz)
    CHI = -0.12              # dispersive shift (MHz)
    F_Q = 2534.4000          # qubit (MHz)
    PI_GAIN = 11500.0        # DAC units for a pi
    T1 = 25.0                # us
    T2 = 0.6                 # us (short, like the real device)
    T_PI = 0.5               # us (4*sigma)
    G_CRIT = 14000.0         # readout gain above which the device ionizes
    NOISE = 0.055            # per-shot amplitude noise at 1 us integration

    def __init__(self, rng):
        self.rng = rng
        self.calls = 0

    # ---- resonator response ----
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
        # T1 decay during integration: the time-averaged excited population
        p_eff = p_e * (self.T1 / L) * (1.0 - np.exp(-L / self.T1))
        a = self.alpha(f, g, p_eff)
        # noise: amplitude noise integrates down as sqrt(L)
        sd = self.NOISE / np.sqrt(max(L, 1e-6))
        n = int(shots)
        self.calls += n
        I = self.rng.normal(a.real, sd, n)
        Q = self.rng.normal(a.imag, sd, n)
        if g > self.G_CRIT:                       # ionization -> a third, smeared blob
            frac = min(0.6, (g / self.G_CRIT - 1.0) * 2.0)
            k = self.rng.random(n) < frac
            I[k] = self.rng.normal(0.0, 4 * sd, k.sum())
            Q[k] = self.rng.normal(0.0, 4 * sd, k.sum())
        if per_shot:
            return I, Q
        return float(I.mean()), float(Q.mean()), float(I.std(ddof=1) / np.sqrt(n)), \
            float(Q.std(ddof=1) / np.sqrt(n))

    # ---- Bloch evolution ----
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

    def run_seq(self, seq, drive_freq):
        """Return the excited population after a sequence.  z=+1 is |g>."""
        v = np.array([0.0, 0.0, 1.0])
        delta = float(drive_freq) - self.F_Q          # MHz
        for op in seq:
            if op[0] == "pulse":
                g, ph = float(op[1]), np.deg2rad(float(op[2]))
                omega = np.pi * (g / self.PI_GAIN) / self.T_PI     # rad/us
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
        stark = 2.5e-9 * gain ** 2                       # MHz, pushes the line up
        d = 2 * np.pi * (np.asarray(f, dtype=float) - (self.F_Q + stark))
        gam = 1.0 / self.T2
        s = (omega ** 2 / 2.0) / (d ** 2 + gam ** 2 + omega ** 2 / 2.0)
        return 0.5 * s


# ======================================================================================
# Patch the tuner's measurement primitives to talk to the virtual device
# ======================================================================================

def install_simulator(dev):
    def _avg_iq(exp, prog_cls, cfg):
        p_e = 0.0
        if int(cfg.get("prep_gain", 0)) > 0:
            p_e = dev.run_seq([("pulse", int(cfg["prep_gain"]), 0.0)], cfg["drive_freq"])
        return dev._readout(cfg, p_e, int(cfg["reps"]), per_shot=False)

    def _run_seq(exp, cfg, seq, drive_freq, shots):
        p_e = dev.run_seq(seq, drive_freq)
        return dev._readout(cfg, p_e, int(shots), per_shot=False)

    def _shots(exp, cfg, seq, drive_freq, shots):
        p_e = dev.run_seq(seq, drive_freq)
        return dev._readout(cfg, p_e, int(shots), per_shot=True)

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
                p = dev.run_seq([("pulse", int(g), 0.0)], cfg["drive_freq"]) if g > 0 else 0.0
                a = dev.alpha(cfg["read_pulse_freq"], cfg["read_pulse_gain"], p)
                sd = dev.NOISE / np.sqrt(max(cfg["read_length"], 1e-6) * cfg["reps"])
                I[j] = dev.rng.normal(a.real, sd)
                Q[j] = dev.rng.normal(a.imag, sd)
            return gains, [[I]], [[Q]]

    T._avg_iq = _avg_iq
    T._run_seq = _run_seq
    T._shots = _shots
    T.SpecProgram = FakeSpec
    T.RabiProgram = FakeRabi


# ======================================================================================
# Unit checks on the pure analysis
# ======================================================================================

rng = np.random.default_rng(11)
print("== pure analysis ==")

f = np.linspace(7246, 7252, 121)
dip = T.lorentzian(f, 7248.953, 0.35, -3.0, 10.0, slope=0.4) + rng.normal(0, 0.05, f.size)
r = T.fit_resonance(f, dip, expected_fwhm=0.35)
check("Lorentzian on a SLOPED baseline: f0 within 20 kHz",
      r["ok"] and abs(r["f0"] - 7248.953) < 0.02, "f0=%.4f slope-tolerant" % r["f0"])

# the fixed-7-boxcar bug: a narrow scan must still find a narrow feature
fn = np.linspace(7248.95 - 1.5, 7248.95 + 1.5, 61)          # 50 kHz spacing
dipn = T.lorentzian(fn, 7248.9378, 0.216, -3.0, 10.0) + rng.normal(0, 0.06, fn.size)
rn = T.fit_resonance(fn, dipn, expected_fwhm=0.216)
check("narrow 3 MHz/61pt scan finds a 216 kHz dip (old fixed kernel erased it)",
      rn["ok"] and abs(rn["f0"] - 7248.9378) < 0.03, "f0=%.4f snr=%.1f" % (rn["f0"], rn["snr"]))

check("pure noise rejected", not T.fit_resonance(f, rng.normal(0, 0.05, f.size))["ok"])

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
# a residual FLOOR must not masquerade as an angle error
res_floor = 0.30 + np.sin(20 * np.pi * (g / gpi - 1.0) / 2.0) ** 2
v = T.parabola_vertex(g, res_floor)
check("a 0.30 decoherence floor does not move the vertex",
      abs(v["x_min"] - gpi) / gpi < 0.005, "%.0f" % v["x_min"])

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
# ionization -> third blob -> outlier gate must fire
ie3 = np.concatenate([rng.normal(6, 1, n // 2), rng.normal(0, 5, n // 2)])
qe3 = np.concatenate([rng.normal(0, 1, n // 2), rng.normal(0, 5, n // 2)])
ss3 = T.single_shot_analysis(ig, qg, ie3, qe3)
check("ionized/smeared readout flagged by the outlier fraction",
      ss3["outlier_frac"] > 0.05, "outliers=%.3f" % ss3["outlier_frac"])

print("== NaN safety ==")
check("iq_to_pop returns NaN on coincident refs",
      np.isnan(T.iq_to_pop(0.5, 0.5, (1.0, 1.0), (1.0, 1.0))))
check("nan_argmin refuses to select a NaN", T.nan_argmin([np.nan, 0.5, 0.2]) == 2)
check("nan_argmin returns None for all-NaN", T.nan_argmin([np.nan, np.nan]) is None)
v = T.parabola_vertex(np.arange(13.0), np.full(13, np.nan))
check("parabola_vertex survives an all-NaN column", not np.isfinite(v["x_err"]))

# ======================================================================================
# End-to-end: run the whole graph against the virtual qubit
# ======================================================================================
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

tmp = tempfile.mkdtemp(prefix="autotuner_test_")
tuner = T.AutoTuner(soc=None, soccfg=None, path="q4", outerFolder=tmp,
                    suffix="Auto_Tune", cfg=dict(BaseConfig),
                    params={"max_rounds": 3,
                            "spec": {"span_mhz": 20.0, "max_span_mhz": 120.0},
                            "t1": {"points": 8, "shots": 400},
                            "single_shot": {"shots": 2500, "min_sep_sigma": 2.0},
                            "fine_pi_amp": {"M_list": (4, 10), "frac": (0.12, 0.05)}})
out = tuner.acquire(plotDisp=False)
w = out["data"]["working"]

print("\n  --- recovered vs truth ---")
f_dressed_g = dev.F_R - dev.CHI       # the |g> scan sees the dressed resonance
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
check("run marked SUCCESS", bool(out["data"]["success"]))
tuned = out["data"]["tuned"]
check("qubit_pi_freq only written because fine_pi_freq measured it",
      "qubit_pi_freq" in tuned)
check("qubit_pi2_gain NOT written (never measured)", "qubit_pi2_gain" not in tuned)

print("\n== the graph must actually ITERATE (this is what the old test missed) ==")
# The previous test asserted only recovered VALUES, so it passed while maintain() ran a
# single straight-line pass and printed "FIXED POINT reached".  Count calibrations.
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
                 params={"max_rounds": 3,
                         "spec": {"span_mhz": 20.0, "max_span_mhz": 120.0},
                         "t1": {"points": 6, "shots": 300},
                         "single_shot": {"shots": 1500, "min_sep_sigma": 2.0},
                         "fine_pi_amp": {"M_list": (4, 10), "frac": (0.12, 0.05)}})
t2.acquire(plotDisp=False)
check("at least one node was recalibrated (invalidation fired)",
      max(calls.values()) >= 2, "calls=%s" % calls)
check("the readout nodes forced spec/rough_pi to be re-measured",
      calls.get("spec", 0) >= 2 or calls.get("rough_pi", 0) >= 2,
      "spec=%d rough_pi=%d" % (calls.get("spec", 0), calls.get("rough_pi", 0)))
check("_mark_dependents_stale is reachable (deps include readout back-edges)",
      any("readout_power" in deps or "chi" in deps for _n, deps, _m in T.GRAPH))

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

print("\n== park-flux assertion ==")
try:
    bad = dict(BaseConfig)
    bad["ff_park_gain"] = 5000
    T.AutoTuner(soc=None, soccfg=None, path="q4", outerFolder=tmp, cfg=bad).acquire()
    check("non-zero park flux refused", False)
except Exception as e:
    check("non-zero park flux refused", "PARK" in str(e).upper() or "park" in str(e))

print()
if FAIL:
    print("FAILURES (%d): %s" % (len(FAIL), FAIL))
    sys.exit(1)
print("ALL AUTOTUNER TESTS PASSED  (virtual device: %d simulated shots)" % dev.calls)
