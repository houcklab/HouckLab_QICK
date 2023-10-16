from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

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

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))

        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=cfg["start"], phase=0,
                                     gain=cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                     mode="periodic")
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"], mode='periodic',
                                     length=self.us2cycles(self.cfg["read_length"]))

        else:
            print("define pi or flat top pulse")

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def body(self):

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
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"])/expt_cfg["SpecNumPoints"]
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                       expt_cfg["SpecNumPoints"])

        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)

        for idx in range(self.cfg["sets"]):
            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False, debug=False)
            if idx == 0:
                self.x_pts = x_pts
                self.avgi = avgi
                self.avgq = avgq
                data = {'config': self.cfg, 'data': {'x_pts': self.qubit_freqs, 'avgi': avgi, 'avgq': avgq}}
            else:
                self.avgi += avgi
                self.avgq += avgq
                data = {'config': self.cfg, 'data': {'x_pts': self.qubit_freqs, 'avgi': self.avgi/(idx+1), 'avgq': self.avgq/(idx+1)}}

            self.data = data

            self.display(plotDisp = True, figNum = 1)
            # self.save_data(data)

        #### find the frequency corresponding to the qubit dip
        sig = data['data']['avgi'] + 1j * data['data']['avgq']
        avgamp0 = np.abs(sig)

        # peak_loc = np.argmax(np.abs(data['data']['avgq'])) # Maximum location
        peak_loc = np.argmin(np.abs(data['data']['avgq']))  # Minimum location
        # print(np.max(np.abs(data['data']['avgq'])))
        self.qubitFreq = data['data']['x_pts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):

        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)

        try:
            self.fig.clf()
        except:
            pass

        self.fig, self.axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        fig = self.fig
        axs = self.axs

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="phase")
        axs[0].set_ylabel("degree.")
        axs[0].set_xlabel("Qubit Frequency (GHz)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Qubit Frequency (GHz)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I - Data")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Qubit Frequency (GHz)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q - Data")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Qubit Frequency (GHz)")
        axs[3].legend()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.2)

        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

