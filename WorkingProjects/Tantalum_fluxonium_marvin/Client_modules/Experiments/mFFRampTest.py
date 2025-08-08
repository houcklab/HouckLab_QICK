###
# This file contains an NDAveragerProgram and ExperimentClass for testing the ramp speed of a fast flux pulse.
# The qubit is measured at some flux point, then, the flux is moved with a variable-time (linear) ramp to a different point.
# The qubit is then moved back to the original point and measured again.
# For the fluxonium experiment, the speed conditions are:
# * slower than any crossings (adiabatic), as well as the energy spliting between g and e. (speed compares to these squared)
# * faster than any decoherence channels
# Lev, June 2025: create file.
###
from qick import NDAveragerProgram

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions

class FFRampTest(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux
        # There is no qubit pulse

        # Declare readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Readout pulse
        # 'periodic' would not make sense for this experiment
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"], #mode="oneshot",
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))

        # Define the fast flux ramp. For now, just linear ramp is supported
        if self.cfg["ff_ramp_style"] == "linear":
            PulseFunctions.create_ff_ramp(self, reversed = False)
            PulseFunctions.create_ff_ramp(self, reversed = True)
        else:
            print("Need an ff_ramp_style! only \"linear\" supported at the moment.")

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        """
        Measures at original flux spot, plays ff ramp to second flux spot, waits, plays reversed ff ramp, measures.
        NOTE: each measurement actually takes read_length + adc_trig_offset time, since the reading starts after the
        pulse and we are waiting for the measurement to finish before starting the next pulse. For now, let's just
        account for this by subtracting adc_trig_offset from the desired delay. If we end up wanting a delay less than
        the trigger offset, we can set wait to False and stop synching all channels, but this likely won't be necessary,
        as we probably want to wait for the cavity to ring down before starting the ramp.
        :return:
        """
        #TODO this doesn't really make sense as written, it would only really work for starting ramp from 0
        #TODO optional qubit pi/2 pulse before experiment?
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"]) # Do NOT include channel, it's wrong!

        # trigger measurement, play measurement pulse, wait for relax_delay_1
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     wait = True, #t = 0,
                     syncdelay=self.us2cycles(self.cfg["relax_delay_1"], gen_ch=self.cfg["res_ch"]))


        self.sync_all(self.us2cycles(0.01)) # Wait for a few ns to align channels

        # play fast flux ramp
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"])

        # play constant pulse to keep FF at ramped value if a delay here is desired
        if self.cfg["ff_delay"] > 0:
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, gain = self.cfg["ff_ramp_stop"],
                                     length = self.us2cycles(self.cfg["ff_delay"], gen_ch=self.cfg["ff_ch"]))
            self.pulse(ch = self.cfg["ff_ch"])

        # play reversed fast flux ramp, return to original spot
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"])

        self.sync_all(self.us2cycles(0.01)) # Wait for a few ns to align channels

        # trigger measurement, play measurement pulse, wait for relax_delay_2
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t = 0, wait = True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay_2"]))


    # Override acquire such that we can collect the single-shot data
    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress) # qick update, debug=debug)

        # self.get_raw() has data in format (#channels, #reps, #measurements/expt, 2)
        # self.di/q_buf[0] have (rep1_meas1, rep1_meas2, ... rep1_measN, rep1_meas1, ...)
        # reshape to have [[rep1_meas1, rep1_meas2], [rep2_meas1, rep2_meas2], ...]
        # di_buf and dq_buf are total integration, divide out readout time
        return (self.di_buf[0].reshape(-1, 2) / self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0]),
                self.dq_buf[0].reshape(-1, 2) / self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0]))

    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section
        "read_pulse_style": "linear",  # --Fixed
        "read_length": 5,  # [us]
        "read_pulse_gain": 8000,  # [DAC units]
        "read_pulse_freq": 7392.25,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "const",  # one of ["linear"]
        "ff_ramp_start": 0, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": 100, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 1, # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

        # Sweep parameters
        "ff_ramp_length_start": 1,  # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 5,  # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_expts": 10, # [int] Number of points in the ff ramp length sweep

        "yokoVoltage": 0,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 10,  # [us] Relax delay after first readout
        "relax_delay_2": 10, # [us] Relax delay after second readout
        "reps": 1000,
        "sets": 5,

        "angle": None, # [radians] Angle of rotation for readout
        "threshold": None, # [DAC units] Threshold between g and e
    }



class FFRampTest_Experiment(ExperimentClass):
    """
    Requires a readout calibration (angle + threshold) to be calculated before.
    We will not use thresholded readout, however, and store the full i/q data, in case we want to analyse it in a
    different way later.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress=False, debug=False):
        ramp_lengths = np.linspace(self.cfg["ff_ramp_length_start"], self.cfg["ff_ramp_length_stop"],
                                   num = self.cfg["ff_ramp_expts"])
        i_arr = np.zeros((self.cfg["ff_ramp_expts"], self.cfg["reps"], 2))
        q_arr = np.zeros((self.cfg["ff_ramp_expts"], self.cfg["reps"], 2))

        # Loop over different ramp lengths. This cannot be done inside an experiment, since we must recompile pulses
        for idx, length in enumerate(ramp_lengths):
            prog = FFRampTest(self.soccfg, self.cfg | {"ff_ramp_length": length})

            # Collect the data
            i_arr[idx], q_arr[idx] = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                                  save_experiments=None, #readouts_per_experiment=2,
                                                  start_src="internal", progress=progress)

        data = {'config': self.cfg, 'data': {'ramp_lengths': ramp_lengths, 'i_arr': i_arr, 'q_arr': q_arr}}
        self.data = data

        return data

    def display(self, data=None, plot_disp = True, plot_all_delays = False, fig_num = 1, **kwargs):

        if data is None:
            data = self.data

        # Dimensions: (# delay points, # reps, # measurement[before/after ramp])
        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']
        ramp_lengths = data['data']['ramp_lengths']

        # If angle and threshold are not given, fit them from the data. Uses first measurement for lowest delay value
        if self.cfg["angle"] is None or self.cfg["threshold"] is None: # Both must be given to be valid
            import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.Shot_Analysis.shot_analysis as shot_analysis
            ssa = shot_analysis.SingleShotAnalysis(i_arr[0, :, 0], q_arr[0, :, 0])
            ssa_centers = ssa.get_Centers(i_arr[0, :, 0], q_arr[0, :, 0])
            # We rotate to undo the current rotation, so - sign
            theta = -np.arctan((ssa_centers[1, 1] - ssa_centers[0, 1]) / (ssa_centers[1, 0] - ssa_centers[0, 0]))
            # Threshold is the rotated i-coordinate of the midpoint between the two blobs centres (sigmas are the same)
            threshold = (ssa_centers[0, 0] + ssa_centers[1, 0]) / 2 * np.cos(-theta) - \
                        (ssa_centers[0, 1] + ssa_centers[1, 1]) / 2 * np.sin(-theta)

        else: # User has provided override values
            theta = self.cfg["angle"]
            threshold = self.cfg["threshold"]

        # Histogram of original data for one of the delay points
        X, Y, hist2d = FFRampTest_Experiment._prepare_hist_data(i_arr[0, :, 0], q_arr[0, :, 0])

        # Make the plot
        while plt.fignum_exists(num=fig_num): ###account for if figure with number already exists
            fig_num += 1
        fig = plt.figure(figsize=(12, 12), num=fig_num)
        ax1 = plt.subplot(2, 2, 1)
        plt.pcolor(X, Y, hist2d[0])
        if self.cfg["angle"] is None or self.cfg["threshold"] is None:
            plt.scatter(ssa_centers[:, 0], ssa_centers[:, 1], color = 'r', marker = 'x')
        plt.xlabel('I (DAC units)')
        plt.ylabel('Q (DAC units)')
        plt.title('Raw I/Q data, smallest delay, before ramp')
        plt.colorbar()
        ax1.set_aspect('equal')

        # Rotate the data. Positive angle rotates ccw
        i_arr_rot = i_arr * np.cos(theta) - q_arr * np.sin(theta)
        q_arr_rot = i_arr * np.sin(theta) + q_arr * np.cos(theta)

        # Threshold; the data has been rotated such that the signal is in e
        data_thresh = i_arr_rot > threshold

        # Scatter plot of rotated data, with colour set by threshold. For now, plot only first delay value
        ax2 = plt.subplot(2, 2, 2)
        plt.scatter(i_arr_rot[0, :, 0][data_thresh[0, :, 0]], q_arr_rot[0, :, 0][data_thresh[0, :, 0]],
                    color = 'r', marker = 'o', alpha = 0.5)
        plt.scatter(i_arr_rot[0, :, 0][~data_thresh[0, :, 0]], q_arr_rot[0, :, 0][~data_thresh[0, :, 0]],
                    color = 'b', marker = 'o', alpha = 0.5)
        plt.xlabel('I (DAC units)')
        plt.ylabel('Q (DAC units)')
        plt.title('Rotated I/Q data, smallest delay, before ramp')
        ax2.set_aspect('equal')

        # Scatter plot of rotated post-ramp points for start in below/above threshold. For now, plot only last delay value
        ax3 = plt.subplot(2, 2, 3)
        #plt.scatter(i_arr_rot[0, :, 1][data_thresh[0, :, 0]], q_arr_rot[0, :, 1][data_thresh[0, :, 0]],
        #            color = 'r', marker = 'o', alpha = 0.5)
        X, Y, hist2d = FFRampTest_Experiment._prepare_hist_data(i_arr_rot[0, :, 1][data_thresh[0, :, 0]],
                                                                q_arr_rot[0, :, 1][data_thresh[0, :, 0]])
        plt.pcolor(X, Y, hist2d[0])
        plt.xlabel('I (DAC units)')
        plt.ylabel('Q (DAC units)')
        plt.title('Rotated I/Q data, smallest length,\nafter ramp, start right of threshold')
        ax3.set_aspect('equal')

        ax4 = plt.subplot(2, 2, 4)
        #plt.scatter(i_arr_rot[0, :, 1][~data_thresh[0, :, 0]], q_arr_rot[0, :, 1][~data_thresh[0, :, 0]],
        #            color = 'b', marker = 'o', alpha = 0.5)
        X, Y, hist2d = FFRampTest_Experiment._prepare_hist_data(i_arr_rot[0, :, 1][~data_thresh[0, :, 0]],
                                                                q_arr_rot[0, :, 1][~data_thresh[0, :, 0]])
        plt.pcolor(X, Y, hist2d[0])
        plt.xlabel('I (DAC units)')
        plt.ylabel('Q (DAC units)')
        plt.title('Rotated I/Q data, smallest length,\nafter ramp, start left of threshold')
        ax4.set_aspect('equal')

        plt.tight_layout()
        fig.subplots_adjust(top=0.95)
        # plt.suptitle(self.fname + '\nYoko voltage %f V, FF amplitude %d DAC.' % (self.cfg['yokoVoltage'], self.cfg['ff_gain']))
        #
        # plt.savefig(self.iname)
        #
        # if plot_disp:
        #     plt.show(block=False)
        #     plt.pause(2)
        #
        # else:
        #     fig.clf(True)
        #     plt.close(fig)

        # Calculate & plot probability of staying in same state vs. ramp time
        p_no_transition = (data_thresh[:, :, 0] == data_thresh[:, :, 1]).sum(axis = 1) / i_arr.shape[1]
        plt.figure()
        plt.plot(ramp_lengths, p_no_transition)
        plt.xlabel('Ramp lengths (us)')
        plt.ylabel('P(no transition after ramp)')

        plt.tight_layout()
        fig.subplots_adjust(top=0.95)
        # plt.suptitle(self.fname + '\nYoko voltage %f V, FF amplitude %d DAC.' % (self.cfg['yokoVoltage'], self.cfg['ff_gain']))
        #
        # plt.savefig(self.iname)
        #
        # if plot_disp:
        #     plt.show(block=False)
        #     plt.pause(2)
        #
        # else:
        #     fig.clf(True)
        #     plt.close(fig)

        if plot_all_delays:
            for i, rl in enumerate(ramp_lengths):
                plt.figure(figsize=(12, 12))
                ax1 = plt.subplot(2, 2, 1)
                plt.scatter(i_arr_rot[i, :, 0][data_thresh[i, :, 0]], q_arr_rot[i, :, 0][data_thresh[i, :, 0]],
                            color='r', marker='o', alpha=0.5)
                plt.scatter(i_arr_rot[i, :, 0][~data_thresh[i, :, 0]], q_arr_rot[i, :, 0][~data_thresh[i, :, 0]],
                            color='b', marker='o', alpha=0.5)
                plt.xlabel('I (DAC units)')
                plt.ylabel('Q (DAC units)')
                plt.title('Rotated I/Q data, %.3f us delay, before ramp' % rl)
                ax1.set_aspect('equal')

                ax2 = plt.subplot(2, 2, 2)
                plt.scatter(i_arr_rot[i, :, 1][data_thresh[i, :, 1]], q_arr_rot[i, :, 1][data_thresh[i, :, 1]],
                            color='r', marker='o', alpha=0.5)
                plt.scatter(i_arr_rot[i, :, 1][~data_thresh[i, :, 1]], q_arr_rot[i, :, 1][~data_thresh[i, :, 1]],
                            color='b', marker='o', alpha=0.5)
                plt.xlabel('I (DAC units)')
                plt.ylabel('Q (DAC units)')
                plt.title('Rotated I/Q data, %.3f us delay, after ramp' % rl)
                ax2.set_aspect('equal')

                ax3 = plt.subplot(2, 2, 3)

                ax3 = plt.subplot(2, 2, 3)

    @staticmethod
    def _prepare_hist_data(i_arr, q_arr):
        # Prepare histogram data
        iq_data = np.vstack((i_arr, q_arr))
        norm = np.sqrt(iq_data[0, :] ** 2 + iq_data[1, :] ** 2)
        bin_size = np.histogram_bin_edges(norm, bins='fd').size
        hist2d = np.histogram2d(iq_data[0, :], iq_data[1, :], bins=bin_size)
        x_points = (hist2d[1][1:] + hist2d[1][:-1]) / 2
        y_points = (hist2d[2][1:] + hist2d[2][:-1]) / 2
        Y, X = np.meshgrid(y_points, x_points)
        return X, Y, hist2d

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        return 0xBADC0FFEE
        # return self.cfg["reps"] * self.cfg["qubit_freq_expts"] * (self.cfg["relax_delay"] + self.cfg["ff_length"]) * 1e-6  # [s]



### Testing:
# a = np.random.multivariate_normal([1, 0.5], [[1, 0], [0, 1]], 10000)
# b = np.random.multivariate_normal([4, 1.5], [[1, 0], [0, 1]], 10000)
# c = np.random.random(10000)
# c = c > 0.3
# d = np.zeros((10000, 2))
# d[c, :] = a[c, :]
# d[~c, :] = b[~c, :]
# plt.figure(); plt.scatter(d[:, 0], d[:, 1])
#
# a2 = np.random.multivariate_normal([1, 0.5], [[1, 0], [0, 1]], 10000)
# b2 = np.random.multivariate_normal([4, 1.5], [[1, 0], [0, 1]], 10000)
# c2 = np.random.random(10000)
# c2 = c2 > 0.15 # Probability of switching states during ramp
# c3 = c == c2 # c is initial state, c2 is whether you switch states => c3 is final distribution after ramp
# d2 = np.zeros((10000, 2))
# d2[c3, :] = a2[c3, :]
# d2[~c3, :] = b2[~c3, :]
#
# i_arr_backup = i_arr.copy()
# q_arr_backup = q_arr.copy()
#
# i_arr = np.column_stack((d[:, 0], d2[:, 0])).reshape((1, 10000, 2))
# q_arr = np.column_stack((d[:, 1], d2[:, 1])).reshape((1, 10000, 2))