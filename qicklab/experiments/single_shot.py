import time

import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram

from qicklab.analysis.readout import classify_thermal_tail, fit_thermal_population, hist_process
from qicklab.core.experiment import ExperimentClass


class SingleShotProgram(AveragerProgram):
    """g/e single-shot program: optional qubit pulse(s), then one readout per rep."""

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = cfg["shots"]
        self.cfg["rounds"] = 1

        if cfg["sigma"] <= 0:
            raise ValueError("cfg['sigma'] must be positive")
        if cfg["readout_length"] <= 0:
            raise ValueError("cfg['readout_length'] must be positive")
        if not cfg["ro_chs"]:
            raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
        for delay_key in ("adc_trig_offset", "relax_delay"):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])

        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        # Same window/tone as ModifiedRamsey and ActiveResetVerify, so the
        # active-reset threshold transfers: docs/concepts/readout_window.md
        required_tone_us = cfg["adc_trig_offset"] + cfg["readout_length"]
        cfg.setdefault("length", required_tone_us)
        if cfg["length"] < required_tone_us:
            raise ValueError(
                "cfg['length'] must cover cfg['adc_trig_offset'] + "
                f"cfg['readout_length'] ({cfg['length']} us < "
                f"{required_tone_us} us)"
            )

        self.adc_trig_offset_cycles = self.us2cycles(cfg["adc_trig_offset"])
        requested_tone_cycles = self.us2cycles(cfg["length"], gen_ch=cfg["res_ch"])
        self.readout_window_cycles = {
            ch: self.us2cycles(cfg["readout_length"], ro_ch=ch) for ch in cfg["ro_chs"]
        }

        f_time = self.soccfg["tprocs"][0]["f_time"]
        res_f_fabric = self.soccfg["gens"][cfg["res_ch"]]["f_fabric"]
        adc_end_tproc = max(
            self.adc_trig_offset_cycles
            + self.readout_window_cycles[ch] * f_time / self.soccfg["readouts"][ch]["f_output"]
            for ch in cfg["ro_chs"]
        )
        required_tone_cycles = int(np.ceil(adc_end_tproc * res_f_fabric / f_time - 1e-12))
        self.readout_tone_cycles = max(requested_tone_cycles, required_tone_cycles)
        self.readout_tone_extension_cycles = self.readout_tone_cycles - requested_tone_cycles

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles,
        )

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth
        )

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4

        if cfg["flattop_length"] != None:
            self.flattop_length = self.us2cycles(
                self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"]
            )
            trig_length += self.cfg["flattop_length"]

        self.trig_length = self.us2cycles(trig_length)
        self.sync_all(200)

    def body(self):
        self.sync_all()
        if self.cfg["Pulse"]:
            gain_ = self.cfg["qubit_gain"]
            freq_ = self.freq2reg(self.cfg["f_ge"], gen_ch=self.cfg["qubit_ch"])

            for i in range(self.cfg["number_of_pulses"]):
                self.trigger(
                    pins=[0],
                    t=self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
                    width=self.trig_length,
                )
                if self.cfg["flattop_length"] != None:
                    self.setup_and_pulse(
                        self.cfg["qubit_ch"],
                        style="flat_top",
                        freq=freq_,
                        phase=0,
                        gain=gain_,
                        waveform="qubit",
                        length=self.flattop_length,
                    )
                else:
                    self.setup_and_pulse(
                        ch=self.cfg["qubit_ch"],
                        style="arb",
                        freq=freq_,
                        phase=0,
                        gain=gain_,
                        waveform="qubit",
                    )
                self.sync_all(self.us2cycles(0.05))
        self.sync_all(self.us2cycles(0.05))

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def acquire(
        self,
        soc,
        threshold=None,
        angle=None,
        load_pulses=True,
        readouts_per_experiment=1,
        save_experiments=None,
        start_src="internal",
        progress=False,
        debug=False,
    ):
        start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        end = time.time()

        print("time", end - start)
        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []
        for i in range(len(self.di_buf)):
            ro_ch = self.cfg["ro_chs"][i]
            norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
            shots_i0 = self.di_buf[i].reshape((1, self.cfg["reps"])) / norm
            shots_q0 = self.dq_buf[i].reshape((1, self.cfg["reps"])) / norm
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i, all_q


class SingleShotProgramFFMUX(ExperimentClass):
    """g/e single-shot clouds with histogram fidelity/threshold/angle; thermal mode at
    number_of_pulses == 0. See docs/experiments/single_shot.md."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )
        self.threshold = []
        self.angle = []

    def acquire(self, progress=False):
        data = {"config": self.cfg, "data": {}}
        self.data = data
        self.fid = []
        self.threshold = []
        self.angle = []

        read_indices = self.cfg.get("Read_Indeces", None)

        # Thermal mode: undriven shots, split by the tail classifier into the same i_g/q_g/i_e/q_e
        # keys (scatter labels only); the population is the ML mixture weight against a labelled
        # |e> reference (docs/concepts/iq_conventions.md section 7).
        if self.cfg.get("number_of_pulses", 1) == 0:
            self.cfg["Pulse"] = False

            prog = SingleShotProgram(self.soccfg, self.cfg)
            shots_i, shots_q = prog.acquire(self.soc, load_pulses=True)

            # Labelled |e> reference: one pi pulse, acquired right after the undriven shots.
            shots_i_pi = shots_q_pi = None
            if self.cfg.get("thermal_pi_calibration", True):
                prog = SingleShotProgram(
                    self.soccfg, dict(self.cfg, Pulse=True, number_of_pulses=1)
                )
                shots_i_pi, shots_q_pi = prog.acquire(self.soc, load_pulses=True)

            if read_indices is None:
                read_indices = list(range(len(shots_i)))
            elif isinstance(read_indices, (int, np.integer)):
                read_indices = [int(read_indices)]
            else:
                read_indices = list(read_indices)

            read_indices = read_indices[: len(shots_i)]
            if not read_indices:
                read_indices = list(range(len(shots_i)))
            if shots_i_pi is not None and len(read_indices) > 1:
                # The pi pulse drives only the qubit on qubit_ch. Another read's "pi" cloud is a
                # second undriven cloud: normally NaN, but if that cloud moved between the two
                # runs (readout drift, cross-Kerr/ZZ to the pi'd qubit) the fit can return a
                # finite, meaningless population with no further warning.
                print(
                    f"[Thermal population] WARNING {len(read_indices)} reads: the pi reference "
                    f"drives only the qubit on qubit_ch ({self.cfg.get('qubit_ch')}); only that "
                    "qubit's read is a population, even if another read returns a number"
                )

            for i, read_index in enumerate(read_indices):
                i_th = np.asarray(shots_i[i][0])
                q_th = np.asarray(shots_q[i][0])
                tail = classify_thermal_tail(i_th, q_th, self.cfg, read_index)
                i_g, q_g, i_e, q_e = tail["i_g"], tail["q_g"], tail["i_e"], tail["q_e"]
                binary_states, tail_fraction = tail["labels"], tail["tail_fraction"]
                center_g, center_e = tail["center_g"], tail["center_e"]
                md2, proj, threshold_proj = (
                    tail["md2"],
                    tail["projection"],
                    tail["projection_threshold"],
                )
                angle, threshold, fid = tail["angle"], tail["threshold"], tail["fid"]

                self.data["data"]["i_g" + str(read_index)] = i_g
                self.data["data"]["q_g" + str(read_index)] = q_g
                self.data["data"]["i_e" + str(read_index)] = i_e
                self.data["data"]["q_e" + str(read_index)] = q_e

                self.data["data"]["i_thermal" + str(read_index)] = i_th
                self.data["data"]["q_thermal" + str(read_index)] = q_th
                self.data["data"]["thermal_labels" + str(read_index)] = binary_states
                self.data["data"]["thermal_tail_fraction" + str(read_index)] = tail_fraction
                self.data["data"]["thermal_center_g" + str(read_index)] = center_g
                self.data["data"]["thermal_center_e" + str(read_index)] = center_e
                self.data["data"]["thermal_md2" + str(read_index)] = md2
                self.data["data"]["thermal_projection" + str(read_index)] = proj
                self.data["data"]["thermal_projection_threshold" + str(read_index)] = threshold_proj

                i_pi = q_pi = e_center_cfg = None
                if shots_i_pi is not None:
                    i_pi = np.asarray(shots_i_pi[i][0])
                    q_pi = np.asarray(shots_q_pi[i][0])
                    self.data["data"]["i_pi" + str(read_index)] = i_pi
                    self.data["data"]["q_pi" + str(read_index)] = q_pi
                elif self.cfg.get("thermal_e_center") is not None:
                    e_center_cfg = np.asarray(self.cfg["thermal_e_center"], dtype=float)
                    if e_center_cfg.ndim == 2:  # one (I, Q) pair per read
                        e_center_cfg = e_center_cfg[i]
                try:
                    pop = fit_thermal_population(
                        i_th, q_th, i_pi=i_pi, q_pi=q_pi, e_center=e_center_cfg
                    )
                except Exception as err:
                    print(f"[Thermal population] Read {read_index}: fit failed: {err}")
                    pop = {
                        "population": np.nan,
                        "population_err": np.nan,
                        "pi_population": np.nan,
                        "e_width_ratio": np.nan,
                        "g_center": np.full(2, np.nan),
                        "e_center": np.full(2, np.nan),
                        "cov": np.full((2, 2), np.nan),
                        "warnings": [],
                    }
                for warning in pop["warnings"]:
                    print(f"[Thermal population] Read {read_index}: WARNING {warning}")
                if np.isfinite(pop["population"]):
                    pi_txt = (
                        f", pi-run excited {100 * pop['pi_population']:.1f} %"
                        if np.isfinite(pop["pi_population"])
                        else ""
                    )
                    p_txt = (
                        f"p = {100 * pop['population']:.3f} +- {100 * pop['population_err']:.3f} %"
                    )
                else:
                    pi_txt = ""
                    p_txt = "p = NaN (not estimated, see WARNING)"
                print(
                    f"[Thermal population] Read {read_index}: {p_txt} "
                    f"(tail fraction {100 * tail_fraction:.3f} %{pi_txt})"
                )
                self.data["data"]["thermal_population" + str(read_index)] = pop["population"]
                self.data["data"]["thermal_population_err" + str(read_index)] = pop[
                    "population_err"
                ]
                self.data["data"]["thermal_pi_population" + str(read_index)] = pop["pi_population"]
                self.data["data"]["thermal_fit_e_width_ratio" + str(read_index)] = pop[
                    "e_width_ratio"
                ]
                self.data["data"]["thermal_fit_g_center" + str(read_index)] = pop["g_center"]
                self.data["data"]["thermal_fit_e_center" + str(read_index)] = pop["e_center"]
                self.data["data"]["thermal_fit_cov" + str(read_index)] = pop["cov"]

                if str(read_index) != str(i):
                    self.data["data"]["i_g" + str(i)] = i_g
                    self.data["data"]["q_g" + str(i)] = q_g
                    self.data["data"]["i_e" + str(i)] = i_e
                    self.data["data"]["q_e" + str(i)] = q_e
                    self.data["data"]["i_thermal" + str(i)] = i_th
                    self.data["data"]["q_thermal" + str(i)] = q_th
                    self.data["data"]["thermal_labels" + str(i)] = binary_states
                    # display() reads suffix 0: mirror everything its title and markers use.
                    for key in (
                        "thermal_population",
                        "thermal_population_err",
                        "thermal_tail_fraction",
                        "thermal_center_g",
                        "thermal_center_e",
                    ):
                        self.data["data"][key + str(i)] = self.data["data"][key + str(read_index)]

                self.fid.append(fid)
                self.threshold.append(threshold)
                self.angle.append(angle)

            self.data["data"]["threshold"] = self.threshold
            self.data["data"]["angle"] = self.angle
            self.data["data"]["thermal_mode"] = True
            self.data["data"]["thermal_fit_type"] = 1

            return self.data

        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ig, shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie, shots_qe = prog.acquire(self.soc, load_pulses=True)

        if read_indices is None:
            read_indices = list(range(len(shots_ig)))
        elif isinstance(read_indices, (int, np.integer)):
            read_indices = [int(read_indices)]
        else:
            read_indices = list(read_indices)

        read_indices = read_indices[: len(shots_ig)]
        if not read_indices:
            read_indices = list(range(len(shots_ig)))

        for i, read_index in enumerate(read_indices):
            i_g = shots_ig[i][0]
            q_g = shots_qg[i][0]
            i_e = shots_ie[i][0]
            q_e = shots_qe[i][0]

            self.data["data"]["i_g" + str(read_index)] = i_g
            self.data["data"]["q_g" + str(read_index)] = q_g
            self.data["data"]["i_e" + str(read_index)] = i_e
            self.data["data"]["q_e" + str(read_index)] = q_e

            if str(read_index) != str(i):
                self.data["data"]["i_g" + str(i)] = i_g
                self.data["data"]["q_g" + str(i)] = q_g
                self.data["data"]["i_e" + str(i)] = i_e
                self.data["data"]["q_e" + str(i)] = q_e

            fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)

            self.data_in_hist = [i_g, q_g, i_e, q_e]
            self.fid.append(fid)
            self.threshold.append(threshold)
            self.angle.append(angle)

        self.data["data"]["threshold"] = self.threshold
        self.data["data"]["angle"] = self.angle
        self.data["data"]["thermal_mode"] = False

        return self.data

    def display(self, data=None, plotDisp=False, figNum=1, ran=None, **kwargs):
        if data is None:
            data = self.data

        thermal_mode = data["data"].get("thermal_mode", False)

        for read_index in [0]:
            title = (
                "Read Length: "
                + str(self.cfg["readout_length"])
                + "us"
                + ", Read: "
                + str(read_index)
            )

            if thermal_mode:
                i_th = np.asarray(data["data"]["i_thermal" + str(read_index)])
                q_th = np.asarray(data["data"]["q_thermal" + str(read_index)])
                labels = np.asarray(data["data"]["thermal_labels" + str(read_index)])

                p_e = data["data"].get("thermal_population" + str(read_index), np.nan)
                p_err = data["data"].get("thermal_population_err" + str(read_index), np.nan)
                f_tail = data["data"].get(
                    "thermal_tail_fraction" + str(read_index),
                    data["data"].get("thermal_population_tail" + str(read_index), np.nan),
                )

                plt.figure(figNum, figsize=(8, 6))
                plt.scatter(
                    i_th[labels == 0], q_th[labels == 0], s=8, alpha=0.4, label="ground-like"
                )
                plt.scatter(
                    i_th[labels == 1], q_th[labels == 1], s=8, alpha=0.4, label="excited-like"
                )

                if "thermal_gmm_means" + str(read_index) in data["data"]:
                    centers = np.asarray(data["data"]["thermal_gmm_means" + str(read_index)])
                    plt.plot(centers[:, 0], centers[:, 1], "kx", markersize=12, label="fit centers")

                elif "thermal_center_g" + str(read_index) in data["data"]:
                    center_g = np.asarray(data["data"]["thermal_center_g" + str(read_index)])
                    center_e = np.asarray(data["data"]["thermal_center_e" + str(read_index)])
                    plt.plot(center_g[0], center_g[1], "kx", markersize=12, label="ground center")
                    if not np.any(np.isnan(center_e)):
                        plt.plot(
                            center_e[0], center_e[1], "rx", markersize=12, label="excited center"
                        )

                plt.xlabel("I")
                plt.ylabel("Q")
                plt.title(
                    title
                    + "\n"
                    + f"Thermal population = {100 * p_e:.2f} +- {100 * p_err:.2f}% "
                    + f"(tail fraction {100 * f_tail:.2f}%)"
                )
                plt.legend()
                plt.tight_layout()
                plt.savefig(self.iname)

                self.fid = np.nan
                self.threshold = data["data"]["threshold"][0]
                self.angle = data["data"]["angle"][0]

                if plotDisp:
                    plt.show(block=True)
                    plt.pause(0.1)
                else:
                    plt.close()

            else:
                i_g = data["data"]["i_g" + str(read_index)]
                q_g = data["data"]["q_g" + str(read_index)]
                i_e = data["data"]["i_e" + str(read_index)]
                q_e = data["data"]["q_e" + str(read_index)]

                fid, threshold, angle = hist_process(
                    data=[i_g, q_g, i_e, q_e], plot=True, ran=None, title=title
                )

                try:
                    fid = min(float(fid), 1.0)
                except Exception:
                    pass

                plt.suptitle(self.titlename + " , Read: " + str(read_index))

                self.fid = fid
                self.threshold = threshold
                self.angle = angle

                plt.savefig(self.iname)

                if plotDisp:
                    plt.show(block=True)
                    plt.pause(0.1)
                else:
                    plt.close()

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
