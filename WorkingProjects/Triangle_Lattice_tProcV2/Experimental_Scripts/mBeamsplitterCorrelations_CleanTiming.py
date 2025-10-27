import numpy as np
from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_plots import \
    SweepExperiment1D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import \
    SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import \
    ThreePartProgramTwoFF, ThreePartProgramOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampCurrentCorrelationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers, CorrelationAnalysis, SweepHelpers
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import Compensate


class RampBeamsplitterPopulationVsTime(SweepExperiment1D_plots):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting
        self.x_key = 'expt_samples'
        self.x_points = np.linspace(self.cfg['start'], self.cfg['ramp_time'], self.cfg['ramp_expts'], dtype=int)

        if self.cfg['stop'] > self.cfg['ramp_time']:
            self.x_points = np.concatenate([self.x_points[:-1], np.linspace(self.cfg['ramp_time'], self.cfg['stop'], self.cfg['BS_expts'], dtype=int)])
            print(self.x_points)

        self.z_value = 'population_corrected'


    def set_up_instance(self):
        t_offset = np.array(self.cfg['t_offset'], dtype=int)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif not isinstance(t_offset, (list, np.ndarray, tuple)):
            raise TypeError('t_offset must be an int or array like of ints')

        t_offset -= np.min(t_offset)
        print("Actual offsets:", t_offset)

        assert ((t_offset >= 0).all())

        # Ramp
        Ramps = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain','Gain_Expt',self.cfg['ramp_time'])
        # BS jump then readout jump
        gain_pulse   = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Pulse')
        gain_expt    = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gain_bs      = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Readout')
        IQArray = []
        for j, (pulse, expt, bs, readout) in enumerate(zip(gain_pulse, gain_expt, gain_bs, gain_readout)):
            bs_length = max(0, self.cfg['expt_samples'] - self.cfg['ramp_time'] - t_offset[j])
            arr = np.concatenate((Ramps[j], np.full(t_offset[j], expt), np.full(bs_length, bs)))

            print(self.cfg['expt_samples'])
            arr = np.concatenate((arr[:self.cfg['expt_samples']], np.full(16 * 5 - t_offset[j], readout)))


            arr = Compensate(arr - pulse, pulse, j+1)
            IQArray.append(arr)
        self.cfg["IDataArray"] = IQArray
        print([len(arr) for arr in IQArray])
        self.cfg['expt_samples'] = self.cfg['expt_samples'] + 16 * 5

class RampBeamsplitterCleanTiming(SweepExperiment2D_plots):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF
        self.xlabel = 'Beamsplitter time (4.65/16 ns)'  # for plotting
        self.x_key = 'expt_samples2'
        self.x_points = self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts'])
        self.z_value = 'population_shots'



    def set_up_instance(self):
        t_offset = np.array(self.cfg['t_offset'], dtype=int)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif not isinstance(t_offset, (list, np.ndarray, tuple)):
            raise TypeError('t_offset must be an int or array like of ints')

        t_offset -= np.min(t_offset)
        print("Actual offsets:", t_offset)

        assert ((t_offset >= 0).all())

        # Ramp
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg,'Gain_Pulse', 'ramp_initial_gain','Gain_Expt',self.cfg['ramp_time'])
        self.cfg['expt_samples1'] = self.cfg['ramp_time']
        # BS jump then readout jump
        gain_expt    = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gain_bs      = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Readout')
        IQArray = []
        for j, (expt, bs, readout) in enumerate(zip(gain_expt, gain_bs, gain_readout)):
            arr = np.concatenate((np.full(t_offset[j], expt), np.full(self.cfg['expt_samples2'], bs), np.full(16*5-t_offset[j], readout)))
            arr = Compensate(arr - expt, expt, j+1)
            IQArray.append(arr)
        self.cfg["IDataArray2"] = IQArray
        print([len(arr) for arr in IQArray])
        self.cfg['expt_samples2'] = len(IQArray[0])

class CleanTimingCorrelations(RampBeamsplitterCleanTiming, RampCurrentCorrelationsR):
    def set_up_instance(self):
        super().set_up_instance()
        assert len(self.cfg['Qubit_Readout_List']) >= 4, "Need MUX >= 4 for current correlations."

        self.readout_pair_1 = self.cfg.get('readout_pair_1', [1, 2])
        self.readout_pair_2 = self.cfg.get('readout_pair_2', [3, 4])

        for index in self.readout_pair_1 + self.readout_pair_2:
            if index not in self.cfg['Qubit_Readout_List']:
                raise ValueError(f'readout pair qubits must be in readout list, given: {index}')

        print(f'readout pairs are: {self.readout_pair_1}, {self.readout_pair_2}')

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

        try:
            x_key_name = SweepHelpers.key_savename(self.x_key)
        except:
            x_key_name = self.loop_names[0]
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



class CleanTimingCorrelationsDoubleJump(CleanTimingCorrelations):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.plotted_jumps = False
        for j in range(len(self.cfg['intermediate_jump_gains'])):
            if self.cfg['intermediate_jump_gains'][j] is None:
                self.cfg['intermediate_jump_gains'][j] = self.cfg['FF_Qubits'][str(j+1)]['Gain_BS']
                self.cfg['intermediate_jump_samples'][j] = 0

    def set_up_instance(self):
        t_offset = np.array(self.cfg['t_offset'], dtype=int)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif not isinstance(t_offset, (list, np.ndarray, tuple)):
            raise TypeError('t_offset must be an int or array like of ints')

        t_offset -= np.min(t_offset)
        print("Actual offsets:", t_offset)

        assert ((t_offset >= 0).all())

        # Ramp
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'ramp_initial_gain',
                                                                           'Gain_Expt', self.cfg['ramp_time'])
        self.cfg['expt_samples1'] = self.cfg['ramp_time']
        # BS jump then readout jump
        gain_expt = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gain_bs = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Readout')

        max_padded_length = max((t_off+t_ij for t_off, t_ij in zip(t_offset, self.cfg['intermediate_jump_samples'])))
        IQArray = []
        for j, (expt, bs, readout) in enumerate(zip(gain_expt, gain_bs, gain_readout)):
            t_ijump = self.cfg['intermediate_jump_samples'][j]
            ijump = self.cfg['intermediate_jump_gains'][j]
            arr = np.concatenate((np.full(t_offset[j], expt), # t_offset, stay at ramp
                                  np.full(t_ijump, ijump),    # intermediate (first) jump
                                  np.full(self.cfg['expt_samples2'], bs),  # beamsplitter jump
                                  # pad end with compensated readout jump
                                  np.full(16 * 5 + max_padded_length - t_offset[j] - t_ijump, readout)))
            arr = Compensate(arr - expt, expt, j + 1)
            IQArray.append(arr)
        self.cfg["IDataArray2"] = IQArray
        print([len(arr) for arr in IQArray])
        self.cfg['expt_samples2'] = len(IQArray[0])


        # Currently this shows the beamsplitter_time = 0 sample, change this for it to be useful
        # total_len = self.cfg['start'] + self.cfg['expts']*self.cfg['step'] + max_padded_length + 16*5
        # if not self.plotted_jumps:
        #     fig, ax = plt.subplots()
        #     for i in range(len(self.cfg["IDataArray2"])):
        #         ax.plot(self.cfg['IDataArray2'][i][:total_len], marker='o', label=f'Qubit {i + 1}')
        #     ax.legend()
        #     fig.canvas.draw()
        #     fig.show()
        #     # plt.show()
        #     self.plotted_jumps = True

