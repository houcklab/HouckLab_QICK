###
# This file contains an NDAveragerProgram and ExperimentClass for testing the ramp speed of a fast flux pulse.
# The qubit is measured at some flux point, then, the flux is moved with a variable-time (linear) ramp to a different point.
# The qubit is then moved back to the original point and measured again.
# For the fluxonium experiment, the speed conditions are:
# * slower than any crossings (adiabatic), as well as the energy spliting between g and e. (speed compares to these squared)
# * faster than any decoherence channels
# Lev, June 2025: create file.
###
import sys

import matplotlib
from qick import NDAveragerProgram
from qick.averager_program import QickSweep

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import PulseFunctions
from mpl_toolkits.axes_grid1 import make_axes_locatable

class FFRampTest(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux
        if self.cfg["qubit_pulse"]:  # Optional qubit pulse
            self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])
            PulseFunctions.create_qubit_pulse(self, self.cfg["qubit_freq"])

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

        # Give tprocessor time to execute all initialisation instructions before we expect any pulses to happen
        self.sync_all(self.us2cycles(1))

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
        #TODO this experiment doesn't really make sense as written, it would only really work for starting ramp from 0
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"]) # Do NOT include channel, it's wrong!

        # Check that the flux ramps finish after the first readout. Otherwise, the sync_all will insert extra delay.
        # This can be fixed by using the t argument everywhere in the body, but I think it's not a good idea
        if self.cfg["relax_delay_1"] + self.cfg['cycle_number'] * (self.cfg['ff_ramp_length'] * 2 + self.cfg['ff_delay'] +
                                                                  self.cfg['cycle_delay']) < self.cfg['adc_trig_offset']:
           print('Warning: readout will not complete before flux ramps. Expect a delay before 2nd readout', file = sys.stderr)

        # Play optional qubit pulse, if requested. This is only done once per experiment.
        if self.cfg["qubit_pulse"]:
            self.pulse(ch = self.cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.02))  # Wait a few ns to align channels

        # trigger measurement, play measurement pulse, wait for relax_delay_1. Once per experiment.
        # Can't use measure command because that has sync_all which pushes us to after the trigger offset
        # Parth : The benefit of not waiting for trigger to finish is of 0.5 us which is negligible.
        self.trigger(self.cfg['ro_chs'], adc_trig_offset=adc_trig_offset_cycles, t = 0)
        self.pulse(ch = self.cfg["res_ch"], t = 0)

        # Cycle the ff ramp as requested.
        for c in range(self.cfg["cycle_number"]):
            # play fast flux ramp
            # I need to use the t argument so that the pulse can start before the readout trigger is complete
            # In principle, this could also be done with synci, but sync_all doesn't know about previous synci commands
            # and there is a bug in the current firmware that incorrectly compiles without a t argument after synci
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel = 'last',
                                     gain = self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
            self.pulse(ch = self.cfg["ff_ch"], t = self.us2cycles(self.cfg["read_length"] + self.cfg["relax_delay_1"] +
                        c * (self.cfg['ff_ramp_length'] * 2 + self.cfg['ff_delay'] + self.cfg['cycle_delay'])))

            # # play constant pulse to keep FF at ramped value if a delay here is desired
            if self.cfg["ff_delay"] > 0:
                self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='const', phase=0, gain = self.cfg["ff_ramp_stop"],
                                         length = self.us2cycles(self.cfg["ff_delay"], gen_ch=self.cfg["ff_ch"]))
                self.pulse(ch = self.cfg["ff_ch"], t ='auto')

            # play reversed fast flux ramp, return to original spot
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                     gain = self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
            self.pulse(ch = self.cfg["ff_ch"], t ='auto')

        # Sync to make sure ramping is done before starting second measurement.
        self.sync_all(self.us2cycles(1))

        # trigger measurement, play measurement pulse, wait for relax_delay_2. Once per experiment.
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t = 0, wait = True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay_2"]))


    # Override acquire such that we can collect the single-shot data
    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress) # qick update, debug=debug)

        # Shape of get_raw: [# readout channels, # expts, # reps, # readouts, I/Q = 2]
        # If no sweeps, # expts dimension goes away (not just becomes 1)
        length = self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0])
        assert len(np.array(self.get_raw()).shape) == 4
        shots_i = np.array(self.get_raw())[0, :, :, 0].reshape((self.cfg["reps"], 2)) / length
        shots_q = np.array(self.get_raw())[0, :, :, 1].reshape((self.cfg["reps"], 2)) / length

        return shots_i, shots_q


    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section
        "read_pulse_style": "linear",     # --Fixed
        "read_length": 5,                 # [us]
        "read_pulse_gain": 8000,          # [DAC units]
        "read_pulse_freq": 7392.25,       # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "const",         # one of ["linear"]
        "ff_ramp_start": 0,               # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": 100,              # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 1,                    # [us] Delay between fast flux ramps
        "ff_ch": 6,                       # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                      # Nyquist zone to use for fast flux drive

        # Optional qubit pulse before measurement, intended as pi/2 to populate both blobs
        "qubit_pulse": False,             # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 1000,               # [MHz] Frequency of qubit pulse
        "qubit_pulse_style": "flat_top",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.050,                   # [us], used with "arb" and "flat_top"
        "qubit_length": 1,                # [us], used with "const"
        "flat_top_length": 0.300,         # [us], used with "flat_top"
        "qubit_gain": 25000,              # [DAC units]
        "qubit_ch": 1,                    # RFSOC output channel of qubit drive
        "qubit_nqz": 1,                   # Nyquist zone to use for qubit drive

        # Ramp length sweep parameters
        "ff_ramp_length_start": 1,        # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 5,         # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_length_expts": 10,       # [int] Number of points in the ff ramp length sweep

        # Gain sweep parameters
        "ff_gain_expts": 10,              # [int] How many different ff ramp gains to use
        "ff_ramp_length": 1,              # [us] Half-length of ramp to use when sweeping gain

        # Number of cycle repetitions sweep parameters
        "cycle_number_expts": 11,         # [int] How many values for number of cycles around to use in this experiment
        "max_cycle_number": 5,            # [int] What is the largest number of cycles to use in sweep? Start at 1
        "cycle_delay": 0.02,              # [us] How long to wait between cycles in one experiment?

        # General sweep parameters
        "sweep_type": 'ramp_length',      # [str] What to sweep? 'ramp_length', 'ff_gain', 'cycle_number'

        # Other parameters
        "yokoVoltage": 0,                 # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 10,              # [us] Relax delay after first readout
        "relax_delay_2": 10,              # [us] Relax delay after second readout
        "reps": 1000,
        "sets": 5,

        "angle": None,                    # [radians] Angle of rotation for readout
        "threshold": None,                # [DAC units] Threshold between g and e

        "plot_all_points": False,  # [bool] Draw histograms for all lengths
        "verbose": False # [bool] Print a bunch of logging info
    }



class FFRampTest_Experiment(ExperimentClass):
    """
    Requires a readout calibration (angle + threshold) to be calculated before.
    We will not use thresholded readout, however, and store the full i/q data, in case we want to analyse it in a
    different way later.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = True):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress=False, debug=False):
        # Deal with cycles
        # I assume that a cycle number is not defined unless we are sweeping cycles. Complain if I am wrong.
        if not self.cfg["sweep_type"] == 'cycle_number':
            if 'cycle_number' in self.cfg.keys():
                raise ValueError('\'cycle_number\' defined, but we are not sweeping cycle_number! Edit code to make this ok')
            self.cfg["cycle_number"] = 1
            self.cfg['cycle_delay'] = 0.01


        if self.cfg["sweep_type"] == 'ramp_length':
            # Loop over different ramp lengths. This cannot be done inside an experiment, since we must recompile pulses
            i_arr = np.zeros((self.cfg["ff_ramp_length_expts"], self.cfg["reps"], 2))
            q_arr = np.zeros((self.cfg["ff_ramp_length_expts"], self.cfg["reps"], 2))

            self.ramp_lengths = np.linspace(self.cfg["ff_ramp_length_start"], self.cfg["ff_ramp_length_stop"],
                                            num=self.cfg["ff_ramp_length_expts"])

            for idx, length in enumerate(self.ramp_lengths):
                prog = FFRampTest(self.soccfg, self.cfg | {"ff_ramp_length": length})

                # Collect the data
                i_arr[idx], q_arr[idx] = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                                      save_experiments=None, #readouts_per_experiment=2,
                                                      start_src="internal", progress=progress)

            data = {'config': self.cfg, 'data': {'ramp_lengths': self.ramp_lengths, 'i_arr': i_arr, 'q_arr': q_arr}}
        elif self.cfg["sweep_type"] == 'ff_gain':  # Sweeping fast flux gain, therefore do not sweep ramp length. Only one allowed for now
            i_arr = np.zeros((self.cfg["ff_gain_expts"], self.cfg["reps"], 2))
            q_arr = np.zeros((self.cfg["ff_gain_expts"], self.cfg["reps"], 2))

            self.final_gains = np.rint(np.linspace(0, self.cfg["ff_ramp_stop"], num = self.cfg["ff_gain_expts"]))
            for idx, final_gain in enumerate(self.final_gains):
                prog = FFRampTest(self.soccfg, self.cfg | {"ff_ramp_stop": final_gain})

                i_arr[idx], q_arr[idx] = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                                      save_experiments=None, #readouts_per_experiment=2,
                                                      start_src="internal", progress=progress)
            data = {'config': self.cfg, 'data': {'final_gains': self.final_gains, 'i_arr': i_arr, 'q_arr': q_arr}}
        elif self.cfg["sweep_type"] == 'cycle_number':
            i_arr = np.zeros((self.cfg["cycle_number_expts"], self.cfg["reps"], 2))
            q_arr = np.zeros((self.cfg["cycle_number_expts"], self.cfg["reps"], 2))

            self.cycle_numbers = np.rint(np.linspace(1, self.cfg["max_cycle_number"], num=self.cfg["cycle_number_expts"])).astype(int)
            for idx, cycle_number in enumerate(self.cycle_numbers):
                prog = FFRampTest(self.soccfg, self.cfg | {'cycle_number' : cycle_number})

                i_arr[idx], q_arr[idx] = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                                      save_experiments=None,  # readouts_per_experiment=2,
                                                      start_src="internal", progress=progress)
            data = {'config': self.cfg, 'data': {'cycle_numbers': self.cycle_numbers, 'i_arr': i_arr, 'q_arr': q_arr}}
        else:
            raise ValueError("cfg[\"sweep_type\"] must be one of \'ramp_length\', \'ff_gain\', or \'cycle_number\'!")

        self.data = data

        return data

    def display(self, data=None, plot_disp = True, fig_num = 1, **kwargs):
        # This seems horrible, but apparently python doesn't allow &&/etc, and ~ does super weird stuff
        # (what do you think ~True is?). Writing out the functions is too long and unreadable
        #NOT = np.logical_not
        #AND = np.logical_and

        plot_all_points = self.cfg["plot_all_points"]

        if data is None:
            data = self.data

        # Dimensions: (# delay points, # reps, # measurement[before/after ramp])
        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']

        if self.cfg["sweep_type"] == 'ff_gain':
            x_points = data['data']['final_gains']
        elif self.cfg["sweep_type"] == 'ramp_length':
            x_points = data['data']['ramp_lengths']
        elif self.cfg["sweep_type"] == 'cycle_number':
            x_points = data['data']['cycle_numbers']

        prob_0, prob_1 = self._gaussian_fit_assignment(i_arr[:, :, 0], q_arr[:, :, 0], i_arr[:, :, 1], q_arr[:, :, 1],
                                                       cen_num = 2)

        pop = self._calculate_pops(prob_0, prob_1, confidence = self.cfg["confidence"])

        self._make_plots_gauss(pop, prob_0, prob_1, data, confidence = self.cfg["confidence"])

        self._plot_gaussian_probabilities(pop, x_points)

        data['data']['pop'] = pop
        data['data']['prob_0'] = prob_0
        data['data']['prob_1'] = prob_1

        return data


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
                                 cen_num: int = 2, bin_size: int = 101) -> tuple[np.ndarray[float], np.ndarray[float]]:
        """ Uses Gaussian fitting to assign most probable cluster numbers to the I/Q arrays passed in.
        We assume the i0/q0 data has enough of all blobs to perform a proper fit. The centres from that fit
        are then used to fit the i0/q0 amplitudes and set the probability distributions.
        :param i_0: ndarray of floats, shape is [# experiments, # shots]. I's of initial measurement
        :param q_0: Q's of initial measurement, see i_0
        :param i_1: I's of final measurement, see i_0
        :param q_1: Q's of final measurement, see i_0
        :param cen_num: number of clusters
        :param bin_size: size of bins for histograms
        :returns array of probabilities of assignments to blobs. [# experiments, # clusters, # shots]
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
                centre_guess = sse2.getCenters(iq_data_0, cen_num)
            else:           # Already have done it, use first result as initial guess
                centre_guess = sse2.getCenters(iq_data_0, cen_num, init_guess=centers[0])

            # I don't really understand the code below since a lot of it is hidden in sse2. I won't look at it too
            # carefully for now, if I can get this to work.

            # Fit Gaussian to first measurement
            # Does not require both sigmas to be the same TODO rewrite for same sigma for all gaussians
            hist2d = sse2.createHistogram(iq_data_0, bin_size) # Generates histogrammed data
            no_of_params = 4
            gaussians_0, popt_0, x_points_0, y_points_0 = sse2.findGaussians(hist2d, centre_guess, cen_num)

            centers.append((popt_0.reshape(cen_num, 4))[:, 1:3]) # Get the x and y coordinates of each Gaussian
            if self.cfg["verbose"]:
                print('=========================================================\nLength #%d' % i)
                print("Centers are ", centers[i])
                print('Fit results pre-ramp: ', popt_0)

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

            if self.cfg["verbose"]:
                print("Fit results post-ramp:", popt_1)

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

        self.centers = centers

        return probability_0, probability_1

    def _calculate_pops(self, prob_0: np.ndarray, prob_1: np.ndarray, confidence: float = 0.5) -> np.ndarray[int]:
        """
        Calculates the populations of state transitions between before and after the ramp.
        :param prob_0: probabilities of I/Q shots being in cluster # cen_num. Shape: [# experiments, # clusters, # shots]
                       First measurement (before ramp).
        :param prob_1: Same as prob_0 but for second measurement (after ramp).
        :param confidence: pick which data to include by how confident we are that it belongs in a given blob. For 50%,
                    (and cen_num = 2), this splits all data between the two blobs. For confidence > 50%, this will
                    throw away some data about which we are not too confident (in the middle between the blobs).
        :return: pop: populations of states in particular clusters before/after ramp.
                      Shape: [# experiments, # start cluster, # end cluster]
        """
        if not (prob_0.shape == prob_1.shape):
            raise ValueError('Shapes of prob_0 and prob_1 are not the same!')
        if confidence <= 0:
            raise ValueError('Confidence should be at least 0%') # < 50% makes sense for > 2 clusters, maybe?
        elif confidence > 1:
            raise ValueError('Confidence should be no more than 100%')


        num_expts = prob_0.shape[0]
        cen_num = prob_0.shape[1]
        # Populations of states in cluster # before/after ramp. Shape: [# experiments, # start blob, # end blob]
        pop = np.zeros((num_expts, cen_num, cen_num))

        for i in range(num_expts):
            # This can probably be done in a vectorised way, but I think it's easier to understand with nested loops
            # cen_num is probably 2 or 3 anyway, so we're not slowing ourselves down too much
            for j in range(cen_num):
                # True where the first measurement places us in cluster j with probability > confidence
                start_mask = prob_0[i, j, :] > confidence
                for k in range(cen_num):
                    # True where the second measurement places us in cluster k with probability > confidence
                    end_mask = prob_1[i, k, :] > confidence
                    pop[i, j, k] = (np.logical_and(start_mask, end_mask)).sum()

        return pop


    def _make_plots_gauss(self, pop: np.ndarray[int], prob_0: np.ndarray[float], prob_1: np.ndarray[float],
                          data: dict, confidence: float = 0.5, fig_num: int = 1) -> None:
        """
        Makes plots of all the things we're interested in for this program when using the Gaussian fitting method.
        This code may break for cen_num != 2.
        :param pop: populations of states in particular clusters before/after ramp.
                          Shape: [# experiments, # start cluster, # end cluster]
        :param prob_0: probability of shot being in a given cluster, first measurement. [# experiments, # clusters, # shots]
        :param prob_1: probability of shot being in a given cluster, second measurement.
        :param data: dictionary of the data taken
        :param fig_num: Number of figure to start plots at
        """

        plot_all_points = self.cfg["plot_all_points"]

        # Number of clusters
        cen_num = prob_0.shape[1]

        # Make sure we're not assigning any shots to multiple blobs, e.g. cen_num = 3, prob = [0.4, 0.4, 0.2], conf =0.3
        if (((prob_0 > confidence).sum(axis=1)) > 1).any() or (((prob_1 > confidence).sum(axis=1)) > 1).any():
            raise ValueError("At least one shot assigned to multiple blobs! Choose a higher confidence")

        if data is None:
            data = self.data

        # Dimensions: (# delay points, # reps, # measurement[before/after ramp])
        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']

        # Determine the x axis
        if self.cfg["sweep_type"] == 'ff_gain':
            final_gains = data['data']['final_gains']
            x_points = final_gains
            fstring = '%d DAC units endpoint'
        elif self.cfg["sweep_type"] == 'ramp_length':
            ramp_lengths = data['data']['ramp_lengths']
            x_points = ramp_lengths
            fstring = '%.3f us ramp half-length'
        elif self.cfg["sweep_type"] == 'cycle_number':
            cycle_numbers = data['data']['cycle_numbers']
            x_points = cycle_numbers
            fstring = '%d cycles of ramp'

        # Determine for which length values we will make a histogram. Always make one for at least the first.
        if not plot_all_points:
             x_points = [x_points[0]]

        # Draw plots for all the desired ramp lengths
        for i, x_pt in enumerate(x_points):
            # Make the figure
            while plt.fignum_exists(num=fig_num):  ###account for if figure with number already exists
                fig_num += 1
            fig = plt.figure(figsize=(12, 12), num=fig_num)

            # Make histogram of original data
            ax1 = plt.subplot(2, cen_num, 1)
            self._draw_histogram(ax1, i_arr[i, :, 0], q_arr[i, :, 0],
                                 ('Raw I/Q data, ' + fstring + ', before ramp') % x_pt)

            # Scatter plot of data, with colour set by assignment.
            ax2 = plt.subplot(2, cen_num, 2)
            for c in range(cen_num): # Draw every cluster
                plt.scatter(i_arr[i, :, 0][prob_0[i, c, :] > confidence], q_arr[i, :, 0][prob_0[i, c, :] > confidence],
                             marker='o', alpha=0.5) # color='r',
                plt.text(self.centers[i][c, 0], self.centers[i][c, 1], '#%d' % c, ha = 'center', va = 'center')
            plt.xlabel('I (DAC units)')
            plt.ylabel('Q (DAC units)')
            plt.title(('I/Q data, ' + fstring + ', before ramp\n%.2f%% | %.2f%%') %
                      (x_pt, (prob_0[i, 0, :] > confidence).sum() / prob_0.shape[2] * 100,
                       (prob_0[i, 1, :] > confidence).sum() / prob_0.shape[2] * 100))

            ax2.set_aspect('equal')

            # Histograms of post-ramp points for start in every cluster
            # Again, nested loop, but easier to understand and cen_num is likely 2 or 3
            for c in range(cen_num):
                axn = plt.subplot(2, cen_num, cen_num + c + 1)
                percentage = " | ".join("%.2f%%" % (((prob_1[i, c_end, :] > confidence)[prob_0[i, c, :] > confidence]).sum()
                                        / (prob_0[i, c, :] > confidence).sum() * 100) for c_end in range(0, cen_num))
                self._draw_histogram(axn, i_arr[i, :, 1][prob_0[i, c, :] > confidence],
                                          q_arr[i, :, 1][prob_0[i, c, :] > confidence],
                        'I/Q data, %.3f us ramp half-length,\nAfter ramp, start in cluster %d\n' % (x_pt, c) + percentage)

            if self.cfg["sweep_type"] == 'ff_gain':
                plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp from %d to %d DAC, FF delay %.2f us. Ramp half-length %.2f us.' %
                                          (self.cfg['yokoVoltage'], self.cfg['ff_ramp_start'], x_pt,
                                           self.cfg['ff_delay'], self.cfg["ff_ramp_length"]))
            elif self.cfg["sweep_type"] == 'ramp_length':
                plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp from %d to %d DAC, FF delay %.2f us. Ramp half-length %.2f us.' %
                                          (self.cfg['yokoVoltage'], self.cfg['ff_ramp_start'], self.cfg['ff_ramp_stop'],
                                           self.cfg['ff_delay'], x_pt))
            elif self.cfg["sweep_type"] == 'cycle_number':
                plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp from %d to %d DAC, FF delay %.2f us. Ramp half-length %.2f us. %d ramp cycles' %
                                          (self.cfg['yokoVoltage'], self.cfg['ff_ramp_start'], self.cfg['ff_ramp_stop'],
                                           self.cfg['ff_delay'], self.cfg["ff_ramp_length"], x_pt))
            plt.tight_layout()
            plt.subplots_adjust(top=0.97, hspace=0.05, wspace=0.2)

            # Always save a plot of the first dataset, so we can see which blob is assigned where
            if i == 0:
                plt.savefig(self.dname + 'hist_plot.png')
                print('Saved histograms at %s' % (self.dname + 'hist_plot.png'))

        # Calculate & plot probability of staying in same state vs. ramp time
        #self._plot_probabilities(data_thresh[:, :, 0], data_thresh[:, :, 1])

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
#        if self.cfg["angle"] is None or self.cfg["threshold"] is None:
            #plt.scatter(self.ssa_centers[:, 0], self.ssa_centers[:, 1], color='r', marker='x')
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

    def _plot_gaussian_probabilities(self, pop: np.ndarray[int], x_points: np.ndarray[float]) -> None:
        if self.cfg["sweep_type"] == 'ff_gain':
            x_lbl = 'Ramp endpoints (DAC units)'
        elif self.cfg["sweep_type"] == 'ramp_length':
            x_lbl = 'Ramp half-lengths (us)'
        elif self.cfg["sweep_type"] == 'cycle_number':
            x_lbl = 'Number of cycles'
        plt.figure(figsize = (14, 14))
        plt.subplot(2, 2, 1)
        plt.plot(x_points, 100 * pop[:, 0, 0] / (pop[:, 0, 0] + pop[:, 0, 1]))
        plt.xlabel(x_lbl)
        plt.ylabel('P(assigned end 0 | assigned start 0)')
        plt.subplot(2, 2, 2)
        plt.plot(x_points, 100 * pop[:, 0, 1] / (pop[:, 0, 0] + pop[:, 0, 1]))
        plt.xlabel(x_lbl)
        plt.ylabel('P(assigned end 1 | assigned start 0)')
        plt.subplot(2, 2, 3)
        plt.plot(x_points, 100 * pop[:, 1, 0] / (pop[:, 1, 0] + pop[:, 1, 1]))
        plt.xlabel(x_lbl)
        plt.ylabel('P(assigned end 0 | assigned start 1)')
        plt.subplot(2, 2, 4)
        plt.plot(x_points, 100 * pop[:, 1, 1] / (pop[:, 1, 0] + pop[:, 1, 1]))
        plt.xlabel(x_lbl)
        plt.ylabel('P(assigned end 1 | assigned start 1)')

        if self.cfg["sweep_type"] == 'ff_gain':
            plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp half-length %.2f us, FF delay %.2f us. Confidence %.4f' %
                                      (self.cfg['yokoVoltage'], self.cfg['ff_ramp_length'],
                                       self.cfg['ff_delay'], self.cfg["confidence"]))
        elif self.cfg["sweep_type"] == 'ramp_length':
            plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp from %d to %d DAC, FF delay %.2f us. Confidence %.4f' %
                                      (self.cfg['yokoVoltage'], self.cfg['ff_ramp_start'], self.cfg['ff_ramp_stop'],
                                       self.cfg['ff_delay'], self.cfg["confidence"]))
        elif self.cfg["sweep_type"] == 'cycle_number':
            plt.suptitle(self.fname + '\nYoko voltage %.5f V, FF ramp from %d to %d DAC, FF ramp half-length %.2f us, FF delay %.2f us. Confidence %.4f' %
                                      (self.cfg['yokoVoltage'], self.cfg["ff_ramp_start"], self.cfg["ff_ramp_stop"],
                                       self.cfg['ff_ramp_length'], self.cfg['ff_delay'], self.cfg["confidence"]))
        plt.tight_layout()
        plt.subplots_adjust(top=0.92, hspace=0.05, wspace=0.2)

        plt.savefig(self.dname + 'prob_plot.png')
        print('Saved histograms at %s' % (self.dname + 'hist_plot.png'))

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