import numpy as np

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class SpecVsGain(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg
        if self.cfg['Gauss']:
            print("'Gauss' is enabled, whereas this experiment sweeps CW gain.")
        self.y_key = "qubit_gain"
        self.y_points = np.linspace(self.cfg["qubit_gain_start"], self.cfg["qubit_gain_stop"], self.cfg["qubit_gain_steps"],
                                    dtype=int)

        self.x_name = "qubit_freq_loop"
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100  ### length of CW drive in us

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Qubit gain'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting