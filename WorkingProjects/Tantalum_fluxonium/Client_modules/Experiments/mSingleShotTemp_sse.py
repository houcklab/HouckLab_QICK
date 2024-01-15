from qick import *
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2
from matplotlib.colors import LogNorm
'''
@author: Parth Jatakia
'''


class LoopbackProgramSingleShot_sse(RAveragerProgram):
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
        # Initial pause
        self.sync_all(self.us2cycles(0.01))
        if self.cfg["initialize_pulse"]:
            if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"] and self.cfg["initialize_pulse"]:
                self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                             width=self.cfg["trig_len"])  # trigger for switc
            self.pulse(ch=self.cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
            self.measure(pulse_ch=self.cfg["res_ch"],
                         adcs=[0],
                         adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                         wait=True,
                         syncdelay=self.us2cycles(self.cfg["relax_delay"]))
            self.measure(pulse_ch=self.cfg["res_ch"],
                         adcs=[0],
                         adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                         wait=True,
                         syncdelay=self.us2cycles(0.01))
        else:
            self.measure(pulse_ch=self.cfg["res_ch"],
                         adcs=[0],
                         adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                         wait=True,
                         syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)
        return self.collect_shots()

    def collect_shots(self):
        if self.cfg["initialize_pulse"]:
            shots_i0 = self.di_buf[0] / self.us2cycles(self.cfg['read_length'], ro_ch=0)
            shots_q0 = self.dq_buf[0] / self.us2cycles(self.cfg['read_length'], ro_ch=0)

            i_0 = shots_i0[0::2]
            i_1 = shots_i0[1::2]
            q_0 = shots_q0[0::2]
            q_1 = shots_q0[1::2]

            return i_0, i_1, q_0, q_1
        else:
            shots_i0 = self.di_buf[0] / self.us2cycles(self.cfg['read_length'], ro_ch=0)
            shots_q0 = self.dq_buf[0]/ self.us2cycles(self.cfg['read_length'], ro_ch=0)
            return shots_i0, shots_q0


# ====================================================== #

class SingleShotSSE(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self):
        # pull the data from the single shots
        prog = LoopbackProgramSingleShot_sse(self.soccfg, self.cfg)
        if self.cfg["initialize_pulse"]:
            i_0,  shots_i, q_0, shots_q = prog.acquire(self.soc, load_pulses=True)
            data = {'config': self.cfg, 'data': {'i_arr': shots_i, 'q_arr': shots_q, "i_0": i_0, "q_0": q_0}}
            self.data = data
        else:
            shots_i, shots_q = prog.acquire(self.soc, load_pulses=True)
            data = {'config': self.cfg, 'data': {'i_arr': shots_i, 'q_arr': shots_q}}
        self.data = data
        return data

    def process_data(self, data = None, **kwargs ):
        """
        kwargs :
        1. cen_num : number of center
        2. save_all : save intermediate processed data
        """
        if data is None:
            data = self.data

        i_arr = data["data"]["i_arr"]
        q_arr = data["data"]["q_arr"]

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        iq_data = np.stack((i_arr,q_arr), axis = 0)

        # Check if bin_size is given as input
        if 'bin_size' in kwargs:
            bin_size = kwargs['bin_size']
        else:
            bin_size = 25

        # Get the centers
        if 'centers' in kwargs:
            self.centers = kwargs["centers"]
        elif self.cfg["initialize_pulse"]:
            i_0 = data["data"]["i_0"]
            q_0 = data["data"]["q_0"]
            iq_data_0 = np.stack((i_0,q_0), axis = 0)
            self.centers = sse2.getCenters(iq_data_0, cen_num = cen_num)
            hist2d_0 = sse2.createHistogram(iq_data_0, bin_size)
            gaussians_0, popt_0, x_points_0, y_points_0 = sse2.findGaussians(hist2d_0, self.centers, cen_num)
            pdf_0 = sse2.calcPDF(gaussians_0)
            update_data = {"data" : { "gaussians_0" : gaussians_0, "x_points_0" : x_points_0, "y_points_0": y_points_0, "pdf_0": pdf_0}}
            data["data"] = data["data"] | update_data["data"]

            # Get the sigma
            sigma_0 = []
            for i in range(cen_num):
                sigma_0.append(popt_0[3 + i * 4])

            # Calculate the probability and centers
            hist2d = sse2.createHistogram(iq_data, bin_size)

            # Find the fit parameters for the double 2D Gaussian
            self.gaussians, self.popt, self.x_points, self.y_points = sse2.findGaussians(hist2d, self.centers, cen_num, sigma = sigma_0)

        else:
            self.centers = sse2.getCenters(iq_data, cen_num = cen_num)

            # Calculate the probability and centers
            hist2d = sse2.createHistogram(iq_data, bin_size)

            # Find the fit parameters for the double 2D Gaussian
            self.gaussians, self.popt, self.x_points, self.y_points = sse2.findGaussians(hist2d, self.centers, cen_num)

        # Calculate the probability function
        self.pdf = sse2.calcPDF(self.gaussians)

        # Calculate the expected probability
        num_samples_in_gaussian = sse2.calcNumSamplesInGaussian(hist2d, self.pdf, cen_num)
        num_samples_in_gaussian_std = sse2.calcNumSamplesInGaussianSTD(hist2d, self.pdf, cen_num)

        prob, prob_std = sse2.calcProbability(num_samples_in_gaussian, num_samples_in_gaussian_std, cen_num)

        tempr, tempr_std = sse2.findTempr(prob, prob_std, self.cfg["qubit_freq"]*1e6)

        update_data = {"data": {"prob" : prob, "prob_std" : prob_std, "tempr": tempr, "tempr_std": tempr_std,
                                "centers": self.centers, "hist2d": hist2d[0],"xedges": hist2d[1],
                                "yedges": hist2d[2]}}
        data["data"] = data["data"] | update_data["data"]
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, save_fig=True, ran=None, **kwargs):
        if data is None:
            data = self.data

        i_arr = data["data"]["i_arr"]
        q_arr = data["data"]["q_arr"]
        prob = data["data"]["prob"]
        prob_std = data["data"]["prob_std"]
        tempr = data["data"]["tempr"]
        tempr_std = data["data"]["tempr_std"]
        centers = data["data"]["centers"]
        hist2d = data["data"]["hist2d"]
        xedges = data["data"]["xedges"]
        yedges = data["data"]["yedges"]

        fig = plt.figure(figsize=[18, 10])
        gs = gridspec.GridSpec(1, 2, width_ratios=[1, 1])
        axs = [plt.subplot(gs[0]), plt.subplot(gs[1])]
        if self.cfg["initialize_pulse"]:
            i_0 = data["data"]["i_0"]
            q_0 = data["data"]["q_0"]
            iq_data_0 = np.stack((i_0, q_0), axis=0)
            pdf_0 = data["data"]["pdf_0"]
            gaussians_0 = data["data"]["gaussians_0"]
            x_points = data["data"]["x_points_0"]
            y_points = data["data"]["y_points_0"]
            sse2.plotFitAndData(pdf_0, gaussians_0, x_points, y_points, self.centers,iq_data_0, fig, axs[0] )
        else:
            axs[0].scatter(i_arr, q_arr, s=0.1)
            axs[0].scatter(centers[:,0], centers[:,1])
            axs[0].set_xlabel('I')
            axs[0].set_ylabel('Q')
            axs[0].set_title("Single Shot Data")

        iq_data = np.stack((i_arr, q_arr), axis = 0)
        sse2.plotFitAndData(self.pdf, self.gaussians, self.x_points, self.y_points, self.centers, iq_data, fig, axs[1])
        axs[1].set_title("Single Shot Histogram")


        data_information = ("Fridge Temperature = " + str(self.cfg["fridge_temp"]) + "mK, Yoko_Volt = "
                            + str(self.cfg["yokoVoltage_freqPoint"]) + "V, relax_delay = " + str(
                            self.cfg["relax_delay"]) + "us." + " Qubit Frequency = " + str(self.cfg["qubit_freq"])
                            + " MHz \n"+
                            "Excited State Population = " + str(np.max(prob).round(4)) + " +/- "
                            + str(prob_std[np.argmax(prob)].round(4)) + ". Temperature of excited state = "
                            + str(tempr.round(4)) + " +/- " + str(tempr_std.round(5)) + " K")
        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        plt.savefig(self.iname, dpi =400)
        if plotDisp:
            plt.show()
        plt.close()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data["data"])
