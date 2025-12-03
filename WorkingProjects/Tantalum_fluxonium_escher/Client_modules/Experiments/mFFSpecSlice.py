###
# This file contains an NDAveragerProgram and ExperimentClass for doing qubit spectroscopy with a fast flux pulse.
# Lev, May 2025: create file.
# Lev, October 2025: Add reverse pulse.
# Lev, October 2025: Modify to allow arbitrarily-long ff pulses via short pulse + stdysel = 'last' + delay
###
import sys

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
        if self.cfg["ff_pulse_style"] == "const":
            # In order to allow the pulse to be very long, define the pulse itself as 3 clock ticks, then wait
            # using stdysel = 'last' to keep the ff value at ff_gain
            self.set_pulse_registers(ch = self.cfg["ff_ch"], style = "const", freq = 0, phase = 0,
                                     gain = self.cfg["ff_gain"], stdysel = 'last', length = 3)
        elif self.cfg["ff_pulse_style"] == "linear":
            PulseFunctions.create_ff_ramp(self, 0, self.cfg["ff_gain"], "ramp_there")
            PulseFunctions.create_ff_ramp(self, self.cfg["ff_gain"], 0, "ramp_back")
            self.set_pulse_registers(ch = self.cfg["ff_ch"], freq = 0, style = 'arb', phase = 0, outsel = "input",
                                     gain = self.soccfg['gens'][0]['maxv'], waveform= "ramp_there",  stdysel = 'last')
            raise ValueError("\"linear\" not yet fully supported!")
        else:
            raise ValueError('Only \"const\" and \"linear\" ff_pulse_style current supported!')

        self.sync_all(self.us2cycles(0.1))



    def body(self):
        # The pulse sequence is (for now) as follows:
        # * After a delay time, start the qubit probe pulse
        # * DC fast flux pulse (from zero) to some value (order of first two depends on parameters)
        # * Play the readout pulse
        # * Play an inverted version of the qubit pulse if desired

        # For convenience
        qubit_pulse_length_cycles = self.us2cycles(self.qubit_pulse_length, gen_ch=self.cfg["qubit_ch"])
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])

        ##### For debugging #####
        # Marker pulse for beginning of experiment
        if "marker_pulse" in self.cfg and self.cfg["marker_pulse"]:
            self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
            self.q_gain = self.sreg(self.cfg["qubit_ch"], "gain")  # Get gain register for qubit_ch
            self.safe_regwi(self.q_rp, self.q_gain, 32000)

            self.pulse(ch = self.cfg["qubit_ch"])

            self.safe_regwi(self.q_rp, self.q_gain, 16000)
            self.sync_all(10)
        #########################

        case3 = False  # lazy
        # Cut the FF pulse short after qubit pulse is done, move readout earlier as well
        if self.cfg["cut_off_ff_pulse"]:
            # Note that we need to be careful in interpreting this case, especially if relax delay is not long enough!
            ### There are three main cases here, within reasonable assumptions

            # Case 1: The qubit pulse is complete before the fast flux pulse even starts; do not play ff at all
            if self.cfg["qubit_spec_delay"] + self.qubit_pulse_length < self.cfg["pre_ff_delay"]:
                self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(self.cfg["qubit_spec_delay"]))  # play probe pulse

                self.sync_all(self.us2cycles(0.05))

                # trigger measurement, play measurement pulse, wait for qubit to relax
                self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], t=0, wait=True,
                             adc_trig_offset=adc_trig_offset_cycles,
                             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

            # Case 2: The qubit pulse has started, but not finished, before ff is complete; play part of ff
            elif self.cfg["qubit_spec_delay"] + self.qubit_pulse_length < \
                    self.cfg["pre_ff_delay"] + self.cfg["ff_length"]:

                self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(self.cfg["qubit_spec_delay"]))  # play probe pulse

                self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                         gain=self.cfg["ff_gain"], stdysel='last', length=3)
                self.pulse(ch=self.cfg["ff_ch"], t=self.us2cycles(self.cfg["pre_ff_delay"]))  # play fast flux pulse

                # Define pulse to bring ff back to 0, and pulse
                self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                         gain=0, stdysel='last', length=3)
                # Cut off the ff pulse after the qubit pulse is done + 50 ns to make sure
                ff_pulse_cutoff = self.cfg["qubit_spec_delay"] + self.qubit_pulse_length + 0.05
                self.pulse(ch=self.cfg["ff_ch"], t=self.us2cycles(ff_pulse_cutoff))

                self.sync_all(self.us2cycles(
                    0.05))  # Wait for a bit to make sure the fast flux is back to 0 in case there's delay

                # trigger measurement, play measurement pulse, wait for qubit to relax
                self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"],
                             adc_trig_offset=adc_trig_offset_cycles,
                             t=0, wait=True,
                             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

                # Reverse pulse assumes base ff value is 0 DAC
                # It doesn't really matter that we relax before this I think, this will effectively just start with a reverse pulse
                if self.cfg['reverse_pulse']:
                    self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0, stdysel='last',
                                             gain=-self.cfg["ff_gain"], length=3)
                    self.pulse(ch=self.cfg["ff_ch"])

                    # Wait -- no need for any command, just increase t on next pulse

                    # Come back to 0 DAC
                    self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0, stdysel='last',
                                             gain=0, length=3)
                    reverse_pulse_length = ff_pulse_cutoff - self.cfg["pre_ff_delay"]
                    self.pulse(ch=self.cfg["ff_ch"], t=self.us2cycles(reverse_pulse_length))

            # Case 3: The qubit pulse has not finished until the end of the fast flux pulse; play the whole ff pulse
            # This is identical to the full pulse below, just no need to wait until we hit the qubit delay stop to read
            else:
                case3 = True

        if not self.cfg["cut_off_ff_pulse"] or case3:
            # t uses the master clock, no generator argument!
            self.pulse(ch = self.cfg["qubit_ch"], t = self.us2cycles(self.cfg["qubit_spec_delay"]))  # play probe pulse

            self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                     gain=self.cfg["ff_gain"], stdysel='last', length=3)
            self.pulse(ch = self.cfg["ff_ch"], t = self.us2cycles(self.cfg["pre_ff_delay"]))   # play fast flux pulse

            # Define pulse to bring ff back to 0, and pulse
            self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                     gain=0, stdysel='last', length=3)
            self.pulse(ch = self.cfg["ff_ch"], t = self.us2cycles(self.cfg["pre_ff_delay"] + self.cfg["ff_length"]))

            # Play another pulse (that does nothing) at the last time, such that the sync_all waits until after this
            # Add 3 clock cycles just to make sure it's not overlapping with previous, it's only a few ns anyway
            # Only do this if this is a mFFSpecVsDelay instance
            # Do NOT do this in case 3 from above, go straight to measurement, we don't want extra wait here
            if "qubit_spec_delay_stop" in self.cfg and not case3:
                self.pulse(ch = self.cfg["ff_ch"], t = self.us2cycles(self.cfg["qubit_spec_delay_stop"]) + 3)

            self.sync_all(self.us2cycles(0.05))  # Wait for a bit to make sure the fast flux is back to 0 in case there's delay

            # trigger measurement, play measurement pulse, wait for qubit to relax
            self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                         t = 0, wait = True,
                         syncdelay=self.us2cycles(self.cfg["relax_delay"]))

            # Reverse pulse assumes base ff value is 0 DAC
            # It doesn't really matter that we relax before this I think, this will effectively just start with a reverse pulse
            if self.cfg['reverse_pulse']:
                self.set_pulse_registers(ch = self.cfg["ff_ch"], style = "const", freq = 0, phase = 0, stdysel = 'last',
                                         gain = -self.cfg["ff_gain"], length = 3)
                self.pulse(ch=self.cfg["ff_ch"])

                # Wait -- no need for any command, just increase t on next pulse

                # Come back to 0 DAC
                self.set_pulse_registers(ch = self.cfg["ff_ch"], style = "const", freq = 0, phase = 0, stdysel = 'last',
                                         gain = 0, length = 3)
                self.pulse(ch=self.cfg["ff_ch"], t = self.us2cycles(self.cfg["ff_length"]))

        # sync everything again before start of next loop, else pulses come in at the wrong time!
        self.sync_all(3)



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
        "ff_pulse_style": "const",       # one of ["const", "linear"], currently only "const" is supported
        "ff_ramp_length": 1,             # [us] length of one half of the flux ramp, used with linear style
        "ff_ch": 6,                      # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
        "reverse_pulse": True,           # [Bool] reverse fast flux pulse to cancel current in reactive components

        # Other parameters
        "yokoVoltage": -0.115,           # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,               # [us]
        "qubit_freq_expts": 2000,         # number of points
        "reps": 1000,
        "sets": 5,
        "use_switch": False,
        "cut_off_ff_pulse": False,       # [Bool] do we cut off the fast flux pulse if the qubit pulse is done already?
    }

# ====================================================== #

class FFSpecSlice_Experiment(ExperimentClass):
    """
    Perform qubit spectroscopy during a fast flux pulse.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress=False, debug=False):
        prog = FFSpecSlice(self.soccfg, self.cfg)

        # print(prog)
        # import sys
        # sys.exit()
        # Check that the arguments make sense. We need the program first, to know the correct qubit pulse length
        # This warning is not relevant in this version, the sync_all ensures readout happens at 0 ff
        # if self.cfg["qubit_spec_delay"] + prog.qubit_pulse_length + self.cfg["read_length"] > self.cfg["ff_length"]:
        #     print("!!! WARNING: fast flux pulse turns off before readout is complete !!!")
        print("Qubit pulse length: ", prog.qubit_pulse_length)

        # Warn the user if we're cutting the ff pulses short, as interpreting this case is difficult for a short relax
        if self.cfg["cut_off_ff_pulse"]:
            print('Warning: cutting off ff pulses. Ensure sufficient relax delay!', file = sys.stderr)

        if "marker_pulse" in self.cfg and self.cfg["marker_pulse"]:
            print('Warning: playing marker pulse!', file = sys.stderr)

        # Collect the data
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=progress)

        self.qubit_freqs = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                       self.cfg["qubit_freq_expts"])
        data = {'config': self.cfg, 'data': {'x_pts': self.qubit_freqs, 'avgi': avgi, 'avgq': avgq}}
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