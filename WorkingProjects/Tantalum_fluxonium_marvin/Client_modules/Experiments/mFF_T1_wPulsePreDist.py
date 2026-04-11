from qick import *
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import GammaFit as gf
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFRampHoldTest_wPulsePreDist import \
    FFRampHoldTest
from tqdm import tqdm
import time

'''
@author: Parth Jatakia
'''


def expFit(x, a, T1, c):
    return a * np.exp(-1 * x / T1) + c


class FF_T1_wPulsePreDist(ExperimentClass):
    """
    Use post selection at a thermal state (significant thermal population) to find T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, plot_predist=False):

        ### Define the wait vector
        if self.cfg['wait_type'] == 'linear':
            wait_vec = np.linspace(self.cfg["wait_start"], self.cfg["wait_stop"], self.cfg["wait_num"])
        if self.cfg['wait_type'] == 'log':
            wait_vec = np.logspace(np.log10(1 + self.cfg["wait_start"]), np.log10(self.cfg["wait_stop"]), self.cfg["wait_num"],
                                   base=10) - 1

        ##### create arrays to store all the raw data
        i_0_arr = np.full((self.cfg["wait_num"], int(self.cfg["reps"])), np.nan)
        q_0_arr = np.full((self.cfg["wait_num"], int(self.cfg["reps"])), np.nan)
        i_1_arr = np.full((self.cfg["wait_num"], int(self.cfg["reps"])), np.nan)
        q_1_arr = np.full((self.cfg["wait_num"], int(self.cfg["reps"])), np.nan)

        ### loop over all wait times and collect raw data
        for idx_wait in tqdm(range(self.cfg["wait_num"])):
            self.cfg["ff_hold"] = wait_vec[idx_wait]

            # if 'auto_dt_pulseplay' in self.cfg :
            #     if self.cfg['auto_dt_pulseplay'] :
            #         # automatic calculation of pulsedelay based on ff_hold time
            #         # pulsedelay should be at least ff_hold + 100 ns
            #         self.cfg['dt_pulseplay'] = max(0.1, (wait_vec[idx_wait]+0.1*self.cfg['relax_delay'])/500)

            #### pull the data from the single shots for the first run
            prog = FFRampHoldTest(self.soccfg, self.cfg, save_loc=self.path_wDate + "_ff_predist_"
                                                                  + str(wait_vec[idx_wait]) + ".png",
                                  plot_debug=plot_predist)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True)

            #### save all the data to arrays
            i_0_arr[idx_wait, :] = i_0
            q_0_arr[idx_wait, :] = q_0
            i_1_arr[idx_wait, :] = i_1
            q_1_arr[idx_wait, :] = q_1

            time.sleep(1)

        ### save the data
        data = {'config': self.cfg, 'data': {
            "wait_vec": wait_vec,
            'i_0': i_0_arr, 'q_0': q_0_arr,
            'i_1': i_1_arr, 'q_1': q_1_arr,
        }
                }

        self.data = data
        return data

    def process_data(self, data=None, **kwargs):
        '''
        kwargs :
        1. cen_num : number of centers
        2. save_all : save intermediate processed data
        '''
        if data is None:
            data = self.data

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]
        wait_vec = data["data"]["wait_vec"]

        data_to_process = [i_0, i_1, q_0, q_1, wait_vec]

        gammafit = gf.GammaFit(data_to_process, freq_01=data['config']["qubit_ge_freq"] * 1e6, verbose=False)
        pop = gammafit.pops_vec
        pop_err = gammafit.pops_err_vec
        centers_list = gammafit.centers
        g01 = gammafit.result.params['g01'].value
        err01 = gammafit.result.params['g01'].stderr
        g10 = gammafit.result.params['g10'].value
        err10 = gammafit.result.params['g10'].stderr
        T1 = gammafit.T1
        T1_err = gammafit.T1_err
        temp_rate = gammafit.temp
        temp_std_rate = gammafit.temp_err
        data_fitted = gammafit.data_fitted
        T1_guess = gammafit.T1_guess

        # saving the processed data
        update_data = {"data": {"population": pop, "population_std": pop_err, "centers_list": centers_list,
                                "g01": g01, "err01": err01, "g10": g10, "err10": err10, "T1": T1, "T1_err": T1_err,
                                "temp_rate": temp_rate, "temp_std_rate": temp_std_rate, "data_fitted": data_fitted,
                                "T1_guess": T1_guess}}

        data["data"] = data["data"] | update_data["data"]
        self.data = data

        return data

    def display(self, data=None, plotDisp=False, saveFig=True, figNum=1, ran=None, **kwargs):

        if data is None:
            data = self.data

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        # Extracting data
        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        wait_vec = data["data"]["wait_vec"]
        pop = data["data"]["population"]
        pop_err = data["data"]["population_std"]
        centers = data["data"]["centers_list"][0]
        centers_last = data['data']['centers_list'][-1]
        # popt_list = data["data"]["popt_list"]
        # perr_list = data["data"]["perr_list"]

        data_fitted = data["data"]["data_fitted"]
        T1 = data["data"]["T1"]
        T1_err = data["data"]["T1_err"]

        # Create histogram
        iq_data = np.stack((i_0[0], q_0[0]), axis=0)
        hist2d = sse2.createHistogram(iq_data, bin_size=51)
        xedges = hist2d[1]
        yedges = hist2d[2]
        x_points = (xedges[1:] + xedges[:-1]) / 2
        y_points = (yedges[1:] + yedges[:-1]) / 2

        # Choice of color
        colorlist = [
            'firebrick',
            'midnightblue',
            'coral',
            'darkolivegreen'
        ]

        ### Plotting the T1 vs wait_vec data and the fitted exponential.
        ### The fit of exponential is only valid for cen_num = 2.
        # Create 2x2 subplots
        gs = gridspec.GridSpec(cen_num, 2, width_ratios=[1, 2])
        fig = plt.figure(figsize=[12, 5 * cen_num])
        # Plot the blob distribution
        subplot_left = plt.subplot(gs[0, 0])
        subplot_left.scatter(i_0[-1], q_0[-1], s=0.1)
        subplot_left.scatter(centers_last[:, 0], centers_last[:, 1], s=10, c='r')
        subplot_left.set_xlabel("I")
        subplot_left.set_ylabel("Q")

        subplot_left_bottom = plt.subplot(gs[1, 0])
        im = subplot_left_bottom.imshow(np.transpose(hist2d[0]),
                                        extent=[x_points[0], x_points[-1], y_points[0], y_points[-1]],
                                        origin='lower', aspect='auto')
        fig.colorbar(im, ax=subplot_left_bottom)
        subplot_left_bottom.scatter(centers[:, 0], centers[:, 1], s=10, c='r')
        subplot_left_bottom.set_xlabel("I")
        subplot_left_bottom.set_ylabel("Q")

        # Plot the population vs time
        subplot_right = []
        for idx_start in range(cen_num):
            subplot_right.append(plt.subplot(gs[idx_start, 1]))
            for idx_end in range(cen_num):
                pop_curr = pop[idx_start, idx_end, :]
                pop_curr_std = pop_err[idx_start, idx_end, :]

                subplot_right[idx_start].errorbar(wait_vec, pop_curr, pop_curr_std, fmt='o',
                                                  label="Blob " + str(idx_end),
                                                  c=colorlist[idx_end])
                # Plot the fit if decay is exponential
                # TODO: extend it to cen_num > 2
                if cen_num == 2:
                    # subplot_right[idx_start].plot(wait_vec, expFit(wait_vec,*popt_list[idx_start][idx_end]),
                    #                               c=colorlist[idx_end], linestyle="--")
                    subplot_right[idx_start].plot(wait_vec, data_fitted[idx_start][:, idx_end],
                                                  c=colorlist[idx_end], linestyle="--")
            if cen_num == 2:
                T1_str = "T1 = " + str(T1.round(3)) + " +/- " + str(T1_err.round(3)) + " us"
            subplot_right[idx_start].set_xlabel("time (n us)")
            subplot_right[idx_start].set_ylabel("Population in Blob")
            subplot_right[idx_start].set_title("Start Blob = " + str(idx_start) + "\n" + T1_str)
            subplot_right[idx_start].legend()

        data_information = ("Fridge Temperature = " + str(self.cfg["fridge_temp"]) + "mK, Yoko_Volt = "
                            + str(self.cfg["yokoVoltage_freqPoint"]) + "V, relax_delay = " + str(
                    self.cfg["relax_delay"])
                            + "us." + " Qubit Frequency = " + str(self.cfg["qubit_freq"])
                            + " MHz")
        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        if saveFig:
            plt.savefig(self.iname, dpi=400)

        if plotDisp:
            plt.show()
        plt.close()

    def display_all_data(self, data=None, **kwargs):
        if data is None:
            data = self.data

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]
        wait_vec = data["data"]["wait_vec"]
        centers_init = data["data"]["centers_list"]
        centers_final = data["data"]["centers_list"]

        # Plot all raw data in I-Q plane, each plot has two subplots. For each wait_vec there is going to be a figure
        # with two subplots. First is a scatter plot of i_0 vs q_0 and the second is a scatter plot of i_1 vs q_1
        # Store each figure as a png file to self.path_only + "\\all_raw_data\\" + "wait_" + str(wait_vec[idx_wait])
        # + ".png" Make the folder if it does not exist

        import os
        folder_path = os.path.join(self.path_only, "all_raw_data_" + self.datetimestring)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        for idx_wait in range(len(wait_vec)):
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))
            ax1.scatter(i_0[idx_wait], q_0[idx_wait], s=0.1)
            # Plot the centers
            ax1.scatter(centers_init[idx_wait][:, 0], centers_init[idx_wait][:, 1], s=10, c='r', label='Init Centers')
            ax1.set_title("Wait time: " + str(wait_vec[idx_wait]) + " us - First Measurement")
            ax1.set_xlabel("I")
            ax1.set_ylabel("Q")
            ax2.scatter(i_1[idx_wait], q_1[idx_wait], s=0.1)
            # Plot the centers
            ax2.scatter(centers_final[idx_wait][:, 0], centers_final[idx_wait][:, 1], s=10, c='r',
                        label='Final Centers')
            ax2.set_title("Wait time: " + str(wait_vec[idx_wait]) + " us - Second Measurement")
            ax2.set_xlabel("I")
            ax2.set_ylabel("Q")
            plt.suptitle(self.outerFolder + '\n' + self.path_wDate)
            plt.tight_layout()
            plt.savefig(os.path.join(folder_path, "wait_" + str(wait_vec[idx_wait]) + ".png"), dpi=300)
            plt.close()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
