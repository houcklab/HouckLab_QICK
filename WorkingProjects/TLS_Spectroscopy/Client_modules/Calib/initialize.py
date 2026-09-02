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
    "read_length": 20.0,
    "readout_guard_us": 1.0,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6918.380,

    "qubit_pulse_style": "arb",
    "qubit_freq": 4964.860,
    "qubit_pi_freq": 4964.860,
    "qubit_pi_gain": 12500,
    "qubit_pi2_gain": 6250,
    "qubit_drag_beta": 0.0,
    "qubit_anharmonicity_mhz": -180.0,
    "qubit_gain": 12500,
    "qubit_length": 0.5,
    "sigma": 0.5,
    "flat_top_length": None,

    "reset_read_delay_us": 2.0,
    "reset_meas_syncdelay_us": 2.0,
    "reset_max_iters": 3,

    "ff_park_gain": 9401,
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

RESONATOR_FIT_PARAMS = [6874670073.295661, 43750274.39379951, 26.839114267816303, 0.23544808740620699, 67520.12869273516, 9400.565057109374, 0.9986913174586942]

FF_STEP_TARGET_GAIN = 8000

outerFolder = 'Z:/FluxTeam/Data/FTT02_SiOxJJ_2026_08_28/RFSOC'