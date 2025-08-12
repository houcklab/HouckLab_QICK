import math

import matplotlib
import numpy as np
from tqdm import tqdm

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotProgram

matplotlib.use("Qt5agg")
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.hist_analysis import *
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2


# ====================================================== #
class SingleShotDecimated(ExperimentClass):
    """
    SingleShot experiment that takes decimated data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.threshold = []
        self.angle = []
        self.ne_contrast = []
        self.ng_contrast = []

        self.confusion_matrix = []

    def acquire(self, progress=False):
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1
        if "readout_length" in self.cfg:
            print(f"Setting readout length to {self.cfg["readout_length"]} us.")
            self.cfg["readout_lengths"][0] = self.cfg["readout_length"]

        # for j in range(len(self.cfg['adc_trig_delays'])):
        #     # self.cfg['readout_lengths'][j]
        #     self.cfg['adc_trig_delays'][j] = 0
        #### pull the data from the single shots
        # self.cfg["IDataArray"] = [None, None, None, None, None, None, None, None]
        # for Q in range(len(self.cfg["IDataArray"])):
        #     self.cfg["IDataArray"][Q] = Compensated_Pulse(self.cfg['FF_Qubits'][str(Q+1)]['Gain_Pulse'], 0, Q)

        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"],
                                 initial_delay=10.0)
        length_of_t = prog.get_time_axis(0, True)
        t_array = prog.get_time_axis(0, False) + self.cfg["adc_trig_delays"][0]
        i_g, q_g, i_e, q_e = [np.zeros((0,length_of_t))] * 4

        shots_per_iteration = 1024 // length_of_t # maximum buffer size is 1024
        num_iterations = self.cfg["Shots"] // shots_per_iteration
        num_shots = num_iterations * shots_per_iteration
        print(f"Doing {num_shots} shots total.")

        for _ in tqdm(range(num_iterations)):
            self.cfg["Pulse"] = False
            prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=shots_per_iteration, final_delay=self.cfg["relax_delay"], initial_delay=10.0)

            decim = prog.acquire_decimated(self.soc, load_pulses=True, progress = False)[0]
            # print(np.array(decim).shape)
            i_g = np.concatenate([i_g, decim[...,0]], axis=0)
            q_g = np.concatenate([q_g, decim[...,1]], axis=0)

            self.cfg["Pulse"] = True
            prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=shots_per_iteration, final_delay=self.cfg["relax_delay"], initial_delay=10.0)
            decim = prog.acquire_decimated(self.soc, load_pulses=True, progress = False)[0]
            i_e = np.concatenate([i_e, decim[..., 0]], axis=0)
            q_e = np.concatenate([q_e, decim[..., 1]], axis=0)

        i_g = np.mean(i_g, axis=0)
        q_g = np.mean(q_g, axis=0)
        i_e = np.mean(i_e, axis=0)
        q_e = np.mean(q_e, axis=0)


        data = {'config': self.cfg, 'data': {'t':t_array}}
                # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}
        self.data = data
        self.fid = []
        for i, read_index in enumerate(self.cfg["Qubit_Readout_List"]):
            # i_g = shots_ig[i]
            # q_g = shots_qg[i]
            # i_e = shots_ie[i]
            # q_e = shots_qe[i]
            self.data['data']['i_g' + str(read_index)] = i_g
            self.data['data']['q_g' + str(read_index)] = q_g
            self.data['data']['i_e' + str(read_index)] = i_e
            self.data['data']['q_e' + str(read_index)] = q_e

        #     fid, threshold, angle, ne_contrast, ng_contrast = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, return_errors=True) ### arbitrary ran, change later
        #     self.data_in_hist = [i_g, q_g, i_e, q_e]
        #     self.fid.append(fid)
        #     self.threshold.append(threshold)
        #     self.angle.append(angle)
        #     self.ne_contrast.append(ne_contrast)
        #     self.ng_contrast.append(ng_contrast)
        #
        #     confusion_matrix = np.array([[1-ng_contrast, ne_contrast],
        #                                  [ng_contrast, 1-ne_contrast]])
        #
        #     self.confusion_matrix.append(confusion_matrix)
        #
        #
        # self.data['data']['threshold'] = self.threshold
        # self.data['data']['angle'] = self.angle
        # self.data['data']['ne_contrast'] = self.ne_contrast
        # self.data['data']['ng_contrast'] = self.ng_contrast
        # self.data['data']['fid'] = self.fid
        #
        # self.data['data']['confusion_matrix'] = self.confusion_matrix

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, display_indices=None, block=True, **kwargs):
        if data is None:
            data = self.data
        if display_indices is None:
            display_indices = self.cfg["Qubit_Readout_List"]

        t = data["data"]["t"]
        for j, read_index in enumerate(display_indices):

            i_g = data["data"]["i_g" + str(read_index)]
            q_g = data["data"]["q_g" + str(read_index)]
            i_e = data["data"]["i_e" + str(read_index)]
            q_e = data["data"]["q_e" + str(read_index)]

            #### plotting is handled by the helper histogram
            # title = 'Read Length: ' + str(self.cfg["readout_lengths"][j]) + "us" + ", Read: " + str(read_index)
            # hist_process(data=[i_g, q_g, i_e, q_e], plot=True, print_fidelities=False, ran=None, title = title)
            fig, axs = plt.subplots(3,1, figsize=(8,8))
            axs[0].plot(t, i_g, label='i_g', color='red')
            axs[0].plot(t, q_g, label='q_g', color='maroon')
            axs[1].plot(t, i_e, label='i_e', color='blue')
            axs[1].plot(t, q_e, label='q_e', color='seagreen')

            axs[0].legend()
            axs[1].legend()

            separation = np.abs(i_g + j*q_g - i_e - j*q_e)
            axs[2].plot(t, separation, label='separation', color='black')
            axs[2].legend()
            axs[2].set_ylabel("Time (us)")
            plt.suptitle(self.titlename + " , Read: " + str(read_index))

            plt.savefig(self.iname)

            if plotDisp:
                plt.show(block=block)
                plt.pause(0.1)
        # else:
        #     plt.clf()
        #     plt.close()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
