from qick import *
from q4diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q4diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class T2RProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp=self.ch_page(cfg["qubit_ch"])     # get register page for qubit_ch
        self.r_wait = 3
        self.r_phase2 = 4
        self.r_phase=self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, cfg["start"])
        self.regwi(self.q_rp, self.r_phase2, 0)

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=0, gain=cfg["pi2_gain"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.regwi(self.q_rp, self.r_phase, 0)

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, "+", 0)
        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"]))  # update the time between two π/2 pulses
        self.mathi(self.q_rp, self.r_phase2, self.r_phase2, '+',
                   self.cfg["phase_step"])  # advance the phase of the LO for the second π/2 pulse


class T2R(ExperimentClass):
    """
    Basic T2R
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = T2RProgram(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        signal = (avgi + 1j * avgq) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))
        avgi = signal.real
        avgq = signal.imag

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
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
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)


        plt.savefig(self.iname[:-4] + 'Q_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
