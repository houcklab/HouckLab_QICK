"""
mRabiVsFFFFMUX.py - Amplitude Rabi vs Fast Flux Gain 2D Sweep

Sweeps amplitude Rabi measurement while varying the fast flux (FF) pulse gain.
This allows characterizing how the qubit response changes with flux bias,
useful for calibrating pi pulse gains at different operating points.

Output: 2D heatmap of IQ contrast or population vs (qubit gain, FF gain)
"""

import numpy as np
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class RabiFFProgram(FFAveragerProgramV2):
    """
    Amplitude Rabi program for use in 2D sweeps.
    
    Applies a variable-amplitude Gaussian pulse and measures population.
    The pulse amplitude is swept using an on-board QICK loop.
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

        # Qubit gain sweep loop
        self.add_loop("qubit_gain_loop", self.cfg["expts"])
        qubit_gain_sweep = QickSweep1D("qubit_gain_loop",
                                       start=0,
                                       end=cfg["max_gain"] / 32766.)

        # Gaussian pulse with swept amplitude
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=90, gain=qubit_gain_sweep)
        self.qubit_length_us = cfg["sigma"] * 4

        self.delay_auto(0.05)

    def _body(self, cfg):
        # Apply FF during experiment
        self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 1)
        
        # Variable amplitude qubit pulse
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)
        self.delay_auto()

        # Readout
        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)

        # Undo FF pulses
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.cfg["sigma"] * 4 + 1)

    def loop_pts(self):
        return (self.get_pulse_param("qubit_drive", "gain", as_array=True) * 32766,)


class RabiVsFFFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Amplitude Rabi vs fast flux gain.
    
    Sweeps over FF_Qubits[qubit_FF_index].Gain_Pulse on the outer loop,
    and qubit drive amplitude on the inner QICK loop.
    
    Required config entries:
        - qubit_FF_index: int, index of FF channel to sweep (1-indexed)
        - FF_gain_start: int, starting FF gain value
        - FF_gain_stop: int, ending FF gain value
        - FF_gain_steps: int, number of FF gain steps
        - max_gain: int, maximum qubit drive gain
        - expts: int, number of gain points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
    """

    def init_sweep_vars(self):
        self.Program = RabiFFProgram

        # Set default values
        cfg_defaults = {
            'start': 0,
            "expts": self.cfg.get("expts", 31),
            "reps": self.cfg.get("reps", 30),
            "rounds": self.cfg.get("rounds", 30),
            "f_ge": self.cfg["qubit_freqs"][0]
        }
        self.cfg = cfg_defaults | self.cfg
        self.cfg['step'] = int(self.cfg["max_gain"] / self.cfg['expts'])

        # Outer sweep: FF gain on specified qubit channel
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(
            self.cfg["FF_gain_start"],
            self.cfg["FF_gain_stop"],
            self.cfg["FF_gain_steps"],
            dtype=int
        )

        # Inner QICK loop: qubit drive gain
        self.x_name = "qubit_gain_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Fast flux gain (Q{self.cfg["qubit_FF_index"]})'
        self.xlabel = 'Qubit drive gain'
