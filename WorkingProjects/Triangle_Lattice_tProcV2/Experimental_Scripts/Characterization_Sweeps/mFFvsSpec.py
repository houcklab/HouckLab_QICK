import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class FFvsSpec(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(self.cfg["FF_gain_start"], self.cfg["FF_gain_stop"], self.cfg["FF_gain_steps"],
                                    dtype=int)

        self.x_name = "qubit_freq_loop"
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100  ### length of CW drive in us

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Fast flux gain index {self.cfg["qubit_FF_index"]}'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting