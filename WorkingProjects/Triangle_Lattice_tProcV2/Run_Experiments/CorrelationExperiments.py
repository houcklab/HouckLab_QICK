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
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCorrelationExperiments import PopulationShots, RampPopulationShots, OscillationPopulationShots, RampOscillationPopulationShots

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

Qubit_Readout = [3]
Qubit_Pulse = ['A']


# simple population experiment after pulse state preparation
run_population_shots = True
population_shots_dict = {'reps': 5000, 'relax_delay': 200}

run_oscillation_population_shots = False
oscillation_population_shots_dict = {'reps': 5000,
                                     'start': 1, 'step': 8, 'expts': 201,
                                     'relax_delay': 200, 'res_length':10}



# experiment to measure population shots after adiabatic ramp
run_ramp_population_shots = False
ramp_population_shots_dict = {'reps': 5000, 'ramp_duration': 3000, 'relax_delay': 200}


# adiabatic ramp into beamsplitter current correlation measurement
run_ramp_oscillation_population_shots = False
ramp_oscillation_population_shots_dict = {'reps': 4000,
                                          't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                          'ramp_time': 2000, 'relax_delay': 200,
                                          'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101}

# full current correlation measurement
run_1D_current_calib_shots = False
current_calibration_dict_shots = {'reps': 4000,
                                  't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                  'ramp_time': 3000, 'relax_delay': 200,
                                  'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101}



# This ends the working section of the file.
exec(open("UPDATE_CONFIG.py").read())
exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

if run_population_shots:
    instance = PopulationShots(path="PopulationShots", outerFolder=outerFolder,
                   cfg=config | population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_oscillation_population_shots:
    instance = OscillationPopulationShots(path="OscillationPopulationShots", outerFolder=outerFolder,
                   cfg=config | oscillation_population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_save(plotDisp=False)

if run_ramp_population_shots:
    instance = RampPopulationShots(path="RampPopulationShots", outerFolder=outerFolder,
                   cfg=config | ramp_population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_ramp_oscillation_population_shots:
    instance = RampOscillationPopulationShots(path="RampOscillationPopulationShots", outerFolder=outerFolder,
                                   cfg=config | ramp_oscillation_population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_save(plotDisp=False)


if run_1D_current_calib_shots:
    instance=RampCurrentCalibration1DShots(path="CurrentCalibration_1D_Shots", outerFolder=outerFolder,
                             cfg=config | current_calibration_dict_shots, soc=soc, soccfg=soccfg)
    instance.acquire_save(plotDisp=False, plotSave=False)

print(config)