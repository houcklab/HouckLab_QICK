from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time


# ====================================================== #
class SingleShotProgram_RB(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.gate_seq = cfg['gate_seq']
        self.gate_set = cfg['gate_set']
        cfg["reps"] = cfg["shots"]
        self.cfg["rounds"] = 1

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch

        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value

        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        # self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        # self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.pulse_sigma_pi2 = self.us2cycles(cfg["sigma_pi2"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth_pi2 = self.us2cycles(cfg["sigma_pi2"] * 4, gen_ch=self.cfg["qubit_ch"])

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
        self.add_gauss(ch=self.cfg["qubit_ch"], name="qubitpi2", sigma=self.pulse_sigma_pi2,
                       length=self.pulse_qubit_lenth_pi2)
        self.add_gauss(ch=self.cfg["qubit_ch"], name="qubitpi", sigma=self.pulse_sigma,
                       length=self.pulse_qubit_lenth)

        self.trig_length = self.us2cycles(trig_length)
        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all()
        if self.cfg["Pulse"]:
            freq_ = self.freq2reg(self.cfg["f_ge"], gen_ch=self.cfg["qubit_ch"])
            self.phase_ref = 0
            for g in self.gate_seq:
                ginfo = self.cfg["gate_set"][g]
                if g == "Z":
                    self.phase_ref += 180
                elif g == "Z/2":
                    self.phase_ref += 90
                elif g == "-Z/2":
                    self.phase_ref += -90
                elif g == "I" or g == "I/2":
                    continue
                else:
                    phase = self.deg2reg(ginfo["phase"] + self.phase_ref, gen_ch=self.cfg["qubit_ch"])
                    if g[-1] == '2':
                        waveform = 'qubitpi2'
                    else:
                        waveform = 'qubitpi'

                    self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=phase,
                                         gain=ginfo["gain"], waveform=waveform)
                self.sync_all(3)
        self.sync_all(self.us2cycles(1))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))
        self.sync_all(self.us2cycles(10))

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):
        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []
        # print(self.di_buf)#, self.di_buf[1][:30])
        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
            shots_q0=self.dq_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


    # def collect_shots(self):
    #     shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
    #     shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
    #     print(len(self.dq_buf))
    #     return shots_i0,shots_q0


class SingleShotProgramFFMUX_RB(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.threshold = []
        self.angle = []

    def acquire(self, theta, threshold, progress=False, debug=False):
        self.cfg["Pulse"] = True
        prog = SingleShotProgram_RB(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

        data = {'config': self.cfg, 'data': {}}
                # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}
        self.data = data
        self.fid = []
        ie = shots_ie[0][0]
        qe = shots_qe[0][0]
        self.data['data']['i_e'] = ie
        self.data['data']['q_e'] = qe

        ie_new = ie * np.cos(theta) - qe * np.sin(theta)
        qe_new = ie * np.sin(theta) + qe * np.cos(theta)
        self.data['data']['i_e'] = ie_new
        self.data['data']['q_e'] = qe_new

        # plt.scatter(ie_new, qe_new, label='g', color='r', marker='*', alpha=0.5)
        # plt.vlines(threshold, np.min(qe_new), np.max(qe_new))
        # plt.show()
        count = np.sum(ie_new < threshold)
        # plt.plot()

        population = count / float(len(ie_new))
        # print(population)

        self.data['data']['population'] = population
        return self.data
    def acquire_single(self, progress=False, debug=False):
        self.cfg["Pulse"] = False
        prog = SingleShotProgram_RB(self.soccfg, self.cfg)
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram_RB(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

        data = {'config': self.cfg, 'data': {}}
                # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}
        self.data = data
        self.fid = []
        for i, read_index in enumerate([0]):
            i_g = shots_ig[i][0]
            q_g = shots_qg[i][0]
            i_e = shots_ie[i][0]
            q_e = shots_qe[i][0]
            self.data['data']['i_g' + str(read_index)] = i_g
            self.data['data']['q_g' + str(read_index)] = q_g
            self.data['data']['i_e' + str(read_index)] = i_e
            self.data['data']['q_e' + str(read_index)] = q_e

            fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None) ### arbitrary ran, change later
            self.data_in_hist = [i_g, q_g, i_e, q_e]
            self.fid.append(fid)
            self.threshold.append(threshold)
            self.angle.append(angle)
        self.data['data']['threshold'] = self.threshold
        self.data['data']['angle'] = self.angle

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

    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        for read_index in [0]:

            i_g = data["data"]["i_g" + str(read_index)]
            q_g = data["data"]["q_g" + str(read_index)]
            i_e = data["data"]["i_e" + str(read_index)]
            q_e = data["data"]["q_e" + str(read_index)]

            #### plotting is handled by the helper histogram
            title = 'Read Length: ' + str(self.cfg["readout_length"]) + "us" + ", Read: " + str(read_index)
            fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=True, ran=None, title = title)

            plt.suptitle(self.titlename + " , Read: " + str(read_index))


            self.fid = fid
            self.threshold = threshold
            self.angle = angle

            plt.savefig(self.iname)

            if plotDisp:
                plt.show(block=True)
                plt.pause(0.1)
        # else:
            # fig.clf(True)
            # plt.close(fig)

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