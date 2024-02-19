from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

from scipy.optimize import curve_fit

# Define the gaussian function
def gauss(x, a, x0, sigma, c):
    return a*np.exp(-(x-x0)**2/(2*sigma**2)) + c

class LoopbackProgramQubit_ef_spectroscopy(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters

        # Frequency of putative ef pulse, in MHz
        self.cfg["start"] = self.cfg["qubit_ef_freq_start"]
        self.cfg["step"] = self.cfg["qubit_ef_freq_step"]
        # How many frequency steps to do
        self.cfg["expts"] = self.cfg["SpecNumPoints"]

        # Number of averages at each step
        # self.cfg["reps"] = self.cfg["AmpRabi_reps"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.r_freq = self.sreg(self.cfg["qubit_ch"], "freq") # frequency register on qubit channel
        # To see list of all registers: self.pulse_registers
        # We need an additional register to use for the e-g frequency.
        # I don't know how to check the list of registers properly, so I will just use an arbitrary number that doesn't
        # match any of the ones listed above for channel 0 or 1, which are readout and qubit, resp.
        self.r_freq_ef = 4 # Taken from https://github.com/conniemiao/slab_rfsoc_expts/blob/d62c098f55bc4745bfb8e9ffa41d5bb49085b11e/experiments/single_qubit/pulse_probe_ef_spectroscopy.py#L99

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_ge_freq = self.freq2reg(cfg["qubit_ge_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.safe_regwi(self.q_rp, self.r_freq_ef, self.freq2reg(self.cfg["start"], gen_ch = self.cfg["qubit_ch"])) # Set the ef frequency register to start at the correct value

        # Define qubit pulse: gaussian
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
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
        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_ge_freq, phase=0,
                                     gain=cfg["qubit_ge_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                     mode="periodic")
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

        # Set up g-e pi pulse
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
                                 waveform="qubit")
        self.pulse(ch=self.cfg["qubit_ch"])  # play ge pi pulse
        self.sync_all(self.us2cycles(0.005))  # align channels and wait /

        # Apply e-f gaussian pulse with increasing amplitude
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ef_gain"],
                                 waveform="qubit")
        self.mathi(self.q_rp, self.r_freq, self.r_freq_ef, '+', 0) # Hack to set the r_freq register page to r_freq_ef (+0)
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])
        self.pulse(ch = self.cfg['qubit_ch']) # play ef probe pulse

        self.sync_all(self.us2cycles(0.05)) # align channels and wait /
        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq_ef, self.r_freq_ef, '+', self.freq2reg(self.cfg["step"], gen_ch = self.cfg["qubit_ch"])) # update frequency of the ef spectroscopy probe




# ====================================================== #

class Qubit_ef_spectroscopy(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramQubit_ef_spectroscopy(self.soccfg, self.cfg)
        start = time.time()
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)

        #### Background data
        qubit_ef_gain = self.cfg["qubit_ef_gain"]
        qubit_ge_gain = self.cfg["qubit_ge_gain"]
        self.cfg["qubit_ef_gain"] = 0
        self.cfg["qubit_ge_gain"] = 0
        prog = LoopbackProgramQubit_ef_spectroscopy(self.soccfg, self.cfg)
        x_pts_bkg, avgi_bkg, avgq_bkg = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                                     readouts_per_experiment=1, save_experiments=None,
                                                     start_src="internal", progress=False, debug=False)
        self.cfg["qubit_ef_gain"] = qubit_ef_gain
        self.cfg["qubit_ge_gain"] = qubit_ge_gain
        # Subtracting
        avgi = avgi[0][0] - avgi_bkg[0][0]
        avgq = avgq[0][0] - avgq_bkg[0][0]
        sig = avgi + 1j * avgq
        amp = np.abs(sig)
        phase = np.angle(sig, deg=True)
        avgi = np.abs(avgi)
        avgq = np.abs(avgq)

        # All information in amp now
        f_reqd = x_pts[np.argmax(amp)]

        ### Save Data
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq,
                                             'amp': amp, 'phase': phase, "f_reqd": f_reqd}}
        self.data = data
        return data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        amp = data['data']['amp']
        phase = data['data']['phase']
        f_reqd = data['data']['f_reqd']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        axs[0].scatter(x_pts, avgi, c='b', label='data')
        axs[0].set_xlabel('Frequency (GHz)')
        axs[0].set_ylabel('I (a.u.)')
        axs[0].set_title('I vs Frequency')
        # Add a text box with the fit parameters

        axs[1].scatter(x_pts, avgq, c='b', label='data')
        axs[1].set_xlabel('Frequency (GHz)')
        axs[1].set_ylabel('Q (a.u.)')
        axs[1].set_title('Q vs Frequency')

        axs[2].scatter(x_pts, amp, c='b', label='data')
        try:
            popt, pcov = curve_fit(gauss, x_pts, amp, p0=[max(amp) - min(amp), f_reqd, (max(x_pts) - min(x_pts))/7,
                                                          min(amp) if f_reqd > np.average(amp) else max(amp)])
            axs[2].plot(x_pts, gauss(x_pts, popt[0], popt[1], popt[2], popt[3]))

            label = r'$f_{01}$ =' + str(popt[1].round(3)) + ' MHz\n$\sigma$ =' + str(popt[2].round(1)) + ' MHz'
            props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
            axs[2].text(0.01, 0.95, label, transform=axs[2].transAxes, fontsize=14,
                        verticalalignment='top', bbox=props)
        except:
            print("Cannot amp-plot fit")
        axs[2].set_xlabel('Frequency (GHz)')
        axs[2].set_ylabel('Amplitude (a.u.)')
        axs[2].set_title('Amplitude vs Frequency')

        axs[3].scatter(x_pts, phase, c='b', label='data')
        axs[3].set_xlabel('Frequency (GHz)')
        axs[3].set_ylabel('Phase (rad)')
        axs[3].set_title('Phase vs Frequency')

        try:
            data_information = ("Fridge Temperature = " + str(self.cfg["fridge_temp"]) + "mK, Yoko_Volt = "
                                + str(self.cfg["yokoVoltage_freqPoint"]) + "V, relax_delay = " + str(
                                self.cfg["relax_delay"]) + "us." + " Qubit Frequency = " + str(f_reqd.round(2))
                                + " MHz \n" )
            plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        except:
            print("Cannot make title")

        plt.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
        else:
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


