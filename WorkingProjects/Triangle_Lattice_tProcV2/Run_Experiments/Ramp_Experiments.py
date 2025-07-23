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
    '1': {'Readout': {'Frequency': 7122 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4188.4, 'sigma': 0.07, 'Gain': 3450},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.4 - BaseConfig["res_LO"], 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3796.8, 'sigma': 0.07, 'Gain': 2470},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3598, 'sigma': 0.07, 'Gain': 11130},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.5 - BaseConfig["res_LO"], 'Gain': 8100,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4001.1, 'sigma': 0.07, 'Gain': 6850},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3799.3, 'sigma': 0.07, 'Gain': 3250},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7077.5 - BaseConfig["res_LO"], 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3700.9, 'sigma': 0.07, 'Gain': 4500},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3647.2, 'sigma': 0.07, 'Gain': 11850},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7568.5 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3755.6, 'sigma': 0.07, 'Gain': 4226},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'BD': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3800.6, 'sigma': 0.07, 'Gain': 2930},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'CD': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3799.3, 'sigma': 0.07, 'Gain': 3250},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
}

FF_gain1_expt = -20622
FF_gain2_expt = -4200
FF_gain3_expt = 4254
FF_gain4_expt = -11705
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = -2005
FF_gain2_BS = 15000
FF_gain3_BS = 4168
FF_gain4_BS = -11743
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0


Qubit_Readout = [1,2,3,4]
Qubit_Pulse = ['D']


run_ramp_gain_calibration = False
ff_expt_vs_pop_dict = {'swept_qubit': str(3),
                       'reps': 1000, 'gain_start': 3700, 'gain_end': 4700, 'gain_num_points': 11,
                        'ramp_duration': 3000}

run_ramp_duration_calibration = False
ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(1), 'duration_end': int(3000), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': True}

#
ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(1), 'duration_end': int(3000), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': False}



# can plot populations during and after ramp
run_ramp_population_over_time = False
delay_vs_pop_dict = {'ramp_duration' : 2000, 'ramp_shape': 'cubic',
        'time_start': 0, 'time_end' : 8000, 'time_num_points' : 51, 'reps': 500}


RampCurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep  time
current_calibration_gain_dict = {'reps': 100, 'swept_index': 0,
                                 't_offset':  [0,0,0,0,0,0,0,0], 'relax_delay': 200, 'ramp_time': 2000,
                            'gainStart': -2500, 'gainStop': 1500, 'gainNumPoints': 11,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,}

RampCurrentCalibration_OffsetSweep = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time
#
current_calibration_offset_dict = {'reps': 100, 'swept_index': 3,
                                   't_offset':  [-4,0,0,0,0,0,0,0],
                                   'ramp_time': 4500, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,
                                   'offsetStart': -20, 'offsetStop':20, 'offsetNumPoints': 51}




run_1D_current_calib = False

current_calibration_dict = {'reps': 100,
                            't_offset':  [-4,0,0,0,0,0,0,0],
                            'ramp_time': 3000, 'relax_delay': 200,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}


run_1D_current_calib_shots = True

current_calibration_dict_shots = {'reps': 4000,
                                  't_offset':  [-4,0,0,0,0,0,0,0],
                                  'ramp_time': 3000, 'relax_delay': 200,
                                  'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 201}


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