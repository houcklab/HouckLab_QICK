"""
Hardware-free deterministic tests for the Modified-Ramsey charge-parity
switching analysis (analyze_ModifiedRamseyParity.py) and the pure planning
helpers in mModifiedRamsey.py.

Everything here is seeded and offline: no RFSoC, no Pyro4, no instruments.
Timing checks that need real clock domains stay in
verify_ModifiedRamsey_timing.py (hardware-in-the-loop companion).

Run from the repo root:
    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.test_ModifiedRamseyParity_offline
or directly:
    python WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/test_ModifiedRamseyParity_offline.py
"""
import math
import os
import sys

import numpy as np

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 5))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ModifiedRamseyParity import (  # noqa: E402
    assess_parity_record,
    autocorrelation_rate_estimate,
    calibrate_readout_from_labeled_shots,
    compare_parity_controls,
    fit_two_state_hmm,
    hmm_forward_backward,
    hmm_viterbi,
    project_iq_trace,
    psd_rate_estimate,
    rate_vs_bin_size,
    remove_slow_drift,
    reset_success_vs_cycle,
    simulate_telegraph_trace,
    transition_matrix_2state,
    analyze_modified_ramsey_record,
)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    ok = bool(ok)
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f"\n         {detail}" if detail else ""))
    return ok


def close(a, b, rel):
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= rel * abs(b)


# ---------------------------------------------------------------------------
# 1. expm(Q*dt) convention
# ---------------------------------------------------------------------------

def test_transition_matrix():
    print("\n=== 1. transition_matrix_2state == scipy expm(Q*dt) ===")
    from scipy.linalg import expm
    ok = True
    for g01, g10, dt in [(400.0, 400.0, 20e-6), (150.0, 900.0, 5e-6),
                         (1e4, 3.0, 1e-3), (0.0, 0.0, 1e-3),
                         (250.0, 250.0, 2.5e-3)]:
        Q = np.array([[-g01, g01], [g10, -g10]])
        P_ref = expm(Q * dt)
        P = transition_matrix_2state(g01, g10, dt)
        ok &= check(
            f"expm match g01={g01}, g10={g10}, dt={dt}",
            np.allclose(P, P_ref, atol=1e-12),
            f"max err {np.max(np.abs(P - P_ref)):.2e}",
        )
        ok &= check(f"rows sum to 1 (g01={g01}, g10={g10})",
                    np.allclose(P.sum(axis=1), 1.0, atol=1e-12))
    return ok


# ---------------------------------------------------------------------------
# 2. Readout calibration: contrast vs assignment fidelity
# ---------------------------------------------------------------------------

def test_calibration():
    print("\n=== 2. Readout calibration from labeled shots ===")
    rng = np.random.default_rng(7)
    n = 20000
    d = 4.0  # separation in units of sigma=1 -> P(correct) = Phi(2) = 0.97725
    Ig = rng.normal(0.0, 1.0, n); Qg = rng.normal(0.0, 1.0, n)
    Ie = rng.normal(d, 1.0, n);   Qe = rng.normal(0.0, 1.0, n)
    cal = calibrate_readout_from_labeled_shots(Ig, Qg, Ie, Qe)

    from scipy.stats import norm as norm_dist
    p_correct = norm_dist.cdf(d / 2.0)
    contrast_true = 2 * p_correct - 1

    ok = check("contrast == max|CDF_g - CDF_e| ~= 2*Phi(d/2)-1",
               abs(cal["contrast"] - contrast_true) < 0.01,
               f"got {cal['contrast']:.4f}, analytic {contrast_true:.4f}")
    ok &= check("assignment fidelity == (1 + contrast)/2 EXACTLY",
                cal["assignment_fidelity"] == 0.5 * (1 + cal["contrast"]))
    ok &= check("max_cdf_gap is the same quantity as contrast (legacy "
                "'Fidelity = xx%' figure)",
                cal["max_cdf_gap"] == cal["contrast"])
    ok &= check("threshold near the midpoint", abs(cal["threshold"]) < 0.15,
                f"threshold {cal['threshold']:.3f}")
    ok &= check("confusion-matrix diagonal ~= Phi(d/2)",
                abs(cal["confusion_matrix"][0, 0] - p_correct) < 0.01
                and abs(cal["confusion_matrix"][1, 1] - p_correct) < 0.01,
                f"diag {cal['confusion_matrix'][0,0]:.4f}, "
                f"{cal['confusion_matrix'][1,1]:.4f}")
    ok &= check("analog SNR ~= d/sigma", close(cal["snr_analog"], d, 0.05),
                f"snr {cal['snr_analog']:.3f}")
    ok &= check("axis points g -> e along +I",
                cal["axis"][0] > 0.99 and abs(cal["axis"][1]) < 0.1)
    ok &= check("covariances ~ identity",
                np.allclose(cal["cov_g"], np.eye(2), atol=0.05)
                and np.allclose(cal["cov_e"], np.eye(2), atol=0.05))

    # Zero contrast: overlapping clouds must warn.
    Ie0 = rng.normal(0.0, 1.0, n); Qe0 = rng.normal(0.05, 1.0, n)
    cal0 = calibrate_readout_from_labeled_shots(Ig, Qg, Ie0, Qe0)
    ok &= check("overlapping clouds -> low contrast + warnings",
                cal0["contrast"] < 0.1 and len(cal0["warnings"]) > 0,
                f"contrast {cal0['contrast']:.3f}")
    return ok


def _make_cal(mu_g, mu_e, sigma, seed=11, n=8000):
    """Calibration object from synthetic labeled clouds along I."""
    rng = np.random.default_rng(seed)
    Ig = rng.normal(mu_g, sigma, n); Qg = rng.normal(0, sigma, n)
    Ie = rng.normal(mu_e, sigma, n); Qe = rng.normal(0, sigma, n)
    return calibrate_readout_from_labeled_shots(Ig, Qg, Ie, Qe)


# ---------------------------------------------------------------------------
# 3. HMM rate recovery
# ---------------------------------------------------------------------------

def test_hmm_symmetric_strong():
    print("\n=== 3. HMM: strong contrast, symmetric switching ===")
    gamma = 400.0
    dt = 20e-6
    n = 30000
    sim = simulate_telegraph_trace(n, dt, gamma, gamma, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=1)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True)
    ok = check("identifiable", fit["identifiable"],
               "; ".join(fit["unidentifiable_reasons"]))
    ok &= check("gamma within 15%", close(fit["gamma01_hz"], gamma, 0.15),
                f"fit {fit['gamma01_hz']:.1f} Hz vs true {gamma} Hz "
                f"(err {fit['gamma01_err_hz']:.1f})")
    ok &= check("Hessian error is finite and sane",
                math.isfinite(fit["gamma01_err_hz"])
                and 0 < fit["gamma01_err_hz"] < gamma,
                f"err {fit['gamma01_err_hz']:.1f} Hz")
    ok &= check("occupancy ~ 50/50",
                abs(fit["occupancy"][1] - 0.5) < 0.1,
                f"occ1 {fit['occupancy'][1]:.3f}")
    ok &= check("posteriors confident", fit["posterior_ambiguity"] < 0.15,
                f"ambiguity {fit['posterior_ambiguity']:.3f}")
    # Viterbi vs truth
    agree = np.mean(fit["viterbi_path"] == sim["states"])
    ok &= check("Viterbi matches true states > 90%", agree > 0.90,
                f"agreement {agree:.3f}")
    return ok


def test_hmm_asymmetric():
    print("\n=== 4. HMM: asymmetric switching ===")
    g01, g10 = 150.0, 450.0
    dt = 20e-6
    n = 30000
    sim = simulate_telegraph_trace(n, dt, g01, g10, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=2)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=False)
    ok = check("identifiable", fit["identifiable"],
               "; ".join(fit["unidentifiable_reasons"]))
    ok &= check("gamma01 within 30%", close(fit["gamma01_hz"], g01, 0.30),
                f"fit {fit['gamma01_hz']:.1f} vs {g01}")
    ok &= check("gamma10 within 30%", close(fit["gamma10_hz"], g10, 0.30),
                f"fit {fit['gamma10_hz']:.1f} vs {g10}")
    ok &= check("occupancy(state1) ~ g01/(g01+g10) = 0.25",
                abs(fit["occupancy"][1] - 0.25) < 0.08,
                f"occ1 {fit['occupancy'][1]:.3f}")
    return ok


def test_hmm_moderate_contrast():
    print("\n=== 5. HMM: moderate contrast ===")
    gamma = 300.0
    dt = 20e-6
    n = 40000
    sim = simulate_telegraph_trace(n, dt, gamma, gamma, mu0=0.0, mu1=1.5,
                                   sigma0=1.0, sigma1=1.0, seed=3)
    em = {"mu0": 0.0, "mu1": 1.5, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True)
    ok = check("identifiable at SNR 1.5", fit["identifiable"],
               "; ".join(fit["unidentifiable_reasons"]))
    ok &= check("gamma within 35%", close(fit["gamma01_hz"], gamma, 0.35),
                f"fit {fit['gamma01_hz']:.1f} vs {gamma}")
    ok &= check("ambiguity reported and sane",
                0.0 <= fit["posterior_ambiguity"] <= 0.5,
                f"ambiguity {fit['posterior_ambiguity']:.3f}")

    # Fast switching (dwell ~2.5 samples) at SNR 1: temporal smoothing cannot
    # disambiguate individual samples, so the posterior-ambiguity warning must
    # fire even though the RATE is still recoverable.
    sim_lo = simulate_telegraph_trace(20000, 100e-6, 4000.0, 4000.0, mu0=0.0,
                                      mu1=1.0, sigma0=1.0, sigma1=1.0, seed=30)
    em_lo = {"mu0": 0.0, "mu1": 1.0, "sigma0": 1.0, "sigma1": 1.0}
    fit_lo = fit_two_state_hmm(sim_lo["v"], 100e-6, em_lo, symmetric=True,
                               min_emission_snr=0.1)
    ok &= check("posterior-ambiguity warning fires when smoothing cannot "
                "disambiguate",
                any("posterior ambiguity" in w for w in fit_lo["warnings"]),
                f"ambiguity {fit_lo['posterior_ambiguity']:.3f}")
    return ok


def test_hmm_zero_contrast():
    print("\n=== 6. HMM: zero contrast -> unidentifiable ===")
    rng = np.random.default_rng(4)
    v = rng.normal(0.0, 1.0, 20000)
    em = {"mu0": 0.0, "mu1": 0.0 + 1e-6, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(v, 20e-6, em, symmetric=True)
    ok = check("zero contrast -> identifiable=False", not fit["identifiable"])
    ok &= check("rates withheld (nan)", math.isnan(fit["gamma01_hz"]))
    ok &= check("reason names emission separation",
                any("emission separation" in r
                    for r in fit["unidentifiable_reasons"]),
                str(fit["unidentifiable_reasons"]))
    return ok


def test_hmm_label_permutation():
    print("\n=== 7. HMM: state-label permutation ===")
    g01, g10 = 200.0, 500.0
    dt = 20e-6
    n = 25000
    sim = simulate_telegraph_trace(n, dt, g01, g10, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=5)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    em_swap = {"mu0": 3.0, "mu1": 0.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=False)
    fit_s = fit_two_state_hmm(sim["v"], dt, em_swap, symmetric=False)
    ok = check("both fits identifiable",
               fit["identifiable"] and fit_s["identifiable"])
    ok &= check("gamma01 <-> gamma10 swap under label permutation",
                close(fit_s["gamma01_hz"], fit["gamma10_hz"], 0.15)
                and close(fit_s["gamma10_hz"], fit["gamma01_hz"], 0.15),
                f"orig ({fit['gamma01_hz']:.0f}, {fit['gamma10_hz']:.0f}) "
                f"swapped ({fit_s['gamma01_hz']:.0f}, {fit_s['gamma10_hz']:.0f})")
    ok &= check("posteriors swap columns",
                np.allclose(fit["posteriors"][:, 0], fit_s["posteriors"][:, 1],
                            atol=0.05))
    ok &= check("occupancies mirror",
                abs(fit["occupancy"][1] - fit_s["occupancy"][0]) < 0.05)
    return ok


def test_hmm_missing_samples():
    print("\n=== 8. HMM: missing samples (non-uniform dt) ===")
    gamma = 400.0
    dt0 = 20e-6
    n_full = 30000
    sim = simulate_telegraph_trace(n_full, dt0, gamma, gamma, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=6)
    rng = np.random.default_rng(60)
    keep = np.sort(rng.choice(n_full, size=int(0.9 * n_full), replace=False))
    v = sim["v"][keep]
    t = sim["t_s"][keep]
    dt_steps = np.diff(t)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(v, dt_steps, em, symmetric=True)
    ok = check("identifiable with 10% samples missing", fit["identifiable"],
               "; ".join(fit["unidentifiable_reasons"]))
    ok &= check("gamma within 20% despite gaps",
                close(fit["gamma01_hz"], gamma, 0.20),
                f"fit {fit['gamma01_hz']:.1f} vs {gamma}")
    return ok


def test_hmm_few_and_no_switches():
    print("\n=== 9. HMM: few-switch and no-switch records ===")
    dt = 20e-6
    n = 20000  # 0.4 s
    sim = simulate_telegraph_trace(n, dt, 5.0, 5.0, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=8)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True)
    ok = check("few-switch record -> unidentifiable", not fit["identifiable"])
    ok &= check("reason names transition count",
                any("transitions" in r for r in fit["unidentifiable_reasons"]),
                str(fit["unidentifiable_reasons"]))

    rng = np.random.default_rng(9)
    v0 = rng.normal(0.0, 1.0, n)  # never leaves state 0
    fit0 = fit_two_state_hmm(v0, dt, em, symmetric=True)
    ok &= check("no-switch record -> unidentifiable", not fit0["identifiable"],
                str(fit0["unidentifiable_reasons"]))
    ok &= check("no-switch rates withheld", math.isnan(fit0["gamma01_hz"]))
    return ok


def test_hmm_bootstrap():
    print("\n=== 10. HMM: parametric bootstrap CI path ===")
    gamma = 500.0
    dt = 20e-6
    sim = simulate_telegraph_trace(8000, dt, gamma, gamma, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=10)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True, n_boot=8, seed=42)
    ci = fit["gamma_boot_ci"]
    ok = check("bootstrap CI produced", ci is not None and ci["n_boot"] == 8)
    if ci:
        p16, p84 = ci["gamma01_hz"]["p16"], ci["gamma01_hz"]["p84"]
        ok &= check("CI brackets are ordered and near the fit",
                    p16 < ci["gamma01_hz"]["p50"] < p84
                    and p16 < fit["gamma01_hz"] * 1.5
                    and p84 > fit["gamma01_hz"] * 0.5,
                    f"p16={p16:.0f}, p50={ci['gamma01_hz']['p50']:.0f}, "
                    f"p84={p84:.0f}, fit={fit['gamma01_hz']:.0f}")
    # Determinism: same seed, same CI.
    fit2 = fit_two_state_hmm(sim["v"], dt, em, symmetric=True, n_boot=8, seed=42)
    ok &= check("bootstrap deterministic under fixed seed",
                fit2["gamma_boot_ci"]["gamma01_hz"]["p50"]
                == ci["gamma01_hz"]["p50"])
    return ok


# ---------------------------------------------------------------------------
# 4. tau_dwell / tau_corr / f_corner conventions
# ---------------------------------------------------------------------------

def test_rate_conventions():
    print("\n=== 11. Rate conventions: dwell, autocorrelation, PSD ===")
    gamma = 250.0          # per-state switch rate
    dt = 20e-6
    n = 200000             # 4 s record, ~2000 switches: tight statistics
    sim = simulate_telegraph_trace(n, dt, gamma, gamma, mu0=-1.0, mu1=1.0,
                                   sigma0=0.05, sigma1=0.05, seed=12)

    # tau_dwell = 1/gamma from the true state path
    states = sim["states"]
    edges = np.flatnonzero(np.diff(states)) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [n]])
    dwells = (ends - starts)[1:-1] * dt  # drop censored first/last runs
    ok = check("mean dwell ~= 1/gamma",
               close(float(np.mean(dwells)), 1.0 / gamma, 0.10),
               f"mean dwell {np.mean(dwells)*1e3:.3f} ms vs "
               f"1/gamma = {1e3/gamma:.3f} ms")

    acf = autocorrelation_rate_estimate(sim["v"], dt)
    ok &= check("acf fit ok", acf["fit_ok"], "; ".join(acf["warnings"]))
    ok &= check("tau_corr ~= 1/(2*gamma)",
                close(acf["tau_corr_s"], 1.0 / (2 * gamma), 0.15),
                f"tau_corr {acf['tau_corr_s']*1e3:.3f} ms vs "
                f"{1e3/(2*gamma):.3f} ms")
    ok &= check("acf gamma ~= gamma", close(acf["gamma_hz"], gamma, 0.15),
                f"acf gamma {acf['gamma_hz']:.1f} Hz")

    psd = psd_rate_estimate(sim["v"], dt)
    ok &= check("psd fit ok", psd["fit_ok"], "; ".join(psd["warnings"]))
    ok &= check("f_corner ~= gamma/pi",
                close(psd["f_corner_hz"], gamma / math.pi, 0.25),
                f"f_corner {psd['f_corner_hz']:.1f} Hz vs "
                f"gamma/pi = {gamma/math.pi:.1f} Hz")
    ok &= check("psd gamma ~= gamma", close(psd["gamma_hz"], gamma, 0.25),
                f"psd gamma {psd['gamma_hz']:.1f} Hz")
    return ok


# ---------------------------------------------------------------------------
# 5. Drift removal
# ---------------------------------------------------------------------------

def test_drift():
    print("\n=== 12. Slow-drift removal ===")
    gamma = 400.0
    dt = 20e-6
    n = 50000  # 1 s
    t = np.arange(n) * dt
    drift_true = 2.5 * (t / t[-1])  # linear ramp comparable to the separation
    sim = simulate_telegraph_trace(n, dt, gamma, gamma, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=13,
                                   drift=drift_true)
    out = remove_slow_drift(sim["v"], dt, drift_timescale_s=0.1,
                            expected_dwell_s=1.0 / gamma)
    ok = check("original trace preserved untouched",
               np.array_equal(out["v_original"], sim["v"]))
    ok &= check("drift window flagged safe (40x dwell)", out["safe"])
    # The rolling mean carries the ramp plus telegraph occupancy fluctuation
    # (~separation/(2*sqrt(N_dwells)) per window) and boundary effects, so the
    # detected span brackets the 2.5 ramp loosely.
    ok &= check("drift span detected ~ ramp amplitude",
                1.5 < out["drift_span"] < 4.5,
                f"span {out['drift_span']:.2f} vs ramp 2.5")

    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    # Center the corrected trace back on the calibrated emission midpoint
    # (drift removal preserves DC = mean of drift, which includes the ramp).
    v_corr = out["v_corrected"] - out["v_corrected"].mean() + 1.5
    fit = fit_two_state_hmm(v_corr, dt, em, symmetric=True)
    ok &= check("rate recovered after drift removal",
                fit["identifiable"] and close(fit["gamma01_hz"], gamma, 0.25),
                f"fit {fit['gamma01_hz']:.1f} vs {gamma}")

    out_short = remove_slow_drift(sim["v"], dt, drift_timescale_s=0.01,
                                  expected_dwell_s=2.5e-3)
    ok &= check("too-short drift window flagged unsafe with warning",
                not out_short["safe"] and out_short["warnings"])
    return ok


# ---------------------------------------------------------------------------
# 6. Controls: final-pulse sign reversal and echo null
# ---------------------------------------------------------------------------

def _analyzed(v, dt, em, label, control_type=None):
    fit = fit_two_state_hmm(v, dt, em, symmetric=False)
    acf = autocorrelation_rate_estimate(v, dt)
    occ1 = float(fit["occupancy"][1]) if fit["posteriors"] is not None \
        else float("nan")
    d = {"label": label, "hmm": fit, "acf": acf, "occupancy_state1": occ1}
    if control_type:
        d["control_type"] = control_type
    return d


def test_controls():
    print("\n=== 13. Controls: flip reversal and echo null ===")
    g01, g10 = 150.0, 450.0    # asymmetric so the mapping inversion is visible
    dt = 20e-6
    n = 30000
    sim = simulate_telegraph_trace(n, dt, g01, g10, mu0=0.0, mu1=3.0,
                                   sigma0=1.0, sigma1=1.0, seed=14)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}

    # flip_final_pi2 swaps which parity branch maps to which readout cloud:
    # the SAME parity trajectory now emits with the means exchanged.
    rng = np.random.default_rng(15)
    mu_flip = np.where(sim["states"] == 0, 3.0, 0.0)
    v_flip = mu_flip + rng.standard_normal(n)

    main = _analyzed(sim["v"], dt, em, "parity")
    flip = _analyzed(v_flip, dt, em, "flip", control_type="flip_final_pi2")

    # echo null: parity contrast destroyed -> emission collapses to one level.
    rng2 = np.random.default_rng(16)
    v_echo = 1.5 + rng2.standard_normal(n)
    echo = _analyzed(v_echo, dt, em, "echo", control_type="use_pi_pulse")
    echo["control_type"] = "echo_null"

    cmp_out = compare_parity_controls(main, [flip, echo])
    by_type = {c["control_type"]: c for c in cmp_out["controls"]}
    ok = check("flip control: telegraph survives with inverted mapping",
               by_type["flip_final_pi2"]["checked"] is True,
               by_type["flip_final_pi2"]["note"])
    ok &= check("occupancy actually inverted",
                abs(main["occupancy_state1"]
                    + flip["occupancy_state1"] - 1.0) < 0.1,
                f"main occ1 {main['occupancy_state1']:.2f}, "
                f"flip occ1 {flip['occupancy_state1']:.2f}")
    ok &= check("echo null: parity contrast suppressed",
                by_type["echo_null"]["checked"] is True,
                by_type["echo_null"]["note"])
    ok &= check("all controls behave as expected", cmp_out["all_expected"])
    ok &= check("echo-null HMM is itself unidentifiable",
                not echo["hmm"]["identifiable"],
                str(echo["hmm"]["unidentifiable_reasons"]))
    return ok


# ---------------------------------------------------------------------------
# 7. Pure planning helpers (tau + mapping conventions, control variants)
# ---------------------------------------------------------------------------

def test_planning_helpers():
    print("\n=== 14. plan_parity_mapping / build_control_variants ===")
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mModifiedRamsey import (
        MR_CONTROL_TYPE_CODES,
        build_control_variants,
        plan_parity_mapping,
    )
    ok = True
    p = plan_parity_mapping(0.5, 0.1)
    ok &= check("tau = 1/(2*df)", p["tau_us"] == 1.0, f"tau {p['tau_us']}")
    ok &= check("gap = tau - 4*sigma (no pi)",
                abs(p["gap_us"] - (1.0 - 0.4)) < 1e-12,
                f"gap {p['gap_us']}")
    ok &= check("standard final pi/2 phase 180 deg",
                p["final_pi2_phase_deg"] == 180)
    ok &= check("feasible at df=0.5, sigma=0.1", p["feasible"],
                str(p["errors"]))

    p_echo = plan_parity_mapping(0.5, 0.1, use_pi_pulse=True)
    ok &= check("echo gap = (tau - 8*sigma)/2",
                abs(p_echo["gap_us"] - (1.0 - 0.8) / 2) < 1e-12,
                f"gap {p_echo['gap_us']}")
    ok &= check("echo warns it is a null control",
                any("null" in w.lower() for w in p_echo["warnings"]))

    p_flip = plan_parity_mapping(0.5, 0.1, flip_final_pi2=True)
    ok &= check("flip final pi/2 phase 0 deg", p_flip["final_pi2_phase_deg"] == 0)
    p_sym = plan_parity_mapping(0.5, 0.1, symmetric_ramsey=True)
    ok &= check("symmetric final pi/2 phase 90 deg",
                p_sym["final_pi2_phase_deg"] == 90)
    p_symflip = plan_parity_mapping(0.5, 0.1, symmetric_ramsey=True,
                                    flip_final_pi2=True)
    ok &= check("symmetric+flip phase 270 deg",
                p_symflip["final_pi2_phase_deg"] == 270)
    ok &= check("symmetric drive offset = -df/2",
                p_sym["drive_freq_offset_mhz"] == -0.25)
    ok &= check("symmetric halves the branch detuning",
                p_sym["branch_detuning_mhz"] == 0.25
                and p["branch_detuning_mhz"] == 0.5)

    p_bad = plan_parity_mapping(2.0, 0.1)  # tau=0.25 us < 4*sigma=0.4 us
    ok &= check("unreachable df -> infeasible with error",
                not p_bad["feasible"] and p_bad["errors"],
                p_bad["errors"][0][:90] if p_bad["errors"] else "")
    ok &= check("df_max = 1/(8*sigma) (no pi)",
                abs(p_bad["df_max_mhz"] - 1.0 / 0.8) < 1e-12)

    # Bandwidth-marginal standard scheme recommends symmetric.
    p_marg = plan_parity_mapping(0.5, 0.5)  # rabi ~0.2 MHz, ratio ~2.5 > 1
    ok &= check("bandwidth-infeasible standard scheme fails and suggests "
                "symmetric",
                not p_marg["feasible"] and p_marg["recommend_symmetric"]
                and any("symmetric" in e for e in p_marg["errors"]))

    base = {"f_ge": 3055.2, "df": 0.5, "sigma": 0.1, "pi2_gain": 2375,
            "pi_gain": 4600}
    variants = build_control_variants(base)
    by = {v["control_type"]: v for v in variants}
    ok &= check("all six variants built",
                set(by) == set(MR_CONTROL_TYPE_CODES))
    ok &= check("parity variant unmodified",
                by["parity"]["cfg"]["df"] == 0.5
                and not by["parity"]["cfg"].get("flip_final_pi2", False))
    ok &= check("flip variant sets flip_final_pi2",
                by["flip_final_pi2"]["cfg"]["flip_final_pi2"] is True)
    ok &= check("echo variant sets use_pi_pulse",
                by["echo_null"]["cfg"]["use_pi_pulse"] is True)
    ok &= check("tau_offset scales df -> tau*(1+frac)",
                abs(by["tau_offset"]["cfg"]["df"] - 0.5 / 1.25) < 1e-12)
    ok &= check("detuned variant shifts f_ge by +df",
                abs(by["drive_detuned"]["cfg"]["f_ge"] - 3055.7) < 1e-9)
    ok &= check("drive_off variant zeroes pi2_gain",
                by["drive_off"]["cfg"]["pi2_gain"] == 0)
    ok &= check("every variant stamps mr_control_type",
                all(v["cfg"] is None
                    or v["cfg"]["mr_control_type"] == v["control_type"]
                    for v in variants))
    ok &= check("base cfg not mutated",
                base.get("flip_final_pi2") is None and base["df"] == 0.5)

    # Echo infeasible at large df: returned as skipped, not raised.
    base_tight = dict(base, df=1.0)   # tau=0.5 us, echo needs > 0.8 us
    v_tight = build_control_variants(base_tight, include=("echo_null",))
    ok &= check("infeasible echo variant skipped with reason",
                v_tight[0]["cfg"] is None and v_tight[0]["skip_reason"])
    return ok


# ---------------------------------------------------------------------------
# 8. Reset validation + bin-size stability + end-to-end record
# ---------------------------------------------------------------------------

def test_reset_and_binsize():
    print("\n=== 15. Reset success vs cycle + rate vs bin size ===")
    cal = _make_cal(0.0, 4.0, 1.0, seed=17)
    rng = np.random.default_rng(18)
    n_shots = 4000

    def cloud(p_excited):
        exc = rng.random(n_shots) < p_excited
        I = np.where(exc, rng.normal(4.0, 1.0, n_shots),
                     rng.normal(0.0, 1.0, n_shots))
        Q = rng.normal(0.0, 1.0, n_shots)
        return I, Q

    # Readout k measures the state before flip k: 40% excited thermally,
    # then 5%, then 1% after successive resets.
    rows = [cloud(0.40), cloud(0.05), cloud(0.01)]
    reset_I = np.stack([r[0] for r in rows])
    reset_Q = np.stack([r[1] for r in rows])
    out = reset_success_vs_cycle(reset_I, reset_Q, cal)
    ok = check("g-fraction increases with reset cycle",
               np.all(np.diff(out["g_fraction"]) > 0),
               f"fractions {np.round(out['g_fraction'], 3)}")
    ok &= check("converged flag set", out["converged"])

    bad = reset_success_vs_cycle(reset_I[:1], reset_Q[:1], cal)
    ok &= check("poor initialization flagged",
                not bad["converged"] and bad["warnings"],
                bad["warnings"][0][:80] if bad["warnings"] else "")

    sim = simulate_telegraph_trace(60000, 20e-6, 300.0, 300.0, mu0=0.0,
                                   mu1=3.0, sigma0=1.0, sigma1=1.0, seed=19)
    rvb = rate_vs_bin_size(sim["v"], 20e-6, threshold=1.5,
                           bin_sizes=(1, 2, 4, 8, 16))
    rates = np.array(rvb["rate_hz"])
    ok &= check("bin-size sweep produced finite rates",
                np.all(np.isfinite(rates)), str(np.round(rates, 1)))
    # Raw single-shot threshold crossings include noise flips; after modest
    # binning the rate should settle toward the true total switch rate.
    ok &= check("binned rate settles near true rate (300 Hz total)",
                abs(rates[2] - 300.0) / 300.0 < 0.5,
                f"rate at bin=4: {rates[2]:.1f} Hz")
    return ok


def test_end_to_end():
    print("\n=== 16. End-to-end analyze_modified_ramsey_record ===")
    cal = _make_cal(0.0, 4.0, 1.0, seed=20)
    gamma = 200.0     # 2.5 ms dwell: the documented BFC operating point
    dt = 20e-6
    n = 60000         # 1.2 s
    mu0p, mu1p = cal["proj_g_mean"], cal["proj_e_mean"]
    sim = simulate_telegraph_trace(
        n, dt, gamma, gamma, mu0=mu0p, mu1=mu1p,
        sigma0=cal["proj_g_sigma"], sigma1=cal["proj_e_sigma"], seed=21)
    # Rebuild I/Q from the projected trace so the projection round-trips:
    # v = ((IQ - midpoint) @ axis), place samples along the axis.
    axis = cal["axis"]; mid = cal["midpoint"]
    I = mid[0] + sim["v"] * axis[0]
    Q = mid[1] + sim["v"] * axis[1]

    res = analyze_modified_ramsey_record(
        I, Q, dt, cal, drift_timescale_s=0.2, expected_dwell_s=1.0 / gamma,
        symmetric_hmm=True, out_dir=None, save_plots=False,
        save_sidecars=False)
    s = res["summary"]
    ok = check("identifiable end-to-end", s["identifiable"],
               str(res["hmm"]["unidentifiable_reasons"]))
    ok &= check("gamma within 25% of 200 Hz (2.5 ms dwell)",
                close(s["gamma01_hz"], gamma, 0.25),
                f"HMM {s['gamma01_hz']:.1f} Hz, ACF {s['acf_gamma_hz']:.1f}, "
                f"PSD {s['psd_gamma_hz']:.1f}")
    ok &= check("estimators agree (no disagreement warning)",
                not any("disagree" in w for w in s["warnings"]),
                str(s["warnings"]))
    ok &= check("dwell ~2.5 ms recovered from Viterbi",
                close(res["hmm"]["dwell_mean_s"]["state0"], 1 / gamma, 0.3)
                or close(res["hmm"]["dwell_mean_s"]["state1"], 1 / gamma, 0.3),
                f"dwells {res['hmm']['dwell_mean_s']}")

    # Zero-contrast end-to-end must come out unidentifiable, not with a rate.
    rng = np.random.default_rng(22)
    I0 = mid[0] + rng.normal(0, 1.0, 30000) * axis[0]
    Q0 = mid[1] + rng.normal(0, 1.0, 30000) * axis[1]
    cal0 = _make_cal(0.0, 0.02, 1.0, seed=23)   # overlapping calibration
    res0 = analyze_modified_ramsey_record(
        I0, Q0, dt, cal0, out_dir=None, save_plots=False, save_sidecars=False)
    ok &= check("zero-contrast record -> unidentifiable end-to-end",
                not res0["summary"]["identifiable"]
                and math.isnan(res0["summary"]["gamma01_hz"]))

    gate = assess_parity_record(calibration=cal0, hmm=res0["hmm"],
                                acf=res0["acf"], psd=res0["psd"],
                                drift=res0["drift"])
    ok &= check("quality gates carry the warnings", not gate["clean"])
    return ok


# ---------------------------------------------------------------------------
# 9. Acquisition-side buffer striding and schedule ledger (mocked program)
# ---------------------------------------------------------------------------

def test_program_buffer_and_ledger():
    print("\n=== 18. collect_reset_shots striding + schedule ledger (mock) ===")
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mModifiedRamsey import (
        ModifiedRamseyProgram,
    )
    reps, n_reset = 5, 2
    reads_per_rep = n_reset + 1
    prog = ModifiedRamseyProgram.__new__(ModifiedRamseyProgram)
    prog.cfg = {"ro_chs": [0], "readout_length": 1.0, "reps": reps}
    prog.reset_cycles = n_reset
    prog.reads_per_rep = reads_per_rep
    prog.us2cycles = lambda *a, **k: 10  # norm = 10

    # Buffer layout: rep r contributes [reset0, reset1, final] sequentially.
    # Encode readout k of rep r as 100*r + k so the striding is checkable.
    raw = np.array([100 * r + k for r in range(reps)
                    for k in range(reads_per_rep)], dtype=float)
    prog.di_buf = [raw]
    prog.dq_buf = [raw + 0.5]

    si, sq = prog.collect_shots()
    ok = check("collect_shots keeps only the FINAL readout of each rep",
               np.array_equal(si.ravel() * 10,
                              np.array([2., 102., 202., 302., 402.])))
    ri, rq = prog.collect_reset_shots()
    ok &= check("reset shots shape (reset_cycles, reps)",
                ri.shape == (n_reset, reps) and rq.shape == (n_reset, reps))
    ok &= check("reset row k holds readout k of every rep",
                np.array_equal(ri[0] * 10, np.array([0., 100., 200., 300., 400.]))
                and np.array_equal(ri[1] * 10,
                                   np.array([1., 101., 201., 301., 401.])))

    # No reset: empty (0, reps) arrays.
    prog.reset_cycles = 0
    ri0, _ = prog.collect_reset_shots()
    ok &= check("no-reset reset_shots empty with stable shape",
                ri0.shape == (0, reps))

    # Schedule ledger: synci immediates plus one r_wait sync per Ramsey gap.
    prog.wait_cycles = 37
    prog.prog_list = [
        {"name": "regwi", "args": [0, 3, 37]},
        {"label": "LOOP_J", "name": "synci", "args": [100]},
        {"name": "set", "args": [1, 0, 0, 0, 0, 0, 0, 7]},
        {"name": "sync", "args": [0, 3]},
        {"name": "synci", "args": [250]},
        {"name": "seti", "args": [0, 0, 0, 0]},
        {"name": "synci", "args": [13]},
        {"name": "loopnz", "args": [0, 15, "LOOP_J"]},
        {"name": "synci", "args": [999]},   # outside the rep loop: ignored
    ]
    ok &= check("ledger sums synci + r_wait syncs inside LOOP_J only",
                prog.scheduled_rep_period_cycles() == 100 + 37 + 250 + 13,
                f"got {prog.scheduled_rep_period_cycles()}")
    return ok


def test_forward_backward_consistency():
    print("\n=== 17. Forward/backward internal consistency ===")
    sim = simulate_telegraph_trace(3000, 20e-6, 400.0, 400.0, mu0=0.0,
                                   mu1=3.0, sigma0=1.0, sigma1=1.0, seed=24)
    fb = hmm_forward_backward(sim["v"], np.full(2999, 20e-6), 400.0, 400.0,
                              0.0, 3.0, 1.0, 1.0)
    ok = check("posteriors normalized",
               np.allclose(fb["posteriors"].sum(axis=1), 1.0, atol=1e-9))
    # Likelihood must be invariant to which end the recursion starts from:
    # logsumexp(alpha_t + beta_t) is constant in t.
    lse = np.logaddexp(fb["log_alpha"][:, 0] + fb["log_beta"][:, 0],
                       fb["log_alpha"][:, 1] + fb["log_beta"][:, 1])
    ok &= check("alpha*beta constant across t (stable log-space recursion)",
                np.allclose(lse, fb["loglik"], atol=1e-6),
                f"max dev {np.max(np.abs(lse - fb['loglik'])):.2e}")
    vit = hmm_viterbi(sim["v"], np.full(2999, 20e-6), 400.0, 400.0,
                      0.0, 3.0, 1.0, 1.0)
    agree = np.mean(vit == sim["states"])
    ok &= check("Viterbi ~ truth on clean data", agree > 0.9,
                f"agreement {agree:.3f}")
    return ok


def main():
    tests = [
        test_transition_matrix,
        test_calibration,
        test_hmm_symmetric_strong,
        test_hmm_asymmetric,
        test_hmm_moderate_contrast,
        test_hmm_zero_contrast,
        test_hmm_label_permutation,
        test_hmm_missing_samples,
        test_hmm_few_and_no_switches,
        test_hmm_bootstrap,
        test_rate_conventions,
        test_drift,
        test_controls,
        test_planning_helpers,
        test_reset_and_binsize,
        test_end_to_end,
        test_program_buffer_and_ledger,
        test_forward_backward_consistency,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001 - a crashed test is a failure
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} raised {type(e).__name__}", False, str(e))

    print(f"\n================ {len(PASS)} passed, {len(FAIL)} failed "
          "================")
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
