from qick import *
from q4diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q4diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import q4diamond.Client_modules.Helpers.FF_utils as FF
from q4diamond.Client_modules.Helpers.rotate_SS_data import *


class WalkProgramSS(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # Qubit
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        self.freq_01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=self.cfg["qubit_ch"])
        self.freq_12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=self.cfg["qubit_ch"])

        # Readout: resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        FF.FFDefinitions(self)

        self.sync_all(200)


    def body(self):
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses(self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_01, phase=0,
                             gain=self.cfg["qubit_gain01"],
                             waveform="qubit", t=self.us2cycles(1))
        self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_12, phase=0,
                             gain=self.cfg["qubit_gain12"],
                             waveform="qubit")
        self.FFPulses_direct(self.FFExpts, self.cfg["variable_wait"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
        self.sync_all(dac_t0=self.dac_t0)

        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        IQ_Array_Negative = np.array([-1 * array if type(array) != type(None) else None for array in self.cfg["IDataArray"]], dtype = object)
        self.FFPulses_direct(-1 * self.FFPulse, self.cfg["variable_wait"], -1 * self.FFPulse, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')
        self.FFPulses(-1 * self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_hires(self, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
        FF.FFPulses_hires(self, list_of_gains, length_us, t_start = t_start, IQPulseArray=IQPulseArray,
                          waveform_label = waveform_label )

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)
    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)

        return shots_i0, shots_q0


# class WalkFFProg(AveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
#         for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
#                                  freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
#
#         f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
#         f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
#
#         FF.FFDefinitions(self)
#
#         self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
#         self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
#         self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
#
#         self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
#                                  phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
#                                  waveform="qubit")
#
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                  gain=cfg["pulse_gain"],
#                                  length=self.us2cycles(cfg["length"]))
#
#         self.sync_all(self.us2cycles(0.1))
#     def body(self):
#         self.sync_all(self.us2cycles(0.05), dac_t0=self.dac_t0)  # align channels and wait 50ns
#         self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 1)
#         self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))  # play probe pulse
#         # if self.cfg["variable_wait"] > 0.01:
#         # self.FFPulses_hires(self.FFExpts, self.cfg["variable_wait"])
#
#         self.FFPulses_direct(self.FFExpts, self.cfg["variable_wait"], previous_gains=self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
#     # self.sync_all()
#         self.sync_all(dac_t0=self.dac_t0)
#
#         # self.FFPulses(1.4 * self.FFReadouts, 0.005)
#         self.FFPulses(self.FFReadouts, self.cfg["length"])
#
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0, 1],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(10))
#         # self.FFPulses_hires(-1 * self.FFExpts, self.cfg["variable_wait"], waveform_label="FF2")
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
#         self.FFPulses_direct(-1 * self.FFExpts, self.cfg["variable_wait"], previous_gains = -1 * self.FFPulse,
#                              IQPulseArray= self.cfg["IDataArray"], waveform_label="FF2")
#         #
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["sigma"] * 4 + 0.503)
#
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)
#
#     def bodyprevious(self):
#         self.sync_all(self.us2cycles(0.05), dac_t0=self.dac_t0)  # align channels and wait 50ns
#         self.FFPulses(self.FFReadouts, self.cfg["sigma"] * 4 + 0.503)
#         self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.5))  # play probe pulse'
#
#         self.FFPulses_direct(self.FFExpts, self.cfg["variable_wait"], IQPulseArray= self.cfg["IDataArray"])
#
#         self.sync_all(dac_t0=self.dac_t0)
#
#         self.FFPulses(2 * self.FFReadouts, 0.008)
#         self.FFPulses(self.FFReadouts, self.cfg["length"])
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0, 1],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(10))
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
#         self.FFPulses_direct(-1 * self.FFExpts, self.cfg["variable_wait"], IQPulseArray= self.cfg["IDataArray"],
#                              waveform_label="FF2")
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["sigma"] * 4 + 0.503)
#
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)
#
#     def FFPulses(self, list_of_gains, length_us, t_start='auto'):
#         FF.FFPulses(self, list_of_gains, length_us, t_start)
#
#     def FFPulses_hires(self, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
#         FF.FFPulses_hires(self, list_of_gains, length_us, t_start = t_start, IQPulseArray=IQPulseArray,
#                           waveform_label = waveform_label )
#
#     def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
#                         waveform_label = "FF"):
#         FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
#                            IQPulseArray=IQPulseArray, waveform_label = waveform_label)

class WalkFFSS(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 ):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)


    def acquire(self, threshold = None, angle = None, progress=False, debug=False):
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        if np.array(self.cfg["IDataArray"]).any() != None:
            self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '1']['Gain_Pulse'], 1)
            self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '2']['Gain_Pulse'], 2)
            self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '3']['Gain_Pulse'], 3)
            self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '4']['Gain_Pulse'], 4)
        results = []
        rotated_iq_array = []
        start = time.time()
        for t in tqdm(tpts, position=0, disable=True):
            self.cfg["variable_wait"] = t
            prog = WalkProgramSS(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc,
                                              load_pulses=True)
            rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
            rotated_iq_array.append(rotated_iq)
            excited_percentage = count_percentage(rotated_iq, threshold=threshold)
            results.append(excited_percentage)

        print(f'Time: {time.time() - start}')
        results = np.transpose(results)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': results, 'RotatedIQ': rotated_iq_array, 'threshold':threshold,
                        'angle': angle, 'wait_times': tpts,
                     }
        }

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['wait_times']
        expectation_values = data['data']['Exp_values']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, expectation_values, 'o-', color = 'blue')
        plt.ylabel("Qubit Population")
        plt.xlabel("Wait time (2.32/16 ns )")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

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
# Pulse_Q1 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q1_awg_V1.p', 'rb'))
# Pulse_Q2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
# Pulse_Q4 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q4_awg_V1.p', 'rb'))
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected.p', 'rb'))
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_corrected_V3.p', 'rb'))
# Qubit2_parameters_long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected_LongTime_3.p', 'rb'))

# Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_PreFinal.p', 'rb'))
# Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
# Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_PreFinal.p', 'rb'))

Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))

v_awg_Q1 = Compensated_AWG(600 * 16 * 3, Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(600 * 16 * 3, Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(600 * 16 * 3, Qubit4_)[1]

print(v_awg_Q1[:20])

Compensated_pulse_list = [v_awg_Q1, v_awg_Q2, v_awg_Q2, v_awg_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)