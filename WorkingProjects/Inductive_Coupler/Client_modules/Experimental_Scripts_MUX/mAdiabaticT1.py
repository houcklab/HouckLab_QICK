from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.AdiabaticRamps import generate_ramp
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.rotate_SS_data import *
from scipy.optimize import curve_fit


# ====================================================== #
class AdiabaticRampT1SSProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        cfg = self.cfg
        self.cfg["rounds"] = 1
        print(cfg["reps"])
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        # self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
        #                          length=self.us2cycles(cfg["length"], gen_ch=self.cfg["res_ch"]))
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["readout_length"] + cfg["adc_trig_offset"] + 1, gen_ch=self.cfg["res_ch"]))

        FF.FFDefinitions(self)
        self.FFRamp = np.array([self.cfg["FF_Qubits"][q]["Gain_Ramp"] for q in self.FFQubits])

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        # print(self.pulse_sigma, self.pulse_qubit_lenth)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)

        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg['sigma'] * 4 + FF_Delay_time)

        if self.cfg["Pulse"]:
            for i in range(len(self.cfg["qubit_gains"])):
                gain_ = self.cfg["qubit_gains"][i]
                freq_ = self.freq2reg(self.cfg["f_ges"][i], gen_ch=self.cfg["qubit_ch"])
                if i == 0:
                    time = self.us2cycles(FF_Delay_time)
                else:
                    time = 'auto'
                # print(freq_, gain_, time)
                for iter in range(self.cfg["number_of_pulses"]):
                    if iter > 0 and time != 'auto':
                        time = 'auto'
                    self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                     gain=gain_,
                                     waveform="qubit", t=time)

        # Do adiabatic ramp
        self.FFPulses_direct(self.FFPulse, self.cfg["ramp_duration"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
        if self.cfg["delay_length"] > 0:
            self.FFPulses(self.FFRamp, self.cfg["delay_length"])
        self.sync_all(gen_t0=self.gen_t0)

        # self.FFPulses(self.FFReadouts * 1.5, 0.03)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        if self.cfg["delay_length"] > 0:
            self.FFPulses(-1 * self.FFRamp, self.cfg["delay_length"])

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

        # print(end - start)
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


class AdiabaticRampT1SS(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.threshold = []
        self.angle = []

    def acquire(self, threshold = None, angle = None, progress=False, figNum = 1, plotDisp = True,
                plotSave = True):

        for j in range(4):
            # FF ramp to put initial qubits onto resonance
            init_gain = self.cfg['FF_Qubits'][str(j + 1)]['Gain_Pulse']
            # init_gain = 0 # temporary
            self.cfg['IDataArray'][j] = generate_ramp(init_gain,
                                 self.cfg['FF_Qubits'][str(j + 1)]['Gain_Ramp'],
                                 self.cfg['ramp_duration'], ramp_shape=self.cfg['ramp_shape'])
            if len(self.cfg['IDataArray'][j]) == 0:
                self.cfg['IDataArray'][j] = np.full(self.cfg['ramp_duration'], init_gain)

        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        self.wait_times = self.cfg["wait_times"]
        Z_values = np.full((len(self.wait_times)), np.nan)


        X = self.wait_times
        X_step = X[1] - X[0]
        Z_fid = np.full(len(X), np.nan)
        Z_overlap = np.full(len(X), np.nan)
        ####create arrays for storing the data


        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': Z_values, 'threshold':threshold,
                        'angle': angle, 'wait_time': self.wait_times,
                     }
        }

        tpts = self.wait_times

        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()
        for i_del in range(len(tpts)):
            # if i_del % 5 == 1:
            self.save_data(self.data)
                # self.soc.reset_gens()
            self.cfg['delay_length'] = tpts[i_del]
                # print
            all_percentage = []
            for r_num in range(self.cfg['repeated_nums']):
                print(self.cfg['reps'], self.cfg['shots'], self.cfg['rounds'])
                prog = AdiabaticRampT1SSProgram(self.soccfg, self.cfg)
                shots_i0, shots_q0 = prog.acquire(self.soc,
                                                  load_pulses=True)
                rotated_iq = rotate_data((shots_i0[0], shots_q0[0]), theta=angle)
                excited_percentage = count_percentage(rotated_iq, threshold = threshold)
                all_percentage.append(excited_percentage[0])

            Z_values[i_del] = np.mean(all_percentage)
            self.data['data']['Exp_values'][i_del] = np.mean(all_percentage)

            if i_del == 0:

                ax_plot_0, = axs.plot(self.wait_times,
                                      Z_values * 100, 'o-', color='black'
                                      )
                step_ = self.wait_times[1] - self.wait_times[0]
                axs.set_xlim(self.wait_times[0] - step_, self.wait_times[-1] + step_)
            else:
                ax_plot_0.set_data(self.wait_times, Z_values * 100)
                y_min, y_max = min(Z_values * 100), max(Z_values * 100)
                axs.set_ylim(0, y_max + 5)
                # axs.relim()  # Recalculate the limits based on the new data
                axs.autoscale_view()  # Autoscale the view to fit the new data
                axs.grid()

            axs.grid()
            axs.set_ylabel("Qubit Population")
            axs.set_xlabel("Delay time (us)")
            axs.set_title('')

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

        if i_del == 0:  ### during the first run create a time estimate for the data aqcuisition
            t_delta = time.time() - start  ### time for single full row in seconds
            timeEst = t_delta * len(self.wait_times)  ### estimate for full scan
            StopTime = startTime + datetime.timedelta(seconds=timeEst)
            print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
            print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
            print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print(f'Time: {time.time() - start}')
        self.save_data(self.data)
        plt.savefig(self.iname)



        if plotDisp:
            def _expFit(x, a, T1, c):
                return a * np.exp(-1 * x / T1) + c

            Z_values_only = Z_values * 100

            a_guess = Z_values_only[0] - Z_values_only[-1]
            b_guess = Z_values_only[-1]
            approx_t1_val = a_guess / 2.6 + b_guess
            index_t1_guess = np.argmin(np.abs(Z_values_only - approx_t1_val))
            t1_guess = self.wait_times[index_t1_guess]
            guess = [a_guess, t1_guess, b_guess]
            pOpt, pCov = curve_fit(_expFit,  self.wait_times, Z_values_only, p0=guess)
            perr = np.sqrt(np.diag(pCov))

            T1_fit = _expFit(self.wait_times, *pOpt)

            T1_est = pOpt[1]
            T1_err = perr[1]
            plt.plot(self.wait_times, T1_fit, '-', label="fit", color='red')
            plt.ylabel("Qubit Population")
            plt.xlabel("Wait time (us)")
            plt.title(f'T1: {T1_est:.2f} us $\pm$ {T1_err:.2f}')
            plt.savefig(self.iname)

            plt.show(block=True)

        return self.data

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
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)