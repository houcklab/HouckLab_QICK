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


class WalkFFProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        FF.FFDefinitions(self)

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                 waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.1))
    def body(self):
        self.sync_all(self.us2cycles(0.05), dac_t0=self.dac_t0)  # align channels and wait 50ns
        self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 1)
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))  # play probe pulse
        # if self.cfg["variable_wait"] > 0.01:
        # self.FFPulses_hires(self.FFExpts, self.cfg["variable_wait"])

        self.FFPulses_direct(self.FFExpts, self.cfg["variable_wait"], previous_gains=self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
    # self.sync_all()
        self.sync_all(dac_t0=self.dac_t0)

        # self.FFPulses(1.4 * self.FFReadouts, 0.005)
        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        # self.FFPulses_hires(-1 * self.FFExpts, self.cfg["variable_wait"], waveform_label="FF2")
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["variable_wait"], previous_gains = -1 * self.FFPulse,
                             IQPulseArray= self.cfg["IDataArray"], waveform_label="FF2")
        #
        self.FFPulses(-1 * self.FFReadouts, self.cfg["sigma"] * 4 + 0.503)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)

    def bodyprevious(self):
        self.sync_all(self.us2cycles(0.05), dac_t0=self.dac_t0)  # align channels and wait 50ns
        self.FFPulses(self.FFReadouts, self.cfg["sigma"] * 4 + 0.503)
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.5))  # play probe pulse'

        self.FFPulses_direct(self.FFExpts, self.cfg["variable_wait"], IQPulseArray= self.cfg["IDataArray"])

        self.sync_all(dac_t0=self.dac_t0)

        self.FFPulses(2 * self.FFReadouts, 0.008)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["variable_wait"], IQPulseArray= self.cfg["IDataArray"],
                             waveform_label="FF2")
        self.FFPulses(-1 * self.FFReadouts, self.cfg["sigma"] * 4 + 0.503)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_hires(self, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
        FF.FFPulses_hires(self, list_of_gains, length_us, t_start = t_start, IQPulseArray=IQPulseArray,
                          waveform_label = waveform_label )

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

class WalkFF(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 I_Ground = 0, I_Excited = 1, Q_Ground = 0, Q_Excited = 1):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

        self.I_Ground = I_Ground
        self.I_Excited = I_Excited
        self.Q_Ground = Q_Ground
        self.Q_Excited = Q_Excited

        self.I_Range = I_Excited - I_Ground
        self.Q_Range = Q_Excited - Q_Ground

    def acquire(self, progress=False, debug=False):
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        print(tpts)
        self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'],
                                                      self.cfg['FF_Qubits']['1']['Gain_Pulse'], Qubit_number=1)
        self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'],
                                                      self.cfg['FF_Qubits']['2']['Gain_Pulse'], Qubit_number=2)
        self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'],
                                                      self.cfg['FF_Qubits']['3']['Gain_Pulse'], Qubit_number=3)
        self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'],
                                                      self.cfg['FF_Qubits']['4']['Gain_Pulse'], Qubit_number=4)

        results = []
        start = time.time()
        for t in tqdm(tpts, position=0, disable=True):
            print(t)
            self.cfg["variable_wait"] = int(t)
            prog = WalkFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
            # time.sleep(5)
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)

        data={'config': self.cfg, 'data': {'results': results, 'tpts':tpts, 'I_Ground': self.I_Ground,
                                           'I_Excited': self.I_Excited, 'Q_Ground': self.Q_Ground,
                                           'Q_Excited': self.Q_Excited}}
        self.data=data

        #### pull the data from the amp rabi sweep
        # prog = OscillationsProgram_RAverager_Wrong(self.soccfg, self.cfg)
        #
        # x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
        #                                  readouts_per_experiment=1, save_experiments=None,
        #                                  start_src="internal", progress=False, debug=False)
        # data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        # x_pts = data['data']['x_pts']
        # avgi = data['data']['avgi'][0][0]
        # avgq = data['data']['avgq'][0][0]

        x_pts = data['data']['tpts']
        avgi = (data['data']['results'][0][0][0] - self.I_Ground) / self.I_Range
        avgq = (data['data']['results'][0][0][1] - self.Q_Ground) / self.Q_Range
        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (2.32/16 ns )")
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
        plt.xlabel("Wait time (2.32/16 ns )")
        plt.legend()
        plt.title(self.titlename)


        plt.savefig(self.iname[:-4] + 'Q_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        # fig = plt.figure(figNum+2)
        # # sig = avgi + 1j * avgq
        # # avgamp0 = np.abs(sig)
        # plt.plot(x_pts, np.abs(avgi + 1j * avgq), 'o-', label="Amplitude")
        # plt.ylabel("a.u.")
        # plt.xlabel("Wait time (us)")
        # plt.legend()
        # plt.title(self.titlename)
        #
        #
        # plt.savefig(self.iname[:-4] + 'Amp_Data.png')
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)
        # else:
        #     fig.clf(True)
        #     plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

import pickle
# Compensated_Step_Pulse = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/v_awg_V2.p', 'rb'))
Pulse_Q1 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q1_awg_V1.p', 'rb'))
Pulse_Q2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
Pulse_Q4 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q4_awg_V1.p', 'rb'))
# Pulse_Q1 -= 0.01
# Pulse_Q2 -= 0.02
# Pulse_Q4 -= 0.013
# Pulse_Q1[1000:] = 1
# Pulse_Q2[1000:] = 1
# Pulse_Q4[1000:] = 1

Pulse_Q1[0] = 1.5
Compensated_pulse_list = [Pulse_Q1, Pulse_Q2, Pulse_Q2, Pulse_Q4]
Pulse_Q1 = np.concatenate([Pulse_Q1, np.ones(16 * 1000)])
Pulse_Q2 = np.concatenate([Pulse_Q2, np.ones(16 * 1000)])
Pulse_Q4 = np.concatenate([Pulse_Q4, np.ones(16 * 1000)])
print(len(Pulse_Q1), len(Pulse_Q2), len(Pulse_Q4))
Compensated_pulse_list = [Pulse_Q1, Pulse_Q2, Pulse_Q2, Pulse_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    if not compensated:
        return(np.ones(16 * 800) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)

