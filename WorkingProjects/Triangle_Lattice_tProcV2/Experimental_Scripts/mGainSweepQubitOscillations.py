import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
# from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *


class GainSweepOscillations(SweepExperiment2D_plots):
    # {'reps': 1000, 'start': int(0), 'step': int(0.25 * 64), 'expts': 121, 'gainStart': 1000,
    #                      'gainStop': 1300, 'gainNumPoints': 11, 'relax_delay': 150}

    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Expt")
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.x_key = 'expt_cycles'
        self.x_points = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.z_value = 'population' # contrast or population
        self.ylabel = f'FF gain index {self.cfg["qubit_FF_index"]} (DAC units)'  # for plotting
        self.xlabel = 'Time (2.32/16 ns)'  # for plotting

        # if np.array(self.cfg["IDataArray"]).any() != None:

        self.cfg["IDataArray"] = [None]*4
        self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '1']['Gain_Pulse'], 1)
        self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '2']['Gain_Pulse'], 2)
        self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '3']['Gain_Pulse'], 3)
        self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                           '4']['Gain_Pulse'], 4)


    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        if type(self.cfg["IDataArray"][0]) != type(None):
            self.cfg["IDataArray"][self.cfg["qubit_FF_index"] - 1] = \
                Compensated_Pulse(self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Expt'],
                                  self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Pulse'],
                                    int(self.cfg["qubit_FF_index"]))
            
