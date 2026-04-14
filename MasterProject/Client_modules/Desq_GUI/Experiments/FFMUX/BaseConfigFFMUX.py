"""
================================================================================
BaseConfigFFMUX.py - Base Configuration for FFMUX Experiments
================================================================================

Base hardware configuration for experiments using Fast Flux (FF) and
Multiplexed (MUX) readout. Analogous to MUXInitialize.py in the main codebase.

KEY DIFFERENCES FROM BASIC CONFIG:
----------------------------------
1. FF_Qubits dict: Defines flux channels and bias gains for each qubit
2. MUX readout: Multiple resonator frequencies read simultaneously
3. Per-qubit parameters: res_freqs, res_gains, qubit_freqs, qubit_gains as lists

USAGE:
------
    from StarterPackConfigFFMUX import BaseConfig, FF_Qubits, make_config
    
    # For single qubit experiment
    cfg = make_config(
        exp_cfg={"stop_delay_us": 100, "expts": 51},
        qubit_indices=[5]  # Measure qubit 5
    )

================================================================================
"""

import os
import platform
import numpy as np

# =============================================================================
# OUTPUT FOLDER
# =============================================================================

if platform.system() == 'Windows':
    outerFolder = "C:\\Data\\Experiments\\"
elif platform.system() == 'Darwin':
    outerFolder = os.path.expanduser("~/Data/Experiments/")
else:
    outerFolder = os.path.expanduser("~/data/experiments/")

os.makedirs(outerFolder, exist_ok=True)


# =============================================================================
# BASE HARDWARE CONFIGURATION
# =============================================================================

BaseConfig = {
    # -------------------------------------------------------------------------
    # DAC Channel Assignments
    # -------------------------------------------------------------------------
    "res_ch": 0,                      # Resonator/readout DAC channel (MUX capable)
    "qubit_ch": 1,                    # Qubit drive DAC channel
    
    # -------------------------------------------------------------------------
    # ADC Channel Assignments
    # -------------------------------------------------------------------------
    "ro_chs": [0],                    # Readout ADC channel(s)
    
    # -------------------------------------------------------------------------
    # Nyquist Zones
    # -------------------------------------------------------------------------
    "res_nqz": 1,                     # Resonator Nyquist zone
    "qubit_nqz": 2,                   # Qubit Nyquist zone
    
    # -------------------------------------------------------------------------
    # Mixer/LO Frequencies (MHz)
    # -------------------------------------------------------------------------
    "mixer_freq": 0,                  # Resonator mixer IF
    "qubit_mixer_freq": 0,            # Qubit mixer IF
    "res_LO": 0,                      # Resonator LO frequency
    "qubit_LO": 0,                    # Qubit LO frequency
    
    # -------------------------------------------------------------------------
    # Readout Parameters (populated per-qubit by make_config)
    # -------------------------------------------------------------------------
    "res_freqs": [6425.0],            # Resonator frequencies [MHz] (list for MUX)
    "res_gains": [1.0],               # Resonator gains (normalized, list for MUX)
    "res_length": 5.0,                # Readout pulse length [µs]
    "readout_lengths": [5.0],         # ADC readout lengths [µs] (list for MUX)
    "adc_trig_delays": [0.5],         # ADC trigger delays [µs] (list for MUX)
    
    # -------------------------------------------------------------------------
    # Qubit Parameters (populated per-qubit by make_config)
    # -------------------------------------------------------------------------
    "qubit_freqs": [4500.0],          # Qubit frequencies [MHz] (list)
    "qubit_gains": [20000],           # π pulse amplitudes [DAC units] (list)
    "sigma": 0.100,                   # Gaussian sigma [µs]
    
    # -------------------------------------------------------------------------
    # Timing Parameters
    # -------------------------------------------------------------------------
    "relax_delay": 500,               # Delay between experiments [µs]
    
    # -------------------------------------------------------------------------
    # Averaging
    # -------------------------------------------------------------------------
    "reps": 100,                      # Repetitions per round
    "rounds": 1,                      # Number of rounds
}


# =============================================================================
# FAST FLUX QUBIT DEFINITIONS
# =============================================================================
# Define the flux bias channels and gains for each qubit.
# Gains are in DAC units [-32766, 32766].

FF_Qubits = {
    '1': {
        'channel': 0,                 # DAC channel for qubit 1's flux line
        'delay_time': 0.0,            # Timing offset [µs]
        'Gain_Readout': 0,            # Flux bias during readout
        'Gain_Expt': 0,               # Flux bias during experiment
        'Gain_Pulse': 0,              # Flux bias during qubit pulses
        'Gain_Init': 0,               # Flux bias for initialization
    },
    '2': {
        'channel': 1,
        'delay_time': 0.0,
        'Gain_Readout': 0,
        'Gain_Expt': 0,
        'Gain_Pulse': 0,
        'Gain_Init': 0,
    },
    '3': {
        'channel': 2,
        'delay_time': 0.0,
        'Gain_Readout': 0,
        'Gain_Expt': 0,
        'Gain_Pulse': 0,
        'Gain_Init': 0,
    },
    '4': {
        'channel': 3,
        'delay_time': 0.0,
        'Gain_Readout': 0,
        'Gain_Expt': 0,
        'Gain_Pulse': 0,
        'Gain_Init': 0,
    },
    '5': {
        'channel': 4,
        'delay_time': 0.0,
        'Gain_Readout': 0,
        'Gain_Expt': 0,
        'Gain_Pulse': 0,
        'Gain_Init': 0,
    },
    '6': {
        'channel': 5,
        'delay_time': 0.0,
        'Gain_Readout': 0,
        'Gain_Expt': 0,
        'Gain_Pulse': 0,
        'Gain_Init': 0,
    },
    '7': {
        'channel': 6,
        'delay_time': 0.0,
        'Gain_Readout': 0,
        'Gain_Expt': 0,
        'Gain_Pulse': 0,
        'Gain_Init': 0,
    },
    '8': {
        'channel': 7,
        'delay_time': 0.0,
        'Gain_Readout': 0,
        'Gain_Expt': 0,
        'Gain_Pulse': 0,
        'Gain_Init': 0,
    },
}


# =============================================================================
# QUBIT PARAMETERS (Calibrated Values)
# =============================================================================
# Store calibrated parameters for each qubit.

QubitParameters = {
    '1': {
        'Readout': {
            'Frequency': 6425.0,      # Resonator frequency [MHz]
            'Gain': 1.0,              # Normalized gain
            'Readout_Time': 5.0,      # Readout length [µs]
            'ADC_Offset': 0.5,        # ADC trigger offset [µs]
        },
        'Qubit': {
            'Frequency': 4500.0,      # Qubit frequency [MHz]
            'Gain': 20000,            # π pulse amplitude [DAC units]
            'sigma': 0.100,           # Gaussian sigma [µs]
        },
        'FF_Gains': [0, 0, 0, 0, 0, 0, 0, 0],  # FF gains during this qubit's readout
        'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0],  # FF gains during this qubit's pulses
    },
    # Add more qubits as calibrated...
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_config(exp_cfg=None, qubit_indices=None):
    """
    Create a complete configuration by merging base config with experiment config.
    
    Parameters:
        exp_cfg (dict): Experiment-specific parameters
        qubit_indices (list): List of qubit indices to measure (e.g., [1, 5])
                             If None, uses qubit 1
    
    Returns:
        dict: Complete configuration dictionary
    """
    # Start with base config
    cfg = BaseConfig.copy()
    
    # Add FF_Qubits
    cfg["FF_Qubits"] = FF_Qubits.copy()
    
    # Set up qubit-specific parameters
    if qubit_indices is None:
        qubit_indices = [1]
    
    cfg["Qubit_Readout_List"] = qubit_indices
    cfg["Qubit_Pulse_List"] = qubit_indices
    
    # Build lists from QubitParameters
    res_freqs = []
    res_gains = []
    readout_lengths = []
    adc_trig_delays = []
    qubit_freqs = []
    qubit_gains = []
    
    for qid in qubit_indices:
        qid_str = str(qid)
        if qid_str in QubitParameters:
            qp = QubitParameters[qid_str]
            res_freqs.append(qp['Readout']['Frequency'])
            res_gains.append(qp['Readout']['Gain'])
            readout_lengths.append(qp['Readout']['Readout_Time'])
            adc_trig_delays.append(qp['Readout']['ADC_Offset'])
            qubit_freqs.append(qp['Qubit']['Frequency'])
            qubit_gains.append(qp['Qubit']['Gain'])
            
            # Update FF_Qubits with qubit-specific FF gains
            if 'FF_Gains' in qp:
                for i, gain in enumerate(qp['FF_Gains']):
                    ff_qid = str(i + 1)
                    if ff_qid in cfg["FF_Qubits"]:
                        cfg["FF_Qubits"][ff_qid]['Gain_Readout'] = gain
            if 'Pulse_FF' in qp:
                for i, gain in enumerate(qp['Pulse_FF']):
                    ff_qid = str(i + 1)
                    if ff_qid in cfg["FF_Qubits"]:
                        cfg["FF_Qubits"][ff_qid]['Gain_Pulse'] = gain
        else:
            # Use defaults
            res_freqs.append(6425.0)
            res_gains.append(1.0)
            readout_lengths.append(5.0)
            adc_trig_delays.append(0.5)
            qubit_freqs.append(4500.0)
            qubit_gains.append(20000)
    
    cfg["res_freqs"] = res_freqs
    cfg["res_gains"] = res_gains
    cfg["readout_lengths"] = readout_lengths
    cfg["adc_trig_delays"] = adc_trig_delays
    cfg["qubit_freqs"] = qubit_freqs
    cfg["qubit_gains"] = qubit_gains
    cfg["ro_chs"] = list(range(len(qubit_indices)))  # One ADC per qubit
    
    # Override with experiment-specific config
    if exp_cfg:
        cfg.update(exp_cfg)
    
    return cfg


def set_ff_gains(cfg, qubit_id, readout_gains=None, pulse_gains=None):
    """
    Update FF gains for a specific qubit configuration.
    
    Parameters:
        cfg (dict): Configuration to update
        qubit_id (int): Qubit ID
        readout_gains (list): FF gains during readout (8 values)
        pulse_gains (list): FF gains during qubit pulses (8 values)
    """
    if readout_gains is not None:
        for i, gain in enumerate(readout_gains):
            ff_qid = str(i + 1)
            if ff_qid in cfg["FF_Qubits"]:
                cfg["FF_Qubits"][ff_qid]['Gain_Readout'] = gain
    
    if pulse_gains is not None:
        for i, gain in enumerate(pulse_gains):
            ff_qid = str(i + 1)
            if ff_qid in cfg["FF_Qubits"]:
                cfg["FF_Qubits"][ff_qid]['Gain_Pulse'] = gain


def IQ_contrast(avgi, avgq):
    """
    Calculate IQ contrast (magnitude of complex signal).
    
    Parameters:
        avgi: I quadrature data
        avgq: Q quadrature data
    
    Returns:
        Magnitude of the IQ signal
    """
    return np.abs(avgi + 1j * avgq)


def print_config(cfg, title="Configuration"):
    """Pretty-print a configuration dictionary."""
    print(f"\n{title}")
    print("=" * 60)
    for key, value in sorted(cfg.items()):
        if key == "FF_Qubits":
            print(f"  {key}: <{len(value)} qubits defined>")
        elif isinstance(value, list) and len(value) > 4:
            print(f"  {key}: [{value[0]}, {value[1]}, ..., {value[-1]}] ({len(value)} items)")
        else:
            print(f"  {key}: {value}")
    print()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("FFMUX STARTER PACK BASE CONFIGURATION")
    print("=" * 60)
    
    print(f"\nOutput folder: {outerFolder}")
    print(f"FF Qubits defined: {list(FF_Qubits.keys())}")
    
    # Example: create config for qubit 1
    cfg = make_config({"stop_delay_us": 100, "expts": 51}, qubit_indices=[1])
    print_config(cfg, "Example Config for Qubit 1")
