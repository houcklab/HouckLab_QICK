from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChargeDispersionQuasiCW import ChargeDispersionQuasiCW
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChargeDispersion import ChargeDispersion
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mModifiedRamsey import ModifiedRamsey
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
import numpy as np
import matplotlib.pyplot as plt
import os
import json
from datetime import datetime
from sklearn.cluster import KMeans
from scipy.signal import find_peaks
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAutoCoherence import find_sweet_spot
from .context import Context, sanity_dump
from .calibration import (
    get_apriori_separator_from_singleshot,
    calibrate_active_reset_readout,
    wire_reset_into_mr_cfg,
    _extract_iq_from_singleshot_data,
)


def run_two_tone_charge_dispersion_quasicw(ctx, TwoToneChargeDispersion_params, Spec_relevant_params, ChargeDispersion_params):
    cfg = ctx.working_config()
    save_dir = os.path.join(ctx.outerFolder, "TwoToneChargeDispersion")
    os.makedirs(save_dir, exist_ok=True)

    df_required = TwoToneChargeDispersion_params["df"]
    dV = TwoToneChargeDispersion_params["dV"]
    voltage_min = max(0.0, TwoToneChargeDispersion_params["voltage_min"])
    voltage_max = TwoToneChargeDispersion_params["voltage_max"]
    max_tries = TwoToneChargeDispersion_params["max_voltage_tries"]
    num_cycles = TwoToneChargeDispersion_params["num_cycles"]

    # start each overall experiment from the yoko's current value
    current_voltage = float(ctx.yoko.query(":SOUR:LEV?"))
    direction = +1

    cycle_summary = []

    for cycle_idx in range(num_cycles):
        print(f"\n================ Cycle {cycle_idx + 1}/{num_cycles} ================")

        success = False
        chosen_probe_freq = None
        chosen_peak_sep = None

        # ---------- search loop for this cycle ----------
        for attempt_idx in range(max_tries):
            print(
                f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}/{num_cycles}, "
                f"attempt {attempt_idx + 1}/{max_tries}, V={current_voltage:.6f} V"
            )

            # --- run two-tone spec at current voltage ---
            cfg["current_voltage"] = current_voltage
            cfg["reps"] = TwoToneChargeDispersion_params["reps"]
            cfg["rounds"] = TwoToneChargeDispersion_params["rounds"]
            cfg["Gauss"] = TwoToneChargeDispersion_params["Gauss"]
            cfg["relax_delay"] = TwoToneChargeDispersion_params["relax_delay"]

            if cfg["Gauss"]:
                cfg["sigma"] = TwoToneChargeDispersion_params["sigma"]
                cfg["qubit_gain"] = TwoToneChargeDispersion_params["gain"]

            cfg["qubit_length"] = TwoToneChargeDispersion_params["qubit_length"]
            cfg["SpecSpan"] = TwoToneChargeDispersion_params["SpecSpan"]
            cfg["SpecNumPoints"] = TwoToneChargeDispersion_params["SpecNumPoints"]
            cfg["step"] = 2 * cfg["SpecSpan"] / cfg["SpecNumPoints"]
            cfg["start"] = ctx.qubit_frequency_center - cfg["SpecSpan"]
            cfg["expts"] = cfg["SpecNumPoints"]

            Instance_specSlice = QubitSpecSliceFF(
                path="TwoToneChargeDispersion",
                cfg=cfg,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
                outerFolder=ctx.outerFolder
            )
            data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
            QubitSpecSliceFF.display(
                Instance_specSlice,
                data_specSlice,
                plotDisp=False,
                figNum=2,
                min_sep=Spec_relevant_params["min_sep_MHz"],
                fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
                prominent_ratio=Spec_relevant_params["prominent_ratio"],
            )
            QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
            QubitSpecSliceFF.save_config(Instance_specSlice)

            x_pts = np.array(data_specSlice["data"]["x_pts"])
            avgi = np.array(data_specSlice["data"]["avgi"][0][0])
            avgq = np.array(data_specSlice["data"]["avgq"][0][0])
            # Rotate onto the signal-bearing IQ axis (background-subtracted) instead
            # of the raw magnitude |I+iQ|^2, which is dominated by the large, noisy
            # background quadrature and buries the qubit feature.
            avgamp0 = project_iq_signal(avgi, avgq)

            freq_choice = choose_two_tone_freqs_from_lorentz_or_peaks(
                data_specSlice,
                min_sep_mhz=Spec_relevant_params["min_sep_MHz"],
            )

            peak_info = freq_choice["peak_info_raw"]
            peak_info["peak_freqs"] = freq_choice["freqs"]
            peak_info["peak_sep"] = freq_choice["peak_sep"]
            peak_info["source"] = freq_choice["source"]

            save_base = save_two_tone_plot(
                x_pts=x_pts,
                avgi=avgi,
                avgq=avgq,
                avgamp0=avgamp0,
                peak_info=peak_info,
                attempt_idx=attempt_idx + cycle_idx * max_tries,
                save_dir=save_dir,
                current_voltage=current_voltage
            )

            with open(save_base + "_summary.txt", "w") as f:
                f.write(f"cycle_idx: {cycle_idx}\n")
                f.write(f"attempt_idx: {attempt_idx}\n")
                f.write(f"current_voltage: {current_voltage:.9f}\n")
                f.write(f"peak_freqs: {peak_info['peak_freqs']}\n")
                f.write(f"peak_vals: {peak_info['peak_vals']}\n")
                f.write(f"peak_sep: {peak_info['peak_sep']}\n")
                f.write(f"df_required: {df_required}\n")

            center_peak_tol_mhz = TwoToneChargeDispersion_params.get("center_peak_tol_mhz", 0.05)

            peak_freqs = np.asarray(peak_info.get("peak_freqs", []), dtype=float)

            highest_peak_freq = None
            highest_peak_is_centered = False

            if len(peak_freqs) > 0:
                # Use the largest response in avgamp0 as the "highest peak".
                peak_indices = [int(np.argmin(np.abs(x_pts - f))) for f in peak_freqs]
                peak_heights = np.asarray([avgamp0[idx] for idx in peak_indices])
                highest_peak_freq = float(peak_freqs[int(np.argmax(peak_heights))])

                highest_peak_is_centered = (
                        abs(highest_peak_freq - ctx.qubit_frequency_center) <= center_peak_tol_mhz
                )

            if highest_peak_is_centered:
                # Calibration/centered mode: run quasi-CW on the centered strongest peak.
                chosen_probe_freq = highest_peak_freq
                chosen_peak_sep = float(peak_info["peak_sep"]) if peak_info["peak_sep"] is not None else 0.0

                print(
                    f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: centered highest peak found, "
                    f"highest_peak={highest_peak_freq:.6f} MHz, "
                    f"center={ctx.qubit_frequency_center:.6f} MHz, "
                    f"|diff|={abs(highest_peak_freq - ctx.qubit_frequency_center):.6f} MHz <= "
                    f"{center_peak_tol_mhz:.6f} MHz. Running quasi-CW with "
                    f"probe_freq={chosen_probe_freq:.6f} MHz"
                )

                success = True
                break

            elif peak_info["peak_sep"] is not None and peak_info["peak_sep"] >= df_required:
                # Normal mode: require two sufficiently separated peaks.
                if TwoToneChargeDispersion_params["use_upper_peak"]:
                    chosen_probe_freq = float(np.max(peak_info["peak_freqs"]))
                else:
                    chosen_probe_freq = float(np.min(peak_info["peak_freqs"]))

                chosen_peak_sep = float(peak_info["peak_sep"])

                print(
                    f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: separated peaks found, "
                    f"peak separation = {chosen_peak_sep:.6f} MHz, "
                    f"probe_freq = {chosen_probe_freq:.6f} MHz"
                )

                success = True
                break

            # --- not separated enough: move voltage ---
            next_voltage, direction = choose_next_voltage(
                current_v=current_voltage,
                dv=dV,
                vmin=voltage_min,
                vmax=voltage_max,
                direction=direction
            )

            if abs(next_voltage - current_voltage) < 1e-15:
                print("[TwoToneChargeDispersion] Voltage step stalled at bounds.")
                break

            ramp_to(ctx.yoko, next_voltage)
            current_voltage = next_voltage

        # ---------- if search failed, record and continue to next cycle ----------
        if not success:
            print(f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: failed to find sufficient peak separation.")
            cycle_summary.append({
                "cycle_idx": cycle_idx,
                "success": False,
                "final_voltage": current_voltage,
                "chosen_probe_freq": None,
                "peak_sep": None,
            })
            continue

        # ---------- run quasi-CW for this cycle ----------
        ChargeDispersion_params["probe_freq"] = chosen_probe_freq

        cfg["current_voltage"] = current_voltage
        cfg["reps"] = TwoToneChargeDispersion_params["qcw_repetitions"]
        cfg["rounds"] = 1
        cfg["Gauss"] = Spec_relevant_params["Gauss"]
        cfg["relax_delay"] = TwoToneChargeDispersion_params["qcw_relax_delay"]

        if cfg["Gauss"]:
            cfg["sigma"] = Spec_relevant_params["sigma"]
            cfg["qubit_gain"] = Spec_relevant_params["gain"]

        cfg["SpecNumPoints"] = 1
        cfg["SpecSpan"] = 0
        cfg["step"] = 0
        cfg["start"] = ChargeDispersion_params["probe_freq"]
        cfg["expts"] = 1

        Instance_qcw = ChargeDispersionQuasiCW(
            path="TwoToneChargeDispersion",
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )

        data_qcw = Instance_qcw.acquire(load_pulses=True, print_time=True)

        raw_i = np.ravel(np.array(data_qcw["data"]["raw_i"]))
        raw_q = np.ravel(np.array(data_qcw["data"]["raw_q"]))
        iq = np.column_stack([raw_i, raw_q])

        kmeans = KMeans(n_clusters=2, random_state=0, n_init=20)
        labels = kmeans.fit_predict(iq)
        centers = kmeans.cluster_centers_

        c0 = centers[0]
        c1 = centers[1]
        normal = c1 - c0
        midpoint = 0.5 * (c0 + c1)
        scores = (iq - midpoint) @ normal
        binary_states = (scores > 0).astype(int)

        n0 = np.sum(binary_states == 0)
        n1 = np.sum(binary_states == 1)
        if n1 > n0:
            binary_states = 1 - binary_states
            c0, c1 = c1, c0
            normal = c1 - c0
            midpoint = 0.5 * (c0 + c1)
            scores = (iq - midpoint) @ normal

        rep_period_us = 1.0 + 0.5 + cfg["readout_length"] + 10 + cfg["relax_delay"]
        elapsed_s = np.arange(len(raw_i)) * rep_period_us * 1e-6

        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        base = os.path.join(save_dir, f"Cycle_{cycle_idx:03d}_QuasiCW_{timestamp}")

        I_min, I_max = raw_i.min(), raw_i.max()
        Q_min, Q_max = raw_q.min(), raw_q.max()
        I_pad = 0.05 * (I_max - I_min if I_max > I_min else 1.0)
        Q_pad = 0.05 * (Q_max - Q_min if Q_max > Q_min else 1.0)
        I_line = np.linspace(I_min - I_pad, I_max + I_pad, 400)

        vertical_line = np.abs(normal[1]) < 1e-12
        if not vertical_line:
            Q_line = midpoint[1] - (normal[0] / normal[1]) * (I_line - midpoint[0])

        plt.figure(figsize=(6, 6))
        plt.plot(raw_i, raw_q, ".", alpha=0.35, label="IQ data")
        plt.plot(c0[0], c0[1], "o", markersize=10, label="Blob center 0")
        plt.plot(c1[0], c1[1], "o", markersize=10, label="Blob center 1")
        if vertical_line:
            plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
        else:
            plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")
        plt.xlabel("I")
        plt.ylabel("Q")
        plt.title(
            f"Cycle {cycle_idx + 1}: QuasiCW IQ, V={current_voltage:.6f} V, "
            f"probe={chosen_probe_freq:.6f} MHz"
        )
        plt.xlim(I_min - I_pad, I_max + I_pad)
        plt.ylim(Q_min - Q_pad, Q_max + Q_pad)
        plt.gca().set_aspect("equal", adjustable="box")
        plt.legend()
        plt.tight_layout()
        plt.savefig(base + "_iq_separator.png", dpi=300, bbox_inches="tight")
        plt.close()

        plt.figure(figsize=(6, 6))
        plt.plot(raw_i[binary_states == 0], raw_q[binary_states == 0], ".", alpha=0.5, label="State 0")
        plt.plot(raw_i[binary_states == 1], raw_q[binary_states == 1], ".", alpha=0.5, label="State 1")
        if vertical_line:
            plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
        else:
            plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")
        plt.xlabel("I")
        plt.ylabel("Q")
        plt.title(f"Cycle {cycle_idx + 1}: QuasiCW IQ labeled")
        plt.xlim(I_min - I_pad, I_max + I_pad)
        plt.ylim(Q_min - Q_pad, Q_max + Q_pad)
        plt.gca().set_aspect("equal", adjustable="box")
        plt.legend()
        plt.tight_layout()
        plt.savefig(base + "_iq_labeled.png", dpi=300, bbox_inches="tight")
        plt.close()

        amps = np.abs(raw_i + 1j * raw_q) ** 2
        plt.figure(figsize=(10, 4))
        plt.plot(elapsed_s, amps, "-", linewidth=1)
        plt.xlabel("Time since start (s)")
        plt.ylabel("Amplitude$^2$")
        plt.title(f"Cycle {cycle_idx + 1}: Amplitude over time")
        plt.tight_layout()
        plt.savefig(base + "_amplitude_vs_time.png", dpi=300, bbox_inches="tight")
        plt.close()


        plt.figure(figsize=(10, 4))
        plt.step(elapsed_s, binary_states, where="post", linewidth=1.5)
        plt.plot(elapsed_s, binary_states, "o", markersize=2)
        plt.xlabel("Time since start (s)")
        plt.ylabel("Assigned state")
        plt.yticks([0, 1])
        plt.ylim(-0.1, 1.1)
        plt.title(f"Cycle {cycle_idx + 1}: QuasiCW binary trace")
        plt.tight_layout()
        plt.savefig(base + "_binary.png", dpi=300, bbox_inches="tight")
        plt.close()

        np.savez(
            base + ".npz",
            elapsed_s=np.array(elapsed_s),
            raw_i=np.array(raw_i),
            raw_q=np.array(raw_q),
            scores=np.array(scores),
            binary_states=np.array(binary_states),
            centers=np.array([c0, c1]),
            midpoint=np.array(midpoint),
            normal=np.array(normal),
            chosen_probe_freq=np.array(chosen_probe_freq),
            final_voltage=np.array(current_voltage),
            peak_sep=np.array(chosen_peak_sep),
            cycle_idx=np.array(cycle_idx),
            config=np.array(cfg, dtype=object),
        )

        with open(base + "_config.json", "w") as f:
            json.dump(cfg, f, indent=2, default=float)

        cycle_summary.append({
            "cycle_idx": cycle_idx,
            "success": True,
            "final_voltage": current_voltage,
            "chosen_probe_freq": chosen_probe_freq,
            "peak_sep": chosen_peak_sep,
        })

        # after finishing this cycle, restart the search from the current voltage
        # direction is preserved so the voltage walk continues naturally

    # ---------- save summary for all cycles ----------
    summary_path = os.path.join(
        save_dir,
        f"CycleSummary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    )
    with open(summary_path, "w") as f:
        json.dump(cycle_summary, f, indent=2, default=float)


def run_modified_ramsey(ctx, ModifiedRamsey_params, Spec_relevant_params):
    date_tag_mr = datetime.now().strftime("%Y_%m_%d")
    save_dir_mr = os.path.join(ctx.outerFolder, "ModifiedRamsey", date_tag_mr)
    os.makedirs(save_dir_mr, exist_ok=True)

    df_required_mr = ModifiedRamsey_params["df"]
    dV_mr = ModifiedRamsey_params["dV"]
    voltage_min_mr = max(0.0, ModifiedRamsey_params["voltage_min"])
    voltage_max_mr = ModifiedRamsey_params["voltage_max"]
    max_tries_mr = ModifiedRamsey_params["max_voltage_tries"]
    num_cycles_mr = ModifiedRamsey_params["num_cycles"]

    ModifiedRamsey_params.setdefault("hysteresis_low", 0.2)
    ModifiedRamsey_params.setdefault("hysteresis_high", 0.8)
    ModifiedRamsey_params.setdefault("window_ms", 0.05)

    current_voltage_mr = float(ctx.yoko.query(":SOUR:LEV?"))
    direction_mr = +1

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

        success_mr = False
        chosen_probe_freq_mr = None
        chosen_peak_sep_mr = None

        # ---------- two-tone voltage search ----------
        for attempt_idx_mr in range(max_tries_mr):
            print(
                f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}/{num_cycles_mr}, "
                f"attempt {attempt_idx_mr + 1}/{max_tries_mr}, V={current_voltage_mr:.6f} V"
            )

            cfg["current_voltage"] = current_voltage_mr
            cfg["reps"] = ModifiedRamsey_params["reps"]
            cfg["rounds"] = ModifiedRamsey_params["rounds"]
            cfg["Gauss"] = ModifiedRamsey_params["Gauss"]
            cfg["relax_delay"] = ModifiedRamsey_params["relax_delay"]

            if cfg["Gauss"]:
                cfg["sigma"] = ModifiedRamsey_params["sigma"]
                cfg["qubit_gain"] = ModifiedRamsey_params["gain"]

            cfg["qubit_length"] = ModifiedRamsey_params["qubit_length"]
            cfg["SpecSpan"] = ModifiedRamsey_params["SpecSpan"]
            cfg["SpecNumPoints"] = ModifiedRamsey_params["SpecNumPoints"]
            cfg["step"] = 2 * cfg["SpecSpan"] / cfg["SpecNumPoints"]
            cfg["start"] = ctx.qubit_frequency_center - cfg["SpecSpan"]
            cfg["expts"] = cfg["SpecNumPoints"]

            Instance_specSlice_mr = QubitSpecSliceFF(
                path="ModifiedRamsey",
                cfg=cfg,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
                outerFolder=ctx.outerFolder
            )
            data_specSlice_mr = QubitSpecSliceFF.acquire(Instance_specSlice_mr)
            QubitSpecSliceFF.display(
                Instance_specSlice_mr,
                data_specSlice_mr,
                plotDisp=False,
                figNum=2,
                min_sep=Spec_relevant_params["min_sep_MHz"],
                fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
                prominent_ratio=Spec_relevant_params["prominent_ratio"],
            )
            QubitSpecSliceFF.save_data(Instance_specSlice_mr, data_specSlice_mr)
            QubitSpecSliceFF.save_config(Instance_specSlice_mr)

            x_pts_mr = np.array(data_specSlice_mr["data"]["x_pts"])
            avgi_mr = np.array(data_specSlice_mr["data"]["avgi"][0][0])
            avgq_mr = np.array(data_specSlice_mr["data"]["avgq"][0][0])
            # Rotate onto the signal-bearing IQ axis (background-subtracted) instead
            # of the raw magnitude |I+iQ|^2, which is dominated by the large, noisy
            # background quadrature and buries the qubit feature.
            avgamp0_mr = project_iq_signal(avgi_mr, avgq_mr)

            # Robust parity-doublet finder: noise-floor-referenced peak detection,
            # symmetric-pair-about-center selection, sub-bin Lorentzian refinement.
            doublet_mr = find_parity_doublet(
                x_pts_mr,
                avgamp0_mr,
                center_freq=ctx.qubit_frequency_center,
                min_sep_mhz=ModifiedRamsey_params.get("min_sep_MHz", 0.02),
                max_sep_mhz=ModifiedRamsey_params.get("max_sep_MHz", None),
                prominence_snr=ModifiedRamsey_params.get("prominence_snr", 5.0),
                smooth_window=ModifiedRamsey_params.get("smooth_window", 5),
                symmetry_tol_mhz=ModifiedRamsey_params.get("symmetry_tol_MHz", None),
                min_height_balance=ModifiedRamsey_params.get("min_height_balance", 0.3),
                fit_window_mhz=ModifiedRamsey_params.get("fit_window_mhz", 0.1),
                refine=True,
            )

            # peak_info compatible with save_two_tone_plot and the summary file.
            peak_info_mr = {
                "peak_inds": doublet_mr["peak_inds"],
                "peak_freqs": doublet_mr["peak_freqs"],
                "peak_vals": doublet_mr["peak_vals"],
                "peak_sep": doublet_mr["peak_sep"],
                "source": doublet_mr["mode"],
            }

            save_base_mr = save_two_tone_plot(
                x_pts=x_pts_mr,
                avgi=avgi_mr,
                avgq=avgq_mr,
                avgamp0=avgamp0_mr,
                peak_info=peak_info_mr,
                current_voltage=current_voltage_mr,
                attempt_idx=attempt_idx_mr + cycle_idx_mr * max_tries_mr,
                save_dir=save_dir_mr,
                qubit_gain=cfg.get("qubit_gain"),
                qubit_length=cfg.get("qubit_length"),
                center_freq=ctx.qubit_frequency_center,
                fit=doublet_mr.get("fit"),
                live_display=ModifiedRamsey_params.get("live_display", False),
                live_pause=ModifiedRamsey_params.get("live_pause", 0.05),
            )

            with open(save_base_mr + "_summary.txt", "w") as f:
                f.write(f"cycle_idx: {cycle_idx_mr}\n")
                f.write(f"attempt_idx: {attempt_idx_mr}\n")
                f.write(f"current_voltage: {current_voltage_mr:.9f}\n")
                f.write(f"mode: {doublet_mr['mode']}\n")
                f.write(f"lower: {doublet_mr['lower']}\n")
                f.write(f"upper: {doublet_mr['upper']}\n")
                f.write(f"center: {doublet_mr['center']}\n")
                f.write(f"peak_sep: {doublet_mr['peak_sep']}\n")
                f.write(f"noise_sigma: {doublet_mr['noise_sigma']}\n")
                f.write(f"candidates: {doublet_mr['candidates']}\n")
                f.write(f"df_required: {df_required_mr}\n")

            center_peak_tol_mhz = ModifiedRamsey_params.get("center_peak_tol_mhz", 0.05)
            center_peak_df_for_tau = ModifiedRamsey_params.get("center_peak_df_for_tau", df_required_mr)

            doublet_centered_mr = (
                doublet_mr["center"] is not None
                and abs(doublet_mr["center"] - ctx.qubit_frequency_center) <= center_peak_tol_mhz
            )

            if (
                doublet_mr["mode"] == "doublet"
                and doublet_mr["peak_sep"] is not None
                and doublet_mr["peak_sep"] >= df_required_mr
            ):
                # Parity mode: a resolved doublet split widely enough for Ramsey.
                chosen_probe_freq_mr = float(doublet_mr["upper"])
                chosen_peak_sep_mr = float(doublet_mr["peak_sep"])

                print(
                    f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: doublet found, "
                    f"lower={doublet_mr['lower']:.6f} MHz, "
                    f"upper={doublet_mr['upper']:.6f} MHz, "
                    f"sep={chosen_peak_sep_mr:.6f} MHz, f_ge={chosen_probe_freq_mr:.6f} MHz, "
                    f"tau={1.0 / (2.0 * chosen_peak_sep_mr):.4f} us"
                )

                success_mr = True
                break

            elif doublet_centered_mr:
                # Calibration mode: feature centered but not split enough; run MR at
                # the center with the configured df-for-tau.
                chosen_probe_freq_mr = float(doublet_mr["center"])
                chosen_peak_sep_mr = float(center_peak_df_for_tau)

                print(
                    f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: centered feature "
                    f"(mode={doublet_mr['mode']}), center={doublet_mr['center']:.6f} MHz, "
                    f"|diff|={abs(doublet_mr['center'] - ctx.qubit_frequency_center):.6f} MHz <= "
                    f"{center_peak_tol_mhz:.6f} MHz. Running calibration Ramsey with "
                    f"f_ge={chosen_probe_freq_mr:.6f} MHz, "
                    f"df_for_tau={chosen_peak_sep_mr:.6f} MHz, "
                    f"tau={1.0 / (2.0 * chosen_peak_sep_mr):.4f} us"
                )

                success_mr = True
                break

            next_voltage_mr, direction_mr = choose_next_voltage(
                current_v=current_voltage_mr,
                dv=dV_mr,
                vmin=voltage_min_mr,
                vmax=voltage_max_mr,
                direction=direction_mr
            )

            if abs(next_voltage_mr - current_voltage_mr) < 1e-15:
                print("[ModifiedRamsey] Voltage step stalled at bounds.")
                break

            ramp_to(ctx.yoko, next_voltage_mr)
            current_voltage_mr = next_voltage_mr

        if not success_mr:
            print(f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: failed to find sufficient peak separation.")
            cycle_summary_mr.append({
                "cycle_idx": cycle_idx_mr,
                "success": False,
                "final_voltage": current_voltage_mr,
                "chosen_probe_freq": None,
                "peak_sep": None,
            })
            continue

        # ---------- run Modified Ramsey with auto-computed tau and f_ge ----------
        tau_us_mr = 1.0 / (2.0 * chosen_peak_sep_mr)

        mr_cfg = {
            "f_ge": chosen_probe_freq_mr,
            "df": chosen_peak_sep_mr,
            "pi2_gain": ctx.pi2_gain,
            "pi_gain": ctx.qubit_gain,
            "use_pi_pulse": ModifiedRamsey_params.get("use_pi_pulse", False),
            # Parity -> state mapping and drive scheme (opt-in; defaults preserve
            # the original standard-scheme behavior).
            "flip_final_pi2": ModifiedRamsey_params.get("flip_final_pi2", False),
            "symmetric_ramsey": ModifiedRamsey_params.get("symmetric_ramsey", False),
            # Hardware active reset to |g> per shot (opt-in). See ModifiedRamsey
            # docstring: requires readout_threshold + I-axis g/e separation.
            "use_active_reset": ModifiedRamsey_params.get("use_active_reset", False),
            "reset_cycles": ModifiedRamsey_params.get("reset_cycles", 1),
            "reset_ground_below_threshold": ModifiedRamsey_params.get("reset_ground_below_threshold", True),
            "reset_readout_relax_delay": ModifiedRamsey_params.get("reset_readout_relax_delay", 1.0),
            "post_reset_wait": ModifiedRamsey_params.get("post_reset_wait", 0.0),
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

        # ---------- classify shots and build averaged 0-to-1 trace ----------
        raw_i_mr = np.ravel(np.array(data_mr["data"]["shots_i"]))
        raw_q_mr = np.ravel(np.array(data_mr["data"]["shots_q"]))

        if apriori_sep_mr is None:
            raise RuntimeError("ModifiedRamsey now requires apriori_sep_mr from SingleShot calibration.")

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

        pulse_length_us = ctx.qubit_sigma * 4
        n_qubit_pulses_mr = 3 if config_mr.get("use_pi_pulse", False) else 2
        rep_period_us = n_qubit_pulses_mr * pulse_length_us + tau_us_mr + 0.05 + config_mr["readout_length"]

        elapsed_ms_mr = np.arange(len(raw_i_mr)) * rep_period_us * 1e-3
        elapsed_avg_ms_mr = (
                np.arange(len(excited_avg_mr)) * average_n_shots_mr * rep_period_us * 1e-3
        )

        timestamp_mr = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        base_mr = os.path.join(save_dir_mr, f"Cycle_{cycle_idx_mr:03d}_MR_{timestamp_mr}")

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
        plt.xlabel("Time since start (ms)")
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
        plt.xlabel("Time since start (ms)")
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
            mr_cfg_mrc = {
                "f_ge":           f_ge_mrc,
                "df":             cd_max_mhz_mrc,
                "pi2_gain":       ctx.pi2_gain,
                "sigma":          ctx.qubit_sigma,
                "flattop_length": ctx.qubit_flattop,
                "reps":           ModifiedRamsey_Control_params["mr_reps"],
                "rounds":         1,
                "current_voltage": current_voltage_mrc,
                "Qubit_number":   ctx.Qubit_Readout,
            }
            config_mrc = cfg | mr_cfg_mrc

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

            kmeans_mrc = KMeans(n_clusters=2, random_state=0, n_init=20)
            kmeans_mrc.fit_predict(iq_mrc)
            centers_mrc = kmeans_mrc.cluster_centers_

            c0_mrc = centers_mrc[0]
            c1_mrc = centers_mrc[1]
            normal_mrc   = c1_mrc - c0_mrc
            midpoint_mrc = 0.5 * (c0_mrc + c1_mrc)
            scores_mrc   = (iq_mrc - midpoint_mrc) @ normal_mrc
            binary_states_mrc = (scores_mrc > 0).astype(int)

            n0_mrc = np.sum(binary_states_mrc == 0)
            n1_mrc = np.sum(binary_states_mrc == 1)
            if n1_mrc > n0_mrc:
                binary_states_mrc = 1 - binary_states_mrc
                c0_mrc, c1_mrc = c1_mrc, c0_mrc
                normal_mrc   = c1_mrc - c0_mrc
                midpoint_mrc = 0.5 * (c0_mrc + c1_mrc)
                scores_mrc   = (iq_mrc - midpoint_mrc) @ normal_mrc

            pulse_length_us_mrc = ctx.qubit_sigma * 4
            rep_period_us_mrc   = (2 * pulse_length_us_mrc + tau_mrc
                                    + 0.05 + config_mrc["readout_length"])
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
            plt.xlabel("Time since start (ms)")
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
                plt.xlabel("Time since start (ms)")
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
                plt.xlabel("Time since start (ms)")
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
                    plt.xlabel("Time since start (ms)")
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


def run_charge_dispersion_quasicw(ctx, ChargeDispersion_params, Spec_relevant_params):
    cfg = ctx.working_config()
    cfg["reps"] = ChargeDispersion_params["repetitions"]
    cfg["rounds"] = 1
    cfg["Gauss"] = Spec_relevant_params["Gauss"]
    cfg["relax_delay"] = ChargeDispersion_params["relax_delay"]

    if cfg["Gauss"]:
        cfg["sigma"] = Spec_relevant_params["sigma"]
        cfg["qubit_gain"] = Spec_relevant_params["gain"]

    # one-frequency mode
    cfg["SpecNumPoints"] = 1
    cfg["SpecSpan"] = 0
    cfg["step"] = 0
    cfg["start"] = ChargeDispersion_params["probe_freq"]
    cfg["expts"] = 1

    Instance_specSlice = ChargeDispersionQuasiCW(
        path="ChargeDispersion",
        cfg=cfg,
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        outerFolder=ctx.outerFolder,
    )

    data_specSlice = Instance_specSlice.acquire(load_pulses=True, print_time=True)

    x_pts = np.array(data_specSlice["data"]["x_pts"])

    # repetition-resolved IQ data
    raw_i = np.ravel(np.array(data_specSlice["data"]["raw_i"]))
    raw_q = np.ravel(np.array(data_specSlice["data"]["raw_q"]))

    # stack IQ points
    iq = np.column_stack([raw_i, raw_q])

    # ---------------------------
    # Straight-line blob separation using 2-cluster fit
    # ---------------------------
    kmeans = KMeans(n_clusters=2, random_state=0, n_init=20)
    labels = kmeans.fit_predict(iq)
    centers = kmeans.cluster_centers_

    c0 = centers[0]
    c1 = centers[1]

    # normal vector to separating line = line connecting the centers
    normal = c1 - c0
    midpoint = 0.5 * (c0 + c1)

    # signed distance from perpendicular bisector
    scores = (iq - midpoint) @ normal

    # binary labels from side of line
    binary_amps = (scores > 0).astype(int)

    # optional relabel so state 1 is the less populated blob
    n0 = np.sum(binary_amps == 0)
    n1 = np.sum(binary_amps == 1)
    if n1 > n0:
        binary_amps = 1 - binary_amps
        labels = 1 - labels
        c0, c1 = c1, c0
        normal = c1 - c0
        midpoint = 0.5 * (c0 + c1)
        scores = (iq - midpoint) @ normal

    # amplitude for reference only
    amps = np.abs(raw_i + 1j * raw_q) ** 2

    # approximate time axis per repetition
    rep_period_us = (
        1.0 + 0.5 + cfg["readout_length"] + 10 + cfg["relax_delay"]
    )
    elapsed_s = np.arange(len(raw_i)) * rep_period_us * 1e-6

    save_dir = os.path.join(ctx.outerFolder, "ChargeDispersion")
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    base = os.path.join(save_dir, f"ChargeDispersionQuasiCW_{timestamp}")

    # line for plotting: normal dot (x - midpoint) = 0
    # => n_x*(I - I_mid) + n_y*(Q - Q_mid) = 0
    # => Q = Q_mid - (n_x/n_y)*(I - I_mid), unless n_y ~ 0
    I_min, I_max = raw_i.min(), raw_i.max()
    I_pad = 0.05 * (I_max - I_min if I_max > I_min else 1.0)
    I_line = np.linspace(I_min - I_pad, I_max + I_pad, 400)

    vertical_line = np.abs(normal[1]) < 1e-12
    if not vertical_line:
        Q_line = midpoint[1] - (normal[0] / normal[1]) * (I_line - midpoint[0])

    # ---------------------------
    # Plot 1: raw IQ blobs with separating line
    # ---------------------------
    plt.figure(figsize=(6, 6))
    plt.plot(raw_i, raw_q, ".", alpha=0.35, label="IQ data")
    plt.plot(c0[0], c0[1], "o", markersize=10, label="Blob center 0")
    plt.plot(c1[0], c1[1], "o", markersize=10, label="Blob center 1")

    if vertical_line:
        plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
    else:
        plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")

    plt.xlabel("I")
    plt.ylabel("Q")
    plt.title("ChargeDispersionQuasiCW IQ blobs with straight-line separator")

    i_min, i_max = raw_i.min(), raw_i.max()
    q_min, q_max = raw_q.min(), raw_q.max()
    i_pad = 0.05 * (i_max - i_min if i_max > i_min else 1.0)
    q_pad = 0.05 * (q_max - q_min if q_max > q_min else 1.0)

    plt.xlim(i_min - i_pad, i_max + i_pad)
    plt.ylim(q_min - q_pad, q_max + q_pad)
    plt.gca().set_aspect("equal", adjustable="box")

    plt.legend()
    plt.tight_layout()
    plt.show()

    # ---------------------------
    # Plot 2: IQ blobs colored by assigned state
    # ---------------------------
    plt.figure(figsize=(6, 6))
    plt.plot(raw_i[binary_amps == 0], raw_q[binary_amps == 0], ".", alpha=0.5, label="State 0")
    plt.plot(raw_i[binary_amps == 1], raw_q[binary_amps == 1], ".", alpha=0.5, label="State 1")
    plt.plot(c0[0], c0[1], "o", markersize=10)
    plt.plot(c1[0], c1[1], "o", markersize=10)

    if vertical_line:
        plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
    else:
        plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")

    plt.xlabel("I")
    plt.ylabel("Q")
    plt.title("IQ blobs colored by straight-line separation")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_iq_blobs_labeled.png", dpi=300, bbox_inches="tight")
    plt.show()
    plt.close()

    # ---------------------------
    # Plot 3: projection score histogram
    # ---------------------------
    plt.figure(figsize=(7, 5))
    plt.hist(scores, bins=100, alpha=0.7)
    plt.axvline(0.0, linestyle="--", linewidth=2, label="Decision boundary")
    plt.xlabel("Signed distance from separator")
    plt.ylabel("Counts")
    plt.title("Separator score histogram")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_separator_score_hist.png", dpi=300, bbox_inches="tight")
    plt.show()
    plt.close()

    # ---------------------------
    # Plot 4: binary parity trace over time
    # ---------------------------
    plt.figure(figsize=(10, 4))
    plt.plot(elapsed_s, binary_states, "-", linewidth=1.5)
    plt.xlabel("Time since start (s)")
    plt.ylabel("Assigned state")
    plt.yticks([0, 1])
    plt.ylim(-0.1, 1.1)
    plt.title(f"Cycle {cycle_idx + 1}: QuasiCW binary trace")
    plt.tight_layout()
    plt.savefig(base + "_binary.png", dpi=300, bbox_inches="tight")
    plt.close()

    np.savez(
        base + ".npz",
        elapsed_s=np.array(elapsed_s),
        raw_i=np.array(raw_i),
        raw_q=np.array(raw_q),
        amps=np.array(amps),
        scores=np.array(scores),
        binary_amps=np.array(binary_amps),
        centers=np.array([c0, c1]),
        midpoint=np.array(midpoint),
        normal=np.array(normal),
        x_pts=np.array(x_pts),
        config=np.array(cfg, dtype=object),
    )

    with open(base + "_config.json", "w") as f:
        json.dump(cfg, f, indent=2, default=float)


def run_charge_dispersion_ramsey(ctx, T1T2_params, ChargeDispersion_params):
    cfg = ctx.working_config()
    repetitions = T1T2_params['repetitions']
    for i in range(repetitions):
        cd_cfg = {
            "df": ChargeDispersion_params["df"],
            "reps": 1,
            "rounds": 1,
            "pi2_gain": ctx.pi2_gain,
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
            "f_ge": ctx.qubit_frequency_center,
            "relax_delay": ChargeDispersion_params["relax_delay"],
            "Qubit_number": ctx.Qubit_Readout,
        }

        config_cd = cfg | cd_cfg
        iCD = ChargeDispersion(
            path="ChargeDispersion",
            cfg=config_cd,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder
        )
        dCD = ChargeDispersion.acquire(iCD)
        ChargeDispersion.display(iCD, dCD, plotDisp=True, figNum=5)
        ChargeDispersion.save_data(iCD, dCD)
        ChargeDispersion.save_config(iCD)


def run_charge_sweep(ctx, Spec_relevant_params):
    cfg = ctx.working_config()
    sanity_dump(cfg)
    cfg["reps"] = Spec_relevant_params['reps']
    cfg["rounds"] = Spec_relevant_params['rounds']
    cfg["Gauss"] = Spec_relevant_params['Gauss']

    if Spec_relevant_params['Gauss']:
        cfg['sigma'] = Spec_relevant_params["sigma"]
        cfg["qubit_gain"] = Spec_relevant_params['gain']

    voltage_pts = np.arange(cfg['voltage_start'],
                            cfg['voltage_end'],
                            cfg['voltage_step'])
    # will initialize after first acquisition, once x_pts length is known
    avgamp_map = None
    fig = None
    ax = None
    im = None
    cbar = None
    for i, voltage in enumerate(voltage_pts):
        if voltage > 10:
            print("voltage too high")
            break
        if not ctx.yoko_fixed:
            ramp_to(ctx.yoko, voltage)
        cfg['current_voltage'] = float(voltage)
        Instance_specSlice = QubitSpecSliceFF(
            path="QubitSpecFF",
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder
        )
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        QubitSpecSliceFF.display(
            Instance_specSlice,
            data_specSlice,
            plotDisp=False,
            figNum=2,
            min_sep=Spec_relevant_params["min_sep_MHz"],
            fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
            prominent_ratio=Spec_relevant_params["prominent_ratio"],
        )
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        QubitSpecSliceFF.save_config(Instance_specSlice)
        x_pts = np.array(data_specSlice['data']['x_pts'])
        avgi = np.array(data_specSlice['data']['avgi'][0][0])
        avgq = np.array(data_specSlice['data']['avgq'][0][0])
        # Rotate onto the signal-bearing IQ axis (background-subtracted) instead of
        # the raw magnitude |I+iQ|^2: the magnitude is dominated by the large, noisy
        # background quadrature, which both buries per-slice peaks and washes out the
        # charge-sweep heatmap. The projection gives each slice a ~0 baseline with the
        # qubit feature as a positive bump.
        avgamp0 = project_iq_signal(avgi, avgq)
        # find up to two peaks with a minimum spacing in x-units
        min_spacing = 0.05  # same units as x_pts
        dx = np.mean(np.diff(x_pts))
        min_distance_pts = max(1, int(np.ceil(min_spacing / dx)))

        peak_inds, _ = find_peaks(avgamp0, distance=min_distance_pts)

        # keep the two tallest peaks
        if len(peak_inds) > 0:
            peak_inds = peak_inds[np.argsort(avgamp0[peak_inds])[::-1][:2]]
            peak_inds = peak_inds[np.argsort(x_pts[peak_inds])]  # optional: sort by frequency
            peak_freqs = x_pts[peak_inds]
            peak_vals = avgamp0[peak_inds]
        else:
            peak_freqs = np.array([])
            peak_vals = np.array([])

        print("peak freqs:", peak_freqs)
        # initialize plotting objects once we know x axis length
        if avgamp_map is None:
            avgamp_map = np.full((len(voltage_pts), len(x_pts)), np.nan)
            plt.ion()
            fig, ax = plt.subplots(figsize=(8, 6))
            x_step = x_pts[1] - x_pts[0] if len(x_pts) > 1 else 1
            y_step = voltage_pts[1] - voltage_pts[0] if len(voltage_pts) > 1 else 1

            im = ax.imshow(
                avgamp_map,
                aspect='auto',
                origin='lower',
                interpolation='none',
                extent=[
                    x_pts[0] - x_step / 2,
                    x_pts[-1] + x_step / 2,
                    voltage_pts[0] - y_step / 2,
                    voltage_pts[-1] + y_step / 2
                ]
            )
            cbar = fig.colorbar(im, ax=ax)
            cbar.set_label("rotated IQ projection")

            ax.set_xlabel("Frequency")
            ax.set_ylabel("Voltage")
            ax.set_title("Charge sweep for Qubit Spec")

            plt.show(block=False)
        # store this voltage slice
        avgamp_map[i, :] = avgamp0
        # update heatmap
        im.set_data(avgamp_map)
        # optional: rescale color as data comes in
        im.set_clim(
            np.nanmin(avgamp_map),
            np.nanmax(avgamp_map)
        )
        ax.set_title(f"\nVoltage = {voltage:.4f}")
        fig.canvas.draw_idle()
        plt.pause(0.1)

    fig.savefig(Instance_specSlice.iname[:-4] + "_ChargeSweepHeatmap.png", dpi=300, bbox_inches="tight")
    np.savez(
        Instance_specSlice.fname[:-3] + "_ChargeSweepHeatmap.npz",
        avgamp_map=avgamp_map,
        x_pts=x_pts,
        voltage_pts=voltage_pts,
    )

    plt.ioff()
    plt.close(fig)
