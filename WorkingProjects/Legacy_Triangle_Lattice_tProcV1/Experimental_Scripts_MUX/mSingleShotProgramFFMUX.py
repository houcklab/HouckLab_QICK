from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experiment import ExperimentClass
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time
import WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.FF_utils as FF

# ====================================================== #
class SingleShotProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],
                                 length=self.us2cycles(cfg["readout_length"] + cfg["adc_trig_offset"] + 1, gen_ch=self.cfg["res_ch"]))

        FF.FFDefinitions(self)

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)

        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, self.cfg['number_of_pulses'] * len(self.cfg["qubit_gains"]) * self.cfg['sigma'] * 4 + FF_Delay_time)
        if self.cfg["Pulse"]:
            for i in range(len(self.cfg["qubit_gains"])):
                gain_ = self.cfg["qubit_gains"][i]
                freq_ = self.freq2reg(self.cfg["qubit_freqs"][i], gen_ch=self.cfg["qubit_ch"])

                for pulse_num in range(self.cfg["number_of_pulses"]):
                    if i == 0 and pulse_num == 0:
                        time = self.us2cycles(FF_Delay_time)
                    else:
                        time = 'auto'
                    self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                     gain=gain_,
                                     waveform="qubit", t=time)

        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False):
        start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        end = time.time()

        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []

        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
            shots_q0=self.dq_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


class SingleShotFFMUX(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.threshold = []
        self.angle = []
        self.ne_contrast = []
        self.ng_contrast = []

    def acquire(self, progress=False):
        self.cfg["reps"] = self.cfg["Shots"]
        self.cfg["rounds"] = 1
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1

        #### pull the data from the single shots
        self.cfg["IDataArray"] = [None, None, None, None]
        self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Pulse'], 0, 1)
        self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Pulse'], 0, 2)
        self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Pulse'], 0, 3)
        self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Pulse'], 0, 4)

        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

        data = {'config': self.cfg, 'data': {}}
                # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}
        self.data = data
        self.fid = []
        for i, read_index in enumerate(self.cfg["Qubit_Readout_List"]):
            i_g = shots_ig[i][0]
            q_g = shots_qg[i][0]
            i_e = shots_ie[i][0]
            q_e = shots_qe[i][0]
            self.data['data']['i_g' + str(read_index)] = i_g
            self.data['data']['q_g' + str(read_index)] = q_g
            self.data['data']['i_e' + str(read_index)] = i_e
            self.data['data']['q_e' + str(read_index)] = q_e

            fid, threshold, angle, ne_contrast, ng_contrast = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, return_errors=True) ### arbitrary ran, change later
            self.data_in_hist = [i_g, q_g, i_e, q_e]
            self.fid.append(fid)
            self.threshold.append(threshold)
            self.angle.append(angle)
            self.ne_contrast.append(ne_contrast)
            self.ng_contrast.append(ng_contrast)


        self.data['data']['threshold'] = self.threshold
        self.data['data']['angle'] = self.angle
        self.data['data']['ne_contrast'] = self.ne_contrast
        self.data['data']['ng_contrast'] = self.ng_contrast
        self.data['data']['fid'] = self.fid

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, display_indices=None, block=True, **kwargs):
        if data is None:
            data = self.data
        if display_indices is None:
            display_indices = self.cfg["Qubit_Readout_List"]

        for read_index in display_indices:

            i_g = data["data"]["i_g" + str(read_index)]
            q_g = data["data"]["q_g" + str(read_index)]
            i_e = data["data"]["i_e" + str(read_index)]
            q_e = data["data"]["q_e" + str(read_index)]

            #### plotting is handled by the helper histogram
            title = 'Read Length: ' + str(self.cfg["readout_length"]) + "us" + ", Read: " + str(read_index)
            hist_process(data=[i_g, q_g, i_e, q_e], plot=True, print_fidelities=False, ran=None, title = title)

            plt.suptitle(self.titlename + " , Read: " + str(read_index))

            plt.savefig(self.iname)

            if plotDisp:
                plt.show(block=block)
                plt.pause(0.1)
        # else:
        #     plt.clf()
        #     plt.close()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])







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
    # print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)