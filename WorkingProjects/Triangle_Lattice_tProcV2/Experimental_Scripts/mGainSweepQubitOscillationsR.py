import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FFEnvelope_Helpers import StepPulseArrays
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.ThreePartProgram_SweepWaveform import ThreePartProgram_SweepOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import soc

class GainSweepOscillationsR(SweepExperiment2D_plots):
    # {'reps': 1000, 'start': int(0), 'step': int(0.25 * 64), 'expts': 121, 'gainStart': 1000,
    #                      'gainStop': 1300, 'gainNumPoints': 11, 'relax_delay': 150}

    def init_sweep_vars(self):
        self.Program = ThreePartProgram_SweepOneFF
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Expt")
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.x_name = 'expt_samples'
        # self.x_points = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.z_value = 'population' # contrast or population
        self.ylabel = f'FF gain index {self.cfg["qubit_FF_index"]} (DAC units)'  # for plotting
        self.xlabel = 'Samples (0.291 ns)'  # for plotting


        self.cfg["IDataArray"] = StepPulseArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt')


    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        # print(self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Expt'])
        soc.reset_gens()
        if type(self.cfg["IDataArray"][0]) != type(None):
            self.cfg["IDataArray"][self.cfg["qubit_FF_index"] - 1] = \
                Compensated_Pulse(self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Expt'],
                                  self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Pulse'],
                                    int(self.cfg["qubit_FF_index"]))
        # soc.load_mem(list(range(10+2*self.cfg['expts'])), 'dmem')
    def debug(self, prog):

        # print(soc.read_mem(10+2*self.cfg['expts'], 'dmem'))
        print(prog)
        pass