"""
================================================================================
StarterPackConfig.py - Base Configuration for Starter Pack Experiments
================================================================================

This file defines the base hardware configuration shared across all experiments.
It is analogous to MUXInitialize.py in the main codebase.

USAGE:
------
    from StarterPackConfig import BaseConfig, outerFolder

    # Merge experiment-specific config with base
    exp_cfg = {"qubit_freq_start": 4450, "qubit_freq_stop": 4550, ...}
    full_cfg = BaseConfig | exp_cfg

    # Or use the helper function
    from StarterPackConfig import make_config
    full_cfg = make_config(exp_cfg)

CUSTOMIZATION:
--------------
Users should modify the BaseConfig values to match their hardware setup:
- Channel assignments (res_ch, qubit_ch, ro_chs)
- Nyquist zones
- Mixer/LO frequencies
- Default timing parameters
- Qubit-specific parameters (in QubitParameters dict)

================================================================================
"""

import os
import platform

# =============================================================================
# OUTPUT FOLDER
# =============================================================================
# Default location for saving experiment data. Change this to your data directory.

# Detect OS and set appropriate default path
if platform.system() == 'Windows':
    outerFolder = "C:\\Data\\Experiments\\"
elif platform.system() == 'Darwin':  # macOS
    outerFolder = os.path.expanduser("~/Data/Experiments/")
else:  # Linux
    outerFolder = os.path.expanduser("~/data/experiments/")

# Create folder if it doesn't exist
os.makedirs(outerFolder, exist_ok=True)

# =============================================================================
# BASE HARDWARE CONFIGURATION
# =============================================================================
# These parameters define the hardware setup and are shared across all experiments.
# Modify these to match your specific RFSoC/QICK setup.

BaseConfig = {
    # -------------------------------------------------------------------------
    # DAC Channel Assignments
    # -------------------------------------------------------------------------
    "res_ch": 0,  # Resonator/readout DAC channel
    "qubit_ch": 1,  # Qubit drive DAC channel

    # -------------------------------------------------------------------------
    # ADC Channel Assignments
    # -------------------------------------------------------------------------
    "ro_chs": [0],  # Readout ADC channel(s)

    # -------------------------------------------------------------------------
    # Nyquist Zones
    # -------------------------------------------------------------------------
    # Zone 1: 0 to fs/2, Zone 2: fs/2 to fs, etc.
    # Choose based on your frequency plan and DAC sample rate
    "nqz": 1,  # Resonator Nyquist zone
    "res_nqz": 1,  # Alias for resonator NQZ (some experiments use this)
    "qubit_nqz": 2,  # Qubit Nyquist zone

    # -------------------------------------------------------------------------
    # Mixer/LO Frequencies (MHz)
    # -------------------------------------------------------------------------
    # Set these if using external mixers for upconversion
    "mixer_freq": 0,  # Resonator mixer IF (0 if direct synthesis)
    "qubit_mixer_freq": 0,  # Qubit mixer IF (0 if direct synthesis)
    "res_LO": 0,  # Resonator LO frequency
    "qubit_LO": 0,  # Qubit LO frequency

    # -------------------------------------------------------------------------
    # Default Readout Parameters
    # -------------------------------------------------------------------------
    "read_pulse_style": "const",  # Readout pulse shape: "const" or "arb"
    "read_pulse_freq": 6425.0,  # Resonator frequency [MHz]
    "read_pulse_gain": 10000,  # Readout pulse amplitude [DAC units]
    "read_length": 5.0,  # Readout pulse length [µs]
    "res_length": 5.0,  # Alias for read_length (some experiments use this)
    "res_phase": 0,  # Readout pulse phase [degrees]

    # -------------------------------------------------------------------------
    # Default Timing Parameters
    # -------------------------------------------------------------------------
    "adc_trig_offset": 0.5,  # ADC trigger offset after pulse start [µs]
    "relax_delay": 1000,  # Delay between experiments [µs]

    # -------------------------------------------------------------------------
    # Default Averaging
    # -------------------------------------------------------------------------
    "reps": 100,  # Default number of averages per point
    "rounds": 1,  # Number of rounds (for longer averaging)
    "sets": 1,  # Number of experiment sets
}

# =============================================================================
# QUBIT-SPECIFIC PARAMETERS
# =============================================================================
# Define parameters for each qubit in your system.
# Access via: QubitParameters['1']['Readout']['Frequency']

QubitParameters = {
    '1': {
        'Readout': {
            'Frequency': 6425.0,  # Resonator frequency [MHz]
            'Gain': 10000,  # Readout amplitude [DAC units]
            'Readout_Time': 5.0,  # Readout length [µs]
            'ADC_Offset': 0.5,  # ADC trigger offset [µs]
        },
        'Qubit': {
            'Frequency': 4500.0,  # Qubit frequency [MHz]
            'Gain': 20000,  # π pulse amplitude [DAC units]
            'sigma': 0.100,  # Gaussian sigma [µs]
        },
        # Single-shot discrimination parameters (after calibration)
        'angle': 0.0,  # IQ rotation angle [degrees]
        'threshold': 0.0,  # Discrimination threshold
    },
    # Add more qubits as needed:
    # '2': { ... },
    # '3': { ... },
}

# =============================================================================
# FAST FLUX CHANNELS (Optional)
# =============================================================================
# Define fast flux line assignments if your system has them.

FF_Channels = {
    '1': {'channel': 0, 'delay_time': 0.0},
    '2': {'channel': 1, 'delay_time': 0.0},
    '3': {'channel': 2, 'delay_time': 0.0},
    '4': {'channel': 3, 'delay_time': 0.0},
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_config(experiment_config, qubit_id=None):
    """
    Merge experiment-specific config with base config.

    Parameters:
        experiment_config (dict): Experiment-specific parameters
        qubit_id (str, optional): If provided, also merge qubit-specific params

    Returns:
        dict: Complete configuration dictionary

    Example:
        cfg = make_config({'qubit_freq_start': 4450, 'qubit_freq_stop': 4550})
    """
    # Start with base config
    full_config = BaseConfig.copy()

    # Add qubit-specific parameters if requested
    if qubit_id is not None and qubit_id in QubitParameters:
        qp = QubitParameters[qubit_id]
        full_config.update({
            'read_pulse_freq': qp['Readout']['Frequency'],
            'read_pulse_gain': qp['Readout']['Gain'],
            'read_length': qp['Readout']['Readout_Time'],
            'adc_trig_offset': qp['Readout']['ADC_Offset'],
            'qubit_freq': qp['Qubit']['Frequency'],
            'qubit_gain': qp['Qubit']['Gain'],
            'sigma': qp['Qubit']['sigma'],
        })
        if 'angle' in qp:
            full_config['angle'] = qp['angle']
        if 'threshold' in qp:
            full_config['threshold'] = qp['threshold']

    # Override with experiment-specific config
    full_config.update(experiment_config)

    return full_config


def get_qubit_config(qubit_id):
    """
    Get the full configuration for a specific qubit.

    Parameters:
        qubit_id (str): Qubit identifier (e.g., '1', '2')

    Returns:
        dict: Configuration with base + qubit-specific parameters
    """
    return make_config({}, qubit_id=qubit_id)


def list_qubits():
    """Return list of defined qubit IDs."""
    return list(QubitParameters.keys())


def print_config(config, title="Configuration"):
    """Pretty-print a configuration dictionary."""
    print(f"\n{title}")
    print("=" * 50)
    for key, value in sorted(config.items()):
        print(f"  {key}: {value}")
    print()


# =============================================================================
# HARDWARE CONNECTION (Optional)
# =============================================================================
# Uncomment and modify to auto-connect to hardware

# RFSOC_IP = "192.168.1.100"  # IP address of your RFSoC board

# def connect_hardware():
#     """Connect to RFSoC hardware and return (soc, soccfg)."""
#     try:
#         from socProxy import makeProxy
#         soc, soccfg = makeProxy(RFSOC_IP)
#         print(f"Connected to RFSoC at {RFSOC_IP}")
#         return soc, soccfg
#     except Exception as e:
#         print(f"Failed to connect to hardware: {e}")
#         return None, None


# =============================================================================
# MAIN - Print configuration summary when run directly
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("STARTER PACK BASE CONFIGURATION")
    print("=" * 60)

    print(f"\nOutput folder: {outerFolder}")

    print_config(BaseConfig, "Base Hardware Config")

    print("Defined Qubits:")
    print("-" * 50)
    for qid in list_qubits():
        qp = QubitParameters[qid]
        print(f"  Qubit {qid}:")
        print(f"    Readout freq: {qp['Readout']['Frequency']} MHz")
        print(f"    Qubit freq:   {qp['Qubit']['Frequency']} MHz")
        print(f"    π pulse gain: {qp['Qubit']['Gain']} DAC units")

    print("\nExample: Creating config for T1 experiment")
    print("-" * 50)
    t1_params = {
        'ntime_steps': 51,
        'total_time': 150,
    }
    full_cfg = make_config(t1_params, qubit_id='1')
    print(f"  T1-specific: {t1_params}")
    print(f"  Full config has {len(full_cfg)} parameters")