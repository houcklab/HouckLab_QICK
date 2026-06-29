import math

import numpy as np
from matplotlib import pyplot as plt

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import \
    SweepExperiment2D_plots
from WorkingProjects.triangle_lattice_quench.Helpers import FFEnvelope_Helpers
from WorkingProjects.triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensate
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mQuenchExperiment import QuenchProgram
from WorkingProjects.triangle_lattice_quench.Helpers.FFEnvelope_Helpers import StepPulseArrays


class QuenchDynamicsSweepBase(SweepExperiment2D_plots):
    def init_sweep_vars(self):

        self.Program = QuenchProgram
        self.z_value = 'population_corrected'

        self.y_key = None
        self.y_points = None
        self.ylabel = None

        self.x_key = 'expt_samples_dynamics'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting


        self.cfg['init_pulse'] = self.cfg.get('init_pulse', True)


    def set_up_instance(self):

        ### round samples to nearest integer
        self.cfg['expt_samples_ramp'] = round(self.cfg['expt_samples_ramp'])
        self.cfg['expt_samples_quench'] = round(self.cfg['expt_samples_quench'])
        self.cfg['expt_samples_dynamics'] = round(self.cfg['expt_samples_dynamics'])


        ### option to offset step pulses
        t_offset = self.cfg.get('t_offset',0)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif isinstance(t_offset, (list, np.ndarray, tuple)):
            np.array(t_offset, dtype=int)
        else:
            raise TypeError('t_offset must be an int or array like of ints')


        t_offset -= np.min(t_offset)
        # print("Actual offsets:", t_offset)

        assert ((t_offset >= 0).all())
        ff_ro_pad = math.ceil(np.max(t_offset) / 16) * 16

        self.t_offset = t_offset

        ### Ramp
        IQArray_ramp = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'Gain_RampInit',
                                                                           'Gain_Expt', self.cfg['expt_samples_ramp'])

        self.cfg["IQArray_ramp"] = IQArray_ramp

        ### Quench
        # TODO for now reuse the Gain_BS label, might want to change in future
        gain_ramp = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gain_quench = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        gain_dynamics = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Dynamics')
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Readout')

        # print(f'gain_ramp: {gain_ramp}')
        # print(f'gain_quench: {gain_quench}')
        # print(f'gain_readout: {gain_readout}')

        IQArray_quench = []
        for j in range(len(gain_ramp)):
            ramp = gain_ramp[j]
            quench = gain_quench[j]

            arr = np.concatenate([np.full(t_offset[j], ramp),
                                  np.full(self.cfg['expt_samples_quench'], quench)])
            arr = Compensate(arr - ramp, ramp, j + 1)
            IQArray_quench.append(arr)

        ### Dynamics
        IQArray_dynamics = []
        for j in range(len(gain_quench)):
            quench = gain_quench[j]
            dynamics = gain_dynamics[j]


            arr = np.concatenate([np.full(t_offset[j], quench),
                                  np.full(self.cfg['expt_samples_dynamics'], dynamics)])
            arr = Compensate(arr - quench, quench, j + 1)
            IQArray_dynamics.append(arr)

        ### Readout
        IQArray_readout = []
        for j in range(len(gain_ramp)):
            dynamics = gain_dynamics[j]
            readout = gain_readout[j]

            arr = np.concatenate([np.full(t_offset[j], dynamics),
                                  np.full(ff_ro_pad - t_offset[j], readout)])
            arr = Compensate(arr - dynamics, dynamics, j + 1)
            IQArray_readout.append(arr)

        self.cfg["IQArray_quench"] = IQArray_quench
        self.cfg["IQArray_dynamics"] = IQArray_dynamics
        self.cfg["IQArray_readout"] = IQArray_readout

        # print(f'expt_samples_ramp: {self.cfg["expt_samples_ramp"]}')
        # print(f'expt_samples_quench: {self.cfg["expt_samples_quench"]}')
        # print(f'expt_samples_dynamics: {self.cfg["expt_samples_dynamics"]}')

        # total_IQArray = [np.concatenate([IQArray_ramp[i], IQArray_quench[i], IQArray_dynamics[i], IQArray_readout[i]]) for i in range(len(IQArray_quench))]
        #
        # if False and self.cfg['expt_samples_dynamics'] > 150:
        #     plt.figure()
        #     for i in range(len(total_IQArray)):
        #         print(f'Q{i+1}: {total_IQArray[i]}')
        #         plt.plot(total_IQArray[i], label=f'Q{i+1}')
        #     plt.axvline(self.cfg['expt_samples_ramp'], color='purple', linestyle='--')
        #     plt.axvline(self.cfg['expt_samples_ramp'] + self.cfg['expt_samples_quench'], color='purple', linestyle='--')
        #     plt.axvline(self.cfg['expt_samples_ramp'] + self.cfg['expt_samples_quench'] + self.cfg['expt_samples_dynamics'], color='purple', linestyle='--')
        #     plt.legend()
        #     plt.show()

class QuenchDynamicsSweepGain(QuenchDynamicsSweepBase):
    def init_sweep_vars(self):

        super().init_sweep_vars()


        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Dynamics")
        self.y_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'],
                                    self.cfg['gain_num_points'])
        self.ylabel = 'FF gain (a.u.)'  # for plotting

        self.count = 0

    def set_up_instance(self):
        super().set_up_instance()

        self.count += 1

        if False and self.count in [1,230]:
            total_IQArray = [np.concatenate([self.cfg["IQArray_ramp"][i], self.cfg["IQArray_ramp"][i], self.cfg["IQArray_quench"][i], self.cfg["IQArray_dynamics"][i]]) for i in range(len(self.cfg["IQArray_readout"]))]


            ramp_end = self.cfg['expt_samples_ramp']
            quench_end = ramp_end + self.cfg['expt_samples_quench']
            dynamics_end = quench_end + self.cfg['expt_samples_dynamics']
            plt.figure()
            for i in range(len(total_IQArray)):
                print(f'Q{i+1}: {total_IQArray[i]}')
                plt.plot(total_IQArray[i], label=f'Q{i+1}')
            plt.axvline(ramp_end, color='purple', linestyle='--')
            plt.text(ramp_end, 0, 'ramp end', rotation=90, va='center')

            plt.axvline(quench_end, color='purple', linestyle='--')
            plt.text(quench_end, 0, 'quench end', rotation=90, va='center')

            plt.axvline(dynamics_end, color='purple', linestyle='--')
            plt.text(dynamics_end, 0, 'dynamics end', rotation=90, va='center')
            plt.legend()
            plt.show()

