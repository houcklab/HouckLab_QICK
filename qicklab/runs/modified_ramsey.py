"""Modified-Ramsey charge-parity runs (parity record and control suite)."""

import json
import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import KMeans

from qicklab.analysis.iq import classify_and_average_iq
from qicklab.analysis.modified_ramsey import analyze_modified_ramsey_record, compare_parity_controls
from qicklab.analysis.readout import calibrate_readout_from_labeled_shots
from qicklab.experiments.modified_ramsey import ModifiedRamsey, build_control_variants, modified_ramsey_timing
from qicklab.runs.active_reset import calibrate_active_reset_readout, wire_reset_into_mr_cfg
from qicklab.runs.single_shot import _extract_iq_from_singleshot_data, get_apriori_separator_from_singleshot
from qicklab.runs.sweet_spot import find_sweet_spot


def run_modified_ramsey(ctx, ModifiedRamsey_params):
    date_tag_mr = datetime.now().strftime("%Y_%m_%d")
    save_dir_mr = os.path.join(ctx.outerFolder, "ModifiedRamsey", date_tag_mr)
    os.makedirs(save_dir_mr, exist_ok=True)

    # Branch separation setting the parity-phase condition tau = 1/(2*df).
    # This is a CONFIGURED value. The two-tone doublet search that used to
    # measure it -- walking the yoko across a voltage window looking for a
    # resolved parity doublet -- has been removed: it never worked reliably and
    # was not used. Set ModifiedRamsey_params["df"] from an independent doublet
    # measurement and treat the realized tau as conditional on it.
    df_mr = float(ModifiedRamsey_params["df"])
    if df_mr <= 0:
        raise ValueError("ModifiedRamsey_params['df'] must be positive")
    # Upper parity branch. Defaults to the qubit centre frequency; override via
    # ModifiedRamsey_params["f_ge"] when the doublet position is known.
    f_ge_mr = float(
        ModifiedRamsey_params.get("f_ge", ctx.qubit_frequency_center))
    num_cycles_mr = ModifiedRamsey_params["num_cycles"]

    # Recorded for provenance only: this routine never moves the yoko.
    current_voltage_mr = float(ctx.yoko.query(":SOUR:LEV?"))

    cycle_summary_mr = []

    apriori_sep_mr = None

    # I-axis rotation + threshold calibration for hardware active reset.
    # Rotates config["res_phase"] IN PLACE so |g>/|e> separate along I (the
    # tProc feedback thresholds on raw I only) and measures the threshold off
    # the rotated blobs. Must run BEFORE the apriori separator below so shot
    # classification uses the same rotated readout frame.
    if ModifiedRamsey_params.get("use_active_reset", False):
        if not ModifiedRamsey_params.get("use_apriori_separator", False):
            raise RuntimeError(
                "use_active_reset=True requires use_apriori_separator=True "
                "(the reset threshold is derived from the SingleShot separator)."
            )
        calibrate_active_reset_readout(ctx)

    if ModifiedRamsey_params.get("use_apriori_separator", False):
        apriori_sep_mr = get_apriori_separator_from_singleshot(
            ctx,
            ss_shots=ModifiedRamsey_params.get("ss_calib_shots", 1000)
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
                    ctx,
                    ss_shots=ModifiedRamsey_params.get("ss_calib_shots", 1000)
                )
        print(f"\n================ ModifiedRamsey Cycle {cycle_idx_mr + 1}/{num_cycles_mr} ================")

        # f_ge and df come straight from configuration; there is no
        # doublet search and no voltage walk.
        chosen_probe_freq_mr = f_ge_mr
        chosen_peak_sep_mr = df_mr

        # ---------- run Modified Ramsey at the configured f_ge and df ----------
        # The parity condition is |relative phase| = pi MODULO 2*pi, so
        # tau = k/(2*df) works for ANY ODD k, all with identical mapping
        # contrast. k=1 is the shortest (least T2 decay) but needs
        # 4*sigma < tau; a large df can make that impossible at a sigma you
        # cannot shorten. Raising k to the next odd value relieves the timing
        # constraint WITHOUT touching sigma and WITHOUT changing the physical
        # branch separation. Even k would put the branches back in phase and
        # destroy the mapping, so reject it loudly.
        tau_k_mr = int(ModifiedRamsey_params.get("tau_harmonic_k", 1))
        if tau_k_mr < 1 or tau_k_mr % 2 == 0:
            raise ValueError(
                f"ModifiedRamsey_params['tau_harmonic_k']={tau_k_mr} must be a "
                "positive ODD integer: tau = k/(2*df) only satisfies the parity "
                "pi condition for odd k (even k returns the branches to phase "
                "and gives zero contrast)")
        tau_us_mr = tau_k_mr / (2.0 * chosen_peak_sep_mr)

        mr_cfg = {
            "f_ge": chosen_probe_freq_mr,
            "df": chosen_peak_sep_mr,
            # Programmed delay only; cfg["df"] above stays the PHYSICAL branch
            # separation, so the saved record still reports the real splitting.
            "ramsey_tau_us": tau_us_mr,
            "mr_tau_harmonic_k": tau_k_mr,
            "pi2_gain": ctx.pi2_gain,
            "pi_gain": ctx.qubit_gain,
            "use_pi_pulse": ModifiedRamsey_params.get("use_pi_pulse", False),
            # Parity -> state mapping and drive scheme (opt-in; defaults preserve
            # the original standard-scheme behavior).
            "flip_final_pi2": ModifiedRamsey_params.get("flip_final_pi2", False),
            "symmetric_ramsey": ModifiedRamsey_params.get("symmetric_ramsey", False),
            # Ceiling on branch_detuning / pi2_Rabi. Above 1.0 the off-resonant
            # branch is barely rotated and the mapping degrades; the program
            # RAISES past this so a contrast-free record is never mistaken for
            # data. Raise it only deliberately, and read the saved
            # drive_bandwidth_ratio when interpreting the result.
            "max_drive_bandwidth_ratio": ModifiedRamsey_params.get(
                "max_drive_bandwidth_ratio", 1.0),
            # Hardware active reset to |g> per shot (opt-in). See ModifiedRamsey
            # docstring: requires readout_threshold + I-axis g/e separation.
            "use_active_reset": ModifiedRamsey_params.get("use_active_reset", False),
            "reset_cycles": ModifiedRamsey_params.get("reset_cycles", 1),
            "reset_ground_below_threshold": ModifiedRamsey_params.get("reset_ground_below_threshold", True),
            "reset_readout_relax_delay": ModifiedRamsey_params.get("reset_readout_relax_delay", 1.0),
            "post_reset_wait": ModifiedRamsey_params.get("post_reset_wait", 0.0),
            "mr_relax_delay": ModifiedRamsey_params.get("mr_relax_delay", 0.0),
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
            "reps": ModifiedRamsey_params["mr_reps"],
            "rounds": 1,
            "current_voltage": current_voltage_mr,
            "Qubit_number": ctx.Qubit_Readout,
        }
        # Wire the feedback threshold. A manually set
        # ModifiedRamsey_params["readout_threshold"] takes precedence; otherwise
        # derive threshold + |g>-below-threshold sign from the CURRENT apriori
        # separator (rotated frame, so it tracks each ss recalibration).
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
            outerFolder=ctx.outerFolder
        )
        data_mr = ModifiedRamsey.acquire(Instance_mr)
        ModifiedRamsey.display(Instance_mr, data_mr, plotDisp=False, figNum=10)
        ModifiedRamsey.save_data(Instance_mr, data_mr)
        ModifiedRamsey.save_config(Instance_mr)

        # ---------- continuous analog parity analysis (primary output) ------
        raw_i_mr = np.ravel(np.array(data_mr["data"]["shots_i"]))
        raw_q_mr = np.ravel(np.array(data_mr["data"]["shots_q"]))

        if apriori_sep_mr is None:
            raise RuntimeError("ModifiedRamsey requires a labeled SingleShot calibration.")

        timestamp_mr = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        base_mr = os.path.join(
            save_dir_mr, f"Cycle_{cycle_idx_mr:03d}_MR_{timestamp_mr}")
        I_g_mr, Q_g_mr = _extract_iq_from_singleshot_data(
            apriori_sep_mr["data_ss"], "g")
        I_e_mr, Q_e_mr = _extract_iq_from_singleshot_data(
            apriori_sep_mr["data_ss"], "e")
        analog_cal_mr = calibrate_readout_from_labeled_shots(
            I_g_mr, Q_g_mr, I_e_mr, Q_e_mr)
        mapping_probabilities_mr = (
            ModifiedRamsey_params.get("mapping_p_e_state0", 0.1),
            ModifiedRamsey_params.get("mapping_p_e_state1", 0.9),
        )
        # Extra kwargs forwarded to fit_two_state_hmm. The one that matters here
        # is min_emission_snr, which gates on PER-SAMPLE emission separation and
        # defaults to 0.7 inside fit_two_state_hmm. That gate is the wrong
        # quantity for a heavily oversampled telegraph: with a rep period of
        # ~11.75 us and a 2.5 ms dwell there are ~213 samples per dwell, so the
        # information per dwell is per_sample_snr * sqrt(213) ~= 15x the
        # per-sample figure. Forward-backward already accumulates that, which is
        # why the rate is recoverable well below the per-sample gate (see
        # test_hmm_moderate_contrast in test_ModifiedRamseyParity_offline.py).
        # Lower it deliberately and cross-check HMM against ACF/PSD; expect the
        # posterior-ambiguity warning to fire, which correctly says "do not
        # trust individual Viterbi samples", NOT "the rate is wrong".
        hmm_kwargs_mr = dict(ModifiedRamsey_params.get("hmm_kwargs") or {})
        if ModifiedRamsey_params.get("hmm_min_emission_snr") is not None:
            hmm_kwargs_mr["min_emission_snr"] = float(
                ModifiedRamsey_params["hmm_min_emission_snr"])
        continuous_mr = None
        if ModifiedRamsey_params.get("parity_analysis_enabled", True):
            continuous_mr = analyze_modified_ramsey_record(
                raw_i_mr,
                raw_q_mr,
                data_mr["data"]["scheduled_rep_period_us"] * 1e-6,
                analog_cal_mr,
                drift_timescale_s=(
                    ModifiedRamsey_params.get("drift_window_ms", 200.0)
                    * 1e-3),
                expected_dwell_s=(
                    ModifiedRamsey_params.get("expected_parity_dwell_ms", 2.5)
                    * 1e-3),
                symmetric_hmm=ModifiedRamsey_params.get("hmm_symmetric", True),
                n_boot=ModifiedRamsey_params.get("hmm_bootstrap_samples", 0),
                mapping_probabilities=mapping_probabilities_mr,
                mapping_probabilities_calibrated=ModifiedRamsey_params.get(
                    "mapping_probabilities_calibrated", False),
                reset_I=data_mr["data"].get("reset_shots_i"),
                reset_Q=data_mr["data"].get("reset_shots_q"),
                out_dir=save_dir_mr,
                base_name=os.path.basename(base_mr) + "_continuous",
                hmm_kwargs=hmm_kwargs_mr,
            )
            print(
                "[ModifiedRamsey] continuous-analysis verdict: "
                f"identifiable={continuous_mr['summary']['identifiable']}, "
                f"gamma={continuous_mr['summary']['gamma01_hz']} Hz")

            # Optional interleaved validation controls. They use the same
            # voltage, calibration, time base, and continuous-emission model as
            # the parity record. Configure a cadence to bound added run time.
            control_names_mr = tuple(
                ModifiedRamsey_params.get("validation_controls", ()))
            control_every_mr = int(
                ModifiedRamsey_params.get(
                    "validation_controls_every_n_cycles", 1))
            if control_every_mr <= 0:
                raise ValueError(
                    "validation_controls_every_n_cycles must be positive")
            if control_names_mr and cycle_idx_mr % control_every_mr == 0:
                analyzed_controls_mr = []
                skipped_controls_mr = []
                for control_mr in build_control_variants(
                        config_mr, include=control_names_mr,
                        tau_offset_frac=ModifiedRamsey_params.get(
                            "control_tau_offset_frac", 0.25),
                        detuning_mhz=ModifiedRamsey_params.get(
                            "control_detuning_mhz")):
                    if control_mr["cfg"] is None:
                        skipped_controls_mr.append({
                            "control_type": control_mr["control_type"],
                            "reason": control_mr["skip_reason"],
                        })
                        continue
                    control_cfg_mr = control_mr["cfg"]
                    control_timing_mr = modified_ramsey_timing(
                        ctx.soccfg, control_cfg_mr)
                    control_cfg_mr["modified_ramsey_timing"] = control_timing_mr
                    control_inst_mr = ModifiedRamsey(
                        path="ModifiedRamsey_Controls",
                        cfg=control_cfg_mr,
                        soc=ctx.soc,
                        soccfg=ctx.soccfg,
                        outerFolder=ctx.outerFolder,
                    )
                    control_data_mr = ModifiedRamsey.acquire(control_inst_mr)
                    ModifiedRamsey.save_data(control_inst_mr, control_data_mr)
                    ModifiedRamsey.save_config(control_inst_mr)
                    control_type_mr = control_mr["control_type"]
                    control_analysis_mr = analyze_modified_ramsey_record(
                        control_data_mr["data"]["shots_i"],
                        control_data_mr["data"]["shots_q"],
                        control_data_mr["data"][
                            "scheduled_rep_period_us"] * 1e-6,
                        analog_cal_mr,
                        drift_timescale_s=(
                            ModifiedRamsey_params.get(
                                "drift_window_ms", 200.0) * 1e-3),
                        expected_dwell_s=(
                            ModifiedRamsey_params.get(
                                "expected_parity_dwell_ms", 2.5) * 1e-3),
                        symmetric_hmm=ModifiedRamsey_params.get(
                            "hmm_symmetric", True),
                        n_boot=ModifiedRamsey_params.get(
                            "hmm_bootstrap_samples", 0),
                        mapping_probabilities=mapping_probabilities_mr,
                        mapping_probabilities_calibrated=ModifiedRamsey_params.get(
                            "mapping_probabilities_calibrated", False),
                        reset_I=control_data_mr["data"].get("reset_shots_i"),
                        reset_Q=control_data_mr["data"].get("reset_shots_q"),
                        out_dir=save_dir_mr,
                        base_name=(os.path.basename(base_mr)
                                   + f"_{control_type_mr}"),
                        # SAME gate as the parity record: comparing a control
                        # fitted under a different identifiability threshold
                        # would not be a control.
                        hmm_kwargs=hmm_kwargs_mr,
                    )
                    analyzed_controls_mr.append({
                        "label": control_type_mr,
                        "control_type": control_type_mr,
                        "hmm": control_analysis_mr["hmm"],
                        "acf": control_analysis_mr["acf"],
                        "occupancy_state1": control_analysis_mr[
                            "summary"]["occupancy_state1"],
                    })
                comparison_mr = compare_parity_controls(
                    {
                        "label": "parity",
                        "hmm": continuous_mr["hmm"],
                        "acf": continuous_mr["acf"],
                        "occupancy_state1": continuous_mr[
                            "summary"]["occupancy_state1"],
                    },
                    analyzed_controls_mr,
                )
                comparison_mr["skipped"] = skipped_controls_mr
                if skipped_controls_mr:
                    comparison_mr["all_expected"] = False
                with open(base_mr + "_control_comparison.json", "w") as f:
                    json.dump(comparison_mr, f, indent=2, default=float)

        # Retain the legacy hard-threshold plots as diagnostics only. Rate
        # inference above uses every unthresholded IQ sample.
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
        streamer_rep_period_us_mr = data_mr["data"].get(
            "streamer_average_rep_period_us", np.nan
        )

        elapsed_ms_mr = np.arange(len(raw_i_mr)) * rep_period_us * 1e-3
        # +0.5 -> label each N-shot bin at its CENTRE, not its left edge, so the
        # averaged trace lines up with the raw single-shot trace above it.
        elapsed_avg_ms_mr = (
                (np.arange(len(excited_avg_mr)) + 0.5)
                * average_n_shots_mr * rep_period_us * 1e-3
        )


        I_min_mr, I_max_mr = raw_i_mr.min(), raw_i_mr.max()
        Q_min_mr, Q_max_mr = raw_q_mr.min(), raw_q_mr.max()
        I_pad_mr = 0.05 * (I_max_mr - I_min_mr if I_max_mr > I_min_mr else 1.0)
        Q_pad_mr = 0.05 * (Q_max_mr - Q_min_mr if Q_max_mr > Q_min_mr else 1.0)
        I_line_mr = np.linspace(I_min_mr - I_pad_mr, I_max_mr + I_pad_mr, 400)

        vertical_line_mr = np.abs(normal_mr[1]) < 1e-12
        if not vertical_line_mr:
            Q_line_mr = midpoint_mr[1] - (normal_mr[0] / normal_mr[1]) * (I_line_mr - midpoint_mr[0])

        # IQ scatter with calibrated SingleShot separator
        plt.figure(figsize=(6, 6))
        plt.plot(raw_i_mr[binary_states_mr == 0], raw_q_mr[binary_states_mr == 0],
                 ".", alpha=0.5, label="Assigned 0")
        plt.plot(raw_i_mr[binary_states_mr == 1], raw_q_mr[binary_states_mr == 1],
                 ".", alpha=0.5, label="Assigned 1")
        plt.plot(c0_mr[0], c0_mr[1], "o", markersize=10, label="SingleShot g center")
        plt.plot(c1_mr[0], c1_mr[1], "o", markersize=10, label="SingleShot e center")

        if vertical_line_mr:
            plt.axvline(midpoint_mr[0], linestyle="--", linewidth=2, label="g/e separator")
        else:
            plt.plot(I_line_mr, Q_line_mr, "--", linewidth=2, label="g/e separator")

        plt.xlabel("I")
        plt.ylabel("Q")
        plt.xlim(I_min_mr - I_pad_mr, I_max_mr + I_pad_mr)
        plt.ylim(Q_min_mr - Q_pad_mr, Q_max_mr + Q_pad_mr)
        plt.gca().set_aspect("equal", adjustable="box")
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey IQ\n"
            f"V={current_voltage_mr:.6f} V, f_ge={chosen_probe_freq_mr:.6f} MHz, "
            f"tau={tau_us_mr:.4f} us"
        )
        plt.legend()
        plt.tight_layout()
        plt.savefig(base_mr + "_iq_labeled_apriori.png", dpi=300, bbox_inches="tight")
        plt.close()

        # Raw 0/1 shot trace
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

        # Averaged 0-to-1 population trace
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

        np.savez(
            base_mr + ".npz",
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

        with open(base_mr + "_config.json", "w") as f:
            json.dump(config_mr, f, indent=2, default=float)

        cycle_summary_mr.append({
            "cycle_idx": cycle_idx_mr,
            "success": True,
            "final_voltage": current_voltage_mr,
            "chosen_probe_freq": chosen_probe_freq_mr,
            "peak_sep": chosen_peak_sep_mr,
            "tau_us": tau_us_mr,
            "scheduled_rep_period_us": rep_period_us,
            "streamer_average_rep_period_us": streamer_rep_period_us_mr,
            "parity_identifiable": (
                continuous_mr["summary"]["identifiable"]
                if continuous_mr is not None else None),
            "gamma01_hz": (
                continuous_mr["summary"]["gamma01_hz"]
                if continuous_mr is not None else None),
            "gamma10_hz": (
                continuous_mr["summary"]["gamma10_hz"]
                if continuous_mr is not None else None),
            "parity_analysis_warnings": (
                continuous_mr["summary"]["warnings"]
                if continuous_mr is not None else []),
        })

    summary_path_mr = os.path.join(
        save_dir_mr,
        f"CycleSummary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    )
    with open(summary_path_mr, "w") as f:
        json.dump(cycle_summary_mr, f, indent=2, default=float)


def run_modified_ramsey_control(ctx, ModifiedRamsey_Control_params):
    save_dir_mrc = os.path.join(ctx.outerFolder, "ModifiedRamsey_Control")
    os.makedirs(save_dir_mrc, exist_ok=True)

    sweet_max_df_mrc  = ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"]
    cd_max_mhz_mrc    = ModifiedRamsey_Control_params["cd_max_mhz"]
    half_period_v_mrc = ModifiedRamsey_Control_params["cd_period_mv"] * 1e-3 / 2.0
    num_cycles_mrc    = ModifiedRamsey_Control_params["num_cycles"]

    ModifiedRamsey_Control_params.setdefault("hysteresis_low",  0.4)
    ModifiedRamsey_Control_params.setdefault("hysteresis_high", 0.6)
    ModifiedRamsey_Control_params.setdefault("window_ms",       0.1)

    current_voltage_mrc = float(ctx.yoko.query(":SOUR:LEV?"))
    cycle_summary_mrc = []

    cfg = ctx.working_config()

    # Parameters forwarded to find_sweet_spot on every cycle.
    # Spec settings and search bounds come directly from ModifiedRamsey_Control_params
    # so the user only has to edit one dict.
    sweet_params_mrc = {
        "spec_span":            ModifiedRamsey_Control_params["SpecSpan"],
        "spec_num_pts":         ModifiedRamsey_Control_params["SpecNumPoints"],
        "spec_reps":            ModifiedRamsey_Control_params["reps"],
        "spec_rounds":          ModifiedRamsey_Control_params["rounds"],
        "spec_relax_delay":     ModifiedRamsey_Control_params["relax_delay"],
        "spec_sigma":           ModifiedRamsey_Control_params["sigma"],
        "spec_gain":            ModifiedRamsey_Control_params["gain"],
        "spec_qubit_length":    ModifiedRamsey_Control_params["qubit_length"],
        "ss_search_df_trigger": ModifiedRamsey_Control_params["df"],
        "ss_accept_sep":        ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"],
        "ss_dV":                ModifiedRamsey_Control_params["dV"],
        "ss_voltage_min":       ModifiedRamsey_Control_params["voltage_min"],
        "ss_voltage_max":       ModifiedRamsey_Control_params["voltage_max"],
        "ss_max_tries":         ModifiedRamsey_Control_params["max_voltage_tries"],
        "cd_period_mv":         ModifiedRamsey_Control_params.get("cd_period_mv"),
    }

    for cycle_idx_mrc in range(num_cycles_mrc):
        print(f"\n================ ModifiedRamsey_Control Cycle {cycle_idx_mrc + 1}/{num_cycles_mrc} ================")

        # ── Sweet-spot search ────────────────────────────────────────────────
        # Uses the two-strategy mAutoCoherence search:
        #   Strategy A (cd_period_mv known): one initial spec + one half-period
        #     jump → typically finds the sweet spot in 1-2 acquisitions.
        #   Strategy B (fallback): incremental walk tracking minimum separation.
        f_ge_mrc, V_sweet_mrc, pki_sw, log_mrc = find_sweet_spot(
            soc=ctx.soc, soccfg=ctx.soccfg,
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

        S_sweet_mrc   = float(pki_sw["peak_sep"]) if pki_sw["peak_sep"] is not None else 0.0
        sweet_verified = (pki_sw["peak_sep"] is None or S_sweet_mrc < sweet_max_df_mrc)

        # tau for Ramsey: maximum sensitivity is at tau = 1 / (2 * max_dispersion).
        # We use cd_max_mhz (from the independent calibration) rather than a
        # measured S1, since the search no longer requires a detour to a
        # large-separation voltage.
        tau_mrc = 1.0 / (2.0 * cd_max_mhz_mrc)

        print(
            f"[MRC] Cycle {cycle_idx_mrc + 1}: V_sweet={current_voltage_mrc:.6f} V, "
            f"f_ge={f_ge_mrc:.6f} MHz, S_sweet={S_sweet_mrc:.4f} MHz, "
            f"verified={sweet_verified}, tau={tau_mrc:.4f} us"
        )

        # ── Run Modified Ramsey at the sweet spot ────────────────────────────
        if sweet_verified:
            # The control must run the SAME sequence as the measurement it
            # controls, otherwise a null result is uninterpretable. Carry the
            # sequence-shaping keys explicitly (pi_gain is also required by the
            # program whenever use_pi_pulse or use_active_reset is on).
            mr_cfg_mrc = {
                "f_ge":           f_ge_mrc,
                "df":             cd_max_mhz_mrc,
                "pi2_gain":       ctx.pi2_gain,
                "pi_gain":        ctx.qubit_gain,
                "use_pi_pulse":   ModifiedRamsey_Control_params.get("use_pi_pulse", False),
                "flip_final_pi2": ModifiedRamsey_Control_params.get("flip_final_pi2", False),
                "symmetric_ramsey": ModifiedRamsey_Control_params.get("symmetric_ramsey", False),
                "use_active_reset": ModifiedRamsey_Control_params.get("use_active_reset", False),
                "reset_cycles":   ModifiedRamsey_Control_params.get("reset_cycles", 1),
                "reset_ground_below_threshold": ModifiedRamsey_Control_params.get(
                    "reset_ground_below_threshold", True),
                "reset_readout_relax_delay": ModifiedRamsey_Control_params.get(
                    "reset_readout_relax_delay", 1.0),
                "post_reset_wait": ModifiedRamsey_Control_params.get("post_reset_wait", 0.0),
                "sigma":          ctx.qubit_sigma,
                "flattop_length": ctx.qubit_flattop,
                "mr_relax_delay": ModifiedRamsey_Control_params.get("mr_relax_delay", 0.0),
                "reps":           ModifiedRamsey_Control_params["mr_reps"],
                "rounds":         1,
                "current_voltage": current_voltage_mrc,
                "Qubit_number":   ctx.Qubit_Readout,
            }
            config_mrc = cfg | mr_cfg_mrc
            timing_mrc = modified_ramsey_timing(ctx.soccfg, config_mrc)
            config_mrc["modified_ramsey_timing"] = timing_mrc

            Instance_mrc = ModifiedRamsey(
                path="ModifiedRamsey_Control",
                cfg=config_mrc, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
            )
            data_mrc = ModifiedRamsey.acquire(Instance_mrc)
            ModifiedRamsey.display(Instance_mrc, data_mrc, plotDisp=False, figNum=11)
            ModifiedRamsey.save_data(Instance_mrc, data_mrc)
            ModifiedRamsey.save_config(Instance_mrc)

            # ---------- classify shots and build parity trace ----------
            raw_i_mrc = np.ravel(np.array(data_mrc["data"]["shots_i"]))
            raw_q_mrc = np.ravel(np.array(data_mrc["data"]["shots_q"]))
            iq_mrc = np.column_stack([raw_i_mrc, raw_q_mrc])

            # KMeans(n_clusters=2) ALWAYS returns two centroids, even for a
            # single unimodal blob, and the majority-forcing below then labels
            # the minority half "1". Left ungated, this control can never
            # report "no switching" -- it manufactures a ~50/50 split out of
            # pure readout noise. So require the two blobs to be genuinely
            # separated before trusting the split.
            kmeans_mrc = KMeans(n_clusters=2, random_state=0, n_init=20)
            labels_mrc = kmeans_mrc.fit_predict(iq_mrc)
            centers_mrc = kmeans_mrc.cluster_centers_

            c0_mrc = centers_mrc[0]
            c1_mrc = centers_mrc[1]
            normal_mrc   = c1_mrc - c0_mrc
            midpoint_mrc = 0.5 * (c0_mrc + c1_mrc)
            scores_mrc   = (iq_mrc - midpoint_mrc) @ normal_mrc
            binary_states_mrc = (scores_mrc > 0).astype(int)

            # Separation test: centroid distance vs the pooled within-cluster
            # spread. Two resolved readout blobs give >~ 2; one blob gives <~ 1.
            sep_mrc = float(np.linalg.norm(normal_mrc))
            within_mrc = float(np.sqrt(np.mean([
                np.mean(np.sum((iq_mrc[labels_mrc == k] - centers_mrc[k]) ** 2, axis=1))
                for k in (0, 1) if np.any(labels_mrc == k)
            ])))
            blob_snr_mrc = sep_mrc / within_mrc if within_mrc > 0 else np.inf
            blobs_resolved_mrc = blob_snr_mrc >= 2.0
            if not blobs_resolved_mrc:
                print(
                    f"[MRC] Cycle {cycle_idx_mrc + 1}: single blob "
                    f"(centroid separation / within-cluster spread = "
                    f"{blob_snr_mrc:.2f} < 2.0). No g/e separation -- reporting "
                    "all shots as state 0 (NO SWITCHING) rather than splitting "
                    "noise in half."
                )
                binary_states_mrc = np.zeros(len(iq_mrc), dtype=int)
            else:
                n0_mrc = np.sum(binary_states_mrc == 0)
                n1_mrc = np.sum(binary_states_mrc == 1)
                if n1_mrc > n0_mrc:
                    binary_states_mrc = 1 - binary_states_mrc
                    c0_mrc, c1_mrc = c1_mrc, c0_mrc
                    normal_mrc   = c1_mrc - c0_mrc
                    midpoint_mrc = 0.5 * (c0_mrc + c1_mrc)
                    scores_mrc   = (iq_mrc - midpoint_mrc) @ normal_mrc

            rep_period_us_mrc = timing_mrc["scheduled_rep_period_us"]
            streamer_rep_period_us_mrc = data_mrc["data"].get(
                "streamer_average_rep_period_us", np.nan
            )
            elapsed_ms_mrc = np.arange(len(raw_i_mrc)) * rep_period_us_mrc * 1e-3

            timestamp_mrc = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            base_mrc = os.path.join(
                save_dir_mrc, f"Cycle_{cycle_idx_mrc:03d}_MRC_{timestamp_mrc}"
            )

            I_min_mrc, I_max_mrc = raw_i_mrc.min(), raw_i_mrc.max()
            Q_min_mrc, Q_max_mrc = raw_q_mrc.min(), raw_q_mrc.max()
            I_pad_mrc = 0.05 * (I_max_mrc - I_min_mrc if I_max_mrc > I_min_mrc else 1.0)
            Q_pad_mrc = 0.05 * (Q_max_mrc - Q_min_mrc if Q_max_mrc > Q_min_mrc else 1.0)
            I_line_mrc = np.linspace(I_min_mrc - I_pad_mrc, I_max_mrc + I_pad_mrc, 400)

            vertical_line_mrc = np.abs(normal_mrc[1]) < 1e-12
            if not vertical_line_mrc:
                Q_line_mrc = (midpoint_mrc[1]
                              - (normal_mrc[0] / normal_mrc[1])
                              * (I_line_mrc - midpoint_mrc[0]))

            # IQ scatter
            plt.figure(figsize=(6, 6))
            plt.plot(raw_i_mrc[binary_states_mrc == 0], raw_q_mrc[binary_states_mrc == 0],
                     ".", alpha=0.5, label="State 0")
            plt.plot(raw_i_mrc[binary_states_mrc == 1], raw_q_mrc[binary_states_mrc == 1],
                     ".", alpha=0.5, label="State 1")
            plt.plot(c0_mrc[0], c0_mrc[1], "o", markersize=10)
            plt.plot(c1_mrc[0], c1_mrc[1], "o", markersize=10)
            if vertical_line_mrc:
                plt.axvline(midpoint_mrc[0], linestyle="--", linewidth=2, label="Separator")
            else:
                plt.plot(I_line_mrc, Q_line_mrc, "--", linewidth=2, label="Separator")
            plt.xlabel("I"); plt.ylabel("Q")
            plt.xlim(I_min_mrc - I_pad_mrc, I_max_mrc + I_pad_mrc)
            plt.ylim(Q_min_mrc - Q_pad_mrc, Q_max_mrc + Q_pad_mrc)
            plt.gca().set_aspect("equal", adjustable="box")
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC IQ (sweet spot)\n"
                f"V_sweet={current_voltage_mrc:.6f} V, f_ge={f_ge_mrc:.6f} MHz, "
                f"tau={tau_mrc:.4f} us"
            )
            plt.legend(); plt.tight_layout()
            plt.savefig(base_mrc + "_iq_labeled.png", dpi=300, bbox_inches="tight")
            plt.close()

            # raw binary parity trace
            plt.figure(figsize=(10, 4))
            plt.step(elapsed_ms_mrc, binary_states_mrc, where="post", linewidth=1.5)
            plt.plot(elapsed_ms_mrc, binary_states_mrc, "o", markersize=2)
            plt.xlabel("Scheduled time since start (ms)")
            plt.ylabel("Parity state")
            plt.yticks([0, 1]); plt.ylim(-0.1, 1.1)
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC parity trace (sweet spot control)\n"
                f"tau={tau_mrc:.4f} us, S_sweet={S_sweet_mrc:.4f} MHz"
            )
            plt.tight_layout()
            plt.savefig(base_mrc + "_binary.png", dpi=300, bbox_inches="tight")
            plt.close()

            # ---------- moving-average + hysteresis ----------
            window_ms_mrc  = ModifiedRamsey_Control_params["window_ms"]
            dt_ms_mrc      = rep_period_us_mrc * 1e-3
            window_n_mrc   = max(1, int(round(window_ms_mrc / dt_ms_mrc)))
            low_thresh_mrc  = ModifiedRamsey_Control_params["hysteresis_low"]
            high_thresh_mrc = ModifiedRamsey_Control_params["hysteresis_high"]

            state_avg_mrc    = None
            state_hyst_mrc   = None
            switches_hyst_mrc = None
            switch_time_ms_mrc = (elapsed_ms_mrc[1:] if len(elapsed_ms_mrc) > 1
                                   else np.array([]))

            if len(binary_states_mrc) >= 1:
                kernel_mrc    = np.ones(window_n_mrc, dtype=float) / window_n_mrc
                state_avg_mrc = np.convolve(
                    binary_states_mrc.astype(float), kernel_mrc, mode="same"
                )

                state_hyst_mrc   = np.empty_like(binary_states_mrc)
                current_state_mrc = int(binary_states_mrc[0])
                for idx_mrc, val_mrc in enumerate(state_avg_mrc):
                    if val_mrc >= high_thresh_mrc:
                        current_state_mrc = 1
                    elif val_mrc <= low_thresh_mrc:
                        current_state_mrc = 0
                    state_hyst_mrc[idx_mrc] = current_state_mrc

                switches_hyst_mrc = (np.diff(state_hyst_mrc) != 0).astype(int)

                plt.figure(figsize=(10, 4))
                plt.plot(elapsed_ms_mrc, state_avg_mrc, linewidth=1.5,
                         label="Moving average")
                plt.axhline(high_thresh_mrc, linestyle="--", linewidth=1.2,
                            label=f"High threshold = {high_thresh_mrc:.2f}")
                plt.axhline(low_thresh_mrc,  linestyle="--", linewidth=1.2,
                            label=f"Low threshold = {low_thresh_mrc:.2f}")
                plt.xlabel("Scheduled time since start (ms)")
                plt.ylabel("Smoothed parity state")
                plt.ylim(-0.05, 1.05)
                plt.title(
                    f"Cycle {cycle_idx_mrc + 1}: MRC moving-average parity trace\n"
                    f"window={window_n_mrc * dt_ms_mrc:.3f} ms, tau={tau_mrc:.4f} us"
                )
                plt.legend(); plt.tight_layout()
                plt.savefig(base_mrc + "_state_moving_avg.png", dpi=300, bbox_inches="tight")
                plt.close()

                plt.figure(figsize=(10, 4))
                plt.step(elapsed_ms_mrc, state_hyst_mrc, where="post",
                         linewidth=1.5, label="Hysteresis state")
                plt.plot(elapsed_ms_mrc, binary_states_mrc, "o", markersize=2,
                         alpha=0.35, label="Raw binary state")
                plt.xlabel("Scheduled time since start (ms)")
                plt.ylabel("Parity state")
                plt.yticks([0, 1]); plt.ylim(-0.1, 1.1)
                plt.title(
                    f"Cycle {cycle_idx_mrc + 1}: MRC hysteresis parity trace\n"
                    f"low={low_thresh_mrc:.2f}, high={high_thresh_mrc:.2f}, "
                    f"window={window_n_mrc * dt_ms_mrc:.3f} ms"
                )
                plt.legend(); plt.tight_layout()
                plt.savefig(base_mrc + "_state_hysteresis.png",
                            dpi=300, bbox_inches="tight")
                plt.close()

                if len(switches_hyst_mrc) >= 1:
                    plt.figure(figsize=(10, 4))
                    plt.step(switch_time_ms_mrc, switches_hyst_mrc, where="post",
                             linewidth=1.5)
                    plt.plot(switch_time_ms_mrc, switches_hyst_mrc, "o", markersize=2)
                    plt.xlabel("Scheduled time since start (ms)")
                    plt.ylabel("Jump detected")
                    plt.yticks([0, 1]); plt.ylim(-0.1, 1.1)
                    plt.title(
                        f"Cycle {cycle_idx_mrc + 1}: MRC jumps from hysteresis state\n"
                        f"low={low_thresh_mrc:.2f}, high={high_thresh_mrc:.2f}"
                    )
                    plt.tight_layout()
                    plt.savefig(base_mrc + "_state_hysteresis_jumps.png",
                                dpi=300, bbox_inches="tight")
                    plt.close()

            np.savez(
                base_mrc + ".npz",
                elapsed_ms           = np.array(elapsed_ms_mrc),
                raw_i                = np.array(raw_i_mrc),
                raw_q                = np.array(raw_q_mrc),
                scores               = np.array(scores_mrc),
                binary_states        = np.array(binary_states_mrc),
                state_avg            = np.array(state_avg_mrc)  if state_avg_mrc  is not None else np.array([]),
                state_hysteresis     = np.array(state_hyst_mrc) if state_hyst_mrc is not None else np.array([]),
                hysteresis_switches  = np.array(switches_hyst_mrc) if switches_hyst_mrc is not None else np.array([]),
                switch_time_ms       = np.array(switch_time_ms_mrc),
                centers              = np.array([c0_mrc, c1_mrc]),
                midpoint             = np.array(midpoint_mrc),
                normal               = np.array(normal_mrc),
                V_sweet              = np.array(current_voltage_mrc),
                S_sweet_mhz          = np.array(S_sweet_mrc),
                f_ge                 = np.array(f_ge_mrc),
                tau_us               = np.array(tau_mrc),
                half_period_v        = np.array(half_period_v_mrc),
                cycle_idx            = np.array(cycle_idx_mrc),
                hysteresis_low       = np.array(low_thresh_mrc),
                hysteresis_high      = np.array(high_thresh_mrc),
                moving_avg_window_n  = np.array(window_n_mrc),
                moving_avg_window_ms = np.array(window_n_mrc * dt_ms_mrc),
                scheduled_rep_period_us = np.array(rep_period_us_mrc),
                streamer_average_rep_period_us = np.array(streamer_rep_period_us_mrc),
                timing_breakdown     = np.array(timing_mrc, dtype=object),
                config               = np.array(config_mrc, dtype=object),
            )

            with open(base_mrc + "_config.json", "w") as fh:
                json.dump(config_mrc, fh, indent=2, default=float)

            cycle_summary_mrc.append({
                "cycle_idx":      cycle_idx_mrc,
                "success":        True,
                "V_sweet":        current_voltage_mrc,
                "S_sweet_mhz":    S_sweet_mrc,
                "sweet_verified": True,
                "f_ge":           f_ge_mrc,
                "tau_us":         tau_mrc,
                "scheduled_rep_period_us": rep_period_us_mrc,
                "streamer_average_rep_period_us": streamer_rep_period_us_mrc,
            })

        else:
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}: sweet spot not verified "
                f"(S_sweet={S_sweet_mrc:.4f} MHz >= threshold {sweet_max_df_mrc} MHz). "
                f"Skipping Ramsey run."
            )
            cycle_summary_mrc.append({
                "cycle_idx":      cycle_idx_mrc,
                "success":        False,
                "stage_failed":   "sweet_spot_not_verified",
                "V_sweet":        current_voltage_mrc,
                "S_sweet_mhz":    S_sweet_mrc,
                "sweet_verified": False,
            })

    summary_path_mrc = os.path.join(
        save_dir_mrc,
        f"CycleSummary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    )
    with open(summary_path_mrc, "w") as fh:
        json.dump(cycle_summary_mrc, fh, indent=2, default=float)
