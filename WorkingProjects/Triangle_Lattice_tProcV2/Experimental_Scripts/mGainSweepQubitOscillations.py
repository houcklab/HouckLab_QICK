from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
# from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FFEnvelope_Helpers import StepPulseArrays


class GainSweepOscillations(SweepExperiment2D_plots):
    # {'reps': 1000, 'start': int(0), 'step': int(0.25 * 64), 'expts': 121, 'gainStart': 1000,
    #                      'gainStop': 1300, 'gainNumPoints': 11, 'relax_delay': 150}

    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Expt")
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.x_key = 'expt_samples'
        self.x_points = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.z_value = 'population' # contrast or population
        self.ylabel = f'FF gain index {self.cfg["qubit_FF_index"]} (DAC units)'  # for plotting
        self.xlabel = 'Time (4.65/16 ns)'  # for plotting

        # if np.array(self.cfg["IDataArray"]).any() != None:

        self.cfg["IDataArray"] = StepPulseArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt')

        self.count = 0


    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        self.cfg["IDataArray"] = StepPulseArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt')

        # self.count += 1
        #
        # if self.count in [1, 230]:
        #     total_IQArray = self.cfg["IDataArray"]
        #
        #     plt.figure()
        #     for i in range(len(total_IQArray)):
        #         print(f'Q{i + 1}: {total_IQArray[i]}')
        #         plt.plot(total_IQArray[i][:self.cfg['expt_samples']], label=f'Q{i + 1}')
        #     plt.legend()
        #     plt.show()