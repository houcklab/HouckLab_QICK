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


# ====================================================== #
class DelayVsPopulationProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        # self.cfg["IDataArray"] = [None, None, None, None]
        #### first do nothing, then apply the pi pulse
        cfg = self.cfg
        cfg["reps"] = cfg["shots"]
        self.cfg["rounds"] = 1
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch

        # Qubit configuration
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
        # print(cfg["mixer_freq"], cfg["pulse_freqs"])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)

        FF.FFDefinitions(self)

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
        # self.FFPulses_direct(self.FFPulse, (self.pulse_qubit_lenth + self.us2cycles(1) + 4) * 16,
        #                      np.array([0, 0, 0, 0]), IQPulseArray= self.cfg["IDataArray"])
        # print(self.cfg["qubit_gains"], self.cfg["f_ges"])
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
        if self.cfg["delay_timesteps"] > 0:
            self.FFPulses_direct(self.FFPulse, int(self.cfg["delay_timesteps"]), self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
        self.sync_all(gen_t0=self.gen_t0)

        # self.FFPulses(self.FFReadouts * 1.5, 0.03)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1)
        # IQ_Array_Negative = np.array([-1 * array if type(array) != type(None) else None for array in self.cfg["IDataArray"]], dtype = object)
        # self.FFPulses_direct(-1 * self.FFPulse, (self.pulse_qubit_lenth + self.us2cycles(1) + 4) * 16,
        #                      np.array([0, 0, 0, 0]), IQPulseArray = IQ_Array_Negative, waveform_label='FF2')
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


class DelayVsPopulation(ExperimentClass):
    """
    Delay vs Population on an adiabatic ramp experiment
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.data = {'config': self.cfg, 'data': {}}

    def acquire(self, progress=False):
        """
        From config dictionary expect:
            'ramp_duration' : int, ramp duration in timesteps (0.145 ns)
            'delay_timesteps': int, total delay in timesteps (0.145 ns)
            'threshold', 'angle', 'confusion_matrix': list, with length = self.cfg['Read_Indeces']
        """

        # Generate FF
        for j in range(4):
            # FF ramp to put initial qubits onto resonance
            init_gain = self.cfg['FF_Qubits'][str(j + 1)]['Gain_Pulse']
            final_gain = self.cfg['FF_Qubits'][str(j + 1)]['Gain_Ramp']
            # init_gain = 0 # temporary
            self.cfg['IDataArray'][j] = generate_ramp(init_gain,
                                 final_gain,
                                 self.cfg['ramp_duration'], ramp_shape=self.cfg['ramp_shape'])
            if len(self.cfg['IDataArray'][j]) == 0:
                self.cfg['IDataArray'][j] = np.full(self.cfg['ramp_duration'], init_gain)

            # Set total waveform length to delay_timesteps
            # For this experiment, want to measure the population at points both before and after ramp
            if self.cfg['delay_timesteps'] == 0:
                pass
            elif self.cfg['ramp_duration'] >= self.cfg['delay_timesteps']:
                self.cfg['IDataArray'][j] = self.cfg['IDataArray'][j][:int(self.cfg['delay_timesteps'])] # truncate
            else:
                self.cfg['IDataArray'][j] = np.append(self.cfg['IDataArray'][j], np.full(self.cfg['delay_timesteps']-self.cfg['ramp_duration'], final_gain))
                # if waveform memory becomes a problem, rewrite this to use another delay instead

        # Acquire SS data
        self.cfg["Pulse"] = True
        prog = DelayVsPopulationProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)


        # Convert to population
        data = {'config': self.cfg, 'data': {}}
        excited_pop = np.zeros(len(self.cfg['Read_Indeces']))

        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            i_e = shots_ie[i][0]
            q_e = shots_qe[i][0]

            e_data = rotate_data((i_e, q_e), self.cfg['angle'][i])[0]

            e_pop_uncorrected = np.sum(e_data > self.cfg['threshold'][i]) / len(e_data)
            excited_pop[i] = correct_occ(e_pop_uncorrected, self.cfg['confusion_matrix'][i])[0]


        data['data']['excited_pop'] = excited_pop
        data['data']['shots_ie'] = shots_ie
        data['data']['shots_qe'] = shots_qe

        self.data = data

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        # One time point: plot bar graph
        bars = plt.bar(self.cfg['Read_Indeces'], data['data']['excited_pop'],
                       color=plt.rcParams['axes.prop_cycle'].by_key()['color'])
        for bar in bars:
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                     f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=12)
        plt.xticks(self.cfg['Read_Indeces'])
        plt.xlabel("Qubit Read")
        plt.ylabel("Occupation")

        plt.suptitle(self.titlename)

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

class SweepDelayVsPopulation(ExperimentClass):
    """
    Delay vs Population on an adiabatic ramp experiment
    From config dictionary expect:
        'ramp_duration' : int, ramp duration in timesteps (0.145 ns)
        'delay_start', 'delay_stop' : int, delay start and stop time in timesteps (0.145 ns)
        'delay_steps' : int, number of delay steps
        'threshold', 'angle', 'confusion_matrix': list, with length = self.cfg['Read_Indeces']

    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.data = {'config': self.cfg, 'data': {}}

    def acquire(self, progress=False):
        delay_vec = np.linspace(self.cfg['delay_start'], self.cfg['delay_stop'], self.cfg['delay_steps'], dtype=int)
        excited_pop_matrix = np.zeros((len(self.cfg['Read_Indeces']), self.cfg['delay_steps']))

        for j, delay in enumerate(delay_vec):
            print(f'Delay = {delay} -> {delay*0.145} ns')
            self.cfg['delay_timesteps'] = delay
            prog = DelayVsPopulation(cfg=self.cfg,
                                       soc=self.soc, soccfg=self.soccfg)
            data = prog.acquire(self.soc)
            excited_pop_matrix[:,j] = data['data']['excited_pop']

        self.data['data']['excited_pop_matrix'] = excited_pop_matrix
        self.data['data']['delay_vec'] = delay_vec
        self.data['data']['ramp_duration'] = self.cfg['ramp_duration']

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        if data['data']['excited_pop_matrix'].shape[1] == 1:
            bars = plt.bar(self.cfg['Read_Indeces'], data['data']['excited_pop_matrix'][:,0],
                           color=plt.rcParams['axes.prop_cycle'].by_key()['color'])
            for bar in bars:
                plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                         f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=12)
            plt.xticks(self.cfg['Read_Indeces'])
            plt.xlabel("Qubit Read")
            plt.ylabel("Occupation")
        else:
            for j, read in enumerate(self.cfg['Read_Indeces']):
                plt.plot(data['data']['delay_vec'], data['data']['excited_pop_matrix'][j,:], marker='o', label=f"Read: {read}")
            plt.axvline(data['data']['ramp_duration'], label='Ramp duration', ls='--', color='black')
            plt.legend()
            plt.xlabel("Delay (timesteps)")
            plt.ylabel("Occupation")


        plt.suptitle(self.titlename)

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