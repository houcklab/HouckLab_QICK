import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class CrosstalkRandomFFvsSpec(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100  ### length of CW drive in us

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Fast flux gain index {self.cfg["qubit_FF_index"]}'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting

        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_key = "Gain_Pulse_vector"
        self.y_points = self.cfg["random_ff_gain_matrix"]



    def set_up_instance(self):
        for qubit, Gain_Pulse in zip(self.cfg["FF_Qubits"], self.cfg["Gain_Pulse_vector"]):
            self.cfg["FF_Qubits"][qubit]["Gain_Pulse"] = Gain_Pulse
