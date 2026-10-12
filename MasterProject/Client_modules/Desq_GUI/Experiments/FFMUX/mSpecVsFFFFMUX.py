"""
mSpecVsFFFFMUX.py - Qubit Spectroscopy vs Fast Flux Gain 2D Sweep

Sweeps qubit spectroscopy frequency while varying the fast flux (FF) pulse gain.
This allows mapping out the qubit frequency as a function of flux bias,
essential for characterizing the flux-tunability of transmon qubits.

Output: 2D heatmap of IQ contrast or population vs (spec frequency, FF gain)
"""

import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class SpecVsFFFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Qubit spectroscopy vs fast flux gain.
    
    Sweeps over FF_Qubits[qubit_FF_index].Gain_Pulse on the outer loop,
    and qubit drive frequency on the inner QICK loop.
    
    Required config entries:
        - qubit_FF_index: int, index of FF channel to sweep (1-indexed)
        - FF_gain_start: int, starting FF gain value
        - FF_gain_stop: int, ending FF gain value
        - FF_gain_steps: int, number of FF gain steps
        - SpecSpan: float, frequency span around qubit_freqs[0] in MHz
        - SpecNumPoints: int, number of frequency points
        - Gauss: bool, whether to use Gaussian pulse (else CW)
        - qubit_gain: int, CW drive gain (if not Gauss)
        - Gauss_gain: int, Gaussian drive gain (if Gauss)
        - sigma: float, Gaussian sigma in us (if Gauss)
        - qubit_length: float, CW drive length in us (if not Gauss)
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
    """

    def init_sweep_vars(self):
        self.Program = QubitSpecSliceFFProg

        # Outer sweep: FF gain on specified qubit channel
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(
            self.cfg["FF_gain_start"],
            self.cfg["FF_gain_stop"],
            self.cfg["FF_gain_steps"],
            dtype=int
        )

        # Inner QICK loop: qubit frequency
        self.x_name = "qubit_freq_loop"
        
        # Set CW drive length if not specified
        self.cfg["qubit_length"] = self.cfg.get("qubit_length") or 100

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Fast flux gain (Q{self.cfg["qubit_FF_index"]})'
        self.xlabel = 'Spec frequency (MHz)'
