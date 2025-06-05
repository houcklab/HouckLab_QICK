"""
======
mT2.py
======

Perform a T2 Ramsey experiment
"""

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit


class LoopbackProgramT2Experiment(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Set the experiment parameters
        cfg["f_res"] = self.cfg["read_pulse_freq"]
        cfg["f_ge"] = self.cfg["qubit_freq"]
        cfg["res_gain"] = self.cfg["read_pulse_gain"]

        # T2 Parameters
        self.q_rp = self.ch_page(cfg["qubit_ch"])                               # get register page for qubit_ch
        self.r_wait = self.us2cycles(0.010)                                     # wait time between two π/2 pulses
        self.r_phase2 = 4                                                       # phase of the pi/2 pulse
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")                # Register to the phase
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))        # set the wait time between 2 π/2 pulses
        self.regwi(self.q_rp, self.r_phase2, 0)                                 # set the phase of the second π/2 pulse

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"]),
                                 freq=cfg["f_res"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["f_res"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(self.cfg["sigma"]),
                       length=self.us2cycles(self.cfg["sigma"]) * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge, phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=self.cfg["pi2_qubit_gain"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=f_res, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

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
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"]))  # update the time between two π/2 pulses
        # self.mathi(self.q_rp, self.r_phase2, self.r_phase2, '+', self.cfg["phase_step"])  # advance the phase of t
# ====================================================== #

class T2Experiment(ExperimentClass):
    """
    Basic T2 Ramsey experiment
    """

    config_template = {
        "read_pulse_style": "const",
        "read_length": 10,  ### in us
        "read_pulse_gain": 12000,  # 12000,           ### [DAC units]
        "read_pulse_freq": 891.5,  ### [MHz] actual frequency is this number + "cavity_LO"

        ##### spec parameters for finding the qubit frequency
        "qubit_freq": 265.56  ,
        "pi_qubit_gain": 856,
        "pi2_qubit_gain": 428,
        "sigma": 0.2,                   ### units us, define a 20ns sigma
        "qubit_pulse_style": "arb",     ### arb means gaussain here
        "relax_delay": 2000,            ### turned into us inside the run function

        ##### T2 ramsey parameters
        "start": 0.010,                 ### us
        "step": 15,                      ### us
        "expts": 51,                    ### number of experiemnts
        "reps": 250,                   ### number of averages on each experiment

    }

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        start_time = time.time()

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramT2Experiment(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)
        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.arctan2(avgq[0][0], avgi[0][0])

        data = {'config': self.cfg, 'data': {'times': x_pts, 'avgi': avgi, 'avgq': avgq, 'mag': mag, 'phase': phase}}

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.angle(avgi[0][0] + 1j * avgq[0][0], deg = True)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(times, phase, 'o-', label="phase")
        axs[0].set_ylabel("degree.")
        axs[0].set_xlabel("Time (us)")
        axs[0].legend()

        ax1 = axs[1].plot(times, mag, 'o-', label="magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Time (us)")
        axs[1].legend()

        ax2 = axs[2].plot(times, np.abs(avgi[0][0]), 'o-', label="I - Data")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Time (us)")
        axs[2].legend()

        ax3 = axs[3].plot(times, np.abs(avgq[0][0]), 'o-', label="Q - Data")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Time (us)")
        axs[3].legend()

        fig.suptitle('T2 Experiment')
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
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