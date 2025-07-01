import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperimentR1D import SweepExperimentR1D
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg


class FFvsSpec(SweepExperimentR1D):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(self.cfg["FF_gain_start"], self.cfg["FF_gain_stop"], self.cfg["FF_gain_steps"],
                                    dtype=int)

        # If using an RAveragerProgram, here you should define the cfg entries start, step, and stop
        self.x_name = "Spec frequency (MHz)"
        self.cfg |= {
            "step": 2 * self.cfg["SpecSpan"] / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["qubit_freqs"][0] - self.cfg["SpecSpan"],
            "expts": self.cfg["SpecNumPoints"]
        }
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100  ### length of CW drive in us

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Fast flux gain index {self.cfg["qubit_FF_index"]}'  # for plotting
        self.xlabel = 'Spec frequency'  # for plotting