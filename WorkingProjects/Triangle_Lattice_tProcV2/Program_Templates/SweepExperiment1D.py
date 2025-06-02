from qick import *

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import *
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


class SweepExperiment1D(ExperimentClass):
    """
        Sweeps a config entry for an AveragerProgram.
        Plots the config sweep on the x-axis.
    """
    def __init__(self, path='', prefix='data', soc=None, soccfg=None, cfg=None, config_file=None,
                 liveplot_enabled=False, **kwargs):
        super().__init__(path=path, prefix=prefix, soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file,
                         liveplot_enabled=liveplot_enabled, **kwargs)
        self.init_sweep_vars()

    def init_sweep_vars(self):
        raise NotImplementedError("Please implement init_sweep_vars() to define sweep variables.")
        self.Program = None
        self.x_key = None
        self.x_points = None
        self.z_value = None  # contrast, population, IQ
        self.xlabel = None  # for plotting

    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        pass

    def acquire(self, progress=False, plotDisp=True, plotSave=True, figNum=1):
        while plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum += 1

        readout_list = self.cfg["Qubit_Readout_List"]

        X = self.x_points

        # Index by Z_mat[ro_index][x]
        Z_array = [np.full(len(X), np.nan) for _ in readout_list]

        if self.z_value == 'contrast' or self.z_value == 'IQ':
            I_array = [np.full(len(X), np.nan) for _ in readout_list]
            Q_array = [np.full(len(X), np.nan) for _ in readout_list]


        # Define data dictionary
        x_key_name = SweepHelpers.key_savename(self.x_key)
        self.data = {
            'config': self.cfg,
            'data': {self.z_value: Z_array,
                     x_key_name: X,
                     'readout_list': readout_list}
        }
        if 'angle'     in self.cfg: self.data['data']['angle']     = self.cfg['angle']
        if 'threshold' in self.cfg: self.data['data']['threshold'] = self.cfg['threshold']
        if self.z_value == 'contrast' or self.z_value == 'IQ':
            self.data['data']['I_array'] = I_array
            self.data['data']['Q_array'] = Q_array


        self.last_saved_time = time.time()

        for j, x_pt in enumerate(X):
            SweepHelpers.set_nested_item(self.cfg, self.x_key, x_pt)

            self.set_up_instance()
            Instance = self.Program(self.soccfg, self.cfg)
            assert(isinstance(Instance, AveragerProgram))

            # AveragerProgram returns avg_di, avg_dq, indexed into by avg_di[ro_ch][0]
            if self.z_value == 'contrast' or self.z_value == 'IQ':
                avgi, avgq = Instance.acquire(self.soc, load_pulses=True)
                for ro_index in range(len(readout_list)):
                    I_array[ro_index][j] = avgi[ro_index][0]
                    Q_array[ro_index][j] = avgq[ro_index][0]
                    rotated_i = IQ_contrast(I_array[ro_index][:j+1], Q_array[ro_index][:j+1])

                    Z_array[ro_index][:j+1] = rotated_i

            elif self.z_value == 'population':
                for ro_index in range(len(readout_list)):
                    excited_populations = Instance.acquire_populations(soc=self.soc, return_shots=False,
                                                                   load_pulses=True)
                    Z_array[ro_index][j] = excited_populations[ro_index]
            elif self.z_value == 'shots':
                "Intended for debugging, no built-in plotting available"
                for ro_index in range(len(readout_list)):
                    _, shots = Instance.acquire_populations(soc=self.soc, return_shots=True,
                                                                   load_pulses=True)
                    Z_array[ro_index][j] = (shots[0][ro_index], shots[1][ro_index])
            else:
                raise ValueError("So far I only support 'IQ', 'contrast', or 'population'.")



            if plotDisp or plotSave:
                # Create figure
                if j == 0:
                    fig, axs, ax_lines = self.display(self.data, figNum=figNum,
                                                              plotDisp=plotDisp, block=False,
                                                              plotSave=False)
                # Update figure
                else:
                    for ro_index, ro_ch in enumerate(readout_list):
                        if self.z_value == 'IQ':
                            ax_lines[ro_index][0].set_data(X, I_array[ro_index])
                            ax_lines[ro_index][1].set_data(X, Q_array[ro_index])
                            axs[ro_index].relim()
                            axs[ro_index].autoscale()
                        else:
                            ax_lines[ro_index][0].set_data(X, Z_array[ro_index])
                            axs[ro_index].relim()
                            axs[ro_index].autoscale()

                        fig.canvas.draw()
                        fig.canvas.flush_events()

            if time.time() - self.last_saved_time > 5 * 60:  # Save data every 5 minutes
                ### print(self.data)
                self.last_saved_time = time.time()
                self.save_data(data=self.data)
                if plotSave:
                    plt.savefig(self.iname[:-4] + '.png')

        if plotDisp or plotSave:
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

        '''Unless plotting IQ values, plot all readouts on same axes'''
        if self.z_value != "IQ":
            fig, ax = plt.subplots(1, 1, num=figNum)
            axs = [ax] * len(readout_list)
        elif len(readout_list) == 1:
            fig, ax = plt.subplots(1, 1, num=figNum)
            axs = [ax]
        elif len(readout_list) == 2:
            fig, axs = plt.subplots(1, 2, figsize=(14, 8), num=figNum)
        elif len(readout_list) in [3, 4]:
            fig, axs = plt.subplots(2, 2, figsize=(14, 14), num=figNum)
            axs = (axs[0][0], axs[0][1], axs[1][0], axs[1][1])
        else:
            raise Exception("I don't think we support MUX with N > 4 yet???")


        fig.suptitle(str(self.titlename), fontsize=16)

        x_key_name = SweepHelpers.key_savename(self.x_key)
        X = data['data'][x_key_name]

        Z_array = data['data'][self.z_value]

        if self.z_value == 'IQ':
            ylabel = 'Transmission (a.u.)'
        elif self.z_value == 'population':
            ylabel = 'Excited state population'
        elif self.z_value == 'contrast':
            ylabel = 'IQ contrast (a.u.)'
        else:
            ylabel = None

        ax_lines = [None] * len(readout_list)
        for ro_index, ro_ch in enumerate(readout_list):
            if self.z_value == 'IQ':
                I_array = data['data']['I_array']
                Q_array = data['data']['Q_array']
                ax_lines[ro_index] =  axs[ro_index].plot(X, I_array[ro_index], label='I', marker='o')
                ax_lines[ro_index] += axs[ro_index].plot(X, Q_array[ro_index], label='Q', marker='o')
                axs[ro_index].set_title(f"Read: {ro_ch}")
            else:
                ax_lines[ro_index] = axs[ro_index].plot(X, Z_array[ro_index], marker='o', label=f"Read: {ro_ch}")

            axs[ro_index].set_ylabel(ylabel)
            axs[ro_index].set_xlabel(self.xlabel)
            axs[ro_index].legend()


        if plotSave:
            plt.savefig(self.iname[:-4] + '.png')

        if plotDisp:
            plt.show(block=block)
            plt.pause(0.05)
        else:
            fig.clf(True)
            plt.close(fig)

        return fig, axs, ax_lines

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
