from qick import *

from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.AdiabaticRamps import generate_ramp
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


class AdiabaticRampOscillationsProgram(AveragerProgram):
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
        # Do adiabatic ramp
        self.FFPulses_direct(self.FFPulse, self.cfg["ramp_duration"] + self.cfg["variable_wait"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(2*self.FFReadouts, 2.32515/1e3*3)
        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        IQ_Array_Negative = [-1 * np.array(array) if type(array) != type(None) else None for array in self.cfg["IDataArray"]]
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
                start_src="internal", progress=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress)

        return self.collect_shots()

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


class AdiabaticRampOscillations(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)


    def acquire(self, threshold = None, angle = None, progress=False):
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])

        for j in range(4):
            # FF ramp to put initial qubits onto resonance
            ramp = generate_ramp(self.cfg['FF_Qubits'][str(j+1)]['Gain_Pulse'],
                                                      self.cfg['FF_Qubits'][str(j + 1)]['Gain_Ramp'],
                                                      self.cfg['ramp_duration'], ramp_shape=self.cfg['ramp_shape'])
            if len(ramp) == 0:
                ramp = np.zeros(self.cfg['ramp_duration'])

            # FF jump during expt, to initiate swaps
            FF_jump = Compensated_Pulse(self.cfg['FF_Qubits'][str(j+1)]['Gain_Expt'], self.cfg['FF_Qubits'][str(j+1)]['Gain_Ramp'])
            self.cfg['IDataArray'][j] = np.concatenate([ramp, FF_jump])
            # plt.plot(self.cfg['IDataArray'][j][:self.cfg["ramp_duration"]])

        results = [[] for i in range(len(self.cfg["ro_chs"]))]
        rotated_iq_array = [[] for i in range(len(self.cfg["ro_chs"]))]
        start = time.time()
        for t in tqdm(tpts, position=0, disable=True):
            self.cfg["variable_wait"] = t
            self.soc.reset_gens()
            prog = AdiabaticRampOscillationsProgram(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc,
                                              load_pulses=True)
            for i in range(len(self.cfg["ro_chs"])):
                rotated_iq = rotate_data((shots_i0[i], shots_q0[i]), theta=angle[i])
                rotated_iq_array[i].append(rotated_iq)
                excited_percentage = count_percentage(rotated_iq, threshold=threshold[i])
                results[i].append(excited_percentage)

        print(f'Time: {time.time() - start}')
        results = [np.transpose(r) for r in results]

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

        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            expectation_values = data['data']['Exp_values'][i]

            while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
                figNum += 1
            fig = plt.figure(figNum)
            plt.plot(x_pts, expectation_values, 'o-', color = 'blue')
            plt.ylabel("Qubit Population")
            plt.xlabel("Wait time (2.32/16 ns )")
            plt.legend()
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


class Oscillations_Gain_SSMUX(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 I_Ground = 0, I_Excited = 1, Q_Ground = 0, Q_Excited = 1):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, progress=False, figNum = 1, plotDisp = True,
                plotSave = True):

        gainVec = np.array([int(x) for x in np.linspace(self.cfg["gainStart"],self.cfg["gainStop"], self.cfg["gainNumPoints"])])
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        self.wait_times = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        Z_values = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        # self.I_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        # self.Q_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        self.rotatedIQ = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': [Z_values for i in range(len(self.cfg["ro_chs"]))], 'RotatedIQ': self.rotatedIQ, 'threshold':threshold,
                        'angle': angle, 'wait_times': self.wait_times,
                        'gainVec': gainVec,
                     }
        }

        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])

        X = tpts
        X_step = X[1] - X[0]
        Y = gainVec
        Y_step = Y[1] - Y[0]

        startTime = datetime.datetime.now()
        start = time.time()
        for i in range(self.cfg["gainNumPoints"]):
            if i % 5 == 1:
                self.save_data(self.data)
                # self.soc.reset_gens()
            self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Expt'] = int(gainVec[i])

            # create FF IDaraArray
            for j in range(4):
                # FF ramp to put initial qubits onto resonance
                ramp = generate_ramp(self.cfg['FF_Qubits'][str(j + 1)]['Gain_Pulse'],
                                     self.cfg['FF_Qubits'][str(j + 1)]['Gain_Expt'],
                                     self.cfg['ramp_duration'], ramp_shape=self.cfg['ramp_shape'])
                if len(ramp) == 0:
                    ramp = np.zeros(self.cfg['ramp_duration'])

                # FF jump during expt, to initiate swaps
                FF_jump = Compensated_Pulse(self.cfg['FF_Qubits'][str(j + 1)]['Gain_Expt'],
                                            self.cfg['FF_Qubits'][str(j + 1)]['Gain_Ramp'])
                self.cfg['IDataArray'][j] = np.concatenate(ramp, FF_jump)

            for j in range(len(self.cfg["ro_chs"])):
                results = []
                rotated_iq_array = []
                start = time.time()
                for t in tqdm(tpts, position=0, disable=True):
                    self.cfg["variable_wait"] = t
                    # print('wait time: ', t)
                    prog = AdiabaticRampOscillationProgram(self.soccfg, self.cfg)
                    shots_i0, shots_q0 = prog.acquire(self.soc,
                                                      load_pulses=True)
                    rotated_iq = rotate_data((shots_i0[j], shots_q0[j]), theta=angle[j])
                    rotated_iq_array.append(rotated_iq)
                    excited_percentage = count_percentage(rotated_iq, threshold = threshold[j])
                    results.append(excited_percentage)
                print(f'Time: {time.time() - start}')

                self.data['data']["Exp_values"][j][i, :] = np.array(results)

                # results = np.transpose(results)
                # self.data['data']["RotatedIQ"][i, :] = np.array(rotated_iq_array)
                if j == 0:
                    Z_values[i, :] = np.array(results)

            if i == 0:
                ax_plot_1 = axs.imshow(
                    Z_values,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('Excited Population', rotation=90)
            else:
                ax_plot_1.set_data(Z_values)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('Excited Population', rotation=90)

            axs.set_ylabel("FF Gain (a.u.)")
            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_title("Oscillations")


            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + 5 * 2### time for single full row in seconds
                timeEst = (t_delta )*self.cfg["gainNumPoints"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))



        print(f'Time: {time.time() - start}')


        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['wait_times']
        percent_excited = data['data']['Exp_values']
        gainVec = data['data']['gainVec']

        X = x_pts
        Y = gainVec

        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]

        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
                figNum += 1

            fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
            fig.suptitle(str(self.titlename), fontsize=16)
            ax_plot_1 = axs.imshow(
                percent_excited[i],
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
            cbar1.set_label('Excited Population', rotation=90)

            axs.set_ylabel("FF Gain (a.u.)")
            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_title("Oscillations")
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

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 2):
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
Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_PreFinal.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_PreFinal.p', 'rb'))
# Qubit1_[0] *= 1.
# Qubit1_[2] *= 1.
# Qubit1_[4] *= 1.2
#
# # print(Qubit4_)
# Qubit4_[0] *= 1.6
# Qubit4_[2] *= 1.6
# Qubit4_[4] *= 1.7

# print(Qubit4_)

Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_PreFinal.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
Qubit2_[0] *= 0.75
Qubit2_[2] *= 0.75
Qubit2_[4] *= 1

Qubit2_[0] *= 1.3
Qubit2_[1] *= 1.2
Qubit2_[2] *= 1.2
Qubit2_[3] *= 1.2

Qubit4_[0] *= 1.3
Qubit4_[1] *= 1.2
Qubit4_[2] *= 1.2
Qubit4_[3] *= 1.2
# Qubit4_[0] *= 1.2



v_awg_Q1 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit4_)[1]



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