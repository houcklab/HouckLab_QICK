from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperimentND import \
    SweepExperimentND
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram_SweepWaveform import \
    ThreePartProgram_SweepTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers, SweepHelpers
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_plots import SweepExperiment1D_plots
import datetime
# from WorkingProjects.Triangle_Lattice_tProcV2.Experiment_Scripts.mRabiOscillations import WalkFFProg

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *


class RampBeamsplitterBase(SweepExperimentND):
    # current_calibration_offset_dict = {'reps': 400, 'ramp_time': 0, 'relax_delay': 150,
    #                                    'start': 0, 'step': 8, 'expts': 71}

    def init_sweep_vars(self):
        self.Program = ThreePartProgram_SweepTwoFF
        self.z_value = 'population'  # contrast or population
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting

        self.cfg['expt_samples1'] = self.cfg['ramp_time']

    def set_up_instance(self):
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse','Gain_Expt',self.cfg['ramp_time'])
        self.cfg["IDataArray2"] = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')

        t_offset = np.array(self.cfg['t_offset'], dtype=int)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif not isinstance(t_offset, (list, np.ndarray, tuple)):
            raise TypeError('t_offset must be an int or array like of ints')
        t_offset -= np.min(t_offset)

        for i in range(len(self.cfg["IDataArray2"])):
            self.cfg["IDataArray2"][i] = np.pad(self.cfg["IDataArray2"][i], (t_offset[i], 0), mode='constant',
                                            constant_values=self.cfg["IDataArray1"][i][self.cfg['expt_samples1']-1])

class RampBeamsplitterOffsetR(RampBeamsplitterBase, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.y_key = ("t_offset", self.cfg["swept_qubit"]-1)
        self.y_points = np.linspace(self.cfg['offsetStart'], self.cfg['offsetStop'], self.cfg['offsetNumPoints'], dtype=int)
        self.ylabel= "Offset time (4.65/16 ns)"

class RampBeamsplitterGainR(RampBeamsplitterBase, GainSweepOscillationsR):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.y_key = ('FF_Qubits', str(self.cfg['swept_qubit']), 'Gain_BS')
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.ylabel = f'FF gain (Qubit {self.cfg["swept_qubit"]})'  # for plotting


class RampBeamsplitterR1D(RampBeamsplitterBase, SweepExperiment1D_lines):
    def init_sweep_vars(self):
        super().init_sweep_vars()


class RampCurrentCorrelationsR(RampBeamsplitterR1D):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.z_value = 'population_shots'
        assert len(self.cfg['Qubit_Readout_List']) == 4, "Need MUX=4 for current correlations."

    def analyze(self, data):
        data_dict = data['data']

        if 'nn_correlations' in data_dict:
            return

        shots_matrices, time = data_dict['population_shots'], data_dict['expt_samples']

        # if 'confusion_matrix' not in data_dict:
        q1, q2, q3, q4 = shots_matrices
        n21, n43 = q2 - q1, q4 - q3
        self.nn_correlations = np.mean(n21*n43, axis=1)
        data_dict['nn_correlations'] = self.nn_correlations
        # else:
        #     conf_mats = data_dict['confusion_matrix']
        #     if len(conf_mats) == 4:
        #         conf12 = np.kron(conf_mats[0], conf_mats[1]) # tensor product
        #         conf23 = np.kron(conf_mats[2], conf_mats[3]) # tensor product
        #     else:
        #         conf12, conf23 = conf_mats
        #
        #     n21, n43 = np.zeros_like(time), np.zeros_like(time)
        #     for j in range(len(time)):
        #         pass


    # def display(self, data=None, plotDisp=True, figNum=1, plotSave=True, block=True, fig_axs=None):
    #     '''Modify display to produce 2 axes, one for populations and one for correlations'''
    #     if fig_axs is None:
    #         if plt.fignum_exists(num=figNum):  # if figure with number already exists
    #             figNum = None
    #         fig, axs = plt.subplots(2, 1, figsize=(14, 8), num=figNum, tight_layout=True)
    #
    #     return super().display(data, plotDisp, figNum, plotSave, block, (fig, axs))

    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs

        # Display population data as usual
        # SweepExperiment1D_lines._display_plot(self, data, (fig, [axs[0]]))

        # Use the second axes to display correlation data
        ax = axs[-1]
        if 'nn_correlations' not in data['data']:
            self.analyze(data)

        readout_list = data['data']['readout_list']
        q1, q2, q3, q4 = readout_list
        ylabel = rf'$\langle n_{{ {q2}{q1}}} n_{{{q4}{q3}}}\rangle$'

        try:
            x_key_name = SweepHelpers.key_savename(self.x_key)
        except:
            x_key_name = self.loop_names[0]
        X = data['data'][x_key_name]
        self.X = X

        fig.suptitle(str(self.titlename), fontsize=16)

        ax.plot(X, self.nn_correlations, marker='o', label=ylabel)

        ax.set_ylabel(ylabel)
        ax.set_xlabel(self.xlabel)
        ax.legend()

        return fig, ax