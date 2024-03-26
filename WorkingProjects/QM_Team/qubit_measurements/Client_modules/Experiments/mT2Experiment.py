#### code to perform a T2 Ramsey experiment

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit


class LoopbackProgramT2Experiment(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        cfg["f_res"] = self.cfg["read_pulse_freq"]
        cfg["f_ge"] = self.cfg["qubit_freq"]
        cfg["res_gain"] = self.cfg["read_pulse_gain"]

        self.q_rp = self.ch_page(cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_wait = self.us2cycles(0.010)
        self.r_phase2 = 4
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))
        self.regwi(self.q_rp, self.r_phase2, 0)

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"]),
                                 freq=cfg["f_res"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["f_res"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        qubit_freq = f_ge

        # add qubit and readout pulses to respective channels
        # self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
        #                sigma=self.us2cycles(self.cfg["sigma"]),
        #                length=self.us2cycles(self.cfg["sigma"]) * 4)
        # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge, phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=self.cfg["pi2_qubit_gain"],
        #                          waveform="qubit")
        #

        ### Declaration of Pulses
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))

        else:
            print("define pi or flat top pulse")

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

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        start_time = time.time()

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramT2Experiment(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.arctan2(avgq[0][0], avgi[0][0])

        data = {'config': self.cfg, 'data': {'times': x_pts, 'avgi': avgi, 'avgq': avgq, 'mag': mag, 'phase': phase}}

        ## perform fit for T1 estimate
        #mag = avgi[0][0]

        ### define T2 function
        def _expCosFit(x, offset, amp, T2, freq, phaseOffset):
            return offset + (amp * np.exp(-1 * x / T2) * np.cos(2*np.pi*freq*x + phaseOffset) )

        offset_guess = (np.max(mag) + np.min(mag))/2
        amp_guess = (np.max(mag) - np.min(mag))/2
        T2_guess = np.max(x_pts)/2
        freq_guess = np.abs(x_pts[np.argmax(mag)] - x_pts[np.argmin(mag)])*2
        phaseOffset_guess = np.pi

        offset_guess = np.min(mag)
        amp_guess = np.max(mag)
        T2_guess = 1
        freq_guess = 1
        phaseOffset_guess = 0

        guess = [offset_guess, amp_guess, T2_guess, freq_guess, phaseOffset_guess]

        self.pOpt, self.pCov = curve_fit(_expCosFit, x_pts, mag, p0=guess)
        self.perr =np.sqrt(np.diag(self.pCov))
        self.T2_fit = _expCosFit(x_pts, *self.pOpt)

        self.T2_est = self.pOpt[2]
        self.T2_err = self.perr[2]
        self.freq_est = self.pOpt[3]
        self.data = data
        print("--- %s seconds ---" % (time.time() - start_time))

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
        axs[1].plot(times, self.T2_fit, label='fit')
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

        plt.suptitle("T2 Experiment, T2 = " + str(round(self.T2_est,1)) + r" $\pm$ " + str(round(self.T2_err,1)) + "us")

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