parameter_higher_excited = {
    'yoko_values': [0.02, 0.1, 0.25],
    'FF_gains': [0, 0, 0],

    'Left_Qubit': {
        "cavity_atten": 12,
        "cavity_frequency": 249.7,
        "cavity_gain": 30000,
        "qubit_frequency01": 4215,  # left qubit
        "qubit_pulse_parameters01": {"sigma": 0.05, "pi_gain": 5200},  # 4800},  #left qubit
        "qubit_frequency12": 3988.4,  # left qubit
        "qubit_pulse_parameters12": {"sigma": 0.05, "pi_gain": 4500},  # 4800},  #left qubit
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
}



parameter_dia = {
    'yoko_values': [-0.213, 0.009, 0.43],
    'FF_gains': [15000, -30000, 0],
    'FF_PiPulse': [15000, -30000, 0],

    'Pi_pulse_Left_Qubit': {
        "cavity_atten": 1,
        "cavity_frequency":  249.55,
        "cavity_gain": 30000,
        "qubit_frequency": 4392.5,   #left qubit
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4500 }, #4800},  #left qubit
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },

    'Left_Qubit': {
        "cavity_atten": 1,
        "cavity_frequency":  249.55,
        "cavity_gain": 30000,
        "qubit_frequency": 4392.5,   #left qubit
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4500}, #4800},  #left qubit
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
    'Middle_Qubit': {
        "cavity_atten": 2,
        "cavity_frequency": 442.5,
        "cavity_gain": 30000,
        "qubit_frequency": 4284.5,    #Middle qubit
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 7500},  #middle qubit
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
}


parameter_3Q = {
    'yoko_values': [-0.213, 0.009, 0.135],
    'FF_gains': [15000, 15000, 0],

    'Left_Qubit': {
        "cavity_atten": 3,
        "cavity_frequency":  249.62,
        "cavity_gain": 30000,
        "qubit_frequency": 4384.65 - 2,   #left qubit
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4650}, #4800},  #left qubit
        # "qubit_frequency": 4691.9,    #Middle qubit
        # "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4800},  #middle qubit
        # "qubit_frequency": 4528.25 + 3,  #Right qubit
        # "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 3800}, #Right Qubit
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
    'Middle_Qubit': {
        "cavity_atten": 6,
        "cavity_frequency": 442.85,
        # "cavity_atten": 4,
        # "cavity_frequency": 442.95,
        "cavity_gain": 30000,
        # "qubit_frequency": 4384.65,   #left qubit
        # "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4650}, #4800},  #left qubit
        "qubit_frequency": 4691.9,    #Middle qubit
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4800},  #middle qubit
        # "qubit_frequency": 4528.25 + 3,  #Right qubit
        # "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 3800}, #Right Qubit
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
    'Right_Qubit': {
        "cavity_atten": 3,
        "cavity_frequency":  640.85,
        "cavity_gain": 30000,
        # "qubit_frequency": 4384.65,   #left qubit
        # "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4650}, #4800},  #left qubit
        # "qubit_frequency": 4691.9,    #Middle qubit
        # "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4800},  #middle qubit
        "qubit_frequency": 4528.25 + 3,  #Right qubit
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 3800}, #Right Qubit
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    }
}



parameterCorrect = {
    'yoko_values': [-0.213, 0.009, 0.135],
    'FF_gains': [15000, 15000, 0],

    'Left_Qubit': {
        "cavity_atten": 3,
        "cavity_frequency":  249.62,
        "qubit_frequency": 4384.65,
        "cavity_gain": 30000,
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4650},
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
    'Middle_Qubit': {
        "cavity_atten": 4,
        "cavity_frequency": 442.95,
        "qubit_frequency": 4691.9,
        "cavity_gain": 30000,
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4800},
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
    'Right_Qubit': {
        "cavity_atten": 3,
        "cavity_frequency":  640.85,
        "qubit_frequency": 4528.25 + 3,
        "cavity_gain": 30000,
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 3800},
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    }
}


parameter_2QubitOscillations = {
    'yoko_values': [-0.213, 0.035, 0.52],
    'FF_gains': [15000, 15000, 0],
    'Middle_Qubit': {
        "cavity_atten": 2,
        "cavity_frequency": 442.82,
        "qubit_frequency": 4706.45,
        "cavity_gain": 30000,
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 4000},
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    },
    'Left_Qubit': {
        "cavity_atten": 3,
        "cavity_frequency": 249.6,
        "qubit_frequency": 4402.25 - 1.5,
        "cavity_gain": 30000,
        "qubit_pulse_parameters": {"sigma": 0.05, "pi_gain": 3300},
        "relax_delay": 300,
        "adc_offset": 1.2,
        "readout_time": 4,
    }
}
