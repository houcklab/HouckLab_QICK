from qick import RAveragerProgram

#import MasterProject.Client_modules.CoreLib.Experiment
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass

import numpy as np
import matplotlib.pyplot as plt

class FFSpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # Convention: all named parameters are in real units, parameters in cycles have suffix _cycles and
        # parameters in register units have suffix _reg

        # Required parameters for the RAveragerProgram, used internally
        self.cfg["x_pts_label"] = "qubit freq (MHz)"
        self.cfg["y_pts_label"] = None
        self.cfg["start"] = self.cfg["qubit_freq_start"]
        self.cfg["step"] = (self.cfg["qubit_freq_stop"] - self.cfg["qubit_freq_start"]) / (self.cfg["qubit_freq_expts"] - 1)
        self.cfg["expts"] = self.cfg["qubit_freq_expts"]

        # Get register page and frequency register for qubit channel
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.q_freq = self.sreg(self.cfg["qubit_ch"], "freq")  # get freq register for qubit_ch

        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])  # Qubit
        self.declare_gen(ch = self.cfg["ff_ch"], nqz = self.cfg["ff_nqz"]) # Fast flux

        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Define some register variables for convenience
        self.qubit_freq_start_reg = self.freq2reg(self.cfg["start"], gen_ch=self.cfg["qubit_ch"])
        self.qubit_freq_step_reg = self.freq2reg(self.cfg["step"], gen_ch=self.cfg["qubit_ch"])
        self.post_ff_delay_cycles = self.us2cycles(self.cfg["post_ff_delay"], gen_ch = self.cfg["ff_ch"])

        # Readout pulse
        mode_setting = "periodic" if self.cfg["ro_mode_periodic"] else "oneshot"
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                ro_ch=self.cfg["ro_chs"][0]), phase=0, gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]), mode = mode_setting)

        # Qubit pulse
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.qubit_freq_start_reg,
                                     phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulse_length = self.cfg["sigma"] * 4 # [us]

        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.qubit_freq_start_reg,
                                     phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulse_length = self.cfg["sigma"] * 4 + self.cfg["flat_top_length"] # [us]

        elif self.cfg["qubit_pulse_style"] == "const":
            mode_setting = "periodic" if self.cfg["qubit_mode_periodic"] else "oneshot"
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.qubit_freq_start_reg, phase=0,
                                     gain=self.cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]),
                                     mode=mode_setting)
            self.qubit_pulse_length = self.cfg["qubit_length"] # [u]s
        else:
            print("define arb, const, or flat top pulse")

        self.qubit_pulse_length_cycles = self.us2cycles(self.qubit_pulse_length, gen_ch=self.cfg["qubit_ch"])

        # Define the fast flux pulse #TODO just constant for now
        if self.cfg["ff_pulse_style"] == "const":
            self.set_pulse_registers(ch = self.cfg["ff_ch"], style = "const", freq = 0, phase = 0,
                                     gain = self.cfg["ff_gain"], length = self.us2cycles(self.cfg["ff_length"], gen_ch = self.cfg["ff_ch"]))
            self.flux_pulse_length = self.us2cycles(self.cfg["ff_length"], gen_ch = self.cfg["ff_ch"])

        self.sync_all(self.us2cycles(0.1))



    def body(self):
        # The pulse sequence is (for now) as follows:
        # * DC fast flux pulse (from zero) to some value
        # * After a delay time, start the qubit probe pulse
        # * Play the readout pulse
        # * Eventually: Play an inverted version of the qubit pulse -- not clear why this is necessary, Jero claims that it helps with flux stability
        self.pulse(ch = self.cfg["ff_ch"])   # play fast flux pulse
        self.pulse(ch = self.cfg["qubit_ch"], t = self.post_ff_delay_cycles)  # play probe pulse

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     t = self.post_ff_delay_cycles + self.qubit_pulse_length, wait = True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.q_freq, self.q_freq, '+', self.qubit_freq_step_reg)  # update freq of the qubit spec pulse

    ### define the template config
    ################################## code for running qubit spec on repeat
    config_template = {
        # Readout section
        "read_pulse_style": "const",     # --Fixed
        "read_length": 5,                # [us]
        "read_pulse_gain": 8000,         # [DAC units]
        "read_pulse_freq": 7392.25,      # [MHz]
        "ro_mode_periodic": False,       # Bool: if True, keeps readout tone on always

        # Qubit spec parameters
        "qubit_freq_start": 1001,        # [MHz]
        "qubit_freq_stop": 2000,         # [MHz]
        "qubit_pulse_style": "flat_top", # one of ["const", "flat_top", "arb"]
        "sigma": 0.050,                  # [us], used with "arb" and "flat_top"
        "qubit_length": 1,               # [us], used with "const"
        "flat_top_length": 0.300,        # [us], used with "flat_top"
        "qubit_gain": 25000,             # [DAC units]
        "qubit_ch": 1,                   # RFSOC output channel of qubit drive
        "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
        "qubit_mode_periodic": False,    # Bool: Applies only to "const" pulse style; if True, keeps qubit tone on always

        # Fast flux pulse parameters
        "ff_gain": 1,                    # [DAC units] Gain for fast flux pulse
        "ff_length": 50,                 # [us] Total length of positive fast flux pulse
        "post_ff_delay": 10,             # [us] Delay after fast flux pulse (before qubit pulse)
        "ff_pulse_style": "const",       # one of ["const", "flat_top", "arb"], currently only "const" is supported
        "ff_ch": 6,                      # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

        "yokoVoltage": -0.115,           # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,               # [us]
        "qubit_freq_expts": 2000,         # number of points
        "reps": 1000,
        "sets": 5,
        "use_switch": False,
    }

# ====================================================== #

class FFSpecSlice_Experiment(ExperimentClass):
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

        prog = FFSpecSlice(self.soccfg, self.cfg)

        # Check that the arguments make sense. We need the program first, to know the correct qubit pulse length
        if self.cfg["post_ff_delay"] + prog.qubit_pulse_length + self.cfg["read_length"] > self.cfg["ff_length"]:
            print("!!! WARNING: fast flux pulse turns off before readout is complete !!!")
        print("Qubit pulse length: ", prog.qubit_pulse_length)


        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)#, debug=False)

        data = {'config': self.cfg, 'data': {'x_pts': self.qubit_freqs, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        #### find the frequency corresponding to the qubit dip
        sig = np.array(data['data']['avgi']) + 1j * np.array(data['data']['avgq'])
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