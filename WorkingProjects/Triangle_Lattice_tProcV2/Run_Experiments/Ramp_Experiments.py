# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')


from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6979.1  - BaseConfig["cavity_LO"] / 1e6, 'Gain': 12500,
                      "FF_Gains": [0, 0, 2000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4736.6, 'sigma': 0.05, 'Gain': 3740},
          'Pulse_FF': [0, 0, 2000, -30000]},  # FOURTH index
    '2': {'Readout': {'Frequency': 7095.687 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4680,
                      "FF_Gains": [0, 0, 2000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4512.7, 'sigma': 0.05, 'Gain': 4200},
          'Pulse_FF':[0, 0, 2000, -30000]}, # third index
    '4': {'Readout': {'Frequency': 7269.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 15000,
                      "FF_Gains": [0, 0, 2000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4035.4, 'sigma': 0.05, 'Gain': 9500},
          'Pulse_FF': [0, 0, 2000, -30000]},
    'Plus': {'Qubit': {'Frequency': 4682.0, 'sigma': 0.05, 'Gain': 6150}, # RO = 1
        'Pulse_FF': [0, 0, 1000, -22500]},
    'Minus': {'Qubit': {'Frequency': 4559.5, 'sigma': 0.05, 'Gain': 5000}, # RO = 2
         'Pulse_FF':[0, 0, 1000, -22500]}
    }

FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 2000
FF_gain4_BS = -4500
# FF_gain3_BS = 1000
# FF_gain4_BS = -8000

FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = -1150
FF_gain4_expt = -22500
FF_gain5_expt = 0  # 8000
FF_gain6_expt = 0
FF_gain7_expt = -1150
FF_gain8_expt = -22500

FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 2000
FF_gain4_BS = -4500
# FF_gain3_BS = 1000
# FF_gain4_BS = -8000

Qubit_Readout = [1,2]
Qubit_Pulse = [2]


RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 1000, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 3, 'cav_relax_delay': 10}

Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 200, "SpecSpan":10, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 950,
                        'reps': 15, 'rounds': 15}

Run_Spec_v_FFgain = False
### Inherits spec parameters from above
FF_sweep_spec_relevant_params = {"qubit_FF_index": 2,
                            "FF_gain_start": -8000, "FF_gain_stop":8000, "FF_gain_steps":11}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"sigma": 0.05, "max_gain":7000}

RunT1 = False
RunT2 = False

T1_params = {"step": 5, "expts": 40, "reps": 15, "rounds": 15}

T2R_params = {"step": 100 * 2.32515e-3, "expts": 100, "reps": 20, "rounds": 20,
              "freq_shift": 0.0, "phase_step_deg": 15, "relax_delay":150}


RunT1_TLS = False
T1TLS_params = {'gainStart': 0, 'gainStop': 0, 'gainNumPoints': 1, 'wait_times': np.linspace(0.01, 150, 31),
                'angle': None, 'threshold': None,
                'meas_shots': 50, 'repeated_nums':10, 'SS_calib_shots': 1500,
                'qubitIndex': 2}#, Qubit_Pulse[0]}

SingleShot = False
SS_params = {"Shots":500, "readout_length": 2.5, "adc_trig_delay": 0.3,
             'number_of_pulses': 1, 'relax_delay': 200}


SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 2000, "gain_stop": 10000, "gain_pts": 7, "span": 2, "trans_pts": 5, 'number_of_pulses': 1}

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 500, "q_gain_pts": 7, "q_freq_span": 1.5, "q_freq_pts": 9,
               'number_of_pulses': 1}

run_ramp_gain_calibration = False
ff_expt_vs_pop_dict = {'swept_qubit': str(3),
                       'reps': 4000, 'gain_start':-1200, 'gain_end':-1100, 'gain_num_points':6,
                        'ramp_duration':9000}

run_ramp_duration_calibration = False
ramp_duration_calibration_dict = {'reps': 1000, 'duration_start': int(1), 'duration_end': int(1250), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': True}

RampCurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep  time
current_calibration_gain_dict = {'reps': 100, 'swept_index':3,
                                 't_offset': -49, 'relax_delay': 200, 'ramp_time':9000,
                            'gainStart': -4800, 'gainStop': -4200, 'gainNumPoints': 11,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,}

RampCurrentCalibration_OffsetSweep = True
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time
#
current_calibration_offset_dict = {'reps': 100, 'ramp_time': 9000, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,
                                   'offsetStart': -20, 'offsetStop':20, 'offsetNumPoints':21}

run_1D_current_calib = False
t_offset = 50

# qubits involved in beamsplitter interaction
Qubit_BS = [1,2]

qubit_to_FF_dict = {1: 3, 2: 2}

# convert Qubit_BS to index based on the order [5, 1, 2, 4]
Qubit_BS_indices = [qubit_to_FF_dict[qubit] for qubit in Qubit_BS]
print(Qubit_BS_indices)

run_ramp_population_over_time = False
delay_vs_pop_dict = {'ramp_duration' : 9000, 'ramp_shape': 'cubic',
        'time_start': 9000, 'time_end' : 10000, 'time_num_points' : 20, 'reps':2000}

# run_ramp_oscillations = False
# # Ramp to FFExpts, then jump to FF_BS
# oscillation_single_dict = {'reps': 1000, 'start': int(0), 'step': int(10), 'expts': 200, 'relax_delay': 300,
#                            'ramp_duration': int(20000), 'ramp_shape': 'cubic'}

# This ends the working section of the file.
exec(open("RUN_EXPTS.py").read())