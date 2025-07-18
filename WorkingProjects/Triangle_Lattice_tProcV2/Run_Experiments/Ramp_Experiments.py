# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import \
    RampCurrentCalibrationGain, RampCurrentCalibration1D,RampCurrentCalibration1DShots, RampCurrentCalibrationOffset
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import RampDurationVsPopulation, \
    FFExptVsPopulation, TimeVsPopulation
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCorrelations import CurrentCorrelationMeasurement

import numpy as np


Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.9 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4213, 'sigma': 0.07, 'Gain': 2700},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.55 - BaseConfig["res_LO"], 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4013, 'sigma': 0.07, 'Gain': 2630},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2630},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3609, 'sigma': 0.07, 'Gain': 10650},
          # 'Qubit': {'Frequency': 3700, 'sigma': 0.07, 'Gain': 10650},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3812.9, 'sigma': 0.07, 'Gain': 2770},
          # 'Qubit': {'Frequency': 3807, 'sigma': 0.07, 'Gain': 5300},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7121.9 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3801, 'sigma': 0.07, 'Gain': 2670},
          'Pulse_FF': [-17000, -11500, 1000, -4500, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7077.55 - BaseConfig["res_LO"], 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3735, 'sigma': 0.07, 'Gain': 5300},
          'Pulse_FF': [-17000, -11500, 1000, -4500, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3634, 'sigma': 0.07, 'Gain': 15050},
          'Pulse_FF': [-17000, -11500, 1000, -4500, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7568 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3700, 'sigma': 0.07, 'Gain': 4210},
          'Pulse_FF': [-17000, -11500, 1000, -4500, 0, 0, 0, 0]},
}

FF_gain1_expt = -21317
FF_gain2_expt = -13160
FF_gain3_expt = 3842
FF_gain4_expt = -4500
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = -15000
FF_gain2_BS = -6646
FF_gain3_BS = 3842
FF_gain4_BS = -4500
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0


Qubit_Readout = [1,3,2,4]
Qubit_Pulse = ['D']


run_ramp_gain_calibration = False
ff_expt_vs_pop_dict = {'swept_qubit': str(1),
                       'reps': 1000, 'gain_start': -22000, 'gain_end': -20500, 'gain_num_points': 11,
                        'ramp_duration': 3000}

run_ramp_duration_calibration = False
ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(1), 'duration_end': int(3000), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': True}


ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(2000), 'duration_end': int(6000), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': False}



# can plot populations during and after ramp
run_ramp_population_over_time = False
delay_vs_pop_dict = {'ramp_duration' : 2000, 'ramp_shape': 'cubic',
        'time_start': 0, 'time_end' : 8000, 'time_num_points' : 51, 'reps': 500}


RampCurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep  time
current_calibration_gain_dict = {'reps': 100, 'swept_index': 3,
                                 't_offset':  [0,0,0,0,0,0,0,0], 'relax_delay': 200, 'ramp_time': 2000,
                            'gainStart': 0, 'gainStop': 5000, 'gainNumPoints': 11,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,}

RampCurrentCalibration_OffsetSweep = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time
#
current_calibration_offset_dict = {'reps': 100, 'swept_index':3,
                                   't_offset':  [0,0,0,-2,0,0,0,0],
                                   'ramp_time': 4500, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,
                                   'offsetStart': -20, 'offsetStop':20, 'offsetNumPoints':11}


run_1D_current_calib = False

current_calibration_dict = {'reps': 100,
                            't_offset':  [0,0,0,0,0,0,0,0],
                            'ramp_time': 3000, 'relax_delay': 200,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}


run_1D_current_calib_shots = True

current_calibration_dict_shots = {'reps': 1000,
                                  't_offset':  [0,0,0,0,0,0,0,0],
                                  'ramp_time': 3000, 'relax_delay': 200,
                                  'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}


run_current_correlation_measurement = False
current_correlation_measurement_dict = {'reps': 1000,
                                        't_offset':  [0,0,0,0,0,0,0,0],
                                        'ramp_time': 3000, 'relax_delay': 200,
                                        'beamsplitter_time': 75}

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

print(config)