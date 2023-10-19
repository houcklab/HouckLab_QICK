from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit


class LoopbackProgramQubit_ef_rabi(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters

        # Amplitude variation for a E-F Rabi
        self.cfg["start"] = self.cfg["qubit_ef_gain_start"]
        self.cfg["step"] = self.cfg["qubit_ef_gain_step"]
        # How many amplitude steps to do
        self.cfg["expts"] = self.cfg["RabiNumPoints"]

        # Number of averages at each step
        # self.cfg["reps"] = self.cfg["AmpRabi_reps"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.qreg_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.qreg_freq = self.sreg(self.cfg["qubit_ch"], "freq") # frequency register on qubit channel
        # To see list of all registers: self.pulse_registers
        # We need an additional register to use for the e-g frequency.
        # I don't know how to check the list of registers properly, so I will just use an arbitrary number that doesn't
        # match any of the ones listed above for channel 0 or 1, which are readout and qubit, resp.
        self.qreg_gain_ef = 4 # Taken from https://github.com/conniemiao/slab_rfsoc_expts/blob/d62c098f55bc4745bfb8e9ffa41d5bb49085b11e/experiments/single_qubit/pulse_probe_ef_spectroscopy.py#L99

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_ge_freq = self.freq2reg(cfg["qubit_ge_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.safe_regwi(self.q_rp, self.qreg_gain_ef, self.cfg["start"]) # Set the ef frequency register to start at the correct value

        # Define qubit pulse: gaussian
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit")
        # Define qubit pulse: flat top
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))

        # Don't know what kind of pulse we want
        else:
            print("define gaussian or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):
        ge_freq = self.freq2reg(self.cfg["qubit_ge_freq"], gen_ch=self.cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        ef_freq = self.freq2reg(self.cfg["qubit_ef_freq"], gen_ch=self.cfg["qubit_ch"])
        # Apply g-e pi pulse
        if self.cfg["apply_ge"]:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                     phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
                                     waveform="qubit")
            self.pulse(ch=self.cfg["qubit_ch"])  # play ge pi pulse

        # Apply e-f gaussian pulse with increasing amplitude
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ef_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=0,
                                 waveform="qubit")
        self.mathi(self.q_rp, self.qreg_gain, self.qreg_gain_ef, '+', 0) # Hack to set the qreg_gain register page to qreg_gain_ef (+0)
        self.pulse(ch = self.cfg['qubit_ch']) # play ef probe pulse

        # Apply g-e pi pulse to read the population of e state
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
                                 waveform="qubit")
        self.pulse(ch=self.cfg["qubit_ch"])  # play ge pi pulse

        # Syncing all pulses
        self.sync_all(self.us2cycles(0.05)) # align channels and wait /

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.qreg_gain_ef, self.qreg_gain_ef, '+', self.cfg["step"]) # update frequency of the ef spectroscopy probe




# ====================================================== #

class Qubit_ef_rabi(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramQubit_ef_rabi(self.soccfg, self.cfg)
        start = time.time()
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.remainder(np.angle(sig,deg=True)+360,360)

        # Fitting the sinusoid
        # Defining the fit function
        def fitfunc(x,a,b,c,d):
            return a*np.sin(x*b+c) + d

        # Fitting for amplitude
        poptsig, pcov = curve_fit(fitfunc, x_pts, avgsig,
                                  [np.ptp(avgsig), 1/(x_pts[np.argmax(avgsig)] -x_pts[np.argmin(avgsig)]), 1,
                                   np.average(avgsig) ])

        #region Fitting for phase, I and Q
        # poptphase, pcov = curve_fit(fitfunc, x_pts, avgphase,
        #                           [np.ptp(avgphase), 1 / (x_pts[np.argmax(avgphase)] - x_pts[np.argmin(avgphase)]), 1,
        #                            np.average(avgphase)])
        #
        # # Fitting for I
        # poptavgi, pcov = curve_fit(fitfunc, x_pts, avgi,
        #                           [np.ptp(avgi), 1 / (x_pts[np.argmax(avgi)] - x_pts[np.argmin(avgi)]), 1,
        #                            np.average(avgi)])
        #
        # # Fitting for Q
        # poptavgq, pcov = curve_fit(fitfunc, x_pts, avgq,
        #                            [np.ptp(avgq), 1 / (x_pts[np.argmax(avgq)] - x_pts[np.argmin(avgq)]), 1,
        #                             np.average(avgq)])
        #endregion , I and Q

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="Phase")
        # ax0 = axs[0].plot(x_pts, fitfunc(x_pts, *poptphase))
        axs[0].set_ylabel("Degrees")
        axs[0].set_xlabel("Amplitude (in dac units)")
        # axs[1].set_title("Pi Pulse at " + str(np.pi /  poptphase[1]))
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="Magnitude")
        ax1 = axs[1].plot(x_pts, fitfunc(x_pts,*poptsig))
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Amplitude (in dac units)")
        axs[1].set_title("Pi Pulse at " + str(np.pi/poptsig[1]))
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I")
        # ax2 = axs[2].plot(x_pts, fitfunc(x_pts,*poptavgi))
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Amplitude (in dac units)")
        # axs[1].set_title("Pi Pulse at " + str(np.pi /  poptavgi[1]))
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q")
        # ax3 = axs[2].plot(x_pts, fitfunc(x_pts, *poptavg1))
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Amplitude (in dac units)")
        # axs[1].set_title("Pi Pulse at " + str(np.pi / poptavgq[1]))
        axs[3].legend()

        fig.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(2)
            plt.close()
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


class Qubit_ef_RPM(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        ## Acquire the data when g-e pi pulse is applied
        self.cfg["apply_ge"] = True
        prog = LoopbackProgramQubit_ef_rabi(self.soccfg, self.cfg)
        g_x_pts, g_avgi, g_avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)

        ## Acquire the daya when no g-e pi pulse is applied
        self.cfg["apply_ge"] = False
        prog = LoopbackProgramQubit_ef_rabi(self.soccfg, self.cfg)
        e_x_pts, e_avgi, e_avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                               readouts_per_experiment=1, save_experiments=None,
                                               start_src="internal", progress=False, debug=False)

        data = {'config': self.cfg, 'data': {'g_x_pts': g_x_pts, 'g_avgi': g_avgi, 'g_avgq': g_avgq, 'e_x_pts': e_x_pts, 'e_avgi': e_avgi, 'e_avgq': e_avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        # Import the data for measuring the g-state population
        g_x_pts = data['data']['g_x_pts']
        g_avgi = data['data']['g_avgi']
        g_avgq = data['data']['g_avgq']
        g_sig  = g_avgi[0][0] + 1j * g_avgq[0][0]
        g_avgsig = np.abs(g_sig)
        g_avgphase = np.remainder(np.angle(g_sig,deg=True)+360,360)

        # Import the data for measuring the e-state
        e_x_pts = data['data']['e_x_pts']
        e_avgi = data['data']['e_avgi']
        e_avgq = data['data']['e_avgq']
        e_sig  = e_avgi[0][0] + 1j * e_avgq[0][0]
        e_avgsig = np.abs(e_sig)
        e_avgphase = np.remainder(np.angle(e_sig,deg=True)+360,360)

        # Fitting the sinusoid
        # Defining the fit function
        def fitfunc(x,a,b,c,d):
            return a*np.sin(x*b+c) + d

        # Fitting for amplitude for g-state
        g_poptsig, g_pcov = curve_fit(fitfunc, g_x_pts, g_avgsig,
                                  [np.ptp(g_avgsig), 1/(g_x_pts[np.argmax(g_avgsig)] -g_x_pts[np.argmin(g_avgsig)]), 1,
                                   np.average(g_avgsig) ])

        # Fitting for amplitude for e-state with bounds on the frequency (b) set by the frequency (b) found for g-state
        # This is basically like a lock-in amplifier
        e_poptsig, e_pcov = curve_fit(fitfunc, e_x_pts, e_avgsig,
                                  [np.ptp(e_avgsig), g_poptsig[1], 1,
                                   np.average(g_avgsig)], bounds = ((-np.inf,g_poptsig[1], -np.inf, -np.inf),(np.inf, g_poptsig[1], np.inf, np.inf)))


        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(g_x_pts, g_avgphase, 'o-', label="g state")
        ax0 = axs[0].plot(e_x_pts, e_avgphase, 'o-', label="e state")
        # ax0 = axs[0].plot(x_pts, fitfunc(x_pts, *poptphase))
        axs[0].set_ylabel("Degrees")
        axs[0].set_xlabel("Amplitude (in dac units)")
        axs[1].set_title("Phase")
        axs[0].legend()

        ax1 = axs[1].plot(g_x_pts, g_avgsig, 'o-', label="g state")
        ax1 = axs[1].plot(g_x_pts, fitfunc(g_x_pts,*g_poptsig))
        ax1 = axs[1].plot(e_x_pts, e_avgsig, 'o-', label="e state")
        ax1 = axs[1].plot(e_x_pts, fitfunc(e_x_pts,*e_poptsig))
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Amplitude (in dac units)")
        axs[1].set_title("Amplitude || RPM A_e/A_g = " + str(e_poptsig[0]/g_poptsig[0]))
        axs[1].legend()

        ax2 = axs[2].plot(g_x_pts, np.abs(g_avgi[0][0]), 'o-', label="g state")
        ax2 = axs[2].plot(e_x_pts, np.abs(e_avgi[0][0]), 'o-', label="e state")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Amplitude (in dac units)")
        axs[1].set_title("I-Data")
        axs[2].legend()

        ax3 = axs[3].plot(g_x_pts, np.abs(g_avgq[0][0]), 'o-', label="g state")
        ax3 = axs[3].plot(e_x_pts, np.abs(e_avgq[0][0]), 'o-', label="e state")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Amplitude (in dac units)")
        axs[1].set_title("Q-Data")
        axs[3].legend()

        fig.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(2)
            plt.close()
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
