import time

import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class FluxStabilitySpec(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        self.y_key = "minutes_passed"
        self.y_points = self.cfg["delay_minutes"] * np.arange(self.cfg["num_steps"])

        self.x_name = "qubit_freq_loop"
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100  ### length of CW drive in us

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Minutes passed'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting

        self.last_spec_time = time.time()

    def set_up_instance(self):
        self.soc.reset_gens()

        if self.cfg["minutes_passed"] != 0:
            spec_time = time.time() - self.last_spec_time
            print(spec_time)
            print("wait:", self.cfg["delay_minutes"] * 60 - spec_time)
            time.sleep(max(0, self.cfg["delay_minutes"] * 60 - spec_time))
            self.last_spec_time = time.time()