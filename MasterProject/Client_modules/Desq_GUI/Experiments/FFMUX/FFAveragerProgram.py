"""
================================================================================
FFAveragerProgram.py - Base Class for Fast Flux Experiments
================================================================================

Provides a base class for experiments using fast flux control.
Inherits from qick.asm_v2.AveragerProgramV2 and adds FF pulse methods.

USAGE:
------
    from FFAveragerProgram import FFAveragerProgramV2
    import FF_utils as FF
    
    class MyProgram(FFAveragerProgramV2):
        def _initialize(self, cfg):
            # Declare generators, readouts
            FF.FFDefinitions(self)
            # Set up pulses
            
        def _body(self, cfg):
            self.FFPulses(self.FFPulse, pulse_length)
            # ... experiment ...
            self.FFPulses(self.FFReadouts, readout_length)
            # ... readout ...
            self.FFPulses(-1 * self.FFReadouts, readout_length)
            self.FFPulses(-1 * self.FFPulse, pulse_length)

================================================================================
"""

import numpy as np

# Try to import from qick
try:
    from qick.asm_v2 import AveragerProgramV2
    QICK_AVAILABLE = True
except ImportError:
    QICK_AVAILABLE = False
    # Provide a stub for testing without hardware
    class AveragerProgramV2:
        def __init__(self, soccfg, cfg, reps=1, final_delay=0, initial_delay=0):
            self.soccfg = soccfg
            self.cfg = cfg
            self.reps = reps
            self._gen_ts = [0] * 16
        
        def us2cycles(self, us, gen_ch=None):
            return int(us * 430.08)  # Approximate conversion
        
        def declare_gen(self, **kwargs):
            pass
        
        def declare_readout(self, **kwargs):
            pass
        
        def add_pulse(self, **kwargs):
            pass
        
        def add_gauss(self, **kwargs):
            pass
        
        def set_pulse_registers(self, **kwargs):
            pass
        
        def pulse(self, **kwargs):
            pass
        
        def delay(self, t):
            pass
        
        def delay_auto(self, t=0):
            pass
        
        def sync_all(self, t=0):
            pass
        
        def trigger(self, **kwargs):
            pass
        
        def wait_auto(self):
            pass
        
        def add_loop(self, name, count):
            pass


class FFAveragerProgramV2(AveragerProgramV2):
    """
    Base class for QICK programs with fast flux support.
    
    Extends AveragerProgramV2 with convenient FFPulses methods.
    Subclasses should implement _initialize() and _body().
    """
    
    def __init__(self, soccfg, cfg, reps=1, final_delay=0, initial_delay=0):
        """
        Initialize the FF averager program.
        
        Parameters:
            soccfg: QICK SoC configuration
            cfg: Experiment configuration dictionary
            reps: Number of repetitions per round
            final_delay: Delay after each rep [µs]
            initial_delay: Delay before starting [µs]
        """
        super().__init__(soccfg, cfg=cfg, reps=reps, 
                        final_delay=final_delay, initial_delay=initial_delay)
        
        # These will be populated by FF.FFDefinitions()
        self.FFQubits = []
        self.FFChannels = []
        self.FFReadouts = np.array([])
        self.FFPulse = np.array([])
        self.gen_t0 = []
    
    def FFPulses(self, list_of_gains, length_us, t_start='auto', **kwargs):
        """
        Play constant-amplitude fast flux pulses on all FF channels.
        
        This is the primary method for applying flux biases during experiments.
        The gains should be "undone" at the end of the body by calling with
        negative gains.
        
        Parameters:
            list_of_gains: Array of gains for each FF channel [DAC units]
                          Use self.FFPulse for qubit drive, self.FFReadouts for readout
            length_us: Pulse length [µs] or QickSweep1D object
            t_start: Start time ('auto' or specific time in µs)
            **kwargs: Additional arguments passed to set_pulse_registers
        
        Example:
            # During qubit pulse
            self.FFPulses(self.FFPulse, qubit_length + 1)
            
            # During readout
            self.FFPulses(self.FFReadouts, cfg["res_length"])
            
            # Undo at end
            self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
            self.FFPulses(-1 * self.FFPulse, qubit_length + 1)
        """
        for i, gain in enumerate(list_of_gains):
            channel = self.FFChannels[i]
            
            # Handle both fixed length and swept length
            if hasattr(length_us, '__class__') and 'QickSweep' in length_us.__class__.__name__:
                # It's a sweep object - convert to cycles differently
                length_cycles = length_us  # Let QICK handle the conversion
            else:
                length_cycles = self.us2cycles(length_us, gen_ch=channel)
            
            self.set_pulse_registers(
                ch=channel,
                style='const',
                freq=0,
                phase=0,
                gain=int(gain),
                length=length_cycles,
                **kwargs
            )
        
        # Pulse all FF channels
        for channel in self.FFChannels:
            if t_start != 'auto':
                t_start_ = t_start + self.gen_t0[channel]
            else:
                t_start_ = 'auto'
            self.pulse(ch=channel, t=t_start_)
    
    def FFPulses_vary_length(self, list_of_gains, length_sweep, t_start='auto'):
        """
        Play FF pulses with swept length (for T1/T2 type experiments).
        
        Parameters:
            list_of_gains: Array of gains for each FF channel
            length_sweep: QickSweep1D object for the length
            t_start: Start time
        """
        self.FFPulses(list_of_gains, length_sweep, t_start=t_start)


# Alias for backwards compatibility
FFAveragerProgram = FFAveragerProgramV2
