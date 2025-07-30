# from WorkingProjects.Triangle_Lattice_tProcV2.Experiment_Scripts.mRabiOscillations import WalkFFProg
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers as RampHelpers

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *


class BaseRampExperiment(SweepExperiment1D_lines):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.x_key = None
        self.x_points = None
        self.z_value = 'population'
        self.xlabel = None

        self.cfg["IDataArray"] = [None]*4

        # print('reps:', self.cfg['reps'])
    def set_up_instance(self):
        '''Create the Ramp '''
        for i, Q in zip([0, 1, 2, 3], ['1', '2', '3', '4']):
            self.cfg["IDataArray"][i] = RampHelpers.generate_cubic_ramp(
                initial_gain=self.cfg['FF_Qubits'][Q]['Gain_Pulse'],
                final_gain=self.cfg['FF_Qubits'][Q]['Gain_Expt'],
                ramp_duration=self.cfg['ramp_duration'])

        self.cfg['expt_samples'] = self.cfg['ramp_duration']


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
                initial_gain=self.cfg['FF_Qubits'][Q]['Gain_Pulse'],
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
        for i, Q in zip([0, 1, 2, 3], ['1', '2', '3', '4']):
            ramp_part = RampHelpers.generate_cubic_ramp(
                initial_gain=self.cfg['FF_Qubits'][Q]['Gain_Pulse'],
                final_gain=self.cfg['FF_Qubits'][Q]['Gain_Expt'],
                ramp_duration=self.cfg['ramp_duration'])

            const_part = np.full(self.cfg['time_end'], self.cfg['FF_Qubits'][Q]['Gain_Expt'])
            self.cfg["IDataArray"][i] = np.concatenate([ramp_part, const_part])

    def set_up_instance(self):
        # Do nothing.
        pass