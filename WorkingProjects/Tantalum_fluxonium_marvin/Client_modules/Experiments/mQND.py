from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.MixedShots_analysis import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.QND_analysis import QND_analysis
import WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.SingleShot_ErrorCalc_2 as sse2
from tqdm.notebook import tqdm
import time

'''
@author: Jake Bryon, Parth Jatakia
'''

class LoopbackProgramQND(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ### set up the experiment updates, only runs it once
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

        ### Configure Resonator Tone
        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"])  # Declare the resonator channel
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch,
                                  ro_ch=cfg["ro_chs"][0])  # Convert to clock ticks
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]), )  # define the pulse

        ### Configure the Qubit Tone
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        qubit_ch = cfg["qubit_ch"]  # Get the qubit channel
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])  # Declare the qubit channel
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # Convert qubit length to clock ticks
        if 'apply_gf_pulse' in self.cfg:
            if self.cfg['apply_gf_pulse']:
                self.declare_gen(ch=cfg["qubit_gf_ch"], nqz=cfg["qubit_gf_nqz"])
                self.qubit_gf_freq = self.freq2reg(cfg["qubit_gf_freq"], gen_ch=cfg['qubit_gf_ch'])
                self.set_pulse_registers(ch=cfg["qubit_gf_ch"], style="const", freq=self.qubit_gf_freq, phase=0,
                                         gain=cfg["qubit_gf_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_gf_ch"]))
        # Define the qubit pulse
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0,
                                     gain=cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])
        else:
            print("define pi or flat top pulse")

        ### Declare ADC Readout
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        ### initial pulse
        self.sync_all(self.us2cycles(0.05))

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))

        if self.cfg.get('apply_gf_pulse', False):
            self.pulse(ch=self.cfg["qubit_gf_ch"])  # play probe pulse
            self.sync_all(self.us2cycles(0.05))

        ### cool the qubit
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]) )

        ### measure the state
        self.sync_all(self.us2cycles(0.01))
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1],
                start_src="internal", progress=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress,
                        readouts_per_experiment=2, save_experiments=[0,1])

        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        shots_i0 = np.array(self.get_raw())[0, :, :, 0, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q0 = np.array(self.get_raw())[0, :, :, 0, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_i1 = np.array(self.get_raw())[0, :, :, 1, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q1 = np.array(self.get_raw())[0, :, :, 1, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        i_0 = shots_i0[0]
        i_1 = shots_i1[0]
        q_0 = shots_q0[0]
        q_1 = shots_q1[0]


        return i_0, i_1, q_0, q_1




# ====================================================== #

class QNDmeas(ExperimentClass):
    """
    run a single shot expirement that utilizes a post selection process to handle thermal starting state
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.params = []
        self.quants = []
        self.tolerance = []
        self.keys = []
        self.index = 0
        self.total_size = 1
        self.mesh_grid = 0
        self.store = False

    def acquire(self, progress=False):
        ### pull the data from the single hots
        prog = LoopbackProgramQND(self.soccfg, self.cfg)
        i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

        ### save the data
        data = {'config': self.cfg, 'data': {'i_0': i_0, 'q_0': q_0,'i_1': i_1, 'q_1': q_1,}}
        self.data = data
        return data

    def process_data(self, data = None, **kwargs):
        if data is None:
            data = self.data

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]

        ### calculate the QND fidelity
        # Changing the way data is stored for kmeans
        iq_data = np.stack((i_0, q_0), axis=0)

        # Get centers of the data
        cen_num = self.cfg["cen_num"]
        centers = sse2.getCenters(iq_data, cen_num)

        if 'confidence_selection' in kwargs:
            confidence_selection = kwargs["confidence_selection"]
        else:
            confidence_selection = 0.99

        # Calculate the probability
        try :
            (state0_probs, state0_probs_err, state0_num,
             state1_probs, state1_probs_err, state1_num,
             i0_shots, q0_shots, i1_shots, q1_shots,
             fit_centers, fit_sigma,
             i0_0_shots, q0_0_shots, i0_1_shots, q0_1_shots) = QND_analysis(
                i_0, q_0, i_1, q_1, centers, confidence_selection=confidence_selection)
            qnd = (state0_probs[0] + state1_probs[1]) / 2
            qnd_err = np.sqrt(state0_probs_err[0] ** 2 + state1_probs_err[0] ** 2)
            center_distance = np.linalg.norm(fit_centers[0] - fit_centers[1])
            shared_sigma = np.mean(fit_sigma)
            snr = center_distance / shared_sigma if shared_sigma > 0 else np.nan
        except:
            state0_probs = [0,0]
            state0_probs_err = [0,0]
            state0_num = 0
            state1_probs = [0,0]
            state1_probs_err = [0,0]
            state1_num = 0
            i0_shots = []
            q0_shots = []
            i1_shots = []
            q1_shots = []
            i0_0_shots = []
            q0_0_shots = []
            i0_1_shots = []
            q0_1_shots = []
            qnd = 0
            qnd_err = 0
            fit_centers = centers
            fit_sigma = np.zeros(cen_num)
            center_distance = 0
            shared_sigma = np.nan
            snr = np.nan


        ### print out results
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
                print("QND SNR is {}".format(round(snr, 8)))

        ### Save the data
        update_data = {"data": {'centers': centers, 'confidence': confidence_selection, 'state0_probs': state0_probs,
                                'state0_probs_err': state0_probs_err, 'state0_num': state0_num,
                                'state1_probs': state1_probs, 'state1_probs_err': state1_probs_err,
                                'state1_num': state1_num, 'i0_shots': i0_shots, 'q0_shots': q0_shots,
                                'i0_0_shots': i0_0_shots, 'q0_0_shots': q0_0_shots,
                                'i0_1_shots': i0_1_shots, 'q0_1_shots': q0_1_shots,
                                'i1_shots':i1_shots, 'q1_shots':q1_shots, 'qnd': qnd, 'qnd_err': qnd_err,
                                'fit_centers': fit_centers, 'fit_sigma': fit_sigma,
                                'center_distance': center_distance, 'shared_sigma': shared_sigma, 'snr': snr, }
                       }
        data["data"] = data["data"] | update_data["data"]
        self.data = data
        return data

    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        try:
            i_0 = data["data"]["i_0"]
            q_0 = data["data"]["q_0"]
            i_1 = data["data"]["i_1"]
            q_1 = data["data"]["q_1"]
            i_0_0 = data["data"].get("i0_0_shots", [])
            q_0_0 = data["data"].get("q0_0_shots", [])
            i_0_1 = data["data"].get("i0_1_shots", [])
            q_0_1 = data["data"].get("q0_1_shots", [])
            i_1_0 = data["data"]["i0_shots"] # Shots in i_1 that originated in blob0
            q_1_0 = data["data"]["q0_shots"]  # Shots in q_1 that originated in blob0
            i_1_1 = data["data"]["i1_shots"]  # Shots in i_1 that originated in blob1
            q_1_1 = data["data"]["q1_shots"]  # Shots in i_1 that originated in blob1
            centers = data["data"]["centers"]
            fit_centers = data["data"].get("fit_centers", centers)
            fit_sigma = data["data"].get("fit_sigma", np.full(len(centers), np.nan))
            center_distance = data["data"].get("center_distance", np.nan)
            shared_sigma = data["data"].get("shared_sigma", np.nan)
            qnd = data["data"]["qnd"]
            qnd_err = data["data"]["qnd_err"]
            snr = data["data"]["snr"]
            confidence = data["data"]["confidence"]
            state1_0_probs = data["data"]["state0_probs"]   #
            state1_1_probs = data["data"]["state1_probs"]

            fig, axs = plt.subplots(nrows=2, ncols=2, figsize=[13, 10])
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
            ax_initial = axs[0, 0]
            im = ax_initial.imshow(np.rint(np.transpose(hist2d[0])),
                                   extent=[x_points[0], x_points[-1], y_points[0], y_points[-1]],
                                   origin='lower', aspect='auto')
            ax_initial.scatter(fit_centers[:, 0], fit_centers[:, 1], c="w", edgecolors="k",
                               s=45, zorder=5)
            for idx, sigma in enumerate(fit_sigma):
                if np.isfinite(sigma) and sigma > 0:
                    circle = plt.Circle((fit_centers[idx, 0], fit_centers[idx, 1]), sigma,
                                        fill=False, color="w", linewidth=1.5, zorder=4)
                    ax_initial.add_patch(circle)
            ax_initial.text(0.03, 0.97,
                            "SNR = {}\nDist = {}\nSigma = {}".format(
                                np.round(snr, 4), np.round(center_distance, 4), np.round(shared_sigma, 4)),
                            transform=ax_initial.transAxes, va="top", ha="left",
                            bbox=dict(facecolor="white", alpha=0.75, edgecolor="none"))
            ax_initial.set_xlabel('I')
            ax_initial.set_ylabel('Q')
            ax_initial.set_title("Initial readout with Gaussian fit")
            fig.colorbar(im, ax=ax_initial)

            # Plot scatter of the final measurement
            ax_final0 = axs[0, 1]
            ax_final0.scatter(i_1_0, q_1_0, s=0.2, c="tab:red", alpha=0.35, rasterized=True)
            ax_final0.scatter(fit_centers[:, 0], fit_centers[:, 1], c="w", edgecolors="k", s=45, label="Fit centers")
            ax_final0.set_xlabel('I')
            ax_final0.set_ylabel('Q')
            ax_final0.set_title("Final readout | initial blob 0 | P(1|0) = " + str(state1_0_probs[1].round(4)))
            ax_final0.legend(fontsize=8)

            ax_final1 = axs[1, 0]
            ax_final1.scatter(i_1_1, q_1_1, s=0.2, c="tab:blue", alpha=0.35, rasterized=True)
            ax_final1.scatter(fit_centers[:, 0], fit_centers[:, 1], c="w", edgecolors="k", s=45, label="Fit centers")
            ax_final1.set_xlabel('I')
            ax_final1.set_ylabel('Q')
            ax_final1.set_title("Final readout | initial blob 1 | P(0|1) = " + str(state1_1_probs[0].round(4)))
            ax_final1.legend(fontsize=8)

            iq_x_values = [np.ravel(i_0), np.ravel(i_1_0), np.ravel(i_1_1), np.ravel(fit_centers[:, 0])]
            iq_y_values = [np.ravel(q_0), np.ravel(q_1_0), np.ravel(q_1_1), np.ravel(fit_centers[:, 1])]
            if np.any(np.isfinite(fit_sigma)):
                sigma_pad = np.nanmax(fit_sigma)
                iq_x_values += [fit_centers[:, 0] - sigma_pad, fit_centers[:, 0] + sigma_pad]
                iq_y_values += [fit_centers[:, 1] - sigma_pad, fit_centers[:, 1] + sigma_pad]
            all_i = np.concatenate([np.asarray(vals, dtype=float) for vals in iq_x_values if len(vals) > 0])
            all_q = np.concatenate([np.asarray(vals, dtype=float) for vals in iq_y_values if len(vals) > 0])
            all_i = all_i[np.isfinite(all_i)]
            all_q = all_q[np.isfinite(all_q)]
            if all_i.size > 0 and all_q.size > 0:
                i_margin = 0.05 * max(np.ptp(all_i), 1e-12)
                q_margin = 0.05 * max(np.ptp(all_q), 1e-12)
                for ax in [ax_initial, ax_final0, ax_final1]:
                    ax.set_xlim(np.min(all_i) - i_margin, np.max(all_i) + i_margin)
                    ax.set_ylim(np.min(all_q) - q_margin, np.max(all_q) + q_margin)

            transition_matrix = np.array([
                [state1_0_probs[0], state1_0_probs[1]],
                [state1_1_probs[0], state1_1_probs[1]],
            ])
            ax_matrix = axs[1, 1]
            matrix_im = ax_matrix.imshow(transition_matrix, vmin=0, vmax=1, cmap="viridis")
            ax_matrix.set_xticks([0, 1])
            ax_matrix.set_xticklabels(["final 0", "final 1"])
            ax_matrix.set_yticks([0, 1])
            ax_matrix.set_yticklabels(["initial 0", "initial 1"])
            ax_matrix.set_title("Transition matrix")
            for row in range(transition_matrix.shape[0]):
                for col in range(transition_matrix.shape[1]):
                    value = transition_matrix[row, col]
                    text_color = "white" if value < 0.5 else "black"
                    ax_matrix.text(col, row, "{:.2f}%".format(100 * value),
                                   ha="center", va="center", color=text_color)
            fig.colorbar(matrix_im, ax=ax_matrix, label="Probability")

            data_information = ("Fridge Temperature = " + str(self.cfg["fridge_temp"]) + "mK, Yoko_Volt = "
                                + str(self.cfg["yokoVoltage_freqPoint"]) + "V, relax_delay = " +
                                str(self.cfg["relax_delay"]) + "us." + " Qubit Frequency = " + str(self.cfg["qubit_freq"])
                                + " MHz \n"+
                                "QND fidelity is " + str((qnd*100).round(4)) + " +/- " + str((qnd_err*100).round(4)) +
                                ", QND SNR is " + str(np.round(snr, 4)) +
                                ", Confidence threshold is " + str(confidence) + ".")

            plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
            plt.tight_layout()
            plt.savefig(self.iname, dpi=400)
            if plotDisp:
                plt.show()
            else:
                plt.close()
        except Exception as e:
            print("Error in display: ", e)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    def calculate_qnd(self, read_param, confidence_selection  = 0.99):
        params = {}
        for i in range(len(self.keys)):
            self.cfg[self.keys[i]] = read_param[i]
            params[self.keys[i]] = read_param[i]
        self.cfg["read_pulse_gain"] = int(self.cfg["read_pulse_gain"])
        self.index += 1

        if self.store :
            # refresh datetimestring
            self.new_file()

        # Get QND Data and process
        data = self.acquire()
        data = self.process_data(data=data,confidence_selection = confidence_selection )

        if self.store:
            self.display(data=data)
            self.save_data(data=data)
            self.save_config()

        # Get the quants
        quant = [data["data"]["qnd"], data["data"]["state0_probs"], data["data"]["state1_probs"],
                 data["data"]["snr"]]
        self.quants.append(quant)
        val = data["data"]["qnd"]
        self.params.append(params)

        # Pretty Print
        print("Parameters Measured are : ", params , " | Finished = ", self.index*100/self.total_size, " %")
        print("Quants Measured are : ", quant)

        return val

    def brute_search(self, keys, param_bounds, tolerance, store = False, confidence_selection = 0.99):
        # Resetting
        self.params = []
        self.quants = []
        self.tolerance = []
        self.index = 0
        self.total_size = 1
        self.store = store

        # Set base factor to 1
        self.keys = keys

        # Create parameter grid
        param_grid = []
        for key in keys:
            # Check if it is a tuple
            if type(param_bounds[key]) is not tuple:
                raise Exception("Parameter bounds is not a dictionary of tuples")

            self.tolerance.append(tolerance[key])
            param_grid.append(np.arange(param_bounds[key][0], param_bounds[key][1] + tolerance[key], tolerance[key]))
            self.total_size *= len(param_grid[-1])

        # Generate all combinations of parameters
        self.mesh_grid = np.meshgrid(*param_grid)
        param_combinations = np.array(np.meshgrid(*param_grid)).T.reshape(-1, len(keys))

        # Pretty Print
        print("~~~~~~ Starting the Brute Force Optimizer~~~~~~~")
        print("Ranges : ", param_bounds)
        print("------------------------------------")

        # Run brute force optimization
        best_val = -np.inf
        best_params = None
        for i, params in enumerate(param_combinations):
            value = self.calculate_qnd(params, confidence_selection = confidence_selection)
            if best_val < value:
                best_val = value
                best_params = self.params[-1]

        return best_val, best_params

    def brute_search_result_display(self, display = False):
        # Plotting
        if len(self.mesh_grid) == 1:
            X = self.mesh_grid[0]

            # Get quants
            qnd = []
            state_pop = []
            snr = []
            for i in range(len(self.quants)):
                qnd.append(self.quants[i][0])
                state_pop.append([self.quants[i][1], self.quants[i][2]])
                snr.append(self.quants[i][3] if len(self.quants[i]) > 3 else np.nan)

            qnd = np.array(qnd)
            state_pop = np.array(state_pop)
            snr = np.array(snr)

            # Plotting
            fig, axs = plt.subplots(4, 1, figsize=(7, 7))

            # plot the qnd
            ax = axs[0]
            art = ax.scatter(X, qnd)
            ax.set_title('QND value')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("Read Gain")

            # plot the SNR
            ax = axs[1]
            art = ax.scatter(X, snr)
            ax.set_title('SNR')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("SNR")

            # Plot the P(0|1)
            ax = axs[2]
            art = ax.scatter(X,state_pop[ :, 0, 1])
            ax.set_title('Probability of measuring in 1 given it was cooled to 0')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("Read Gain")

            # Plot the P(1|0)
            ax = axs[3]
            art = ax.scatter(X, state_pop[:, 1, 0])
            ax.set_title('Probability of measuring in 0 given it was cooled to 1')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("Read Gain")

            plt.tight_layout()
            plt.savefig(self.path_wDate + "total.png", dpi=400)
            if display:
                plt.show()
            else:
                plt.close()

        elif len(self.mesh_grid) == 2:
            X = read_length_grid = self.mesh_grid[0]
            Y = read_gain_grid = self.mesh_grid[1]

            # Get quants
            qnd = []
            state_pop = []
            snr = []
            for i in range(len(self.quants)):
                qnd.append(self.quants[i][0])
                state_pop.append([self.quants[i][1], self.quants[i][2]])
                snr.append(self.quants[i][3] if len(self.quants[i]) > 3 else np.nan)

            qnd = np.array(qnd).reshape(read_length_grid.shape[::-1]).T
            state_pop = np.array(state_pop).reshape(read_length_grid.shape[::-1] + (2, 2)).transpose((1, 0, 2, 3))
            snr = np.array(snr).reshape(read_length_grid.shape[::-1]).T

            # Plotting
            fig, axs = plt.subplots(4, 1, figsize=(7, 7))

            # Define colorscheme
            cmap = plt.get_cmap('viridis')

            # plot the qnd
            ax = axs[0]
            art = ax.pcolor(X, Y, qnd, shading='auto', cmap=cmap)
            plt.colorbar(art, ax=ax, label='z')
            ax.set_title('QND value')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("Read Gain")

            # plot the SNR
            ax = axs[1]
            art = ax.pcolor(X, Y, snr, shading='auto', cmap=cmap)
            plt.colorbar(art, ax=ax, label='z')
            ax.set_title('SNR')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("Read Gain")

            # Plot the P(0|1)
            ax = axs[2]
            art = ax.pcolor(X, Y, state_pop[:, :, 0, 1], shading='auto', cmap=cmap)
            plt.colorbar(art, ax=ax, label='z')
            ax.set_title('Probability of measuring in 1 given it was cooled to 0')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("Read Gain")

            # Plot the P(1|0)
            ax = axs[3]
            art = ax.pcolor(X, Y, state_pop[:, :, 1, 0], shading='auto', cmap=cmap)
            plt.colorbar(art, ax=ax, label='z')
            ax.set_title('Probability of measuring in 0 given it was cooled to 1')
            ax.set_xlabel('Read Length')
            ax.set_ylabel("Read Gain")

            plt.tight_layout()
            plt.savefig(self.path_wDate + "total.png", dpi=400)
            if display:
                plt.show()
