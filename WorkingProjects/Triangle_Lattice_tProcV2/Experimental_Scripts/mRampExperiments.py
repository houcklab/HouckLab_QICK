import time


# from WorkingProjects.Triangle_Lattice_tProcV2.Experiment_Scripts.mRabiOscillations import WalkFFProg
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers as RampHelpers

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass


class BaseRampExperiment(SweepExperiment1D_lines):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.x_key = None
        self.x_points = None
        self.z_value = 'population_corrected'
        self.xlabel = None

        # initialize ramp initial gain
        # if the list ramp_initial_gain is provided in cfg, use that
        # if not, use the gain pulse values
        for i in range(len(self.cfg['FF_Qubits'])):
            if not 'ramp_initial_gains' in self.cfg['FF_Qubits'][str(i + 1)]:
                if 'ramp_initial_gains' in self.cfg:
                    self.cfg['FF_Qubits'][str(i + 1)]['ramp_initial_gain'] = self.cfg['ramp_initial_gains'][i]
                else:
                    self.cfg['FF_Qubits'][str(i + 1)]['ramp_initial_gain'] = self.cfg['FF_Qubits'][str(i + 1)][
                        'Gain_Pulse']

        self.cfg["IDataArray"] = [None]*len(self.cfg['FF_Qubits'])

        # print('reps:', self.cfg['reps'])
    def set_up_instance(self):


        '''Create the Ramp '''
        if True:
            self.cfg["IDataArray"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain', 'Gain_Expt',
                                              self.cfg['ramp_duration'])
        # elif self.cfg['ramp_shape'] == 'linear':
        #     self.cfg["IDataArray"] = FFEnvelope_Helpers.LinearRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
        #                                                                 self.cfg['ramp_duration'])
        self.cfg['expt_samples'] = self.cfg['ramp_duration']

    # def display(self, *args, **kwargs):
    #     super().display(*args, **kwargs)



class RampDurationVsPopulation(BaseRampExperiment):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.x_key = 'ramp_duration'
        self.x_points = np.linspace(self.cfg['duration_start'], self.cfg['duration_end'], self.cfg['duration_num_points'])
        self.xlabel = 'Ramp Duration (4.65 ns/16)'


    def set_up_instance(self):
        '''Create the Ramp '''
        for i, Q in zip([0, 1, 2, 3], ['1', '2', '3', '4']):

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

        print(f'setting up sweep')

        # Ramp + constant gain after the ramp
        self.cfg["IDataArray"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain', 'Gain_Expt',
                                                                    self.cfg['ramp_duration'])
        for i in range(len(self.cfg["IDataArray"])):
            ramp_part = self.cfg["IDataArray"][i]
            const_part = np.full(self.cfg['time_end'], self.cfg['FF_Qubits'][str(i+1)]['Gain_Expt'])
            self.cfg["IDataArray"][i] = np.concatenate([ramp_part, const_part])

        # plt.figure()
        # for i in range(len(self.cfg["IDataArray"])):
        #     plt.plot( self.cfg["IDataArray"][i], label=f'Q{i+1}')
        #
        # plt.legend()
        # plt.show()

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

