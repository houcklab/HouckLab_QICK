from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy


FF_CH = 3

FF_Qubits = {
    str(4): {'channel': FF_CH, 'delay_time': 0.0},
}


BaseConfig = {
    "res_ch": 0,
    "qubit_ch": 1,
    "ff_ch": FF_CH,
    "ro_chs": [0],
    "nqz": 2,
    "qubit_nqz": 1,
    "ff_nqz": 1,
    "mixer_freq": 0.0,
    "cavity_LO": 0,

    "reps": 1000,
    "relax_delay": 1500,
    "flux_settle_time_us": 0.5,
    "ff_ramp_length": 0.5,
    "adc_trig_offset": 0.5,
    "res_phase": 165.0,

    "read_pulse_style": "const",
    "read_length": 15.0,
    "readout_guard_us": 1.0,
    "read_pulse_gain": 3500,
    "read_pulse_freq": 7248.967089,

    "qubit_pulse_style": "arb",
    "qubit_freq": 2534.550,
    "qubit_pi_freq": 2534.550,
    "qubit_pi_gain": 5900,
    "qubit_pi2_gain": 2750,
    "qubit_drag_beta": 0.0,
    "qubit_anharmonicity_mhz": -200.0,
    "qubit_gain": 5500,
    "qubit_length": 0.25,
    "sigma": 0.25,
    "flat_top_length": None,

    "ff_park_gain": 0,
    "FF_Qubits": FF_Qubits,

    "trig_buffer_start": 0.02,
    "trig_buffer_end": 0.02,
    "trig_delay": 0.082,
    "use_switch": False,

    "cavity_winding_freq": 0,
    "cavity_winding_offset": 0,
}


FLUX_FIT_PARAMS = None

FF_PARK_GAIN = 0
FF_STEP_TARGET_GAIN = 8000

outerFolder = 'Z:/FluxTeam/Data/FTT02_SiOxJJ_2026_06_25/RFSOC'
