from qick import *

from WorkingProjects.Triangle_Lattice.Helpers.AdiabaticRamps import generate_ramp
from WorkingProjects.Triangle_Lattice.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from WorkingProjects.Triangle_Lattice.Helpers.rotate_SS_data import *
import scipy
import functools
import operator

def set_nested_item(d, key_list, value):
    """Sets into nested dicts,
    e.g. set nested_item(d, ['a', 'b', 'c'], value) executes -----> d['a']['b']['c'] = value"""
    # functools.reduce(operator.getitem, [d, *key_list[:-1]])[key_list[-1]] = value
    for key in key_list[:-1]:
        d = d[key]
    d[key_list[-1]] = value


class SweepExperiment2D(ExperimentClass):
    """
        Sweeps a config entry for an AveragerProgram.
    """
    def init_sweep_vars(self):
        raise NotImplementedError("Please implement init_sweep_vars() to define sweep variables.")
        self.Program = None
        self.y_key = None
        self.y_points = None
        self.x_key = None
        self.x_points = None
        self.z_value = None  # contrast or population
        self.ylabel = None  # for plotting
        self.xlabel = None  # for plotting

    def before_each_program(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        pass


    def __init__(self, path='', prefix='data', soc=None, soccfg=None, cfg=None, config_file=None,
                 liveplot_enabled=False, **kwargs):
        super().__init__(path=path, prefix=prefix, soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file,
                         liveplot_enabled=liveplot_enabled, **kwargs)
        self.init_sweep_vars()

    def acquire(self, angle=None, threshold=None, progress=False, plotDisp=True, plotSave=True, figNum=1):
        while plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum += 1

        readout_list = self.cfg['Readout_indices']

        Y = self.y_points
        X = self.x_points
        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]

        # Index by Z_mat[ro_index][y, x]
        Z_mat = [np.full((len(Y), len(X)), np.nan) for _ in readout_list]
        I_mat = [np.full((len(Y), len(X)), np.nan) for _ in readout_list]
        Q_mat = [np.full((len(Y), len(X)), np.nan) for _ in readout_list]


        # Define data dictionary
        y_key_name = self.y_key if not isinstance(self.y_key, (list, tuple)) else self.y_key[-1]
        x_key_name = self.x_key if not isinstance(self.x_key, (list, tuple)) else self.x_key[-1]
        self.data = {
            'config': self.cfg,
            'data': {self.z_value: Z_mat,
                     'I_array': I_mat,
                     'Q_array': Q_mat,
                     y_key_name: Y,
                     x_key_name: X,
                     'readout_list': readout_list}
        }
        if angle is not None: self.data['angle'] = angle
        if threshold is not None: self.data['threshold'] = threshold

        self.save_time = time.time()

        for i, y_pt in enumerate(Y):
            for j, x_pt in enumerate(X):
                # Update config entries based on sweep
                if not isinstance(self.x_key, (list, tuple)):
                    self.cfg[self.x_key] = x_pt
                else:
                    set_nested_item(self.cfg, self.x_key, x_pt)

                if not isinstance(self.y_key, (list, tuple)):
                    self.cfg[self.y_key] = y_pt
                else:
                    set_nested_item(self.cfg, self.y_key, y_pt)

                self.before_each_program()
                Instance = self.Program(self.soccfg, self.cfg)
                assert (isinstance(Instance, AveragerProgram))

                # AveragerProgram returns avg_di, avg_dq, indexed into by avg_di[ro_ch][0]

            for ro_index in range(len(readout_list)):
                if self.z_value == 'contrast':
                    avgi, avgq = Instance.acquire(self.soc, load_pulses=True)
                    I_mat[ro_index][i,j] = avgi[ro_index][0]
                    Q_mat[ro_index][i,j] = avgq[ro_index][0]

                    theta = IQ_angle(I_mat[ro_index][:i+1,:j+1], Q_mat[ro_index][:i+1,:j+1])
                    rotated_i, _ = rotate(theta, I_mat[ro_index][:i+1,:j+1], Q_mat[ro_index][:i+1,:j+1])
                    Z_mat[ro_index][:i+1,:j+1] = rotated_i

                elif self.z_value == 'population':
                    excited_populations = Instance.acquire_populations(soc=self.soc, angle=angle,
                                                                   threshold=threshold, return_shots=False,
                                                                   load_pulses=True)
                    Z_mat[ro_index][i,j] = excited_populations[ro_index]

                else:
                    raise ValueError("So far I only support 'contrast' or 'population'.")

                if plotDisp or plotSave:
                    # Create figure
                    if i == 0:
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


                        plt.show(block=False)
                        plt.pause(0.05)

                if time.time() - self.save_time > 5 * 60:  # Save data every 5 minutes
                    ### print(self.data)
                    self.save_data(data=self.data)
                    if plotSave:
                        plt.savefig(self.iname[:-4] + '.png')

        fig.clf(True)
        plt.close(fig)

        self.save_data(data=self.data)
        return self.data


    def display(self, data=None, plotDisp=True, figNum=1, plotSave=False, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum += 1

        readout_list = self.cfg['Readout_indices']
        if len(readout_list) == 1:
            fig, ax = plt.subplots(1, 1, figsize=(10, 8), num=figNum)
            axs = [ax]
        elif len(readout_list) == 2:
            fig, axs = plt.subplots(1, 2, figsize=(20, 8), num=figNum)
        elif len(readout_list) in [3, 4]:
            fig, axs = plt.subplots(2, 2, figsize=(20, 14), num=figNum)
            axs = (axs[0][0], axs[0][1], axs[1][0], axs[1][1])
        else:
            raise Exception("I don't think we support MUX with N > 4 yet???")


        fig.suptitle(str(self.titlename), fontsize=16)

        x_key_name = self.x_key if not isinstance(self.x_key, (list, tuple)) else self.x_key[-1]
        y_key_name = self.y_key if not isinstance(self.y_key, (list, tuple)) else self.y_key[-1]
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
            plt.pause(0.05)
        else:
            fig.clf(True)
            plt.close(fig)

        return fig, axs, ax_images, cbars

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
