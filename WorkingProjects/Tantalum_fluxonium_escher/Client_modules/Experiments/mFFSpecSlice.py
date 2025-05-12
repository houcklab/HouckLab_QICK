from qick import NDAveragerProgram
from qick.averager_program import QickSweep

#import MasterProject.Client_modules.CoreLib.Experiment
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions


class FFSpecSlice(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):

        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])  # Qubit
        self.declare_gen(ch = self.cfg["ff_ch"], nqz = self.cfg["ff_nqz"]) # Fast flux

        # Declare readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Create the sweep over qubit frequency
        qubit_freq_reg = self.get_gen_reg(self.cfg["qubit_ch"], "freq")
        self.add_sweep(QickSweep(self, qubit_freq_reg, self.cfg["qubit_freq_start"],
                                 self.cfg["qubit_freq_stop"], self.cfg["qubit_freq_expts"]))

        # Readout pulse
        mode_setting = "periodic" if self.cfg["ro_mode_periodic"] else "oneshot"
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                ro_ch=self.cfg["ro_chs"][0]), phase=0, gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]), mode = mode_setting)

        # Qubit pulse
        self.qubit_pulse_length = PulseFunctions.create_qubit_pulse(self, self.cfg["qubit_freq_start"])

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

        # For convenience
        post_ff_delay_cycles = self.us2cycles(self.cfg["post_ff_delay"], gen_ch=self.cfg["ff_ch"])
        qubit_pulse_length_cycles = self.us2cycles(self.qubit_pulse_length, gen_ch=self.cfg["qubit_ch"])
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0])

        self.pulse(ch = self.cfg["ff_ch"])   # play fast flux pulse
        self.pulse(ch = self.cfg["qubit_ch"], t = post_ff_delay_cycles)  # play probe pulse

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t = post_ff_delay_cycles + qubit_pulse_length_cycles, wait = True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    # Template config dictionary, used in GUI for initial values
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