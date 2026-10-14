"""Modified-Ramsey charge-parity runs (parity record and control suite)."""

import json
import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np

from qicklab.analysis.iq import classify_and_average_iq, kmeans_split
from qicklab.analysis.modified_ramsey import analyze_modified_ramsey_record, compare_parity_controls
from qicklab.analysis.plotting import iq_separator_geometry, plot_separator, set_iq_limits
from qicklab.analysis.readout import calibrate_readout_from_labeled_shots
from qicklab.core.experiment import finish
from qicklab.core.io import save_cycle_summary, save_record, timestamp
from qicklab.experiments.modified_ramsey import (
    ModifiedRamsey,
    build_control_variants,
    modified_ramsey_timing,
)
from qicklab.runs.active_reset import calibrate_active_reset_readout, wire_reset_into_mr_cfg
from qicklab.runs.single_shot import (
    _extract_iq_from_singleshot_data,
    get_apriori_separator_from_singleshot,
)
from qicklab.runs.sweet_spot import find_sweet_spot


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

        # tau = k/(2 df) needs odd k: docs/experiments/modified_ramsey.md (choosing tau)
        tau_k_mr = int(ModifiedRamsey_params.get("tau_harmonic_k", 1))
        if tau_k_mr < 1 or tau_k_mr % 2 == 0:
            raise ValueError(
                f"ModifiedRamsey_params['tau_harmonic_k']={tau_k_mr} must be a "
                "positive ODD integer: tau = k/(2*df) only satisfies the parity "
                "pi condition for odd k (even k returns the branches to phase "
                "and gives zero contrast)"
            )
        tau_us_mr = tau_k_mr / (2.0 * chosen_peak_sep_mr)

        mr_cfg = {
            "f_ge": chosen_probe_freq_mr,
            "df": chosen_peak_sep_mr,
            "ramsey_tau_us": tau_us_mr,
            "mr_tau_harmonic_k": tau_k_mr,
            "pi2_gain": ctx.pi2_gain,
            "pi_gain": ctx.qubit_gain,
            "use_pi_pulse": ModifiedRamsey_params.get("use_pi_pulse", False),
            "flip_final_pi2": ModifiedRamsey_params.get("flip_final_pi2", False),
            "symmetric_ramsey": ModifiedRamsey_params.get("symmetric_ramsey", False),
            "max_drive_bandwidth_ratio": ModifiedRamsey_params.get(
                "max_drive_bandwidth_ratio", 1.0
            ),
            "use_active_reset": ModifiedRamsey_params.get("use_active_reset", False),
            "reset_cycles": ModifiedRamsey_params.get("reset_cycles", 1),
            "reset_ground_below_threshold": ModifiedRamsey_params.get(
                "reset_ground_below_threshold", True
            ),
            "reset_readout_relax_delay": ModifiedRamsey_params.get(
                "reset_readout_relax_delay", 1.0
            ),
            "post_reset_wait": ModifiedRamsey_params.get("post_reset_wait", 0.0),
            "mr_relax_delay": ModifiedRamsey_params.get("mr_relax_delay", 0.0),
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
            "reps": ModifiedRamsey_params["mr_reps"],
            "rounds": 1,
            "current_voltage": current_voltage_mr,
            "Qubit_number": ctx.Qubit_Readout,
        }
        # forwarded only when set, so the program's 0.5 us default/floor applies otherwise
        if "reset_read_latency_us" in ModifiedRamsey_params:
            mr_cfg["reset_read_latency_us"] = ModifiedRamsey_params["reset_read_latency_us"]
        # a manual readout_threshold wins over the one derived from the current separator
        if ModifiedRamsey_params.get("readout_threshold") is not None:
            mr_cfg["readout_threshold"] = ModifiedRamsey_params["readout_threshold"]
        elif mr_cfg["use_active_reset"]:
            wire_reset_into_mr_cfg(mr_cfg, apriori_sep_mr)
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
        mapping_probabilities_mr = (
            ModifiedRamsey_params.get("mapping_p_e_state0", 0.1),
            ModifiedRamsey_params.get("mapping_p_e_state1", 0.9),
        )
        # min_emission_snr: do not lower (CSTQ03 Q2, 2026-08-04), docs/experiments/modified_ramsey.md
        hmm_kwargs_mr = dict(ModifiedRamsey_params.get("hmm_kwargs") or {})
        if ModifiedRamsey_params.get("hmm_min_emission_snr") is not None:
            hmm_kwargs_mr["min_emission_snr"] = float(ModifiedRamsey_params["hmm_min_emission_snr"])
        continuous_mr = None
        analysis_enabled_mr = ModifiedRamsey_params.get("parity_analysis_enabled", True)
        if analysis_enabled_mr:
            continuous_mr = analyze_modified_ramsey_record(
                raw_i_mr,
                raw_q_mr,
                data_mr["data"]["scheduled_rep_period_us"] * 1e-6,
                analog_cal_mr,
                drift_timescale_s=(ModifiedRamsey_params.get("drift_window_ms", 200.0) * 1e-3),
                expected_dwell_s=(
                    ModifiedRamsey_params.get("expected_parity_dwell_ms", 2.5) * 1e-3
                ),
                symmetric_hmm=ModifiedRamsey_params.get("hmm_symmetric", True),
                n_boot=ModifiedRamsey_params.get("hmm_bootstrap_samples", 0),
                mapping_probabilities=mapping_probabilities_mr,
                mapping_probabilities_calibrated=ModifiedRamsey_params.get(
                    "mapping_probabilities_calibrated", False
                ),
                reset_I=data_mr["data"].get("reset_shots_i"),
                reset_Q=data_mr["data"].get("reset_shots_q"),
                out_dir=save_dir_mr,
                base_name=os.path.basename(base_mr) + "_continuous",
                hmm_kwargs=hmm_kwargs_mr,
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
                tau_offset_frac=ModifiedRamsey_params.get("control_tau_offset_frac", 0.25),
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
                control_analysis_mr = analyze_modified_ramsey_record(
                    control_data_mr["data"]["shots_i"],
                    control_data_mr["data"]["shots_q"],
                    control_data_mr["data"]["scheduled_rep_period_us"] * 1e-6,
                    analog_cal_mr,
                    drift_timescale_s=(ModifiedRamsey_params.get("drift_window_ms", 200.0) * 1e-3),
                    expected_dwell_s=(
                        ModifiedRamsey_params.get("expected_parity_dwell_ms", 2.5) * 1e-3
                    ),
                    symmetric_hmm=ModifiedRamsey_params.get("hmm_symmetric", True),
                    n_boot=ModifiedRamsey_params.get("hmm_bootstrap_samples", 0),
                    mapping_probabilities=mapping_probabilities_mr,
                    mapping_probabilities_calibrated=ModifiedRamsey_params.get(
                        "mapping_probabilities_calibrated", False
                    ),
                    reset_I=control_data_mr["data"].get("reset_shots_i"),
                    reset_Q=control_data_mr["data"].get("reset_shots_q"),
                    out_dir=save_dir_mr,
                    base_name=(os.path.basename(base_mr) + f"_{control_type_mr}"),
                    hmm_kwargs=hmm_kwargs_mr,  # same gate as the parity record
                )
                analyzed_controls_mr.append(
                    {
                        "label": control_type_mr,
                        "control_type": control_type_mr,
                        "hmm": control_analysis_mr["hmm"],
                        "acf": control_analysis_mr["acf"],
                        "occupancy_state1": control_analysis_mr["summary"]["occupancy_state1"],
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


def run_modified_ramsey_control(ctx, ModifiedRamsey_Control_params):
    save_dir_mrc = os.path.join(ctx.outerFolder, "ModifiedRamsey_Control")
    os.makedirs(save_dir_mrc, exist_ok=True)

    sweet_max_df_mrc = ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"]
    cd_max_mhz_mrc = ModifiedRamsey_Control_params["cd_max_mhz"]
    half_period_v_mrc = ModifiedRamsey_Control_params["cd_period_mv"] * 1e-3 / 2.0
    num_cycles_mrc = ModifiedRamsey_Control_params["num_cycles"]

    ModifiedRamsey_Control_params.setdefault("hysteresis_low", 0.4)
    ModifiedRamsey_Control_params.setdefault("hysteresis_high", 0.6)
    ModifiedRamsey_Control_params.setdefault("window_ms", 0.1)

    current_voltage_mrc = float(ctx.yoko.query(":SOUR:LEV?"))
    cycle_summary_mrc = []

    cfg = ctx.working_config()

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
        sweet_verified = pki_sw["peak_sep"] is None or S_sweet_mrc < sweet_max_df_mrc

        # reported only; the program derives tau from df = cd_max_mhz
        tau_mrc = 1.0 / (2.0 * cd_max_mhz_mrc)

        print(
            f"[MRC] Cycle {cycle_idx_mrc + 1}: V_sweet={current_voltage_mrc:.6f} V, "
            f"f_ge={f_ge_mrc:.6f} MHz, S_sweet={S_sweet_mrc:.4f} MHz, "
            f"verified={sweet_verified}, tau={tau_mrc:.4f} us"
        )

        if sweet_verified:
            # not yet the same sequence as modified_ramsey: docs/experiments/modified_ramsey_control.md
            mr_cfg_mrc = {
                "f_ge": f_ge_mrc,
                "df": cd_max_mhz_mrc,
                "pi2_gain": ctx.pi2_gain,
                "pi_gain": ctx.qubit_gain,
                "use_pi_pulse": ModifiedRamsey_Control_params.get("use_pi_pulse", False),
                "flip_final_pi2": ModifiedRamsey_Control_params.get("flip_final_pi2", False),
                "symmetric_ramsey": ModifiedRamsey_Control_params.get("symmetric_ramsey", False),
                "use_active_reset": ModifiedRamsey_Control_params.get("use_active_reset", False),
                "reset_cycles": ModifiedRamsey_Control_params.get("reset_cycles", 1),
                "reset_ground_below_threshold": ModifiedRamsey_Control_params.get(
                    "reset_ground_below_threshold", True
                ),
                "reset_readout_relax_delay": ModifiedRamsey_Control_params.get(
                    "reset_readout_relax_delay", 1.0
                ),
                "post_reset_wait": ModifiedRamsey_Control_params.get("post_reset_wait", 0.0),
                "sigma": ctx.qubit_sigma,
                "flattop_length": ctx.qubit_flattop,
                "mr_relax_delay": ModifiedRamsey_Control_params.get("mr_relax_delay", 0.0),
                "reps": ModifiedRamsey_Control_params["mr_reps"],
                "rounds": 1,
                "current_voltage": current_voltage_mrc,
                "Qubit_number": ctx.Qubit_Readout,
            }
            # forwarded only when set, so the program's 0.5 us default/floor applies otherwise
            if "reset_read_latency_us" in ModifiedRamsey_Control_params:
                mr_cfg_mrc["reset_read_latency_us"] = ModifiedRamsey_Control_params[
                    "reset_read_latency_us"
                ]
            config_mrc = cfg | mr_cfg_mrc
            timing_mrc = modified_ramsey_timing(ctx.soccfg, config_mrc)
            config_mrc["modified_ramsey_timing"] = timing_mrc

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
                    f"{blob_snr_mrc:.2f} < 2.0). No g/e separation -- reporting "
                    "all shots as state 0 (NO SWITCHING) rather than splitting "
                    "noise in half."
                )

            rep_period_us_mrc = timing_mrc["scheduled_rep_period_us"]
            streamer_rep_period_us_mrc = data_mrc["data"].get(
                "streamer_average_rep_period_us", np.nan
            )
            elapsed_ms_mrc = np.arange(len(raw_i_mrc)) * rep_period_us_mrc * 1e-3

            base_mrc = os.path.join(save_dir_mrc, f"Cycle_{cycle_idx_mrc:03d}_MRC_{timestamp()}")

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

            kernel_mrc = np.ones(window_n_mrc, dtype=float) / window_n_mrc
            state_avg_mrc = np.convolve(binary_states_mrc.astype(float), kernel_mrc, mode="same")

            state_hyst_mrc = np.empty_like(binary_states_mrc)
            current_state_mrc = int(binary_states_mrc[0])
            for idx_mrc, val_mrc in enumerate(state_avg_mrc):
                if val_mrc >= high_thresh_mrc:
                    current_state_mrc = 1
                elif val_mrc <= low_thresh_mrc:
                    current_state_mrc = 0
                state_hyst_mrc[idx_mrc] = current_state_mrc

            switches_hyst_mrc = (np.diff(state_hyst_mrc) != 0).astype(int)

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

            save_record(
                base_mrc,
                config_mrc,
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
                }
            )

        else:
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}: sweet spot not verified "
                f"(S_sweet={S_sweet_mrc:.4f} MHz >= threshold {sweet_max_df_mrc} MHz). "
                f"Skipping Ramsey run."
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
