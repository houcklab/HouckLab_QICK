"""
mT1VsFFFFMUX.py - T1 Decay vs Fast Flux Gain 2D Sweep

Sweeps T1 decay measurement while varying the fast flux (FF) pulse gain.
This allows characterizing how T1 varies with flux bias, useful for
identifying two-level system (TLS) defects and optimal operating points.

Output: 2D heatmap of IQ contrast or population vs (delay time, FF gain)
"""

import numpy as np
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class T1FFProgram(FFAveragerProgramV2):
    """
    T1 program for use in 2D sweeps.
    
    Applies a pi pulse, waits a variable delay, then measures.
    The delay is swept using an on-board QICK loop.
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

        # Delay sweep loop
        self.add_loop("delay_loop", self.cfg["expts"])
        self.delay_loop = QickSweep1D("delay_loop", start=0, end=cfg["stop_delay_us"])

        # Pi pulse using Gaussian envelope
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=90, gain=cfg["qubit_gains"][0] / 32766.)
        self.qubit_length_us = cfg["sigma"] * 4

    def _body(self, cfg):
        expt_length = self.qubit_length_us + 1.05 + self.delay_loop
        
        # Apply FF during experiment
        self.FFPulses(self.FFPulse, expt_length)
        
        # Pi pulse to excite qubit
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)
        self.delay(self.qubit_length_us + 1.05)

        # Variable delay (T1 decay time)
        self.delay(self.delay_loop, tag='swept_delay')

        # Readout
        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)

        # Undo FF pulses
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, expt_length)

    def loop_pts(self):
        return (self.get_time_param("swept_delay", "t", as_array=True),)


class T1VsFFFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: T1 decay vs fast flux gain.
    
    Sweeps over FF_Qubits[qubit_FF_index].Gain_Pulse on the outer loop,
    and T1 delay time on the inner QICK loop.
    
    Required config entries:
        - qubit_FF_index: int, index of FF channel to sweep (1-indexed)
        - FF_gain_start: int, starting FF gain value
        - FF_gain_stop: int, ending FF gain value
        - FF_gain_steps: int, number of FF gain steps
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
        self.Program = T1FFProgram

        # Outer sweep: FF gain on specified qubit channel
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(
            self.cfg["FF_gain_start"],
            self.cfg["FF_gain_stop"],
            self.cfg["FF_gain_steps"],
            dtype=int
        )

        # Inner QICK loop: delay time
        self.x_name = "delay_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Fast flux gain (Q{self.cfg["qubit_FF_index"]})'
        self.xlabel = 'Delay time (us)'
