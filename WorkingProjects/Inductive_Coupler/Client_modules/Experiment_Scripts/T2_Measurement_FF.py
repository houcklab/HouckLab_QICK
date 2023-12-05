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


class T2FFProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        self.f_ge = f_ge

        FF.FFDefinitions(self)

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["pi2_gain"],
                                 waveform="qubit")

        # self.sync_all(self.us2cycles(0.1))

    def body(self):
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses(self.FFRamp, 0.5) #Should be 0 anyways
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses_direct(self.FFPulse, self.cfg["variable_wait"] + 2 * int(self.pulse_qubit_lenth * 16) + 1600, self.FFRamp,
                             IQPulseArray = self.cfg["IDataArray"])
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.1))  # play probe pulse
        self.pulse(ch=self.cfg["qubit_ch"], t=self.cfg["variable_wait"] // 16 + self.us2cycles(0.1) + self.pulse_qubit_lenth)  # play probe pulse
        self.sync_all(dac_t0=self.dac_t0)
        # self.sync_all()

        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        # self.FFPulses(-1 * self.FFExpts, self.cycles2us(self.cfg["variable_wait"]))
        # self.FFPulses_hires(-1 * self.FFExpts, self.cfg["variable_wait"], IQPulseArray = self.cfg["IDataArray"],
        #                     waveform_label='FF2')
        IQ_Array_Negative = np.array([-1 * array if type(array) != type(None) else None for array in self.cfg["IDataArray"]], dtype = object)
        self.FFPulses_direct(-1 * self.FFPulse, self.cfg["variable_wait"] + 2 * int(self.pulse_qubit_lenth * 16) + 1600, -1 * self.FFRamp,
                             IQPulseArray = self.cfg["IDataArray"], waveform_label='FF2')
        #
        self.FFPulses(-1 * self.FFReadouts, self.cfg["sigma"] * 4 + 0.103) #Should be 0 anyways
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))#, dac_t0=self.dac_t0)
        # print("final", self.gen_mgrs[self.FFChannels[0]].pulses)



    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)
    def FFPulses_hires(self, list_of_gains, length_dt, t_start='auto', IQPulseArray=None, padval=0, waveform_label = 'FF'):
        FF.FFPulses_hires(self, list_of_gains, length_dt,  t_start = t_start, IQPulseArray=IQPulseArray, padval=padval,
                          waveform_label=waveform_label)
    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                       waveform_label='FF'):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains = previous_gains, t_start=t_start, IQPulseArray=IQPulseArray,
                          waveform_label=waveform_label)

class T2FF(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        print(tpts)
        results = []
        results90 = []
        data = {'config': self.cfg, 'data': {'results': results, 'tpts':tpts}}
        self.data = data
        start = time.time()
        if np.array(self.cfg["IDataArray"]).any() != None:
            self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Pulse'], self.cfg['FF_Qubits'][
                '1']['Gain_Init'], 1)
            self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Pulse'], self.cfg['FF_Qubits'][
                '2']['Gain_Init'], 2)
            self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Pulse'], self.cfg['FF_Qubits'][
                '3']['Gain_Init'], 3)
            self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Pulse'], self.cfg['FF_Qubits'][
                '4']['Gain_Init'], 4)
        for i, t in enumerate(tpts):
            if i % 10 == 2:
                self.save_data(self.data)
                print(t)
                print(t)
            self.cfg["variable_wait"] = t
            prog = T2FFProgram(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
            self.data['data']['results'] = np.transpose(results)

        print(f'Time: {time.time() - start}')
        results = np.transpose(results)


        # data = {'config': self.cfg, 'data': {'results': results, 'tpts':tpts}}
        # self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        # x_pts = data['data']['x_pts']
        # avgi = data['data']['avgi'][0][0]
        # avgq = data['data']['avgq'][0][0]

        x_pts = data['data']['tpts']
        avgi = data['data']['results'][0][0][0]
        avgq = data['data']['results'][0][0][1]

        signal = (avgi + 1j * avgq) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))
        avgi = signal.real
        avgq = signal.imag


        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (clock cycles)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + 'I_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum+1)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        plt.plot(x_pts, avgq, 'o-', label="q")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (clock cycles)")
        plt.legend()
        plt.title(self.titlename)


        plt.savefig(self.iname[:-4] + 'Q_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum+2)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        plt.plot(x_pts, np.abs(avgi + 1j * avgq), 'o-', label="Amplitude")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (clock cycles)")
        plt.legend()
        plt.title(self.titlename)


        plt.savefig(self.iname[:-4] + 'Amp_Data.png')

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


Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_PreFinal.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
Qubit2_[0] *= 0.75
Qubit2_[2] *= 0.75
Qubit2_[4] *= 1

v_awg_Q1 = Compensated_AWG(600 * 16 * 3, Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(600 * 16 * 3, Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(600 * 16 * 3, Qubit4_)[1]


Compensated_pulse_list = [v_awg_Q1, v_awg_Q2, v_awg_Q2, v_awg_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)
