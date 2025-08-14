###
# This file contains an NDAveragerProgram and ExperimentClass for testing the ramp speed of a fast flux pulse.
# The qubit is measured at some flux point, then, the flux is moved with a variable-time (linear) ramp to a different point.
# The qubit is then moved back to the original point and measured again.
# For the fluxonium experiment, the speed conditions are:
# * slower than any crossings (adiabatic), as well as the energy spliting between g and e. (speed compares to these squared)
# * faster than any decoherence channels
# Lev, June 2025: create file.
###
import matplotlib
from qick import NDAveragerProgram

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions
from mpl_toolkits.axes_grid1 import make_axes_locatable

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

        # self.get_raw() has data in format (#channels, #reps, #readouts, 2)
        # self.di/q_buf[0] have (rep1_meas1, rep1_meas2, ... rep1_measN, rep1_meas1, ...)
        # reshape to have [[rep1_meas1, rep1_meas2], [rep2_meas1, rep2_meas2], ...]
        # di_buf and dq_buf are total integration, divide out readout time

        # Something about this has broken, and now I don't understand how it ever worked.
        # Currently, di/q_buf has only 2 points, which are the 2 expts averaged reps times. Why did this ever have more points?
        #return (self.di_buf[0].reshape(-1, 2) / self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0]),
        #        self.dq_buf[0].reshape(-1, 2) / self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0]))

        # Shape of get_raw: [# readout channels, # expts, # reps, # readouts, I/Q = 2]
        length = self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0])
        shots_i = np.array(self.get_raw())[0, :, :, 0].reshape((self.cfg["reps"], 2)) / length
        shots_q = np.array(self.get_raw())[0, :, :, 1].reshape((self.cfg["reps"], 2)) / length
        return shots_i, shots_q


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

        "verbose": False # [bool] Print a bunch of logging info
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
        self.ramp_lengths = np.linspace(self.cfg["ff_ramp_length_start"], self.cfg["ff_ramp_length_stop"],
                                   num = self.cfg["ff_ramp_expts"])
        i_arr = np.zeros((self.cfg["ff_ramp_expts"], self.cfg["reps"], 2))
        q_arr = np.zeros((self.cfg["ff_ramp_expts"], self.cfg["reps"], 2))

        # Loop over different ramp lengths. This cannot be done inside an experiment, since we must recompile pulses
        for idx, length in enumerate(self.ramp_lengths):
            prog = FFRampTest(self.soccfg, self.cfg | {"ff_ramp_length": length})

            # Collect the data
            i_arr[idx], q_arr[idx] = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                                  save_experiments=None, #readouts_per_experiment=2,
                                                  start_src="internal", progress=progress)

        data = {'config': self.cfg, 'data': {'ramp_lengths': self.ramp_lengths, 'i_arr': i_arr, 'q_arr': q_arr}}
        self.data = data

        return data

    def display(self, data=None, plot_disp = True, plot_all_lengths = False, fig_num = 1, **kwargs):
        # This seems horrible, but apparently python doesn't do operator overloading or allow &&/etc, and ~ does super
        # weird stuff (what do you think ~True is?). Writing out the functions is too long and unreadable
        NOT = np.logical_not
        AND = np.logical_and

        if data is None:
            data = self.data

        # Dimensions: (# delay points, # reps, # measurement[before/after ramp])
        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']
        ramp_lengths = data['data']['ramp_lengths']

        # If angle and threshold are not given, fit them from the data. Uses first measurement for lowest delay value
        if self.cfg["angle"] is None or self.cfg["threshold"] is None: # Both must be given to be valid
            theta, threshold = self._find_angle_threshold(i_arr[0, :, 0], q_arr[0, :, 0])
        else: # User has provided override values
            theta = self.cfg["angle"]
            threshold = self.cfg["threshold"]

        # Rotate the data. Positive angle rotates ccw
        i_arr_rot = i_arr * np.cos(theta) - q_arr * np.sin(theta)
        q_arr_rot = i_arr * np.sin(theta) + q_arr * np.cos(theta)

        # Threshold; the data has been rotated such that the signal is in e
        data_thresh = i_arr_rot > threshold

        if plot_all_lengths:
            ramp_lengths_loop = ramp_lengths
        else:
            ramp_lengths_loop = [ramp_lengths[0]]

        # Draw plots for all the desired ramp lengths
        for i, rl in enumerate(ramp_lengths_loop):
            # Make the figure
            while plt.fignum_exists(num=fig_num): ###account for if figure with number already exists
                fig_num += 1
            fig = plt.figure(figsize=(12, 12), num=fig_num)

            # Make histogram of original data
            ax1 = plt.subplot(2, 2, 1)
            self._draw_histogram(ax1, i_arr[i, :, 0], q_arr[i, :, 0], 'Raw I/Q data, %.3f us ramp half-length, before ramp' % rl)

            # Scatter plot of rotated data, with colour set by threshold. For now, plot only first delay value
            ax2 = plt.subplot(2, 2, 2)
            plt.scatter(i_arr_rot[i, :, 0][data_thresh[i, :, 0]], q_arr_rot[i, :, 0][data_thresh[i, :, 0]],
                        color = 'r', marker = 'o', alpha = 0.5)
            plt.scatter(i_arr_rot[i, :, 0][NOT(data_thresh[i, :, 0])], q_arr_rot[i, :, 0][NOT(data_thresh[i, :, 0])],
                        color = 'b', marker = 'o', alpha = 0.5)
            plt.xlabel('I (DAC units)')
            plt.ylabel('Q (DAC units)')
            plt.title('Rotated I/Q data, %.3f us ramp half-length, before ramp\n%.2f%% | %.2f%%' %
                      (rl, NOT(data_thresh[i, :, 0]).sum() / data_thresh.shape[1] * 100,
                           data_thresh[i, :, 0].sum() / data_thresh.shape[1] * 100 ))

            ax2.set_aspect('equal')

            # Histograms of rotated post-ramp points for start in below/above threshold.
            ax3 = plt.subplot(2, 2, 3)
            self._draw_histogram(ax3, i_arr_rot[i, :, 1][NOT(data_thresh[i, :, 0])],
                                      q_arr_rot[i, :, 1][NOT(data_thresh[i, :, 0])],
                'Rotated I/Q data, %.3f us ramp half-length,\nafter ramp, start left of threshold\n%.2f%% | %.2f%%' % (
                rl,
                NOT(data_thresh[i, :, 1])[NOT(data_thresh[i, :, 0])].sum() / NOT(data_thresh[i, :, 0]).sum() * 100,
                data_thresh[i, :, 1][NOT(data_thresh[i, :, 0])].sum() / NOT(data_thresh[i, :, 0]).sum() * 100 ))


            ax4 = plt.subplot(2, 2, 4)
            self._draw_histogram(ax4, i_arr_rot[i, :, 1][data_thresh[i, :, 0]], q_arr_rot[i, :, 1][data_thresh[i, :, 0]],
                   'Rotated I/Q data, %.3f ramp half-length,\nafter ramp, start right of threshold\n%.2f%% | %.2f%%' % (
                   rl,
                   NOT(data_thresh[i, :, 1])[data_thresh[i, :, 0]].sum() / data_thresh[i, :, 0].sum() * 100,
                   data_thresh[i, :, 1][data_thresh[i, :, 0]].sum() / data_thresh[i, :, 0].sum() * 100 ))

            plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp from %d to %d DAC, FF delay %.2f us.' %
                         (self.cfg['yokoVoltage'], self.cfg['ff_ramp_start'], self.cfg['ff_ramp_stop'], self.cfg['ff_delay']))
            plt.tight_layout()
            plt.subplots_adjust(top=0.97, hspace = 0.05, wspace = 0.2)

        # Calculate & plot probability of staying in same state vs. ramp time
        self._plot_probabilities(data_thresh[:, :, 0], data_thresh[:, :, 1])

        #
        # if plot_disp:
        #     plt.show(block=False)
        #     plt.pause(2)
        #
        # else:
        #     fig.clf(True)
        #     plt.close(fig)


    def _find_angle_threshold(self, i_arr: np.ndarray, q_arr: np.ndarray) -> tuple[float, float]:
        import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.Shot_Analysis.shot_analysis as shot_analysis
        ssa = shot_analysis.SingleShotAnalysis(i_arr, q_arr)
        ssa_centers = ssa.get_Centers(i_arr, q_arr)
        self.ssa_centers = ssa_centers
        # We rotate to undo the current rotation, so - sign
        theta = -np.arctan((ssa_centers[1, 1] - ssa_centers[0, 1]) / (ssa_centers[1, 0] - ssa_centers[0, 0]))
        # Threshold is the rotated i-coordinate of the midpoint between the two blobs centres (sigmas are the same)
        threshold = (ssa_centers[0, 0] + ssa_centers[1, 0]) / 2 * np.cos(theta) - \
                    (ssa_centers[0, 1] + ssa_centers[1, 1]) / 2 * np.sin(theta)
        print("Fit angle: %.4f\nFit threshold: %.3f" % (theta, threshold))
        return theta, threshold

    def _gaussian_fit_assignment(self, i_0: np.ndarray, q_0: np.ndarray, i_1: np.ndarray, q_1: np.ndarray,
                                 cen_num: int = 2, bin_size: int = 101) -> tuple[np.ndarray, np.ndarray]:
        """ Uses Gaussian fitting to assign most probable cluster numbers to the I/Q arrays passed in.
        We assume the i0/q0 data has enough of all blobs to perform a proper fit. The centres from that fit
        are then used to fit the i0/q0 amplitudes and set the probability distributions.
        :param i_0: ndarray of floats, shape is [# experiments, # shots]. I's of initial measurement
        :param q_0: Q's of initial measurement, see i_0
        :param i_1: I's of final measurement, see i_0
        :param q_1: Q's of final measurement, see i_0
        :param cen_num: number of clusters
        :param bin_size: size of bins for histograms
        :returns array of assignments to blobs.
        Code adapted from mSpecSlice_PS_sse.py"""

        from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2

        # Verify inputs
        if not (i_0.shape == q_0.shape == i_1.shape == q_1.shape):
            raise ValueError('Shapes of i0, q0, i1, and q1 are not all the same!')
        if cen_num < 2:
            raise ValueError('cen_num must be at least 2!')
        if bin_size < 2:
            raise ValueError('bin_size must be at least 2')

        # Create empty arrays to save data
        centers = []

        # Probabilities of each shot being in cluster # cen_num. Shape: [# experiments, # clusters, # shots]
        probability_0 = np.zeros((i_0.shape[0], cen_num, i_0.shape[1]))
        probability_1 = np.zeros((i_0.shape[0], cen_num, i_0.shape[1]))

        # Loop over experiments (i.e. variations of some external parameter)
        for i in range(i_0.shape[0]):
            # Perform post selection for the initial data for two centers
            # by selecting points withing some confidence bound.
            # This turns the arrays and gives a [2, # shots] array as a result.
            iq_data_0 = np.stack((i_0[i, :], q_0[i, :]), axis=0)
            iq_data_1 = np.stack((i_1[i, :], q_1[i, :]), axis=0)

            # Get centers
            if i == 0:      # First pass, just do it
                centers.append(sse2.getCenters(iq_data_0, cen_num))
            else:           # Already have done it, use first result as initial guess
                centers.append(sse2.getCenters(iq_data_0, cen_num, init_guess=centers[0]))

            if self.cfg["verbose"]:
                print("Centers are ", centers[i])

            # I don't really understand the code below since a lot of it is hidden in sse2. I won't look at it too
            # carefully for now, if I can get this to work.

            # Fit Gaussian to first measurement
            # Does not require both sigmas to be the same TODO rewrite for same sigma for all gaussians
            hist2d = sse2.createHistogram(iq_data_0, bin_size) # Generates histogrammed data
            no_of_params = 4
            gaussians_0, popt_0, x_points_0, y_points_0 = sse2.findGaussians(hist2d, centers[i], cen_num)

            # Don't understand the point of defining these, they're not used
            # # create bounds given current fit
            # bound = [popt_0 - 1e-5, popt_0 + 1e-5]
            #
            # for idx_bound in range(cen_num):
            #     bound[0][0 + int(idx_bound * no_of_params)] = 0
            #     bound[1][0 + int(idx_bound * no_of_params)] = np.inf

            # Get probability density function
            pdf_0 = sse2.calcPDF(gaussians_0)

            # print("Shape of probability array is ", probability.shape)
            for k in range(cen_num):
                for j in range(iq_data_0.shape[1]): # This seems to loop over every shot? Probably very slow
                    # I think the x and y points are the grid points for the histogram? Not sure
                    # find the x,y point closest to the i,q point instead of getting a continuous pdf
                    indx_i = np.argmin(np.abs(x_points_0 - iq_data_0[0, j]))
                    indx_q = np.argmin(np.abs(y_points_0 - iq_data_0[1, j]))
                    # Calculate the probability
                    probability_0[i, k, j] = pdf_0[k][indx_i, indx_q]

            # Use fit result from first measurement to fit second measurement (only amplitudes)
            hist2d = sse2.createHistogram(iq_data_1, bin_size)
            # I think the parameters are, in order, amplitude, x0, y0, sigma, amplitude, x0, y0, sigma
            # Set bounds on amplitude [0, inf); every other parameter should have both bounds be its value from before
            # We don't want the second fit to be able to change the parameters except for amplitude, but we have to
            # provide a bit of wiggle room, otherwise curve fit complains
            eps = 1e-6  # small number
            bound = [(popt_0 - np.abs(popt_0) * eps) * np.array([0, 1, 1, 1, 0, 1, 1, 1]) ,
                     (popt_0 + np.abs(popt_0) * eps) * np.array([np.inf, 1, 1, 1, np.inf, 1, 1, 1]) ]
            gaussians_1, popt_1, x_points_1, y_points_1 = sse2.findGaussians(hist2d, centers[i], cen_num,
                                                                             input_bounds=bound, p_guess=popt_0)
            # Get probability density function
            pdf_1 = sse2.calcPDF(gaussians_1)

            for k in range(cen_num):
                for j in range(iq_data_1.shape[1]): # This seems to loop over every shot? Probably very slow
                    # I think the x and y points are the grid points for the histogram? Not sure
                    # find the x,y point closest to the i,q point instead of getting a continuous pdf
                    indx_i = np.argmin(np.abs(x_points_1 - iq_data_1[0, j]))
                    indx_q = np.argmin(np.abs(y_points_1 - iq_data_1[1, j]))
                    # Calculate the probability
                    probability_1[i, k, j] = pdf_1[k][indx_i, indx_q]

            return probability_0, probability_1

    def _calculate_probs(self, i_0: np.ndarray, q_0: np.ndarray, i_1: np.ndarray, q_1: np.ndarray,
                         prob_0: np.ndarray, prob_1: np.ndarray, confidence: float = 0.8, draw_all_plots: bool = False):
        """
        Calculates the probabilities of state transitions between before and after the ramp. Draws some plots.
        :param i_0: ndarray of floats, shape is [# experiments, # shots]. I's of initial measurement
        :param q_0: Q's of initial measurement, see i_0
        :param i_1: I's of final measurement, see i_0
        :param q_1: Q's of final measurement, see i_0
        :param prob_0: probabilities of I/Q shots being in cluster # cen_num. Shape: [# experiments, # clusters, # shots]
                       First measurement (before ramp).
        :param prob_1: Same as prob_0 but for second measurement (after ramp).
        :param confidence: pick which data to include by how confident we are that it belongs in a given blob. For 50%,
                    (and cen_num = 2), this splits all data between the two blobs. For confidence > 50%, this will
                    throw away some data about which we are not too confident (in the middle between the blobs).
        :param draw_all_plots: Draw all the intermediate plots or just a smaller number
        :return:
        """
        if not (i_0.shape == q_0.shape == i_1.shape == q_1.shape):
            raise ValueError('Shapes of i0, q0, i1, and q1 are not all the same!')
        if not (prob_0.shape == prob_1.shape):
            raise ValueError('Shapes of prob_0 and prob_1 are not the same!')
        if not (i_0.shape[0] == prob_0.shape[0]):
            raise ValueError('Number of experiments (dimension 0) for i/q and prob are not the same!')
        if not (i_0.shape[1] == prob_0.shape[2]):
            raise ValueError('Number of shots (dim. 0 for i, dim. 2 for prob) are not the same!')
        if confidence < 0.5:
            raise ValueError('Confidence should be at least 50%')
        elif confidence > 1:
            raise ValueError('Confidence should be no more than 100%')


        num_expts = prob_0.shape[0]
        cen_num = prob_0.shape[1]
        # Dimensions: [# start blob, # end blob, # experiments]
        pop = np.zeros((cen_num, cen_num, num_expts]))

    @staticmethod
    def _prepare_hist_data(i_arr: np.ndarray, q_arr: np.ndarray):
        # Prepare histogram data
        iq_data = np.vstack((i_arr, q_arr))
        norm = np.sqrt(iq_data[0, :] ** 2 + iq_data[1, :] ** 2)
        bin_size = np.histogram_bin_edges(norm, bins='fd').size
        hist2d = np.histogram2d(iq_data[0, :], iq_data[1, :], bins=bin_size)
        x_points = (hist2d[1][1:] + hist2d[1][:-1]) / 2
        y_points = (hist2d[2][1:] + hist2d[2][:-1]) / 2
        Y, X = np.meshgrid(y_points, x_points)
        return X, Y, hist2d

    def _draw_histogram(self, ax: matplotlib.axes.Axes, i_arr: np.ndarray, q_arr: np.ndarray,  title: str) -> None:
        """ Draw a histogram of the I/Q data in i_arr/q_arr onto axes ax with title title."""
        X, Y, hist2d = FFRampTest_Experiment._prepare_hist_data(i_arr, q_arr)
        Z = hist2d[0]
        p1 = plt.pcolor(X, Y, Z)
        # If we have fit the data within this program, draw the centres
        if self.cfg["angle"] is None or self.cfg["threshold"] is None:
            plt.scatter(self.ssa_centers[:, 0], self.ssa_centers[:, 1], color='r', marker='x')
        plt.xlabel('I (DAC units)')
        plt.ylabel('Q (DAC units)')
        plt.title(title)

        # Matplotlib magic that makes the colourbar not be a stupid size
        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="5%", pad=0.05)
        plt.colorbar(p1, cax=cax)
        ax.set_aspect('equal')

    def _plot_probabilities(self, shots0: np.ndarray, shots1: np.ndarray):
        """ Plots the probabilities of (no) transition vs. ramp lengths.
        shots0/1: ndarray of booleans, True if right of threshold. First/second measurement.
        Shape is (# ramp lengths, # shots). """

        # This seems horrible, but apparently python doesn't do operator overloading or allow &&/etc, and ~ does super
        # weird stuff (what do you think ~True is?). Writing out the functions is too long and unreadable
        NOT = np.logical_not
        AND = np.logical_and

        # Calculate & plot probability of staying in same state vs. ramp time
        p_no_transition = (shots0 == shots1).sum(axis = 1) / shots0.shape[1]
        p_start_L_end_L = (AND(NOT(shots0), NOT(shots1))).sum(axis=1) / NOT(shots0).sum(axis=1)
        p_start_R_end_R = (AND(shots0, shots1)).sum(axis=1) / shots0.sum(axis = 1)
        #assert all(p_no_transition - (p_start_L_end_L + p_start_R_end_R) < np.ones(p_no_transition.shape) * 1e-10)

        plt.figure(figsize=(16, 8))
        plt.subplot(1, 3, 1)
        plt.plot(self.ramp_lengths, p_no_transition)
        plt.xlabel('Ramp lengths (us)')
        plt.ylabel('P(no transition after ramp)')

        plt.subplot(1, 3, 2)
        plt.plot(self.ramp_lengths, p_start_L_end_L)
        plt.xlabel('Ramp lengths (us)')
        plt.ylabel('P(start left, end left)')

        plt.subplot(1, 3, 3)
        plt.plot(self.ramp_lengths, p_start_R_end_R)
        plt.xlabel('Ramp lengths (us)')
        plt.ylabel('P(start right, end right)')

        plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp from %d to %d DAC, FF delay %.2f us.' %
                     (self.cfg['yokoVoltage'], self.cfg['ff_ramp_start'], self.cfg['ff_ramp_stop'], self.cfg['ff_delay']))
        plt.tight_layout()

        plt.savefig(self.iname)
        print('Saved probabilities at %s' % self.iname)


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