from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from Protomon.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import pyvisa
from scipy.signal import savgol_filter


class PulseProbeSpectroscopyProgram(RAveragerProgram):

    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # Qubit configuration
        ### New things added by Sara to get fast averaging working
        self.q_rp=self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq=self.sreg(cfg["qubit_ch"], "freq")   # get frequency register for qubit_ch
        self.f_start =self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step =self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"], length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)

        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"],gen_ch=cfg["res_ch"]))#,mode="periodic")
        #             self.set_pulse_registers(ch=qubit_ch, style=style, freq=qubit_freq, phase=0, gain=cfg["qubit_gain"],
        #                                      length=cfg["qubit_length"],mode="periodic")


        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4


        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                     gain=cfg["qubit_gain"], mode = 'periodic',
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))

        else:
            print("define pi pulse")



        # self.set_pulse_registers(ch=qubit_ch, style="const",
        #                          freq=self.f_start, phase=0,
        #                          gain=cfg["qubit_gain"],
        #                          length=self.us2cycles(self.cfg["qubit_length"],gen_ch=qubit_ch))#, mode="periodic")
        self.sync_all(self.us2cycles(1))  # give processor some time to configure pulses

    def body(self):
        # Play qubit pulse
        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        # self.synci(self.us2cycles(45))
        self.sync_all() # align channels and wait 50ns

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["qubit_relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


# ====================================================== #

class SpecSlice(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
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
        ### take the transmission data
        fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.cfg["step"] = np.float((expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"])/expt_cfg["SpecNumPoints"])
        self.cfg["start"] = self.cfg["qubit_freq_start"]
        self.cfg["expts"] = self.cfg["SpecNumPoints"]
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["rounds"] = self.cfg["spec_rounds"]
        print("beginning acquire spec")
        print(self.cfg)
        start = time.time()
        prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')


        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data=data

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        x_pts = data['data']['x_pts']/1e3 # GHz
        Iavg_array = data['data']['avgi'][0][0]
        Qavg_array = data['data']['avgq'][0][0]


        ## Sara: Instead of fitting the magnitude or phase, fit whichever has higher contrast, I or Q (this drifts)
        Icontrast = np.max(abs(Iavg_array)) - np.min(abs(Iavg_array))
        Qcontrast = np.max(abs(Qavg_array)) - np.min(abs(Qavg_array))
        if Qcontrast > Icontrast:
            fit_array = Qavg_array
        if Icontrast >= Qcontrast:
            fit_array = Iavg_array

        # Smooth out the fit array and overlay that smoothed fit
        smoothed = savgol_filter(fit_array,np.shape(data['data']['x_pts'])[0], 10) ## Figure out if 51, 3 is correct

        # #### find the frequency corresponding to the qubit dip
        peak_loc = np.argmax(smoothed) #changed from argmax to argmin because I see a dip
        self.peakFreq = data['data']['x_pts'][peak_loc]

        # sig = np.abs(avgi + 1j * avgq)
        # avgamp0 = np.abs(sig)
        plt.plot(x_pts,  Iavg_array,label="I")
        plt.plot(x_pts,  Qavg_array,label="Q")
        # plt.plot(x_pts,  smoothed,label="Smoothed")
        # plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title("Reps = " + str(self.cfg["reps"]) + ", Rounds = " + str(self.cfg["rounds"]))
        plt.legend()

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


