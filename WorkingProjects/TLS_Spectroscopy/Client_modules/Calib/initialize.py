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
    "relax_delay": 1200,
    "flux_settle_time_us": 0.5,
    "ff_ramp_length": 1.0,
    "adc_trig_offset": 0.5,
    "res_phase": 165.0,

    "read_pulse_style": "const",
    "read_length": 10.0,
    "readout_guard_us": 1.0,
    "read_pulse_gain": 1200,
    "read_pulse_freq": 7118.35,

    "qubit_pulse_style": "arb",
    "qubit_freq": 2994.5,
    "qubit_pi_freq": 2994.5,
    "qubit_pi_gain": 20218,
    "qubit_pi2_gain": 10109,
    "qubit_drag_beta": 0.0,
    "qubit_anharmonicity_mhz": -200.0,
    "qubit_gain": 20218,
    "qubit_length": 0.25,
    "sigma": 0.25,
    "flat_top_length": None,

    "ff_park_gain": 1000,
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

RESONATOR_FIT_PARAMS = [7115362032.567416, 110917843.54213749, 11.283057766395405,
                        0.21945247382116667, 23929.719229908005, 12252.43722306208,
                        0.5152813948431779]

FF_STEP_TARGET_GAIN = 8000

outerFolder = 'Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC'
