import time
from itertools import product

# from WorkingProjects.Triangle_Lattice_tProcV2.Experiment_Scripts.mRabiOscillations import WalkFFProg
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers as RampHelpers

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperimentND import \
    SweepExperimentND
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCorrelationExperiments import generate_counts
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers, CorrelationAnalysis
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FFEnvelope_Helpers import get_gains


class BaseRampExperiment(SweepExperiment1D_lines):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.x_key = None
        self.x_points = None
        self.z_value = 'population_corrected'
        self.xlabel = None

        self.cfg["IDataArray"] = [None]*len(self.cfg['FF_Qubits'])

    def set_up_instance(self):


        '''Create the Ramp '''
        self.cfg["IDataArray"] = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'ramp_initial_gain', 'Gain_Expt',
                                              self.cfg['ramp_duration'])
        # elif self.cfg['ramp_shape'] == 'linear':
        #     self.cfg["IDataArray"] = FFEnvelope_Helpers.LinearRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
        #                                                                 self.cfg['ramp_duration'])
        self.cfg['expt_samples'] = self.cfg['ramp_duration']

class RampCheckDensityCorrelations(BaseRampExperiment):
    '''Class that plots n21*n43, etc. to check fidelity of state preparation'''
    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.z_value = 'population_shots'

    def analyze(self, data, **kwargs):
        print("RampCheckDensityCorrelations: Analyzing data.")
        data_dict = data['data']
        shots_matrices = data_dict['population_shots']
        # Extract correlation data
        nn_correls = []
        nn_correls_corrected = []
        def get_ro_ind(Qubit):
            return data_dict['readout_list'].index(Qubit)

        shot_matrices_first = [shots_matrices[get_ro_ind(q)] for q in self.cfg['first_pair']]
        for second_pair in self.cfg['second_pairs']:
            shot_matrices_second = [shots_matrices[get_ro_ind(q)] for q in second_pair]
            nn_correls.append(CorrelationAnalysis.get_nn_correlations(*shot_matrices_first, *shot_matrices_second))

            if 'confusion_matrix' in data_dict:
                four_qubits = np.concatenate([self.cfg['first_pair'], second_pair])
                conf_mats = [data_dict['confusion_matrix'][get_ro_ind(q)] for q in four_qubits]
                nn_correls_corrected.append(CorrelationAnalysis.get_corrected_nn_correlations(
                    *shot_matrices_first, *shot_matrices_second, conf_mats))

        data_dict['nn_correlations'] = nn_correls
        data_dict['corrected_nn'] = nn_correls_corrected
        data_dict['first_pair'] = self.cfg['first_pair']
        data_dict['second_pairs'] = self.cfg['second_pairs']

    def _make_subplots(self, figNum, count):
        '''Modify display to produce 1 axes'''
        if plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum = None
        fig, axs = plt.subplots(2, 1, figsize=(7, 8), num=figNum, tight_layout=True)
        return fig, axs

    def _display_plot(self, data, fig_axs):
        data_dict = data['data']
        if 'nn_correlations' in data_dict:
            fig = fig_axs[0]
            ax = fig_axs[1][0]
            n = len(data_dict['population'])
            ax.bar(range(1,n+1), data_dict['population'], ls='dashed', linewidth=1.5, edgecolor='black', color='none', label="Uncorrected", zorder=2)
            bars = ax.bar(range(1,n+1), data_dict['population_corrected'], color=plt.rcParams['axes.prop_cycle'].by_key()['color'], label=f"Corrected, sum={sum(data_dict['population_corrected']):.2f}")
            ax.set_xticks(range(1,n+1))
            ax.set_xlabel("Qubit")
            ax.set_ylabel("Occupation")
            ax.set_xticklabels(data_dict['readout_list'], rotation=70, fontsize=15)
            for bar in bars:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                         f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=12)
            ax.legend()

            ax = fig_axs[1][1]
            k = len(data_dict['second_pairs'])
            q1, q2 = data_dict['first_pair']
            bar_labels = [rf'$\langle n_{{{q2}{q1}}} n_{{{q4}{q3}}}\rangle$' for q3, q4 in data_dict['second_pairs']]

            if len(data_dict['corrected_nn']) > 0:
                ax.bar(range(k), data_dict['nn_correlations'], linewidth=5, edgecolor='black', color='none', label="Uncorrected", zorder=2)
                bars = ax.bar(range(k), data_dict['corrected_nn'], color='blue', alpha=0.8, label="Corrected")
                for bar in bars:
                    ax.text(bar.get_x() + bar.get_width() / 2, np.sign(bar.get_height()) * -0.05,
                            f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=12)
            ax.set_xticks(range(k))
            ax.set_xticklabels(bar_labels, rotation=70, fontsize=15)
            ax.legend()
            ax.axhline(0, color='black')

            fig.suptitle(str(self.titlename), fontsize=16)

class RampDurationVsPopulation(BaseRampExperiment):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.x_key = 'ramp_duration'
        self.x_points = np.linspace(self.cfg['duration_start'], self.cfg['duration_end'], self.cfg['duration_num_points'])
        self.xlabel = 'Ramp Duration (4.65 ns/16)'


    def set_up_instance(self):
        '''Create the Ramp '''
        for i, Q in zip([0, 1, 2, 3, 4, 5, 6, 7], ['1', '2', '3', '4', '5', '6', '7', '8']):

            ramp_on = RampHelpers.generate_cubic_ramp(
                initial_gain=self.cfg['FF_Qubits'][Q]['ramp_initial_gain'],
                final_gain=self.cfg['FF_Qubits'][Q]['Gain_Expt'],
                ramp_duration=self.cfg['ramp_duration'])
            ramp_delay = np.full(self.cfg['ramp_wait_timesteps'], self.cfg['FF_Qubits'][Q]['Gain_Expt'])
            ramp_off = np.array([]) if not self.cfg['double'] else np.flip(ramp_on)

            self.cfg["IDataArray"][i] = np.concatenate([ramp_on, ramp_delay, ramp_off])


        self.cfg['expt_samples'] = len(self.cfg["IDataArray"][0])


class FFExptVsPopulation(BaseRampExperiment):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.x_key = ('FF_Qubits', self.cfg['swept_qubit'], 'Gain_Expt')
        self.x_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'], self.cfg['gain_num_points'])
        self.xlabel = f'FF gain index {self.cfg["swept_qubit"]} (DAC units)'

class TimeVsPopulation(BaseRampExperiment):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.x_key = 'expt_samples'
        self.x_points = np.linspace(self.cfg['time_start'], self.cfg['time_end'], self.cfg['time_num_points'], dtype=int)
        self.xlabel = 'Time (4.65 ns/16)'

        # Ramp + constant gain after the ramp
        self.cfg["IDataArray"] = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse','ramp_initial_gain', 'Gain_Expt',
                                                                    self.cfg['ramp_duration'])
        Gain_Expts = get_gains(self.cfg, 'Gain_Expt')
        for i in range(len(self.cfg["IDataArray"])):
            ramp_part = self.cfg["IDataArray"][i]
            const_part = np.full(self.cfg['time_end'], ramp_part[-1])
            self.cfg["IDataArray"][i] = np.concatenate([ramp_part, const_part])

        plt.figure()
        for i in range(len(self.cfg["IDataArray"])):
            plt.plot( self.cfg["IDataArray"][i], label=f'Q{i+1}')

        plt.legend()
        plt.show(block=False)

    def set_up_instance(self):
        pass

    def analyze(self, data):
        d = data['data']
        if 'population_corrected' in d:
            d['pop_sum_corrected'] = np.sum(np.array(d['population_corrected']), axis=0)
        d['pop_sum'] = np.sum(np.array(d['population']), axis=0)

    def _display_plot(self, data=None, fig_axs=None):
        fig, ax = super()._display_plot(data=data, fig_axs=fig_axs)
        if 'pop_sum_corrected' in data['data']:
            ax.plot(data['data']['expt_samples'], data['data']['pop_sum_corrected'], label='Population Sum', color='black', linestyle='dashed', marker='o')
            ax.legend()
        elif 'pop_sum' in data['data']:
            ax.plot(data['data']['expt_samples'], data['data']['pop_sum'], label='Sum', color='black', linestyle='dashed', marker='o')
            ax.legend()

class TimeVsPopulation_Shots(TimeVsPopulation):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.z_value = 'population_shots'

        self.time_index = round((self.cfg['time_to_show_shots_samples']/( self.cfg['time_start'] - self.cfg['time_end'])/self.cfg['time_num_points']))

    def analyze(self, data):
        super().analyze(data=data)
        data['data']['population_shots'] = np.array(data['data']['population_shots'],dtype=int)

        counts = []
        for i in range(len(data['data']['expt_samples'])):
            counts.append(generate_counts(data['data']['population_shots'][:,i,:], num_qubits=len(data['data']['Qubit_Readout_List'])))
        counts = np.transpose(np.array(counts))
        self.data['data']['counts'] = counts

    def display(self, data=None, plotDisp=True, figNum=1, plotSave=True, block=True, fig_axs=None):
        '''Modify display to produce 2 axes, one for populations and one for correlations'''
        if fig_axs is None:
            if plt.fignum_exists(num=figNum):  # if figure with number already exists
                figNum = None
            fig, axs = plt.subplots(2, 1, figsize=(14, 8), num=figNum, tight_layout=True)

        return super().display(data, plotDisp, figNum, plotSave, block, (fig, axs))

    def _update_fig(self, Z_mat, fig, axs):
        self.data['data']['population'] = [np.mean(shots_matrix, axis=1).flatten() for shots_matrix in
                                      self.data['data']['population_shots']]
        # TODO: fix the error when this is uncommented
        # super()._update_fig(self.data['data']['population'], fig, axs[:1])

    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs
        data['data']['population'] = [np.mean(shots_matrix, axis=1).flatten() for shots_matrix in
                                      data['data']['population_shots']]

        # Display population data as usual
        self.z_value = 'population_corrected' if 'population_corrected' in data['data'] else 'population'
        SweepExperiment1D_lines._display_plot(self, data, (fig, [axs[0]]))
        self.z_value = 'population_shots'

        # Use the second axes to display shots data
        ax = axs[-1]
        if 'counts' in data['data']:
            counts = data['data']['counts'][:,self.time_index]


            probs = counts / np.sum(counts)
            bitstrings = list(product([0, 1], repeat=len(data['data']['Qubit_Readout_List'])))

            k = min(20, len(bitstrings))
            idx_sorted = np.argsort(probs)[::-1]
            top_idx = idx_sorted[:k]
            top_probs = probs[top_idx]
            top_labels = [''.join(map(str, bitstrings[i])) for i in top_idx]

            ax.bar(range(k), top_probs)
            ax.set_xticks(range(k))
            ax.set_xticklabels(top_labels, rotation=70, fontsize=9)
            ax.set_ylabel('Probability')
            ax.set_title(f'Top {k} outcomes by probability')

        return fig, ax

class TimeVsPopulation_GainSweep(BaseRampExperiment, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.Program = ThreePartProgramOneFF
        self.x_key = 'expt_samples'
        self.x_points = np.linspace(self.cfg['time_start'], self.cfg['time_end'], self.cfg['time_num_points'], dtype=int)
        self.xlabel = 'Time (4.65 ns/16)'





        self.y_key = 'ramp_gain_offset'
        self.y_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'], self.cfg['gain_num_points'])
        self.ylabel = 'FF gain offset (DAC units)'

        if not self.y_key in self.cfg:
            self.cfg[self.y_key] = 0

        self.z_value = 'population_corrected'

        self.initial_ramp_gains = np.array([self.cfg['FF_Qubits'][str(i+1)]['Gain_Expt'] for i in range(len(self.cfg['FF_Qubits']))])

        print(f'initial ramp gains: {self.initial_ramp_gains}')

        self.cfg["IDataArray"] = [None] * len(self.cfg['FF_Qubits'])



    def set_up_instance(self):

        for i in range(len(self.cfg['FF_Qubits'])):
            self.cfg['FF_Qubits'][str(i+1)]['Gain_Expt'] = self.initial_ramp_gains[i] + self.cfg['ramp_gain_offset']

        # Ramp + constant gain after the ramp
        self.cfg["IDataArray"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain', 'Gain_Expt',
                                                                    self.cfg['ramp_duration'])
        for i in range(len(self.cfg["IDataArray"])):
            ramp_part = self.cfg["IDataArray"][i]
            const_part = np.full(self.cfg['time_end'], self.cfg['FF_Qubits'][str(i + 1)]['Gain_Expt'])
            self.cfg["IDataArray"][i] = np.concatenate([ramp_part, const_part])

