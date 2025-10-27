from jupyterlab.labextensions import list_flags
from qick import *
import matplotlib.pyplot as plt
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import datetime
import time
from scipy.signal import savgol_filter
import WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.FF_utils as FF
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFSpecCalibration_MUX import FFSpecCalibrationProgram
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFProg
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Basic_Experiments_Programs.AveragerProgramFF import RAveragerProgramFF
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Basic_Experiments_Programs.SweepExperimentR1D import SweepExperimentR1D
import numpy as np

from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.Compensated_Pulse_Jero import Compensated_Pulse

'''Two sweeps:
    One sweeping the initial point of a compensated pulse to see if the final value changes.
    A second sweeping the Gauss gain of a SpecSlice to see when the Stark Shift saturates.
    A third sweeping a Ramsey experiment to also see the detuning due to the qubit drive Stark Shift'''

class SweepFFInitPoint(SweepExperimentR1D):
    """
    Spec experiment that finds the qubit frequency during and after a fast-flux pulse
    """

    def init_sweep_vars(self):
        self.Program = FFSpecCalibrationProgram
        self.y_key = ("FF_Qubits", self.cfg["swept_qubit"], 'Gain_Init')
        self.y_points = self.cfg["list_of_gain_init"]
        # For the RAveragerProgram, you should define the cfg entries start, step, and stop too
        self.x_name = 'specfreqs'
        self.z_value = 'contrast'  # contrast or population
        self.ylabel = 'Delay time (2.32 ns)'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting

        self.cfg |= {
            "step": (self.cfg["SpecEnd"] - self.cfg["SpecStart"]) / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["SpecStart"],
            "expts": self.cfg["SpecNumPoints"]
        }

    def set_up_instance(self):
        self.cfg["IDataArray"] = [None] * 4
        # self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
        #     '1']['Gain_Init'], 1)
        # self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
        #     '2']['Gain_Init'], 2)
        # self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
        #     '3']['Gain_Init'], 3)
        # self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
        #     '4']['Gain_Init'], 4)

class StarkShift_vs_qubit_gain(SweepExperimentR1D):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        self.y_key = "qubit_gain"
        self.y_points = np.linspace(self.cfg["qubit_gain_start"], self.cfg["qubit_gain_stop"], self.cfg["qubit_gain_steps"],
                                    dtype=int)

        # If using an RAveragerProgram, here you should define the cfg entries start, step, and stop
        self.x_name = "Spec frequency (MHz)"
        self.cfg |= {
            "Gauss": False,
            "step": 2 * self.cfg["SpecSpan"] / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["qubit_freqs"][0] - self.cfg["SpecSpan"],
            "expts": self.cfg["SpecNumPoints"]
        }
        self.cfg.setdefault("qubit_length", 100)

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Qubit drive gain (DAC units)'  # for plotting
        self.xlabel = 'Spec frequency'  # for plotting

class StarkShift_vs_Gauss_gain(SweepExperimentR1D):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        self.y_key = "Gauss_gain"
        self.y_points = np.linspace(self.cfg["Gauss_gain_start"], self.cfg["Gauss_gain_stop"], self.cfg["Gauss_gain_steps"],
                                    dtype=int)

        # If using an RAveragerProgram, here you should define the cfg entries start, step, and stop
        self.x_name = "Spec frequency (MHz)"
        self.cfg |= {
            "Gauss": True,
            "step": 2 * self.cfg["SpecSpan"] / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["qubit_freqs"][0] - self.cfg["SpecSpan"],
            "expts": self.cfg["SpecNumPoints"]
        }

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Gauss gain'  # for plotting
        self.xlabel = 'Spec frequency'  # for plotting

        print(self.cfg['sigma'], self.cfg['qubit_gains'][0])
        self.sigma_gain_product = self.cfg['sigma'] * self.cfg['qubit_gains'][0]

    def set_up_instance(self):
        self.cfg["sigma"] = max(self.sigma_gain_product / self.cfg["Gauss_gain"], 0.005)