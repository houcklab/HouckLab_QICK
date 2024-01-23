from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.MixedShots_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.QND_analysis import QND_analysis
import WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.SingleShot_ErrorCalc_2 as sse2
from scipy import constants as ct
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
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"],
                         ro_ch=cfg["ro_chs"][0])  # Declare the resonator channel
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
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug,
                        readouts_per_experiment=2, save_experiments=[0,1])

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)

        i_0 = shots_i0[0::2]
        i_1 = shots_i0[1::2]
        q_0 = shots_q0[0::2]
        q_1 = shots_q0[1::2]

        return i_0, i_1, q_0, q_1




# ====================================================== #

class QNDmeas(ExperimentClass):
    """
    run a single shot expirement that utilizes a post selection process to handle thermal starting state
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
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
        cen_num = 2
        centers = sse2.getCenters(iq_data, cen_num)

        if 'confidence_selection' in kwargs:
            confidence_selection = kwargs["confidence_selection"]
        else:
            confidence_selection = 0.9

        # Calculate the probability
        (state0_probs, state0_probs_err, state0_num,
         state1_probs, state1_probs_err, state1_num,
         i0_shots, q0_shots, i1_shots, q1_shots) = QND_analysis(i_0, q_0, i_1, q_1, centers,
                                                                confidence_selection=confidence_selection)
        qnd = (state0_probs[0] + state1_probs[1]) / 2
        qnd_err = np.sqrt(state0_probs_err[0] ** 2 + state1_probs_err[0] ** 2)


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

        ### Save the data
        update_data = {"data": {'centers': centers, 'confidence': confidence_selection, 'state0_probs': state0_probs,
                                'state0_probs_err': state0_probs_err, 'state0_num': state0_num,
                                'state1_probs': state1_probs, 'state1_probs_err': state1_probs_err,
                                'state1_num': state1_num, 'i0_shots': i0_shots, 'q0_shots': q0_shots,
                                'i1_shots':i1_shots, 'q1_shots':q1_shots, 'qnd': qnd, 'qnd_err': qnd_err, }
                       }
        data["data"] = data["data"] | update_data["data"]
        self.data = data
        return data

    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]
        i_1_0 = data["data"]["i0_shots"] # Shots in i_1 that originated in blob0
        q_1_0 = data["data"]["q0_shots"]  # Shots in q_1 that originated in blob0
        i_1_1 = data["data"]["i1_shots"]  # Shots in i_1 that originated in blob1
        q_1_1 = data["data"]["q1_shots"]  # Shots in i_1 that originated in blob1
        centers = data["data"]["centers"]
        qnd = data["data"]["qnd"]
        qnd_err = data["data"]["qnd_err"]
        confidence = data["data"]["confidence"]
        state1_0_probs = data["data"]["state0_probs"]   #
        state1_1_probs = data["data"]["state1_probs"]

        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=[18, 8], width_ratios=[1.2, 1, 1])
        # Plot histogram of the initial measurement
        if "bin_size" in kwargs:
            bin_size = kwargs["bin_size"]
        else:
            bin_size = 51
        iq_data = np.stack((i_0, q_0), axis=0)
        hist2d = sse2.createHistogram(iq_data, bin_size)
        xedges = hist2d[1]
        yedges = hist2d[2]
        x_points = (xedges[1:] + xedges[:-1]) / 2
        y_points = (yedges[1:] + yedges[:-1]) / 2
        im = axs[0].imshow(np.transpose(hist2d[0]), extent=[x_points[0], x_points[-1], y_points[0], y_points[-1]],
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
        axs[1].set_title("P( End in 1 | Begin in 0 ) = " + str(state1_0_probs[1].round(4)) + " || T (mK) = " + str((-ct.h*1000*self.cfg["qubit_freq"]*1e6/(ct.k*np.log(state1_0_probs[1]))).round(1)))
        axs[1].legend()

        axs[2].scatter(i_1_1, q_1_1, s=0.1)
        axs[2].scatter(centers[0, 0], centers[0, 1], c="k", label="Blob 0")
        axs[2].scatter(centers[1, 0], centers[1, 1], c="w", label="Blob 1")
        axs[2].set_xlabel('I')
        axs[2].set_ylabel('Q')
        axs[2].set_title("P( End in 0 | Begin in 1 ) = " + str(state1_1_probs[0].round(4)) + " || T (mk) = " + str((-ct.h*1000*self.cfg["qubit_freq"]*1e6/(ct.k*np.log(state1_1_probs[0]))).round(1)))
        axs[2].legend()

        data_information = ("Fridge Temperature = " + str(self.cfg["fridge_temp"]) + "mK, Yoko_Volt = "
                            + str(self.cfg["yokoVoltage_freqPoint"]) + "V, relax_delay = " +
                            str(self.cfg["relax_delay"]) + "us." + " Qubit Frequency = " + str(self.cfg["qubit_freq"])
                            + " MHz \n"+
                            "QND fidelity is " + str((qnd*100).round(4)) + " +/- " + str((qnd_err*100).round(4)) +
                            ", Confidence threshold is " + str(confidence) + ".")

        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        plt.savefig(self.iname, dpi=400)
        if plotDisp:
            plt.show()
        plt.close()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


