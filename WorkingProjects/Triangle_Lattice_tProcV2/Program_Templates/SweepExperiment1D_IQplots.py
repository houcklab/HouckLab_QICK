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
import itertools
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.SweepHelpers
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates import SweepExperimentND
from qick.asm_v2 import AveragerProgramV2


class SweepExperiment1D_IQplots(SweepExperimentND):
    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs

        if self.z_value == 'IQ':
            ylabel = 'Transmission (a.u.)'
        elif self.z_value == 'population':
            ylabel = 'Excited state population'
        elif self.z_value == 'population_corrected':
            ylabel = 'Excited state population (corrected)'
        elif self.z_value == 'contrast':
            ylabel = 'IQ contrast (a.u.)'
        else:
            ylabel = None

        x_key_name = SweepHelpers.key_savename(self.x_key)
        X = data['data'][x_key_name]
        self.X = X

        I_mat = data['data']['I']
        Q_mat = data['data']['Q']

        readout_list = data['data']['readout_list']
        for ro_index, ro_ch in enumerate(readout_list):
            axs[ro_index].plot(X, I_mat[ro_index], label='I', marker='o')
            axs[ro_index].plot(X, Q_mat[ro_index], label='Q', marker='o')
            axs[ro_index].set_title(f"Read: {ro_ch}")

            axs[ro_index].set_ylabel(ylabel)
            axs[ro_index].set_xlabel(self.xlabel)
            axs[ro_index].legend()


    def update_1D_IQ(self, Z_mat, fig, axs):
        I_mat = self.data['data']['I']
        Q_mat = self.data['data']['Q']

        for ro_index in range(len(I_mat)):
            lines = axs[ro_index].lines
            lines[0].set_data(self.X, I_mat[ro_index])
            lines[1].set_data(self.X, Q_mat[ro_index])
            axs[ro_index].relim()
            axs[ro_index].autoscale()


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
