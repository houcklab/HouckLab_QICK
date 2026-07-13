from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time


class SingleShotProgramWITHUPDATE(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        cfg["start"]=0
        cfg["step"]=cfg["qubit_gain"]
        cfg["reps"]=cfg["shots"]
        cfg["expts"]=2

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get frequency register for qubit_ch

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value


        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])


        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        # convert frequency to dac frequency (ensuring it is an available adc frequency)

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        print(self.pulse_sigma, self.pulse_qubit_lenth)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                 waveform="qubit")

        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(dac_t0=self.dac_t0)
        for i in range(len(self.cfg["qubit_gains"])):
            gain_ = self.cfg["qubit_gains"][i]
            freq_ = self.freq2reg(self.cfg["f_ges"][i], gen_ch=self.cfg["qubit_ch"])
            if i == 0:
                time = self.us2cycles(1)
            else:
                time = 'auto'
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                             gain=gain_,
                             waveform="qubit", t=time)

        # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  #play probe pulse
        self.sync_all(dac_t0=self.dac_t0)

        # self.FFPulses(self.FFReadouts * 1.5, 0.03)
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', int(self.cfg["step"]/2))  # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):
        start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)
        end = time.time()

        print('time', end - start)
        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []
        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
            shots_q0=self.dq_buf[i].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


    # def collect_shots(self):
    #     shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
    #     shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
    #     print(len(self.dq_buf))
    #     return shots_i0,shots_q0
# ====================================================== #
class SingleShotProgram(AveragerProgram):
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

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch

        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value

        # Active-reset thresholds are calibrated from this program and consumed
        # by ModifiedRamsey/ActiveResetVerify. All three programs must therefore
        # integrate the same physical ADC window and play the same resonator tone.
        # Convert each duration using its owning hardware clock, then extend the
        # tone by the minimum generator cycles needed after cross-clock rounding.
        required_tone_us = cfg["adc_trig_offset"] + cfg["readout_length"]
        cfg.setdefault("length", required_tone_us)
        if cfg["length"] < required_tone_us:
            raise ValueError(
                "cfg['length'] must cover cfg['adc_trig_offset'] + "
                f"cfg['readout_length'] ({cfg['length']} us < "
                f"{required_tone_us} us)"
            )

        self.adc_trig_offset_cycles = self.us2cycles(cfg["adc_trig_offset"])
        requested_tone_cycles = self.us2cycles(
            cfg["length"], gen_ch=cfg["res_ch"]
        )
        self.readout_window_cycles = {
            ch: self.us2cycles(cfg["readout_length"], ro_ch=ch)
            for ch in cfg["ro_chs"]
        }

        f_time = self.soccfg["tprocs"][0]["f_time"]
        res_f_fabric = self.soccfg["gens"][cfg["res_ch"]]["f_fabric"]
        adc_end_tproc = max(
            self.adc_trig_offset_cycles
            + self.readout_window_cycles[ch]
            * f_time / self.soccfg["readouts"][ch]["f_output"]
            for ch in cfg["ro_chs"]
        )
        required_tone_cycles = int(np.ceil(
            adc_end_tproc * res_f_fabric / f_time - 1e-12
        ))
        self.readout_tone_cycles = max(
            requested_tone_cycles, required_tone_cycles
        )
        self.readout_tone_extension_cycles = (
            self.readout_tone_cycles - requested_tone_cycles
        )

        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.readout_window_cycles[ch],
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.readout_tone_cycles)

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        # print(self.pulse_sigma, self.pulse_qubit_lenth)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)
        # self.trig_length = self.us2cycles((cfg["trig_buffer_start"] +
        #                                    cfg["trig_buffer_end"])) + self.pulse_qubit_lenth * self.cfg["number_of_pulses"]
        # if cfg["flattop_length"] != None:
        #     self.flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
        #     self.trig_length += self.flattop_length * self.cfg["number_of_pulses"]

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4

        if cfg["flattop_length"] != None:
            self.flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            # trig_length += self.flattop_length * self.cfg["number_of_pulses"]
            trig_length += self.cfg["flattop_length"]


        self.trig_length = self.us2cycles(trig_length)
        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all()
        if self.cfg["Pulse"]:
            gain_ = self.cfg["qubit_gain"]
            freq_ = self.freq2reg(self.cfg["f_ge"], gen_ch=self.cfg["qubit_ch"])
            # print(freq_, gain_, time)
            # self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
            #              width=self.trig_length)

            for i in range(self.cfg["number_of_pulses"]):
                self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
                             width=self.trig_length)
                if self.cfg["flattop_length"] != None:
                    self.setup_and_pulse(self.cfg["qubit_ch"], style='flat_top', freq=freq_, phase=0,
                                     gain=gain_,
                                             waveform="qubit",
                                             length=self.flattop_length)
                else:
                    self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                     gain=gain_,
                                     waveform="qubit")
                self.sync_all(self.us2cycles(0.05))
            # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  #play probe pulse
        self.sync_all(self.us2cycles(0.05))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.adc_trig_offset_cycles,
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):
        start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress)#  debug=debug)
        end = time.time()

        print('time', end - start)
        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []
        # print(self.di_buf)#, self.di_buf[1][:30])
        for i in range(len(self.di_buf)):
            ro_ch = self.cfg["ro_chs"][i]
            norm = self.us2cycles(self.cfg['readout_length'], ro_ch=ro_ch)
            shots_i0=self.di_buf[i].reshape((1,self.cfg["reps"])) / norm
            shots_q0=self.dq_buf[i].reshape((1,self.cfg["reps"])) / norm
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


    # def collect_shots(self):
    #     shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
    #     shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
    #     print(len(self.dq_buf))
    #     return shots_i0,shots_q0


class SingleShotProgramFFMUX(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.threshold = []
        self.angle = []

    def acquire(self, progress=False):
        data = {'config': self.cfg, 'data': {}}
        self.data = data
        self.fid = []
        self.threshold = []
        self.angle = []

        read_indices = self.cfg.get("Read_Indeces", None)

        # ======================================================
        # Thermal population mode: number_of_pulses == 0
        # Only acquire no-pulse shots, then store them in the
        # same i_g/q_g/i_e/q_e structure so display/save still work.
        # ======================================================
        if self.cfg.get("number_of_pulses", 1) == 0:
            self.cfg["Pulse"] = False

            prog = SingleShotProgram(self.soccfg, self.cfg)
            shots_i, shots_q = prog.acquire(self.soc, load_pulses=True)

            if read_indices is None:
                read_indices = list(range(len(shots_i)))
            elif isinstance(read_indices, (int, np.integer)):
                read_indices = [int(read_indices)]
            else:
                read_indices = list(read_indices)

            read_indices = read_indices[:len(shots_i)]
            if not read_indices:
                read_indices = list(range(len(shots_i)))

            for i, read_index in enumerate(read_indices):
                i_th = np.asarray(shots_i[i][0])
                q_th = np.asarray(shots_q[i][0])
                iq = np.column_stack([i_th, q_th])

                try:
                    from sklearn.covariance import MinCovDet

                    # Robust fit to dominant/main blob
                    mcd = MinCovDet(support_fraction=0.75, random_state=0).fit(iq)
                    center_g = mcd.location_
                    cov_g = mcd.covariance_
                    inv_cov_g = np.linalg.pinv(cov_g)

                    # Mahalanobis distance from main blob
                    diff = iq - center_g
                    md2 = np.einsum("ij,jk,ik->i", diff, inv_cov_g, diff)

                    # Find outlier / protrusion candidates
                    # 95% chi-square threshold for 2D is ~5.99; use 6-9 depending on overlap
                    tail_md2_threshold = self.cfg.get("thermal_tail_md2_threshold", 6.0)
                    tail_candidates = md2 > tail_md2_threshold

                    # Direction of protrusion: use mean of farthest points
                    n_tail_seed = max(10, int(0.05 * len(iq)))
                    far_idx = np.argsort(md2)[-n_tail_seed:]
                    center_e_seed = np.mean(iq[far_idx], axis=0)

                    axis = center_e_seed - center_g
                    axis_norm = np.linalg.norm(axis)

                    if axis_norm < 1e-12:
                        raise RuntimeError("Could not determine thermal protrusion axis.")

                    axis = axis / axis_norm

                    # Project all points along protrusion axis
                    proj = diff @ axis

                    # Robust width of main blob along that axis
                    proj_main = proj[~tail_candidates]
                    if len(proj_main) < 10:
                        proj_main = proj

                    med_proj = np.median(proj_main)
                    mad_proj = np.median(np.abs(proj_main - med_proj))
                    sigma_proj = 1.4826 * mad_proj

                    if sigma_proj <= 1e-12:
                        sigma_proj = np.std(proj_main)

                    # Classify excited-like population as one-sided positive protrusion
                    # Use 2.0-3.0 depending on desired aggressiveness
                    tail_sigma_threshold = self.cfg.get("thermal_tail_sigma_threshold", 2.5)
                    threshold_proj = med_proj + tail_sigma_threshold * sigma_proj

                    binary_states = (proj > threshold_proj).astype(int)

                    # Soft-ish population estimate from tail probability
                    # This is conservative: only counts points sticking out of main blob
                    thermal_population = float(np.mean(binary_states))

                    i_g = i_th[binary_states == 0]
                    q_g = q_th[binary_states == 0]
                    i_e = i_th[binary_states == 1]
                    q_e = q_th[binary_states == 1]

                    center_e = np.array([
                        np.mean(i_e) if len(i_e) > 0 else np.nan,
                        np.mean(q_e) if len(q_e) > 0 else np.nan,
                    ])

                    angle = -np.arctan2(axis[1], axis[0])
                    threshold = (
                            center_g[0] * np.cos(angle)
                            - center_g[1] * np.sin(angle)
                            + threshold_proj
                    )

                    fid = np.nan

                    print(
                        f"[Thermal protrusion] Read {read_index}: "
                        f"P_excited_tail={thermal_population:.5f}, "
                        f"N_excited={np.sum(binary_states)}, "
                        f"threshold_proj={threshold_proj:.4f}, "
                        f"sigma_proj={sigma_proj:.4f}, "
                        f"angle={angle:.4f}"
                    )

                except Exception as err:
                    print(f"[SingleShot thermal mode] protrusion fit failed: {err}")

                    binary_states = np.zeros(len(i_th), dtype=int)
                    thermal_population = np.nan
                    angle = 0.0
                    threshold = np.nan
                    fid = np.nan

                    i_g = i_th
                    q_g = q_th
                    i_e = np.array([])
                    q_e = np.array([])

                    center_g = np.array([np.nan, np.nan])
                    center_e = np.array([np.nan, np.nan])
                    md2 = np.full(len(i_th), np.nan)
                    proj = np.full(len(i_th), np.nan)
                    threshold_proj = np.nan


                self.data['data']['i_g' + str(read_index)] = i_g
                self.data['data']['q_g' + str(read_index)] = q_g
                self.data['data']['i_e' + str(read_index)] = i_e
                self.data['data']['q_e' + str(read_index)] = q_e

                self.data['data']['i_thermal' + str(read_index)] = i_th
                self.data['data']['q_thermal' + str(read_index)] = q_th
                self.data['data']['thermal_labels' + str(read_index)] = binary_states
                self.data['data']['thermal_population_tail' + str(read_index)] = thermal_population
                self.data['data']['thermal_center_g' + str(read_index)] = center_g
                self.data['data']['thermal_center_e' + str(read_index)] = center_e
                self.data['data']['thermal_md2' + str(read_index)] = md2
                self.data['data']['thermal_projection' + str(read_index)] = proj
                self.data['data']['thermal_projection_threshold' + str(read_index)] = threshold_proj

                if str(read_index) != str(i):
                    self.data['data']['i_g' + str(i)] = i_g
                    self.data['data']['q_g' + str(i)] = q_g
                    self.data['data']['i_e' + str(i)] = i_e
                    self.data['data']['q_e' + str(i)] = q_e
                    self.data['data']['i_thermal' + str(i)] = i_th
                    self.data['data']['q_thermal' + str(i)] = q_th
                    self.data['data']['thermal_labels' + str(i)] = binary_states

                self.fid.append(fid)
                self.threshold.append(threshold)
                self.angle.append(angle)

            self.data['data']['threshold'] = self.threshold
            self.data['data']['angle'] = self.angle
            self.data['data']['thermal_mode'] = True
            self.data['data']['thermal_fit_type'] = 1

            return self.data
        # ======================================================
        # Normal single-shot mode: acquire no-pulse and pulsed clouds
        # ======================================================
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

        read_indices = read_indices[:len(shots_ig)]
        if not read_indices:
            read_indices = list(range(len(shots_ig)))

        for i, read_index in enumerate(read_indices):
            i_g = shots_ig[i][0]
            q_g = shots_qg[i][0]
            i_e = shots_ie[i][0]
            q_e = shots_qe[i][0]

            self.data['data']['i_g' + str(read_index)] = i_g
            self.data['data']['q_g' + str(read_index)] = q_g
            self.data['data']['i_e' + str(read_index)] = i_e
            self.data['data']['q_e' + str(read_index)] = q_e

            if str(read_index) != str(i):
                self.data['data']['i_g' + str(i)] = i_g
                self.data['data']['q_g' + str(i)] = q_g
                self.data['data']['i_e' + str(i)] = i_e
                self.data['data']['q_e' + str(i)] = q_e

            fid, threshold, angle = hist_process(
                data=[i_g, q_g, i_e, q_e],
                plot=False,
                ran=None
            )

            self.data_in_hist = [i_g, q_g, i_e, q_e]
            self.fid.append(fid)
            self.threshold.append(threshold)
            self.angle.append(angle)

        self.data['data']['threshold'] = self.threshold
        self.data['data']['angle'] = self.angle
        self.data['data']['thermal_mode'] = False

        return self.data
        #
        # plt.figure(10, figsize=(10, 7))
        # plt.scatter(shots_i0[0], shots_q0[0], label='g', color='r', marker='*', alpha=0.5)
        # plt.show()

        # data = {'config': self.cfg, 'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}}
        # self.data = data
        #
        # ### use the helper histogram to find the fidelity and such
        # fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None) ### arbitrary ran, change later
        # self.data_in_hist = [i_g, q_g, i_e, q_e]
        # # stop = 100
        # # plt.figure(101)
        # # plt.plot(i_g[0:stop], q_g[0:stop], 'o')
        # # plt.plot(i_e[0:stop], q_e[0:stop], 'o')
        # # plt.show()
        #
        #
        # self.fid = fid
        # self.threshold = threshold
        # self.angle = angle
        #
        # return data

    # def acquireUPDATE(self, progress=False, debug=False):
    #     #### pull the data from the single hots
    #     self.cfg["IDataArray"] = [None, None, None, None]
    #     self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Pulse'], 0, 1)
    #     self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Pulse'], 0, 2)
    #     self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Pulse'], 0, 3)
    #     self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Pulse'], 0, 4)
    #     prog = SingleShotProgram(self.soccfg, self.cfg)
    #     shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)
    #
    #     data = {'config': self.cfg, 'data': {}}
    #             # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}
    #     self.data = data
    #     for i, read_index in enumerate(self.cfg['Read_Indeces']):
    #         i_g = shots_i0[i][0]
    #         q_g = shots_q0[i][0]
    #         i_e = shots_i0[i][1]
    #         q_e = shots_q0[i][1]
    #         self.data['data']['i_g' + str(read_index)] = i_g
    #         self.data['data']['q_g' + str(read_index)] = q_g
    #         self.data['data']['i_e' + str(read_index)] = i_e
    #         self.data['data']['q_e' + str(read_index)] = q_e
    #
    #         fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None) ### arbitrary ran, change later
    #         self.data_in_hist = [i_g, q_g, i_e, q_e]
    #         self.fid = fid
    #         self.threshold = threshold
    #         self.angle = angle
    #     return self.data
    #     #
    #     # plt.figure(10, figsize=(10, 7))
    #     # plt.scatter(shots_i0[0], shots_q0[0], label='g', color='r', marker='*', alpha=0.5)
    #     # plt.show()
    #
    #     # data = {'config': self.cfg, 'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}}
    #     # self.data = data
    #     #
    #     # ### use the helper histogram to find the fidelity and such
    #     # fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None) ### arbitrary ran, change later
    #     # self.data_in_hist = [i_g, q_g, i_e, q_e]
    #     # # stop = 100
    #     # # plt.figure(101)
    #     # # plt.plot(i_g[0:stop], q_g[0:stop], 'o')
    #     # # plt.plot(i_e[0:stop], q_e[0:stop], 'o')
    #     # # plt.show()
    #     #
    #     #
    #     # self.fid = fid
    #     # self.threshold = threshold
    #     # self.angle = angle
    #     #
    #     # return data

    def display(self, data=None, plotDisp=False, figNum=1, ran=None, **kwargs):
        if data is None:
            data = self.data

        thermal_mode = data["data"].get("thermal_mode", False)

        for read_index in [0]:

            title = 'Read Length: ' + str(self.cfg["readout_length"]) + "us" + ", Read: " + str(read_index)

            if thermal_mode:
                i_th = np.asarray(data["data"]["i_thermal" + str(read_index)])
                q_th = np.asarray(data["data"]["q_thermal" + str(read_index)])
                labels = np.asarray(data["data"]["thermal_labels" + str(read_index)])

                p_e = data["data"].get(
                    "thermal_population_soft" + str(read_index),
                    data["data"].get(
                        "thermal_population_tail" + str(read_index),
                        np.nan
                    )
                )

                plt.figure(figNum, figsize=(8, 6))
                plt.scatter(
                    i_th[labels == 0],
                    q_th[labels == 0],
                    s=8,
                    alpha=0.4,
                    label="ground-like"
                )
                plt.scatter(
                    i_th[labels == 1],
                    q_th[labels == 1],
                    s=8,
                    alpha=0.4,
                    label="excited-like"
                )

                if "thermal_gmm_means" + str(read_index) in data["data"]:
                    centers = np.asarray(data["data"]["thermal_gmm_means" + str(read_index)])
                    plt.plot(centers[:, 0], centers[:, 1], "kx", markersize=12, label="fit centers")

                elif "thermal_center_g" + str(read_index) in data["data"]:
                    center_g = np.asarray(data["data"]["thermal_center_g" + str(read_index)])
                    center_e = np.asarray(data["data"]["thermal_center_e" + str(read_index)])
                    plt.plot(center_g[0], center_g[1], "kx", markersize=12, label="ground center")
                    if not np.any(np.isnan(center_e)):
                        plt.plot(center_e[0], center_e[1], "rx", markersize=12, label="excited center")

                plt.xlabel("I")
                plt.ylabel("Q")
                plt.title(
                    title + "\n"
                    + f"Thermal population mode: P_excited-like = {100 * p_e:.2f}%"
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
                    data=[i_g, q_g, i_e, q_e],
                    plot=True,
                    ran=None,
                    title=title
                )

                # Guard against unphysical display values
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
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


class LoopbackProgramSingleShotWorking(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### first do nothing, then apply the pi pulse
        cfg["start"]=0
        cfg["step"]=cfg["qubit_gain"]
        cfg["reps"]=cfg["shots"]
        cfg["expts"]=2

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get frequency register for qubit_ch

        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_readout_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
                                 length=self.us2cycles(self.cfg["readout_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        #FF Start
        for FF_info in cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
        self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]


        self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
        self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]
        self.FF_Gain3_exp = self.cfg["FF_list_exp"][2][1]

        self.FFChannels = [self.FF_Channel1, self.FF_Channel2, self.FF_Channel3]
        self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])
        self.FFExpts = np.array([self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp])

        #FF End

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        # self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
        #                          length=self.us2cycles(self.cfg["readout_length"] + self.cfg["adc_trig_offset"]),
        #                          ) # mode="periodic")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=read_freq, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))
        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(200)  # align channels and wait 50ns

        self.FFPulses(-1 * self.FFExpts, self.qubit_pulseLength + self.us2cycles(2))

        self.sync_all(self.us2cycles(2))  # align channels and wait 50ns

        self.FFPulses(self.FFExpts, self.qubit_pulseLength + self.us2cycles(2))

        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(2))  #play probe pulse
        self.sync_all() # align


        self.FFPulses(self.FFReadouts, self.us2cycles(self.cfg["length"]))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(1))

        self.FFPulses(-1 * self.FFReadouts, self.us2cycles(self.cfg["length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

        # wait = True
        # syncdelay=self.us2cycles(self.cfg["relax_delay"])
        # self.trigger([0], pins=None, adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))
        # self.pulse(ch=self.cfg["res_ch"])
        # self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"]) + self.us2cycles(self.cfg["readout_length"]))
        # # self.waiti(0, self.us2cycles(self.cfg["readout_length"]) + 100)
        # if wait:
        #     # tProc should wait for the readout to complete.
        #     # This prevents loop counters from getting incremented before the data is available.
        #     self.wait_all()
        # if syncdelay is not None:
        #     self.sync_all(syncdelay)
        #
        # # self.synci(self.us2cycles(self.cfg["relax_delay"]))
        # self.measure(pulse_ch=self.cfg["res_ch"],
        #              adcs=[0],
        #              adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
        #              wait=True,
        #              syncdelay=self.us2cycles(self.cfg["relax_delay"]))



    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', int(self.cfg["step"]/2))  # update frequency list index

    def FFPulses(self, list_of_gains, length):
        for i, gain in enumerate(list_of_gains):
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)

        return shots_i0,shots_q0


import pickle
def QuadExponentialFit(t, A1, T1, A2, T2, A3, T3, A4, T4):
    return(A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2) + A3 * np.exp(-t / T3) + A4 * np.exp(-t / T4))

def Compensated_AWG(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = QuadExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3], Fit_Parameters[4], Fit_Parameters[5],
                                   Fit_Parameters[6], Fit_Parameters[7])
    analytic_n[analytic_n < -0.8] = -0.8
    v_awg = ideal_AWG / (1 + analytic_n)
    v_awg[v_awg > maximum] = maximum
    return(time, v_awg)

def DoubleExponentialFit(t, A1, T1, A2, T2):
    return (A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2))

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = DoubleExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3])
    print('analytic_n Before correction', analytic_n[:30])
    analytic_n[analytic_n < -0.7] = -0.7
    print('analytic_n After correction', analytic_n[:30])

    v_awg = ideal_AWG / (1 + analytic_n)
    print('v_awg Before correction', v_awg[:30])

    v_awg[v_awg > maximum] = maximum
    print('v_awg After correction', v_awg[:30])

    return(time, v_awg)

# Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
# Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
# Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
#
# v_awg_Q1 = Compensated_AWG(600 * 16 * 3, Qubit1_)[1]
# v_awg_Q2 = Compensated_AWG(600 * 16 * 3, Qubit2_)[1]
# v_awg_Q4 = Compensated_AWG(600 * 16 * 3, Qubit4_)[1]

v_awg_Q1 = np.ones(600 * 16 * 3)
v_awg_Q2 = np.ones(600 * 16 * 3)
v_awg_Q4 = np.ones(600 * 16 * 3)

Compensated_pulse_list = [v_awg_Q1, v_awg_Q2, v_awg_Q2, v_awg_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)
