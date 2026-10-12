"""
mSingleShotOptimizeFFMUX.py - Single Shot Readout and Qubit Optimization 2D Sweeps

Collection of 2D sweeps for optimizing single-shot readout fidelity:
- Readout power vs frequency optimization
- Qubit pulse gain vs frequency optimization
- SNR optimization sweeps

Output: 2D heatmaps of fidelity/SNR vs sweep parameters
"""

import numpy as np
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class SingleShotFFProgram(FFAveragerProgramV2):
    """
    Single shot program with optional pi pulse for use in 2D optimization sweeps.
    
    Can run with or without the pi pulse to get |g> and |e> state distributions.
    """
    
    def _initialize(self, cfg):
        # Qubit generator
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])

        # Readout MUX generator and ADC channels
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        # Fast flux definitions
        FF.FFDefinitions(self)

        # Gaussian pulse for pi operation
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=90, gain=cfg["qubit_gains"][0] / 32766.)
        self.qubit_length_us = cfg["sigma"] * 4

        # Number of pi pulses (0 = ground state, 1 = excited state)
        self.num_pulses = cfg.get("number_of_pulses", 1)

    def _body(self, cfg):
        # Apply FF during experiment
        if self.num_pulses > 0:
            self.FFPulses(self.FFPulse, self.qubit_length_us * self.num_pulses + 1)
            
            # Apply pi pulses
            for _ in range(self.num_pulses):
                self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)
                self.delay(self.qubit_length_us)
            
            self.delay_auto()

        # Readout
        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)

        # Undo FF pulses
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        if self.num_pulses > 0:
            self.FFPulses(-1 * self.FFPulse, self.qubit_length_us * self.num_pulses + 1)

    def loop_pts(self):
        return tuple()


class ReadoutOptimizeFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Readout gain vs readout frequency for optimizing single-shot fidelity.
    
    Sweeps readout power and frequency to find optimal discrimination parameters.
    
    Required config entries:
        - gain_start: int, starting readout gain
        - gain_stop: int, ending readout gain
        - gain_pts: int, number of gain points
        - span: float, frequency span in MHz
        - trans_pts: int, number of frequency points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - Shots: int, number of single shots per point
        - number_of_pulses: int, number of pi pulses (0=ground, 1=excited)
        - relax_delay: float, delay between shots in us
    
    The experiment measures single-shot distributions and computes fidelity
    at each (gain, frequency) point.
    """

    def init_sweep_vars(self):
        self.Program = SingleShotFFProgram

        # Outer sweep: readout gain
        self.y_key = ("res_gains", "0")  # First readout channel gain
        self.y_points = np.linspace(
            self.cfg["gain_start"],
            self.cfg["gain_stop"],
            self.cfg["gain_pts"],
            dtype=int
        )

        # X sweep: readout frequency
        self.x_key = ("res_freqs", "0")  # First readout channel frequency
        center_freq = self.cfg["res_freqs"][0]
        self.x_points = np.linspace(
            center_freq - self.cfg["span"],
            center_freq + self.cfg["span"],
            self.cfg["trans_pts"]
        )

        # Configure for single-shot acquisition
        self.cfg["reps"] = self.cfg["Shots"]
        
        # Z-axis: will compute fidelity
        self.z_value = "population_shots"
        
        # Axis labels
        self.ylabel = 'Readout gain'
        self.xlabel = 'Readout frequency (MHz)'


class QubitOptimizeFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Qubit gain vs qubit frequency for optimizing single-shot fidelity.
    
    Sweeps qubit drive parameters to find optimal pi pulse for discrimination.
    
    Required config entries:
        - q_gain_span: int, qubit gain span around nominal value
        - q_gain_pts: int, number of gain points
        - q_freq_span: float, frequency span in MHz
        - q_freq_pts: int, number of frequency points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - Shots: int, number of single shots per point
        - number_of_pulses: int, number of pi pulses
        - relax_delay: float, delay between shots in us
    
    Optional:
        - qubit_sweep_index: int, which qubit pulse to optimize (-1 for last)
    """

    def init_sweep_vars(self):
        self.Program = SingleShotFFProgram

        # Determine which qubit to optimize
        qubit_index = self.cfg.get("qubit_sweep_index", -1)
        if qubit_index == -1:
            qubit_index = len(self.cfg["qubit_freqs"]) - 1
        self.qubit_index = qubit_index

        # Outer sweep: qubit drive gain
        center_gain = self.cfg["qubit_gains"][qubit_index]
        self.y_key = ("qubit_gains", str(qubit_index))
        self.y_points = np.linspace(
            center_gain - self.cfg["q_gain_span"] / 2,
            center_gain + self.cfg["q_gain_span"] / 2,
            self.cfg["q_gain_pts"],
            dtype=int
        )

        # X sweep: qubit frequency
        center_freq = self.cfg["qubit_freqs"][qubit_index]
        self.x_key = ("qubit_freqs", str(qubit_index))
        self.x_points = np.linspace(
            center_freq - self.cfg["q_freq_span"] / 2,
            center_freq + self.cfg["q_freq_span"] / 2,
            self.cfg["q_freq_pts"]
        )

        # Configure for single-shot acquisition
        self.cfg["reps"] = self.cfg["Shots"]
        
        # Z-axis: will compute fidelity
        self.z_value = "population_shots"
        
        # Axis labels
        self.ylabel = f'Qubit gain (Q{qubit_index + 1})'
        self.xlabel = f'Qubit frequency (Q{qubit_index + 1}) (MHz)'


class SNROptimizeFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Readout gain vs frequency for SNR optimization.
    
    Similar to ReadoutOptimize but computes SNR directly from I/Q distributions.
    
    Required config entries:
        - gain_start: float, starting gain (can be in dB or linear)
        - gain_stop: float, ending gain
        - gain_pts: int, number of gain points
        - freq_start: float, starting frequency in MHz
        - freq_stop: float, ending frequency in MHz
        - freq_pts: int, number of frequency points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - Shots: int, number of single shots per point
        - number_of_pulses: int, number of pi pulses
        - relax_delay: float, delay between shots in us
    """

    def init_sweep_vars(self):
        self.Program = SingleShotFFProgram

        # Outer sweep: readout gain
        self.y_key = ("res_gains", "0")
        self.y_points = np.linspace(
            self.cfg["gain_start"],
            self.cfg["gain_stop"],
            self.cfg["gain_pts"],
            dtype=int
        )

        # X sweep: readout frequency
        self.x_key = ("res_freqs", "0")
        self.x_points = np.linspace(
            self.cfg["freq_start"],
            self.cfg["freq_stop"],
            self.cfg["freq_pts"]
        )

        # Configure for single-shot acquisition
        self.cfg["reps"] = self.cfg["Shots"]
        
        # Z-axis: will compute SNR
        self.z_value = "population_shots"
        
        # Axis labels
        self.ylabel = 'Readout gain'
        self.xlabel = 'Readout frequency (MHz)'


class SingleShotVsFFFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Single shot fidelity vs fast flux gain.
    
    Measures single-shot fidelity while varying FF bias to find optimal
    operating point for readout.
    
    Required config entries:
        - qubit_FF_index: int, index of FF channel to sweep (1-indexed)
        - FF_gain_start: int, starting FF gain value
        - FF_gain_stop: int, ending FF gain value
        - FF_gain_steps: int, number of FF gain steps
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - Shots: int, number of single shots per point
        - number_of_pulses: int, number of pi pulses
        - relax_delay: float, delay between shots in us
    """

    def init_sweep_vars(self):
        self.Program = SingleShotFFProgram

        # Outer sweep: FF gain
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(
            self.cfg["FF_gain_start"],
            self.cfg["FF_gain_stop"],
            self.cfg["FF_gain_steps"],
            dtype=int
        )

        # X sweep: effectively just a single point (use dummy)
        # Or we could sweep number of pi pulses
        self.x_key = "number_of_pulses"
        self.x_points = np.array([0, 1])  # Ground and excited state

        # Configure for single-shot acquisition
        self.cfg["reps"] = self.cfg["Shots"]
        
        # Z-axis
        self.z_value = "population_shots"
        
        # Axis labels
        self.ylabel = f'Fast flux gain (Q{self.cfg["qubit_FF_index"]})'
        self.xlabel = 'Number of pi pulses'
