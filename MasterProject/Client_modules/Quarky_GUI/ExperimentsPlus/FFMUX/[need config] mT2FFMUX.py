# Not finished

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
import datetime
from tqdm.notebook import tqdm
import time

from Pyro4 import Proxy
from qick import QickConfig

from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
import MasterProject.Client_modules.Quarky_GUI.ExperimentsPlus.FFMUX.FF_utils as FF

class T2R_FFProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],  # gain=cfg["res_gain"],
                                 length=self.us2cycles(cfg["res_length"]))

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_length)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi2_gain"],
                                 waveform="qubit")
        FF.FFDefinitions(self)

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        FFPulse_length = 7+self.cfg["sigma"]*8+self.cfg['delay']+2
        # print(FFPulse_length, "us")
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq2reg(self.cfg["f_ge"], gen_ch=self.cfg["qubit_ch"]),
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]),
                                 gain=self.cfg["pi2_gain"], waveform="qubit")

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(7))

        remaining_length = FFPulse_length
        while remaining_length > 150:
            self.FFPulses(self, self.FFPulse, 150)
            remaining_length -= 150
        self.FFPulses(self, self.FFPulse, remaining_length)

        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq2reg(self.cfg["f_ge"], gen_ch=self.cfg["qubit_ch"]),
                                 phase=self.deg2reg(self.cfg['phase_deg'], gen_ch=self.cfg["qubit_ch"]),
                                 gain=self.cfg["pi2_gain"], waveform="qubit")

        # self.synci(0, self.us2cycles(7+self.cfg['delay']))

        self.pulse(ch=self.cfg["qubit_ch"],t=self.us2cycles(self.cfg["sigma"]*4+7+self.cfg['delay']))  # play probe pulse
        self.sync_all()

        self.FFPulses(self, self.FFReadouts, self.cfg['res_length'])
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        # invert pulses
        self.FFPulses(self, -self.FFReadouts, self.cfg['res_length'])
        remaining_length = FFPulse_length
        while remaining_length > 150:
            self.FFPulses(self, -self.FFPulse, 150)
            remaining_length -= 150
        self.FFPulses(self, -self.FFPulse, remaining_length)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


class T2RFF(ExperimentClassPlus):
    """
    Basic T2R
    """

    config_template = {
        "read_pulse_style": "const",
        "read_length": 10,  ### in us
        "read_pulse_gain": 12000,  # 12000,           ### [DAC units]
        "read_pulse_freq": 891.5,  ### [MHz] actual frequency is this number + "cavity_LO"

        ##### spec parameters for finding the qubit frequency
        "qubit_freq": 265.56,
        "pi_qubit_gain": 856,
        "pi2_qubit_gain": 428,
        "sigma": 0.2,  ### units us, define a 20ns sigma
        "qubit_pulse_style": "arb",  ### arb means gaussain here
        "relax_delay": 2000,  ### turned into us inside the run function

        ##### T2 ramsey parameters
        "start": 0.010,  ### us
        "step": 15,  ### us
        "expts": 51,  ### number of experiemnts
        "reps": 20,  ### number of averages on each experiment
    }

    
    ### Hardware Requirement
    hardware_requirement = [Proxy, QickConfig]

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg = hardware

    def acquire(self, progress=False):
        print(self.cfg)
        self.cfg.setdefault('start',    0)  ### start time
        self.cfg.setdefault('f_ge',     self.cfg['qubit_freqs'][0] + self.cfg["freq_shift"])
        self.cfg.setdefault('pi_gain',  int(self.cfg['qubit_gains'][0]))
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] // 2)
        self.cfg['phase_step'] = self.soccfg.deg2reg(self.cfg["phase_step_deg"], gen_ch=self.cfg['qubit_ch'])

        delays = self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts'])

        phase_degs = self.cfg["phase_step_deg"] * np.arange(self.cfg['expts'])

        avgi = [[np.zeros(self.cfg['expts'])]]
        avgq = [[np.zeros(self.cfg['expts'])]]
        for j, (delay, phase_deg) in enumerate(zip(delays, phase_degs)):
            self.cfg['delay'] = delay
            self.cfg['phase_deg'] = phase_deg
            # print(delay, phase_deg)
            prog = T2R_FFProgram(self.soccfg, self.cfg)
            # print(prog)
            i, q = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False)
            # print(i[0].shape)
            avgi[0][0][j], avgq[0][0][j] = i[0].item(), q[0].item()

        x_pts = delays
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq, 'qfreq': self.cfg["f_ge"],
                                             'rfreq': self.cfg["mixer_freq"] + self.cfg["res_freqs"][0] + self.cfg["cavity_LO"] / 1e6}}
        print(data['data']['qfreq'])
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        while plt.fignum_exists(num=figNum):  ###account for if figure with number already exists
            figNum += 1
        fig, (ax_i, ax_q) = plt.subplots(1, 2, figsize=(12.8, 4.8), num=figNum, tight_layout=True)

        ax_i.plot(x_pts, avgi, 'o-', label="i", color='orange')
        ax_i.set_ylabel("a.u.")
        ax_i.set_xlabel("Wait time (us)")
        ax_i.legend()
        ax_q.plot(x_pts, avgq, 'o-', label="q")
        ax_q.set_ylabel("a.u.")
        ax_q.set_xlabel("Wait time (us)")
        ax_q.legend()

        plt.suptitle(self.titlename)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass