from qick import *

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import *
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy

# import matplotlib; matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt

import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *
import scipy
import functools
import operator
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.SweepHelpers



class SweepExperiment2D(ExperimentClass):
    """
        Sweeps a config entry for an AveragerProgram.
    """
    def init_sweep_vars(self):
        self.Program =  None   #  AveragerProgram
        self.y_key =    None   #  key, or a list of keys for nested dicts
        self.y_points = None   #  1D array
        self.x_key =    None   #  key, or a list of keys for nested dicts
        self.x_points = None   #  1D array
        self.z_value =  None   #  'contrast' or 'population'

        self.ylabel =   None   #  for plotting
        self.xlabel =   None   #  for plotting

        raise NotImplementedError("Please implement init_sweep_vars() to define sweep variables.")

    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        pass


    def __init__(self, path='', prefix='data', soc=None, soccfg=None, cfg=None, config_file=None,
                 liveplot_enabled=False, **kwargs):
        super().__init__(path=path, prefix=prefix, soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file,
                         liveplot_enabled=liveplot_enabled, **kwargs)


        self.init_sweep_vars()

    def acquire(self, progress=False, plotDisp=True, plotSave=True, figNum=1):
        while plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum += 1

        readout_list = self.cfg["Qubit_Readout_List"]

        '''Define y_plot_points only if you want the plotted/saved axes to be different from the swept ones.
            Currently only used in mOptimizeReadoutAndPulse'''
        Y = self.__dict__.get('y_plot_points', self.y_points)
        X = self.__dict__.get('x_plot_points', self.x_points)

        # Index by Z_mat[ro_index][y, x]
        Z_mat = [np.full((len(Y), len(X)), np.nan) for _ in readout_list]
        # if self.z_value == 'shots':
        #     Z_mat = [[[[None for i in range(len(X))] for j in range(len(X))]] for ro_ind in range(len(readout_list))]
        if self.z_value == 'contrast':
            I_mat = [np.full((len(Y), len(X)), np.nan) for _ in readout_list]
            Q_mat = [np.full((len(Y), len(X)), np.nan) for _ in readout_list]


        # Define data dictionary
        y_key_name = SweepHelpers.key_savename(self.y_key)
        x_key_name = SweepHelpers.key_savename(self.x_key)
        self.data = {
            'config': self.cfg,
            'data': {self.z_value: Z_mat,
                     y_key_name: Y,
                     x_key_name: X,
                     'readout_list': readout_list}
        }
        if 'angle'     in self.cfg: self.data['data']['angle'] = self.cfg['angle']
        if 'threshold' in self.cfg: self.data['data']['threshold'] = self.cfg['threshold']
        if self.z_value == 'contrast':
            self.data['data']['I_mat'] = I_mat
            self.data['data']['Q_mat'] = Q_mat

        self.last_saved_time = time.time()

        for i, y_pt in enumerate(self.y_points):
            for j, x_pt in enumerate(self.x_points):
                # Update config entries based on sweep
                SweepHelpers.set_nested_item(self.cfg, self.x_key, x_pt)
                SweepHelpers.set_nested_item(self.cfg, self.y_key, y_pt)

                # set up the AveragerProgram instance
                self.set_up_instance()

                if issubclass(self.Program, AveragerProgram):
                    Instance = self.Program(self.soccfg, self.cfg)
                elif issubclass(self.Program, ExperimentClass):
                    Instance = self.Program(path=self.path, prefix=self.prefix, soc=self.soc, soccfg=self.soccfg,
                                            cfg=self.cfg, config_file=None, outerFolder = self.outerFolder)
                else:
                    raise TypeError("Please assign an AveragerProgram object in self.Program.")

                # Acquire data and assign into Z_mat
                # AveragerProgram returns avg_di, avg_dq, indexed into by avg_di[ro_ch][0]
                if isinstance(Instance, ExperimentClass):
                    '''!!! Exceptional case intended only for OptimizeReadoutAndPulse !!!.
                    Otherwise, make sure data['data'][z_value][ro_ind] is one number'''
                    data = Instance.acquire(self)
                    for ro_index in range(len(readout_list)):
                        Z_mat[ro_index][i, j] = data['data'][self.z_value][ro_index]

                elif self.z_value == 'contrast':
                    avgi, avgq = Instance.acquire(self.soc, load_pulses=True)
                    for ro_index in range(len(readout_list)):
                        I_mat[ro_index][i,j] = avgi[ro_index][0]
                        Q_mat[ro_index][i,j] = avgq[ro_index][0]
                        rotated_i = IQ_contrast(I_mat[ro_index][:i+1,:j+1], Q_mat[ro_index][:i+1,:j+1])

                        Z_mat[ro_index][:i+1,:j+1] = rotated_i
                elif self.z_value == 'population':
                    excited_populations = Instance.acquire_populations(soc=self.soc, return_shots=False,
                                                                   load_pulses=True)
                    for ro_index in range(len(readout_list)):
                        Z_mat[ro_index][i,j] = excited_populations[ro_index]
                # elif self.z_value == 'shots':
                #     "Intended for debugging, no built-in plotting available"
                #     for ro_index in range(len(readout_list)):
                #         _, shots = Instance.acquire_populations(soc=self.soc, return_shots=True,
                #                                                 load_pulses=True)
                #         Z_mat[ro_index][i][j] = (shots[0][ro_index], shots[1][ro_index])
                else:
                    raise ValueError("So far I only support 'contrast' or 'population'.")

                if (plotDisp or plotSave) and j == len(X)-1:
                    # Create figure
                    if i == 0:# and j == 0:
                        fig, axs, ax_images, cbars = self.display(self.data, figNum=figNum,
                                                                plotDisp=plotDisp, block=False,
                                                                plotSave=False)
                        if self.z_value == 'contrast':
                            colorbar_label = 'IQ contrast (a.u.)'
                        elif self.z_value == 'population':
                            colorbar_label = 'Excited state population'
                        else:
                            colorbar_label = None
                    # Update figure
                    else:
                        for ro_index, ro_ch in enumerate(readout_list):
                            ax_images[ro_index].set_data(Z_mat[ro_index])
                            ax_images[ro_index].autoscale()
                            cbars[ro_index].remove()
                            cbars[ro_index] = fig.colorbar(ax_images[ro_index], ax=axs[ro_index], extend='both')
                            cbars[ro_index].set_label(colorbar_label, rotation=90)

                        # fig.canvas.draw()
                        # fig.canvas.flush_events()
                        fig.show()
                        plt.pause(0.1)

                if time.time() - self.last_saved_time > 5 * 60:  # Save data every 5 minutes
                    ### print(self.data)
                    self.last_saved_time = time.time()
                    self.save_data(data=self.data)
                    if plotSave:
                        plt.savefig(self.iname[:-4] + '.png')

            ### DEBUG
            # fig2, ax2 = plt.subplots(1, 1, figsize=(7, 5))
            # ax2.plot(self.cfg["IDataArray2"][0], label='1')
            # ax2.plot(self.cfg["IDataArray2"][1], label='2')
            # ax2.plot(self.cfg["IDataArray2"][2], label='3')
            # ax2.plot(self.cfg["IDataArray2"][3], label='4')
            # ax2.set_title(f'{y_key_name} = {y_pt}')
            # ax2.set_xlim([0, 1000])
            # ax2.legend()
            #
            # fig2.show()
            # plt.pause(0.1)

        if (plotDisp or plotSave):
            fig.clf(True)
            plt.close(fig)

        self.save_data(data=self.data)
        return self.data


    def display(self, data=None, plotDisp=True, figNum=1, plotSave=True, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum += 1

        readout_list = self.cfg["Qubit_Readout_List"]

        # Can pass in your own fig and axs to, for example, add this to your own subplot
        if len(readout_list) == 1:
            fig, ax = plt.subplots(1, 1, figsize=(10, 8), num=figNum)
            axs = [ax]
        elif len(readout_list) == 2:
            fig, axs = plt.subplots(1, 2, figsize=(14, 8), num=figNum, tight_layout=True)
        elif len(readout_list) in [3, 4]:
            fig, axs = plt.subplots(2, 2, figsize=(14, 8), num=figNum, tight_layout=True)
            axs = (axs[0][0], axs[0][1], axs[1][0], axs[1][1])
            if len(readout_list) == 3:
                axs[3].set_axis_off()
        else:
            raise Exception("I don't think we support MUX with N > 4 yet???")


        fig.suptitle(str(self.titlename), fontsize=16)

        y_key_name = SweepHelpers.key_savename(self.y_key)
        x_key_name = SweepHelpers.key_savename(self.x_key)
        X, Y = data['data'][x_key_name], data['data'][y_key_name]
        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]
        Z_mat = data['data'][self.z_value]


        if self.z_value == 'contrast':
            colorbar_label = 'IQ contrast (a.u.)'
        elif self.z_value == 'population':
            colorbar_label = 'Excited state population'
        else:
            colorbar_label = None

        ax_images = [None] * len(readout_list)
        cbars = [None] * len(readout_list)
        for ro_index, ro_ch in enumerate(readout_list):
            ax_images[ro_index] = axs[ro_index].imshow(
                Z_mat[ro_index],
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none')
            axs[ro_index].set_ylabel(self.ylabel)
            axs[ro_index].set_xlabel(self.xlabel)
            axs[ro_index].set_title(f"Read: {ro_ch}")
            cbars[ro_index] = fig.colorbar(ax_images[ro_index], ax=axs[ro_index], extend='both')
            cbars[ro_index].set_label(colorbar_label, rotation=90)


        if plotSave:
            plt.savefig(self.iname[:-4] + '.png')

        if plotDisp:
            plt.show(block=block)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        return fig, axs, ax_images, cbars

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
