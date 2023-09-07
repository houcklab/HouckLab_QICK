from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q3diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class PulseProbeSpectroscopyProgramFFSingleFF(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        self.declare_gen(ch=cfg["ff_ch"], nqz=cfg["ff_nqz"])
        ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])

        ff_style = self.cfg["ff_pulse_style"]

        if ff_style == 'const':
            self.set_pulse_registers(ch=cfg["ff_ch"], style=ff_style, freq=ff_freq, phase=0, gain=cfg["ff_gain"],
                                     length = self.us2cycles(cfg["length"] + cfg["qubit_length"] + cfg["ff_additional_length"]))
        else:
            print('No FF pulse style matches: currently only supports const')
        ### Finish FF

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                 length=self.us2cycles(cfg["qubit_length"]))
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.res_wait = self.us2cycles(cfg["qubit_length"] + 0.02 + 0.05)

        self.sync_all(self.us2cycles(1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        self.pulse(ch=self.cfg['ff_ch'])
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))  # play probe pulse
        # self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        self.synci(self.res_wait)

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.cfg["adc_trig_offset"],
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index

class PulseProbeSpectroscopyProgramFFMultipleFF(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux


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
        self.FFReadouts = [self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout]
        self.FFExpts = [self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp]


        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                 length=self.us2cycles(cfg["qubit_length"]))
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.res_wait = self.us2cycles(cfg["qubit_length"] + 0.02 + 0.05)

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        for i, gain in enumerate(self.FFExpts):
            print(self.FFChannels[i], gain)
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=self.us2cycles(self.cfg["qubit_length"]) + self.us2cycles(0.1))
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)


        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.1))  # play probe pulse
        # self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        # self.synci(self.res_wait)
        self.sync_all()
        # trigger measurement, play measurement pulse, wait for qubit to relax
        for i, gain in enumerate(self.FFReadouts):
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=self.us2cycles(self.cfg["length"]))

        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class SpecSliceFF(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        prog = PulseProbeSpectroscopyProgramFFMultipleFF(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
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

        # plt.plot(x_pts, results[0][0][0],label="I value; ADC 0")
        # plt.plot(x_pts, results[0][0][1],label="Q value; ADC 0")

        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color = 'Orange', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title(self.titlename)
        plt.legend()

        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)

        plt.figure(figNum)
        plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title(self.titlename)

        plt.savefig(self.iname[:-4] + '_Amplitude.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


