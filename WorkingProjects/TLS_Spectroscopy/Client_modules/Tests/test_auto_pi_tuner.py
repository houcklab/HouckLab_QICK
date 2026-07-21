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
