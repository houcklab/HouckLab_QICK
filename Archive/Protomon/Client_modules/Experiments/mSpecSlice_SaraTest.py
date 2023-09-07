from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from Protomon.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import pyvisa

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
        self.set_pulse_registers(ch=qubit_ch, style=self.cfg["qubit_pulse_style"],
                                 freq=self.f_start, phase=0,
                                 gain=cfg["qubit_gain"],
                                 length=self.us2cycles(self.cfg["qubit_length"],gen_ch=qubit_ch))#, mode="periodic")
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        # Play qubit pulse
        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        self.sync_all() # align channels and wait 50ns

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

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
        self.cfg["reps"] = self.cfg["spec_reps"]
        fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.cfg["step"] = np.float((expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"])/expt_cfg["SpecNumPoints"])
        self.cfg["start"] = self.cfg["qubit_freq_start"]
        self.cfg["expts"] = self.cfg["SpecNumPoints"]
        results = []
        start = time.time()
        prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        print(f'Time: {time.time() - start}')
        self.data=data

        # #### find the frequency corresponding to the qubit dip
        # sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        # avgamp0 = np.abs(sig)
        # peak_loc = np.argmin(avgamp0)
        # self.qubitFreq = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        x_pts = data['data']['x_pts']/1e3 # GHz
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        sig = np.abs(avgi + 1j * avgq)
        avgamp0 = np.abs(sig)
        plt.plot(x_pts,  avgi,label="I value; ADC 0")
        plt.plot(x_pts,  avgq,label="Q value; ADC 0")
        plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title("Averages = " + str(self.cfg["reps"]))
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


