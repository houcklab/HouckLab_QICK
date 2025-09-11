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
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import correct_occ


class RampBeamsplitterBase(SweepExperimentND):
    # current_calibration_offset_dict = {'reps': 400, 'ramp_time': 0, 'relax_delay': 150,
    #                                    'start': 0, 'step': 8, 'expts': 71}

    def init_sweep_vars(self):
        self.Program = ThreePartProgram_SweepTwoFF
        self.z_value = 'population'  # contrast or population
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting

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

        self.cfg['expt_samples1'] = self.cfg['ramp_time']

    def set_up_instance(self):



        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain','Gain_Expt',self.cfg['ramp_time'])
        self.cfg["IDataArray2"] = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')

        t_offset = np.array(self.cfg['t_offset'], dtype=int)
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

    # def debug(self, prog):
    #     print(prog)

def collate(n1, n2):
    '''
    Converts shots of n1 and n2 into shots of (n2-n1).
    2 matrices of (timesteps, shots) where each shot is 0 or 1
    ---> 1 matrix of (timesteps, 4) where the 4 is the probability of 00, 01, 10, or 11\
    '''
    n1 = np.asarray(n1, dtype=int)
    n2 = np.asarray(n2, dtype=int)

    new_matrix = np.zeros((*n1.shape, 2, 2))
    for i in range(n1.shape[0]):
        for j in range(n1.shape[1]):
            new_matrix[i, j, n1[i, j], n2[i, j]] = 1
    new_matrix = np.reshape(new_matrix, (*n1.shape, 4))

    probs = np.mean(new_matrix, axis=1)

    return probs

class RampCurrentCorrelationsR(RampBeamsplitterR1D):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.z_value = 'population_shots'
        assert len(self.cfg['Qubit_Readout_List']) == 4, "Need MUX=4 for current correlations."



    def analyze(self, data):
        data_dict = data['data']
        if 'nn_correlations' in data_dict:
            return
        print("CurrentCalibration: Analyzing data.")
        shots_matrices, time = data_dict['population_shots'], data_dict['expt_samples']

        q1, q2, q3, q4 = shots_matrices
        # First store population data
        print(q1.shape)
        pop1, pop2, pop3, pop4 = (np.mean(q, axis=1).flatten() for q in (q1, q2, q3, q4))
        data_dict['population'] = [pop1, pop2, pop3, pop4]


        # Extract correlation data
        n21, n43 = q2 - q1, q4 - q3
        self.nn_correlations = np.mean(n21*n43, axis=1)
        data_dict['nn_correlations'] = self.nn_correlations

        if 'confusion_matrix' in data_dict:
            conf_mats = data_dict['confusion_matrix']
            assert len(conf_mats) == 4
            conf1, conf2, conf3, conf4 = conf_mats

            data_dict['population_corrected'] = [correct_occ(pop, conf) for pop, conf in zip((pop1,pop2,pop3,pop4), (conf1,conf2,conf3,conf4))]

            conf24 = np.kron(conf2, conf4)
            conf14 = np.kron(conf1, conf4)
            conf23 = np.kron(conf2, conf3)
            conf13 = np.kron(conf1, conf3)

            q24 = np.linalg.inv(conf24) @ collate(q2, q4).T
            q14 = np.linalg.inv(conf14) @ collate(q1, q4).T
            q23 = np.linalg.inv(conf23) @ collate(q2, q3).T
            q13 = np.linalg.inv(conf13) @ collate(q1, q3).T

            n24 = np.array([0, 0, 0, 1]) @ q24
            n14 = np.array([0, 0, 0, 1]) @ q14
            n23 = np.array([0, 0, 0, 1]) @ q23
            n13 = np.array([0, 0, 0, 1]) @ q13

            corrected_nn = n24 - n14 - n23 + n13

            data_dict['corrected_nn'] = corrected_nn


    def display(self, data=None, plotDisp=True, figNum=1, plotSave=True, block=True, fig_axs=None):
        '''Modify display to produce 2 axes, one for populations and one for correlations'''
        if fig_axs is None:
            if plt.fignum_exists(num=figNum):  # if figure with number already exists
                figNum = None
            fig, axs = plt.subplots(2, 1, figsize=(14, 8), num=figNum, tight_layout=True)

        return super().display(data, plotDisp, figNum, plotSave, block, (fig, axs))

    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs

        if 'nn_correlations' not in data['data']:
            self.analyze(data)

        # Display population data as usual
        self.z_value = 'population_corrected' if 'population_corrected' in data['data'] else 'population'
        SweepExperiment1D_lines._display_plot(self, data, (fig, [axs[0]]))
        self.z_value = 'population_shots'

        # Use the second axes to display correlation data
        ax = axs[-1]


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

        nn_correlations = data['data']['nn_correlations']
        ax.plot(X, nn_correlations, marker='o', label=ylabel, color='black')
        if 'corrected_nn' in data['data']:
            corrected_nn = data['data']['corrected_nn']
            ax.plot(X, corrected_nn, marker='o', label="Corrected "+ylabel, color='blue')

        ax.set_ylabel(ylabel)
        ax.set_xlabel(self.xlabel)
        ax.legend()

        return fig, ax

class RampDoubleJumpBase(RampBeamsplitterBase):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.plotted_jumps = False

    def set_up_instance(self):
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'ramp_initial_gain','Gain_Expt',self.cfg['ramp_time'])

        self.cfg["IDataArray2"] = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')
        # Add first jump
        total_len = self.cfg['start'] + self.cfg['step'] * self.cfg['expts']
        for i in range(len(self.cfg["IDataArray2"])):
            first_jump_gain = self.cfg['intermediate_jump_gains'][i]
            if first_jump_gain is not None:
                gain_expt, gain_bs = (self.cfg['FF_Qubits'][str(i+1)][ff_key] for ff_key in ['Gain_Expt', 'Gain_BS'])

                # Jumps relative to gain_expt
                first_jump = first_jump_gain - gain_expt
                second_jump = gain_bs - gain_expt
                IData = np.concatenate([np.full(self.cfg["intermediate_jump_samples"][i], first_jump), np.full(total_len+16-self.cfg['intermediate_jump_samples'][i], second_jump)])
                self.cfg["IDataArray2"][i] = Compensate(IData, gain_expt, str(i+1))

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

class RampDoubleJumpR1D(RampDoubleJumpBase, SweepExperiment1D_lines):
    pass

class RampDoubleJumpCorrelations(RampDoubleJumpBase, RampCurrentCorrelationsR):
    def init_sweep_vars(self):
        RampDoubleJumpBase.init_sweep_vars(self)
        self.z_value = 'population_shots'
        assert len(self.cfg['Qubit_Readout_List']) == 4, "Need MUX=4 for current correlations."