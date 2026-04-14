"""
================================================================================
FF_utils.py - Fast Flux Utility Functions
================================================================================

Utility functions for controlling fast flux lines in QICK experiments.
These functions handle the setup and pulsing of flux bias channels.

USAGE:
------
    import FF_utils as FF
    
    # In your program's initialize():
    FF.FFDefinitions(self)
    
    # In your program's body():
    FF.FFPulses(self, self.FFPulse, pulse_length_us)
    # ... do experiment ...
    FF.FFPulses(self, self.FFReadouts, readout_length_us)
    # ... readout ...
    # Undo pulses
    FF.FFPulses(self, -1 * self.FFReadouts, readout_length_us)
    FF.FFPulses(self, -1 * self.FFPulse, pulse_length_us)

CONFIG STRUCTURE:
-----------------
    cfg["FF_Qubits"] = {
        '1': {
            'channel': 0,
            'delay_time': 0.0,
            'Gain_Readout': 1000,
            'Gain_Expt': 0,
            'Gain_Pulse': 500,
        },
        '2': {...},
        ...
    }

================================================================================
"""

import numpy as np


def FFDefinitions(instance):
    """
    Initialize fast flux channels and gain arrays from config.
    
    This function should be called in the program's initialize() method
    after declaring the qubit and resonator generators.
    
    Sets up:
        instance.FFQubits   - List of qubit IDs (sorted)
        instance.FFChannels - List of DAC channels for FF
        instance.FFReadouts - Array of gains during readout
        instance.FFExpts    - Array of gains during experiment (if defined)
        instance.FFPulse    - Array of gains during qubit pulses (if defined)
        instance.FFRamp     - Array of gains for initialization (if defined)
        instance.FFBS       - Array of gains for beamsplitter ops (if defined)
        instance.gen_t0     - Array of timing offsets for each generator
    
    Parameters:
        instance: Program instance (e.g., FFAveragerProgramV2)
    """
    cfg = instance.cfg
    
    # Get sorted list of qubit IDs and their channels
    instance.FFQubits = sorted(cfg["FF_Qubits"].keys())
    instance.FFChannels = [cfg["FF_Qubits"][q]['channel'] for q in instance.FFQubits]
    
    # Declare FF generators
    for channel in instance.FFChannels:
        instance.declare_gen(ch=int(channel))
    
    # Extract gain arrays for different experiment phases
    instance.FFReadouts = np.array([
        cfg["FF_Qubits"][q]["Gain_Readout"] for q in instance.FFQubits
    ])
    
    # Optional gain arrays (check if first qubit has them defined)
    first_qubit = instance.FFQubits[0]
    
    if "Gain_Expt" in cfg["FF_Qubits"][first_qubit]:
        instance.FFExpts = np.array([
            cfg["FF_Qubits"][q]["Gain_Expt"] for q in instance.FFQubits
        ])
    
    if "Gain_Init" in cfg["FF_Qubits"][first_qubit]:
        instance.FFRamp = np.array([
            cfg["FF_Qubits"][q]["Gain_Init"] for q in instance.FFQubits
        ])
    
    if "Gain_Pulse" in cfg["FF_Qubits"][first_qubit]:
        instance.FFPulse = np.array([
            cfg["FF_Qubits"][q]["Gain_Pulse"] for q in instance.FFQubits
        ])
    
    if "Gain_BS" in cfg["FF_Qubits"][first_qubit]:
        instance.FFBS = np.array([
            cfg["FF_Qubits"][q]["Gain_BS"] for q in instance.FFQubits
        ])
    
    # Get delay times for each FF channel
    FFDelays = np.array([
        cfg["FF_Qubits"][q]["delay_time"] for q in instance.FFQubits
    ])
    
    # Handle additional delays (for non-FF channels that need timing adjustment)
    if 'Additional_Delays' not in cfg:
        cfg['Additional_Delays'] = {}
    
    additional_delay_keys = cfg['Additional_Delays'].keys()
    Additional_delay_channels = [
        cfg['Additional_Delays'][k]['channel'] for k in additional_delay_keys
    ]
    Additional_delay_times = [
        instance.us2cycles(cfg['Additional_Delays'][k]['delay_time']) 
        for k in additional_delay_keys
    ]
    
    # Set up generator timing offsets
    # This ensures all pulses are properly synchronized
    num_gens = len(instance._gen_ts) if hasattr(instance, '_gen_ts') else 16
    instance.gen_t0 = np.array([0] * num_gens)
    instance.gen_t0[instance.FFChannels] = [instance.us2cycles(d) for d in FFDelays]
    
    for ch, delay in zip(Additional_delay_channels, Additional_delay_times):
        instance.gen_t0[ch] = delay
    
    instance.gen_t0 = list(instance.gen_t0)


def FFPulses(instance, list_of_gains, length_us, t_start='auto', **kwargs):
    """
    Play constant-amplitude fast flux pulses on all FF channels.
    
    Parameters:
        instance: Program instance
        list_of_gains: Array of gains for each FF channel [DAC units]
        length_us: Pulse length [µs]
        t_start: Start time ('auto' or specific time)
        **kwargs: Additional arguments passed to set_pulse_registers
    """
    for i, gain in enumerate(list_of_gains):
        channel = instance.FFChannels[i]
        length_cycles = instance.us2cycles(length_us, gen_ch=channel)
        
        instance.set_pulse_registers(
            ch=channel,
            style='const',
            freq=0,
            phase=0,
            gain=int(gain),
            length=length_cycles,
            **kwargs
        )
    
    # Pulse all FF channels
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.gen_t0[channel]
        else:
            t_start_ = 'auto'
        instance.pulse(ch=channel, t=t_start_)


def FFPulses_direct(instance, list_of_gains, length_dt, previous_gains, 
                    t_start='auto', IQPulseArray=None, waveform_label="FF"):
    """
    Play arbitrary waveform fast flux pulses (high resolution).
    
    This function allows arbitrary waveforms sampled at 1/16 clock cycle resolution.
    Useful for shaped flux pulses or flux ramps.
    
    Parameters:
        instance: Program instance
        list_of_gains: Default gains for each FF channel (if no IQPulse provided)
        length_dt: Length in units of 1/16 clock cycle
        previous_gains: Gains to use for padding (for timing alignment)
        t_start: Start time ('auto' or specific time)
        IQPulseArray: List of arbitrary waveforms (one per channel), or None
        waveform_label: Label for the waveform in QICK
    """
    IQPulseArray = [None] * len(instance.FFChannels) if IQPulseArray is None else IQPulseArray
    
    for i, (gain, IQPulse) in enumerate(zip(list_of_gains, IQPulseArray)):
        channel = instance.FFChannels[i]
        gencfg = instance.soccfg['gens'][channel]
        
        if IQPulse is None:
            IQPulse = np.ones(length_dt) * gain
        else:
            # Validate range
            if np.max(IQPulse) > gencfg['maxv'] or np.min(IQPulse) < -gencfg['maxv']:
                raise ValueError(
                    f"IQPulseArray[{i}] out of range: [{-gencfg['maxv']}, {gencfg['maxv']}]"
                )
        
        # Truncate to desired length
        IQPulse = IQPulse[:length_dt]
        
        # Pad beginning for clock cycle alignment (must be multiple of 16)
        if len(IQPulse) % 16 != 0:
            extralen = 16 - (len(IQPulse) % 16)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        
        # Minimum length is 3 clock cycles (48 samples)
        if len(IQPulse) // 16 < 3:
            extralen = 48 - len(IQPulse)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        
        # Add the pulse
        instance.add_pulse(
            ch=channel,
            name=waveform_label,
            idata=IQPulse,
            qdata=np.zeros_like(IQPulse)
        )
        instance.set_pulse_registers(
            ch=channel,
            freq=0,
            style='arb',
            phase=0,
            gain=gencfg['maxv'],
            waveform=waveform_label,
            outsel="input"
        )
    
    # Pulse all channels
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.gen_t0[channel]
        else:
            t_start_ = 'auto'
        instance.pulse(ch=channel, t=t_start_)


def FFPulses_directSET_REGS(instance, list_of_gains, length_dt, previous_gains,
                            IQPulseArray=None, waveform_label="FF", invert=False):
    """
    Set up arbitrary waveform registers without pulsing.
    
    Use this with FFPulses_directPULSE() to separate setup from execution.
    
    Parameters:
        instance: Program instance
        list_of_gains: Default gains for each FF channel
        length_dt: Length in units of 1/16 clock cycle
        previous_gains: Gains for padding
        IQPulseArray: List of arbitrary waveforms, or None
        waveform_label: Label for the waveform
        invert: If True, invert the gain sign
    """
    IQPulseArray = [None] * len(instance.FFChannels) if IQPulseArray is None else IQPulseArray
    
    for i, (gain, IQPulse) in enumerate(zip(list_of_gains, IQPulseArray)):
        channel = instance.FFChannels[i]
        gencfg = instance.soccfg['gens'][channel]
        
        if IQPulse is None:
            IQPulse = np.ones(length_dt) * gain
        else:
            if np.max(IQPulse) > gencfg['maxv'] or np.min(IQPulse) < -gencfg['maxv']:
                raise ValueError(
                    f"IQPulseArray[{i}] out of range: [{-gencfg['maxv']}, {gencfg['maxv']}]"
                )
        
        IQPulse = IQPulse[:length_dt]
        
        if len(IQPulse) % 16 != 0:
            extralen = 16 - (len(IQPulse) % 16)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        
        if len(IQPulse) // 16 < 3:
            extralen = 48 - len(IQPulse)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        
        instance.add_pulse(
            ch=channel,
            name=waveform_label,
            idata=IQPulse,
            qdata=np.zeros_like(IQPulse)
        )
        
        gain_sign = -1 if invert else 1
        instance.set_pulse_registers(
            ch=channel,
            freq=0,
            style='arb',
            phase=0,
            gain=gencfg['maxv'] * gain_sign,
            waveform=waveform_label,
            outsel="input"
        )


def FFPulses_directPULSE(instance, t_start='auto'):
    """
    Pulse all FF channels (after registers have been set up).
    
    Parameters:
        instance: Program instance
        t_start: Start time ('auto' or specific time)
    """
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.gen_t0[channel]
        else:
            t_start_ = 'auto'
        instance.pulse(ch=channel, t=t_start_)
