"""Board-level default cfg (channel wiring, Nyquist zones, trigger timing) and the fast-flux map."""

import copy

BASE_CONFIG = {
    "res_ch": 0,
    "qubit_ch": 1,
    "mixer_freq": 0.0,  # MHz
    "ro_chs": [0],
    "reps": 1000,
    "nqz": 2,
    "qubit_nqz": 1,
    "relax_delay": 3000,
    "res_phase": 0,
    "pulse_style": "const",
    "length": 30,  # [us] resonator pulse duration (converted by each program)
    "pulse_gain": 30000,  # [DAC units]
    "adc_trig_offset": 1,  # [us]
    "cavity_LO": 0,  # Hz
    "cavity_winding_freq": 0,
    "cavity_winding_offset": 0,
    "trig_buffer_start": 0.02,
    "trig_buffer_end": 0.02,
    "trig_delay": 0.082,
}
BaseConfig = BASE_CONFIG

FF_channel1 = 2
FF_channel2 = 4
FF_channel3 = 5
FF_channel4 = 6


FF_QUBITS = {
    str(1): {"channel": FF_channel1, "delay_time": 0.017 + 0.0045},
    str(2): {"channel": FF_channel2, "delay_time": 0},
    str(3): {"channel": FF_channel3, "delay_time": 0},
    str(4): {"channel": FF_channel4, "delay_time": 0},
}
FF_Qubits = FF_QUBITS


def base_config():
    """Return a fresh deep copy of BASE_CONFIG."""
    return copy.deepcopy(BASE_CONFIG)
