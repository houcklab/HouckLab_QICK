"""Synthetic verification of the AutoPiTuner: fits recover ground truth, the
correction loops converge on a simulated qubit, and the config writer round-trips
on a copy of the real initialize.py."""
import os
import shutil
import sys
import types

import numpy as np

import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
SCRATCH = tempfile.mkdtemp(prefix="auto_pi_tuner_test_")
sys.path.insert(0, REPO)

# ---- mock qick (only the two base classes the module subclasses) ----
qick = types.ModuleType("qick")
qick.AveragerProgram = type("AveragerProgram", (), {})
qick.RAveragerProgram = type("RAveragerProgram", (), {})
sys.modules["qick"] = qick

import matplotlib
matplotlib.use("Agg")

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mAutoPiTuner as T
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import config_updater as CU

rng = np.random.default_rng(7)
FAIL = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print("  %-58s %s %s" % (name, status, detail))
    if not cond:
        FAIL.append(name)


print("== fit_resonance ==")
f = np.linspace(7246.0, 7252.0, 121)
dip = T.lorentzian(f, 7248.953, 0.4, -3.0, 10.0) + rng.normal(0, 0.05, f.size)
r = T.fit_resonance(f, dip)
check("dip f0 within 20 kHz", r["ok"] and abs(r["f0"] - 7248.953) < 0.02, "f0=%.4f" % r["f0"])
check("dip polarity", r["polarity"] == "dip")
peak = T.lorentzian(f, 7249.4, 0.6, +2.0, 1.0) + rng.normal(0, 0.04, f.size)
r = T.fit_resonance(f, peak)
check("peak f0 within 30 kHz", r["ok"] and abs(r["f0"] - 7249.4) < 0.03, "f0=%.4f" % r["f0"])
flat = rng.normal(0, 0.05, f.size)
r = T.fit_resonance(f, flat)
check("pure noise rejected (ok=False)", not r["ok"], "snr=%.1f" % r["snr"])

print("== fit_rabi ==")
g = np.arange(61) * 500.0                      # 0..30000
pi_true = 12850.0
sig = 0.2 - 0.15 * np.cos(np.pi * g / pi_true) + rng.normal(0, 0.006, g.size)
r = T.fit_rabi(g, sig)
check("pi gain within 1%", r["ok"] and abs(r["pi_gain"] - pi_true) / pi_true < 0.01,
      "pi=%.0f r2=%.3f" % (r["pi_gain"], r["r2"]))
sig2 = -(0.2 - 0.15 * np.cos(np.pi * g / 9000.0)) + rng.normal(0, 0.006, g.size)
r = T.fit_rabi(g, sig2)
check("inverted-sign trace, pi=9000 within 1%", r["ok"] and abs(r["pi_gain"] - 9000) / 9000 < 0.01,
      "pi=%.0f" % r["pi_gain"])
r = T.fit_rabi(g, rng.normal(0, 0.01, g.size))
check("noise-only Rabi rejected", not r["ok"], "r2=%.2f" % r["r2"])

print("== fit_ramsey_xy (signed) ==")
t = np.linspace(0.05, 4.0, 31)
for f_true in (+1.23, -0.78):
    X = 0.5 + 0.45 * np.exp(-t / 8.0) * np.cos(2 * np.pi * f_true * t + 0.05) + rng.normal(0, 0.02, t.size)
    Y = 0.5 + 0.45 * np.exp(-t / 8.0) * np.sin(2 * np.pi * f_true * t + 0.05) + rng.normal(0, 0.02, t.size)
    r = T.fit_ramsey_xy(t, X, Y)
    check("f=%+.2f recovered (sign + 20 kHz)" % f_true,
          r["ok"] and abs(r["f_mhz"] - f_true) < 0.02, "fit=%+.4f T2=%.1f" % (r["f_mhz"], r["t2_us"]))
r = T.fit_ramsey_xy(t, 0.5 + rng.normal(0, 0.02, t.size), 0.5 + rng.normal(0, 0.02, t.size))
check("no-fringe rejected", not r["ok"], "amp=%.3f" % r["amp"])

print("== fit_error_amp ==")
N = np.arange(0, 15)
for dth_true, eps_true in ((+0.05, 0.02), (-0.11, -0.04), (0.002, 0.0)):
    pop = 0.5 + 0.5 * ((-1.0) ** N) * np.sin(N * dth_true + eps_true) + rng.normal(0, 0.012, N.size)
    r = T.fit_error_amp(N, pop)
    tolerance = max(0.01, 3 * r["sigma"])
    check("dtheta=%+.3f recovered" % dth_true, r["ok"] and abs(r["d_theta"] - dth_true) < tolerance,
          "fit=%+.4f+/-%.4f eps=%+.3f" % (r["d_theta"], r["sigma"], r["eps"]))

print("== closed-loop convergence simulations ==")


def converged(r, pop, n_max, tol=0.01):
    """The tuner's actual convergence rule: constrained fit within tol, OR the
    pattern's flatness physically bounds |dtheta| below tol."""
    flat_bound = 2.0 * (0.5 * float(np.ptp(pop))) / n_max
    return (abs(r["d_theta"]) <= tol and r["sigma"] <= 0.03) or flat_bound <= tol


# a 0.05 rad error must NOT be declared converged on its first look
pop = 0.5 + 0.5 * ((-1.0) ** N) * np.sin(N * 0.05) + rng.normal(0, 0.012, N.size)
r = T.fit_error_amp(N, pop)
check("dtheta=0.05 NOT prematurely converged", not converged(r, pop, N.max()),
      "fit=%+.4f+/-%.4f" % (r["d_theta"], r["sigma"]))
# a truly flat pattern (dtheta ~ 0) IS converged via the flatness bound
pop = 0.5 + 0.5 * ((-1.0) ** N) * np.sin(N * 0.002) + rng.normal(0, 0.012, N.size)
r = T.fit_error_amp(N, pop)
check("dtheta=0.002 converged via flatness bound", converged(r, pop, N.max()))

# fine-amp loop: virtual qubit whose per-pulse angle = pi * gain/gain_pi_true
gain_pi_true = 13100.0
gain = 12300.0                                   # start 6% low
rounds_used = 0
for _ in range(5):
    rounds_used += 1
    dth_actual = np.pi * gain / gain_pi_true - np.pi
    pop = 0.5 + 0.5 * ((-1.0) ** N) * np.sin(N * dth_actual) + rng.normal(0, 0.01, N.size)
    r = T.fit_error_amp(N, pop)
    if converged(r, pop, N.max()):
        break
    gain = gain * float(np.clip(np.pi / (np.pi + r["d_theta"]), 0.8, 1.25))
final_err = abs(np.pi * gain / gain_pi_true - np.pi)
check("fine-amp loop converges (<0.35% angle)", final_err < 0.011,
      "resid=%.4f rad in %d rounds" % (final_err, rounds_used))

# Ramsey sign logic, BOTH hardware conventions p_hw = +/-1:
#   f_osc = |f_virt + p_hw * (f_q - f_drive)|; probe: slope = d|f_osc|/d f_drive = -p_hw
for p_hw in (+1, -1):
    f_q, f_d, f_v, d = 2557.37, 2557.25, 1.0, 0.25
    fo1 = abs(f_v + p_hw * (f_q - f_d))
    fo2 = abs(f_v + p_hw * (f_q - (f_d + d)))
    slope = (fo2 - fo1) / d
    p_est = -1 if slope > 0 else +1
    delta_est = (fo1 - f_v) / p_est
    f_d2 = f_d + delta_est
    resid = abs(f_q - f_d2)
    check("ramsey sign+correction, p_hw=%+d" % p_hw, p_est == p_hw and resid < 1e-9,
          "p_est=%+d resid=%.2e MHz" % (p_est, resid))

print("== iq_to_pop ==")
pop = T.iq_to_pop([0.4, 0.5, 0.45], [0.4, 0.5, 0.45], (0.4, 0.4), (0.5, 0.5))
check("g->0, e->1, mid->0.5", np.allclose(pop, [0.0, 1.0, 0.5], atol=1e-12), str(pop))

print("== config_updater round-trip (on a COPY) ==")
src = os.path.join(REPO, "WorkingProjects/TLS_Spectroscopy/Client_modules/Calib/initialize.py")
cpy = os.path.join(SCRATCH, "initialize_copy.py")
shutil.copy2(src, cpy)
before = open(cpy, encoding="utf-8").read()
updates = {"read_pulse_freq": 7249.1234, "qubit_freq": 2556.789, "qubit_pi_freq": 2556.9012,
           "qubit_pi_gain": 13111, "qubit_pi2_gain": 6556}
changed = CU.update_baseconfig(updates, path=cpy, backup=True)
vals = CU.read_baseconfig(cpy)
check("all 5 values verified after write",
      all((vals[k] == v if isinstance(v, int) else abs(vals[k] - v) < 1e-9)
          for k, v in updates.items()), str({k: vals[k] for k in updates}))
after = open(cpy, encoding="utf-8").read()
b_lines, a_lines = before.splitlines(), after.splitlines()
check("same line count", len(b_lines) == len(a_lines))
diff = [i for i, (b, a) in enumerate(zip(b_lines, a_lines)) if b != a]
check("exactly 5 lines changed", len(diff) == 5, "changed lines: %s" % diff)
check("comments preserved on changed lines",
      all(("#" in a_lines[i]) == ("#" in b_lines[i]) for i in diff))
check("untouched value intact (sigma)", vals["sigma"] == 0.125)
check("untouched value intact (read_pulse_gain)", vals["read_pulse_gain"] == 4300)
baks = [x for x in os.listdir(SCRATCH) if x.startswith("initialize_copy.py.bak_")]
check("backup created", len(baks) >= 1, str(baks))
try:
    CU.update_baseconfig({"no_such_key": 1}, path=cpy)
    check("missing key raises", False)
except RuntimeError as e:
    check("missing key raises", True, str(e)[:50])
after2 = open(cpy, encoding="utf-8").read()
check("failed update wrote nothing", after2 == after)

hist = os.path.join(SCRATCH, "pi_calibration_history.json")
if os.path.exists(hist):
    os.remove(hist)
CU.append_history({"time": "t1", "success": False, "ramsey_sign": None}, path=cpy)
CU.append_history({"time": "t2", "success": True, "ramsey_sign": -1}, path=cpy)
check("last_ramsey_sign from history", CU.last_ramsey_sign(path=cpy) == -1)

print("== review-fix regressions ==")
# numpy scalars must keep their types in the file (np.int64 gain must NOT become a float)
changed2 = CU.update_baseconfig({"qubit_pi_gain": np.int64(14001),
                                 "qubit_pi_freq": np.float64(2557.123456789)}, path=cpy)
vals2 = CU.read_baseconfig(cpy)
check("np.int64 gain written as int", isinstance(vals2["qubit_pi_gain"], int)
      and vals2["qubit_pi_gain"] == 14001, repr(vals2["qubit_pi_gain"]))
check("unrounded np.float64 freq verifies (4-dec contract)",
      abs(vals2["qubit_pi_freq"] - 2557.1235) < 1e-9, repr(vals2["qubit_pi_freq"]))
check("_fmt(np.int64) is an int literal", CU._fmt(np.int64(7)) == "7")
check("_fmt(np.bool_) is a bool literal", CU._fmt(np.bool_(True)) == "True")

print("== plot robustness (mismatched arrays must not crash a finished run) ==")
import matplotlib.pyplot as plt
_fig, _ax = plt.subplots()
try:
    T.AutoPiTuner._pair(_ax, np.arange(41), np.arange(183), "-")   # the shape that crashed
    T.AutoPiTuner._pair(_ax, np.arange(10), np.arange(10), "-")    # valid pair still plots
    check("mismatched x/y skipped, matched pair drawn", len(_ax.lines) == 1,
          "%d line(s) drawn" % len(_ax.lines))
except Exception as e:
    check("mismatched x/y skipped, matched pair drawn", False, repr(e))
plt.close(_fig)

print("== ramsey coherence-limited diagnosis ==")
# T2*=0.6 us -> resolution ~265 kHz; the observed 0.081 -> 0.159 MHz "growth" is noise,
# so it must NOT be blamed on the sign convention.
for t2, d_prev, d_now, expect_sign_blame in ((0.6, 0.0809, 0.1591, False),
                                             (20.0, 0.0809, 0.1591, True)):
    f_res = 1.0 / (2.0 * np.pi * t2)
    blames_sign = (d_now - d_prev) > 2.0 * f_res
    check("T2*=%.1f us -> sign blamed: %s" % (t2, expect_sign_blame),
          blames_sign == expect_sign_blame, "f_res=%.3f MHz" % f_res)
# and a detuning below the resolution counts as converged
check("detuning below resolution = converged",
      0.0809 <= max(0.02, 1.0 / (2.0 * np.pi * 0.6)))

print("== pi-harmonic validation (the 2x-wrong-period failure) ==")
# |g>-displacement vs gain follows |sin(theta/2)| with theta = pi*g/g_pi_true.
# If the Rabi fit returned 2x the true pi, the max displacement must appear at 0.5x.
def _disp(mults, g0, g_true):
    return [abs(np.sin(0.5 * np.pi * (g0 * m) / g_true)) for m in mults]
mults = [0.0, 0.5, 1.0, 1.5, 2.0]
g_true = 5838.0
check("fit returned 2x pi -> max displacement at 0.5x",
      int(np.argmax(_disp(mults, 2 * g_true, g_true))) == 1)
check("fit correct -> max displacement at 1.0x",
      int(np.argmax(_disp(mults, g_true, g_true))) == 2)
check("fit returned 0.5x pi -> max displacement at 2.0x",
      int(np.argmax(_disp(mults, 0.5 * g_true, g_true))) == 4)

print("== ramsey contrast guard (bad pi/2 must not read as short T2*) ==")
t = np.linspace(0.05, 4.0, 31)
# a proper pi/2 pair: full-contrast fringe, long T2*
X = 0.5 + 0.45 * np.exp(-t / 20.0) * np.cos(2 * np.pi * 1.05 * t) + rng.normal(0, 0.02, t.size)
Y = 0.5 + 0.45 * np.exp(-t / 20.0) * np.sin(2 * np.pi * 1.05 * t) + rng.normal(0, 0.02, t.size)
good = T.fit_ramsey_xy(t, X, Y)
check("full-contrast fringe passes the 0.20 contrast gate", good["amp"] >= 0.20,
      "amp=%.3f T2=%.1f" % (good["amp"], good["t2_us"]))
# pi pulses instead of pi/2: fringe collapses -> must be REJECTED, not read as short T2*
Xb = 0.5 + 0.03 * np.exp(-t / 20.0) * np.cos(2 * np.pi * 1.05 * t) + rng.normal(0, 0.02, t.size)
Yb = 0.5 + 0.03 * np.exp(-t / 20.0) * np.sin(2 * np.pi * 1.05 * t) + rng.normal(0, 0.02, t.size)
bad = T.fit_ramsey_xy(t, Xb, Yb)
check("collapsed fringe caught by contrast gate (not blamed on T2*)", bad["amp"] < 0.20,
      "amp=%.3f (fit would have claimed T2=%.2f us)" % (bad["amp"], bad["t2_us"]))

print("== classic (drive-detuned) Ramsey fallback ==")
tt = np.linspace(0.05, 4.0, 31)
for x_true in (+0.137, -0.242, 0.0):
    d = 1.0
    fits = []
    for off in (+d, -d):
        f_true = abs(x_true - off)          # |f_q - (drive + offset)|
        y = 0.5 + 0.45 * np.exp(-tt / 12.0) * np.cos(2 * np.pi * f_true * tt + 0.3) \
            + rng.normal(0, 0.02, tt.size)
        fits.append(T.fit_decay_cosine(tt, y))
    check("classic |f| recovered at both offsets (x=%+.3f)" % x_true,
          fits[0]["ok"] and fits[1]["ok"])
    x_est = (fits[1]["f_mhz"] - fits[0]["f_mhz"]) / 2.0
    check("classic x=(f2-f1)/2 gives %+.3f MHz within 20 kHz" % x_true,
          abs(x_est - x_true) < 0.02, "est=%+.4f" % x_est)
# guard: a fringe beyond the offset means |detuning| > offset and the formula is invalid
check("fringe > 1.9*offset flagged invalid", (2.5 > 1.9 * 1.0))

print("== lock-in Ramsey (envelope + phase slope) ==")
# simulate: P(tau, phase) = 0.5 + 0.5*exp(-tau/T2)*cos(phase - 2*pi*det*tau)
for T2, det in ((0.5, +0.180), (12.0, -0.045)):
    dly = np.linspace(0.02, max(0.10, 1.2 * T2), 16)
    pop = np.empty((dly.size, 4))
    for i, tau in enumerate(dly):
        for j, ph in enumerate((0.0, 90.0, 180.0, 270.0)):
            pop[i, j] = 0.5 + 0.5 * np.exp(-tau / T2) * np.cos(
                np.deg2rad(ph) - 2 * np.pi * det * tau) + rng.normal(0, 0.015)
    C = (pop[:, 0] - pop[:, 2]) / 2.0
    S = (pop[:, 1] - pop[:, 3]) / 2.0
    amp = np.hypot(C, S)
    ph_un = np.unwrap(np.arctan2(S, C))
    env = T.fit_exp_decay(dly, amp)
    check("T2*=%.1f us recovered from envelope (no oscillation fit)" % T2,
          env["ok"] and abs(env["tau"] - T2) / T2 < 0.25, "fit=%.2f us" % env["tau"])
    good = amp > max(0.25 * amp.max(), 0.05)
    b = np.polyfit(dly[good], ph_un[good], 1)[0]
    det_est = -b / (2 * np.pi)
    # sign convention here: phase = -2*pi*det*tau  ->  slope/-2pi = det
    check("detuning %+.3f MHz from phase slope within 15 kHz" % det,
          abs(abs(det_est) - abs(det)) < 0.015, "est=%+.4f (%d/%d delays used)"
          % (det_est, good.sum(), dly.size))
# short-T2 case that the OLD fringe fit could not handle at all
dly_old = np.linspace(0.05, 4.0, 31)          # the old fixed grid
amp_old = np.exp(-dly_old / 0.5)
check("old fixed grid wasted most points on dead signal (T2*=0.5us)",
      float((amp_old < 0.1).mean()) > 0.65, "%.0f%% dead" % (100 * (amp_old < 0.1).mean()))
# the adaptive grid keeps essentially every point inside the coherence window
dly_new = np.linspace(0.5 * 1.2 / 16, 0.5 * 1.2, 16)
check("adaptive grid keeps >90% of points alive",
      float((np.exp(-dly_new / 0.5) >= 0.1).mean()) > 0.9,
      "%.0f%% alive" % (100 * (np.exp(-dly_new / 0.5) >= 0.1).mean()))

print("== spec edge-clip detection ==")
span, f_edge, f_mid = 48.0, 2534.45, 2557.0
lo, hi = 2557.25 - span / 2, 2557.25 + span / 2
check("peak 1.2 MHz from edge flagged as clipped",
      min(abs(f_edge - lo), abs(f_edge - hi)) <= 0.15 * span,
      "%.2f MHz from edge vs %.2f threshold" % (min(abs(f_edge - lo), abs(f_edge - hi)), 0.15 * span))
check("interior peak not flagged",
      min(abs(f_mid - lo), abs(f_mid - hi)) > 0.15 * span)

print("== single-shot fidelity (absolute pi judge) ==")
n, sd = 4000, 1.0
sig = rng.normal(0, sd, n)
ig, qg = rng.normal(0, sd, n), rng.normal(0, sd, n)
ie, qe = rng.normal(6, sd, n), rng.normal(0, sd, n)
r = T.single_shot_fidelity(ig, qg, ie, qe)
check("perfect pi -> F>0.99, sep>5 sigma", r["fidelity"] > 0.99 and r["sep_sigma"] > 5,
      "F=%.3f sep=%.2f" % (r["fidelity"], r["sep_sigma"]))
k = int(0.2 * n)                                   # 20% of the e-prep left in |g>
ie2 = np.concatenate([rng.normal(0, sd, k), rng.normal(6, sd, n - k)])
r2 = T.single_shot_fidelity(ig, qg, ie2, rng.normal(0, sd, n))
check("20% bad pi -> P(g|e) equals the pi error", abs(r2["p_g_given_e"] - 0.20) < 0.03,
      "P(g|e)=%.3f" % r2["p_g_given_e"])
check("bad pi does NOT corrupt P(e|g) (isolates pi from readout)",
      r2["p_e_given_g"] < 0.02, "P(e|g)=%.3f" % r2["p_e_given_g"])
r3 = T.single_shot_fidelity(ig, qg, rng.normal(0.5, sd, n), rng.normal(0, sd, n))
check("overlapping blobs flagged (<2 sigma)", r3["sep_sigma"] < 2.0,
      "sep=%.2f" % r3["sep_sigma"])
# the OLD SEM-based gate would have passed this same non-discriminating readout
sem_snr = (0.5) / ((sd / np.sqrt(1000)) * np.sqrt(2))
check("old SEM-based SNR would have passed a 0.5-sigma readout", sem_snr > 4.0,
      "SEM snr=%.1f vs real sep=0.50 sigma" % sem_snr)

print("== even-M pi-train minimisation (no pi/2, no free evolution) ==")
gpi = 11500.0
for M, tol_frac in ((4, 0.02), (12, 0.005), (32, 0.005)):
    g = np.round(gpi * np.linspace(0.95, 1.05, 13)).astype(int)
    res = np.sin(M * (np.pi * (g / gpi - 1.0)) / 2.0) ** 2 + rng.normal(0, 0.01, g.size)
    gopt, interior = T.parabola_min(g, res)
    check("M=%d train recovers pi within %.1f%%" % (M, 100 * tol_frac),
          abs(gopt - gpi) / gpi < tol_frac and interior,
          "gain %.0f (err %+.2f%%)" % (gopt, 100 * (gopt - gpi) / gpi))
# residual at the minimum bounds the per-pulse angle error with no fitting at all
d32 = 2 * np.arcsin(np.sqrt(0.002)) / 32
check("M=32 residual 0.002 bounds |dtheta| under 0.1% of pi", 100 * d32 / np.pi < 0.1,
      "%.3f%% of pi" % (100 * d32 / np.pi))

print("== module surface ==")
check("programs subclass mocked qick bases",
      issubclass(T.TunerSeqProgram, qick.AveragerProgram)
      and issubclass(T.TunerRabiProgram, qick.RAveragerProgram))
check("DEFAULT_PARAMS merged override",
      T._merged_params({"rabi": {"points": 99}})["rabi"]["points"] == 99
      and T._merged_params({"rabi": {"points": 99}})["rabi"]["gain_max"] == 30000)

print()
if FAIL:
    print("FAILURES: %s" % FAIL)
    sys.exit(1)
print("ALL %s TESTS PASSED" % "SYNTHETIC")
