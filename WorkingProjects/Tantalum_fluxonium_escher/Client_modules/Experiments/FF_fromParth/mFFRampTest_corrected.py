###
# This file contains an NDAveragerProgram and ExperimentClass for testing the ramp speed of a fast flux pulse.
# The qubit is measured at some flux point, then, the flux is moved with a variable-time (linear) ramp to a different point.
# The qubit is then moved back to the original point and measured again.
# For the fluxonium experiment, the speed conditions are:
# * slower than any crossings (adiabatic), as well as the energy spliting between g and e. (speed compares to these squared)
# * faster than any decoherence channels
# Lev, June 2025: create file.
# Parth, Dec 2025 : Correct fidelity calculation and plotting functions
###
import sys

import matplotlib
from qick import NDAveragerProgram
from qick.averager_program import QickSweep

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.MixedShots_analysis import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.QND_analysis import QND_analysis
import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.SingleShot_ErrorCalc_2 as sse2
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
        print(f"FF ramp length is {self.cfg['ff_ramp_length']} us")
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

            self.cycle_numbers = np.rint(np.linspace(0, self.cfg["max_cycle_number"], num=self.cfg["cycle_number_expts"])).astype(int)
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


    def process(self, data = None, **kwargs):
        """
        Process the data acquired in the acquire step.
        Currently, just makes some plots of the raw IQ data.
        """
        if data is None:
            data = self.data
        i_arr = self.data['data']['i_arr']
        q_arr = self.data['data']['q_arr']

        if self.cfg["sweep_type"] == 'ramp_length':
            sweep_points = self.ramp_lengths
            sweep_name = 'Ramp length [us]'
        elif self.cfg["sweep_type"] == 'ff_gain':
            sweep_points = self.final_gains
            sweep_name = 'Final fast flux gain [DAC units]'
        elif self.cfg["sweep_type"] == 'cycle_number':
            sweep_points = self.cycle_numbers
            sweep_name = 'Number of cycles'
        else:
            raise ValueError("cfg[\"sweep_type\"] must be one of \'ramp_length\', \'ff_gain\', or \'cycle_number\'!")

        fid_list = []
        fid_err_list = []
        state0_probs_arr = np.zeros((sweep_points.size, 2))
        state1_probs_arr = np.zeros((sweep_points.size, 2))
        for i in range(sweep_points.size):
            i_0 = i_arr[i,:,0]
            q_0 = q_arr[i,:,0]
            i_1 = i_arr[i,:,1]
            q_1 = q_arr[i,:,1]

            ### calculate the QND fidelity
            # Changing the way data is stored for kmeans
            if i == 0 :
                iq_data = np.stack((i_0, q_0), axis=0)

                # Get centers of the data
                cen_num = self.cfg["cen_num"]
                centers = sse2.getCenters(iq_data, cen_num)

            if 'confidence' in self.cfg.keys():
                confidence_selection = self.cfg["confidence"]
            else:
                confidence_selection = 0.95

            # Calculate the probability
            (state0_probs, state0_probs_err, state0_num,
             state1_probs, state1_probs_err, state1_num,
             i0_shots, q0_shots, i1_shots, q1_shots) = QND_analysis(i_0, q_0, i_1, q_1, centers,
                                                                    confidence_selection=confidence_selection)
            qnd = (state0_probs[0] + state1_probs[1]) / 2
            fid_list.append(qnd)
            qnd_err = np.sqrt(state0_probs_err[0] ** 2 + state1_probs_err[0] ** 2)
            fid_err_list.append(qnd_err)

            state0_probs_arr[i, 0] = state0_probs[0]
            state0_probs_arr[i, 1] = state0_probs[1]
            state1_probs_arr[i, 0] = state1_probs[0]
            state1_probs_arr[i, 1] = state1_probs[1]

            if 'toPrint' in kwargs:
                if kwargs['toPrint']:
                    print('Note: labeling of states does not necessarily reflect actual qubit state')
                    print('Number of 0 state samples ' + str(round(state0_num, 1)))
                    print('Number of 1 state samples ' + str(round(state1_num, 1)))
                    for idx in range(2):
                        print("Probability of state 0 in state {} is {} +/- {}".format(
                            idx, round(100 * state0_probs[idx], 8), round(100 * state0_probs_err[0], 8))
                        )
                        print("Probability of state 1 state {} is {} +/- {}".format(
                            idx, round(100 * state1_probs[idx], 8), round(100 * state1_probs_err[0], 8))
                        )
                    print("QND fidelity is {} +/- {}".format(round(100 * qnd, 8), round(100 * qnd_err, 8)))

        # Fit the fidelity curve to A*P^x + B if sweep over cycle number
        if self.cfg["sweep_type"] == 'cycle_number':
            from scipy.optimize import curve_fit

            def fidelity_decay(x, A, B, P):
                return A * P**x + B

            try :
                popt, pcov = curve_fit(fidelity_decay,
                                       sweep_points,
                                       fid_list,
                                       p0=[0.5, 0.5, 0.9],
                                       sigma = np.array(fid_err_list),
                                       absolute_sigma = True,
                                       bounds=([0, 0, 0], [1, 1, 1]))
                A_fit, B_fit, P_fit = popt
                perr = np.sqrt(np.diag(pcov))
                A_err, B_err, P_err = perr

                print("Fitted parameters for fidelity decay over cycle number:")
                print("A = {:.4f} +/- {:.4f}".format(A_fit, A_err))
                print("B = {:.4f} +/- {:.4f}".format(B_fit, B_err))
                print("P = {:.4f} +/- {:.4f}".format(P_fit, P_err))
            except Exception as e:
                print("Fitting fidelity decay failed:", e)
                popt, pcov = None, None


        # Update data dictionary
        update_data = {'fid_list': np.array(fid_list),
                       'fid_err_list': np.array(fid_err_list),
                       'state0_probs_arr': state0_probs_arr,
                       'state1_probs_arr': state1_probs_arr,
                       'centers': centers,
                       'popt': popt if self.cfg["sweep_type"] == 'cycle_number' else None,
                       'pcov': pcov if self.cfg["sweep_type"] == 'cycle_number' else None}
        self.data['data'] = self.data['data'] | update_data
        return self.data

    def display(self, data = None, plotDisp = True, indx_to_plot = 0, **kwargs):
        if data is None:
            data = self.data

        i_arr = self.data['data']['i_arr']
        q_arr = self.data['data']['q_arr']
        fid_list = self.data['data']['fid_list']
        fid_err_list = self.data['data']['fid_err_list']
        state0_probs_arr = self.data['data']['state0_probs_arr']
        state1_probs_arr = self.data['data']['state1_probs_arr']
        centers = self.data['data']['centers']
        popt = self.data['data']['popt']
        pcov = self.data['data']['pcov']
        if self.cfg["sweep_type"] == 'ramp_length':
            sweep_points = self.ramp_lengths
            sweep_name = 'Ramp length [us]'
        elif self.cfg["sweep_type"] == 'ff_gain':
            sweep_points = self.final_gains
            sweep_name = 'Final fast flux gain [DAC units]'
        elif self.cfg["sweep_type"] == 'cycle_number':
            sweep_points = self.cycle_numbers
            sweep_name = 'Number of cycles'
        else:
            raise ValueError("cfg[\"sweep_type\"] must be one of \'ramp_length\', \'ff_gain\', or \'cycle_number\'!")

        # Figure 1 : For the first sweep point, show the histograms and scatter plots
        i_0 = i_arr[indx_to_plot,:,0]
        q_0 = q_arr[indx_to_plot,:,0]
        i_1 = i_arr[indx_to_plot,:,1]
        q_1 = q_arr[indx_to_plot,:,1]
        # Separate final points based on initial state
        if 'confidence' in self.cfg.keys():
            confidence_selection = self.cfg["confidence"]
        else:
            confidence_selection = 0.95

        # Calculate the probability
        (state1_0_probs, state0_probs_err, state0_num,
         state1_1_probs, state1_probs_err, state1_num,
         i_1_0, q_1_0, i_1_1, q_1_1) = QND_analysis(i_0, q_0, i_1, q_1, centers,
                                                                confidence_selection=confidence_selection)

        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=[15, 6], width_ratios=[1.2, 1, 1])
        # Plot histogram of the initial measurement
        if "bin_size" in kwargs:
            bin_size = kwargs["bin_size"]
        else:
            bin_size = 151
        iq_data = np.stack((i_0, q_0), axis=0)
        hist2d = sse2.createHistogram(iq_data, bin_size)
        xedges = hist2d[1]
        yedges = hist2d[2]
        x_points = (xedges[1:] + xedges[:-1]) / 2
        y_points = (yedges[1:] + yedges[:-1]) / 2
        im = axs[0].imshow(np.rint(np.transpose(hist2d[0])), extent=[x_points[0], x_points[-1], y_points[0], y_points[-1]],
                           origin='lower', aspect='auto')
        axs[0].scatter(centers[0, 0], centers[0, 1], c="k", label="Blob 0")
        axs[0].scatter(centers[1, 0], centers[1, 1], c="w", label="Blob 1")
        axs[0].set_xlabel('I')
        axs[0].set_ylabel('Q')
        axs[0].set_title("Single Shot Histogram of the initial state")
        axs[0].legend()
        fig.colorbar(im, ax=axs[0])

        # Plot scatter of the final measurement
        axs[1].scatter(i_1_0, q_1_0, s=0.1)
        axs[1].scatter(centers[0, 0], centers[0, 1], c="k", label="Blob 0")
        axs[1].scatter(centers[1, 0], centers[1, 1], c="w", label="Blob 1")
        axs[1].set_xlabel('I')
        axs[1].set_ylabel('Q')
        axs[1].set_title("Begin in Blob 0 | P( Other blob ) = " + str(state1_0_probs[1].round(4)))
        axs[1].legend()

        axs[2].scatter(i_1_1, q_1_1, s=0.1)
        axs[2].scatter(centers[0, 0], centers[0, 1], c="k", label="Blob 0")
        axs[2].scatter(centers[1, 0], centers[1, 1], c="w", label="Blob 1")
        axs[2].set_xlabel('I')
        axs[2].set_ylabel('Q')
        axs[2].set_title("Begin in Blob 1 | P( Other blob ) = " + str(state1_1_probs[0].round(4)))
        axs[2].legend()

        data_information = ("Yoko_Volt = " + str(self.cfg["yokoVoltage"]) + "V,  Qubit Frequency = " + str(self.cfg["qubit_freq"])
                            + " MHz \n"+
                            "QND fidelity is " + str((fid_list[0]*100).round(4)) + " +/- " + str((fid_err_list[0]*100).round(4)) +
                            ", Confidence threshold is " + str(confidence_selection) + ".")

        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        plt.savefig(self.path_wDate + "_sweep0_gauss.png", dpi=400)
        if plotDisp:
            plt.show(block=False)
            plt.pause(2)
        else:
            plt.close()

        # Figure 2 : Plot fidelity vs sweep parameter and state probabilities
        # Make a plot with three subplots :
        # Subplot 1 : Fidelity vs sweep parameter
        # Subplot 2 : state0_probs_arr[:,0] and state1_probs_arr[:,1] vs sweep parameter
        # Subplot 3 : state0_probs_arr[:,1] and state1_probs_arr[:,0] vs sweep parameter
        fig2, axs2 = plt.subplots(nrows=1, ncols=3, figsize=[18, 5])
        axs2[0].errorbar(sweep_points, fid_list, yerr=fid_err_list, fmt='o-')
        if self.cfg["sweep_type"] == 'cycle_number' and popt is not None and pcov is not None:
            A_fit, B_fit, P_fit = popt
            y_fit = A_fit * P_fit**sweep_points + B_fit
            axs2[0].plot(sweep_points, y_fit, 'r--', label='Fit: A*P^x + B')
            axs2[0].legend()
        axs2[0].set_xlabel(sweep_name)
        axs2[0].set_ylabel('FF Fidelity')
        axs2[0].set_title('FF Fidelity vs ' + sweep_name)
        axs2[0].grid()
        axs2[1].errorbar(sweep_points, state0_probs_arr[:,0], yerr=0, fmt='o-', label='Start in 0 -> Measured 0')
        axs2[1].errorbar(sweep_points, state1_probs_arr[:,1], yerr=0, fmt='o-', label='Start in 1 -> Measured 1')
        axs2[1].set_xlabel(sweep_name)
        axs2[1].set_ylabel('Probability')
        axs2[1].set_title('Probability of measuring same state vs ' +sweep_name)
        axs2[1].legend()
        axs2[1].grid()
        axs2[2].errorbar(sweep_points, state0_probs_arr[:,1], yerr=0, fmt='o-', label='Start in 0 -> Measured 1')
        axs2[2].errorbar(sweep_points, state1_probs_arr[:,0], yerr=0, fmt='o-', label='Start in 1 -> Measured 0')
        axs2[2].set_xlabel(sweep_name)
        axs2[2].set_ylabel('Probability')
        axs2[2].set_title('Probability of measuring different state vs ' +sweep_name)
        axs2[2].legend()
        axs2[2].grid()
        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' )
        plt.tight_layout()
        plt.savefig(self.path_wDate + "_sweep_fidelity.png", dpi=400)
        if plotDisp:
            plt.show(block=False)
            plt.pause(2)
        else:
            plt.close()



