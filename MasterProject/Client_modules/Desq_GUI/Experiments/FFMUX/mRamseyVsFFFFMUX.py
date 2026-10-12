"""
mRamseyVsFFFFMUX.py - Ramsey (T2*) vs Fast Flux Gain 2D Sweep

Sweeps Ramsey (T2R) measurement while varying the fast flux (FF) pulse gain.
This allows characterizing how dephasing varies with flux bias and can
reveal flux noise sensitivity at different operating points.

Output: 2D heatmap of IQ contrast or population vs (delay time, FF gain)
"""

import numpy as np
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class RamseyFFProgram(FFAveragerProgramV2):
    """
    Ramsey (T2R) program for use in 2D sweeps.
    
    Applies pi/2 - delay - pi/2 sequence with optional phase accumulation.
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
        
        # Check for minimum step size
        if cfg["stop_delay_us"] / cfg["expts"] < 0.00465:
            print(f"RamseyFFProgram: WARNING: step size ({cfg['stop_delay_us']}/{cfg['expts']}) "
                  f"is less than one cycle (4.65 ns)!")

        # Phase accumulation for artificial detuning
        if "phase_shift_cycles" in cfg and cfg["phase_shift_cycles"] != 0:
            self.phase_loop = QickSweep1D("delay_loop", start=0, end=360 * cfg["phase_shift_cycles"])
        else:
            self.phase_loop = 180  # Static phase for second pi/2

        # Gaussian pulses for pi/2 operations
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        
        # First pi/2 pulse (phase=0)
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive_1', style="arb", envelope="qubit",
                       freq=cfg["qubit_drive_freq"],
                       phase=0, gain=cfg["pi2_gain"] / 32766.)
        
        # Second pi/2 pulse (variable phase)
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive_2', style="arb", envelope="qubit",
                       freq=cfg["qubit_drive_freq"],
                       phase=self.phase_loop, gain=cfg["pi2_gain"] / 32766.)
        
        self.qubit_length_us = cfg["sigma"] * 4

    def _body(self, cfg):
        expt_length = self.qubit_length_us + 10.05 + self.delay_loop + self.qubit_length_us + 1
        
        # Apply FF during experiment
        self.FFPulses(self.FFPulse, expt_length)
        self.delay(10.0)
        
        # First pi/2 pulse
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_1", t=0)
        self.delay(self.qubit_length_us)
        
        # Variable delay with second pi/2 pulse
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_2", t=self.delay_loop, tag='swept_delay')
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
        self.FFPulses(-1 * self.FFPulse, expt_length)

    def loop_pts(self):
        return (self.get_time_param("swept_delay", "t", as_array=True),)


class RamseyVsFFFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Ramsey (T2*) vs fast flux gain.
    
    Sweeps over FF_Qubits[qubit_FF_index].Gain_Pulse on the outer loop,
    and Ramsey delay time on the inner QICK loop.
    
    Required config entries:
        - qubit_FF_index: int, index of FF channel to sweep (1-indexed)
        - FF_gain_start: int, starting FF gain value
        - FF_gain_stop: int, ending FF gain value
        - FF_gain_steps: int, number of FF gain steps
        - stop_delay_us: float, maximum Ramsey delay in us
        - expts: int, number of delay points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - freq_shift: float, frequency detuning in MHz (default 0)
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
        - phase_shift_cycles: int, number of 2pi phase shifts across sweep
        - populations: bool, if True use population measurement
    """

    def init_sweep_vars(self):
        self.Program = RamseyFFProgram

        # Set default values
        self.cfg.setdefault('qubit_drive_freq', self.cfg['qubit_freqs'][0] + self.cfg.get("freq_shift", 0))
        self.cfg.setdefault('pi_gain', self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)

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
        if self.cfg.get("populations", False):
            self.z_value = "population"
        else:
            self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Fast flux gain (Q{self.cfg["qubit_FF_index"]})'
        self.xlabel = 'Delay time (us)'
