import numpy as np

from WorkingProjects.Triangle_Lattice.Basic_Experiments_Programs.SweepExperimentR1D import SweepExperimentR1D
from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFProg


class FFvsSpec(SweepExperiment2D):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(self.cfg["FF_gain_start"], self.cfg["FF_gain_stop"], self.cfg["FF_gain_steps"],
                                    dtype=int)

        # If using an RAveragerProgram, here you should define the cfg entries start, step, and stop
        self.x_key = "Spec frequency"

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = 'Fast flux gain'  # for plotting
        self.xlabel = 'Spec frequency'  # for plotting

    def acquire(self, *args, **kwargs):
        ### create waveforms

        return super().acquire(*args, **kwargs)