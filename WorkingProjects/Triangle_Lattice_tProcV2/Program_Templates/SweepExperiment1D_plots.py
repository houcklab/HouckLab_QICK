

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
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperimentND import SweepExperimentND
from qick.asm_v2 import AveragerProgramV2


class SweepExperiment1D_plots(SweepExperimentND):
    def _display_plot(self, data=None, fig_axs=None):
        print("displaying")
        if data is None:
            data = self.data
        fig, axs = fig_axs

        if self.z_value == 'IQ':
            ylabel = 'Transmission (a.u.)'
        elif self.z_value == 'population':
            ylabel = 'Excited state population'
        elif self.z_value == 'contrast':
            ylabel = 'IQ contrast (a.u.)'
        elif self.z_value == 'population_corrected':
            ylabel = 'Excited state population (corrected)'
        else:
            ylabel = None

        x_key_name = SweepHelpers.key_savename(self.x_key)
        X = data['data'][x_key_name]
        self.X = X

        Z_mat = data['data'][self.z_value]

        readout_list = data['data']['readout_list']
        for ro_index, ro_ch in enumerate(readout_list):
            axs[ro_index].plot(X, Z_mat[ro_index], marker='o', label=f"Read: {ro_ch}")

            axs[ro_index].set_ylabel(ylabel)
            axs[ro_index].set_xlabel(self.xlabel)
            axs[ro_index].legend()

    def _update_fig(self, Z_mat, fig, axs):
        for ro_index in range(len(Z_mat)):
            line = axs[ro_index].lines[-1]
            line.set_data(self.X, Z_mat[ro_index])
            axs[ro_index].relim()
            axs[ro_index].autoscale()