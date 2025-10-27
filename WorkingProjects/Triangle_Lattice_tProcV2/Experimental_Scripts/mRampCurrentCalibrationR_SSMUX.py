from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperimentND import \
    SweepExperimentND
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram_SweepWaveform import \
    ThreePartProgram_SweepTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers, SweepHelpers, CorrelationAnalysis
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_plots import SweepExperiment1D_plots
import datetime
# from WorkingProjects.Triangle_Lattice_tProcV2.Experiment_Scripts.mRabiOscillations import WalkFFProg

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import correct_occ


class RampBeamsplitterBase(SweepExperimentND):
    # current_calibration_offset_dict = {'reps': 400, 'ramp_time': 0, 'relax_delay': 150,
    #                                    'start': 0, 'step': 8, 'expts': 71}

    def init_sweep_vars(self):
        self.Program = ThreePartProgram_SweepTwoFF
        self.z_value = 'population'  # contrast or population
        # self.z_value = 'population_shots'  # contrast or population
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting



    def set_up_instance(self):
        self.cfg['expt_samples1'] = self.cfg['ramp_time']
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'ramp_initial_gain','Gain_Expt',self.cfg['ramp_time'])
        self.cfg["IDataArray2"] = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')

        t_offset = np.asarray(self.cfg['t_offset'], dtype=int)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif not isinstance(t_offset, (list, np.ndarray, tuple)):
            raise TypeError('t_offset must be an int or array like of ints')


        t_offset -= np.min(t_offset)
        print("Actual offsets:", t_offset)

        assert((t_offset >= 0).all())
        self.cfg['max_t_offset'] = np.max(t_offset)
        for i in range(len(self.cfg["IDataArray2"])):
            self.cfg["IDataArray2"][i] = np.pad(self.cfg["IDataArray2"][i], (t_offset[i], 0), mode='constant',
                                            constant_values=self.cfg["IDataArray1"][i][self.cfg['expt_samples1']-1])

class RampBeamsplitterOffsetR(RampBeamsplitterBase, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.y_key = ("t_offset", self.cfg["swept_qubit"]-1)
        self.y_points = np.linspace(self.cfg['offsetStart'], self.cfg['offsetStop'], self.cfg['offsetNumPoints'], dtype=int)
        self.ylabel= f"Offset time of Qubit {self.cfg["swept_qubit"]} (4.65/16 ns)"

class RampBeamsplitterGainR(RampBeamsplitterBase, GainSweepOscillationsR):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.y_key = ('FF_Qubits', str(self.cfg['swept_qubit']), 'Gain_BS')
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.ylabel = f'FF gain (Qubit {self.cfg["swept_qubit"]})'  # for plotting

class RampBeamsplitterR1D(RampBeamsplitterBase, SweepExperiment1D_lines):
    def init_sweep_vars(self):
        super().init_sweep_vars()

    # def debug(self, prog):
    #     print(prog)




class RampCurrentCorrelationsR(RampBeamsplitterR1D):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.z_value = 'population_shots'
        assert len(self.cfg['Qubit_Readout_List']) >= 4, "Need MUX >= 4 for current correlations."

        self.readout_pair_1 = self.cfg.get('readout_pair_1', [1,2])
        self.readout_pair_2 = self.cfg.get('readout_pair_2', [3,4])

        for index in self.readout_pair_1 + self.readout_pair_2:
            if index not in self.cfg['Qubit_Readout_List']:
                raise ValueError(f'readout pair qubits must be in readout list, given: {index}')

        print(f'readout pairs are: {self.readout_pair_1}, {self.readout_pair_2}')

    def process_data(self, sweep_indices, sweep_values):
        data_dict = self.data['data']
        readout_list = data_dict['readout_list']

        if 'nn_correlations' not in data_dict:
            data_dict['nn_correlations'] = np.full_like(data_dict['population'][0], np.nan)

        shots_matrices = [data_dict['population_shots'][ro_ind][*sweep_indices] for ro_ind in range(len(readout_list))]
        q1 = shots_matrices[readout_list.index(self.readout_pair_1[0])]
        q2 = shots_matrices[readout_list.index(self.readout_pair_1[1])]
        q3 = shots_matrices[readout_list.index(self.readout_pair_2[0])]
        q4 = shots_matrices[readout_list.index(self.readout_pair_2[1])]

        self.nn_correlations = CorrelationAnalysis.get_nn_correlations(q1, q2, q3, q4)
        data_dict['nn_correlations'][*sweep_indices] = self.nn_correlations

        if 'confusion_matrix' in data_dict:
            if 'corrected_nn' not in data_dict:
                data_dict['corrected_nn'] = np.full_like(data_dict['population'][0], np.nan)

            conf_mats = data_dict['confusion_matrix']
            conf1 = conf_mats[readout_list.index(self.cfg['readout_pair_1'][0])]
            conf2 = conf_mats[readout_list.index(self.cfg['readout_pair_1'][1])]
            conf3 = conf_mats[readout_list.index(self.cfg['readout_pair_2'][0])]
            conf4 = conf_mats[readout_list.index(self.cfg['readout_pair_2'][1])]

            corrected_nn = CorrelationAnalysis.get_corrected_nn_correlations(q1, q2, q3, q4, [conf1, conf2, conf3, conf4])

            data_dict['corrected_nn'][*sweep_indices] = corrected_nn


    def _make_subplots(self, figNum, count):
        '''Modify display to produce 2 axes, one for populations and one for correlations'''
        if plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum = None
        fig, axs = plt.subplots(2, 1, figsize=(14, 8), num=figNum, tight_layout=True)
        return fig, axs

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


class SweepRampLengthCorrelations(RampCurrentCorrelationsR, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        RampCurrentCorrelationsR.init_sweep_vars(self)
        self.y_key = "ramp_time"
        self.y_points = np.linspace(self.cfg["ramp_length_start"], self.cfg["ramp_length_stop"],
                                    self.cfg["ramp_length_num_points"], dtype=int)
        self.ylabel = f"Ramp length (samples = 0.290 ns)"

    def _make_subplots(self, figNum, count):
        '''Modify display to produce 2 axes, one for populations and one for correlations'''
        if plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum = None
        fig, axs = plt.subplots(1, 1, figsize=(14, 8), num=figNum, tight_layout=True)
        return fig, [axs]

    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs

        fig.suptitle(str(self.titlename), fontsize=16)

        y_key_name = SweepHelpers.key_savename(self.y_key)
        try:
            x_key_name = self.x_key
        except:
            x_key_name = self.loop_names[0]

        X, Y = data['data'][x_key_name], data['data'][y_key_name]

        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]
        Z_mat = data['data']['corrected_nn']

        q1, q2 = self.cfg['readout_pair_1']
        q3, q4 = self.cfg['readout_pair_2']
        colorbar_label = rf'$\langle n_{{ {q2}{q1}}} n_{{{q4}{q3}}}\rangle$'

        ax_im = axs[0].imshow(
            Z_mat,
            aspect='auto',
            extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                    Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
            origin='lower',
            interpolation='none')
        axs[0].set_ylabel(self.ylabel)
        axs[0].set_xlabel(self.xlabel)
        axs[0].set_title(rf'$\langle n_{{ {q2}{q1}}} n_{{{q4}{q3}}}\rangle$')
        cbar = fig.colorbar(ax_im, ax=axs[0], extend='both')
        cbar.set_label(colorbar_label, rotation=90)

        fig.show()
        return fig, axs

    def _update_fig(self, data, fig, axs):
        im = axs[0].get_images()[-1],
        im = im[-1]
        cbar = im.colorbar
        im.set_data(data['data']["corrected_nn"])
        im.autoscale()
        cbar.update_normal()


class RampCorrelations_Sweep_Base(RampCurrentCorrelationsR, SweepExperiment2D_plots):

    def _make_subplots(self, figNum, count):
        '''Modify display to produce 2 axes, one for populations and one for correlations'''
        if plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum = None
        fig, axs = plt.subplots(1, 1, figsize=(14, 8), num=figNum, tight_layout=True)
        return fig, [axs]

    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs

        fig.suptitle(str(self.titlename), fontsize=16)

        y_key_name = SweepHelpers.key_savename(self.y_key)
        try:
            x_key_name = self.x_key
        except:
            x_key_name = self.loop_names[0]

        X, Y = data['data'][x_key_name], data['data'][y_key_name]

        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]
        Z_mat = data['data']['corrected_nn']

        q1, q2 = self.cfg['readout_pair_1']
        q3, q4 = self.cfg['readout_pair_2']
        colorbar_label = rf'$\langle n_{{ {q2}{q1}}} n_{{{q4}{q3}}}\rangle$'

        ax_im = axs[0].imshow(
            Z_mat,
            aspect='auto',
            extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                    Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
            origin='lower',
            interpolation='none')
        axs[0].set_ylabel(self.ylabel)
        axs[0].set_xlabel(self.xlabel)
        axs[0].set_title(rf'$\langle n_{{ {q2}{q1}}} n_{{{q4}{q3}}}\rangle$')
        cbar = fig.colorbar(ax_im, ax=axs[0], extend='both')
        cbar.set_label(colorbar_label, rotation=90)

        fig.show()
        return fig, axs

    def _update_fig(self, data, fig, axs):
        im = axs[0].get_images()[-1],
        im = im[-1]
        cbar = im.colorbar
        im.set_data(data['data']["corrected_nn"])
        im.autoscale()
        cbar.update_normal()


class RampCorrelations_Sweep_BS_Gain(RampCorrelations_Sweep_Base, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        RampCurrentCorrelationsR.init_sweep_vars(self)
        self.y_key = ('FF_Qubits', str(self.cfg['swept_qubit']), 'Gain_BS')
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.ylabel = f'FF gain (Qubit {self.cfg["swept_qubit"]})'  # for plotting



class RampCorrelations_Sweep_BS_Offset(RampCorrelations_Sweep_Base, SweepExperiment2D_plots):

    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.y_key = ("t_offset", self.cfg["swept_qubit"] - 1)
        self.y_points = np.linspace(self.cfg['offsetStart'], self.cfg['offsetStop'], self.cfg['offsetNumPoints'],
                                    dtype=int)
        self.ylabel = f"Offset time of Qubit {self.cfg["swept_qubit"]} (4.65/16 ns)"

    def set_up_instance(self):
        print(f'setting up instance')
        print(f't offsets: {self.cfg["t_offset"]}')
        super().set_up_instance()

######################################

# Double Jump Experiments

######################################

class RampDoubleJumpBase(RampBeamsplitterBase):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.plotted_jumps = False

    def set_up_instance(self):
        self.cfg['expt_samples1'] = self.cfg['ramp_time']
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain','Gain_Expt',self.cfg['expt_samples1'])

        self.cfg["IDataArray2"] = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')
        # Add first jump
        total_len = self.cfg['start'] + self.cfg['step'] * self.cfg['expts']
        gains_expt = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gains_bs = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        for i in range(len(self.cfg["IDataArray2"])):
            first_jump_gain = self.cfg['intermediate_jump_gains'][i]
            if first_jump_gain is not None:
                # Jumps relative to gain_expt
                first_jump = first_jump_gain - gains_expt[i]
                second_jump = gains_bs[i] - gains_expt[i]
                IData = np.concatenate([np.full(self.cfg["intermediate_jump_samples"][i], first_jump), np.full(total_len+16-self.cfg['intermediate_jump_samples'][i], second_jump)])
                self.cfg["IDataArray2"][i] = Compensate(IData, gains_expt[i], i+1)

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

        if not self.plotted_jumps:
            fig, ax = plt.subplots()
            for i in range(len(self.cfg["IDataArray2"])):
                ax.plot(self.cfg['IDataArray2'][i][:total_len], marker='o', label=f'Qubit {i+1}')
            ax.legend()
            fig.canvas.draw()
            fig.show()
            # plt.show()
            self.plotted_jumps = True

class RampDoubleJumpGainR(RampDoubleJumpBase, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        RampDoubleJumpBase.init_sweep_vars(self)
        self.y_key = ("intermediate_jump_gains", self.cfg["swept_qubit"] - 1)
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'],
                                    dtype=int)
        self.ylabel = "Intermediate Jump Gain"

class RampDoubleJumpIntermediateSamplesR(RampDoubleJumpBase, SweepExperiment2D_plots):
    def init_sweep_vars(self):
        RampDoubleJumpBase.init_sweep_vars(self)
        self.y_key = ("intermediate_jump_samples", self.cfg["swept_qubit"] - 1)
        self.y_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_stop'], self.cfg['samples_numPoints'],
                                    dtype=int)
        self.ylabel = "Intermediate Jump Samples (4.65/16 ns)"

class RampDoubleJump_BS_GainR(RampDoubleJumpBase, GainSweepOscillationsR):
    def init_sweep_vars(self):
        RampDoubleJumpBase.init_sweep_vars(self)
        self.y_key = ('FF_Qubits', str(self.cfg['swept_qubit']), 'Gain_BS')
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'],
                                    dtype=int)
        self.ylabel = "Beamsplitter Jump Gain"


class RampDoubleJumpR1D(RampDoubleJumpBase, SweepExperiment1D_lines):
    pass

class RampDoubleJumpCorrelations(RampDoubleJumpBase, RampCurrentCorrelationsR):
    def init_sweep_vars(self):
        RampDoubleJumpBase.init_sweep_vars(self)
        self.z_value = 'population_shots'
        assert len(self.cfg['Qubit_Readout_List']) >= 4, "Need MUX>=4 for current correlations."