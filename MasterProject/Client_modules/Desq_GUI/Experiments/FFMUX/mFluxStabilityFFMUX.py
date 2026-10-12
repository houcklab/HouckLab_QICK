"""
mFluxStabilityFFMUX.py - Flux Stability (Spectroscopy vs Time) 2D Sweep

Repeatedly measures qubit spectroscopy over time to monitor flux stability.
This allows tracking qubit frequency drift and characterizing flux noise
over long timescales (minutes to hours).

Output: 2D heatmap of IQ contrast vs (spec frequency, time)
"""

import time
import datetime
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class FluxStabilityFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Qubit spectroscopy vs time for flux stability monitoring.
    
    Repeatedly runs spectroscopy at fixed intervals to track frequency drift.
    The outer loop is a time sweep with configurable delays between measurements.
    
    Required config entries:
        - delay_minutes: float, delay between measurements in minutes
        - num_steps: int, number of time steps
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
    """

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        # Outer sweep: time index
        self.y_key = "time_index"
        self.y_points = np.arange(self.cfg["num_steps"])

        # Inner QICK loop: qubit frequency
        self.x_name = "qubit_freq_loop"
        
        # Set CW drive length if not specified
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Time (step = {self.cfg["delay_minutes"]:.2f} min)'
        self.xlabel = 'Spec frequency (MHz)'

        # Store delay in seconds
        self.delay_seconds = self.cfg["delay_minutes"] * 60
        
        # Track timestamps
        self.timestamps = []
        self.start_time = time.time()
        
        # Estimate total time
        total_minutes = self.cfg["delay_minutes"] * self.cfg["num_steps"]
        estimated_end = datetime.datetime.now() + datetime.timedelta(minutes=total_minutes)
        print(f"FluxStability: Running {self.cfg['num_steps']} steps with {self.cfg['delay_minutes']:.2f} min delay")
        print(f"Estimated completion: {estimated_end.strftime('%A %B %d, %I:%M:%S %p')}")

    def set_up_instance(self):
        """Wait for the specified delay before each iteration."""
        current_step = self.cfg["time_index"]
        
        # Record timestamp
        self.timestamps.append(time.time() - self.start_time)
        
        # Wait for delay (skip on first iteration)
        if current_step > 0:
            elapsed = time.time() - self.start_time
            target_time = current_step * self.delay_seconds
            wait_time = max(0, target_time - elapsed)
            
            if wait_time > 0:
                print(f"Step {current_step}/{self.cfg['num_steps']}: Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
        
        # Print progress
        elapsed_min = (time.time() - self.start_time) / 60
        print(f"Step {current_step + 1}/{self.cfg['num_steps']} at t = {elapsed_min:.2f} min")

    def analyze(self, data, **kwargs):
        """Add timestamps to saved data."""
        data['data']['timestamps_seconds'] = np.array(self.timestamps)
        data['data']['delay_minutes'] = self.cfg["delay_minutes"]
        return super().analyze(data, **kwargs)


class T1StabilityFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: T1 decay vs time for stability monitoring.
    
    Repeatedly runs T1 measurements at fixed intervals to track T1 drift.
    
    Required config entries:
        - delay_minutes: float, delay between measurements in minutes
        - num_steps: int, number of time steps
        - stop_delay_us: float, maximum T1 delay in us
        - expts: int, number of delay points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
    """

    def init_sweep_vars(self):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1Program
        self.Program = T1Program

        # Outer sweep: time index
        self.y_key = "time_index"
        self.y_points = np.arange(self.cfg["num_steps"])

        # Inner QICK loop: delay time
        self.x_name = "delay_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Time (step = {self.cfg["delay_minutes"]:.2f} min)'
        self.xlabel = 'Delay time (us)'

        # Store delay in seconds
        self.delay_seconds = self.cfg["delay_minutes"] * 60
        
        # Track timestamps
        self.timestamps = []
        self.start_time = time.time()

    def set_up_instance(self):
        """Wait for the specified delay before each iteration."""
        current_step = self.cfg["time_index"]
        self.timestamps.append(time.time() - self.start_time)
        
        if current_step > 0:
            elapsed = time.time() - self.start_time
            target_time = current_step * self.delay_seconds
            wait_time = max(0, target_time - elapsed)
            if wait_time > 0:
                time.sleep(wait_time)

    def analyze(self, data, **kwargs):
        """Add timestamps to saved data."""
        data['data']['timestamps_seconds'] = np.array(self.timestamps)
        return super().analyze(data, **kwargs)


class RamseyStabilityFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Ramsey (T2*) vs time for stability monitoring.
    
    Repeatedly runs Ramsey measurements at fixed intervals to track dephasing drift.
    
    Required config entries:
        - delay_minutes: float, delay between measurements in minutes
        - num_steps: int, number of time steps
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
    """

    def init_sweep_vars(self):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RProgram
        self.Program = T2RProgram

        # Set default values
        self.cfg.setdefault('qubit_drive_freq', self.cfg['qubit_freqs'][0] + self.cfg.get("freq_shift", 0))
        self.cfg.setdefault('pi_gain', self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)

        # Outer sweep: time index
        self.y_key = "time_index"
        self.y_points = np.arange(self.cfg["num_steps"])

        # Inner QICK loop: delay time
        self.x_name = "delay_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Time (step = {self.cfg["delay_minutes"]:.2f} min)'
        self.xlabel = 'Delay time (us)'

        # Store delay in seconds
        self.delay_seconds = self.cfg["delay_minutes"] * 60
        
        # Track timestamps
        self.timestamps = []
        self.start_time = time.time()

    def set_up_instance(self):
        """Wait for the specified delay before each iteration."""
        current_step = self.cfg["time_index"]
        self.timestamps.append(time.time() - self.start_time)
        
        if current_step > 0:
            elapsed = time.time() - self.start_time
            target_time = current_step * self.delay_seconds
            wait_time = max(0, target_time - elapsed)
            if wait_time > 0:
                time.sleep(wait_time)

    def analyze(self, data, **kwargs):
        """Add timestamps to saved data."""
        data['data']['timestamps_seconds'] = np.array(self.timestamps)
        return super().analyze(data, **kwargs)
