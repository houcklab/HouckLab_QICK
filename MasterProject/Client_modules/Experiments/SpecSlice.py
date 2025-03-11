from qick import RAveragerProgram
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass

import numpy as np
import matplotlib.pyplot as plt

class SpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        #### set the start, step, and other parameters
        self.cfg["x_pts_label"] = "qubit freq (MHz)"
        self.cfg["y_pts_label"] = None

        ### define the start and step for the dictionary
        self.cfg["start"] = self.cfg["qubit_freq_start"]
        self.cfg["step"] = (self.cfg["qubit_freq_stop"] - self.cfg["qubit_freq_start"]) / (self.cfg["qubit_freq_expts"] - 1)
        self.cfg["expts"] = self.cfg["qubit_freq_expts"]

        ### define the start and step in dac values
        self.f_start = self.freq2reg(self.cfg["start"], gen_ch=self.cfg["qubit_ch"])
        self.f_step = self.freq2reg(self.cfg["step"], gen_ch=self.cfg["qubit_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.q_freq = self.sreg(self.cfg["qubit_ch"], "freq")  # get freq register for qubit_ch

        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])  # Qubit

        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        ### convert the readout frequency to proper units
        read_freq = self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                  ro_ch=self.cfg["ro_chs"][0])  # convert to dac register value


        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        #### define the qubit pulse depending on the pulse type
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")

        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))

        elif self.cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                     gain=self.cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]), )
            # mode="periodic")
        else:
            print("define arb, const, or flat top pulse")

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
        self.mathi(self.q_rp, self.q_freq, self.q_freq, '+', self.f_step)  # update freq of the Gaussian pi pulse

    ### define the template config
    ################################## code for running qubit spec on repeat
    config_template = {
        ##### define attenuators
        "yokoVoltage": 0.25,
        ###### cavity
        "read_pulse_style": "const",  # --Fixed
        "read_length": 5,  # us
        "read_pulse_gain": 10000,  # [DAC units]
        "read_pulse_freq": 6425.3,
        ##### spec parameters for finding the qubit frequency
        "qubit_freq_start": 2869 - 20,
        "qubit_freq_stop": 2869 + 20,
        "qubit_freq_expts": 81,  ### number of points
        "qubit_pulse_style": "flat_top",
        "sigma": 0.050,  ### units us
        "qubit_length": 1,  ### units us, doesnt really get used though
        "flat_top_length": 0.300,  ### in us
        "relax_delay": 500,  ### turned into us inside the run function
        "qubit_gain": 20000,  # Constant gain to use
        # "qubit_gain_start": 18500, # shouldn't need this...
        "reps": 100,
        "sets": 5,
    }

# ====================================================== #

class SpecSlice_Experiment(ExperimentClass):
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
            "qubit_freq_expts": self.cfg["qubit_freq_expts"],  ### number of points
        }
        # self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"])/expt_cfg["qubit_freq_expts"]
        self.cfg["expts"] = expt_cfg["qubit_freq_expts"]

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                       expt_cfg["qubit_freq_expts"])

        prog = SpecSlice(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)

        data = {'config': self.cfg, 'data': {'x_pts': self.qubit_freqs, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        #### find the frequency corresponding to the qubit dip
        #### Has a complex multiplication type error somewhere below
        # sig = data['data']['avgi'] + 1j * data['data']['avgq']
        # avgamp0 = np.abs(sig)

        # peak_loc = np.argmax(np.abs(data['data']['avgq'])) # Maximum location
        # peak_loc = np.argmin(np.abs(data['data']['avgq']))  # Minimum location
        # print(np.max(np.abs(data['data']['avgq'])))
        # self.qubitFreq = data['data']['x_pts'][peak_loc]

        return data

    @classmethod
    def plotter(cls, data):
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        sig = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)

        # Create structured output
        prepared_data = {
            "plots": [
                {"x": x_pts, "y": avgphase, "label": "Phase", "xlabel": "Qubit Frequency (GHz)", "ylabel": "Degree"},
                {"x": x_pts, "y": avgsig, "label": "Magnitude", "xlabel": "Qubit Frequency (GHz)", "ylabel": "a.u."},
                {"x": x_pts, "y": np.abs(avgi[0][0]), "label": "I - Data", "xlabel": "Qubit Frequency (GHz)",
                 "ylabel": "a.u."},
                {"x": x_pts, "y": np.abs(avgq[0][0]), "label": "Q - Data", "xlabel": "Qubit Frequency (GHz)",
                 "ylabel": "a.u."}
            ]
        }

        return prepared_data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):

        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)
        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

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

        plt.tight_layout()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(2)

        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
