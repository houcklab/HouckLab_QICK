# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import \
    RampCurrentCalibrationGain, RampCurrentCalibration1D, RampCurrentCalibrationOffset
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import RampDurationVsPopulation, \
    FFExptVsPopulation, TimeVsPopulation
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX


import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7120.9 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3509.1, 'sigma': 0.07, 'Gain': 900},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.5 - BaseConfig["res_LO"], 'Gain': 8500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3759.7, 'sigma': 0.07, 'Gain': 1250},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.9 - BaseConfig["res_LO"], 'Gain': 10000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3845.7, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.5 - BaseConfig["res_LO"], 'Gain': 10000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4117.5, 'sigma': 0.07, 'Gain': 2150},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
}



FF_gain1_expt = 14489
# FF_gain1_expt = 0
FF_gain2_expt = -2500
# FF_gain3_expt = -5510
FF_gain3_expt = 0
# FF_gain4_expt = -16763
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 0
FF_gain4_BS = 0
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0


Qubit_Readout = [1,2]
Qubit_Pulse = [2]


run_ramp_gain_calibration = False
ff_expt_vs_pop_dict = {'swept_qubit': str(1),
                       'reps': 1000, 'gain_start': 14000, 'gain_end': 15000, 'gain_num_points': 6,
                        'ramp_duration': 4000}

run_ramp_duration_calibration = False
ramp_duration_calibration_dict = {'reps': 1000, 'duration_start': int(1), 'duration_end': int(1200), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': False}

RampCurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep  time
current_calibration_gain_dict = {'reps': 100, 'swept_index':3,
                                 't_offset':  [0,0,0,0,0,0,0,0], 'relax_delay': 200, 'ramp_time':9000,
                            'gainStart': -4800, 'gainStop': -4200, 'gainNumPoints': 11,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,}

RampCurrentCalibration_OffsetSweep = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time
#
current_calibration_offset_dict = {'reps': 100, 'swept_index':3,
                                   't_offset':  [0,0,0,0,0,0,0,0],
                                   'ramp_time': 9000, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,
                                   'offsetStart': -20, 'offsetStop':20, 'offsetNumPoints':21}

run_1D_current_calib = False
t_offset = [0,0,0,0,0,0,0,0] # For 1D current calib


run_ramp_population_over_time = True
delay_vs_pop_dict = {'ramp_duration' : 9000, 'ramp_shape': 'cubic',
        'time_start': 9000, 'time_end' : 10000, 'time_num_points' : 20, 'reps':1000}

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
    RampCurrentCalibrationGain(path="CurrentCalibration_GainSweep", outerFolder=outerFolder,
                           cfg=config | current_calibration_gain_dict, soc=soc,
                           soccfg=soccfg).acquire_display_save(plotDisp=True)

if RampCurrentCalibration_OffsetSweep:
    RampCurrentCalibrationOffset(path="CurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                             cfg=config | current_calibration_offset_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_1D_current_calib:
    RampCurrentCalibration1D(path="CurrentCalibration_1D", outerFolder=outerFolder,
                             cfg=config | current_calibration_offset_dict | {"t_offset":t_offset},
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_ramp_population_over_time:
    TimeVsPopulation(path="TimeVsPopulation", outerFolder=outerFolder,
                             cfg=config | delay_vs_pop_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

print(config)