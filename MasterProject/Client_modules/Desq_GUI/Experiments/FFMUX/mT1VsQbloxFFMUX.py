"""
mT1VsQbloxFFMUX.py - T1 Decay vs Qblox DC Voltage 2D Sweep

Sweeps T1 decay measurement while varying the Qblox DC voltage.
This allows characterizing T1 vs flux with slow DC bias changes,
complementing the fast-flux based T1 vs FF sweeps.

Output: 2D heatmap of IQ contrast or population vs (delay time, Qblox voltage)
"""

import time
import numpy as np

from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Qblox_Functions import Qblox
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1Program
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class T1VsQbloxFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: T1 decay vs Qblox DC voltage.
    
    Sweeps over Qblox DAC voltage on the outer loop (with settling time),
    and T1 delay time on the inner QICK loop.
    
    Required config entries:
        - Qblox_start: float, starting Qblox voltage
        - Qblox_stop: float, ending Qblox voltage
        - Qblox_steps: int, number of voltage steps
        - DAC: int, Qblox DAC channel number
        - stop_delay_us: float, maximum T1 delay in us
        - expts: int, number of delay points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
        - Qblox_settle_time: float, settling time after voltage change in seconds (default 1.0)
    """

    def init_sweep_vars(self):
        self.Program = T1Program

        # Outer sweep: Qblox voltage
        self.y_key = "Qblox_voltage"
        self.y_points = np.linspace(
            self.cfg["Qblox_start"],
            self.cfg["Qblox_stop"],
            self.cfg["Qblox_steps"]
        )

        # Inner QICK loop: delay time
        self.x_name = "delay_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Qblox voltage (DAC {self.cfg["DAC"]})'
        self.xlabel = 'Delay time (us)'

        # Initialize Qblox interface
        self.QbloxClass = Qblox()
        
        # Settling time
        self.settle_time = self.cfg.get("Qblox_settle_time", 1.0)

        print(f"T1VsQblox: Sweeping voltage from {self.y_points[0]:.4f} to {self.y_points[-1]:.4f} V")

    def set_up_instance(self):
        """Set Qblox voltage before each sweep iteration."""
        voltage = self.cfg["Qblox_voltage"]
        self.QbloxClass.set_voltage([self.cfg['DAC']], [voltage])
        time.sleep(self.settle_time)


class SpecVsQbloxFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Qubit spectroscopy vs Qblox DC voltage.
    
    Sweeps over Qblox DAC voltage on the outer loop (with settling time),
    and qubit drive frequency on the inner QICK loop.
    
    Required config entries:
        - Qblox_start: float, starting Qblox voltage
        - Qblox_stop: float, ending Qblox voltage
        - Qblox_steps: int, number of voltage steps
        - DAC: int, Qblox DAC channel number
        - SpecSpan: float, frequency span around qubit_freqs[0] in MHz
        - SpecNumPoints: int, number of frequency points
        - Gauss: bool, whether to use Gaussian pulse
        - qubit_gain: int, CW drive gain (if not Gauss)
        - Gauss_gain: int, Gaussian drive gain (if Gauss)
        - sigma: float, Gaussian sigma in us (if Gauss)
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
        - Qblox_settle_time: float, settling time after voltage change in seconds (default 1.0)
    """

    def init_sweep_vars(self):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
        self.Program = QubitSpecSliceFFProg

        # Outer sweep: Qblox voltage
        self.y_key = "Qblox_voltage"
        self.y_points = np.linspace(
            self.cfg["Qblox_start"],
            self.cfg["Qblox_stop"],
            self.cfg["Qblox_steps"]
        )

        # Inner QICK loop: qubit frequency
        self.x_name = "qubit_freq_loop"
        
        # Configure RAverager parameters
        self.cfg |= {
            "step": 2 * self.cfg["SpecSpan"] / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["qubit_freqs"][0] - self.cfg["SpecSpan"],
            "expts": self.cfg["SpecNumPoints"]
        }
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Qblox voltage (DAC {self.cfg["DAC"]})'
        self.xlabel = 'Spec frequency (MHz)'

        # Initialize Qblox interface
        self.QbloxClass = Qblox()
        
        # Settling time
        self.settle_time = self.cfg.get("Qblox_settle_time", 1.0)

        print(f"SpecVsQblox: Sweeping voltage from {self.y_points[0]:.4f} to {self.y_points[-1]:.4f} V")

    def set_up_instance(self):
        """Set Qblox voltage before each sweep iteration."""
        voltage = self.cfg["Qblox_voltage"]
        self.QbloxClass.set_voltage([self.cfg['DAC']], [voltage])
        time.sleep(self.settle_time)


class RamseyVsQbloxFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Ramsey (T2*) vs Qblox DC voltage.
    
    Sweeps over Qblox DAC voltage on the outer loop (with settling time),
    and Ramsey delay time on the inner QICK loop.
    
    Required config entries:
        - Qblox_start: float, starting Qblox voltage
        - Qblox_stop: float, ending Qblox voltage
        - Qblox_steps: int, number of voltage steps
        - DAC: int, Qblox DAC channel number
        - stop_delay_us: float, maximum Ramsey delay in us
        - expts: int, number of delay points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - freq_shift: float, frequency detuning in MHz
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
        - Qblox_settle_time: float, settling time after voltage change in seconds (default 1.0)
    """

    def init_sweep_vars(self):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RProgram
        self.Program = T2RProgram

        # Set default values
        self.cfg.setdefault('qubit_drive_freq', self.cfg['qubit_freqs'][0] + self.cfg.get("freq_shift", 0))
        self.cfg.setdefault('pi_gain', self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)

        # Outer sweep: Qblox voltage
        self.y_key = "Qblox_voltage"
        self.y_points = np.linspace(
            self.cfg["Qblox_start"],
            self.cfg["Qblox_stop"],
            self.cfg["Qblox_steps"]
        )

        # Inner QICK loop: delay time
        self.x_name = "delay_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Qblox voltage (DAC {self.cfg["DAC"]})'
        self.xlabel = 'Delay time (us)'

        # Initialize Qblox interface
        self.QbloxClass = Qblox()
        
        # Settling time
        self.settle_time = self.cfg.get("Qblox_settle_time", 1.0)

        print(f"RamseyVsQblox: Sweeping voltage from {self.y_points[0]:.4f} to {self.y_points[-1]:.4f} V")

    def set_up_instance(self):
        """Set Qblox voltage before each sweep iteration."""
        voltage = self.cfg["Qblox_voltage"]
        self.QbloxClass.set_voltage([self.cfg['DAC']], [voltage])
        time.sleep(self.settle_time)
