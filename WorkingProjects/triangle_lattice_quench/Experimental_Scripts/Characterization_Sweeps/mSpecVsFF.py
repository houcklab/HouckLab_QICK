import numpy as np

from triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSpecSlice import QubitSpecSliceProg
from triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class SpecVsFF(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceProg

        self.y_key = ("FF_Pulses", int(self.cfg["qubit_FF_index"]))
        self.y_points = np.linspace(self.cfg["FF_gain_start"], self.cfg["FF_gain_stop"], self.cfg["FF_gain_steps"],
                                    dtype=int)

        self.x_name = "qubit_freq_loop"
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 50 ### length of CW drive in us

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Fast flux gain index {self.cfg["qubit_FF_index"]}'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting