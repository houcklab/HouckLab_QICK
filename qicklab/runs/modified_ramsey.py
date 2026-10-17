"""Modified-Ramsey charge-parity runs (parity record and control suite)."""

import glob
import json
import math
import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np

from qicklab.analysis.iq import classify_and_average_iq, kmeans_split
from qicklab.analysis.modified_ramsey import (
    TRUE_STATE_SEPARATION_SOURCES,
    _lag_cov_ratio,
    analyze_modified_ramsey_record,
    compare_parity_controls,
    true_state_separation,
)
from qicklab.analysis.plotting import iq_separator_geometry, plot_separator, set_iq_limits
from qicklab.analysis.readout import calibrate_readout_from_labeled_shots
from qicklab.core.experiment import finish
from qicklab.core.io import save_cycle_summary, save_record, timestamp
from qicklab.experiments.modified_ramsey import (
    ModifiedRamsey,
    build_control_variants,
    modified_ramsey_timing,
    predict_pi_transfer,
    predicted_mapping_seed,
)
from qicklab.runs.active_reset import calibrate_active_reset_readout, wire_reset_into_mr_cfg
from qicklab.runs.single_shot import (
    _extract_iq_from_singleshot_data,
    get_apriori_separator_from_singleshot,
)
from qicklab.runs.sweet_spot import find_sweet_spot

# a bias readback this far from the recorded f_ge_measured_at_V counts as moved (also: MRC
# recalibrates its SingleShot when V_sweet moves this far)
F_GE_BIAS_TOLERANCE_V = 1e-4

# build_modified_ramsey_cfg keys that modified_ramsey_control takes from ModifiedRamsey_params
# when given (a differing value in ModifiedRamsey_Control_params is ignored, with a note)
MRC_SEQUENCE_KEYS = (
    "mr_reps",
    "mr_relax_delay",
    "tau_harmonic_k",
    "use_pi_pulse",
    "flip_final_pi2",
    "symmetric_ramsey",
    "max_drive_bandwidth_ratio",
    "use_active_reset",
    "reset_cycles",
    "reset_ground_below_threshold",
    "reset_readout_relax_delay",
    "reset_read_latency_us",
    "post_reset_wait",
    "readout_threshold",
)

# a SingleShot e purity at least this high leaves the MRC/MR lag-covariance ratio within
# ~10 % of its true-state value when the separation is the raw one (bias ~ purity^2)
SS_PREP_NEAR_ONE = 0.95
# below this predicted purity the raw calibration is too poorly prepared to correct by
# 1/purity^2 (the correction would amplify the model error); the corrected ratio is NaN
SS_PREP_CORRECTABLE = 0.5

# modified_ramsey_control npz keys that are KMeans / hysteresis diagnostics, not the result
MRC_DIAGNOSTIC_KEYS = (
    "scores",
    "binary_states",
    "state_avg",
    "state_hysteresis",
    "hysteresis_switches",
    "switch_time_ms",
    "centers",
    "midpoint",
    "normal",
    "hysteresis_low",
    "hysteresis_high",
    "moving_avg_window_n",
    "moving_avg_window_ms",
)


def check_f_ge_near_qubit(
    f_ge_mhz,
    df_mhz,
    qubit_center_mhz,
    sigma_us,
    *,
    qubit_pulse=None,
    strict=False,
    measured_at_v=None,
    current_v=None,
):
    """Check that the configured doublet sits on the calibrated qubit; return the numbers.

    The doublet centre ``f_ge - df/2`` (the symmetric drive frequency; ``f_ge`` is the
    upper branch) is compared with ``qubit_center_mhz``, where the pi/2 and pi gains and
    the SingleShot separator were calibrated. The tolerance is
    ``max(5*df, 2 MHz, 1/(4*sigma_us))``: the last term is the order of the bandwidth of
    the 4*sigma Gaussian. Far outside it the calibrated pulses do not address this
    transition and the record would show no drive. ``strict=True`` raises ValueError; the
    default prints a warning (the CSTQ03 runner has f_ge on Q2 while pulsing Q5, see
    docs/experiments/modified_ramsey.md#known-issues). ``measured_at_v`` (the bias at
    which df and f_ge were measured) only warns when ``current_v`` differs from it by more
    than F_GE_BIAS_TOLERANCE_V.
    """
    centre = float(f_ge_mhz) - float(df_mhz) / 2.0
    offset = centre - float(qubit_center_mhz)
    # a non-positive sigma is refused later by the program planner, with its own message
    bw_mhz = 1.0 / (4.0 * float(sigma_us)) if float(sigma_us) > 0 else 0.0
    tol = max(5.0 * float(df_mhz), 2.0, bw_mhz)
    out = {
        "doublet_centre_mhz": centre,
        "qubit_frequency_center_mhz": float(qubit_center_mhz),
        "offset_mhz": offset,
        "tolerance_mhz": tol,
        "on_qubit": abs(offset) <= tol,
        "bias_moved": False,
    }
    if not out["on_qubit"]:
        msg = (
            f"ModifiedRamsey f_ge={float(f_ge_mhz)} MHz, df={float(df_mhz)} MHz puts the "
            f"doublet centre at {centre:.4f} MHz, {offset:+.4f} MHz from the calibrated "
            f"qubit frequency {float(qubit_center_mhz)} MHz (Qubit_Pulse={qubit_pulse}; "
            f"tolerance {tol:.4f} MHz). The pi/2, pi gains and the SingleShot separator "
            "belong to that qubit, so the Ramsey drive would not address it. Check f_ge "
            "(it may be another qubit's frequency) or Qubit_Parameters."
        )
        if strict:
            raise ValueError(msg + " (require_f_ge_near_qubit=True)")
        print("WARNING: " + msg)
    if measured_at_v is not None and current_v is not None:
        dv = float(current_v) - float(measured_at_v)
        out["bias_moved"] = abs(dv) > F_GE_BIAS_TOLERANCE_V
        if out["bias_moved"]:
            print(
                f"WARNING: ModifiedRamsey df/f_ge were measured at {float(measured_at_v)} V "
                f"but the bias now reads {float(current_v)} V ({dv:+.6f} V): "
                "the doublet may have moved."
            )
    return out


def build_modified_ramsey_cfg(
    ctx, params, *, f_ge, df, current_voltage, apriori_sep=None, measured_at_v=None
):
    """The ModifiedRamsey cfg keys of one record (merged over the working config by the caller).

    Shared by modified_ramsey and modified_ramsey_control so the sweet-spot null is the same
    sequence. ``params`` is a ModifiedRamsey_params-style dict; tau = k/(2*df) with odd
    k = ``tau_harmonic_k`` (docs/experiments/modified_ramsey.md, choosing tau).
    ``measured_at_v`` is saved as ``f_ge_measured_at_V`` when given. With active reset and
    no manual ``readout_threshold`` the threshold comes from ``apriori_sep``.
    """
    tau_k = int(params.get("tau_harmonic_k", 1))
    if tau_k < 1 or tau_k % 2 == 0:
        raise ValueError(
            f"ModifiedRamsey_params['tau_harmonic_k']={tau_k} must be a "
            "positive ODD integer: tau = k/(2*df) only satisfies the parity "
            "pi condition for odd k (even k returns the branches to phase "
            "and gives zero contrast)"
        )
    mr_cfg = {
        "f_ge": f_ge,
        "df": df,
        "ramsey_tau_us": tau_k / (2.0 * df),
        "mr_tau_harmonic_k": tau_k,
        "pi2_gain": ctx.pi2_gain,
        "pi_gain": ctx.qubit_gain,
        "use_pi_pulse": params.get("use_pi_pulse", False),
        "flip_final_pi2": params.get("flip_final_pi2", False),
        "symmetric_ramsey": params.get("symmetric_ramsey", False),
        "max_drive_bandwidth_ratio": params.get("max_drive_bandwidth_ratio", 1.0),
        "use_active_reset": params.get("use_active_reset", False),
        "reset_cycles": params.get("reset_cycles", 1),
        "reset_ground_below_threshold": params.get("reset_ground_below_threshold", True),
        "reset_readout_relax_delay": params.get("reset_readout_relax_delay", 1.0),
        "post_reset_wait": params.get("post_reset_wait", 0.0),
        "mr_relax_delay": params.get("mr_relax_delay", 0.0),
        "sigma": ctx.qubit_sigma,
        "flattop_length": ctx.qubit_flattop,
        "reps": params["mr_reps"],
        "rounds": 1,
        "current_voltage": current_voltage,
        "Qubit_number": ctx.Qubit_Readout,
    }
    # provenance of df/f_ge, saved with the record only when set
    if measured_at_v is not None:
        mr_cfg["f_ge_measured_at_V"] = float(measured_at_v)
    # forwarded only when set, so the program's 0.5 us default/floor applies otherwise
    if "reset_read_latency_us" in params:
        mr_cfg["reset_read_latency_us"] = params["reset_read_latency_us"]
    # a manual readout_threshold wins over the one derived from the current separator
    if params.get("readout_threshold") is not None:
        mr_cfg["readout_threshold"] = params["readout_threshold"]
    elif mr_cfg["use_active_reset"]:
        wire_reset_into_mr_cfg(mr_cfg, apriori_sep)
    return mr_cfg


def parity_analysis_settings(params, config, tag="ModifiedRamsey"):
    """(mapping_probabilities, fit_mapping, seed_source, hmm_kwargs) of the parity analysis.

    One rule for modified_ramsey, its validation controls and modified_ramsey_control: the
    emission model and the gates are the same for all of them.
    """
    mapping = (params.get("mapping_p_e_state0", 0.1), params.get("mapping_p_e_state1", 0.9))
    # min_emission_snr: do not lower (CSTQ03 Q2, 2026-08-04), docs/experiments/modified_ramsey.md
    hmm_kwargs = dict(params.get("hmm_kwargs") or {})
    if params.get("hmm_min_emission_snr") is not None:
        hmm_kwargs["min_emission_snr"] = float(params["hmm_min_emission_snr"])
    # the effective switch: hmm_kwargs["fit_mapping"] overrides hmm_fit_mapping in the
    # analysis, so it decides here too; an idealised prediction must never become a
    # FIXED mapping that the emission gate then trusts
    fit_mapping = bool(hmm_kwargs.get("fit_mapping", params.get("hmm_fit_mapping", True)))
    calibrated = params.get("mapping_probabilities_calibrated", False)
    seed_source = "calibrated" if calibrated else ("supplied" if fit_mapping else "assumed")
    if fit_mapping and not calibrated:
        # seed of the mapping fit: the predicted mapping of this sequence; the
        # controls reuse it (docs/experiments/modified_ramsey.md#analysis)
        p0_seed, p1_seed, seed_source = predicted_mapping_seed(config, fallback=mapping)
        mapping = (p0_seed, p1_seed)
        print(
            f"[{tag}] mapping fit seeded at p_e = "
            f"({mapping[0]:.3f}, {mapping[1]:.3f}) "
            f"({seed_source})"
        )
    return mapping, fit_mapping, seed_source, hmm_kwargs


def analyze_parity_record(
    params,
    settings,
    I,
    Q,
    dt_s,
    calibration,
    *,
    reset_I,
    reset_Q,
    out_dir,
    base_name,
    readout_prep_e_predicted=None,
):
    """analyze_modified_ramsey_record with the analysis keys of ``params`` and ``settings``
    (parity_analysis_settings): the one call shared by MR, its controls and MRC.
    ``readout_prep_e_predicted`` (predicted_singleshot_prep) goes to the sidecar only."""
    mapping, fit_mapping, seed_source, hmm_kwargs = settings
    return analyze_modified_ramsey_record(
        I,
        Q,
        dt_s,
        calibration,
        drift_timescale_s=(params.get("drift_window_ms", 200.0) * 1e-3),
        expected_dwell_s=(params.get("expected_parity_dwell_ms", 2.5) * 1e-3),
        symmetric_hmm=params.get("hmm_symmetric", True),
        n_boot=params.get("hmm_bootstrap_samples", 0),
        mapping_probabilities=mapping,
        mapping_probabilities_calibrated=params.get("mapping_probabilities_calibrated", False),
        fit_mapping=fit_mapping,
        mapping_seed_source=seed_source,
        reset_I=reset_I,
        reset_Q=reset_Q,
        out_dir=out_dir,
        base_name=base_name,
        hmm_kwargs=hmm_kwargs,
        readout_prep_e_predicted=readout_prep_e_predicted,
    )


def predicted_singleshot_prep(ctx, f_ge, df):
    """Predicted e purity of the SingleShot calibration's pi-prepared set at a bias whose
    parity branches are f_ge (upper) and f_ge - df [MHz], or None if not modelled.

    get_apriori_separator_from_singleshot plays its pi (ctx.qubit_sigma, area pi) at
    ctx.qubit_frequency_center; each branch is excited with predict_pi_transfer at its
    detuning (ideal two-level, nominal 4*sigma Gaussian), averaged over equally occupied
    branches. A flat-top qubit pulse (ctx.qubit_flattop set) is not modelled: None. It is
    an upper bound on the measured purity (no decay during readout, no thermal g)."""
    flattop = getattr(ctx, "qubit_flattop", None)
    sigma = _finite_float(getattr(ctx, "qubit_sigma", None))
    if flattop not in (None, 0) or not sigma > 0:
        return None
    f_pi = float(ctx.qubit_frequency_center)
    upper = float(f_ge) - f_pi
    lower = upper - float(df)
    return 0.5 * (predict_pi_transfer(sigma, upper) + predict_pi_transfer(sigma, lower))


def run_modified_ramsey(ctx, ModifiedRamsey_params):
    date_tag_mr = datetime.now().strftime("%Y_%m_%d")
    save_dir_mr = os.path.join(ctx.outerFolder, "ModifiedRamsey", date_tag_mr)
    os.makedirs(save_dir_mr, exist_ok=True)

    # df and f_ge are configured, never searched: docs/experiments/modified_ramsey.md
    df_mr = float(ModifiedRamsey_params["df"])
    if df_mr <= 0:
        raise ValueError("ModifiedRamsey_params['df'] must be positive")
    f_ge_mr = float(ModifiedRamsey_params.get("f_ge", ctx.qubit_frequency_center))
    num_cycles_mr = ModifiedRamsey_params["num_cycles"]

    # provenance only: this routine never moves the yoko
    current_voltage_mr = float(ctx.yoko.query(":SOUR:LEV?"))
    f_ge_measured_at_v_mr = ModifiedRamsey_params.get("f_ge_measured_at_V")

    # before any acquisition: is the doublet on the qubit the gains were calibrated on?
    check_f_ge_near_qubit(
        f_ge_mr,
        df_mr,
        ctx.qubit_frequency_center,
        ctx.qubit_sigma,
        qubit_pulse=ctx.Qubit_Pulse,
        strict=ModifiedRamsey_params.get("require_f_ge_near_qubit", False),
        measured_at_v=f_ge_measured_at_v_mr,
        current_v=current_voltage_mr,
    )

    cycle_summary_mr = []

    apriori_sep_mr = None

    # rotates ctx.config["res_phase"] in place; must precede the separator below
    # (docs/experiments/active_reset.md)
    if ModifiedRamsey_params.get("use_active_reset", False):
        if not ModifiedRamsey_params.get("use_apriori_separator", False):
            raise RuntimeError(
                "use_active_reset=True requires use_apriori_separator=True "
                "(the reset threshold is derived from the SingleShot separator)."
            )
        calibrate_active_reset_readout(ctx)

    if ModifiedRamsey_params.get("use_apriori_separator", False):
        apriori_sep_mr = get_apriori_separator_from_singleshot(
            ctx, ss_shots=ModifiedRamsey_params.get("ss_calib_shots", 1000)
        )
    ss_recalib_n_mr = ModifiedRamsey_params.get("ss_recalib_every_n_cycles", None)

    cfg = ctx.working_config()

    for cycle_idx_mr in range(num_cycles_mr):
        if ModifiedRamsey_params.get("use_apriori_separator", False):
            if apriori_sep_mr is None or (
                ss_recalib_n_mr is not None
                and ss_recalib_n_mr > 0
                and cycle_idx_mr % ss_recalib_n_mr == 0
            ):
                apriori_sep_mr = get_apriori_separator_from_singleshot(
                    ctx, ss_shots=ModifiedRamsey_params.get("ss_calib_shots", 1000)
                )
        print(
            f"\n================ ModifiedRamsey Cycle {cycle_idx_mr + 1}/{num_cycles_mr} ================"
        )

        chosen_probe_freq_mr = f_ge_mr
        chosen_peak_sep_mr = df_mr

        mr_cfg = build_modified_ramsey_cfg(
            ctx,
            ModifiedRamsey_params,
            f_ge=chosen_probe_freq_mr,
            df=chosen_peak_sep_mr,
            current_voltage=current_voltage_mr,
            apriori_sep=apriori_sep_mr,
            measured_at_v=f_ge_measured_at_v_mr,
        )
        tau_us_mr = mr_cfg["ramsey_tau_us"]
        config_mr = cfg | mr_cfg
        timing_mr = modified_ramsey_timing(ctx.soccfg, config_mr)
        config_mr["modified_ramsey_timing"] = timing_mr

        Instance_mr = ModifiedRamsey(
            path="ModifiedRamsey",
            cfg=config_mr,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )
        data_mr = ModifiedRamsey.acquire(Instance_mr)
        finish(ModifiedRamsey, Instance_mr, data_mr, plotDisp=False, figNum=10)

        raw_i_mr = np.ravel(np.array(data_mr["data"]["shots_i"]))
        raw_q_mr = np.ravel(np.array(data_mr["data"]["shots_q"]))

        if apriori_sep_mr is None:
            raise RuntimeError("ModifiedRamsey requires a labeled SingleShot calibration.")

        base_mr = os.path.join(save_dir_mr, f"Cycle_{cycle_idx_mr:03d}_MR_{timestamp()}")
        I_g_mr, Q_g_mr = _extract_iq_from_singleshot_data(apriori_sep_mr["data_ss"], "g")
        I_e_mr, Q_e_mr = _extract_iq_from_singleshot_data(apriori_sep_mr["data_ss"], "e")
        analog_cal_mr = calibrate_readout_from_labeled_shots(I_g_mr, Q_g_mr, I_e_mr, Q_e_mr)
        continuous_mr = None
        analysis_enabled_mr = ModifiedRamsey_params.get("parity_analysis_enabled", True)
        if analysis_enabled_mr:
            settings_mr = parity_analysis_settings(ModifiedRamsey_params, config_mr)
            continuous_mr = analyze_parity_record(
                ModifiedRamsey_params,
                settings_mr,
                raw_i_mr,
                raw_q_mr,
                data_mr["data"]["scheduled_rep_period_us"] * 1e-6,
                analog_cal_mr,
                reset_I=data_mr["data"].get("reset_shots_i"),
                reset_Q=data_mr["data"].get("reset_shots_q"),
                out_dir=save_dir_mr,
                base_name=os.path.basename(base_mr) + "_continuous",
                readout_prep_e_predicted=predicted_singleshot_prep(
                    ctx, chosen_probe_freq_mr, chosen_peak_sep_mr
                ),
            )
            print(
                "[ModifiedRamsey] continuous-analysis verdict: "
                f"identifiable={continuous_mr['summary']['identifiable']}, "
                f"gamma={continuous_mr['summary']['gamma01_hz']} Hz"
            )

        # controls are acquired whatever parity_analysis_enabled says; only their analysis
        # is optional (docs/experiments/modified_ramsey.md#validation-controls)
        control_names_mr = tuple(ModifiedRamsey_params.get("validation_controls", ()))
        control_every_mr = int(ModifiedRamsey_params.get("validation_controls_every_n_cycles", 1))
        if control_every_mr <= 0:
            raise ValueError("validation_controls_every_n_cycles must be positive")
        if control_names_mr and cycle_idx_mr % control_every_mr == 0:
            if not analysis_enabled_mr:
                print(
                    "[ModifiedRamsey] parity_analysis_enabled=False: validation controls "
                    f"{list(control_names_mr)} are acquired and saved but not analysed "
                    f"(index: {os.path.basename(base_mr)}_controls_index.json)"
                )
            analyzed_controls_mr = []
            skipped_controls_mr = []
            acquired_controls_mr = {}
            for control_mr in build_control_variants(
                config_mr,
                include=control_names_mr,
                tau_offset_frac=ModifiedRamsey_params.get("control_tau_offset_frac"),
                detuning_mhz=ModifiedRamsey_params.get("control_detuning_mhz"),
            ):
                if control_mr["cfg"] is None:
                    skipped_controls_mr.append(
                        {
                            "control_type": control_mr["control_type"],
                            "reason": control_mr["skip_reason"],
                        }
                    )
                    continue
                control_cfg_mr = control_mr["cfg"]
                # link to the parent record, for pairing offline
                control_cfg_mr["mr_parent_record"] = Instance_mr.fname
                control_cfg_mr["mr_parent_cycle_idx"] = cycle_idx_mr
                control_timing_mr = modified_ramsey_timing(ctx.soccfg, control_cfg_mr)
                control_cfg_mr["modified_ramsey_timing"] = control_timing_mr
                control_inst_mr = ModifiedRamsey(
                    path="ModifiedRamsey_Controls",
                    cfg=control_cfg_mr,
                    soc=ctx.soc,
                    soccfg=ctx.soccfg,
                    outerFolder=ctx.outerFolder,
                )
                control_data_mr = ModifiedRamsey.acquire(control_inst_mr)
                finish(ModifiedRamsey, control_inst_mr, control_data_mr, plotDisp=False, figNum=12)
                control_type_mr = control_mr["control_type"]
                acquired_controls_mr[control_type_mr] = control_inst_mr.fname
                if not analysis_enabled_mr:
                    continue
                control_analysis_mr = analyze_parity_record(
                    ModifiedRamsey_params,
                    settings_mr,  # same gate as the parity record
                    control_data_mr["data"]["shots_i"],
                    control_data_mr["data"]["shots_q"],
                    control_data_mr["data"]["scheduled_rep_period_us"] * 1e-6,
                    analog_cal_mr,
                    reset_I=control_data_mr["data"].get("reset_shots_i"),
                    reset_Q=control_data_mr["data"].get("reset_shots_q"),
                    out_dir=save_dir_mr,
                    base_name=(os.path.basename(base_mr) + f"_{control_type_mr}"),
                )
                analyzed_controls_mr.append(
                    {
                        "label": control_type_mr,
                        "control_type": control_type_mr,
                        "hmm": control_analysis_mr["hmm"],
                        "acf": control_analysis_mr["acf"],
                        "occupancy_state1": control_analysis_mr["summary"]["occupancy_state1"],
                        "null_control_valid": control_mr["null_control_valid"],
                        "null_invalid_reason": control_mr["null_invalid_reason"],
                        "inverted_mapping_expected": control_mr["inverted_mapping_expected"],
                        "inverted_mapping_reason": control_mr["inverted_mapping_reason"],
                    }
                )
            if not acquired_controls_mr:
                print(
                    "[ModifiedRamsey] every validation control was skipped as infeasible: "
                    + "; ".join(f"{s['control_type']}: {s['reason']}" for s in skipped_controls_mr)
                )
            if analysis_enabled_mr:
                comparison_mr = compare_parity_controls(
                    {
                        "label": "parity",
                        "hmm": continuous_mr["hmm"],
                        "acf": continuous_mr["acf"],
                        "occupancy_state1": continuous_mr["summary"]["occupancy_state1"],
                    },
                    analyzed_controls_mr,
                )
                comparison_mr["skipped"] = skipped_controls_mr
                if skipped_controls_mr:
                    comparison_mr["all_expected"] = False
                with open(base_mr + "_control_comparison.json", "w") as f:
                    json.dump(comparison_mr, f, indent=2, default=float)
            else:
                with open(base_mr + "_controls_index.json", "w") as f:
                    json.dump(
                        {
                            "cycle_idx": cycle_idx_mr,
                            "parent_record": Instance_mr.fname,
                            "controls": acquired_controls_mr,
                            "skipped": skipped_controls_mr,
                        },
                        f,
                        indent=2,
                    )

        # hard-threshold diagnostics only; rates come from the unthresholded analysis above
        average_n_shots_mr = ModifiedRamsey_params.get("average_n_shots", 25)

        classification_mr = classify_and_average_iq(
            raw_i=raw_i_mr,
            raw_q=raw_q_mr,
            g_center=apriori_sep_mr["g_center"],
            e_center=apriori_sep_mr["e_center"],
            average_n_shots=average_n_shots_mr,
        )

        binary_states_mr = classification_mr["binary_states"]
        excited_avg_mr = classification_mr["excited_avg"]
        scores_mr = classification_mr["scores"]
        normal_mr = classification_mr["normal"]
        midpoint_mr = classification_mr["midpoint"]

        c0_mr = apriori_sep_mr["g_center"]
        c1_mr = apriori_sep_mr["e_center"]

        rep_period_us = timing_mr["scheduled_rep_period_us"]
        streamer_rep_period_us_mr = data_mr["data"].get("streamer_average_rep_period_us", np.nan)

        elapsed_ms_mr = np.arange(len(raw_i_mr)) * rep_period_us * 1e-3
        # +0.5: label each N-shot bin at its centre so it lines up with the raw trace
        elapsed_avg_ms_mr = (
            (np.arange(len(excited_avg_mr)) + 0.5) * average_n_shots_mr * rep_period_us * 1e-3
        )

        xlim_mr, ylim_mr, I_line_mr, Q_line_mr = iq_separator_geometry(
            raw_i_mr, raw_q_mr, midpoint_mr, normal_mr
        )

        plt.figure(figsize=(6, 6))
        plt.plot(
            raw_i_mr[binary_states_mr == 0],
            raw_q_mr[binary_states_mr == 0],
            ".",
            alpha=0.5,
            label="Assigned 0",
        )
        plt.plot(
            raw_i_mr[binary_states_mr == 1],
            raw_q_mr[binary_states_mr == 1],
            ".",
            alpha=0.5,
            label="Assigned 1",
        )
        plt.plot(c0_mr[0], c0_mr[1], "o", markersize=10, label="SingleShot g center")
        plt.plot(c1_mr[0], c1_mr[1], "o", markersize=10, label="SingleShot e center")

        if Q_line_mr is None:
            plt.axvline(midpoint_mr[0], linestyle="--", linewidth=2, label="g/e separator")
        else:
            plt.plot(I_line_mr, Q_line_mr, "--", linewidth=2, label="g/e separator")

        plt.xlabel("I")
        plt.ylabel("Q")
        set_iq_limits(xlim_mr, ylim_mr)
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey IQ\n"
            f"V={current_voltage_mr:.6f} V, f_ge={chosen_probe_freq_mr:.6f} MHz, "
            f"tau={tau_us_mr:.4f} us"
        )
        plt.legend()
        plt.tight_layout()
        plt.savefig(base_mr + "_iq_labeled_apriori.png", dpi=300, bbox_inches="tight")
        plt.close()

        plt.figure(figsize=(10, 4))
        plt.step(elapsed_ms_mr, binary_states_mr, where="post", linewidth=1.2)
        plt.plot(elapsed_ms_mr, binary_states_mr, "o", markersize=2)
        plt.xlabel("Scheduled time since start (ms)")
        plt.ylabel("Single-shot state")
        plt.yticks([0, 1])
        plt.ylim(-0.1, 1.1)
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey single-shot state\n"
            f"tau={tau_us_mr:.4f} us, df={chosen_peak_sep_mr:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_single_shot_binary.png", dpi=300, bbox_inches="tight")
        plt.close()

        plt.figure(figsize=(10, 4))
        plt.plot(elapsed_avg_ms_mr, excited_avg_mr, "o-", linewidth=1.5)
        plt.xlabel("Scheduled time since start (ms)")
        plt.ylabel("Averaged excited-state population")
        plt.ylim(-0.05, 1.05)
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey averaged state\n"
            f"{average_n_shots_mr} shots per point, tau={tau_us_mr:.4f} us"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_averaged_population.png", dpi=300, bbox_inches="tight")
        plt.close()

        save_record(
            base_mr,
            config_mr,
            Instance_mr,
            elapsed_ms=np.array(elapsed_ms_mr),
            elapsed_avg_ms=np.array(elapsed_avg_ms_mr),
            raw_i=np.array(raw_i_mr),
            raw_q=np.array(raw_q_mr),
            scores=np.array(scores_mr),
            binary_states=np.array(binary_states_mr),
            excited_avg=np.array(excited_avg_mr),
            average_n_shots=np.array(average_n_shots_mr),
            g_center=np.array(c0_mr),
            e_center=np.array(c1_mr),
            midpoint=np.array(midpoint_mr),
            normal=np.array(normal_mr),
            chosen_probe_freq=np.array(chosen_probe_freq_mr),
            peak_sep=np.array(chosen_peak_sep_mr),
            tau_us=np.array(tau_us_mr),
            final_voltage=np.array(current_voltage_mr),
            cycle_idx=np.array(cycle_idx_mr),
            scheduled_rep_period_us=np.array(rep_period_us),
            streamer_average_rep_period_us=np.array(streamer_rep_period_us_mr),
            timing_breakdown=np.array(timing_mr, dtype=object),
            config=np.array(config_mr, dtype=object),
        )

        cycle_summary_mr.append(
            {
                "cycle_idx": cycle_idx_mr,
                "success": True,
                "final_voltage": current_voltage_mr,
                "chosen_probe_freq": chosen_probe_freq_mr,
                "peak_sep": chosen_peak_sep_mr,
                "tau_us": tau_us_mr,
                "scheduled_rep_period_us": rep_period_us,
                "streamer_average_rep_period_us": streamer_rep_period_us_mr,
                "parity_identifiable": (
                    continuous_mr["summary"]["identifiable"] if continuous_mr is not None else None
                ),
                "gamma01_hz": (
                    continuous_mr["summary"]["gamma01_hz"] if continuous_mr is not None else None
                ),
                "gamma10_hz": (
                    continuous_mr["summary"]["gamma10_hz"] if continuous_mr is not None else None
                ),
                "parity_analysis_warnings": (
                    continuous_mr["summary"]["warnings"] if continuous_mr is not None else []
                ),
            }
        )

    save_cycle_summary(save_dir_mr, cycle_summary_mr)


def latest_modified_ramsey_analysis(outer_folder):
    """The newest analysed modified_ramsey record under ``<outer>/ModifiedRamsey``, or None.

    Read from its ``*_continuous_analysis.json`` sidecar (file, identifiable, gamma01_hz,
    gamma01_err_hz, acf_amplitude, acf_r1, lag_covariance_sum, readout_separation
    (true_state_separation: true-state only when readout_separation_source is "mixture"),
    readout_separation_source, readout_prep_e_predicted (predicted_singleshot_prep); the
    last five are None in sidecars written before they were added). Records taken with
    parity_analysis_enabled=False have no sidecar and are not found.
    """
    pattern = os.path.join(outer_folder, "ModifiedRamsey", "*", "*_continuous_analysis.json")
    paths = glob.glob(pattern)
    if not paths:
        return None
    path = max(paths, key=os.path.getmtime)
    try:
        with open(path) as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        return None
    return {
        "file": path,
        "identifiable": record.get("identifiable"),
        "gamma01_hz": record.get("gamma01_hz"),
        "gamma01_err_hz": record.get("gamma01_err_hz"),
        "acf_amplitude": (record.get("acf") or {}).get("amplitude"),
        "acf_r1": (record.get("acf") or {}).get("r1"),
        "lag_covariance_sum": (record.get("acf") or {}).get("lag_covariance_sum"),
        "readout_separation": record.get("readout_separation"),
        "readout_separation_source": record.get("readout_separation_source"),
        "readout_prep_e_predicted": record.get("readout_prep_e_predicted"),
    }


def normalised_lag_covariance(lag_sum, separation):
    """lagged_autocovariance_sum dict divided by the readout separation squared.

    ``separation`` should be the TRUE-state separation (true_state_separation with a
    "mixture" source): the raw labelled-set separation is shrunk by the SingleShot pi
    pulse's prep error, which differs between biases (null_lag_covariance_vs_mr flags and
    corrects a raw one). The lagged covariance of the projected trace is separation^2 times the summed lagged
    covariance of the excited-state indicator (white readout noise does not enter lags >= 1),
    so the quotient is dimensionless and comparable between records with different readout
    scales (MRC at V_sweet vs MR at its bias). Unavailable when either input is missing.
    """
    sep = _finite_float(separation)
    lag_sum = lag_sum or {}
    if not (lag_sum.get("available") and math.isfinite(sep) and sep > 0):
        reason = lag_sum.get("reason") or (
            "no lag-covariance statistic" if not lag_sum.get("available") else ""
        )
        if not reason:
            reason = f"readout separation {separation} not usable"
        return {"available": False, "reason": reason}
    scale = sep * sep
    return {
        "available": True,
        "value": float(lag_sum["value"]) / scale,
        "boot": np.asarray(lag_sum.get("boot", ()), dtype=float) / scale,
        "max_lag": int(lag_sum["max_lag"]),
        "reason": "",
    }


def _separation_shrink(source, prep):
    """used separation / true-state separation of one record: 1 for a true-state source,
    the predicted SingleShot purity for a raw one, None when that is unknown."""
    if source in TRUE_STATE_SEPARATION_SOURCES:
        return 1.0
    prep = _finite_float(prep)
    return min(prep, 1.0) if prep > 0 else None


def null_lag_covariance_vs_mr(
    mrc_acf, mrc_separation, mr_reference, mrc_separation_source=None, mrc_prep_predicted=None
):
    """The sweet-spot null against an MR record: compare_parity_controls' lag-covariance
    ratio (_lag_cov_ratio) on the separation-normalised statistic.

    Returns {"lag_covariance_norm", "lag_covariance_norm_mr", "ratio", "upper95", "lower05",
    "reason", "ratio_prep_corrected", "upper95_prep_corrected", "warning"}. A valid null
    reads ratio ~ 0 with upper95 well below 1; the ratio is NaN (with a reason) when either
    record lacks the statistic, their max_lag differs, or the MR record's own lag sum is not
    significantly > 0.

    Prep bias. A separation that is not true-state (readout_separation_source not "mixture",
    the usual case at analog SNR <~ 1.5) is the raw one, shrunk by the SingleShot e purity
    p, so that record's normalised sum is inflated by 1/p^2. On the MR side that biases the
    ratio LOW by p_mr^2, toward passing the null; on the MRC side high (conservative).
    The two prep-corrected values multiply ratio and upper95 by (s_mrc / s_mr)^2, s = 1 for
    a true-state source, else the predicted purity (readout_prep_e_predicted of the MR
    sidecar, ``mrc_prep_predicted``); an unknown MRC purity counts as 1 (conservative), an
    unknown MR purity, or one below SS_PREP_CORRECTABLE, leaves them NaN (an MRC purity
    below it counts as 1). The prediction is an ideal two-level upper bound on p, so the
    correction removes the detuning part of the bias only. ``warning`` is non-empty when
    the MR separation is raw and its purity is not known to be >= SS_PREP_NEAR_ONE.
    """
    ctl = normalised_lag_covariance((mrc_acf or {}).get("lag_covariance_sum"), mrc_separation)
    ref = mr_reference or {}
    main = normalised_lag_covariance(ref.get("lag_covariance_sum"), ref.get("readout_separation"))
    if mr_reference is None:
        main = {"available": False, "reason": "no analysed MR record to compare with"}
    out = _lag_cov_ratio(
        {"acf": {"lag_covariance_sum": ctl}}, {"acf": {"lag_covariance_sum": main}}
    )

    s_mr = None
    warning = ""
    if mr_reference is not None:
        source_mr = ref.get("readout_separation_source")
        s_mr = _separation_shrink(source_mr, ref.get("readout_prep_e_predicted"))
        if s_mr is None or s_mr < SS_PREP_NEAR_ONE:
            if s_mr is None:
                purity = "unknown"
            elif s_mr < SS_PREP_CORRECTABLE:
                purity = f"predicted {s_mr:.3f}, too low to correct (< {SS_PREP_CORRECTABLE:g})"
            else:
                purity = f"predicted {s_mr:.3f} (the corrected ratio is x {1.0 / s_mr**2:.2f})"
            warning = (
                f"the MR readout_separation is the raw labelled-set one (source {source_mr}: "
                f"no resolved SingleShot mixture fit) and its SingleShot e purity p is "
                f"{purity}: the ratio is biased LOW by ~p^2, toward passing the null"
            )
    if s_mr is not None and s_mr >= SS_PREP_CORRECTABLE:
        s_mrc = _separation_shrink(mrc_separation_source, mrc_prep_predicted)
        if s_mrc is None or s_mrc < SS_PREP_CORRECTABLE:
            s_mrc = 1.0  # unknown or uncorrectable: the larger (conservative) ratio
        factor = (s_mrc / s_mr) ** 2
        corrected, corrected_upper = out["ratio"] * factor, out["upper95"] * factor
    else:
        corrected = corrected_upper = float("nan")
    return {
        "lag_covariance_norm": ctl.get("value", float("nan")),
        "lag_covariance_norm_mr": main.get("value", float("nan")),
        "ratio": out["ratio"],
        "upper95": out["upper95"],
        "lower05": out["lower05"],
        "reason": out["reason"],
        "ratio_prep_corrected": float(corrected),
        "upper95_prep_corrected": float(corrected_upper),
        "warning": warning,
    }


def hysteresis_parity_trace(binary_states, window_n, low, high):
    """(moving average over window_n shots, hysteresis state, 0/1 jumps) of a binary trace.

    Diagnostic plot of modified_ramsey_control only: it has no null distribution, and at
    window_n = 1 it counts every shot-to-shot flip.
    """
    kernel = np.ones(window_n, dtype=float) / window_n
    state_avg = np.convolve(binary_states.astype(float), kernel, mode="same")
    state_hyst = np.empty_like(binary_states)
    current_state = int(binary_states[0])
    for idx, val in enumerate(state_avg):
        if val >= high:
            current_state = 1
        elif val <= low:
            current_state = 0
        state_hyst[idx] = current_state
    switches = (np.diff(state_hyst) != 0).astype(int)
    return state_avg, state_hyst, switches


def _finite_float(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return x if math.isfinite(x) else float("nan")


def run_modified_ramsey_control(ctx, ModifiedRamsey_Control_params, ModifiedRamsey_params=None):
    """Sweet-spot null of modified_ramsey: search, then the MR sequence and the MR analysis.

    With ``ModifiedRamsey_params`` (the session's modified_ramsey settings) the Ramsey cfg is
    build_modified_ramsey_cfg of those settings (df, tau_harmonic_k, mr_reps, mr_relax_delay,
    pulses, active reset) and the record is analysed as an MR record (SingleShot calibration
    at V_sweet, the same mapping seed, emission model and gates). Without it the Ramsey uses
    df = cd_max_mhz and this dict's mr_reps / mr_relax_delay (not comparable with an MR rate).
    docs/experiments/modified_ramsey_control.md
    """
    save_dir_mrc = os.path.join(ctx.outerFolder, "ModifiedRamsey_Control")
    os.makedirs(save_dir_mrc, exist_ok=True)

    sweet_max_df_mrc = ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"]
    cd_max_mhz_mrc = ModifiedRamsey_Control_params["cd_max_mhz"]
    half_period_v_mrc = ModifiedRamsey_Control_params["cd_period_mv"] * 1e-3 / 2.0
    num_cycles_mrc = ModifiedRamsey_Control_params["num_cycles"]

    ModifiedRamsey_Control_params.setdefault("hysteresis_low", 0.4)
    ModifiedRamsey_Control_params.setdefault("hysteresis_high", 0.6)
    ModifiedRamsey_Control_params.setdefault("window_ms", 0.1)

    # the Ramsey sequence and its analysis keys: the session's MR settings when given
    if ModifiedRamsey_params is not None:
        seq_params_mrc = ModifiedRamsey_params
        df_mrc = float(ModifiedRamsey_params["df"])
        if df_mrc <= 0:
            raise ValueError("ModifiedRamsey_params['df'] must be positive")
        for key_mrc in MRC_SEQUENCE_KEYS:
            if key_mrc in ModifiedRamsey_Control_params and ModifiedRamsey_Control_params[
                key_mrc
            ] != ModifiedRamsey_params.get(key_mrc):
                print(
                    f"[MRC] ModifiedRamsey_Control_params['{key_mrc}']="
                    f"{ModifiedRamsey_Control_params[key_mrc]} ignored: the Ramsey uses "
                    f"ModifiedRamsey_params['{key_mrc}']="
                    f"{ModifiedRamsey_params.get(key_mrc, '<unset: program default>')}"
                )
    else:
        seq_params_mrc = ModifiedRamsey_Control_params
        df_mrc = cd_max_mhz_mrc
        print(
            "WARNING: [MRC] no ModifiedRamsey_params: the Ramsey uses df = cd_max_mhz = "
            f"{cd_max_mhz_mrc} MHz, mr_reps={ModifiedRamsey_Control_params.get('mr_reps')} and "
            f"mr_relax_delay={ModifiedRamsey_Control_params.get('mr_relax_delay', 0.0)} us from "
            "ModifiedRamsey_Control_params, not the modified_ramsey sequence; its rate is not "
            "comparable with an MR record (docs/experiments/modified_ramsey_control.md)"
        )
    # reported only; build_modified_ramsey_cfg validates k
    tau_mrc = int(seq_params_mrc.get("tau_harmonic_k", 1)) / (2.0 * df_mrc)
    ss_shots_mrc = seq_params_mrc.get("ss_calib_shots", 1000)
    ss_recalib_n_mrc = seq_params_mrc.get("ss_recalib_every_n_cycles", None)

    current_voltage_mrc = float(ctx.yoko.query(":SOUR:LEV?"))
    cycle_summary_mrc = []

    # rotates ctx.config["res_phase"] in place; must precede the working config
    # (docs/experiments/active_reset.md)
    if seq_params_mrc.get("use_active_reset", False):
        calibrate_active_reset_readout(ctx)

    cfg = ctx.working_config()

    # the MR record the null is compared with (newest analysed one on disk)
    mr_reference_mrc = latest_modified_ramsey_analysis(ctx.outerFolder)
    # as saved with each MRC record: without the MR bootstrap replicates
    mr_reference_saved_mrc = (
        None
        if mr_reference_mrc is None
        else {k: v for k, v in mr_reference_mrc.items() if k != "lag_covariance_sum"}
    )
    apriori_sep_mrc = None
    sep_voltage_mrc = None
    analog_cal_mrc = None

    sweet_params_mrc = {
        "spec_span": ModifiedRamsey_Control_params["SpecSpan"],
        "spec_num_pts": ModifiedRamsey_Control_params["SpecNumPoints"],
        "spec_reps": ModifiedRamsey_Control_params["reps"],
        "spec_rounds": ModifiedRamsey_Control_params["rounds"],
        "spec_relax_delay": ModifiedRamsey_Control_params["relax_delay"],
        "spec_sigma": ModifiedRamsey_Control_params["sigma"],
        "spec_gain": ModifiedRamsey_Control_params["gain"],
        "spec_qubit_length": ModifiedRamsey_Control_params["qubit_length"],
        "ss_search_df_trigger": ModifiedRamsey_Control_params["df"],
        "ss_accept_sep": ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"],
        "ss_dV": ModifiedRamsey_Control_params["dV"],
        "ss_voltage_min": ModifiedRamsey_Control_params["voltage_min"],
        "ss_voltage_max": ModifiedRamsey_Control_params["voltage_max"],
        "ss_max_tries": ModifiedRamsey_Control_params["max_voltage_tries"],
        "cd_period_mv": ModifiedRamsey_Control_params.get("cd_period_mv"),
    }

    for cycle_idx_mrc in range(num_cycles_mrc):
        print(
            f"\n================ ModifiedRamsey_Control Cycle {cycle_idx_mrc + 1}/{num_cycles_mrc} ================"
        )

        # moves the yoko; strategies in docs/experiments/modified_ramsey_control.md
        f_ge_mrc, V_sweet_mrc, pki_sw, log_mrc = find_sweet_spot(
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            config=cfg,
            save_folder=save_dir_mrc + "/",
            qubit_freq_center=ctx.qubit_frequency_center,
            qubit_readout=ctx.Qubit_Readout,
            yoko=ctx.yoko,
            sweet_params=sweet_params_mrc,
        )
        if V_sweet_mrc is not None:
            current_voltage_mrc = V_sweet_mrc
        for line_mrc in log_mrc:
            print(f"  {line_mrc}")

        S_sweet_mrc = float(pki_sw["peak_sep"]) if pki_sw["peak_sep"] is not None else 0.0
        # sweet_spot_ok False: the search failed the peak-SNR gate (yoko back at the start)
        sweet_verified = pki_sw["sweet_spot_ok"] and (
            pki_sw["peak_sep"] is None or S_sweet_mrc < sweet_max_df_mrc
        )

        print(
            f"[MRC] Cycle {cycle_idx_mrc + 1}: V_sweet={current_voltage_mrc:.6f} V, "
            f"f_ge={f_ge_mrc:.6f} MHz, S_sweet={S_sweet_mrc:.4f} MHz, "
            f"verified={sweet_verified}, tau={tau_mrc:.4f} us"
        )

        if sweet_verified:
            # readout is bias-dependent: calibrate at V_sweet on the first Ramsey, after a
            # bias move, and on the ss_recalib_every_n_cycles cadence
            if (
                apriori_sep_mrc is None
                or abs(current_voltage_mrc - sep_voltage_mrc) > F_GE_BIAS_TOLERANCE_V
                or (
                    ss_recalib_n_mrc is not None
                    and ss_recalib_n_mrc > 0
                    and cycle_idx_mrc % ss_recalib_n_mrc == 0
                )
            ):
                apriori_sep_mrc = get_apriori_separator_from_singleshot(
                    ctx, ss_shots=ss_shots_mrc, current_voltage=current_voltage_mrc
                )
                sep_voltage_mrc = current_voltage_mrc
                I_g_mrc, Q_g_mrc = _extract_iq_from_singleshot_data(apriori_sep_mrc["data_ss"], "g")
                I_e_mrc, Q_e_mrc = _extract_iq_from_singleshot_data(apriori_sep_mrc["data_ss"], "e")
                analog_cal_mrc = calibrate_readout_from_labeled_shots(
                    I_g_mrc, Q_g_mrc, I_e_mrc, Q_e_mrc
                )

            # the modified_ramsey sequence, at the sweet spot
            config_mrc = cfg | build_modified_ramsey_cfg(
                ctx,
                seq_params_mrc,
                f_ge=f_ge_mrc,
                df=df_mrc,
                current_voltage=current_voltage_mrc,
                apriori_sep=apriori_sep_mrc,
            )
            timing_mrc = modified_ramsey_timing(ctx.soccfg, config_mrc)
            config_mrc["modified_ramsey_timing"] = timing_mrc
            rep_period_us_mrc = timing_mrc["scheduled_rep_period_us"]
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}: Ramsey record {config_mrc['reps']} shots x "
                f"{rep_period_us_mrc:.2f} us = "
                f"{config_mrc['reps'] * rep_period_us_mrc * 1e-6:.1f} s"
            )

            Instance_mrc = ModifiedRamsey(
                path="ModifiedRamsey_Control",
                cfg=config_mrc,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
                outerFolder=ctx.outerFolder,
            )
            data_mrc = ModifiedRamsey.acquire(Instance_mrc)
            finish(ModifiedRamsey, Instance_mrc, data_mrc, plotDisp=False, figNum=11)

            raw_i_mrc = np.ravel(np.array(data_mrc["data"]["shots_i"]))
            raw_q_mrc = np.ravel(np.array(data_mrc["data"]["shots_q"]))
            iq_mrc = np.column_stack([raw_i_mrc, raw_q_mrc])
            base_mrc = os.path.join(save_dir_mrc, f"Cycle_{cycle_idx_mrc:03d}_MRC_{timestamp()}")

            # the result: the MR parity analysis (HMM rate, identifiability, ACF)
            # (the SingleShot pi's predicted purity at V_sweet: branches f_ge, f_ge - S_sweet)
            prep_pred_mrc = predicted_singleshot_prep(ctx, f_ge_mrc, S_sweet_mrc)
            settings_mrc = parity_analysis_settings(seq_params_mrc, config_mrc, tag="MRC")
            continuous_mrc = analyze_parity_record(
                seq_params_mrc,
                settings_mrc,
                raw_i_mrc,
                raw_q_mrc,
                data_mrc["data"]["scheduled_rep_period_us"] * 1e-6,
                analog_cal_mrc,
                reset_I=data_mrc["data"].get("reset_shots_i"),
                reset_Q=data_mrc["data"].get("reset_shots_q"),
                out_dir=save_dir_mrc,
                base_name=os.path.basename(base_mrc) + "_continuous",
                readout_prep_e_predicted=prep_pred_mrc,
            )
            summary_mrc = continuous_mrc["summary"]
            acf_amp_mrc = _finite_float(continuous_mrc["acf"].get("amplitude"))
            acf_lags_mrc = np.ravel(np.asarray(continuous_mrc["acf"].get("acf", ()), dtype=float))
            acf_r1_mrc = float(acf_lags_mrc[1]) if acf_lags_mrc.size > 1 else float("nan")
            # the null vs MR: r(1) and the separation-normalised lag-covariance sum (the
            # ACF amplitude is a fit that returns NaN for an uncorrelated record)
            ref_r1_mrc = _finite_float((mr_reference_mrc or {}).get("acf_r1"))
            sep_mrc, sep_source_mrc = true_state_separation(continuous_mrc.get("calibration") or {})
            lag_vs_mr_mrc = null_lag_covariance_vs_mr(
                continuous_mrc["acf"],
                sep_mrc,
                mr_reference_mrc,
                mrc_separation_source=sep_source_mrc,
                mrc_prep_predicted=prep_pred_mrc,
            )
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}: null record identifiable="
                f"{summary_mrc['identifiable']}, gamma01={summary_mrc['gamma01_hz']} Hz, "
                f"r(1)={acf_r1_mrc:.3f}, lag covariance / separation^2="
                f"{lag_vs_mr_mrc['lag_covariance_norm']:.4g}, ACF amplitude={acf_amp_mrc:.4g}"
            )
            if mr_reference_mrc is None:
                print(
                    "[MRC]   no analysed ModifiedRamsey record under "
                    f"{os.path.join(ctx.outerFolder, 'ModifiedRamsey')} to compare with"
                )
            else:
                print(
                    f"[MRC]   most recent MR record {os.path.basename(mr_reference_mrc['file'])}: "
                    f"identifiable={mr_reference_mrc['identifiable']}, "
                    f"gamma01={mr_reference_mrc['gamma01_hz']} Hz, r(1)={ref_r1_mrc:.3f}, "
                    "lag covariance / separation^2="
                    f"{lag_vs_mr_mrc['lag_covariance_norm_mr']:.4g}; MRC/MR lag covariance = "
                    f"{lag_vs_mr_mrc['ratio']:.3g} (95% upper {lag_vs_mr_mrc['upper95']:.3g})"
                    + (f" [{lag_vs_mr_mrc['reason']}]" if lag_vs_mr_mrc["reason"] else "")
                )
                if lag_vs_mr_mrc["warning"]:
                    print(
                        f"[MRC]   WARNING: {lag_vs_mr_mrc['warning']} (prep-corrected ratio "
                        f"{lag_vs_mr_mrc['ratio_prep_corrected']:.3g}, 95% upper "
                        f"{lag_vs_mr_mrc['upper95_prep_corrected']:.3g})"
                    )

            # KMeans + hysteresis: diagnostic plots only (no null distribution)
            (
                binary_states_mrc,
                c0_mrc,
                c1_mrc,
                normal_mrc,
                midpoint_mrc,
                scores_mrc,
                blob_snr_mrc,
            ) = kmeans_split(iq_mrc, min_blob_snr=2.0)
            if not blob_snr_mrc >= 2.0:
                print(
                    f"[MRC] Cycle {cycle_idx_mrc + 1}: single blob "
                    f"(centroid separation / within-cluster spread = "
                    f"{blob_snr_mrc:.2f} < 2.0). No g/e separation -- the diagnostic "
                    "KMeans trace reports all shots as state 0 rather than splitting "
                    "noise in half."
                )

            streamer_rep_period_us_mrc = data_mrc["data"].get(
                "streamer_average_rep_period_us", np.nan
            )
            elapsed_ms_mrc = np.arange(len(raw_i_mrc)) * rep_period_us_mrc * 1e-3

            xlim_mrc, ylim_mrc, I_line_mrc, Q_line_mrc = iq_separator_geometry(
                raw_i_mrc, raw_q_mrc, midpoint_mrc, normal_mrc
            )

            plt.figure(figsize=(6, 6))
            plt.plot(
                raw_i_mrc[binary_states_mrc == 0],
                raw_q_mrc[binary_states_mrc == 0],
                ".",
                alpha=0.5,
                label="State 0",
            )
            plt.plot(
                raw_i_mrc[binary_states_mrc == 1],
                raw_q_mrc[binary_states_mrc == 1],
                ".",
                alpha=0.5,
                label="State 1",
            )
            plt.plot(c0_mrc[0], c0_mrc[1], "o", markersize=10)
            plt.plot(c1_mrc[0], c1_mrc[1], "o", markersize=10)
            plot_separator(midpoint_mrc, I_line_mrc, Q_line_mrc)
            plt.xlabel("I")
            plt.ylabel("Q")
            set_iq_limits(xlim_mrc, ylim_mrc)
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC IQ (sweet spot)\n"
                f"V_sweet={current_voltage_mrc:.6f} V, f_ge={f_ge_mrc:.6f} MHz, "
                f"tau={tau_mrc:.4f} us"
            )
            plt.legend()
            plt.tight_layout()
            plt.savefig(base_mrc + "_iq_labeled.png", dpi=300, bbox_inches="tight")
            plt.close()

            plt.figure(figsize=(10, 4))
            plt.step(elapsed_ms_mrc, binary_states_mrc, where="post", linewidth=1.5)
            plt.plot(elapsed_ms_mrc, binary_states_mrc, "o", markersize=2)
            plt.xlabel("Scheduled time since start (ms)")
            plt.ylabel("Parity state")
            plt.yticks([0, 1])
            plt.ylim(-0.1, 1.1)
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC parity trace (sweet spot control)\n"
                f"tau={tau_mrc:.4f} us, S_sweet={S_sweet_mrc:.4f} MHz"
            )
            plt.tight_layout()
            plt.savefig(base_mrc + "_binary.png", dpi=300, bbox_inches="tight")
            plt.close()

            window_ms_mrc = ModifiedRamsey_Control_params["window_ms"]
            dt_ms_mrc = rep_period_us_mrc * 1e-3
            window_n_mrc = max(1, int(round(window_ms_mrc / dt_ms_mrc)))
            low_thresh_mrc = ModifiedRamsey_Control_params["hysteresis_low"]
            high_thresh_mrc = ModifiedRamsey_Control_params["hysteresis_high"]

            switch_time_ms_mrc = elapsed_ms_mrc[1:]

            state_avg_mrc, state_hyst_mrc, switches_hyst_mrc = hysteresis_parity_trace(
                binary_states_mrc, window_n_mrc, low_thresh_mrc, high_thresh_mrc
            )

            plt.figure(figsize=(10, 4))
            plt.plot(elapsed_ms_mrc, state_avg_mrc, linewidth=1.5, label="Moving average")
            plt.axhline(
                high_thresh_mrc,
                linestyle="--",
                linewidth=1.2,
                label=f"High threshold = {high_thresh_mrc:.2f}",
            )
            plt.axhline(
                low_thresh_mrc,
                linestyle="--",
                linewidth=1.2,
                label=f"Low threshold = {low_thresh_mrc:.2f}",
            )
            plt.xlabel("Scheduled time since start (ms)")
            plt.ylabel("Smoothed parity state")
            plt.ylim(-0.05, 1.05)
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC moving-average parity trace\n"
                f"window={window_n_mrc * dt_ms_mrc:.3f} ms, tau={tau_mrc:.4f} us"
            )
            plt.legend()
            plt.tight_layout()
            plt.savefig(base_mrc + "_state_moving_avg.png", dpi=300, bbox_inches="tight")
            plt.close()

            plt.figure(figsize=(10, 4))
            plt.step(
                elapsed_ms_mrc,
                state_hyst_mrc,
                where="post",
                linewidth=1.5,
                label="Hysteresis state",
            )
            plt.plot(
                elapsed_ms_mrc,
                binary_states_mrc,
                "o",
                markersize=2,
                alpha=0.35,
                label="Raw binary state",
            )
            plt.xlabel("Scheduled time since start (ms)")
            plt.ylabel("Parity state")
            plt.yticks([0, 1])
            plt.ylim(-0.1, 1.1)
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC hysteresis parity trace\n"
                f"low={low_thresh_mrc:.2f}, high={high_thresh_mrc:.2f}, "
                f"window={window_n_mrc * dt_ms_mrc:.3f} ms"
            )
            plt.legend()
            plt.tight_layout()
            plt.savefig(base_mrc + "_state_hysteresis.png", dpi=300, bbox_inches="tight")
            plt.close()

            plt.figure(figsize=(10, 4))
            plt.step(switch_time_ms_mrc, switches_hyst_mrc, where="post", linewidth=1.5)
            plt.plot(switch_time_ms_mrc, switches_hyst_mrc, "o", markersize=2)
            plt.xlabel("Scheduled time since start (ms)")
            plt.ylabel("Jump detected")
            plt.yticks([0, 1])
            plt.ylim(-0.1, 1.1)
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC jumps from hysteresis state\n"
                f"low={low_thresh_mrc:.2f}, high={high_thresh_mrc:.2f}"
            )
            plt.tight_layout()
            plt.savefig(base_mrc + "_state_hysteresis_jumps.png", dpi=300, bbox_inches="tight")
            plt.close()

            # the rate result
            parity_fields_mrc = {
                "parity_identifiable": bool(summary_mrc["identifiable"]),
                "gamma01_hz": _finite_float(summary_mrc["gamma01_hz"]),
                "gamma10_hz": _finite_float(summary_mrc["gamma10_hz"]),
                "gamma01_err_hz": _finite_float(summary_mrc["gamma01_err_hz"]),
                "acf_amplitude": acf_amp_mrc,
                "acf_r1": acf_r1_mrc,
                "acf_r1_mr": ref_r1_mrc,
                "lag_covariance_norm": _finite_float(lag_vs_mr_mrc["lag_covariance_norm"]),
                "lag_covariance_norm_mr": _finite_float(lag_vs_mr_mrc["lag_covariance_norm_mr"]),
                "lag_covariance_ratio_to_mr": _finite_float(lag_vs_mr_mrc["ratio"]),
                "lag_covariance_ratio_upper95": _finite_float(lag_vs_mr_mrc["upper95"]),
                "lag_covariance_ratio_prep_corrected": _finite_float(
                    lag_vs_mr_mrc["ratio_prep_corrected"]
                ),
                "lag_covariance_ratio_upper95_prep_corrected": _finite_float(
                    lag_vs_mr_mrc["upper95_prep_corrected"]
                ),
                "blob_snr": _finite_float(blob_snr_mrc),
            }
            save_record(
                base_mrc,
                config_mrc,
                Instance_mrc,
                elapsed_ms=np.array(elapsed_ms_mrc),
                raw_i=np.array(raw_i_mrc),
                raw_q=np.array(raw_q_mrc),
                scores=np.array(scores_mrc),
                binary_states=np.array(binary_states_mrc),
                state_avg=np.array(state_avg_mrc),
                state_hysteresis=np.array(state_hyst_mrc),
                hysteresis_switches=np.array(switches_hyst_mrc),
                switch_time_ms=np.array(switch_time_ms_mrc),
                centers=np.array([c0_mrc, c1_mrc]),
                midpoint=np.array(midpoint_mrc),
                normal=np.array(normal_mrc),
                V_sweet=np.array(current_voltage_mrc),
                S_sweet_mhz=np.array(S_sweet_mrc),
                f_ge=np.array(f_ge_mrc),
                tau_us=np.array(tau_mrc),
                half_period_v=np.array(half_period_v_mrc),
                cycle_idx=np.array(cycle_idx_mrc),
                hysteresis_low=np.array(low_thresh_mrc),
                hysteresis_high=np.array(high_thresh_mrc),
                moving_avg_window_n=np.array(window_n_mrc),
                moving_avg_window_ms=np.array(window_n_mrc * dt_ms_mrc),
                scheduled_rep_period_us=np.array(rep_period_us_mrc),
                streamer_average_rep_period_us=np.array(streamer_rep_period_us_mrc),
                timing_breakdown=np.array(timing_mrc, dtype=object),
                config=np.array(config_mrc, dtype=object),
                **{k: np.array(v) for k, v in parity_fields_mrc.items()},
                diagnostic_only=np.array(MRC_DIAGNOSTIC_KEYS),
                lag_covariance_ratio_reason=np.array(lag_vs_mr_mrc["reason"]),
                lag_covariance_ratio_warning=np.array(lag_vs_mr_mrc["warning"]),
                mr_reference=np.array(mr_reference_saved_mrc, dtype=object),
            )

            cycle_summary_mrc.append(
                {
                    "cycle_idx": cycle_idx_mrc,
                    "success": True,
                    "V_sweet": current_voltage_mrc,
                    "S_sweet_mhz": S_sweet_mrc,
                    "sweet_verified": True,
                    "f_ge": f_ge_mrc,
                    "tau_us": tau_mrc,
                    "scheduled_rep_period_us": rep_period_us_mrc,
                    "streamer_average_rep_period_us": streamer_rep_period_us_mrc,
                    **parity_fields_mrc,
                    "parity_analysis_warnings": summary_mrc["warnings"],
                    "lag_covariance_ratio_reason": lag_vs_mr_mrc["reason"],
                    "lag_covariance_ratio_warning": lag_vs_mr_mrc["warning"],
                    "mr_reference": mr_reference_saved_mrc,
                    "diagnostic_only": list(MRC_DIAGNOSTIC_KEYS),
                }
            )

        else:
            reason_mrc = (
                f"S_sweet={S_sweet_mrc:.4f} MHz >= threshold {sweet_max_df_mrc} MHz"
                if pki_sw["sweet_spot_ok"]
                else f"search failed the peak-SNR gate, start-voltage SNR {pki_sw['snr']:.2f}"
            )
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}: sweet spot not verified "
                f"({reason_mrc}). Skipping Ramsey run."
            )
            cycle_summary_mrc.append(
                {
                    "cycle_idx": cycle_idx_mrc,
                    "success": False,
                    "stage_failed": "sweet_spot_not_verified",
                    "V_sweet": current_voltage_mrc,
                    "S_sweet_mhz": S_sweet_mrc,
                    "sweet_verified": False,
                }
            )

    save_cycle_summary(save_dir_mrc, cycle_summary_mrc)
