import os
import sys
import types
import tempfile

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

    def run_seq(self, seq, drive_freq):
        """Return the excited population after a sequence.  z=+1 is |g>."""
        v = np.array([0.0, 0.0, 1.0])
        delta = float(drive_freq) - self.F_Q
        for op in seq:
            if op[0] == "pulse":
                g, ph = float(op[1]), np.deg2rad(float(op[2]))
                omega = np.pi * (g / self.PI_GAIN) / self.T_PI
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



rng = np.random.default_rng(11)
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

print("== NaN safety ==")
check("iq_to_pop returns NaN on coincident refs",
      np.isnan(T.iq_to_pop(0.5, 0.5, (1.0, 1.0), (1.0, 1.0))))
check("nan_argmin refuses to select a NaN", T.nan_argmin([np.nan, 0.5, 0.2]) == 2)
check("nan_argmin returns None for all-NaN", T.nan_argmin([np.nan, np.nan]) is None)
v = T.parabola_vertex(np.arange(13.0), np.full(13, np.nan))
check("parabola_vertex survives an all-NaN column", not np.isfinite(v["x_err"]))

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
check("the refined pi forced the readout chain to be re-measured",
      calls.get("chi", 0) >= 2 and calls.get("readout_power", 0) >= 2
      and calls.get("single_shot", 0) >= 2,
      "chi=%d readout_power=%d single_shot=%d"
      % (calls.get("chi", 0), calls.get("readout_power", 0), calls.get("single_shot", 0)))
check("spec is OUTSIDE the loop (a readout change must not re-run it)",
      calls.get("spec", 0) == 1 and calls.get("rough_pi", 0) == 1,
      "spec=%d rough_pi=%d" % (calls.get("spec", 0), calls.get("rough_pi", 0)))
check("the feedback edge is fine_pi_amp -> chi/readout_power",
      all("fine_pi_amp" in dict((n, d) for n, d, _ in T.GRAPH)[k]
          for k in ("chi", "readout_power")))
check("spec depends only on the resonator",
      dict((n, d) for n, d, _ in T.GRAPH)["spec"] == ["resonator"])
check("a better readout re-refines the pi amplitude, not just its frequency",
      "single_shot" in dict((n, d) for n, d, _ in T.GRAPH)["fine_pi_amp"])
check("T1 is re-measured through the IMPROVED readout, not only the starting one",
      "single_shot" in dict((n, d) for n, d, _ in T.GRAPH)["t1"] and calls.get("t1", 0) >= 2,
      "t1 calls=%d" % calls.get("t1", 0))
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
check("a stable device verifies clean", tuner.w.get("verified") is True)


vt = T.AutoTuner.__new__(T.AutoTuner)
vt.report_lines = []
vt.drifted = []
vt.P = T.merge_params({"single_shot": {"verify_tol_frac": 0.15}})
vt.w = {"ss_sep_sigma": 2.07, "pi_gain": 11500, "drive_freq": 2534.4}
vt._cfg_for = lambda node: {}
vt._shots_calls = 0


def _fake_ss(*a, **k):
    return {"sep_sigma": 1.81, "fidelity": 0.667, "p_e_given_g": 0.14,
            "p_g_given_e": 0.19, "outlier_frac": 0.008, "theta": 0.0}


_saved_shots, _saved_ssa = T._shots, T.single_shot_analysis
T._shots = lambda *a, **k: (np.zeros(4), np.zeros(4))
T.single_shot_analysis = _fake_ss
vt._verify_final()
T._shots, T.single_shot_analysis = _saved_shots, _saved_ssa
check("the re-measured value overwrites the stale one the gate reads",
      abs(vt.w["ss_verify_sigma"] - 1.81) < 1e-9 and vt.w["ss_sep_sigma"] == 1.81,
      "verified=%s drift=%.0f%%" % (vt.w["verified"], 100 * abs(1.81 - 2.07) / 2.07))

vt2 = T.AutoTuner.__new__(T.AutoTuner)
vt2.report_lines = []
vt2.drifted = []
vt2.P = T.merge_params({"single_shot": {"verify_tol_frac": 0.05}})
vt2.w = {"ss_sep_sigma": 2.07, "pi_gain": 11500, "drive_freq": 2534.4}
vt2._cfg_for = lambda node: {}
T._shots = lambda *a, **k: (np.zeros(4), np.zeros(4))
T.single_shot_analysis = _fake_ss
vt2._verify_final()
T._shots, T.single_shot_analysis = _saved_shots, _saved_ssa
check("a drift beyond tolerance marks the config unverified",
      vt2.w["verified"] is False
      and any("no longer reproduce" in l for l in vt2.report_lines))

print("\n== fine_pi_amp: a pi train may REFINE the anchor, never relocate it ==")


class _StubTuner(T.AutoTuner):
    def __init__(self, vertex_gain, anchor, **kw):
        self.report_lines = []
        self.node_data = {}
        self.drifted = []
        self.stale = {n: True for n, _, _ in T.GRAPH}
        self.P = T.merge_params(kw.pop("params", None))
        self.cfg = dict(BaseConfig)
        self.element = "q4"
        self.soc = None
        self._vertex = float(vertex_gain)
        self.windows = []
        self.w = {"pi_gain": float(anchor), "drive_freq": 2534.4, "t1_us": 1e6,
                  "relax_delay": 500.0, "read_pulse_freq": 7248.9, "read_pulse_gain": 4300,
                  "read_length": 20.0, "res_phase": 0.0, "updated": set(),
                  "pi_gain_anchor_err": 0.03 * float(anchor)}

    def _pi_train(self, cfg, gain, M, freq, shots):
        return float((gain - self._vertex) ** 2) / 1e6, 1.0, 1e-4

    def _cfg_for(self, node):
        return dict(self.cfg)


st = _StubTuner(vertex_gain=11400.0, anchor=11542.0,
                params={"fine_pi_amp": {"M_list": (4, 10, 20), "points": 13}})
st._cal_fine_pi_amp()
check("a vertex consistent with the anchor is adopted",
      abs(st.w["pi_gain"] - 11400) < 60, "got %d" % st.w["pi_gain"])

st2 = _StubTuner(vertex_gain=10674.0, anchor=11542.0,
                 params={"fine_pi_amp": {"M_list": (4, 10, 20), "points": 13}})
try:
    st2._cal_fine_pi_amp()
    moved2 = abs(st2.w["pi_gain"] - 11542)
except T.TunerError:
    moved2 = 0.0
check("a vertex 868 DAC off the anchor is REJECTED, not adopted (the M-ladder poisoning)",
      moved2 < 400, "estimate moved %d DAC" % moved2)
check("the rejection is reported, not silent",
      any("REJECTED as a sidelobe" in l for l in st2.report_lines))
check("the M-agreement count reports ADOPTED passes, not every pass attempted",
      st2.w.get("pi_n_agree") == 0 and st.w.get("pi_n_agree") == 3,
      "rejected-run=%s good-run=%s" % (st2.w.get("pi_n_agree"), st.w.get("pi_n_agree")))

st3 = _StubTuner(vertex_gain=11400.0, anchor=11542.0,
                 params={"fine_pi_amp": {"M_list": (20,), "frac": (0.025,), "points": 13}})
st3.w["pi_gain_anchor_err"] = 0.03 * 11542
try:
    st3._cal_fine_pi_amp()
except T.TunerError:
    pass
check("M=20 is skipped when a 3% estimate is too coarse to error-amplify safely",
      any("skipping M=20" in l and "sidelobe" in l for l in st3.report_lines))

print("\n== the pi-train window cap must match the real sin^2 response ==")
for M in (4, 10, 20):
    f = np.linspace(1e-6, 1.0 / M, 400)
    p = np.sin(M * np.pi * f / 2.0) ** 2
    check("M=%d: the response rises monotonically across the whole 1/M window" % M,
          bool(np.all(np.diff(p) > 0)), "half-width %.3f" % (1.0 / M))
    fz = np.linspace(1e-6, 3.0 / M, 4000)
    pz = np.sin(M * np.pi * fz / 2.0) ** 2
    first_zero = float(fz[1 + np.argmin(pz[1:])])
    check("M=%d: the first spurious minimum is at 2/M, twice the cap used" % M,
          abs(first_zero - 2.0 / M) < 0.02 / M, "%.4f vs %.4f" % (first_zero, 2.0 / M))

worst = []
for M in (4, 10, 20):
    alias = 1.0 / M
    for u in np.linspace(1e-5, 0.75 * alias / 2.0, 60):
        need = 2.0 * u
        if need > 0.75 * alias:
            continue
        frac = dict(zip(T.DEFAULTS["fine_pi_amp"]["M_list"],
                        T.DEFAULTS["fine_pi_amp"]["frac"]))[M]
        half = float(np.clip(frac, need, 1.5 * alias - need))
        worst.append((need + half) * M)
check("window edge + 2-sigma excursion NEVER reaches the 2/M sidelobe zero",
      max(worst) < 2.0, "worst reach = %.2f/M (zero at 2/M)" % max(worst))

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
lt2._cal_readout_len()
check("extension stops at the T1/2 cap and says the LIFETIME is the limit",
      lt2.w["read_length"] <= 50.0
      and any("T1/2 cap" in l for l in lt2.report_lines),
      "chose %.1f us (cap 50)" % lt2.w["read_length"])

print("\n== readout_power: the outlier gate is a penalty, not a cliff ==")


class _PowTuner(_StubTuner):
    ROWS = [(1075, 0.84, 0.346, 0.000), (1720, 1.21, 0.487, 0.001),
            (2580, 1.73, 0.661, 0.002), (3655, 1.81, 0.700, 0.029),
            (5160, 1.98, 0.751, 0.049), (7310, 1.26, 0.573, 0.047),
            (10320, 1.27, 0.639, 0.084), (14620, 0.20, 0.043, 0.011)]

    def _sweep_readout(self, node, cands, apply_fn, shots):
        d = {r[0]: r for r in self.ROWS}
        sep = np.array([d[c][1] for c in cands])
        fid = np.array([d[c][2] for c in cands])
        out = np.array([d[c][3] for c in cands])
        return sep, fid, out, 0.0


pt = _PowTuner(11500.0, 11500.0)
pt.w["read_pulse_gain"] = 4300
pt.P["readout_power"]["ratios"] = tuple(r[0] / 4300.0 for r in _PowTuner.ROWS)
pt._cal_readout_power()
check("the hardware run's 1.98 sigma point is no longer discarded for a 4.9% outlier rate",
      pt.w["read_pulse_gain"] == 5160, "chose gain %d" % pt.w["read_pulse_gain"])
check("a grossly non-two-blob power is still rejected outright",
      pt.w["read_pulse_gain"] != 10320)
pt2 = _PowTuner(11500.0, 11500.0)
pt2.w["read_pulse_gain"] = 4300
pt2.P["readout_power"]["ratios"] = tuple(r[0] / 4300.0 for r in _PowTuner.ROWS)
pt2.P["readout_power"]["outlier_weight"] = 50.0
pt2._cal_readout_power()
check("raising outlier_weight restores the strict choice",
      pt2.w["read_pulse_gain"] == 2580, "chose gain %d" % pt2.w["read_pulse_gain"])

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
                 params={"max_rounds": 2, "spec": {"span_mhz": 20.0, "max_span_mhz": 120.0},
                         "t1": {"points": 6, "shots": 300},
                         "single_shot": {"shots": 1200, "min_sep_sigma": 2.0},
                         "fine_pi_amp": {"M_list": (4, 10), "frac": (0.12, 0.05)}})
out3 = t3.acquire(plotDisp=False)
T.AutoTuner._cal_spec = _real_spec
T.AutoTuner._cal_fine_pi_amp = _orig_fine
check("a round-2 spec failure did not abort the run",
      bool(out3["data"].get("tuned")), "tuned=%s" % bool(out3["data"].get("tuned")))
check("the fallback is reported, not silent",
      any("KEEPING the round-1 value" in l for l in t3.report_lines))
check("the mixed-vintage config is flagged", "spec" in t3.drifted)

print("\n== T1 with a 57% error bar must not silently shorten downstream bounds ==")


class _T1Tuner(_StubTuner):
    def __init__(self, tau, tau_err, **kw):
        _StubTuner.__init__(self, 11500.0, 11500.0, **kw)
        self._tau, self._err = float(tau), float(tau_err)

    def _cfg_for(self, node):
        return dict(self.cfg)


def _run_t1(tau, tau_err, relax0=3000.0):
    t = _T1Tuner(tau, tau_err)
    t.w["relax_delay"] = relax0
    saved_pop, saved_fit = T._pop_with_local_refs, T.fit_exp_decay
    T._pop_with_local_refs = lambda *a, **k: (0.5, 1.0, 0.01)
    T.fit_exp_decay = lambda ts, ps: {"ok": True, "tau": t._tau, "tau_err": t._err,
                                      "yfit": np.zeros_like(ts)}
    try:
        t._cal_t1()
    finally:
        T._pop_with_local_refs, T.fit_exp_decay = saved_pop, saved_fit
    return t


t1t = _run_t1(140.6, 80.3)
check("a 57%-determined T1 does NOT collapse relax_delay (5*T1=703, never 25 us)",
      t1t.w["relax_delay"] >= 5.0 * 140.6,
      "relax_delay=%.0f us vs 5*tau=%.0f" % (t1t.w["relax_delay"], 5 * 140.6))
check("relax_delay uses the UPPER T1 bound, so a wait is never shorter than 5*tau",
      t1t.w["relax_delay"] >= 5.0 * t1t.w["t1_us"],
      "%.0f vs 5*t1_us=%.0f" % (t1t.w["relax_delay"], 5 * t1t.w["t1_us"]))
check("the readout-length cap uses the LOWER bound (shorter is the safe side)",
      t1t.w["t1_lo_us"] < t1t.w["t1_us"] < t1t.w["t1_hi_us"],
      "lo=%.1f tau=%.1f hi=%.1f" % (t1t.w["t1_lo_us"], t1t.w["t1_us"], t1t.w["t1_hi_us"]))
check("the reported T1 is the FIT, not a bound",
      abs(t1t.w["t1_us"] - 140.6) < 1e-9, "t1_us=%.1f" % t1t.w["t1_us"])
check("the low bound does not collapse to a hard floor and gut the readout ladder",
      t1t.w["t1_lo_us"] >= 0.25 * 140.6, "lo=%.1f" % t1t.w["t1_lo_us"])

t1g = _run_t1(25.0, 1.0)
check("a well-determined T1 still shortens relax_delay for runtime",
      t1g.w["relax_delay"] < 3000.0 and t1g.w["relax_delay"] >= 5.0 * 25.0,
      "relax_delay=%.0f us" % t1g.w["relax_delay"])

t1n = _run_t1(140.6, float("inf"))
check("a T1 with NO usable error bar is not treated as precise",
      t1n.w["t1_hi_us"] > 140.6 and t1n.w["relax_delay"] >= 5.0 * 140.6,
      "hi=%.1f relax=%.0f" % (t1n.w["t1_hi_us"], t1n.w["relax_delay"]))

print("\n== an ASYMMETRIC resonator dip must not bias f0 ==")
_rng = np.random.default_rng(7)
for phi in (0.0, 30.0, 60.0):
    fr, kap = 7248.9000, 0.350
    fgrid = np.linspace(fr - 2.0, fr + 2.0, 81)
    xg = fgrid - fr
    s21 = 1.0 - (0.55 * np.exp(1j * np.deg2rad(phi))) / (1 + 2j * xg / kap)
    zc = 3000.0 * np.exp(1j * 0.7) * (1 + 0.01 * xg) * s21
    zc = zc + (_rng.normal(0, 25, fgrid.size) + 1j * _rng.normal(0, 25, fgrid.size))
    sym = T.fit_resonance(fgrid, np.abs(zc) ** 2, expected_fwhm=0.3)
    cpx = T.fit_notch_complex(fgrid, zc, f0_guess=fgrid[np.argmin(np.abs(zc))],
                              kappa_guess=0.4)
    check("phi=%2.0f deg: complex notch fit recovers f0 to <20 kHz" % phi,
          cpx["ok"] and abs(cpx["f0"] - fr) < 0.020,
          "err = %+.1f kHz" % (1000 * (cpx["f0"] - fr)))
    check("phi=%2.0f deg: complex fit recovers kappa to <10%%" % phi,
          cpx["ok"] and abs(cpx["fwhm"] - kap) / kap < 0.10,
          "kappa = %.3f vs %.3f" % (cpx["fwhm"], kap))
    check("phi=%2.0f deg: asymmetry angle is reported, not hidden" % phi,
          cpx["ok"] and abs(cpx["asym_deg"] - phi) < 6.0,
          "asym = %.1f deg" % cpx["asym_deg"])
    if phi >= 30.0:
        check("phi=%2.0f deg: the SYMMETRIC fit really is biased (this is why)" % phi,
              sym["ok"] and abs(sym["f0"] - fr) > 0.050,
              "symmetric err = %+.1f kHz = %.2f kappa"
              % (1000 * (sym["f0"] - fr), abs(sym["f0"] - fr) / kap))

print("\n== a real qubit line must survive the spec power confirmation ==")


def _spec_run(snr_full, seed=3):
    rng = np.random.default_rng(seed)
    f_true, fwhm = 2530.84, 3.9

    class FakeSpec(object):
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, **kw):
            c = self.cfg
            fs = c["start"] + c["step"] * np.arange(c["expts"])
            amp = snr_full * (float(c["spec_gain"]) / 7000.0) ** 2
            peak = amp / (1.0 + ((fs - f_true) / (fwhm / 2.0)) ** 2)
            i = peak + rng.normal(0, 1.0, fs.size)
            q = rng.normal(0, 1.0, fs.size)
            return fs, [[i]], [[q]]

    t = _StubTuner(11500.0, 11500.0)
    t.cfg["qubit_gain"], t.cfg["qubit_length"] = 7000, 2.0
    t.w["qubit_freq"] = 2512.0
    t.soccfg, t.soc = None, None
    saved = T.SpecProgram
    T.SpecProgram = FakeSpec
    try:
        return t, t._cal_spec()
    finally:
        T.SpecProgram = saved


st_w, res_w = _spec_run(14.1)
check("a REAL line at the snr that just failed on hardware is now accepted",
      abs(res_w[0]["f"] - 2530.84) < 1.0, "found %.3f MHz" % res_w[0]["f"])
check("a weak line is never made WORSE by extrapolating over a short lever arm",
      abs(res_w[0]["f"] - 2530.84) < 0.15,
      "found %.4f, full-power centre was accurate" % res_w[0]["f"])
check("and the tuner says WHY it did not extrapolate, instead of dying",
      any(("lever arm" in l or "gain^2" in l) for l in st_w.report_lines))

st_v, res_v = _spec_run(5.5, seed=11)
check("an even weaker line skips the ladder entirely rather than failing",
      abs(res_v[0]["f"] - 2530.84) < 1.5, "found %.3f" % res_v[0]["f"])
check("the Rabi is named as the real confirmation, not the power ladder",
      any("coherent oscillation" in l for l in st_v.report_lines)
      or any("lever arm" in l for l in st_v.report_lines))

st_s, res_s = _spec_run(400.0)
check("a STRONG line still gets the zero-power Stark extrapolation",
      any("zero-power extrapolation" in l for l in st_s.report_lines),
      "f = %.3f" % res_s[0]["f"])

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

print()
if FAIL:
    print("FAILURES (%d): %s" % (len(FAIL), FAIL))
    sys.exit(1)
print("ALL AUTOTUNER TESTS PASSED  (virtual device: %d simulated shots)" % dev.calls)
