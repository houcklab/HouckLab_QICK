import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import \
    CavitySpecFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots

from windfreak import SynthHD

class FFvsSpec(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = CavitySpecFFProg

        self.y_key = "pump_power"
        self.y_points = np.linspace(self.cfg["power_start"], self.cfg["power_stop"], self.cfg["power_steps"],
                                    dtype=int)

        self.x_key = "pump_freq"
        self.x_points = np.linspace(self.cfg["pump_freq_start"], self.cfg["pump_freq_stop"], self.cfg["pump_freq_steps"],
                                    dtype=int)

        self.z_value = 'IQ'  # contrast or population
        self.ylabel = 'Pump power (dB)'  # for plotting
        self.xlabel = 'Pump frequency (Hz)'  # for plotting

        self.synth = SynthHD(r'USB\VID_0483&PID_A3E5&MI_00\6&371C5830&0&0000')
        self.synth.init()

    def set_up_instance(self):
        # Set channel 0 power and frequency
        self.synth[0].power = -10.
        self.synth[0].frequency = 2.e9

        # Enable channel 0 output
        self.synth[0].enable = True