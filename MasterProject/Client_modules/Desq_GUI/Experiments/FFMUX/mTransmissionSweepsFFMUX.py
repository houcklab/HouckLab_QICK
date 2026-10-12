"""
mTransmissionSweepsFFMUX.py - Transmission vs Voltage/FF 2D Sweep Experiments

Collection of 2D sweeps for characterizing resonator transmission:
- Transmission vs Qblox DC voltage (for finding resonator flux dependence)
- Transmission vs FF gain (for fast flux characterization)
- Transmission vs power (for power-dependent shifts)

Output: 2D heatmaps of IQ signal vs (frequency, voltage/FF/power)
"""

import time
import numpy as np
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class TransmissionFFProgram(FFAveragerProgramV2):
    """
    Transmission (cavity spectroscopy) program for use in 2D sweeps.
    
    Applies a tone at variable frequency and measures transmitted signal.
    The frequency is swept using an on-board QICK loop.
    """
    
    def _initialize(self, cfg):
        # Readout MUX generator and ADC channels
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])

        # Fast flux definitions
        FF.FFDefinitions(self)

        # Frequency sweep loop
        self.add_loop("trans_freq_loop", self.cfg["TransNumPoints"])
        trans_freq_sweep = QickSweep1D("trans_freq_loop",
                                       start=cfg["res_freqs"][0] - cfg["TransSpan"],
                                       end=cfg["res_freqs"][0] + cfg["TransSpan"])

        # Readout pulse with swept frequency
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["readout_length"], freq=trans_freq_sweep)

    def _body(self, cfg):
        # Apply FF during measurement
        self.FFPulses(self.FFReadouts, cfg["readout_length"])
        
        # Trigger readout and send pulse
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(cfg.get("cav_relax_delay", 10))

        # Undo FF pulses
        self.FFPulses(-1 * self.FFReadouts, cfg["readout_length"])

    def loop_pts(self):
        return (self.get_pulse_param("res_drive", "freq", as_array=True),)


class TransmissionVsQbloxFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Cavity transmission vs Qblox DC voltage.
    
    Sweeps over Qblox DAC voltage on the outer loop (with settling time),
    and resonator frequency on the inner QICK loop.
    
    Useful for finding flux-dependent resonator shifts and identifying
    the coupling between resonator and qubit vs flux.
    
    Required config entries:
        - Qblox_start: float, starting Qblox voltage
        - Qblox_stop: float, ending Qblox voltage
        - Qblox_steps: int, number of voltage steps
        - DAC: int, Qblox DAC channel number
        - TransSpan: float, frequency span around res_freqs[0] in MHz
        - TransNumPoints: int, number of frequency points
        - readout_length: float, readout pulse length in us
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'IQ'
        - Qblox_settle_time: float, settling time in seconds (default 1.0)
    """

    def init_sweep_vars(self):
        from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Qblox_Functions import Qblox
        
        self.Program = TransmissionFFProgram

        # Outer sweep: Qblox voltage
        self.y_key = "Qblox_voltage"
        self.y_points = np.linspace(
            self.cfg["Qblox_start"],
            self.cfg["Qblox_stop"],
            self.cfg["Qblox_steps"]
        )

        # Inner QICK loop: resonator frequency
        self.x_name = "trans_freq_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'Qblox voltage (DAC {self.cfg["DAC"]})'
        self.xlabel = 'Resonator frequency (MHz)'

        # Initialize Qblox interface
        self.QbloxClass = Qblox()
        self.settle_time = self.cfg.get("Qblox_settle_time", 1.0)

        print(f"TransVsQblox: Sweeping voltage from {self.y_points[0]:.4f} to {self.y_points[-1]:.4f} V")

    def set_up_instance(self):
        """Set Qblox voltage before each sweep iteration."""
        voltage = self.cfg["Qblox_voltage"]
        self.QbloxClass.set_voltage([self.cfg['DAC']], [voltage])
        time.sleep(self.settle_time)


class TransmissionVsFFFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Cavity transmission vs fast flux gain.
    
    Sweeps over FF_Qubits[qubit_FF_index].Gain_Readout on the outer loop,
    and resonator frequency on the inner QICK loop.
    
    Required config entries:
        - qubit_FF_index: int, index of FF channel to sweep (1-indexed)
        - FF_gain_start: int, starting FF gain value
        - FF_gain_stop: int, ending FF gain value
        - FF_gain_steps: int, number of FF gain steps
        - TransSpan: float, frequency span around res_freqs[0] in MHz
        - TransNumPoints: int, number of frequency points
        - readout_length: float, readout pulse length in us
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'IQ'
    """

    def init_sweep_vars(self):
        self.Program = TransmissionFFProgram

        # Outer sweep: FF gain on specified channel (readout FF)
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Readout")
        self.y_points = np.linspace(
            self.cfg["FF_gain_start"],
            self.cfg["FF_gain_stop"],
            self.cfg["FF_gain_steps"],
            dtype=int
        )

        # Inner QICK loop: resonator frequency
        self.x_name = "trans_freq_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = f'FF readout gain (Q{self.cfg["qubit_FF_index"]})'
        self.xlabel = 'Resonator frequency (MHz)'


class TransmissionVsPowerFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Cavity transmission vs readout power.
    
    Sweeps over readout gain on the outer loop,
    and resonator frequency on the inner QICK loop.
    
    Useful for characterizing power-dependent effects like
    photon-number dependent shifts and non-linearities.
    
    Required config entries:
        - power_start: int, starting readout gain
        - power_stop: int, ending readout gain
        - power_steps: int, number of power steps
        - TransSpan: float, frequency span around res_freqs[0] in MHz
        - TransNumPoints: int, number of frequency points
        - readout_length: float, readout pulse length in us
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    
    Optional config entries:
        - z_value: 'contrast' (default) or 'IQ'
    """

    def init_sweep_vars(self):
        self.Program = TransmissionFFProgram

        # Outer sweep: readout gain (power)
        self.y_key = ("res_gains", "0")  # First readout channel
        self.y_points = np.linspace(
            self.cfg["power_start"],
            self.cfg["power_stop"],
            self.cfg["power_steps"],
            dtype=int
        )

        # Inner QICK loop: resonator frequency
        self.x_name = "trans_freq_loop"

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = 'Readout gain (power)'
        self.xlabel = 'Resonator frequency (MHz)'


class TransmissionVsQubitStateFFMUX(SweepExperiment2D_plots):
    """
    2D sweep: Cavity transmission with qubit in different states.
    
    Compares resonator response with qubit in |g> vs |e> state,
    useful for measuring dispersive shift chi.
    
    Sweeps number of pi pulses (0 or 1) on outer loop,
    and resonator frequency on inner QICK loop.
    
    Required config entries:
        - TransSpan: float, frequency span around res_freqs[0] in MHz
        - TransNumPoints: int, number of frequency points
        - readout_length: float, readout pulse length in us
        - sigma: float, Gaussian pulse sigma in us
        - qubit_freqs: list, qubit frequencies in MHz
        - qubit_gains: list, qubit pulse gains
        - reps: int, number of repetitions
        - relax_delay: float, delay between shots in us
    """

    def init_sweep_vars(self):
        # Use the SingleShot program which has optional pi pulse
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Sweeps.mSingleShotOptimizeFFMUX import SingleShotFFProgram
        
        self.Program = SingleShotFFProgram

        # Outer sweep: number of pi pulses (0 = ground, 1 = excited)
        self.y_key = "number_of_pulses"
        self.y_points = np.array([0, 1])

        # Inner QICK loop: resonator frequency
        # We need a program that sweeps frequency, so this won't directly work
        # Instead, we'll do a custom implementation
        
        self.x_name = "trans_freq_loop"  # Placeholder

        # Z-axis value type
        self.z_value = self.cfg.get("z_value", "contrast")
        
        # Axis labels for plotting
        self.ylabel = 'Qubit state (0=|g>, 1=|e>)'
        self.xlabel = 'Resonator frequency (MHz)'
