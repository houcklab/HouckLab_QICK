# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')


from qubit_parameter_files.Qubit_Parameters_Master import *

Qubit_Parameters = {
    '1ef': {'Readout': {'Frequency': 7121.1, 'Gain': 825,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 8318},
          'Pulse_FF': readout_params},
    '2ef': {'Readout': {'Frequency': 7077.6, 'Gain': 700,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 4704},
          'Pulse_FF': readout_params},
    '3ef': {'Readout': {'Frequency': 7511.4, 'Gain': 580,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 9291},
          'Pulse_FF': readout_params},
    '4ef': {'Readout': {'Frequency': 7568.1, 'Gain': 750,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 8000},
          'Pulse_FF': readout_params},
    '5ef': {'Readout': {'Frequency': 7362.9, 'Gain': 833,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 11800},
          'Pulse_FF': readout_params},
    '6ef': {'Readout': {'Frequency': 7441.7, 'Gain': 1033,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 5830},
          'Pulse_FF': readout_params},
    '7ef': {'Readout': {'Frequency': 7254.2, 'Gain': 666,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 10800},
          'Pulse_FF': readout_params},
    '8ef': {'Readout': {'Frequency': 7308.65, 'Gain': 666,
                      'FF_Gains': readout_params, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3600, 'sigma': 0.03, 'Gain': 5371},
          'Pulse_FF': readout_params},
}


Qubit_Readout = [8]
Qubit_Pulse = [8]

for Q in [1,2,3,4,5,6,7,8]:
# for Q in [3]:
    Qubit_Readout = [Q]
    Qubit_Pulse =   [f"{Q}R"]
    # Qubit_Pulse = [Q]
    # Qubit_Pulse = ['5AC']
    Pulse_FF = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']
    Expt_FF_subsys = Expt_FF.subsys(Q, det=-10000)

    Expt_FF_subsys = Expt_FF.subsys(Q, det=-20000)

    FF_gain1_expt = Expt_FF_subsys[0]
    FF_gain2_expt = Expt_FF_subsys[1]
    FF_gain3_expt = Expt_FF_subsys[2]
    FF_gain4_expt = Expt_FF_subsys[3]
    FF_gain5_expt = Expt_FF_subsys[4]
    FF_gain6_expt = Expt_FF_subsys[5]
    FF_gain7_expt = Expt_FF_subsys[6]
    FF_gain8_expt = Expt_FF_subsys[7]

    # print(f'pulse gains: {Qubit_Parameters[prepared_state]['Pulse_FF']}')

    t = True
    f = False

    Run_FF_v_Ramsey = False
    FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 3, "expts": 61, "reps": 400,
                                        "qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                        "FF_gain_start": Expt_FF[int(str(Qubit_Readout[0])[0])-1] - 100,
                                        "FF_gain_stop": Expt_FF[int(str(Qubit_Readout[0])[0])-1] + 100,
                                        "FF_gain_steps": 7,
                                        "relax_delay":100, 'populations':False# "qubit_drive_freq":3950.0
                                       }

    RunTransmissionSweep = False # determine cavity frequency
    Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                            "readout_length": 3, 'cav_relax_delay': 10}
    Run2ToneSpec = False
    Spec_relevant_params = {
                          # "qubit_gain": 4000, "SpecSpan": 400, "SpecNumPoints": 71,
                          #   "qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 71,
                          #    "qubit_gain": 100, "SpecSpan": 150, "SpecNumPoints": 4*71,
                            "qubit_gain": 199, "SpecSpan": 50, "SpecNumPoints": 71,
                            # "qubit_gain": 10, "SpecSpan": 10, "SpecNumPoints": 71,
                            'Gauss': False, "sigma": 0.03, "Gauss_gain": Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Gain'],
                            'reps': 2*155, 'rounds': 1}

    Run_Spec_vs_FFgain = True # Inherit spec parameters from above

    FF_sweep_spec_relevant_params = {"qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                "FF_gain_start": Pulse_FF[int(str(Qubit_Readout[0])[0])-1] - 1500,
                                "FF_gain_stop": Pulse_FF[int(str(Qubit_Readout[0])[0])-1] + 1500,
                                     "FF_gain_steps": 11,
                                     'relax_delay':100}

    # FF_sweep_spec_relevant_params = {"qubit_FF_index": int(str(Qubit_Readout[0])[0]),
    #                                 "FF_gain_start": -25000,
    #                                 "FF_gain_stop": -5000,
    #                                      "FF_gain_steps": 31,
    #                                      'relax_delay':100}
    Run_Spec_vs_Qubit_gain = False
    gain_sweep_spec_params = {"qubit_gain_start": 100,
                                     "qubit_gain_stop": 3000,
                                     "qubit_gain_steps": 11,
                                     'relax_delay': 100}

    FluxStability = False # Repeat SpecSlice over time
    Flux_Stability_params = {"delay_minutes": 10, "num_steps": 6 * 8}


    Run_Spec_v_Qblox = False
    Spec_v_Qblox_params = {"Qblox_start": 0.4, "Qblox_stop": 1.2, "Qblox_steps": 6, "DAC": 9}

    RunAmplitudeRabi = False
    Amplitude_Rabi_params = {"max_gain": 15000, 'relax_delay':100}


    SingleShot = False
    SS_params = {"Shots": 4000, 'number_of_pulses': 1, 'relax_delay': 200,
                 "readout_lengths":[6],
                 "adc_trig_delays":[0]}

    SingleShotDecimate = False

    SingleShot_ReadoutOptimize = False
    SS_R_params = {"Shots": 500,
                   "gain_start": 2000, "gain_stop": 8000, "gain_pts": 8, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}

    SingleShot_QubitOptimize = False
    SS_Q_params = {"Shots": 500,
                   "q_gain_span": 1000, "q_gain_pts": 7, "q_freq_span": 2.0, "q_freq_pts": 7,
                   'number_of_pulses': 1,
                   'qubit_sweep_index': -1}

    if SingleShot_QubitOptimize and SS_Q_params['qubit_sweep_index'] >= len(Qubit_Pulse):
        raise ValueError("Qubit optimize sweep index out of range")

    SingleShot_SNROptimize = False
    SNR_params = {'Shots': 1000,
                  'gain_start': -2.6, 'gain_stop': 0.5, 'gain_pts': 20,
                  'freq_start': 7700, 'freq_stop': 8000, 'freq_pts': 20,
                  'number_of_pulses': 1}
    # These T1 and T2R experiments are done at FFPulses!
    RunT1 = False
    RunT2 = False

    T1_params = {"stop_delay_us": 100, "expts": 40, "reps": 150}

    T2R_params = {"stop_delay_us": 5, "expts": 150, "reps": 300,
                  "freq_shift": 0.0, "phase_shift_cycles": 5, "relax_delay":200}

    RunT2E = False


    RunT1_TLS = False
    T1TLS_params = {"FF_gain_start": max(-32766, Readout_FF[Q-1]-10000),
                    "FF_gain_stop": min(32766, Readout_FF[Q-1]+10000),
                    "FF_gain_steps": 101,
                    "stop_delay_us": 5, "expts": 5, "reps": 2*300,
                    'qubitIndex': int(str(Qubit_Readout[0])[0])}

    T1TLS_params = {"FF_gain_start": -10000,
                        "FF_gain_stop": 0,
                        "FF_gain_steps": 201,
                        "stop_delay_us": 5, "expts": 5, "reps": 300,
                        'qubitIndex': int(str(Qubit_Readout[0])[0])}

    # SingleShot_ROTimingOptimize = False
    # SS_Timing_params = {"Shots": 500,
    #                   "read_length_start":1, "read_length_end":10, "read_length_points":5,
    #                   "trig_time_start":0.1, "trig_time_end":3, "trig_time_points":5}
    Run_Readout_Crosstalk = False
    ro_crosstalk_params = {"Shots": 4000, "Qubit_Pulse": Qubit_Pulse} # Second argument is only for plotting


    Oscillation_Gain = False
    oscillation_gain_dict = {'qubit_FF_index': Q+2, 'reps': 700,
                             'start': 1, 'step': 20, 'expts': 71,
                             'gainStart': -6000,
                             'gainStop': -4000, 'gainNumPoints': 11, 'relax_delay': 200,
                             'fit': True}
    Oscillation_Gain_QICK_sweep = True

    try:
        center = Ramp_FF[oscillation_gain_dict['qubit_FF_index']-1]
        # center = -13000
        oscillation_gain_dict['gainStart'] = center - 1000
        oscillation_gain_dict['gainStop'] = center + 1000
    except:
        pass


    Oscillation_Single = False # uses same dict as gain sweep

    Calib_FF_vs_drive_delay = False
    ff_drive_delay_dict = {'start':200, 'step':8, 'expts': 200, # delay of FF, units of samples
                           'qubit_delay_cycles': 80,
                           'reps': 4000,
                            'qubit_index': Qubit_Pulse[0],}

    # RunChiShift = False
    # ChiShift_Params = {'pulse_expt': {'check_12': False},
    #                    'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'], 'qubit_gain01': 1670 // 2,
    #                    'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'],  'qubit_gain12': 1670 // 2}


    CalibrationFF_params = {'FFQubitIndex': 3, 'FFQubitExpGain': 3000,
                            "start": 0, "step": 1, "expts": 20 * 16 * 1,
                            "reps": 100, "rounds": 200, "relax_delay": 100, "YPulseAngle": 93,
               }


    SingleShot_2Qubit = False
    SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400}


    SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400,
                    'second_qubit_freq': 3809.3, 'second_qubit_gain': 1140}

    # This ends the working section of the file.
    #----------------------------------------
    # Not used
    FF_gain1_BS = 0
    FF_gain2_BS = 0
    FF_gain3_BS = 0
    FF_gain4_BS = 0
    FF_gain5_BS = 0
    FF_gain6_BS = 0
    FF_gain7_BS = 0
    FF_gain8_BS = 0
    exec(open("UPDATE_CONFIG.py").read())
    #--------------------------------------------------
    # This begins the booleans
    soc.reset_gens()


