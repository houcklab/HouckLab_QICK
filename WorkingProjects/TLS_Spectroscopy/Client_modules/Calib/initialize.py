from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy


FF_CH = 3

FF_Qubits = {
    str(1): {'channel': FF_CH, 'delay_time': 0.0},
}


BaseConfig = {
    "res_ch": 0,
    "qubit_ch": 1,
    "ff_ch": FF_CH,
    "ro_chs": [0],
    "nqz": 2,
    "qubit_nqz": 2,
    "ff_nqz": 1,
    "mixer_freq": 0.0,
    "cavity_LO": 0,

    "reps": 1000,
    "relax_delay": 1000,
    "flux_settle_time_us": 0.5,
    "ff_ramp_length": 4.0,
    "adc_trig_offset": 0.5,
    "res_phase": 165.0,

    "read_pulse_style": "const",
    "read_length": 5.0,
    "readout_guard_us": 1.0,
    "read_pulse_gain": 1740,
    "read_pulse_freq": 6933.026,

    "qubit_pulse_style": "arb",
    "qubit_freq": 4367.250,
    "qubit_pi_freq": 4367.250,
    "qubit_pi_gain": 11100,
    "qubit_pi2_gain": 5550,
    "qubit_drag_beta": 0.0,
    "qubit_anharmonicity_mhz": -180.0,
    "qubit_gain": 11100,
    "qubit_length": 0.25,
    "sigma": 0.25,
    "flat_top_length": None,

    "reset_read_delay_us": 2.0,
    "reset_meas_syncdelay_us": 2.0,
    "reset_max_iters": 3,

    "ff_park_gain": -25790,
    "ff_park_settle_us": 1.0,
    "FF_Qubits": FF_Qubits,

    "trig_buffer_start": 0.02,
    "trig_buffer_end": 0.02,
    "trig_delay": 0.082,
    "use_switch": False,

    "cavity_winding_freq": 0,
    "cavity_winding_offset": 0,
}


FLUX_FIT_PARAMS = None

RESONATOR_FIT_PARAMS = None

FF_STEP_TARGET_GAIN = 8000

outerFolder = 'Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC'