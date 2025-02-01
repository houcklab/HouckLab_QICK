from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time


class QubitSpecSliceFFProg(RAveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in self.cfg['ro_chs']:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["length"], ro_ch = self.cfg["res_ch"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])


        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            if 'qb_periodic' in self.cfg.keys():
                if self.cfg['qb_periodic']:
                    print("Qubit tone is periodic")
                    self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                             length=self.us2cycles(cfg["qubit_length"]), mode='periodic')
                    self.qubit_length_us = cfg["qubit_length"]
                else:
                    self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                             gain=cfg["qubit_gain"],
                                             length=self.us2cycles(cfg["qubit_length"]))
                    self.qubit_length_us = cfg["qubit_length"]
            else:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                         gain=cfg["qubit_gain"],
                                         length=self.us2cycles(cfg["qubit_length"]))
                self.qubit_length_us = cfg["qubit_length"]

        if 'ro_periodic' in self.cfg.keys():
            if self.cfg['ro_periodic']:
                print("Readout periodic")
                self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=0,
                                         gain=cfg["pulse_gain"],
                                         length=self.us2cycles(cfg["length"], gen_ch=cfg["res_ch"]) , mode='periodic')
            else:
                self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                         gain=cfg["pulse_gain"],
                                         length=self.us2cycles(cfg["length"]))  # , mode='periodic')
        else:
            self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                     gain=cfg["pulse_gain"],
                                     length=self.us2cycles(cfg["length"]))#, mode='periodic')
        self.sync_all(self.us2cycles(1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        # self.pulse(ch=self.cfg["res_ch"])
        # self.sync_all(self.us2cycles(0.01))
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(self.us2cycles(0.05))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))



    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class QubitSpecSliceFF(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        signal = (avgi + 1j * avgq) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))
        avgi = signal.real
        avgq = signal.imag

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        peak_loc = np.argmax(avgamp0)
        self.qubitFreq = x_pts[peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        avgphase = np.unwrap(np.angle(sig))

        # Create figure and set up subplots (2x2 grid)
        plt.figure(figNum, figsize=(10, 8))

        # Plot I (Real part)
        plt.subplot(2, 2, 1)  # 2x2 grid, 1st subplot
        plt.plot(x_pts, avgi, '.-', color='Orange', label="I")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.ylabel("a.u.")
        plt.title("I Component")
        plt.legend()
        plt.grid(True)

        # Plot Q (Imaginary part)
        plt.subplot(2, 2, 2)  # 2x2 grid, 2nd subplot
        plt.plot(x_pts, avgq, '.-', color='Blue', label="Q")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.ylabel("a.u.")
        plt.title("Q Component")
        plt.legend()
        plt.grid(True)

        # Plot Amplitude
        plt.subplot(2, 2, 3)  # 2x2 grid, 3rd subplot
        plt.plot(x_pts, avgamp0, '.-', color='Green', label="Amplitude")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.ylabel("Amplitude (a.u.)")
        plt.title("Amplitude")
        plt.legend()
        plt.grid(True)

        # Plot Phase
        plt.subplot(2, 2, 4)  # 2x2 grid, 4th subplot
        plt.plot(x_pts, avgphase, '.-', color='Red', label="Phase")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.ylabel("Phase (radians)")
        plt.title("Phase")
        plt.legend()
        plt.grid(True)

        # Adjust layout to prevent overlap
        plt.tight_layout()


        plt.savefig(self.iname[:-4] + '_IQ.png')
        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        plt.close(figNum)

        # plt.figure(figNum)
        # plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        # plt.ylabel("a.u.")
        # plt.xlabel("Qubit Frequency (GHz)")
        # plt.title(self.titlename)
        #
        # plt.savefig(self.iname[:-4] + '_Amplitude.png')
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)
        # plt.close(figNum)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


