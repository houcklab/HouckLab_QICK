# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import \
    (RampCurrentCalibrationGain, RampCurrentCalibration1D,RampCurrentCalibration1DShots, RampCurrentCalibrationOffset,
     RampCurrentCalibrationOffset_Multiple, RampCurrentCalibrationTime)
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import RampDurationVsPopulation, \
    FFExptVsPopulation, TimeVsPopulation
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCorrelations import CurrentCorrelationMeasurement

import numpy as np


Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4393.76, 'sigma': 0.07, 'Gain': 3920},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 3920},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3829.2, 'sigma': 0.07, 'Gain': 4240},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 4240},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3560.5, 'sigma': 0.07, 'Gain': 17000},
          # 'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 17000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4116.7, 'sigma': 0.07, 'Gain': 6400},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 6400},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4101.3, 'sigma': 0.07, 'Gain': 5100},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4000.9, 'sigma': 0.07, 'Gain': 3844},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3937.4, 'sigma': 0.07, 'Gain': 10202},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4049.9, 'sigma': 0.07, 'Gain': 5810},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'BD': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                       "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
           'Qubit': {'Frequency': 4101.97, 'sigma': 0.07, 'Gain': 4800},
           'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'BC': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7400,
                       "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
           'Qubit': {'Frequency': 4051.2, 'sigma': 0.07, 'Gain': 4220},
           'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
}


# with splitter
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 2300,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4393.15, 'sigma': 0.07, 'Gain': 4190},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.65 - BaseConfig["res_LO"], 'Gain': 1600,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4120.6, 'sigma': 0.07, 'Gain': 1700},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 2000,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3559.7, 'sigma': 0.07, 'Gain': 19140},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7567.9 - BaseConfig["res_LO"], 'Gain': 1500,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3810, 'sigma': 0.07, 'Gain': 1140},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 700,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3937.3, 'sigma': 0.07, 'Gain': 4085},
          'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 820,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4024.3, 'sigma': 0.07, 'Gain': 1160},
          'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 740,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3998.0, 'sigma': 0.07, 'Gain': 2280},
          'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 800,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 4118.2, 'sigma': 0.07, 'Gain': 1790},
              'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},

}

### with LO

# with splitter
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 2300,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4393.15, 'sigma': 0.07, 'Gain': 13000},
          # 'Qubit': {'Frequency': 4150, 'sigma': 0.07, 'Gain': 3920},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.65 - BaseConfig["res_LO"], 'Gain': 1600,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4120.6, 'sigma': 0.07, 'Gain': 9800},
          # 'Qubit': {'Frequency': 3830.0, 'sigma': 0.07, 'Gain': 5300},
          # 'Qubit': {'Frequency': 3829.9, 'sigma': 0.07, 'Gain': 5200/2},
          # 'Qubit': {'Frequency': 4100, 'sigma': 0.07, 'Gain': 4240},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 1500,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3560.4, 'sigma': 0.07, 'Gain': 18000},
          # 'Qubit': {'Frequency': 3478.3, 'sigma': 0.07, 'Gain': 14000},
          # 'Qubit': {'Frequency': 3558.8, 'sigma': 0.07, 'Gain': 20932},
          # 'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 17000},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7567.9 - BaseConfig["res_LO"], 'Gain': 1500,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3810, 'sigma': 0.07, 'Gain': 4950},
          # 'Qubit': {'Frequency': 3809.3, 'sigma': 0.07, 'Gain': 1140},
          # 'Qubit': {'Frequency': 4050, 'sigma': 0.07, 'Gain': 1140},
          # 'Qubit': {'Frequency': 4117.7, 'sigma': 0.07, 'Gain': 2600},
          # 'Qubit': {'Frequency': 4140.4, 'sigma': 0.07, 'Gain': 1330},
          # 'Qubit': {'Frequency': 4116.3, 'sigma': 0.07, 'Gain': 7000},
          # 'Qubit': {'Frequency': 4117, 'sigma': 0.07, 'Gain': 6990/2},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 700,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3937.3, 'sigma': 0.07, 'Gain': 18640},
          'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 820,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4024.3, 'sigma': 0.07, 'Gain': 6270},
          'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 740,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3998.0, 'sigma': 0.07, 'Gain': 11000},
          'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 800,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 4118.2, 'sigma': 0.07, 'Gain': 10000},
              'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},
    '0': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 800,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 4600, 'sigma': 0.07, 'Gain': 0},
              'Pulse_FF': [-21800, 12000, 14500, -4750, 0, 0, 0, 0]},

}


FF_gain1_expt = -22470
# FF_gain1_expt = 0

FF_gain2_expt = 7000
FF_gain2_expt = 12000

FF_gain3_expt = 17158
# FF_gain3_expt = 0

FF_gain4_expt = -4583
# FF_gain4_expt = 0

FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = -7500
FF_gain2_BS = 22784
FF_gain3_BS = 7000
FF_gain4_BS = -15503
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0

Qubit_Readout = [1,2,3,4]
Qubit_Pulse = ['C']


run_ramp_gain_calibration = False
ff_expt_vs_pop_dict = {'swept_qubit': str(4),
                       'reps': 1000, 'gain_start': -5200, 'gain_end': -4200, 'gain_num_points': 11,
                        'ramp_duration': 3000}





run_ramp_duration_calibration = True
ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(1), 'duration_end': int(3000), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': True}



ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(1), 'duration_end': int(3000), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': False}

# ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(2000), 'duration_end': int(4000), 'duration_num_points': 61,
#                                    'ramp_wait_timesteps': 0,
#                                    'relax_delay': 200, 'double': False}



# can plot populations during and after ramp
run_ramp_population_over_time = False
delay_vs_pop_dict = {'ramp_duration' : 2000, 'ramp_shape': 'cubic',
        'time_start': 0, 'time_end' : 4000, 'time_num_points' : 51, 'reps': 500}


# experiment to measure population shots after adiabatic ramp
run_ramp_population_shots = False
ramp_population_shots_dict = {'reps': 5000, 'ramp_duration': 3000, 'relax_delay': 200}


RampCurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep  time
current_calibration_gain_dict = {'reps': 100, 'swept_index': 1,
                                 't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                 'relax_delay': 100, 'ramp_time': 3000,
                                 'gainStart': 22000, 'gainStop': 23000, 'gainNumPoints': 11,
                                 'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,}

RampCurrentCalibration_OffsetSweep = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time
#


current_calibration_offset_dict = {'reps': 500, 'swept_index': 0,
                                   't_offset':  [-5,0,-7,7,0,0,0,0],
                                   'ramp_time': 2000, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}


current_calibration_offset_dict = {'reps': 2000, 'swept_index': 2,
                                   't_offset':  [-5,1,-6,7,0,0,0,0],
                                   'ramp_time': 3000, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}

current_calibration_offset_dict = {'reps': 4000, 'swept_index': 0,
                                   't_offset':  [-5,1,-6,7,0,0,0,0],
                                   'ramp_time': 3000, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}



run_1D_current_calib = False

current_calibration_dict = {'reps': 500,
                            't_offset':  [-5,0,-14,0,0,0,0,0],
                            'ramp_time': 2000, 'relax_delay': 200,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}

current_calibration_dict = {'reps': 4000,
                            't_offset':  [-5,1,-6,7,0,0,0,0],
                            'ramp_time': 3000, 'relax_delay': 200,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}

# current_calibration_dict = {'reps': 2000,
#                             't_offset': [505, 0, -7, 507, 0, 0, 0, 0],
#                             'ramp_time': 2000, 'relax_delay': 200,
#                             'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}
#
# current_calibration_dict = {'reps': 2000,
#                             't_offset': [505, 0, 493, 7, 0, 0, 0, 0],
#                             'ramp_time': 2000, 'relax_delay': 200,
#                             'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}
#
# current_calibration_dict = {'reps': 2000,
#                             't_offset': [150+5, 0, 150-7, 7, 0, 0, 0, 0],
#                             'ramp_time': 2000, 'relax_delay': 200,
#                             'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}

# current_calibration_dict = {'reps': 2000,
#                             't_offset': [5, 500, 493, 7, 0, 0, 0, 0],
#                             'ramp_time': 2000, 'relax_delay': 200,
#                             'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}


run_1D_current_calib_shots = False

current_calibration_dict_shots = {'reps': 4000,
                                  't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                  'ramp_time': 3000, 'relax_delay': 200,
                                  'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101}



run_current_correlation_measurement = False
current_correlation_measurement_dict = {'reps': 1000,
                                        't_offset':  [0,0,0,0,0,0,0,0],
                                        'ramp_time': 3000, 'relax_delay': 200,
                                        'beamsplitter_time': 75}

ramp_current_calibration_time = False
ramp_current_calibration_time_dict =  {'reps': 500,
                                       't_offset':  [-5,0,93,107,0,0,0,0],
                                       'ramp_time': 2000, 'relax_delay': 200,
                                       'timeStart': 0, 'timeStop': 2500, 'timeNumPoints': 251}

ramp_current_calibration_time_dict =  {'reps': 100,
                                       't_offset':  [5,500,493,7,0,0,0,0],
                                       'ramp_time': 2000, 'relax_delay': 200,
                                       'timeStart': 0, 'timeStop': 3000, 'timeNumPoints': 301}

ramp_current_calibration_time_dict =  {'reps': 500,
                                       't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                       'ramp_time': 3000, 'relax_delay': 100,
                                       'timeStart': 2900, 'timeStop': 3200, 'timeNumPoints': 203}


# run_ramp_oscillations = False
# # Ramp to FFExpts, then jump to FF_BS
# oscillation_single_dict = {'reps': 1000, 'start': int(0), 'step': int(10), 'expts': 200, 'relax_delay': 300,
#                            'ramp_duration': int(20000), 'ramp_shape': 'cubic'}

# This ends the working section of the file.
exec(open("UPDATE_CONFIG.py").read())
exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

if run_ramp_duration_calibration:
    RampDurationVsPopulation(path="RampDurationCalibration", outerFolder=outerFolder,
                      cfg=config | ramp_duration_calibration_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_ramp_gain_calibration:
    FFExptVsPopulation(path="RampGainCalibration", outerFolder=outerFolder,
                      cfg=config | ff_expt_vs_pop_dict, soc=soc, soccfg=soccfg).acquire_display_save(
        plotDisp=True)

if RampCurrentCalibration_GainSweep:
    RampCurrentCalibrationGain(path="RampCurrentCalibration_GainSweep", outerFolder=outerFolder,
                           cfg=config | current_calibration_gain_dict, soc=soc,
                           soccfg=soccfg).acquire_display_save(plotDisp=True)

if RampCurrentCalibration_OffsetSweep:
    if isinstance(current_calibration_offset_dict['swept_index'], int):
        RampCurrentCalibrationOffset(path="RampCurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                             cfg=config | current_calibration_offset_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
    elif isinstance(current_calibration_offset_dict['swept_index'], (list, tuple)):
        RampCurrentCalibrationOffset_Multiple(path="RampCurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                                     cfg=config | current_calibration_offset_dict,
                                     soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_1D_current_calib:
    RampCurrentCalibration1D(path="CurrentCalibration_1D", outerFolder=outerFolder,
                             cfg=config | current_calibration_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if run_1D_current_calib_shots:
    RampCurrentCalibration1DShots(path="CurrentCalibration_1D_Shots", outerFolder=outerFolder,
                             cfg=config | current_calibration_dict_shots,
                             soc=soc, soccfg=soccfg).acquire_save(plotDisp=False, plotSave=False)

if run_ramp_population_over_time:
    TimeVsPopulation(path="TimeVsPopulation", outerFolder=outerFolder,
                             cfg=config | delay_vs_pop_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_current_correlation_measurement:
    CurrentCorrelationMeasurement(path="CurrentCorrelations", outerFolder=outerFolder,
                             cfg=config | current_correlation_measurement_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
if ramp_current_calibration_time:
    RampCurrentCalibrationTime(path="RampCurrentCalibrationTime", outerFolder=outerFolder,
                             cfg=config | ramp_current_calibration_time_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

print(config)