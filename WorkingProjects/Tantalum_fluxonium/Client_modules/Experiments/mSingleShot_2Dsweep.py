### code to look at single shot fidelity of any two variables

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import LoopbackProgramSingleShot
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time


# ====================================================== #

class SingleShot_2Dsweep(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp = True, figNum = 1):

        ### define variables to sweep over
        expt_cfg = {
            ### x variable
            "x_var": self.cfg["x_var"],
            "x_start": self.cfg["x_start"],
            "x_stop": self.cfg["x_stop"],
            "x_num": self.cfg["x_num"],
            ### y variable
            "y_var": self.cfg["y_var"],
            "y_start": self.cfg["y_start"],
            "y_stop": self.cfg["y_stop"],
            "y_num": self.cfg["y_num"],
        }
        ### create arrays for variables
        #### if varibale is a gain, needs to be an int
        if expt_cfg["x_var"] == "read_pulse_gain" or expt_cfg["x_var"] == "qubit_gain":
            x_vec = np.linspace(expt_cfg["x_start"], expt_cfg["x_stop"], expt_cfg["x_num"], dtype=int)
        else:
            x_vec = np.linspace(expt_cfg["x_start"], expt_cfg["x_stop"], expt_cfg["x_num"])

        if expt_cfg["y_var"] == "read_pulse_gain" or expt_cfg["y_var"] == "qubit_gain":
            y_vec = np.linspace(expt_cfg["y_start"], expt_cfg["y_stop"], expt_cfg["y_num"], dtype=int)
        else:
            y_vec = np.linspace(expt_cfg["y_start"], expt_cfg["y_stop"], expt_cfg["y_num"])

        #### define the plotting X and Y and data holders Z
        X = x_vec
        X_step = X[1] - X[0]
        Y = y_vec
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        ### create array for storing the data
        self.data= {
            'config': self.cfg,
            'data': {'fid_mat': Z_fid,
                        'x_arr': x_vec,
                        'y_arr': y_vec,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 1, figsize=(8, 8), num=figNum)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start loop over both axes
        for idx_y in range(expt_cfg["y_num"]):
            #### define the y variable
            self.cfg[self.cfg["y_var"]] = y_vec[idx_y]
            ### loop over x values
            for idx_x in range(expt_cfg["x_num"]):
                ### define the x variable
                self.cfg[self.cfg["x_var"]] = x_vec[idx_x]

                #### pull the data from the single hots
                prog = LoopbackProgramSingleShot(self.soccfg, self.cfg)
                shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)

                i_g = shots_i0[0]
                q_g = shots_q0[0]
                i_e = shots_i0[1]
                q_e = shots_q0[1]

                ### use the helper histogram to find the fidelity and such
                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=20) ### arbitrary ran, change later

                Z_fid[idx_y, idx_x] = fid

                self.data['data']['fid_mat'][idx_y, idx_x] = fid

                ####### plotting data
                if idx_x == 0 and idx_y == 0:  #### if first sweep add a colorbar
                    #### plotting
                    ax_plot_0 = axs.imshow(
                        Z_fid,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )

                    cbar0 = fig.colorbar(ax_plot_0, ax=axs, extend='both')
                    cbar0.set_label('fidelity', rotation=90)
                else:
                    ax_plot_0.set_data(Z_fid)
                    ax_plot_0.data = Z_fid
                    ax_plot_0.set_clim(vmin = np.nanmin(Z_fid))
                    ax_plot_0.set_clim(vmax= np.nanmax(Z_fid))
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs, extend='both')
                    cbar0.set_label('fidelity', rotation=90)

                axs.set_ylabel(expt_cfg["y_var"])
                axs.set_xlabel(expt_cfg["x_var"])
                axs.set_title("fidelity")

                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)

                if idx_y == 0 and idx_x == 0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * len(X) * len(Y)
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

                plt.tight_layout()
        ### save the figure and return the data
        data = self.data
        plt.savefig(self.iname, dpi = 600)  #### save the figure

        return data


    # def display(self, data=None, plotDisp = False, figNum = 1, save_fig = True, ran=None, **kwargs):
    #     if data is None:
    #         data = self.data
    #
    #     i_g = data["data"]["i_g"]
    #     q_g = data["data"]["q_g"]
    #     i_e = data["data"]["i_e"]
    #     q_e = data["data"]["q_e"]
    #
    #     #### plotting is handled by the helper histogram
    #     title = ('Read Length: ' + str(self.cfg["read_length"]) + "us, freq: " + str(self.cfg["read_pulse_freq"])
    #                 + "MHz, gain: " + str(self.cfg["read_pulse_gain"]) )
    #     fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=plotDisp, ran=ran, title = title)
    #
    #
    #     self.fid = fid
    #     self.threshold = threshold
    #     self.angle = angle
    #
    #
    #     if save_fig:
    #         plt.savefig(self.iname)
    #
    #     if plotDisp:
    #         plt.show(block=False)
    #         plt.pause(0.1)
    #     # else:
    #         # fig.clf(True)
    #         # plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


