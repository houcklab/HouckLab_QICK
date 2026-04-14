'''Experiments taking the clean timing experiment to be the base for gain and offset sweeps.
    Includes double jump functionality; treat single jump as a special case with intermediate jump gain == None.'''

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FF_Crosstalk_Helper

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import Compensate

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampDoubleJumpGainR, RampDoubleJumpIntermediateSamplesR, RampCurrentCorrelationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperimentND import SweepExperimentND
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers

class BSClean(SweepExperimentND):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF
        self.xlabel = 'Beamsplitter time (4.65/16 ns)'  # for plotting
        self.x_key = 'expt_samples2'
        self.x_points = self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts'])
        self.z_value = 'population_corrected'

        self.plotted_jumps = True

        # Assign intermediate gains into cfg['FF_Qubits'] for crosstalk processing
        for j, ijump_gain in enumerate(self.cfg['intermediate_jump_gains']):
            if ijump_gain is None:
                self.cfg['intermediate_jump_gains'][j] = self.cfg['FF_Qubits'][str(j+1)]['Gain_BS']
                self.cfg['intermediate_jump_samples'][j] = 0

        # bs_samples allows you to have a different number of beamsplitter samples per qubit,
        # while the existing value of expt_samples2 will be added to each
        if 'bs_samples' not in self.cfg:
            self.cfg['bs_samples'] = np.zeros_like(self.cfg['intermediate_jump_samples'])
            print("Doing equal time beamsplitter for all.")
        else:
            print(f"Using beamsplitter times {self.cfg['bs_samples']}.")


    def set_up_instance(self):
        t_offset = np.array(self.cfg['t_offset'], dtype=int)
        t_offset -= np.min(t_offset)

        bs_samples = self.cfg['bs_samples'] + self.cfg['expt_samples2']
        # print("bs_samples:", bs_samples)
        inter_samples = self.cfg['intermediate_jump_samples']

        # Ramp
        # self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain','Gain_Expt', self.cfg['ramp_time'])
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'ramp_initial_gain', 'Gain_Expt',
                                              self.cfg['ramp_time'])
        self.cfg['expt_samples1'] = self.cfg['ramp_time']

        # BS jump then readout jump
        gain_expt = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gain_bs = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Readout')
        gain_inter = self.cfg['intermediate_jump_gains'] # no crosstalk applied here to match the other experiment


        # Create BS array
        RO_PAD = 0* 20*16
        max_array_2_length = np.max(t_offset + inter_samples + bs_samples)
        IQArray = []
        for j in range(len(gain_expt)):
            padded_readout_samples = max_array_2_length - t_offset[j] - inter_samples[j] - bs_samples[j] + RO_PAD
            arr = np.repeat([gain_expt[j], gain_inter[j],   gain_bs[j],     gain_readout[j]],
                                 [t_offset[j], inter_samples[j], bs_samples[j], padded_readout_samples],)
            arr = Compensate(arr - gain_expt[j], gain_expt[j], j+1)
            # Don't compensate readout jump?
            if padded_readout_samples > 0:
                arr[-padded_readout_samples:] = gain_readout[j]
            IQArray.append(arr)
        self.cfg["IDataArray2"] = IQArray
        self.cfg['expt_samples2'] = len(IQArray[0])


        if not self.plotted_jumps and self.cfg['expt_samples2'] > 40:
            fig, ax = plt.subplots()
            for i in range(len(self.cfg["IDataArray2"])):
                ax.plot(self.cfg['IDataArray2'][i], marker='o', label=f'Qubit {i + 1}')
            ax.legend()
            fig.canvas.draw()
            plt.show(block=False)
            self.plotted_jumps = True




class BSClean_offset(BSClean, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.y_key = ("t_offset", self.cfg["swept_qubit"]-1)
        self.y_points = np.arange(self.cfg['offsetStart'], self.cfg['offsetStop']+ self.cfg['offsetStep'], self.cfg['offsetStep'], dtype=int)
        self.ylabel= f"Offset time of Qubit {self.cfg["swept_qubit"]} (4.65/16 ns)"



class BSClean_BSGain(BSClean, GainSweepOscillationsR):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.y_key = ('FF_Qubits', str(self.cfg['swept_qubit']), 'Gain_BS')
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.ylabel = f'FF gain (Qubit {self.cfg["swept_qubit"]})'  # for plotting

class BSClean_ISamples(BSClean, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        BSClean.init_sweep_vars(self)
        self.y_key = ("intermediate_jump_samples", self.cfg["swept_qubit"] - 1)
        self.y_points = np.arange(self.cfg['samples_start'], self.cfg['samples_stop']+self.cfg['samples_step'], self.cfg['samples_step'],
                                    dtype=int)
        self.ylabel = f"Intermediate Jump Samples (4.65/16 ns) Qubit {self.cfg["swept_qubit"]}"


class BSClean_IGain(BSClean, RampDoubleJumpGainR):
    def init_sweep_vars(self):
        BSClean.init_sweep_vars(self)
        self.y_key = ("intermediate_jump_gains", self.cfg["swept_qubit"] - 1)
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'],
                                    dtype=int)
        self.ylabel = f"Intermediate Jump Gain Qubit {self.cfg["swept_qubit"]}"

class BSClean_Correlations(BSClean, RampCurrentCorrelationsR):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.z_value = 'population_shots'

    def set_up_instance(self):
        super().set_up_instance()
        assert len(self.cfg['Qubit_Readout_List']) >= 4, "Need MUX >= 4 for current correlations."

        self.readout_pair_1 = self.cfg.get('readout_pair_1', [1, 2])
        self.readout_pair_2 = self.cfg.get('readout_pair_2', [3, 4])

        for index in self.readout_pair_1 + self.readout_pair_2:
            if index not in self.cfg['Qubit_Readout_List']:
                raise ValueError(f'readout pair qubits must be in readout list, given: {index}')

        # print(f'readout pairs are: {self.readout_pair_1}, {self.readout_pair_2}')

    def analyze(self, data, **kwargs):
        super().analyze(data, **kwargs)
        self.data['data']['bs_samples_origin'] = self.cfg.get('exact_t_bs')

    def process_data(self, sweep_indices, sweep_values):
        RampCurrentCorrelationsR.process_data(self, sweep_indices, sweep_values)

    def _make_subplots(self, figNum, count):
        '''Modify display to produce 2 axes, one for populations and one for correlations'''
        if plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum = None
        fig, axs = plt.subplots(2, 1, figsize=(14, 8), num=figNum, tight_layout=True)
        return fig, axs

    def _update_fig(self, data, fig, axs):
        data_dict = data['data']

        pop_mat = data_dict['population_corrected']
        lines = axs[0].lines
        for ro_index in range(len(pop_mat)):
            lines[ro_index].set_data(self.X, pop_mat[ro_index])
        axs[0].relim()
        axs[0].autoscale()

        axs[1].lines[0].set_data(self.X, data_dict['nn_correlations'])
        axs[1].lines[1].set_data(self.X, data_dict['corrected_nn'])
        axs[1].relim()
        axs[1].autoscale()


    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs


        # Display population data as usual
        self.z_value = 'population_corrected' if 'population_corrected' in data['data'] else 'population'
        SweepExperiment1D_lines._display_plot(self, data, (fig, [axs[0]]))
        self.z_value = 'population_shots'

        # Use the second axes to display correlation data
        ax = axs[-1]


        readout_list = data['data']['readout_list']
        q1, q2 = self.cfg['readout_pair_1']
        q3, q4 = self.cfg['readout_pair_2']
        ylabel = rf'$\langle n_{{ {q2}{q1}}} n_{{{q4}{q3}}}\rangle$'

        x_key_name = SweepHelpers.key_savename(self.x_key)
        X = data['data'][x_key_name]
        self.X = X

        fig.suptitle(str(self.titlename), fontsize=16)

        nn_correlations = data['data']['nn_correlations']
        ax.plot(X, nn_correlations, marker='o', label=ylabel, color='black')
        if 'corrected_nn' in data['data']:
            corrected_nn = data['data']['corrected_nn']
            ax.plot(X, corrected_nn, marker='o', label="Corrected "+ylabel, color='blue')

        ax.set_ylabel(ylabel)
        ax.set_xlabel(self.xlabel)
        ax.legend()

        return fig, ax
