"""
mT2EVsFFFFMUX.py - T2 Echo vs Fast Flux Gain 2D Sweep

Sweeps T2 Echo (Hahn echo) measurement while varying the fast flux (FF) pulse gain.
This allows characterizing how the coherence time varies with flux bias,
useful for identifying flux-insensitive sweet spots.

Output: 2D heatmap of IQ contrast or population vs (delay time, FF gain)
"""

import numpy as np
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class T2EchoFFProgram(FFAveragerProgramV2):
    """
    T2 Echo (Hahn echo) program for use in 2D sweeps.
    
    Applies pi/2 - delay/2 - pi - delay/2 - pi/2 sequence.
    The total delay is swept using an on-board QICK loop.
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

        # Delay sweep loop (half of total echo time)
        self.add_loop("delay_loop", self.cfg["expts"])
        self.half_delay_loop = QickSweep1D("delay_loop", start=0, end=cfg["stop_delay_us"] / 2)

        # Gaussian pulses
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        
        # pi/2 pulse
        self.add_pulse(ch=cfg["qubit_ch"], name='pi2_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=0, gain=cfg["pi2_gain"] / 32766.)
        
        # pi pulse (refocusing)
        self.add_pulse(ch=cfg["qubit_ch"], name='pi_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=0, gain=cfg["pi_gain"] / 32766.)
        
        self.qubit_length_us = cfg["sigma"] * 4

    def _body(self, cfg):
        # Total experiment length: 3 pulses + 2 half-delays + buffer
        expt_length = 3 * self.qubit_length_us + 2 * self.half_delay_loop + 12
        
        # Apply FF during experiment
        self.FFPulses(self.FFPulse, expt_length)
        self.delay(10.0)
        
        # First pi/2 pulse
        self.pulse(ch=cfg["qubit_ch"], name="pi2_drive", t=0)
        self.delay(self.qubit_length_us)
        
        # First half delay
        self.delay(self.half_delay_loop, tag='swept_delay_1')
        
        # Refocusing pi pulse
        self.pulse(ch=cfg["qubit_ch"], name="pi_drive", t=0)
        self.delay(self.qubit_length_us)
        
        # Second half delay
        self.delay(self.half_delay_loop, tag='swept_delay_2')
        
        # Final pi/2 pulse
        self.pulse(ch=cfg["qubit_ch"], name="pi2_drive", t=0)
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
        # Return total delay (2 * half delay)
        return (2 * self.get_time_param("swept_delay_1", "t", as_array=True),)


class T2EVsFFFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: T2 Echo vs fast flux gain.
    
    Sweeps over FF_Qubits[qubit_FF_index].Gain_Pulse on the outer loop,
    and T2E total delay time on the inner QICK loop.
    
    Required config entries:
        - qubit_FF_index: int, index of FF channel to sweep (1-indexed)
        - FF_gain_start: int, starting FF gain value
        - FF_gain_stop: int, ending FF gain value
        - FF_gain_steps: int, number of FF gain steps
        - stop_delay_us: float, maximum total T2E delay in us
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
        self.Program = T2EchoFFProgram

        # Set default values
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

        # Inner QICK loop: total delay time
        self.x_name = "delay_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Fast flux gain (Q{self.cfg["qubit_FF_index"]})'
        self.xlabel = 'Total echo time (us)'


class T2EVsQbloxFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: T2 Echo vs Qblox DC voltage.
    
    Sweeps over Qblox DAC voltage on the outer loop (with settling time),
    and T2E total delay time on the inner QICK loop.
    
    Required config entries:
        - Qblox_start: float, starting Qblox voltage
        - Qblox_stop: float, ending Qblox voltage
        - Qblox_steps: int, number of voltage steps
        - DAC: int, Qblox DAC channel number
        - stop_delay_us: float, maximum T2E delay in us
        - expts: int, number of delay points
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'population'
        - Qblox_settle_time: float, settling time in seconds (default 1.0)
    """

    def init_sweep_vars(self):
        import time
        from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Qblox_Functions import Qblox
        
        self.Program = T2EchoFFProgram

        # Set default values
        self.cfg.setdefault('pi_gain', self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)

        # Outer sweep: Qblox voltage
        self.y_key = "Qblox_voltage"
        self.y_points = np.linspace(
            self.cfg["Qblox_start"],
            self.cfg["Qblox_stop"],
            self.cfg["Qblox_steps"]
        )

        # Inner QICK loop: total delay time
        self.x_name = "delay_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Qblox voltage (DAC {self.cfg["DAC"]})'
        self.xlabel = 'Total echo time (us)'

        # Initialize Qblox interface
        self.QbloxClass = Qblox()
        self.settle_time = self.cfg.get("Qblox_settle_time", 1.0)
        self._time_module = time

    def set_up_instance(self):
        """Set Qblox voltage before each sweep iteration."""
        voltage = self.cfg["Qblox_voltage"]
        self.QbloxClass.set_voltage([self.cfg['DAC']], [voltage])
        self._time_module.sleep(self.settle_time)
