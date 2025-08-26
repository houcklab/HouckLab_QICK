"""
Created on Mar 20, 2020
Basic T1 experiment that looks at the decaying signal
"""

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit


class LoopbackProgramT1Experiment(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):

        # Set the start, step
        cfg = self.cfg
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_wait = self.us2cycles(0.010)
        self.regwi(self.q_rp, self.r_wait, self.cfg["start"])

        # Create readout channel
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["ro_chs"][0]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Create readout tone
        read_freq = self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"], ro_ch=self.cfg["ro_chs"][0])
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        # Create qubit tone
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])  # Qubit
        qubit_freq = self.freq2reg(self.cfg["qubit_freq"], gen_ch=self.cfg["qubit_ch"])
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4
        elif self.cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0,
                                     gain=self.cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]),
                                     )
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"])
        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=0, gain=self.cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = (self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4
                                      + self.us2cycles(self.cfg["flat_top_length"], gen_ch=self.cfg["qubit_ch"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=self.cfg["qubit_ch"]) + self.qubit_pulseLength
        self.sync_all(0.05)

    def body(self):
        self.sync_all(0.05)

        # Trigger Switch
        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])

        # Play Pulse
        self.pulse(ch=self.cfg["qubit_ch"])

        # Sync and wait for both to finish
        self.sync_all(self.us2cycles(0.05))

        # Wait
        self.sync(self.q_rp, self.r_wait)

        # Measure
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        # Update wait time
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"]))


# ====================================================== #

class T1Experiment(ExperimentClass):
    """
    Basic T1 experiment
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramT1Experiment(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False,)
        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.arctan2(avgq[0][0], avgi[0][0])

        data = {'config': self.cfg, 'data': {'times': x_pts, 'avgi': avgi, 'avgq': avgq, 'mag': mag, 'phase': phase}}

        #### perform fit for T1 estimate

        #### define T1 function
        mag = np.sqrt(avgi[0][0] ** 2 + avgq[0][0] ** 2)  # Fit to magnitude rather than I quadrature -- Lev

        mag_fit = mag

        def _expFit(x, a, T1, c):
            return a * np.exp(-1 * x / T1) + c

        a_geuss = (np.max(mag_fit) - np.min(mag_fit)) * -1
        b_geuss = np.min(mag_fit)
        T1_geuss = np.max(x_pts) / 3
        geuss = [a_geuss, T1_geuss, b_geuss]
        self.pOpt, self.pCov = curve_fit(_expFit, x_pts, mag_fit, p0=geuss)

        self.T1_fit = _expFit(x_pts, *self.pOpt)

        self.T1_est = self.pOpt[1]
        self.T1_err = self.pCov

        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.angle(avgi[0][0] + 1j * avgq[0][0], deg=True)
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(times, phase, 'o-', label="phase")
        axs[0].set_ylabel("degree.")
        axs[0].set_xlabel("Time (us)")
        axs[0].legend()

        ax1 = axs[1].plot(times, mag, 'o-', label="magnitude")
        axs[1].plot(times, self.T1_fit, label='fit')
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Time (us)")
        axs[1].legend()

        ax2 = axs[2].plot(times, np.abs(avgi[0][0]), 'o-', label="I - Data")
        # axs[2].plot(times, self.T1_fit, label='fit')
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Time (us)")
        axs[2].legend()

        ax3 = axs[3].plot(times, np.abs(avgq[0][0]), 'o-', label="Q - Data")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Time (us)")
        axs[3].legend()

        print(self.T1_err)

        plt.suptitle("T1 Experiment, T1 = " + str(round(self.T1_est, 1)) + " us")

        plt.tight_layout()

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
