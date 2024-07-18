from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from scipy.optimize import curve_fit

# Define the gaussian function
def gauss(x, a, x0, sigma, c):
    return a*np.exp(-(x-x0)**2/(2*sigma**2)) + c

class LoopbackProgramSpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters
        self.cfg["start"] = self.freq2reg(self.cfg["qubit_freq_start"], gen_ch=self.cfg["qubit_ch"])
        # We are also given freq_stop and SpecNumPoints, use these to compute freq_step
        self.cfg["step"] = self.freq2reg(
            (self.cfg["qubit_freq_stop"] - self.cfg["qubit_freq_start"]) / (self.cfg["SpecNumPoints"] - 1),
            gen_ch=self.cfg["qubit_ch"])
        self.cfg["expts"] = self.cfg["SpecNumPoints"]
        # self.cfg["reps"] = self.cfg["averages"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.q_freq = self.sreg(cfg["qubit_ch"], "freq")  # get freq register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                                  ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        # qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg[
        #     "qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=cfg["start"], phase=0,
                                     gain=cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                     # mode="periodic")
                                     )
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"])
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"], mode='periodic',
                                     length=self.us2cycles(self.cfg["read_length"]))


        else:
            print("define pi or flat top pulse")

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            print("Using Switch")
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def body(self):
        self.sync_all(self.us2cycles(0.01))
        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.q_freq, self.q_freq, '+', self.cfg["step"])  # update freq of the Gaussian pi pulse


# ====================================================== #

class SpecSlice_bkg_sub(ExperimentClass):
    """
    Basic spec experiment that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        ##### code to aquire just the qubit spec data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"])/(expt_cfg["SpecNumPoints"] - 1)
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                       expt_cfg["SpecNumPoints"])

        ### Actual data
        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)

        ### Background data
        qubit_gain = self.cfg["qubit_gain"]
        self.cfg["qubit_gain"] = 0
        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
        x_pts_bkg, avgi_bkg, avgq_bkg = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        self.cfg["qubit_gain"] = qubit_gain

        # Subtracting
        avgi = avgi[0][0] - avgi_bkg[0][0]
        avgq = avgq[0][0] - avgq_bkg[0][0]
        sig = avgi + 1j * avgq
        amp = np.abs(sig)
        phase = np.angle(sig, deg=True)
        avgi = np.abs(avgi)
        avgq = np.abs(avgq)

        # All information in amp now
        f_reqd = self.qubit_freqs[np.argmax(amp)]


        ### Save Data
        data = {'config': self.cfg, 'data': {'x_pts': self.qubit_freqs, 'avgi': avgi, 'avgq': avgq,
                                             'amp': amp, 'phase': phase, "f_reqd": f_reqd}}
        self.data = data
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


