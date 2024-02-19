from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit
from matplotlib import pyplot
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

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
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
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

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):
        ge_freq = self.freq2reg(self.cfg["qubit_ge_freq"], gen_ch=self.cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        ef_freq = self.freq2reg(self.cfg["qubit_ef_freq"], gen_ch=self.cfg["qubit_ch"])
        # Apply g-e pi pulse
        if self.cfg["apply_ge"]:
            if self.cfg["use_switch"]:
                self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                             width=self.cfg["trig_len"])  # trigger for switch
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                     phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
                                     waveform="qubit")
            self.pulse(ch=self.cfg["qubit_ch"])  # play ge pi pulse
        self.sync_all(self.us2cycles(0.1))
        # Apply e-f gaussian pulse with increasing amplitude
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ef_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=0,
                                 waveform="qubit")
        self.mathi(self.q_rp, self.qreg_gain, self.qreg_gain_ef, '+', 0) # Hack to set the qreg_gain register page to qreg_gain_ef (+0)
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch
        self.pulse(ch = self.cfg['qubit_ch']) # play ef probe pulse

        # # Apply g-e pi pulse to read the population of e state
        # self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
        #                          phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
        #                          waveform="qubit")
        # if self.cfg["use_switch"]:
        #     self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
        #                  width=self.cfg["trig_len"])  # trigger for switch
        # self.pulse(ch=self.cfg["qubit_ch"])  # play ge pi pulse

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
        # poptsig, pcov = curve_fit(fitfunc, x_pts, avgsig,
        #                           [np.ptp(avgsig), 1/(x_pts[np.argmax(avgsig)] -x_pts[np.argmin(avgsig)]), 1,
        #                            np.average(avgsig) ])

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
        # ax1 = axs[1].plot(x_pts, fitfunc(x_pts,*poptsig))
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Amplitude (in dac units)")
        # axs[1].set_title("Pi Pulse at " + str(np.pi/poptsig[1]))
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, avgi[0][0], 'o-', label="I")
        # ax2 = axs[2].plot(x_pts, fitfunc(x_pts,*poptavgi))
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Amplitude (in dac units)")
        # axs[1].set_title("Pi Pulse at " + str(np.pi /  poptavgi[1]))
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, avgq[0][0], 'o-', label="Q")
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

class Qubit_ef_rabiChevron(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        # Create a vector of the possible e-f frequencies to sweep over
        self.qubit_ef_freq_vec = np.linspace(self.cfg['qubit_ef_freq_start'],
                                             self.cfg['qubit_ef_freq_start'] + self.cfg['qubit_ef_freq_step']*(self.cfg["qubit_ef_freq_pts"]-1),
                                             self.cfg["qubit_ef_freq_pts"])

        # Create a vector of the possible pulse gains to sweep over
        self.qubit_ef_gain_vec = np.linspace(self.cfg['qubit_ef_gain_start'],
                                              self.cfg['qubit_ef_gain_start'] + self.cfg['RabiNumPoints']*(self.cfg['qubit_ef_gain_step']-1),
                                             self.cfg['RabiNumPoints'])

        # Create a 2d array to store the iq data
        self.Z_avgi = np.full((self.qubit_ef_freq_vec.size, self.qubit_ef_gain_vec.size), np.nan)
        self.Z_avgq = np.full((self.qubit_ef_freq_vec.size, self.qubit_ef_gain_vec.size), np.nan)

        # Collect data by sweeping over the qubit ef frequency
        for i in range(self.qubit_ef_freq_vec.size):
            # Update the qubit ef frequency
            self.cfg['qubit_ef_freq'] = self.qubit_ef_freq_vec[i]

            # pull the data from the amp rabi sweep
            prog = LoopbackProgramQubit_ef_rabi(self.soccfg, self.cfg)
            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False, debug=False)

            # Update the data arrays
            self.Z_avgi[i, :] = avgi
            self.Z_avgq[i, :] = avgq

            data = {'config': self.cfg,
                    'data': {'qubit_ef_freq_vec': self.qubit_ef_freq_vec, 'qubit_ef_gain_vec': self.qubit_ef_gain_vec,
                             'Z_avgi': self.Z_avgi, 'Z_avgq': self.Z_avgq}}

            # Update the display
            if i == 0:
                fig, axs = self.display(data = data, plotDisp = True)
            else:
                fig, axs = self.display(data=data, fig = fig, axs = axs, plotDisp = True)

        plt.close()
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, fig = None, axs = None, **kwargs):
        if data is None:
            data = self.data

        x = data['data']['qubit_ef_freq_vec']
        y = data['data']['qubit_ef_gain_vec']
        Z_avgi = data['data']['Z_avgi']
        Z_avgq = data['data']['Z_avgq']
        sig = Z_avgi + 1j * Z_avgq
        Z_avgsig = np.abs(sig)
        Z_avgphase = np.remainder(np.angle(sig, deg=True) + 360, 360)

        to_update = True

        if fig is None or axs is None:
            fig, axs = plt.subplots(4, 1, figsize=(12, 12))
            to_update = False
        else:
            if len(axs) != 4:
                raise ValueError("Unexpected number of axes provided.")
            for ax in axs:
                ax.clear()  # Clear existing plots

        # Plot Z_avgi
        ax_plot_0 = axs[0].imshow(
            Z_avgi.T,
            aspect='auto',
            extent=[x[0], x[-1], y[0], y[-1]],
            origin='lower',
            interpolation='none',
        )
        if not to_update:
            cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
            cbar0.set_label('a.u.', rotation=90)
        axs[0].set_ylabel("qubit gain")
        axs[0].set_xlabel("qubit frequency (GHz)")
        axs[0].set_title("rabi power blob: avgi")

        # Plot Z_avgq
        ax_plot_1 = axs[1].imshow(
            Z_avgq.T,
            aspect='auto',
            extent=[x[0], x[-1], y[0], y[-1]],
            origin='lower',
            interpolation='none',
        )
        if not to_update:
            cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
            cbar1.set_label('a.u.', rotation=90)
        axs[1].set_ylabel("qubit gain")
        axs[1].set_xlabel("qubit frequency (GHz)")
        axs[1].set_title("rabi power blob: avgq")

        # plot the amp
        ax_plot_2 = axs[2].imshow(
            Z_avgsig.T,
            aspect='auto',
            extent=[x[0], x[-1], y[0], y[-1]],
            origin='lower',
            interpolation='none',
        )
        if not to_update:
            cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
            cbar2.set_label('a.u.', rotation=90)
        axs[2].set_ylabel("qubit gain")
        axs[2].set_xlabel("qubit frequency (GHz)")
        axs[2].set_title("rabi power blob: amp")

        # Plot the phase
        ax_plot_3 = axs[3].imshow(
            Z_avgphase.T,
            aspect='auto',
            extent=[x[0], x[-1], y[0], y[-1]],
            origin='lower',
            interpolation='none',
        )
        if not to_update:
            cbar3 = fig.colorbar(ax_plot_3, ax=axs[3], extend='both')
            cbar3.set_label('a.u.', rotation=90)
        axs[3].set_ylabel("qubit gain")
        axs[3].set_xlabel("qubit frequency (GHz)")
        axs[3].set_title("rabi power blob: phase")

        fig.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(2)
        else:
            fig.clf(True)
            plt.close(fig)

        return fig, axs
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
        self.cfg["reps"] = self.cfg["g_reps"]
        prog = LoopbackProgramQubit_ef_rabi(self.soccfg, self.cfg)
        g_x_pts, g_avgi, g_avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)

        ## Acquire the data when no g-e pi pulse is applied
        self.cfg["apply_ge"] = False
        self.cfg["reps"] = self.cfg["e_reps"]
        print(self.cfg["reps"])
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
        g_avgi = data['data']['g_avgi'][0][0]
        g_avgq = data['data']['g_avgq'][0][0]
        g_sig  = g_avgi + 1j * g_avgq
        g_avgsig = np.abs(g_sig)
        g_avgphase = np.remainder(np.angle(g_sig,deg=True)+360,360)

        # Import the data for measuring the e-state
        e_x_pts = data['data']['e_x_pts']
        e_avgi = data['data']['e_avgi'][0][0]
        e_avgq = data['data']['e_avgq'][0][0]
        e_sig  = e_avgi + 1j * e_avgq
        e_avgsig = np.abs(e_sig)
        e_avgphase = np.remainder(np.angle(e_sig,deg=True)+360,360)

        # Fitting the sinusoid
        # Defining the fit function
        def fitfunc(x,a,b,c,d):
            return a*np.sin(x*b+c) + d

        # Fitting for amplitude for g-state
        g_popti, g_pcov = curve_fit(fitfunc, g_x_pts, g_avgi,
                                  [np.ptp(g_avgi), 1/(g_x_pts[np.argmax(g_avgi)] -g_x_pts[np.argmin(g_avgi)]), 1,
                                   np.average(g_avgi) ])

        # Fitting for amplitude for e-state with bounds on the frequency (b) set by the frequency (b) found for g-state
        # This is basically like a lock-in amplifier
        e_popti, e_pcov = curve_fit(fitfunc, e_x_pts, e_avgi,
                                  [np.ptp(e_avgi), g_popti[1], g_popti[2],
                                   np.average(e_avgi)], bounds = ((-np.inf, g_popti[1]-np.abs(g_popti[1]/10), -np.inf, -np.inf),(np.inf, g_popti[1], np.inf, np.inf)))


        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(g_x_pts, g_avgphase, 'o-', label="g state")
        ax0 = axs[0].plot(e_x_pts, e_avgphase, 'o-', label="e state")
        # ax0 = axs[0].plot(x_pts, fitfunc(x_pts, *poptphase))
        axs[0].set_ylabel("Degrees")
        axs[0].set_xlabel("Amplitude (in dac units)")
        axs[0].set_title("Phase")
        axs[0].legend()

        ax1 = axs[1].plot(g_x_pts, g_avgsig, 'o-', label="g state")

        ax1 = axs[1].plot(e_x_pts, e_avgsig, 'o-', label="e state")

        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Amplitude (in dac units)")

        axs[1].legend()

        ax2 = axs[2].plot(g_x_pts, g_avgi, 'o-', label="g state")
        ax1 = axs[2].plot(g_x_pts, fitfunc(g_x_pts, *g_popti))
        ax2 = axs[2].plot(e_x_pts, e_avgi, 'o-', label="e state")
        ax1 = axs[2].plot(e_x_pts, fitfunc(e_x_pts, *e_popti))
        axs[2].set_ylabel("Amplitude")
        axs[2].set_xlabel("Amplitude (in dac units)")
        axs[2].set_title("I-Data")
        axs[2].set_title("Amplitude || RPM : A_e/A_g = " + str(np.abs(e_popti[0] / g_popti[0])))
        axs[2].legend()

        ax3 = axs[3].plot(g_x_pts,  g_avgq, 'o-', label="g state")
        ax3 = axs[3].plot(e_x_pts,  e_avgq, 'o-', label="e state")
        axs[3].set_ylabel("Amplitude")
        axs[3].set_xlabel("Amplitude (in dac units)")
        axs[3].set_title("Q-Data")
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
