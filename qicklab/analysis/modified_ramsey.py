"""Offline analysis of Modified-Ramsey charge-parity records: reset checks, control comparisons,
quality gates, plots and the analyze_modified_ramsey_record pipeline. Method and rate conventions:
docs/experiments/modified_ramsey.md#analysis. Tests: tests/test_modified_ramsey_offline.py."""

import json
import math
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")  # B1: stays until its own fix commit (design.md)
import matplotlib.pyplot as plt

from qicklab.analysis.dwell import dwell_time_statistics
from qicklab.analysis.hmm import fit_two_state_hmm
from qicklab.analysis.rates import (
    autocorrelation_rate_estimate,
    psd_rate_estimate,
    rate_vs_bin_size,
    remove_slow_drift,
)
from qicklab.analysis.readout import project_iq_trace


def reset_success_vs_cycle(reset_I, reset_Q, calibration, post_reset_I=None, post_reset_Q=None):
    """Report what the saved active-reset readouts actually establish.

    Reset readout k is acquired before corrective flip k. Consequently row 0
    is the pre-reset population and row k validates only the k corrections
    preceding it. The last corrective flip is not observable unless an
    explicit post-reset verification readout is supplied.
    """
    reset_I = np.atleast_2d(np.asarray(reset_I, dtype=float))
    reset_Q = np.atleast_2d(np.asarray(reset_Q, dtype=float))
    if reset_I.shape != reset_Q.shape:
        raise ValueError("reset_I and reset_Q shapes differ")
    threshold = calibration["threshold"]
    e_above = calibration["e_above_threshold"]

    def ground_fraction(i_values, q_values):
        projected = project_iq_trace(i_values, q_values, calibration)
        ground = projected <= threshold if e_above else projected > threshold
        return float(np.mean(ground))

    pre_correction = np.asarray(
        [ground_fraction(reset_I[k], reset_Q[k]) for k in range(reset_I.shape[0])]
    )
    warnings = []
    final_fraction = float("nan")
    converged = None
    if post_reset_I is not None and post_reset_Q is not None:
        final_fraction = ground_fraction(post_reset_I, post_reset_Q)
        converged = bool(final_fraction > 0.9)
        if not converged:
            warnings.append(
                f"post-reset ground fraction {final_fraction:.3f} <= 0.9: "
                "active reset did not establish reliable initialization"
            )
    else:
        warnings.append(
            "no post-reset verification readout was saved; the final "
            "corrective flip cannot be validated from ModifiedRamsey reset "
            "buffers. Use mActiveResetVerify before trusting initialization"
        )

    return {
        "g_fraction": pre_correction,
        "pre_correction_g_fraction": pre_correction,
        "validated_after_reset_g_fraction": pre_correction[1:],
        "final_ground_fraction": final_fraction,
        "n_cycles": int(reset_I.shape[0]),
        "n_shots": int(reset_I.shape[1]),
        "n_resets_observed": max(0, int(reset_I.shape[0]) - 1),
        "converged": converged,
        "warnings": warnings,
    }


def compare_parity_controls(main_result, control_results):
    """
    Sanity checks between the parity-sensing run and its controls.

    Parameters
    ----------
    main_result : dict
        {"label", "hmm": fit_two_state_hmm output, "acf": autocorrelation
        output, "occupancy_state1": float} for the parity-sensing run.
    control_results : list of dicts
        Same structure plus "control_type" in
        {"flip_final_pi2", "echo_null", "tau_offset", "drive_detuned",
         "drive_off"}.

    Checks applied (each control gets checked=True/False + note):
      flip_final_pi2 : telegraph must SURVIVE (similar amplitude/rate) with
                       the state-occupancy mapping inverted:
                       occ1_flip ~ 1 - occ1_main.
      echo_null      : telegraph must be SUPPRESSED: ACF amplitude < 25% of
                       the main run's, or the HMM must report unidentifiable.
      tau_offset / drive_detuned / drive_off :
                       reduced contrast expected; reported informationally
                       with amplitude ratios.

    Returns dict: {"controls": [...], "all_expected": bool}
    """

    def amp(res):
        a = res.get("acf", {}).get("amplitude", float("nan"))
        return a if (a is not None and math.isfinite(a) and a > 0) else float("nan")

    main_amp = amp(main_result)
    main_occ1 = float(main_result.get("occupancy_state1", float("nan")))
    main_identifiable = bool(main_result.get("hmm", {}).get("identifiable", False))
    main_valid = main_identifiable and math.isfinite(main_amp)
    entries = []
    all_ok = main_valid
    n_decisive_checks = 0
    for ctl in control_results:
        ctype = ctl.get("control_type", "unknown")
        c_amp = amp(ctl)
        ratio = (
            c_amp / main_amp
            if (math.isfinite(c_amp) and math.isfinite(main_amp) and main_amp > 0)
            else float("nan")
        )
        entry = {
            "control_type": ctype,
            "label": ctl.get("label", ctype),
            "amplitude_ratio": ratio,
            "checked": None,
            "note": "",
        }
        if ctype == "flip_final_pi2":
            occ1 = float(ctl.get("occupancy_state1", float("nan")))
            survives = math.isfinite(ratio) and ratio > 0.25
            inverted = (
                math.isfinite(occ1)
                and math.isfinite(main_occ1)
                and abs(occ1 - (1.0 - main_occ1)) < 0.15
            )
            ok = main_valid and survives and inverted
            entry["checked"] = bool(ok)
            entry["note"] = (
                f"amplitude ratio {ratio:.2f} (expect ~1), occupancy(state1) "
                f"{occ1:.2f} vs 1-main={1.0 - main_occ1:.2f} (expect equal)"
            )
        elif ctype == "echo_null":
            hmm_ident = bool(ctl.get("hmm", {}).get("identifiable", False))
            suppressed = math.isfinite(ratio) and ratio < 0.25
            null_evidence = suppressed or (not hmm_ident and main_valid)
            ok = main_valid and null_evidence
            entry["checked"] = bool(ok)
            entry["note"] = (
                f"amplitude ratio {ratio if math.isfinite(ratio) else float('nan'):.2f} "
                "(expect << 1: echo refocuses the static parity detuning)"
            )
        else:
            entry["checked"] = None  # informational only
            entry["note"] = f"amplitude ratio {ratio}"
        if entry["checked"] is not None:
            n_decisive_checks += 1
        if entry["checked"] is False:
            all_ok = False
        entries.append(entry)
    return {"controls": entries, "all_expected": bool(all_ok and n_decisive_checks > 0)}


def assess_parity_record(
    calibration=None,
    hmm=None,
    acf=None,
    psd=None,
    drift=None,
    reset=None,
    estimator_agreement_factor=3.0,
):
    """
    Aggregate quality gates into a warnings list. Never upgrades a result --
    only flags reasons NOT to over-interpret it.
    """
    warnings = []
    for src in (calibration, hmm, acf, psd, drift, reset):
        if src:
            warnings.extend(src.get("warnings", []))
    if hmm and hmm.get("identifiable"):
        rates = [hmm.get("gamma01_hz"), hmm.get("gamma10_hz")]
        alt = []
        for est, name in ((acf, "autocorrelation"), (psd, "PSD")):
            if est and est.get("fit_ok") and math.isfinite(est.get("gamma_hz", float("nan"))):
                alt.append((name, est["gamma_hz"]))
        g_eff = 0.0
        if all(r and math.isfinite(r) and r > 0 for r in rates):
            # For asymmetric rates the ACF/PSD see gamma_eff = (g01+g10)/2.
            g_eff = 0.5 * (rates[0] + rates[1])
        for name, g_alt in alt:
            if g_eff > 0 and (
                g_alt / g_eff > estimator_agreement_factor
                or g_eff / g_alt > estimator_agreement_factor
            ):
                warnings.append(
                    f"HMM effective rate {g_eff:.1f} Hz and {name} rate "
                    f"{g_alt:.1f} Hz disagree by more than "
                    f"{estimator_agreement_factor:g}x: at least one estimator "
                    "is not measuring parity switching"
                )
    return {"warnings": warnings, "clean": not warnings}


def _plot_projected_trace(t_s, v, v_corr, drift, out_path, max_pts=200_000):
    stride = max(1, v.size // max_pts)
    fig, axes = plt.subplots(2, 1, figsize=(11, 5), sharex=True)
    axes[0].plot(t_s[::stride], v[::stride], lw=0.4, label="projected v(t)")
    if drift is not None:
        axes[0].plot(t_s[::stride], drift[::stride], "r-", lw=1.2, label="drift estimate")
    axes[0].set_ylabel("v (raw units)")
    axes[0].legend(loc="best")
    axes[1].plot(t_s[::stride], v_corr[::stride], lw=0.4, color="C2")
    axes[1].set_ylabel("v corrected")
    axes[1].set_xlabel("time (s)")
    fig.suptitle("Projected analog parity trace")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_hmm(t_s, v, hmm, out_path, max_pts=200_000):
    stride = max(1, v.size // max_pts)
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(t_s[::stride], v[::stride], lw=0.4)
    # Reference levels for the two PARITY states. Two emission models reach
    # here and they do not share key names: the plain Gaussian model carries
    # mu0/mu1 directly, while the ge_mixture model (which is what
    # analyze_modified_ramsey_record always builds) carries the calibrated
    # readout clouds mu_g/mu_e plus per-state excited-state probabilities. For
    # the mixture, the level a parity state actually emits at is the
    # probability-weighted mean of the two clouds, not either cloud itself.
    em = hmm["emissions_used"]
    if em.get("model") == "ge_mixture":
        mu_g, mu_e = em["mu_g"], em["mu_e"]
        state_means = (
            (1.0 - em["p_e_state0"]) * mu_g + em["p_e_state0"] * mu_e,
            (1.0 - em["p_e_state1"]) * mu_g + em["p_e_state1"] * mu_e,
        )
        # the underlying g/e clouds, for context
        for mu, lbl in ((mu_g, "readout |g>"), (mu_e, "readout |e>")):
            axes[0].axhline(mu, color="0.6", ls=":", lw=0.8, label=lbl)
        axes[0].legend(loc="best", fontsize="x-small")
    else:
        state_means = (em["mu0"], em["mu1"])
    for mu, c in zip(state_means, ("C0", "C1")):
        axes[0].axhline(mu, color=c, ls="--", lw=1)
    axes[0].set_ylabel("v")
    if hmm["posteriors"] is not None:
        axes[1].plot(t_s[::stride], hmm["posteriors"][::stride, 1], lw=0.5)
        axes[1].set_ylim(-0.05, 1.05)
    axes[1].set_ylabel("P(state1 | data)")
    if hmm["viterbi_path"] is not None:
        axes[2].step(t_s[::stride], hmm["viterbi_path"][::stride], where="post", lw=0.6)
        axes[2].set_ylim(-0.1, 1.1)
    axes[2].set_ylabel("Viterbi state")
    axes[2].set_xlabel("time (s)")
    title = "2-state HMM"
    if hmm["identifiable"]:
        title += f": g01={hmm['gamma01_hz']:.1f} Hz, g10={hmm['gamma10_hz']:.1f} Hz"
    else:
        title += ": UNIDENTIFIABLE (rates withheld)"
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_acf_psd(acf_out, psd_out, out_path):
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(11, 4))
    if acf_out["acf"].size:
        ax0.plot(acf_out["lags_s"] * 1e3, acf_out["acf"], ".-", ms=3)
        if acf_out["fit_ok"]:
            lags = acf_out["lags_s"]
            c0_amp = acf_out["amplitude"] / (
                acf_out["amplitude"] + max(acf_out["noise_variance"], 0.0)
            )
            ax0.plot(
                lags * 1e3,
                c0_amp * np.exp(-lags / acf_out["tau_corr_s"]),
                "r-",
                label=(
                    f"tau_corr={acf_out['tau_corr_s'] * 1e3:.2f} ms -> "
                    f"gamma={acf_out['gamma_hz']:.1f} Hz"
                ),
            )
            ax0.legend()
    ax0.set_xlabel("lag (ms)")
    ax0.set_ylabel("normalized ACF")
    ax0.set_title("Autocorrelation")
    if psd_out["freqs_hz"].size:
        ax1.loglog(psd_out["freqs_hz"], psd_out["psd"], lw=0.7)
        if psd_out["fit_ok"]:
            f = psd_out["freqs_hz"]
            fit = psd_out["s0"] / (1 + (f / psd_out["f_corner_hz"]) ** 2) + psd_out["white_floor"]
            ax1.loglog(
                f,
                fit,
                "r-",
                label=(
                    f"f_c={psd_out['f_corner_hz']:.1f} Hz -> gamma={psd_out['gamma_hz']:.1f} Hz"
                ),
            )
            ax1.legend()
    ax1.set_xlabel("frequency (Hz)")
    ax1.set_ylabel("PSD")
    ax1.set_title("Welch PSD")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_calibration(calibration, out_path):
    fig, ax = plt.subplots(figsize=(6, 6))
    for c, cov, lbl, col in (
        (calibration["g_center"], calibration["cov_g"], "g", "C0"),
        (calibration["e_center"], calibration["cov_e"], "e", "C1"),
    ):
        ax.plot(*c, "x", color=col, ms=12, mew=3, label=f"|{lbl}> center")
        # 1-sigma covariance ellipse
        w, vecs = np.linalg.eigh(cov)
        th = np.linspace(0, 2 * np.pi, 100)
        ell = vecs @ (np.sqrt(np.maximum(w, 0))[:, None] * np.vstack([np.cos(th), np.sin(th)]))
        ax.plot(c[0] + ell[0], c[1] + ell[1], color=col, lw=1)
    mid = calibration["midpoint"]
    axv = calibration["axis"]
    span = calibration["separation"]
    ax.plot(
        [mid[0] - axv[0] * span, mid[0] + axv[0] * span],
        [mid[1] - axv[1] * span, mid[1] + axv[1] * span],
        "k--",
        lw=1,
        label="projection axis",
    )
    ax.set_xlabel("I")
    ax.set_ylabel("Q")
    ax.axis("equal")
    ax.legend()
    ax.set_title(
        f"Readout calibration: SNR={calibration['snr_analog']:.2f}, "
        f"contrast={calibration['contrast']:.3f},\n"
        f"F_assign=(1+C)/2={calibration['assignment_fidelity']:.3f}"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_rate_vs_bin(rvb, out_path):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.semilogx(rvb["bin_us"], rvb["rate_hz"], "o-")
    ax.set_xlabel("bin size (us)")
    ax.set_ylabel("threshold switch rate (Hz)")
    ax.set_title("Rate stability vs visualization bin size")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_dwells(hmm, out_path):
    if hmm["viterbi_path"] is None:
        return
    path = hmm["viterbi_path"]
    t_us = np.arange(path.size, dtype=float)  # unit spacing; scaled below
    stats = dwell_time_statistics(path, t_us)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, dw, lbl in (
        (axes[0], stats["dwell_0_us"], "state0"),
        (axes[1], stats["dwell_1_us"], "state1"),
    ):
        if dw.size:
            ax.hist(dw, bins=min(30, max(5, dw.size // 5)), log=True)
        ax.set_xlabel("dwell (samples)")
        ax.set_title(f"{lbl} dwells (Viterbi)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _json_default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return str(x)


def analyze_modified_ramsey_record(
    I,
    Q,
    dt_s,
    calibration,
    drift_timescale_s=0.2,
    expected_dwell_s=2.5e-3,
    symmetric_hmm=True,
    n_boot=0,
    seed=0,
    mapping_probabilities=(0.1, 0.9),
    mapping_probabilities_calibrated=False,
    reset_I=None,
    reset_Q=None,
    out_dir=None,
    base_name="mr_parity",
    save_plots=True,
    save_sidecars=True,
    hmm_kwargs=None,
):
    """
    End-to-end offline analysis of one Modified-Ramsey parity record.

    Parameters
    ----------
    I, Q          : (N,) unthresholded per-shot IQ (final Ramsey readout).
    dt_s          : float or (N-1,) array, ACTUAL per-shot interval(s) in
                    seconds (use the scheduled rep period from the saved
                    timing, and per-step gaps where the record has them).
    calibration   : output of calibrate_readout_from_labeled_shots.
    drift_timescale_s : rolling drift window; default 0.2 s = 80x a 2.5 ms
                    expected dwell.
    expected_dwell_s  : expected parity dwell (2-3 ms on BFC devices).
    symmetric_hmm : fit a single symmetric rate by default (charge parity has
                    no preferred branch); set False for asymmetric rates.
    mapping_probabilities : assumed P(e|state0), P(e|state1) for the Ramsey
                    mapping. These must come from a device-specific mapping
                    calibration; g/e readout fidelity alone is not sufficient.
    mapping_probabilities_calibrated : whether that independent calibration was
                    performed; False adds an explicit quality warning.
    reset_I/Q     : optional (n_cycles, N) reset readouts for initialization
                    validation.
    out_dir/base_name/save_plots/save_sidecars : output control.
    hmm_kwargs    : extra kwargs forwarded to fit_two_state_hmm.

    Returns dict with sub-results: calibration, drift, hmm, acf, psd,
    rate_vs_bin, reset, assessment, plus scalar summary fields.
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    if I.size != Q.size:
        raise ValueError("I and Q must have the same length")
    original_n = I.size
    finite = np.isfinite(I) & np.isfinite(Q)
    if np.count_nonzero(finite) < 10:
        raise ValueError("fewer than 10 jointly finite IQ samples remain")

    if np.isscalar(dt_s):
        dt_value = float(dt_s)
        if not math.isfinite(dt_value) or dt_value <= 0:
            raise ValueError("dt_s must be finite and positive")
        full_t = np.arange(original_n, dtype=float) * dt_value
    else:
        raw_steps = np.ravel(np.asarray(dt_s, dtype=float))
        if raw_steps.size != original_n - 1:
            raise ValueError("dt_s array must have length original_N-1")
        if np.any(~np.isfinite(raw_steps)) or np.any(raw_steps <= 0):
            raise ValueError("all dt steps must be finite and positive")
        full_t = np.concatenate([[0.0], np.cumsum(raw_steps)])

    I, Q = I[finite], Q[finite]
    t_s = full_t[finite]
    dt_steps = np.diff(t_s)
    dt_nominal = float(np.median(dt_steps))
    removed = int(original_n - I.size)
    v = project_iq_trace(I, Q, calibration)

    uniform_timing = bool(
        np.allclose(dt_steps, dt_nominal, rtol=1e-6, atol=max(1e-15, dt_nominal * 1e-9))
    )
    if uniform_timing:
        drift = remove_slow_drift(
            v, dt_nominal, drift_timescale_s, expected_dwell_s=expected_dwell_s
        )
    else:
        warning = (
            "nonuniform timing/gaps detected: drift filtering, "
            "autocorrelation, PSD, and bin-size estimates were skipped; "
            "the HMM alone uses exact per-step timing"
        )
        drift = {
            "v_original": v.copy(),
            "v_corrected": v.copy(),
            "drift": np.zeros_like(v),
            "window_samples": 0,
            "drift_span": 0.0,
            "safe": False,
            "warnings": [warning],
        }
    if removed:
        drift["warnings"].append(
            f"removed {removed} non-finite IQ samples and carried their "
            "elapsed time into HMM dt steps"
        )
    v_corr = drift["v_corrected"]

    p0, p1 = map(float, mapping_probabilities)
    if not (0.0 <= p0 <= 1.0 and 0.0 <= p1 <= 1.0):
        raise ValueError("mapping probabilities must lie in [0, 1]")
    if p0 == p1:
        raise ValueError(
            "mapping probabilities must differ; identical probabilities carry no parity information"
        )
    if not mapping_probabilities_calibrated:
        drift["warnings"].append(
            "Ramsey mapping probabilities are assumed rather than independently "
            "calibrated; fitted rates are conditional on those assumptions"
        )
    emissions = {
        "model": "ge_mixture",
        "mu_g": calibration["proj_g_mean"],
        "mu_e": calibration["proj_e_mean"],
        "sigma_g": calibration["proj_g_sigma"],
        "sigma_e": calibration["proj_e_sigma"],
        "p_e_state0": p0,
        "p_e_state1": p1,
    }
    fit_options = dict(hmm_kwargs or {})
    if expected_dwell_s and expected_dwell_s > 0:
        fit_options.setdefault("gamma_init_hz", 1.0 / expected_dwell_s)
    hmm = fit_two_state_hmm(
        v_corr,
        dt_steps,
        emissions,
        symmetric=symmetric_hmm,
        n_boot=n_boot,
        seed=seed,
        **fit_options,
    )

    if uniform_timing:
        acf = autocorrelation_rate_estimate(v_corr, dt_nominal)
        psd = psd_rate_estimate(v_corr, dt_nominal)
        rvb = rate_vs_bin_size(v_corr, dt_nominal, calibration["threshold"])
    else:
        skipped = drift["warnings"][0]
        acf = {
            "tau_corr_s": float("nan"),
            "gamma_hz": float("nan"),
            "amplitude": float("nan"),
            "noise_variance": float("nan"),
            "acf": np.zeros(0),
            "lags_s": np.zeros(0),
            "fit_ok": False,
            "warnings": [skipped],
        }
        psd = {
            "f_corner_hz": float("nan"),
            "gamma_hz": float("nan"),
            "s0": float("nan"),
            "white_floor": float("nan"),
            "freqs_hz": np.zeros(0),
            "psd": np.zeros(0),
            "fit_ok": False,
            "warnings": [skipped],
        }
        rvb = {
            "bin_sizes": [],
            "bin_us": [],
            "rate_hz": [],
            "n_switches": [],
            "warnings": [skipped],
        }

    reset = None
    if reset_I is not None and reset_Q is not None and np.size(reset_I):
        reset_i = np.asarray(reset_I)
        reset_q = np.asarray(reset_Q)
        if reset_i.shape[-1] == original_n:
            reset_i, reset_q = reset_i[..., finite], reset_q[..., finite]
        reset = reset_success_vs_cycle(reset_i, reset_q, calibration)
    assessment = assess_parity_record(
        calibration=calibration, hmm=hmm, acf=acf, psd=psd, drift=drift, reset=reset
    )

    t_s = (
        np.concatenate([[0.0], np.cumsum(dt_steps)])
        if dt_steps is not None
        else np.arange(v.size) * dt_nominal
    )

    summary = {
        "n_samples": int(v.size),
        "n_samples_removed_nonfinite": removed,
        "uniform_timing": uniform_timing,
        "dt_nominal_s": dt_nominal,
        "record_duration_s": float(t_s[-1]) if v.size else 0.0,
        "emission_model": "ge_mixture",
        "mapping_p_e_state0": p0,
        "mapping_p_e_state1": p1,
        "mapping_probabilities_calibrated": bool(mapping_probabilities_calibrated),
        "identifiable": hmm["identifiable"],
        "gamma01_hz": hmm["gamma01_hz"],
        "gamma10_hz": hmm["gamma10_hz"],
        "gamma01_err_hz": hmm["gamma01_err_hz"],
        "gamma10_err_hz": hmm["gamma10_err_hz"],
        "acf_gamma_hz": acf["gamma_hz"],
        "psd_gamma_hz": psd["gamma_hz"],
        "posterior_ambiguity": hmm["posterior_ambiguity"],
        "expected_transitions": hmm["expected_transitions"],
        "occupancy_state1": float(hmm["occupancy"][1])
        if np.all(np.isfinite(hmm["occupancy"]))
        else float("nan"),
        "readout_contrast": calibration["contrast"],
        "assignment_fidelity": calibration["assignment_fidelity"],
        "snr_analog": calibration["snr_analog"],
        "drift_span": drift["drift_span"],
        "drift_safe": drift["safe"],
        "reset_converged": (reset or {}).get("converged"),
        "warnings": assessment["warnings"],
    }

    if out_dir is not None and (save_plots or save_sidecars):
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.join(out_dir, base_name)
        if save_plots:
            _plot_calibration(calibration, base + "_calibration.png")
            _plot_projected_trace(t_s, v, v_corr, drift["drift"], base + "_projected_trace.png")
            _plot_hmm(t_s, v_corr, hmm, base + "_hmm.png")
            _plot_acf_psd(acf, psd, base + "_acf_psd.png")
            _plot_rate_vs_bin(rvb, base + "_rate_vs_bin.png")
            _plot_dwells(hmm, base + "_dwells.png")
            if reset is not None:
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.plot(np.arange(reset["n_cycles"]), reset["pre_correction_g_fraction"], "o-")
                ax.set_xlabel("pre-correction readout index")
                ax.set_ylabel("ground fraction before correction")
                ax.set_ylim(0, 1.02)
                ax.set_title("Active-reset pre-correction populations")
                fig.tight_layout()
                fig.savefig(base + "_reset_success.png", dpi=150)
                plt.close(fig)
        if save_sidecars:
            with open(base + "_analysis.json", "w") as fh:
                json.dump(
                    {
                        **summary,
                        "acf": {
                            k: acf[k]
                            for k in (
                                "tau_corr_s",
                                "gamma_hz",
                                "amplitude",
                                "noise_variance",
                                "fit_ok",
                            )
                        },
                        "psd": {
                            k: psd[k]
                            for k in ("f_corner_hz", "gamma_hz", "s0", "white_floor", "fit_ok")
                        },
                        "rate_vs_bin": rvb,
                        "gamma_boot_ci": hmm["gamma_boot_ci"],
                        "dwell_mean_s": hmm["dwell_mean_s"],
                        "reset_pre_correction_g_fraction": (reset or {}).get(
                            "pre_correction_g_fraction"
                        ),
                        "reset_validated_after_reset_g_fraction": (reset or {}).get(
                            "validated_after_reset_g_fraction"
                        ),
                        "reset_final_ground_fraction": (reset or {}).get("final_ground_fraction"),
                    },
                    fh,
                    indent=2,
                    default=_json_default,
                )
            try:
                import h5py

                with h5py.File(base + "_analysis.h5", "w") as fh:
                    fh.create_dataset("v_projected", data=v)
                    fh.create_dataset("v_corrected", data=v_corr)
                    fh.create_dataset("drift", data=drift["drift"])
                    fh.create_dataset("t_s", data=t_s)
                    if hmm["posteriors"] is not None:
                        fh.create_dataset("posterior_state1", data=hmm["posteriors"][:, 1])
                    if hmm["viterbi_path"] is not None:
                        fh.create_dataset("viterbi_path", data=hmm["viterbi_path"])
                    for k, val in summary.items():
                        if k == "warnings":
                            fh.attrs[k] = json.dumps(val)
                        elif val is None:
                            fh.attrs[k] = "None"
                        else:
                            fh.attrs[k] = val
            except ImportError:
                pass

    return {
        "summary": summary,
        "calibration": calibration,
        "drift": drift,
        "hmm": hmm,
        "acf": acf,
        "psd": psd,
        "rate_vs_bin": rvb,
        "reset": reset,
        "assessment": assessment,
        "v_projected": v,
        "v_corrected": v_corr,
        "t_s": t_s,
    }
