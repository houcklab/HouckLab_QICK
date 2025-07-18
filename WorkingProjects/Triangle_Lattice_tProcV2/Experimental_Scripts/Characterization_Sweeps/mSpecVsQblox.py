import time

import numpy as np

from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Qblox_Functions import Qblox
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg


class SpecVsQblox(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        self.y_key = "Qblox_voltage"
        self.y_points = np.linspace(self.cfg["Qblox_start"], self.cfg["Qblox_stop"], self.cfg["Qblox_steps"])

        # If using an RAveragerProgram, here you should define the cfg entries start, step, and stop
        self.x_name = "qubit_freq_loop"
        self.cfg |= {
            "step": 2 * self.cfg["SpecSpan"] / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["qubit_freqs"][0] - self.cfg["SpecSpan"],
            "expts": self.cfg["SpecNumPoints"]
        }
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100  ### length of CW drive in us

        self.z_value = 'contrast'  # contrast or population
        self.ylabel = f'Qblox voltage DAC {self.cfg["DAC"]}'  # for plotting
        self.xlabel = 'Spec frequency'  # for plotting

        self.QbloxClass = Qblox()

        print(self.y_points)
    def set_up_instance(self):

        self.QbloxClass.set_voltage([self.cfg['DAC']], [self.cfg["Qblox_voltage"]])
        # self.QbloxClass.print_voltages()
        time.sleep(1)