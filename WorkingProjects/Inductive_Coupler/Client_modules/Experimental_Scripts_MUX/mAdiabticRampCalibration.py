from qick import *
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.rotate_SS_data import *
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.AdiabaticRamps import generate_ramp


class AdiabaticRampCalibrationProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # Qubit
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        # self.freq_01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=self.cfg["qubit_ch"])
        # self.freq_12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=self.cfg["qubit_ch"])

        # Readout: resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        FF.FFDefinitions(self)

        self.sync_all(200)




    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            gain_ = self.cfg["qubit_gains"][i]
            freq_ = self.freq2reg(self.cfg["f_ges"][i], gen_ch=self.cfg["qubit_ch"])
            if i == 0:
                time = self.us2cycles(1)
            else:
                time = 'auto'
            # print(freq_, gain_, time)
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                 gain=gain_,
                                 waveform="qubit", t=time)


        self.FFPulses_direct(self.FFExpts, self.cfg['ramp_length'], self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        IQ_Array_Negative = [-1 * array for array in self.cfg["IDataArray"]]
        self.FFPulses_direct(-1 * self.FFPulse, 1, -1 * self.FFPulse,
                             IQPulseArray=IQ_Array_Negative,
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
                start_src="internal", progress=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress)

        return self.collect_shots()

    # def collect_shots(self):
    #     shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
    #         self.cfg['readout_length'], ro_ch=0)
    #     shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
    #         self.cfg['readout_length'], ro_ch=0)
    #
    #     return shots_i0, shots_q0

    def collect_shots(self):
        all_i = []
        all_q = []
        # print(self.di_buf)#, self.di_buf[1][:30])
        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            shots_q0=self.dq_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


class AdiabticRampCalibration(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 ):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)


    def acquire(self, threshold = None, angle = None, progress=False):

        ramp_durations = np.linspace(self.cfg["duration_start"], self.cfg["duration_end"], self.cfg["duration_num_points"])


        results = [[] for i in range(len(self.cfg["ro_chs"]))]
        rotated_iq_array = [[] for i in range(len(self.cfg["ro_chs"]))]
        start = time.time()
        for i in range(len(ramp_durations)):


            ramp_length = 0
            for j in range(4):
                init_gain = self.cfg["FF_Qubits"][str(j+1)]["Gain_Pulse"]
                # init_gain = 0 # temporary
                ramp = generate_ramp(init_gain, self.cfg['FF_Qubits'][str(j+1)]['Gain_Ramp'], ramp_durations[i], ramp_shape=self.cfg['ramp_shape'])
                # the delay after the initial ramp
                ramp_delay = np.full(self.cfg['ramp_wait_timesteps'], self.cfg['FF_Qubits'][str(j+1)]['Gain_Ramp'])
                ramp = np.concatenate([ramp, ramp_delay])
                if self.cfg['double_ramp']:
                    reverse_ramp = generate_ramp(self.cfg['FF_Qubits'][str(j+1)]['Gain_Ramp'], init_gain, ramp_durations[i], reverse=True, ramp_shape=self.cfg['ramp_shape'])

                    ramp = np.concatenate([ramp, reverse_ramp])

                self.cfg["IDataArray"][j] = ramp
                plt.plot(ramp, color=['red', 'blue', 'green', 'orange'][j], label=j if i==0 else None)

                if len(self.cfg["IDataArray"][j]) == 0:
                    self.cfg["IDataArray"][j] = np.array([0])

                # set ramp length to longest ramp duration
                if len(self.cfg['IDataArray'][j]) > ramp_length:
                    ramp_length = len(self.cfg['IDataArray'][j])

            self.cfg['ramp_length'] = ramp_length


            self.soc.reset_gens()
            prog = AdiabaticRampCalibrationProgram(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc,
                                              load_pulses=True)
            for j in range(len(self.cfg["ro_chs"])):
                rotated_iq = rotate_data((shots_i0[j], shots_q0[j]), theta=angle[j])
                rotated_iq_array[j].append(rotated_iq)

                if self.cfg['use_confusion_matrix']:
                    excited_percentage = correct_occ(count_percentage(rotated_iq, threshold=threshold[j]), self.cfg['confusion_matrix'][j])[0]
                else:
                    excited_percentage = count_percentage(rotated_iq, threshold=threshold[j])


                results[j].append(excited_percentage)

        plt.xlabel("Time (2.34/16 ns)")
        plt.ylabel("FF Gain")
        plt.legend()
        plt.title("FF Gain ramps")
        plt.show(block=False)
        print(f'Time: {time.time() - start}')
        results = [np.transpose(r) for r in results]

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': results, 'RotatedIQ': rotated_iq_array, 'threshold':threshold,
                        'angle': angle, 'ramp_durations': ramp_durations,
                     }
        }

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['ramp_durations']

        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            expectation_values = data['data']['Exp_values'][i]

            while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
                figNum += 1
            fig = plt.figure(figNum)
            plt.plot(x_pts, expectation_values, 'o-', color = 'blue')
            plt.ylabel("Qubit Population")
            plt.xlabel("Ramp Duration (2.32/16 ns )")
            # plt.legend()
            plt.title(self.titlename + ", Read: " + str(read_index))
            plt.savefig(self.iname[:-4] + "_Read_" + str(read_index) + '.png')

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

'''Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))



Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_PreFinal.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
Qubit2_[0] *= 0.75
Qubit2_[2] *= 0.75
Qubit2_[4] *= 1

v_awg_Q1 = Compensated_AWG(600 * 16 * 5, Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(600 * 16 * 5, Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(600 * 16 * 5, Qubit4_)[1]'''

v_awg_Q1 = np.ones(600 * 16 * 3)
v_awg_Q2 = np.ones(600 * 16 * 3)
v_awg_Q4 = np.ones(600 * 16 * 3)

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