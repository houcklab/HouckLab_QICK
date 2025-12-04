###
# This file contains an NDAveragerProgram and ExperimentClass
# for ramping and then holding for some time and then ramping back down
# Parth, Sept 2025: create file.
###

import sys

import matplotlib
from qick import NDAveragerProgram
from qick.averager_program import QickSweep
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import PulseFunctions


class FFRampHoldPopTest(NDAveragerProgram):
    def __init__(self, soccfg, cfg, save_loc=None, plot_debug=True):
        self.plot_debug = plot_debug
        self.save_loc = save_loc
        super().__init__(soccfg, cfg)

    def create_avg_segs(self, seg, dt_pulsedef=0.25, dt_pulseplay=10):
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
        if len(seg) == 0:  # Making sure that empty segments dont return Nan values but just empty lists
            return []
        points_per_play_step = int(dt_pulseplay / dt_pulsedef)
        num_play_steps = int(len(seg) / points_per_play_step)
        if num_play_steps == 0:  # If number of steps is zero given segment is non zero implies that dt_pulseplay >
            # length of seg
            num_play_steps = 1
        seg_play = np.zeros(num_play_steps)
        for i in range(num_play_steps):
            seg_play[i] = np.mean(seg[i * points_per_play_step:(i + 1) * points_per_play_step])
        return seg_play

    def play_ff_pulse(self, seg1=None, seg2=None, seg3=None, dt_pulseplay=5):
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

        # Play the ff pulse
        for i in range(len(seg1)):
            if i == 0:
                self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, stdysel='last',
                                         gain=int(seg1[i]),
                                         length=self.us2cycles(dt_pulseplay, gen_ch=self.cfg['ff_ch']))
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
            if i == 0:
                self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, stdysel='last',
                                         gain=int(seg2[i]),
                                         length=self.us2cycles(dt_pulseplay, gen_ch=self.cfg['ff_ch']))
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
            if i == 0:
                self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, stdysel='last',
                                         gain=int(seg3[i]),
                                         length=self.us2cycles(dt_pulseplay, gen_ch=self.cfg['ff_ch']))
                self.pulse(ch=self.cfg["ff_ch"])

            else:
                self.safe_regwi(ff_ch_rp, ff_gain_reg, int(seg3[i]))
                self.pulse(ch=self.cfg["ff_ch"])

    def play_ff_zeroing_pulse(self, amps = None, length = None):
        """
        Plays the fast flux zeroing pulse based on the provided amplitudes and length.

        This method plays a zeroing pulse for the fast flux channel. The zeroing pulse is used to
        counteract any residual effects of the fast flux pulse. The pulse is played in segments, with each segment
        having a specified amplitude and duration.

        Parameters:
            amps (list or numpy array, optional): A list of amplitudes for the zeroing pulse segments. Each amplitude
                                                  corresponds to a segment of the pulse. Default is None.
            length (float, optional): The duration (in microseconds) of each segment of the zeroing pulse. If not
                                      provided, the method does not play the pulse. Default is None.

        Returns:
            None
        """
        # Get the gain register for the ff channel
        ff_ch_rp = self.ch_page(self.cfg["ff_ch"])
        ff_gain_reg = self.sreg(self.cfg["ff_ch"], "gain")

        if self.cfg.get('zeroing_pulse', False) and amps is not None and length is not None:
            # Play the zeroing pulse
            ts = self.get_timestamp(gen_ch=self.cfg['ff_ch'])
            length = max(length, 0.05)
            max_length = min(self.us2cycles(1, gen_ch=self.cfg['ff_ch']),
                             self.us2cycles(length, gen_ch=self.cfg['ff_ch']))
            for i in range(len(amps)):
                if i == 0:
                    self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, stdysel='last',
                                             gain=int(amps[i]), length=max_length)
                    self.pulse(ch=self.cfg["ff_ch"], t=ts)
                else:
                    self.safe_regwi(ff_ch_rp, ff_gain_reg, int(amps[i]))
                    self.pulse(ch=self.cfg["ff_ch"], t=ts)
                ts = ts + self.us2cycles(length)
            self.safe_regwi(ff_ch_rp, ff_gain_reg, int(0))
            self.pulse(ch=self.cfg["ff_ch"], t=ts)

    def build_ff_pulse(self, dt_pulsedef=0.25, dt_pulseplay=5):
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

        self.cfg['ff_ramp_style'] = "linear"
        if 'ff_ramp_length' not in self.cfg.keys():
            raise Exception("ff_ramp_length nor defined in the config")

        # Saving ff_ramp_stop
        self.cfg['ff_gain'] = self.cfg['ff_ramp_stop']

        # BUILDING THE PULSE
        if self.cfg.get("pulse_pre_dist", False):
            print(
                "!!! WARNING: pulse pre-distortion is enabled. Make sure the pre-distortion parameters are set correctly. !!!")
            model = PulseFunctions.SimpleFourTailDistortion(A1 = self.cfg.get("A1", -0.02),
                                                      tau1 = self.cfg.get("tau1", 17.9),
                                                      A2 = self.cfg.get("A2", 0.128),
                                                      tau2 = self.cfg.get("tau2", 417.5),
                                                      A3=self.cfg.get("A3", 0.0608),
                                                      tau3=self.cfg.get("tau3", 6850.47),
                                                      A4 = self.cfg.get("A4", -0.0269),
                                                      tau4 = self.cfg.get("tau4", 1076.0),
                                                      x_val = dt_pulsedef)

        total_time = (self.cfg["qubit_length"] + self.cfg["pre_meas_delay"] + self.cfg["read_length"]
                      + self.cfg['relax_delay_1'] + self.cfg["ff_ramp_length"] + self.cfg["ff_hold"] + self.cfg[
                          'pop_pulse_length'] + self.cfg['pop_relax_delay']
                      + self.cfg["ff_ramp_length"] + self.cfg['pre_meas_delay'] + self.cfg["read_length"] + 3*dt_pulseplay)  # in us
        pb = PulseFunctions.PulseBuilder(dt_pulsedef, total_time)
        pb.add_trapezoid(
            start=self.cfg["qubit_length"] + self.cfg["pre_meas_delay"] + self.cfg["read_length"] + self.cfg[
                'relax_delay_1'],
            rise=self.cfg["ff_ramp_length"],
            flat=self.cfg["ff_hold"] + self.cfg['pop_pulse_length'] + self.cfg['pop_relax_delay'],
            fall=self.cfg["ff_ramp_length"], amp=self.cfg["ff_gain"])
        waveform = pb.waveform()

        # Apply pre-distortion if applicable
        if self.cfg.get("pulse_pre_dist", False):
            waveform = model.predistort(waveform)

        seg1_end = int((self.cfg["qubit_length"] + self.cfg["pre_meas_delay"] + self.cfg["read_length"]
                        + self.cfg['relax_delay_1']) / dt_pulsedef) + 1
        seg2_beg = int((self.cfg["qubit_length"] + self.cfg["pre_meas_delay"] + self.cfg["read_length"]
                        + self.cfg['relax_delay_1'] + self.cfg["ff_ramp_length"]) / dt_pulsedef) + 1
        seg2_end = int((self.cfg["qubit_length"] + self.cfg["pre_meas_delay"] + self.cfg["read_length"]
                        + self.cfg['relax_delay_1'] + self.cfg["ff_ramp_length"] + self.cfg["ff_hold"]
                        + self.cfg['pop_pulse_length'] + self.cfg['pop_relax_delay']) / dt_pulsedef) + 1
        seg3_beg = int((self.cfg["qubit_length"] + self.cfg["pre_meas_delay"] + self.cfg["read_length"]
                        + self.cfg['relax_delay_1'] + self.cfg["ff_ramp_length"] + self.cfg["ff_hold"]
                        + self.cfg['pop_pulse_length'] + self.cfg['pop_relax_delay']
                        + self.cfg["ff_ramp_length"]) / dt_pulsedef) + 1
        seg1 = waveform[0:seg1_end]
        seg2 = waveform[seg2_beg:seg2_end]
        seg3 = waveform[seg3_beg:]

        # Play the full ff pulse
        seg1_play = self.create_avg_segs(seg1, dt_pulsedef, dt_pulseplay)
        seg2_play = self.create_avg_segs(seg2, dt_pulsedef, dt_pulseplay)
        seg3_play = self.create_avg_segs(seg3, dt_pulsedef, dt_pulseplay)

        # # Add one more seg to seg3_pplay with value zero
        if not self.cfg.get("zeroing_pulse", False):
            seg3_play = np.append(seg3_play, 0)

        # Save it as an object attribute
        self.seg1_play = seg1_play
        self.seg2_play = seg2_play
        self.seg3_play = seg3_play

        # Adding one more seg to seg3_pplay with value zero
        # seg3_play = np.append(seg3_play, 0)

        # Define the ff pulses
        self.cfg["ff_ramp_start"] = int(seg1_play[-1])
        self.cfg['ff_ramp_stop'] = int(seg2_play[0])
        PulseFunctions.create_ff_ramp(self, reversed=False)
        self.cfg["ff_ramp_stop"] = int(seg2_play[-1])
        self.cfg['ff_ramp_start'] = int(seg3_play[0])
        PulseFunctions.create_ff_ramp(self, reversed=True)

        # Resetting the ff_ramp_start and ff_ramp_stop to original values
        self.cfg['ff_ramp_start'] = 0
        self.cfg['ff_ramp_stop'] = self.cfg['ff_gain']

        if self.cfg.get('zeroing_pulse', False) and self.cfg.get("pulse_pre_dist", False):
            x_pulse = waveform
            T_opt, amps, edges = model.design_four_tail_zeroing_with_amax(x_pulse, a_max=self.cfg.get("zeroing_a_max", 30000))
            self.t_opt = T_opt
            # print("Zeroing pulse parameters:")
            print(f"Optimal zeroing time: {T_opt} us")
            # print(f"Edges: {edges}")
            # print(f"Amplitudes: {amps}")
            self.length = edges[-1] - edges[-2]
            self.amps = amps

            # Making it plottable if needed
            taus = np.array([model.params.tau1, model.params.tau2, model.params.tau3, model.params.tau4])
            t_zeroing = np.arange(0, T_opt + 100, model.dt)
            x_full = np.zeros_like(t_zeroing)
            x_full[:len(x_pulse)] = waveform

            for j in range(4):
                start_idx = int(round(edges[j] / model.dt))
                end_idx = int(round(edges[j + 1] / model.dt))
                x_full[start_idx:end_idx] = amps[j]

            y_full = model.simulate(x_full)

        # Plotting the pulse with and without zeroing
        fig, axs = plt.subplots(2, 1, figsize=(12, 12))
        # Plot the full waveform and pre-distorted waveform if applicable
        time_axis = pb.t
        axs[0].plot(time_axis, pb.waveform(), label="Ideal Fast flux pulse")
        if self.cfg.get("pulse_pre_dist", False):
            axs[0].plot(time_axis, waveform, label="Pre-distorted Fast flux pulse")
        axs[0].set_xlabel("Time (us)")
        axs[0].set_ylabel("Amplitude (DAC units)")
        axs[0].set_title("Fast flux pulse shape")
        axs[0].legend()

        # Plot y_full vs t_zeroing
        if self.cfg.get('zeroing_pulse', False) and self.cfg.get("pulse_pre_dist", False):
            axs[1].plot(t_zeroing, y_full, label="Simulated Zeroing Pulse")
            axs[1].set_xlabel("Time (us)")
            axs[1].set_ylabel("Amplitude (DAC units)")
            axs[1].set_title("Zeroing Pulse Simulation")
            axs[1].legend()

        plt.tight_layout()
        if self.save_loc is not None:
            plt.savefig(self.save_loc + "FF_pulse_shape.png")
        if self.plot_debug:
            plt.show(block=False)
            plt.pause(1)
        else:
            plt.close(fig)

    def initialize(self):
        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])
        PulseFunctions.create_qubit_pulse(self, self.cfg["qubit_freq"])

        # Declare readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Readout pulse
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))

        if 'pre_meas_delay' not in self.cfg.keys():
            self.cfg['pre_meas_delay'] = 1
        else:
            print(f"Pre Meas Delay = {self.cfg['pre_meas_delay']}")

        # Building the pulses
        self.build_ff_pulse(dt_pulsedef=self.cfg.get('dt_pulsedef', 0.002),
                            dt_pulseplay=self.cfg.get('dt_pulseplay', 5))

        self.sync_all(self.us2cycles(10))

    def body(self):
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])
        read1_length_cycles = self.us2cycles(self.cfg["qubit_length"] + self.cfg["pre_meas_delay"])
        read2_length_cycles = self.us2cycles(self.cfg["qubit_length"] + self.cfg["pre_meas_delay"]
                                             + self.cfg["read_length"] + self.cfg['relax_delay_1']
                                             + self.cfg["ff_ramp_length"] + self.cfg["ff_hold"]
                                             + self.cfg['pop_pulse_length'] + self.cfg['pop_relax_delay']
                                             + self.cfg["ff_ramp_length"] + self.cfg['pre_meas_delay'])
        pop_length_cycles = self.us2cycles(self.cfg["qubit_length"] + self.cfg["pre_meas_delay"]
                                           + self.cfg["read_length"] + self.cfg['relax_delay_1']
                                           + self.cfg["ff_ramp_length"] + self.cfg["ff_hold"])

        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t=read1_length_cycles, wait=False, syncdelay=None)

        # Play the populating pulse
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["pop_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["pop_pulse_gain"],
                                 length=self.us2cycles(self.cfg["pop_pulse_length"], gen_ch=self.cfg["ro_chs"][0]))
        self.pulse(ch=self.cfg["res_ch"], t=pop_length_cycles)

        # trigger measurement, play measurement pulse, wait for relax_delay_2. Once per experiment.
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t=read2_length_cycles, wait=False, syncdelay=None)

        # Play the fast flux pulse
        self.play_ff_pulse(self.seg1_play, self.seg2_play, self.seg3_play, dt_pulseplay=self.cfg.get('dt_pulseplay', 5))

        self.sync_all(self.us2cycles(1))

        # Play the zeroing pulse if applicable
        if self.cfg.get('zeroing_pulse', False):
            self.play_ff_zeroing_pulse(amps=getattr(self, 'amps', None), length=getattr(self, 'length', None))

        self.sync_all(self.us2cycles(self.cfg["relax_delay_2"]))

    # Override acquire such that we can collect the single-shot data
    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None,
                save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress)  # qick update, debug=debug)

        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        data = self.get_raw()
        shots_i0 = np.array(data)[0, :, 0, 0] / length
        shots_q0 = np.array(data)[0, :, 0, 1] / length
        shots_i1 = np.array(data)[0, :, 1, 0] / length
        shots_q1 = np.array(data)[0, :, 1, 1] / length
        i_0 = shots_i0
        i_1 = shots_i1
        q_0 = shots_q0
        q_1 = shots_q1

        return i_0, i_1, q_0, q_1


if __name__ == '__main__':
    from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *

    print("Running the Ramp - Hold - DeRamp Test")
    soc, soccfg = makeProxy()
    soc.reset_gens()

    SwitchConfig = {
        "trig_buffer_start": 0.05,  # 0.035, # in us
        "trig_buffer_end": 0.04,  # 0.024, # in us
        "trig_delay": 0.07,  # in us
    }

    BaseConfig = BaseConfig | SwitchConfig

    outerFolder = r"Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

    UpdateConfig = {
        # Readout section
        "read_pulse_style": "const",  # --Fixed
        "read_length": 20,  # [us]
        "read_pulse_gain": 30000,  # 5600,  # [DAC units]
        "read_pulse_freq": 6671.71,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "linear",  # one of ["linear"]
        "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": -32000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_hold": 50,  # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
        "ff_ramp_length": 2,  # [us] Half-length of ramp to use when sweeping gain

        # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
        "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 512,  # [MHz] Frequency of qubit pulse
        "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.50,  # [us], used with "arb" and "flat_top"
        "qubit_length": 0.5,  # [us], used with "const"
        "flat_top_length": 1,  # [us], used with "flat_top"
        "qubit_gain": 1000,  # [DAC units]

        # Ramp sweep parameters
        "yokoVoltage": -0.115,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 0.1,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
        "relax_delay_2": 10 - BaseConfig["adc_trig_offset"],  # [us] Relax delay after second readout

        # General parameters
        "reps": 100,
    }

    config = BaseConfig | UpdateConfig

    prog = FFRampHoldPopTest(soccfg, config)

    try:
        a, b, c, d = prog.acquire(soc, threshold=None, angle=None, load_pulses=True, save_experiments=None,
                                  start_src="internal", progress=True)
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))

    print(a.shape)
