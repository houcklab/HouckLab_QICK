###
# This file contains an NDAveragerProgram and ExperimentClass
# for ramping and then holding for some time and then ramping back down
# Parth, Sept 2025: create file.
###

import sys
from tqdm import tqdm
import matplotlib
from qick import NDAveragerProgram
from qick.averager_program import QickSweep
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2
import time

class mFFTransmission(NDAveragerProgram):
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

       The method also handles pre-distortion of the waveform if enabled in the configuration.

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
            # print(
            #     "!!! WARNING: pulse pre-distortion is enabled. Make sure the pre-distortion parameters are set correctly. !!!")
            # print("Using 1 tail distortion model with default parameters unless specified otherwise in the config.")
            model = PulseFunctions.SimpleSingleTailDistortion(A=self.cfg.get("A1", -0.00499),
                                                              tau=self.cfg.get("tau1", 50.6),
                                                              x_val=self.cfg.get("dt_pulsedef", 0.002))


        total_time = ( self.cfg["read_length"] + self.cfg['post_meas_delay'] + self.cfg["ff_ramp_length"] + self.cfg['pre_meas_delay'] + self.cfg["read_length"] +  self.cfg['post_meas_delay'] + self.cfg["ff_ramp_length"] )  # in us
        pb = PulseFunctions.PulseBuilder(dt_pulsedef, total_time)
        pb.add_trapezoid(
            start= self.cfg["read_length"] + self.cfg['post_meas_delay'],
            rise=self.cfg["ff_ramp_length"],
            flat=self.cfg['pre_meas_delay'] + self.cfg["scan_length"] + self.cfg['post_meas_delay'],
            fall=self.cfg["ff_ramp_length"], amp=self.cfg["ff_gain"])
        waveform = pb.waveform()

        # Apply pre-distortion if applicable
        if self.cfg.get("pulse_pre_dist", False):
            waveform = model.predistort(waveform)

        seg1_end = int((self.cfg["read_length"] + self.cfg['post_meas_delay']) / dt_pulsedef) + 1
        seg2_beg = int((self.cfg["read_length"] + self.cfg['post_meas_delay'] + self.cfg["ff_ramp_length"]) / dt_pulsedef) + 1
        seg2_end = int((self.cfg["read_length"] + self.cfg['post_meas_delay'] + self.cfg["ff_ramp_length"] + self.cfg['pre_meas_delay'] + self.cfg["scan_length"] + self.cfg['post_meas_delay']) / dt_pulsedef) + 1
        seg3_beg = int((self.cfg["read_length"] + self.cfg['post_meas_delay'] + self.cfg["ff_ramp_length"] + self.cfg['pre_meas_delay'] + self.cfg["scan_length"] + self.cfg["ff_ramp_length"] +  self.cfg['post_meas_delay']) / dt_pulsedef) + 1
        seg1 = waveform[0:seg1_end]
        seg2 = waveform[seg2_beg:seg2_end]
        seg3 = waveform[seg3_beg:]

        # Play the full ff pulse
        seg1_play = self.create_avg_segs(seg1, dt_pulsedef, dt_pulseplay)
        seg2_play = self.create_avg_segs(seg2, dt_pulsedef, dt_pulseplay)
        seg3_play = self.create_avg_segs(seg3, dt_pulsedef, dt_pulseplay)

        # Add one more seg to seg3_pplay with value zero
        # seg3_play = np.append(seg3_play, 0)

        # Save it as an object attribute
        self.seg1_play = seg1_play
        self.seg2_play = seg2_play
        self.seg3_play = seg3_play

        # Adding one more seg to seg3_pplay with value zero
        # seg3_play = np.append(seg3_play, 0)

        # Define the ff pulses
        self.cfg["ff_ramp_start"] = 0
        self.cfg['ff_ramp_stop'] = int(seg2_play[0])
        PulseFunctions.create_ff_ramp(self, reversed=False)
        self.cfg["ff_ramp_stop"] = int(seg2_play[-1])
        self.cfg['ff_ramp_start'] = 0
        PulseFunctions.create_ff_ramp(self, reversed=True)

        # Resetting the ff_ramp_start and ff_ramp_stop to original values
        self.cfg['ff_ramp_start'] = 0
        self.cfg['ff_ramp_stop'] = self.cfg['ff_gain']

        if self.cfg.get('zeroing_pulse', False) and self.cfg.get("pulse_pre_dist", False):
            x_pulse = waveform
            T_opt, amps, edges = model.design_single_tail_zeroing(x_pulse, a_max=self.cfg.get("zeroing_a_max", 30000))
            self.t_opt = T_opt
            # print("Zeroing pulse parameters:")
            # print(f"Optimal zeroing time: {T_opt} us")
            # print(f"Edges: {edges}")
            # print(f"Amplitudes: {amps}")
            self.length = edges[-1] - edges[-2]
            self.amps = amps

            # Making it plottable if needed
            taus = np.array([model.params.tau])
            t_zeroing = np.arange(0, T_opt + 100, model.dt)
            x_full = np.zeros_like(t_zeroing)
            x_full[:len(x_pulse)] = waveform

            for j in range(1):
                start_idx = int(round(edges[j] / model.dt))
                end_idx = int(round(edges[j + 1] / model.dt))
                x_full[start_idx:end_idx] = amps[j]

            y_full = model.simulate(x_full)

        # # Plotting the pulse with and without zeroing
        # fig, axs = plt.subplots(2, 1, figsize=(12, 12))
        # # Plot the full waveform and pre-distorted waveform if applicable
        # time_axis = pb.t
        # axs[0].plot(time_axis, pb.waveform(), label="Ideal Fast flux pulse")
        # if self.cfg.get("pulse_pre_dist", False):
        #     axs[0].plot(time_axis, waveform, label="Pre-distorted Fast flux pulse")
        # axs[0].set_xlabel("Time (us)")
        # axs[0].set_ylabel("Amplitude (DAC units)")
        # axs[0].set_title("Fast flux pulse shape")
        # axs[0].legend()
        #
        # # Plot y_full vs t_zeroing
        # if self.cfg.get('zeroing_pulse', False) and self.cfg.get("pulse_pre_dist", False):
        #     axs[1].plot(t_zeroing, y_full, label="Simulated Zeroing Pulse")
        #     axs[1].set_xlabel("Time (us)")
        #     axs[1].set_ylabel("Amplitude (DAC units)")
        #     axs[1].set_title("Zeroing Pulse Simulation")
        #     axs[1].legend()
        #
        # plt.tight_layout()
        # if self.save_loc is not None:
        #     plt.savefig(self.save_loc + "FF_pulse_shape.png")
        # if self.plot_debug:
        #     plt.show(block=False)
        #     plt.pause(1)
        # else:
        #     plt.close(fig)

    def initialize(self):
        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux

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

        # Qubit pulse
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        qubit_ch = self.cfg["qubit_ch"]  # Get the qubit channel
        self.declare_gen(ch=qubit_ch, nqz=self.cfg["qubit_nqz"])  # Declare the qubit channel
        qubit_freq = self.freq2reg(self.cfg["qubit_freq"], gen_ch=self.cfg["qubit_ch"])  # Convert qubit length to clock ticks
        self.qubit_freq = qubit_freq
        # Define the qubit pulse
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
        elif self.cfg["qubit_pulse_style"] == 'const':
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0,
                                     gain=self.cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]),
                                     mode="periodic")
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"])
        else:
            print("define arb or flat top pulse or const")

        # Building the pulses
        self.build_ff_pulse(dt_pulsedef=self.cfg.get('dt_pulsedef', 0.002),
                            dt_pulseplay=self.cfg.get('dt_pulseplay', 5))

        self.sync_all(self.us2cycles(1))

    def body(self):
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])
        read_length_cycles = self.us2cycles( self.cfg["read_length"] + self.cfg['post_meas_delay'] + self.cfg["ff_ramp_length"] + self.cfg["pre_meas_delay"])

        # self.pulse(ch=self.cfg["qubit_ch"])
        # for ch in self.cfg["ro_chs"]:
        #     self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
        #                          freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t=0, wait=False, syncdelay=None)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
        # Declare readout
        # for ch in self.cfg["ro_chs"]:
        #     self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["scan_length"], ro_ch=self.cfg["res_ch"]),
        #                          freq=self.cfg["scan_pulse_freq"], gen_ch=self.cfg["res_ch"])
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["scan_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["scan_pulse_gain"],
                                 length=self.us2cycles(self.cfg["scan_length"], gen_ch=self.cfg["ro_chs"][0]))
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t=read_length_cycles, wait=False, syncdelay=None)

        # Play the fast flux pulse
        # self.play_ff_pulse(self.seg1_play, self.seg2_play, self.seg3_play, dt_pulseplay=self.cfg.get('dt_pulseplay', 5))

        # self.sync_all(self.us2cycles(1))

        # Play the zeroing pulse if applicable
        # if self.cfg.get('zeroing_pulse', False):
        #     self.play_ff_zeroing_pulse(amps=getattr(self, 'amps', None), length=getattr(self, 'length', None))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    # Override acquire such that we can collect the single-shot data

    # def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None, save_experiments=None,
    #             start_src="internal", progress=False, debug=False):
    #
    #     super().acquire(soc, load_pulses=load_pulses, progress=progress) # qick update, debug=debug)
    #
    #     length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
    #     data = self.get_raw()
    #     shots_i0 = np.array(data)[0, :, 0, 0]/ length
    #     shots_q0 = np.array(data)[0, :, 0, 1]/ length
    #     shots_i1 = np.array(data)[0, :, 1, 0]/ length
    #     shots_q1 = np.array(data)[0, :, 1, 1]/ length
    #     i_0 = shots_i0
    #     i_1 = shots_i1
    #     q_0 = shots_q0
    #     q_1 = shots_q1
    #
    #     return i_0, i_1, q_0, q_1

    def acquire(self, soc, load_pulses=True, progress=True, **kwargs):
        ro_ch = self.cfg["ro_chs"][0]
        fs = self.soccfg['readouts'][ro_ch]['f_output']
        buf_maxlen = self.soccfg['readouts'][ro_ch]['buf_maxlen']

        herald_len = self.us2cycles(self.cfg["read_length"], ro_ch=ro_ch)
        scan_len = self.us2cycles(self.cfg["scan_length"], ro_ch=ro_ch)
        samples_per_rep = herald_len + scan_len
        print(f"Samples per rep: {samples_per_rep}, Buffer maxlen: {buf_maxlen}")

        n_total_shots = self.cfg["reps"]
        print(f"Total shots: {n_total_shots}")
        shots_per_batch = buf_maxlen // samples_per_rep
        print(f"Shots per batch: {shots_per_batch}")
        n_batches = int(np.ceil(n_total_shots / shots_per_batch))

        all_i_herald = []
        all_q_herald = []
        all_i_scan = []
        all_q_scan = []

        delta_f = self.cfg["scan_pulse_freq"] - self.cfg["read_pulse_freq"]
        t = np.arange(scan_len) / fs
        demod = np.exp(-1j * 2 * np.pi * delta_f * t)

        for batch in tqdm(range(n_batches), disable=not progress):
            self.cfg["reps"] = min(shots_per_batch,
                                   n_total_shots - batch * shots_per_batch)

            data = self.acquire_decimated(soc, rounds=1,
                                          load_envelopes=(batch == 0),
                                          progress=False)
            d = np.array(data)

            # Herald (read 0): NCO matched, integrate directly
            i_h = d[:, 0, :herald_len, 0].sum(axis=-1) / herald_len
            q_h = d[:, 0, :herald_len, 1].sum(axis=-1) / herald_len
            all_i_herald.append(i_h)
            all_q_herald.append(q_h)

            # Scan (read 1): software demodulate
            scan_complex = (d[:, 1, :scan_len, 0] + 1j * d[:, 1, :scan_len, 1]) * demod[np.newaxis, :]
            i_s = np.real(scan_complex).sum(axis=-1) / scan_len
            q_s = np.imag(scan_complex).sum(axis=-1) / scan_len
            all_i_scan.append(i_s)
            all_q_scan.append(q_s)

        # Restore original reps
        self.cfg["reps"] = n_total_shots

        return (np.concatenate(all_i_herald), np.concatenate(all_q_herald),
                np.concatenate(all_i_scan), np.concatenate(all_q_scan))
class FFTransmission_PS(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plot_predist=False):

        if 'pre_meas_delay' not in self.cfg.keys():
            self.cfg['pre_meas_delay'] = 1
        else:
            print(f"Pre Meas Delay = {self.cfg['pre_meas_delay']}")


        expt_cfg = {
                "center": self.cfg["read_pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / (expt_cfg["expts"]-1)
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        start = time.time()

        # Defining the variables to store all data
        i_0_arr = np.full((fpts.size, int(self.cfg["reps"])), np.nan)
        q_0_arr = np.full((fpts.size, int(self.cfg["reps"])), np.nan)
        i_1_arr = np.full((fpts.size, int(self.cfg["reps"])), np.nan)
        q_1_arr = np.full((fpts.size,  int(self.cfg["reps"])), np.nan)

        if self.cfg.get("pulse_pre_dist", False):
            print(
                "!!! WARNING: pulse pre-distortion is enabled. Make sure the pre-distortion parameters are set correctly. !!!")
        for indx in range(fpts.size):
            self.cfg["scan_pulse_freq"] = fpts[indx]
            prog = mFFTransmission(self.soccfg, self.cfg,save_loc=self.path_wDate + "_ff_predist.png", plot_debug=plot_predist)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True)

            i_0_arr[indx] = i_0
            q_0_arr[indx] = q_0
            i_1_arr[indx] = i_1
            q_1_arr[indx] = q_1
            # time.sleep(0.01) # Added to wait for the RFSOC to send all data
        if debug:
            print(f'Time: {time.time() - start}')

        self.cfg["scan_pulse_freq"] = expt_cfg["center"] # reset to original value
        data={'config': self.cfg, 'data': {'fpts':fpts, "i_0_arr" : i_0_arr, "q_0_arr": q_0_arr,
                                           "i_1_arr": i_1_arr, "q_1_arr": q_1_arr }}
        self.data=data
        return data

    def process(self, data=None, debug = False, **kwargs):
        i_0 = data["data"]["i_0_arr"]
        q_0 = data["data"]["q_0_arr"]
        i_1 = data["data"]["i_1_arr"]
        q_1 = data["data"]["q_1_arr"]
        fpts = data["data"]["fpts"]

        if "cen_num" in self.cfg:
            cen_num = self.cfg["cen_num"]
        else:
            cen_num = 2

        ### Create empty arrays to save data
        # start blob x end blob x qubit_gain_vec x qubit_freq_vec
        sig = np.zeros((cen_num, i_0.shape[0]), dtype=complex)
        centers = []

        for indx_gain in range(fpts.size):

            ### Perform post selection for the initial data for two centers
            ### by selecting points withing some confidence bound.
            iq_data_0 = np.stack((i_0[indx_gain, :], q_0[indx_gain, :]), axis=0)
            iq_data_1 = np.stack((i_1[indx_gain, :], q_1[indx_gain, :]), axis=0)

            if indx_gain == 0 :
                # Get centers
                centers.append(sse2.getCenters(iq_data_0, cen_num))
            else:
                centers.append(sse2.getCenters(iq_data_0, cen_num, init_guess=centers[0]))

            # Fit Gaussian
            if 'bin_size' in kwargs:
                bin_size = kwargs['bin_size']
            else:
                bin_size = 51
            hist2d = sse2.createHistogram(iq_data_0, bin_size)
            no_of_params = 4
            gaussians_0, popt, x_points_0, y_points_0 = sse2.findGaussians(hist2d, centers[indx_gain],
                                                                           cen_num)

            # create bounds given current fit
            bound = [popt - 1e-5, popt + 1e-5]

            for idx_bound in range(cen_num):
                bound[0][0 + int(idx_bound * no_of_params)] = 0
                bound[1][0 + int(idx_bound * no_of_params)] = np.inf

            # Get probability function
            pdf_0 = sse2.calcPDF(gaussians_0)

            # Calculate the probability
            probability = np.zeros((cen_num, iq_data_0.shape[1]))
            for i in range(cen_num):
                for j in range(iq_data_0.shape[1]):
                    # find the x,y point closest to the i,q point
                    indx_i = np.argmin(np.abs(x_points_0 - iq_data_0[0, j]))
                    indx_q = np.argmin(np.abs(y_points_0 - iq_data_0[1, j]))
                    # Calculate the probability
                    probability[i, j] = pdf_0[i][indx_i, indx_q]

            # Find the sorted data
            sorted_prob = np.zeros((cen_num, iq_data_0.shape[1]))
            sorted_data_0 = np.zeros((cen_num,) + iq_data_0.shape)
            sorted_data_1 = np.zeros((cen_num,) + iq_data_1.shape)

            for i in range(cen_num):
                sorted_indx = np.argsort(-probability[i, :])
                sorted_prob[i, :] = probability[i, sorted_indx]
                sorted_data_0[i, :, :] = iq_data_0[:, sorted_indx]
                sorted_data_1[i, :, :] = iq_data_1[:, sorted_indx]

            # Selecting the points in the confidence regime and calculating the populations
            if 'confidence' in kwargs:
                confidence = kwargs["confidence"]
            else:
                confidence = 0

            if debug and indx_gain == 0:
                fig,axs = plt.subplots(1,1, figsize=(12,6))
                sse2.plotFitAndData(pdf_0, gaussians_0, x_points_0, y_points_0, centers[indx_gain], iq_data_0, fig, axs)
                plt.show(block=False)


            # Calculating the signal given the confidence bound
            for i in range(cen_num):
                indx_confidence = np.argmin(np.abs(sorted_prob[i, :] - confidence))
                selected_data = sorted_data_1[i,:, :indx_confidence+1]
                sig[i, indx_gain] = np.mean(selected_data[0, :]) + 1j*np.mean(selected_data[1, :])

        update_data = {"data": {"pdf_0": pdf_0, "gaussians_0": gaussians_0, "x_points_0": x_points_0,
                                "y_points_0": y_points_0, "centers": centers, "sig_I": np.real(sig), "sig_Q": np.imag(sig)}}
        data["data"] = data["data"] | update_data["data"]
        self.data = data
        return data
    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        sig_I = data["data"]["sig_I"]
        sig_Q = data["data"]["sig_Q"]
        sig = sig_I + 1j*sig_Q
        fpts = data["data"]["fpts"]
        i_0_arr = data["data"]["i_0_arr"]
        q_0_arr = data["data"]["q_0_arr"]

        # Plot the magnitude of the signal if the qubit is in 0 or 1 state in two different subplots
        fig, axs = plt.subplots(2, 1, figsize=(12, 6), num=figNum)
        axs[0].plot(fpts, np.abs(sig[0, :]), label="Abs")
        axs[0].plot(fpts, np.real(sig[0, :]), label="I")
        axs[0].plot(fpts, np.imag(sig[0, :]), label="Q")
        axs[0].set_xlabel("Frequency (MHz)")
        axs[0].set_ylabel("Magnitude of signal (a.u.)")
        axs[0].set_title("Transmission vs Frequency (Qubit in 0 state)")
        axs[0].legend()
        axs[1].plot(fpts, np.abs(sig[1, :]), label="Qubit in 1 state")
        axs[1].plot(fpts, np.real(sig[1, :]), label="I")
        axs[1].plot(fpts, np.imag(sig[1, :]), label="Q")
        axs[1].set_xlabel("Frequency (MHz)")
        axs[1].set_ylabel("Magnitude of signal (a.u.)")
        axs[1].set_title("Transmission vs Frequency (Qubit in 1 state)")
        axs[1].legend()
        plt.tight_layout()
        plt.savefig(self.path_wDate + "_ff_transmission.png", dpi= 150)

        if plotDisp:
            plt.show(block=False)
            plt.pause(1)

        else:
            fig.clf(True)
            plt.close(fig)

        # Plot the raw I and Q data for the first measurement as a scatter plot for the first frequency point
        fig, ax = plt.subplots(figsize=(6, 6), num=figNum+1)
        ax.scatter(i_0_arr[0, :], q_0_arr[0, :], alpha=0.5)
        ax.set_xlabel("I (a.u.)")
        ax.set_ylabel("Q (a.u.)")
        ax.set_title("Raw I-Q data for first frequency point ")
        plt.tight_layout()
        plt.savefig(self.path_wDate + "_ff_transmission_ss_IQ.png", dpi= 150)
        if plotDisp:
            plt.show(block=False)
            plt.pause(1)
        else:
            fig.clf(True)
            plt.close(fig)

    #
    # def acquire_2d(self,
    #                sweep_key: str,
    #                sweep_values,
    #                live_plot: bool = True,
    #                plot_what: str = "mag",  # "mag", "I", or "Q" for the live image
    #                progress: bool = False,
    #                debug: bool = False):
    #     """
    #     Sweep transmission vs. readout frequency and one extra config parameter.
    #
    #     Parameters
    #     ----------
    #     sweep_key : str
    #         Name of the key in self.cfg to vary (e.g., "ff_amp", "read_pulse_gain", etc.).
    #     sweep_values : array-like
    #         Values to assign to self.cfg[sweep_key] for each outer slice.
    #     live_plot : bool
    #         If True, draws/updates a live 2D image after each slice.
    #     plot_what : {"mag","I","Q"}
    #         Which quantity to visualize live. Data always saved for all three.
    #     progress : bool
    #         Passed through to `acquire()` per slice.
    #     debug : bool
    #         Passed through to `acquire()` per slice.
    #
    #     Returns
    #     -------
    #     data2d : dict
    #         {
    #           "config": <final cfg snapshot>,
    #           "axes": {
    #               "sweep_key": <name>,
    #               "sweep_values": np.array([...]),
    #               "fpts": np.array([...]),  # in MHz (as in acquire)
    #               "x_ghz": np.array([...])  # GHz axis used in plots
    #           },
    #           "data": {
    #               "I": 2D np.array [n_slices, n_freq],
    #               "Q": 2D np.array [n_slices, n_freq],
    #               "mag": 2D np.array [n_slices, n_freq],
    #               "peak_freqs": 1D np.array [n_slices],  # MHz
    #           }
    #         }
    #     """
    #
    #     import numpy as np
    #     import matplotlib.pyplot as plt
    #     import time
    #
    #     # Validate plot_what
    #     plot_what = plot_what.lower()
    #     if plot_what not in ("mag", "i", "q"):
    #         plot_what = "mag"
    #
    #     # Preserve original value to restore at the end
    #     _had_key = sweep_key in self.cfg
    #     _orig_val = self.cfg.get(sweep_key, None)
    #
    #     sweep_values = np.array(list(sweep_values))
    #     n_slices = len(sweep_values)
    #
    #     # Run the first slice to discover frequency grid size and set up arrays/plot.
    #     self.cfg[sweep_key] = sweep_values[0]
    #     first = self.acquire(progress=progress, debug=debug)
    #     fpts = np.array(first["data"]["fpts"])                      # MHz
    #     x_ghz = (fpts + self.cfg.get("cavity_LO", 0.0)/1e6) / 1e3   # GHz, matching your display()
    #     n_freq = fpts.size
    #
    #     # Allocate 2D arrays
    #     I2d   = np.zeros((n_slices, n_freq), dtype=float)
    #     Q2d   = np.zeros((n_slices, n_freq), dtype=float)
    #     Mag2d = np.zeros((n_slices, n_freq), dtype=float)
    #     peaks = np.zeros((n_slices,), dtype=float)
    #
    #     # Fill row 0 from the first slice
    #     I2d[0, :]   = np.array(first["data"]["avgi"])
    #     Q2d[0, :]   = np.array(first["data"]["avgq"])
    #     Mag2d[0, :] = np.array(first["data"]["amp0"])
    #     peaks[0]    = float(first["data"]["peak_freq"])
    #
    #     # Set up live plot
    #     fig, ax, im, cbar = None, None, None, None
    #     if live_plot:
    #         plt.ion()
    #         fig, ax = plt.subplots()
    #         ax.set_xlabel("Cavity Frequency (GHz)")
    #         ax.set_ylabel(sweep_key)
    #         # ax.set_yticks(np.arange(n_slices))
    #         # ax.set_yticklabels([f"{v}" for v in sweep_values])
    #         ax.set_title(f"Live transmission vs freq × {sweep_key}  (Averages={self.cfg.get('reps','?')})")
    #
    #         def _pick_field():
    #             return {"mag": Mag2d, "i": I2d, "q": Q2d}[plot_what]
    #
    #         data_for_plot = _pick_field()
    #         # Use extent so the x-axis is in GHz and y is slice index (we label ticks with sweep_values)
    #         im = ax.imshow(data_for_plot,
    #                        aspect="auto",
    #                        origin="lower",
    #                        extent=(x_ghz.min(), x_ghz.max(), sweep_values[0], sweep_values[-1]),)
    #         cbar = fig.colorbar(im, ax=ax, label={"mag": "|IQ| (a.u.)", "i": "I (a.u.)", "q": "Q (a.u.)"}[plot_what])
    #         fig.tight_layout()
    #         fig.canvas.draw(); fig.canvas.flush_events()
    #         time.sleep(2)
    #
    #     # Process remaining slices
    #     for i in range(1, n_slices):
    #         self.cfg[sweep_key] = sweep_values[i]
    #         d = self.acquire(progress=progress, debug=debug)
    #
    #         I2d[i, :]   = np.array(d["data"]["avgi"])
    #         Q2d[i, :]   = np.array(d["data"]["avgq"])
    #         Mag2d[i, :] = np.array(d["data"]["amp0"])
    #         peaks[i]    = float(d["data"]["peak_freq"])
    #
    #         if live_plot:
    #             # Update the displayed matrix only up to the current row (optional but visually clearer)
    #             if plot_what == "mag":
    #                 current = Mag2d.copy()
    #             elif plot_what == "i":
    #                 current = I2d.copy()
    #             else:
    #                 current = Q2d.copy()
    #
    #             # Optionally mask unfilled rows to keep color scale sane
    #             if i < n_slices - 1:
    #                 current[i+1:, :] = np.nan
    #
    #             im.set_data(current)
    #             # Autoscale color limits on the filled portion to keep contrast decent
    #             finite_vals = current[np.isfinite(current)]
    #             if finite_vals.size:
    #                 im.set_clim(np.nanpercentile(finite_vals, 2), np.nanpercentile(finite_vals, 98))
    #             fig.canvas.draw(); fig.canvas.flush_events()
    #             time.sleep(2)
    #
    #     # Build return object (and stash on self)
    #     data2d = {
    #         "config": dict(self.cfg),
    #         "axes": {
    #             "sweep_key": sweep_key,
    #             "sweep_values": sweep_values,
    #             "fpts": fpts,
    #             "x_ghz": x_ghz
    #         },
    #         "data": {
    #             "I": I2d,
    #             "Q": Q2d,
    #             "mag": Mag2d,
    #             "peak_freqs": peaks
    #         }
    #     }
    #     self.data2d = data2d
    #
    #     # Restore original cfg value for cleanliness
    #     if _had_key:
    #         self.cfg[sweep_key] = _orig_val
    #     else:
    #         self.cfg.pop(sweep_key, None)
    #
    #     return data2d


    def save_data(self, data=None):
        # print(f'Saving {self.fname}')
        super().save_data(data=data['data'])



