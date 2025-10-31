###
# Experiment to perform qubit spectroscopy during a fast flux pulse with pulse pre-distortion
# Author : Parth Jatakia
# Date : October 2025
###

from qick import NDAveragerProgram
from qick.averager_program import QickSweep

#import MasterProject.Client_modules.CoreLib.Experiment
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import PulseFunctions


class FFSpecSlice_wPPD(NDAveragerProgram):
    def __init__(self, soccfg, cfg, plot_debug = False):
        self.plot_debug = plot_debug
        super().__init__(soccfg, cfg)

    def create_avg_segs(self, seg, dt_pulsedef = 0.25, dt_pulseplay = 10):
        """
        Creates averaged segments from the input waveform `seg` by grouping points and calculating their mean.

        This function takes an input waveform `seg` and divides it into smaller segments based on the time step
        `dt_pulseplay`. Each segment is averaged to produce a simplified representation of the waveform.

        Parameters:
            seg (list or numpy array): The input waveform, where each point is spaced by `dt_pulsedef`.
            dt_pulsedef (float, optional): The time step (in microseconds) between points in the input waveform. Default is 0.25.
            dt_pulseplay (float, optional): The time step (in microseconds) for grouping points to calculate the mean. Default is 10.

        Returns:
            numpy array: A new waveform where each point represents the mean of a group of points from the input waveform.
                         If the input `seg` is empty, an empty list is returned.
        """
        if len(seg) == 0: # Making sure that empty segments dont return Nan values but just empty lists
            return []
        points_per_play_step = int(dt_pulseplay/dt_pulsedef)
        num_play_steps = int(len(seg)/points_per_play_step)
        if num_play_steps == 0 : # If number of steps is zero given segment is non zero implies that dt_pulseplay >
            # length of seg
            num_play_steps = 1
        seg_play = np.zeros(num_play_steps)
        for i in range(num_play_steps):
            seg_play[i] = np.mean(seg[i*points_per_play_step:(i+1)*points_per_play_step])
        return seg_play

    def play_ff_pulse(self, seg1 = None, seg2 = None, seg3 = None, dt_pulseplay = 5, case = 1):
        """
        Plays the fast flux pulse according to the specified configuration.

        This method plays a fast flux pulse based on the provided segments and configuration.
        The pulse is divided into three segments (seg1, seg2, seg3) and includes ramp-up and ramp-down phases.

        Parameters:
            seg1 (list or numpy array, optional): The first segment of the pulse, where the pulse is OFF. Default is None.
            seg2 (list or numpy array, optional): The second segment of the pulse, where the pulse is ON. Default is None.
            seg3 (list or numpy array, optional): The third segment of the pulse, where the pulse is OFF. Default is None.
            dt_pulseplay (float, optional): The time step (in microseconds) for playing the pulse. Default is 5.
            case (int, optional): The case number determining the pulse sequence.
                                  Case 1: Qubit tone is played before the fast flux pulse.
                                  Case 2 or 3: Fast flux pulse is played with the specified segments. Default is 1.

        Returns:
            None
        """
        # Get the gain register for the ff channel
        ff_ch_rp = self.ch_page(self.cfg["ff_ch"])
        ff_gain_reg = self.sreg(self.cfg["ff_ch"], "gain")

        # Case 1 : if the qubit tone is played before the fast flux pulse
        if case == 1:
            # Nothing to play technically
            pass

        if case == 2 or case == 3:
            # Play the ff pulse
            for i in range(len(seg1)):
                if i == 0 :
                    self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, stdysel='last',
                                             gain=int(seg1[i]), length=self.us2cycles(dt_pulseplay, gen_ch=self.cfg['ff_ch']))
                    self.pulse(ch=self.cfg["ff_ch"])

                else:
                    self.safe_regwi(ff_ch_rp, ff_gain_reg, int(seg1[i]))
                    self.pulse(ch=self.cfg["ff_ch"])

            # Play the ramp up
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                        gain=self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"])

            # Play seg2
            for i in range(len(seg2)):
                if i == 0 :
                    self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, stdysel='last',
                                             gain=int(seg2[i]), length=self.us2cycles(dt_pulseplay, gen_ch=self.cfg['ff_ch']))
                    self.pulse(ch=self.cfg["ff_ch"])
                else:
                    self.safe_regwi(ff_ch_rp, ff_gain_reg, int(seg2[i]))
                    self.pulse(ch=self.cfg["ff_ch"])

            # Play the ramp down
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                        gain=self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"])

            # Play seg3
            for i in range(len(seg3)):
                if i == 0 :
                    self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, stdysel='last',
                                             gain=int(seg3[i]), length=self.us2cycles(dt_pulseplay, gen_ch=self.cfg['ff_ch']))
                    self.pulse(ch=self.cfg["ff_ch"])

                else:
                    self.safe_regwi(ff_ch_rp, ff_gain_reg, int(seg3[i]))
                    self.pulse(ch=self.cfg["ff_ch"])

    def build_ff_pulse(self, dt_pulsedef = 0.25, dt_pulseplay = 5):
        """
        Build the fast flux pulse according to the configuration.

        This method generates a fast flux pulse waveform based on the configuration parameters. The pulse is divided into
        three segments:
        1. Pre-FF delay
        2. FF pulse
        3. Post-FF delay

        The pulse is constructed using small-time steps where the amplitude is constant. The method also handles
        pre-distortion of the waveform if enabled in the configuration.

        Parameters:
            dt_pulsedef (float, optional): Time step in microseconds for building the pulse. Default is 0.25.
            dt_pulseplay (float, optional): Time step in microseconds for playing the pulse. Default is 5.

        Raises:
            Exception: If `ff_pulse_style` is not "ramp".
            Exception: If `ff_ramp_length` is not defined in the configuration.
            Exception: If there are timing issues between the qubit and fast flux pulse.

        Returns:
            None
        """
        # CHECKING IF THE CONFIGURATION IS VALID
        if self.cfg["ff_pulse_style"] != "ramp":
            raise Exception("ff_pulse_style other than ramp not implemented in play_ff_pulse")
        self.cfg['ff_ramp_style'] = "linear"
        if 'ff_ramp_length' not in self.cfg.keys():
            raise Exception("ff_ramp_length nor defined in the config")

        # BUILDING THE PULSE
        if self.cfg.get("pulse_pre_dist", False):
            print("!!! WARNING: pulse pre-distortion is enabled. Make sure the pre-distortion parameters are set correctly. !!!")
            model = PulseFunctions.SimpleTwoTailDistortion(A1 = self.cfg.get("A1", -0.02),
                                                      tau1 = self.cfg.get("tau1", 17.9),
                                                      A2 = self.cfg.get("A2", 0.128),
                                                      tau2 = self.cfg.get("tau2", 417.5),
                                                      x_val = dt_pulsedef)

        # Case 1 : if the qubit tone is played before the fast flux pulse
        if self.cfg["qubit_spec_delay"] + self.qubit_pulse_length < self.cfg["pre_ff_delay"]:
            self.case = 1
            # No need to play the fast flux pulse yet and the pulse shape ends after the end of readout
            total_time = self.cfg['qubit_spec_delay'] + self.qubit_pulse_length + self.cfg["pre_meas_delay"] + self.cfg['read_length'] # in us
            pb = PulseFunctions.PulseBuilder(dt_pulsedef, total_time)
            waveform = pb.waveform()
            if self.cfg.get("pulse_pre_dist", False):
                waveform = model.predistort(waveform)
            # Save it as an object attribute
            self.seg1_play = None
            self.seg2_play = None
            self.seg3_play = None

        # Case 2 : if the qubit tone is played during the fast flux pulse
        elif (self.cfg["qubit_spec_delay"] + self.qubit_pulse_length >= self.cfg["pre_ff_delay"]  and
              self.cfg["qubit_spec_delay"] <= self.cfg["pre_ff_delay"] + self.cfg["ff_length"] + 2*self.cfg['ff_ramp_length']):

            self.case = 2

            # Play fast flux pulse only till the qubit pulse is done and pulse shape plays after the end of readout
            total_time = self.cfg['qubit_spec_delay'] + self.qubit_pulse_length + self.cfg["pre_meas_delay"] + self.cfg['read_length']
            pb = PulseFunctions.PulseBuilder(dt_pulsedef, total_time)
            # Some comments on the flat : It is set such that we dont need to play the full ff pulse if the qubit
            # pulse ends before that. If the qubit pulse is happening while the ff is being ramped up then we let the
            # ramping get finished, and we ramp down but the flat is zero A padding is added after the qubit pulse so
            # that the aliasing of the ff pulse does not create any timing issue.
            pb.add_trapezoid(start = self.cfg["pre_ff_delay"], rise = self.cfg["ff_ramp_length"],
                             flat = max(min(self.cfg["qubit_spec_delay"] + self.qubit_pulse_length + self.cfg['qubit_spec_buffer'] - (self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"]), self.cfg["ff_length"]),0),
                             fall = self.cfg["ff_ramp_length"], amp = self.cfg["ff_gain"])
            waveform = pb.waveform()

            # Pre distort the waveform
            if self.cfg.get("pulse_pre_dist", False):
                waveform = model.predistort(waveform)

            seg1_end = int(self.cfg["pre_ff_delay"]/dt_pulsedef)
            seg2_beg = int((self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"])/dt_pulsedef)
            seg2_end = int((max(min(self.cfg["qubit_spec_delay"] + self.qubit_pulse_length + self.cfg['qubit_spec_buffer'] - (self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"]), self.cfg["ff_length"]),0) + self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"] )/dt_pulsedef)
            seg3_beg = int((max(min(self.cfg["qubit_spec_delay"] + self.qubit_pulse_length + self.cfg['qubit_spec_buffer'] - (self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"]), self.cfg["ff_length"]),0) + self.cfg["pre_ff_delay"] + 2*self.cfg["ff_ramp_length"])/dt_pulsedef)
            seg1 = waveform[0:seg1_end]
            seg2 = waveform[seg2_beg:seg2_end]
            seg3 = waveform[seg3_beg:]

            # Creating the play segments
            seg1_play = self.create_avg_segs(seg1, dt_pulsedef, dt_pulseplay)
            seg2_play = self.create_avg_segs(seg2, dt_pulsedef, dt_pulseplay)
            seg3_play = self.create_avg_segs(seg3, dt_pulsedef, dt_pulseplay)

            # Add one more seg to seg3_pplay with value zero
            seg3_play = np.append(seg3_play, 0)

            # Save it as an object attribute
            self.seg1_play = seg1_play
            self.seg2_play = seg2_play
            self.seg3_play = seg3_play

            # Define the ff pulses
            self.cfg["ff_ramp_start"] = int(seg1_play[-1]) if len(seg1_play) >0 else 0
            self.cfg['ff_ramp_stop'] = int(seg2_play[0]) if len(seg2_play) >0 else self.cfg["ff_gain"]
            PulseFunctions.create_ff_ramp(self, reversed=False)
            self.cfg["ff_ramp_stop"] = int(seg2_play[-1]) if len(seg2_play) >0 else self.cfg["ff_gain"]
            self.cfg['ff_ramp_start'] = int(seg3_play[0]) if len(seg3_play) >0 else 0
            PulseFunctions.create_ff_ramp(self, reversed=True)

        # Case 3 : if the qubit tone is played after the fast flux pulse
        elif self.cfg["qubit_spec_delay"] > self.cfg["pre_ff_delay"] + self.cfg["ff_length"] + 2*self.cfg['ff_ramp_length']:
            self.case = 3

            # Play the full fast flux pulse ant the pulse shape plays after the end of readout
            total_time = self.cfg['qubit_spec_delay'] + self.qubit_pulse_length + self.cfg["pre_meas_delay"] + self.cfg['read_length']
            pb = PulseFunctions.PulseBuilder(dt_pulsedef, total_time)
            pb.add_trapezoid(start = self.cfg["pre_ff_delay"], rise = self.cfg["ff_ramp_length"],
                                flat = self.cfg["ff_length"] ,
                                fall = self.cfg["ff_ramp_length"], amp = self.cfg["ff_gain"])
            waveform = pb.waveform()
            if self.cfg.get("pulse_pre_dist", False):
                waveform = model.predistort(waveform)

            seg1_end = int(self.cfg["pre_ff_delay"]/dt_pulsedef) + 1
            seg2_beg = int((self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"])/dt_pulsedef) + 1
            seg2_end = int((self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"] + self.cfg["ff_length"])/dt_pulsedef) + 1
            seg3_beg = int((self.cfg["pre_ff_delay"] + self.cfg["ff_ramp_length"] + self.cfg["ff_length"] + self.cfg["ff_ramp_length"])/dt_pulsedef) + 1
            seg1 = waveform[0:seg1_end]
            seg2 = waveform[seg2_beg:seg2_end]
            seg3 = waveform[seg3_beg:]

            # Play the full ff pulse
            seg1_play = self.create_avg_segs(seg1, dt_pulsedef, dt_pulseplay)
            seg2_play = self.create_avg_segs(seg2, dt_pulsedef, dt_pulseplay)
            seg3_play = self.create_avg_segs(seg3, dt_pulsedef, dt_pulseplay)

            # Add one more seg to seg3_pplay with value zero
            seg3_play = np.append(seg3_play, 0)

            # Save it as an object attribute
            self.seg1_play = seg1_play
            self.seg2_play = seg2_play
            self.seg3_play = seg3_play

            # Adding one more seg to seg3_pplay with value zero
            seg3_play = np.append(seg3_play, 0)

            # Define the ff pulses
            self.cfg["ff_ramp_start"] = int(seg1_play[-1])
            self.cfg['ff_ramp_stop'] = int(seg2_play[0])
            PulseFunctions.create_ff_ramp(self, reversed=False)
            self.cfg["ff_ramp_stop"] = int(seg2_play[-1])
            self.cfg['ff_ramp_start'] = int(seg3_play[0])
            PulseFunctions.create_ff_ramp(self, reversed=True)

        else:
            raise Exception(f"Weird timing issue with the qubit and fast flux pulse.The timings are as follows "
                            f"- qubit_spec_delay : {self.cfg['qubit_spec_delay']} us, qubit pulse length : "
                            f"{self.qubit_pulse_length} us, pre_ff_delay : {self.cfg['pre_ff_delay']} us, ff_length :"
                            f" {self.cfg['ff_length']} us")
        if self.plot_debug:
            fig, ax = plt.subplots(figsize=(12, 12))
            # Plot the full waveform and pre-distorted waveform if applicable
            time_axis = pb.t
            ax.plot(time_axis, pb.waveform(), label="Ideal Fast flux pulse")
            if self.cfg.get("pulse_pre_dist", False):
                ax.plot(time_axis, waveform, label="Pre-distorted Fast flux pulse")
            ax.set_xlabel("Time (us)")
            ax.set_ylabel("Amplitude (DAC units)")
            ax.set_title("Fast flux pulse shape")
            ax.legend()
            plt.show(block=False)
            plt.pause(1)

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

        # Building the pulses
        self.build_ff_pulse(dt_pulsedef = self.cfg.get('dt_pulsedef', 0.002), dt_pulseplay = self.cfg.get('dt_pulseplay', 5))

        self.sync_all(self.us2cycles(10))



    def body(self):

        qubit_spec_delay_cycles = self.us2cycles(self.cfg["qubit_spec_delay"])
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])
        qubit_length_cycles = self.us2cycles(self.qubit_pulse_length)
        pre_meas_delay_cycles = self.us2cycles(self.cfg["pre_meas_delay"])
        read_after_cycle = self.us2cycles(self.cfg["qubit_spec_delay"]) + qubit_length_cycles + pre_meas_delay_cycles

        # Some sync time to let the code settle on the instructions (I havent seen this affect RFSOC, but suggested
        # by the documentation)
        self.sync_all(self.us2cycles(10))

        # play qubit spec pulse
        self.pulse(ch=self.cfg["qubit_ch"], t=qubit_spec_delay_cycles)

        # Measure the qubit
        # BEFORE RUNNING THIS MAKE SURE YOU HAVE CORRECTED THE BUG IN THE MEASURE QICK COMMAND
        # WHERE THE TRIGGER DOES NOT PLAY AT TIME T
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t=read_after_cycle, wait=False)

        # Play ff pulse ( Code it after the measure and qubit tone so that the RFSOC plays all pulses correctly. What
        # I have noticed is that in the other case the measure pulse is delayed dependent on how many pulses are
        # there in the RFSOC
        self.play_ff_pulse(seg1=self.seg1_play, seg2=self.seg2_play, seg3=self.seg3_play,
                           dt_pulseplay=self.cfg.get('dt_pulseplay', 5), case=self.case)


        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))



# ====================================================== #
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

class FFSpecSlice_Experiment_wPPD(ExperimentClass):
    """
    Perform qubit spectroscopy during a fast flux pulse.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress=False, debug=False, plot_debug = True):
        self.soc.reset_gens()
        prog = FFSpecSlice_wPPD(self.soccfg, self.cfg, plot_debug=plot_debug)

        if 'pre_meas_delay' not in self.cfg:
            self.cfg['pre_meas_delay'] = 2

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