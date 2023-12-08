#### code to perform a T1 experiment

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from STFU.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit

prog_name = ""
class LoopbackProgramT1Experiment(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        cfg["f_res"] = self.cfg["read_pulse_freq"]
        cfg["f_ge"] = self.cfg["qubit_freq"]
        cfg["res_gain"] = self.cfg["read_pulse_gain"]

        #### set the start, step, and other parameters
        self.q_rp = self.ch_page(cfg["qubit_ch"])     # get register page for qubit_ch
        self.r_wait = self.us2cycles(0.010)
        self.regwi(self.q_rp, self.r_wait, cfg["start"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], ro_ch=0),
                                 freq=cfg["f_res"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(self.cfg["sigma"]),
                       length=self.us2cycles(self.cfg["sigma"]) * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        self.sync_all(50)

    # def initialize(self):
    #     cfg = self.cfg
    #
    #     #### set the start, step, and other parameters
    #     self.cfg["start"] = self.cfg["qubit_gain_start"]
    #     self.cfg["step"] = self.cfg["qubit_gain_step"]
    #     self.cfg["expts"] = self.cfg["qubit_gain_expts"]
    #     self.cfg["reps"] = self.cfg["AmpRabi_reps"]
    #
    #     self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
    #     self.r_wait = self.us2cycles(0.010)
    #     self.regwi(self.q_rp, self.r_wait, cfg["start"])
    #     self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
    #     self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
    #     for ch in cfg["ro_chs"]:
    #         self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
    #                              freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])
    #
    #     read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
    #     qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
    #
    #     if cfg["qubit_pulse_style"] == "arb":
    #         self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
    #                        sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
    #                        length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
    #         self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
    #                                  phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
    #                                  waveform="qubit")
    #
    #     elif cfg["qubit_pulse_style"] == "flat_top":
    #         self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
    #                        sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
    #                        length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
    #         self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
    #                                  phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
    #                                  waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
    #
    #     else:
    #         print("define pi or flat top pulse")
    #
    #     self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
    #                              gain=cfg["read_pulse_gain"],
    #                              length=self.us2cycles(self.cfg["read_length"]))
    #
    #     self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def body(self):
        self.sync_all(50)

        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        self.sync_all()
        self.sync(self.q_rp,self.r_wait)

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

        # self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        # self.sync_all(self.us2cycles(0.05)) # align channels and wait 50ns
        #
        # #trigger measurement, play measurement pulse, wait for qubit to relax
        # self.measure(pulse_ch=self.cfg["res_ch"],
        #      adcs=self.cfg["ro_chs"],
        #      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
        #      wait=True,
        #      syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"])) ### update wait time


# ====================================================== #

class T1Experiment(ExperimentClass):
    """
    Basic T1 experiment
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramT1Experiment(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.arctan2(avgq[0][0], avgi[0][0])

        data = {'config': self.cfg, 'data': {'times': x_pts, 'avgi': avgi, 'avgq': avgq, 'mag': mag, 'phase': phase}}

        #### perform fit for T1 estimate

        #### define T1 function
        mag = np.sqrt(avgi[0][0] ** 2 + avgq[0][0] ** 2) # Fit to magnitude rather than I quadrature -- Lev

        mag_fit = avgi[0][0]

        def _expFit(x, a, T1, c):
            return a * np.exp(-1 * x / T1) + c

        a_geuss = (np.max(mag_fit)-np.min(mag_fit))*-1
        b_geuss = np.min(mag_fit)
        T1_geuss = np.max(x_pts)/3
        geuss = [a_geuss, T1_geuss, b_geuss]
        self.pOpt, self.pCov = curve_fit(_expFit, x_pts, mag_fit, p0=geuss)

        self.T1_fit = _expFit(x_pts, *self.pOpt)

        self.T1_est = self.pOpt[1]
        self.T1_err = self.pCov

        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.angle(avgi[0][0] + 1j * avgq[0][0], deg = True)
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(4,1, figsize = (12,12), num = figNum)

        ax0 = axs[0].plot(times, phase, 'o-', label="phase")
        axs[0].set_ylabel("degree.")
        axs[0].set_xlabel("Time (us)")
        axs[0].legend()

        ax1 = axs[1].plot(times, mag, 'o-', label="magnitude")
        # axs[1].plot(times, self.T1_fit, label='fit')
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Time (us)")
        axs[1].legend()

        ax2 = axs[2].plot(times, np.abs(avgi[0][0]) , 'o-', label="I - Data")
        axs[2].plot(times, self.T1_fit, label='fit')
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Time (us)")
        axs[2].legend()

        ax3 = axs[3].plot(times, np.abs(avgq[0][0]) , 'o-', label="Q - Data")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Time (us)")
        axs[3].legend()

        print(self.T1_err)

        plt.suptitle("T1 Experiment, T1 = " + str(round(self.T1_est,1) ) + " us")

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