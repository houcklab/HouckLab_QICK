###

###

from qick import NDAveragerProgram
from qick.averager_program import QickSweep

#import MasterProject.Client_modules.CoreLib.Experiment
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import PulseFunctions


class FFSpecSliceReversed(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):

        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])  # Qubit
        self.declare_gen(ch = self.cfg["ff_ch"], nqz = self.cfg["ff_nqz"]) # Fast flux

        # Declare readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch = self.cfg["res_ch"]),
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
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]), mode = mode_setting)

        # Qubit pulse
        self.qubit_pulse_length = PulseFunctions.create_qubit_pulse(self, self.cfg["qubit_freq_start"])

        # Define the fast flux pulse
        if self.cfg["ff_pulse_style"] == "ramp":
            print("Using RAMP")
            self.cfg["ff_ramp_start"] = 0
            self.cfg['ff_ramp_stop'] = self.cfg['ff_gain']
            self.cfg['ff_ramp_style'] = "linear"
            if 'ff_ramp_length' not in self.cfg.keys():
                raise Exception("ff_ramp_length nor defined in the config")
            PulseFunctions.create_ff_ramp(self, reversed=False)
            PulseFunctions.create_ff_ramp(self, reversed=True)
        else:
            raise Exception("Only 'ramp' ff_pulse_style is currently supported")

        if "negative_pulse" in self.cfg.keys():
            if self.cfg["negative_pulse"]:
                print(f"Playing negative pulses for integration to be zero")
        else:
            self.cfg['negative_pulse'] = False
            print("Not playing negative pulses")

        self.sync_all(self.us2cycles(0.1))



    def body(self):
            qubit_spec_delay_cycles = self.us2cycles(self.cfg["qubit_spec_delay"])
            adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])
            meas_delay_cycles = self.us2cycles(self.cfg.get("pre_meas_delay", self.cfg['qubit_spec_delay'] + self.qubit_pulse_length))
            pre_ff_delay_cycles = self.us2cycles(self.cfg["pre_ff_delay"])
            ff_length_cycles = self.us2cycles(self.cfg["ff_length"])
            ramp_length_cycles = self.us2cycles(self.cfg["ff_ramp_length"])

            self.pulse(ch=self.cfg["qubit_ch"], t=qubit_spec_delay_cycles)

            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                     gain=self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t=pre_ff_delay_cycles)

            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                     gain=self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t=pre_ff_delay_cycles + ff_length_cycles+ramp_length_cycles)

            # trigger measurement, play measurement pulse, wait for qubit to relax
            self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                         t=meas_delay_cycles, wait=False) #self.wait_4_pulse_pattern
            # Sync all
            self.sync_all(self.us2cycles(1))
            if self.cfg['negative_pulse']:
                self.sync_all(self.us2cycles(1))
                self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                         gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
                self.pulse(ch=self.cfg["ff_ch"], t='auto')
                self.sync_all(ff_length_cycles+ramp_length_cycles)
                self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                         gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
                self.pulse(ch=self.cfg["ff_ch"], t='auto')

            self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

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
        "qubit_spec_delay": 10,          # [us] Delay before qubit pulse

        # Fast flux pulse parameters
        "ff_gain": 1,                    # [DAC units] Gain for fast flux pulse
        "ff_length": 50,                 # [us] Total length of positive fast flux pulse
        "pre_ff_delay": 1,               # [us] Delay before the fast flux pulse
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

class FFSpecSliceReverse_Experiment(ExperimentClass):
    """
    Perform qubit spectroscopy during a fast flux pulse.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress=False, debug=False):
        self.soc.reset_gens()

        if self.cfg['qubit_spec_delay'] + self.cfg["qubit_length"] - self.cfg["pre_ff_delay"] - self.cfg["ff_length"] > 0:
            print("The qubit tone is on after the end of the fast flux pulse.")
        if self.cfg['qubit_spec_delay'] + self.cfg["qubit_length"] - self.cfg["pre_ff_delay"] < 0:
            print("The qubit tone starts before the beginning of the fast flux pulse.")
        if self.cfg["pre_meas_delay"] < self.cfg['qubit_spec_delay'] + self.cfg["qubit_length"]:
            print("Warning: Measurement starts before the end of the qubit pulse.")
        if self.cfg["pre_meas_delay"] > self.cfg["pre_ff_delay"] + self.cfg["ff_length"]:
            print("Warning: Measurement starts after the end of the fast flux pulse.")
        if self.cfg["pre_meas_delay"] + self.cfg["read_length"] > self.cfg["pre_ff_delay"] + self.cfg["ff_length"]:
            print("Warning: Measurement ends after the end of the fast flux pulse.")

         # Create the experiment program
        prog = FFSpecSliceReversed(self.soccfg, self.cfg)
        # Collect the data
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=progress)

        self.qubit_freqs = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                       self.cfg["qubit_freq_expts"])

        sig  = avgi[0][0] + 1j * avgq[0][0]
        mag = np.abs(sig)

        self.qubit_peak_freq = self.qubit_freqs[np.argmax(mag)]

        data = {'config': self.cfg, 'data': {'x_pts': self.qubit_freqs, 'avgi': avgi, 'avgq': avgq, 'qubit_peak_freq': self.qubit_peak_freq}}
        self.data = data

        return data

    def display(self, data=None, plot_disp = False, fig_num = 1, **kwargs):

        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)
        while plt.fignum_exists(num=fig_num): ###account for if figure with number already exists
            fig_num += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=fig_num)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="phase")
        axs[0].set_ylabel("deg")
        axs[0].set_xlabel("Qubit Frequency (GHz)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="magnitude")
        axs[1].set_ylabel("ADC units")
        axs[1].set_xlabel("Qubit Frequency (GHz)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I - Data")
        axs[2].set_ylabel("ADC units")
        axs[2].set_xlabel("Qubit Frequency (GHz)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q - Data")
        axs[3].set_ylabel("ADC units")
        axs[3].set_xlabel("Qubit Frequency (GHz)")
        axs[3].legend()

        plt.tight_layout()
        fig.subplots_adjust(top=0.95)
        plt.suptitle(self.fname + '\nYoko voltage %f V, FF amplitude %d DAC.' % (self.cfg['yokoVoltage'], self.cfg['ff_gain']))

        plt.savefig(self.iname)

        if plot_disp:
            plt.show(block=False)
            plt.pause(2)

        else:
            fig.clf(True)
            plt.close(fig)




    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        #TODO broken by change of experiment
        return self.cfg["reps"] * self.cfg["qubit_freq_expts"] * (self.cfg["relax_delay"] + self.cfg["ff_length"]) * 1e-6  # [s]