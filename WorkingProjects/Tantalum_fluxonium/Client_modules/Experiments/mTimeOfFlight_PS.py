from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.MixedShots_analysis import *
import WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.SingleShot_ErrorCalc_2 as sse2
from tqdm.notebook import tqdm
import time

'''
@author: Parth Jatakia
'''

class LoopbackProgramTOFPS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ### set up the experiment updates, only runs it once
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

        ### Configuring Resonator Tone
        res_ch = cfg["res_ch"]
        self.read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=self.read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"]),
                                 )  # mode="periodic")

        ### Configuring Qubit Tone
        self.q_rp = self.ch_page(cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        qubit_ch = cfg["qubit_ch"]
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=qubit_ch)
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"]),
                           length=self.us2cycles(cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(cfg["sigma"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"]),
                           length=self.us2cycles(cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(cfg["sigma"]) * 4 + self.us2cycles(cfg["flat_top_length"])
        else:
            print("define pi or flat top pulse")

        ### Configuring the ADC readout
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"]), gen_ch=cfg["res_ch"])

        ### If offset is more than max_pulse_length
        self.num_pulses = int((self.cfg["offset"]) / self.cfg["max_pulse_length"]) + 2
        # print(self.num_pulses)
        self.synci(200)  # give processor some time to configure pulses


    def body(self):
        # Pause
        self.sync_all(self.us2cycles(0.01))

        # Qubit tone to create a mixed state
        self.pulse(ch=self.cfg["qubit_ch"])

        # Pause
        self.sync_all(self.us2cycles(0.01))

        # Post Selection Pulse
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))

        # Pause
        self.sync_all(self.us2cycles(0.01))

        # Redefining pulses and adc
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.read_freq,
                                 phase=0, gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["max_pulse_length"]), )
        # Redefine the readout length
        self.declare_readout(ch=self.cfg["ro_chs"][0], freq=self.cfg["read_pulse_freq"],
                             length=self.us2cycles(self.cfg["read_length_tof"]), gen_ch=self.cfg["res_ch"])

        # Pause
        self.sync_all(self.us2cycles(0.01))

        # Multiple Pulses
        for i in range(self.num_pulses):
            self.pulse(ch=self.cfg["res_ch"])

        # Pause
        self.synci(self.us2cycles(self.cfg["offset"]))

        # Pulse the cavity -> after an offset read the adc
        self.trigger(adcs=[0], adc_trig_offset=self.us2cycles(0.005))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2,
                save_experiments=[0, 1],
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug,
                        readouts_per_experiment=2, save_experiments=[0, 1])

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0] / self.us2cycles(self.cfg['read_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0] / self.us2cycles(self.cfg['read_length'], ro_ch=0)

        i_0 = shots_i0[0::2]
        i_1 = shots_i0[1::2]
        q_0 = shots_q0[0::2]
        q_1 = shots_q0[1::2]

        return i_0, i_1, q_0, q_1


# ====================================================== #

class TimeOfFlightPS(ExperimentClass):
    """
    run a single shot expirement that utilizes a post selection process to handle thermal starting state
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        # Create an array to store all data
        i_0_arr = np.full((self.cfg["offset_num"], int(self.cfg["shots"])), np.nan)
        q_0_arr = np.full((self.cfg["offset_num"], int(self.cfg["shots"])), np.nan)
        i_1_arr = np.full((self.cfg["offset_num"], int(self.cfg["shots"])), np.nan)
        q_1_arr = np.full((self.cfg["offset_num"], int(self.cfg["shots"])), np.nan)

        # Create a for-loop to collect the data for different offsets
        offset_vec = np.linspace(self.cfg["offset_start"], self.cfg["offset_end"], self.cfg["offset_num"])

        for i in range(offset_vec.size):
            self.cfg["offset"] = offset_vec[i]
            prog = LoopbackProgramTOFPS(self.soccfg, self.cfg)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                              save_experiments=[0, 1])
            i_0_arr[i,:] = i_0
            i_1_arr[i,:] = i_1
            q_0_arr[i,:] = q_0
            q_1_arr[i,:] = q_1

        data = {'config': self.cfg, 'data': {"offset_vec": offset_vec,
                                             "i_0" : i_0_arr, "i_1" : i_1_arr,
                                             "q_0" : q_0_arr, "q_1" : q_1_arr}
                }
        self.data = data
        return data

    def processData(self, data = None, **kwargs):
        if data is None:
            data = self.data

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        # Creating empty data
        avgi = np.zeros((cen_num, i_0.shape[0]))
        stdi = np.zeros((cen_num, i_0.shape[0]))
        avgq = np.zeros((cen_num, i_0.shape[0]))
        stdq = np.zeros((cen_num, i_0.shape[0]))

        # Creating other data. Use this wisely. Only if things are not behaving well
        if 'save_all' in kwargs:
            if kwargs['save_all'] == True:
                centers_list = []
                gaussians_list = []
                x_points_list = []
                y_points_list = []

        # For loop around the offset num
        for indx_off in range(i_0.shape[0]):

            # TODO : Write the code for general number of centers
            ### Perform post selection for the initial data for two centers
            ### by selecting points withing some confidence bound.
            iq_data_0 = np.stack((i_0[indx_off, :], q_0[indx_off, :]), axis=0)
            iq_data_1 = np.stack((i_1[indx_off, :], q_1[indx_off, :]), axis=0)

            if indx_off == 0:
                # Get centers
                centers = sse2.getCenters(iq_data_0, cen_num)

            # Fit Gaussian
            bin_size = 25
            hist2d = sse2.createHistogram(iq_data_0, bin_size)
            gaussians, popt, x_points, y_points = sse2.findGaussians(hist2d, centers, cen_num)

            # Get probability function
            pdf = sse2.calcPDF(gaussians)

            # Calculate the probability
            probability = np.zeros((cen_num, iq_data_0.shape[1]))
            for i in range(cen_num):
                for j in range(iq_data_0.shape[1]):
                    # find the x,y point closest to the i,q point
                    indx_i = np.argmin(np.abs(x_points - iq_data_0[0, j]))
                    indx_q = np.argmin(np.abs(y_points - iq_data_0[1, j]))
                    # Calculate the probability
                    probability[i, j] = pdf[i][indx_i,indx_q]

            # Find the sorted data
            sorted_prob = np.zeros((cen_num, iq_data_0.shape[1]))
            sorted_data_0 = np.zeros((cen_num,) + iq_data_0.shape)
            sorted_data_1 = np.zeros((cen_num,) + iq_data_1.shape)

            for i in range(cen_num):
                sorted_indx = np.argsort(-probability[i, :])
                sorted_prob[i, :] = probability[i, sorted_indx]
                sorted_data_0[i, :, :] = iq_data_0[:, sorted_indx]
                sorted_data_1[i, :, :] = iq_data_1[:, sorted_indx]

            # Selecting the points in the confidence regime and averaging them
            if 'confidence' in kwargs:
                confidence = kwargs["confidence"]
            else:
                confidence = 0.99

            for i in range(cen_num):
                indx_confidence = np.argmin(np.abs(sorted_prob[i, :] - confidence))
                avgi[i,indx_off] = np.mean(sorted_data_1[i, 0, 0:indx_confidence+1])
                stdi[i,indx_off] = np.std(sorted_data_1[i, 0, 0:indx_confidence+1])
                avgq[i,indx_off] = np.mean(sorted_data_1[i, 1, 0:indx_confidence+1])
                stdq[i,indx_off] = np.std(sorted_data_1[i, 1, 0:indx_confidence+1])

            if 'save_all' in kwargs:
                if kwargs['save_all'] == True:
                    centers_list.append(centers)
                    gaussians_list.append(gaussians)
                    x_points_list.append(x_points)
                    y_points_list.append(y_points)

        update_data = {"data" : {"avgi" : avgi, "avgq" : avgq, "stdi" : stdi, "stdq": stdq}}
        data["data"] = data["data"] | update_data["data"]

        if 'save_all' in kwargs:
            if kwargs['save_all'] == True:
                update_data = {"temp_data" : {"centers" : centers_list, "gaussians" : gaussians_list,
                               "x_points" : x_points_list, "y_points" : y_points_list}}
                data = data | update_data

        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, ran=None, **kwargs):
        if data is None:
            data = self.data

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        # Extracting data
        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        offset_vec = data["data"]["offset_vec"]
        avgi = data["data"]["avgi"]
        avgq = data["data"]["avgq"]
        stdi = data["data"]["stdi"]
        stdq = data["data"]["stdq"]

        # Choice of color
        colorlist = [
            'firebrick',
            'midnightblue',
            'coral',
            'darkolivegreen'
        ]

        if "save_all" in kwargs:
            if kwargs['save_all'] == True:
                centers = data["temp_data"]["centers"]
                for i in range(i_0.shape[0]):
                    plt.figure()
                    plt.scatter(i_0[i,:], q_0[i, :], s=0.1)
                    plt.scatter(centers[i][:, 0], centers[i][ :, 1], s=10, c='r')
                    plt.xlabel('I')
                    plt.ylabel('Q')
                    plt.tight_layout()
                    plt.savefig(self.iname[0:-4] + "_offsetslice_" + str(i) + '_centers.png', dpi = 300)
                    plt.close()

        fig, axs = plt.subplots(2, 1, figsize=[12, 6])
        for i in range(cen_num):
            axs[0].errorbar(offset_vec, avgi[i], stdi[i], fmt = 'o-', label="Starts in Blob " + str(i), c=colorlist[i])
            axs[1].errorbar(offset_vec, avgq[i], stdq[i], fmt = 'o-', label="Starts in Blob " + str(i), c=colorlist[i])
        name = ["I-Data", "Q-data"]
        for i in range(2):
            axs[i].set_xlabel("time (in us)")
            axs[i].set_title(name[i])
            axs[i].set_ylabel("ADC units")
            axs[i].legend()
        data_information = "Read_pulse_gain = " + str(self.cfg["read_pulse_gain"]) + " , Read length of t.o.f. = " + str(self.cfg["read_length_tof"]) + " us, read freq = " + str(self.cfg["read_pulse_freq"])
        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        plt.savefig(self.iname, dpi =400)
        if plotDisp:
            plt.show()
        plt.close()
        return

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
