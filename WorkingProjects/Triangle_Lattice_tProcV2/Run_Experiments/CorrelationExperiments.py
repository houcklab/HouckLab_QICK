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

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.8 - BaseConfig["res_LO"], 'Gain': 5400,
                      "FF_Gains": [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75, 'cavmin': True},
          'Qubit': {'Frequency': 4086.3, 'sigma': 0.07, 'Gain': 2000},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7078.3 - BaseConfig["res_LO"], 'Gain': 5000,
                      "FF_Gains" : [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75, 'cavmin': True},
          'Qubit': {'Frequency': 4399, 'sigma': 0.07, 'Gain': 2570},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3560.7, 'sigma': 0.07, 'Gain': 9500},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.0 - BaseConfig["res_LO"], 'Gain': 6500,
                      "FF_Gains": [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3905, 'sigma': 0.07, 'Gain': 2820},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7122.2 - BaseConfig["res_LO"], 'Gain': 5000,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75,
                      'cavmin': True},
          'Qubit': {'Frequency': 4393.6, 'sigma': 0.07, 'Gain': 3600},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7077.6 - BaseConfig["res_LO"], 'Gain': 3200,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75,
                      'cavmin': True},
          'Qubit': {'Frequency': 4120.9, 'sigma': 0.07, 'Gain': 3500},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7567.9 - BaseConfig["res_LO"], 'Gain': 1500,
                  "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
      'Qubit': {'Frequency': 3809.7, 'sigma': 0.07, 'Gain': 2000},
      'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 1000,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3560.3, 'sigma': 0.07, 'Gain': 9500},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},

}


FF_gain1_expt = -22542
FF_gain1_expt = 0

FF_gain2_expt = 7000
# FF_gain2_expt = 12000

FF_gain3_expt = 17325
FF_gain3_expt = 0

FF_gain4_expt = -4460
# FF_gain4_expt = 0

FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = -7500
FF_gain2_BS = 22555
FF_gain3_BS = 7000
FF_gain4_BS = -15505
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0

Qubit_Readout = [1,2,3,4]
Qubit_Pulse = ['C']



# Josh parameters
Readout_FF = [4191, 30177, -26187, -7760, 0, 0, 0, 0]
# (4100.0, 4397.0, 3460.8, 3800.0, 4378.9, 4358.5, 4312.9, 4405.3)
Expt_FF = np.array([2625, 2580, 2532, 2590, 0, 0, 0, 0])
# All at 4000.0
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.8 - BaseConfig["res_LO"], 'Gain': 4000,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4100.3, 'sigma': 0.07, 'Gain': 3250},
          'Pulse_FF': Readout_FF},
    '2': {'Readout': {'Frequency': 7078.35 - BaseConfig["res_LO"], 'Gain': 7300,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4398.7, 'sigma': 0.07, 'Gain': 3030},
          'Pulse_FF': Readout_FF},
    '3': {'Readout': {'Frequency': 7510.45 - BaseConfig["res_LO"], 'Gain': 5300,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3574.0, 'sigma': 0.07, 'Gain': 14500},
          'Pulse_FF': [4191, 30177, -26187 + 10000, -7760, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.05 - BaseConfig["res_LO"], 'Gain': 5300,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3798.8, 'sigma': 0.07, 'Gain': 2350},
          'Pulse_FF': Readout_FF},
    # Resonant points. +- 4000 FF gain ~ 100 MHz
    '1H': {'Qubit': {'Frequency': 4134.67, 'sigma': 0.07, 'Gain': 4000},
           'Pulse_FF': Expt_FF + [3000,0,0,0,0,0,0,0]},
    '2H': {'Qubit': {'Frequency': 4131.6, 'sigma': 0.07, 'Gain': 2660},
           'Pulse_FF': Expt_FF + [0,3000,0,0,0,0,0,0]},
    '3H': {'Qubit': {'Frequency': 4136.0, 'sigma': 0.07, 'Gain': 4150},
           'Pulse_FF': Expt_FF + [0,0,3000,0,0,0,0,0]},
    '4H': {'Qubit': {'Frequency': 4134.8, 'sigma': 0.07, 'Gain': 3250},
           'Pulse_FF': Expt_FF + [0,0,0,3000,0,0,0,0]},

    # Ramp remaining qubits up rather than ramping excitation down
    '1H0': {'Qubit': {'Frequency': 4066.7, 'sigma': 0.07, 'Gain': 3200},
            'Pulse_FF': Expt_FF + [0, -3000, -3000, -3000, -3000, 0, 0, 0]},
    '2H0': {'Qubit': {'Frequency': 4066.4, 'sigma': 0.07, 'Gain': 2000},
            'Pulse_FF': Expt_FF + [-3000, 0, -3000, -3000, -3000, 0, 0, 0]},
    '3H0': {'Qubit': {'Frequency': 4066.7, 'sigma': 0.07, 'Gain': 4100},
            'Pulse_FF': Expt_FF + [-3000, -3000, 0, -3000, -3000, 0, 0, 0]},
    '4H0': {'Qubit': {'Frequency': 4065.9, 'sigma': 0.07, 'Gain': 2500},
            'Pulse_FF': Expt_FF + [-3000, -3000, -3000, 0, -3000, 0, 0, 0]},

    '2HH': {'Qubit': {'Frequency': 4130.4, 'sigma': 0.07, 'Gain': 2660},
            'Pulse_FF': Expt_FF + [-3000, +3000, +0, -3000, 0, 0, 0, 0]},
    '3HH': {'Qubit': {'Frequency': 4066.0, 'sigma': 0.07, 'Gain': 10000},
            'Pulse_FF': Expt_FF + [-3000, +3000, +0, -3000, 0, 0, 0, 0]},

    # Resonant points. Guess: [0,0,0,0]
    '1R': {'Qubit': {'Frequency': 4065, 'sigma': 0.07, 'Gain': 2388},
           'Pulse_FF': [0, 0 - 4000, 0 - 4000, 0 - 4000, 0, 0, 0, 0]},
    '2R': {'Qubit': {'Frequency': 4065, 'sigma': 0.07, 'Gain': 3200},
           'Pulse_FF': [0 - 4000, 0, 0 - 4000, 0 - 4000, 0, 0, 0, 0]},
    '3R': {'Qubit': {'Frequency': 4065, 'sigma': 0.07, 'Gain': 5000},
           'Pulse_FF': [0 - 4000, 0 - 4000, 0, 0 - 4000, 0, 0, 0, 0]},
    '4R': {'Qubit': {'Frequency': 4065, 'sigma': 0.07, 'Gain': 4200},
           'Pulse_FF': [0 - 4000, 0 - 4000, 0 - 4000, 0, 0, 0, 0, 0]},
}

# [-56, -260, -41, 45, 0, 0, 0, 0]
FF_gain1_expt = Expt_FF[0]  # resonance
FF_gain2_expt = Expt_FF[1] # resonance
FF_gain3_expt = Expt_FF[2] - 6000# resonance
FF_gain4_expt = Expt_FF[3] - 6000# resonance
# FF_gain1_expt = -8000
# FF_gain2_expt = -8000
# FF_gain3_expt = -8000
# FF_gain4_expt = -8000
FF_gain5_expt =  0
FF_gain6_expt =  0
FF_gain7_expt =  0
FF_gain8_expt =  0

FF_gain1_BS =  13069  # 4265.0
FF_gain2_BS =  13299  # 4265.0
FF_gain3_BS =  -4885  # 3865.0
FF_gain4_BS =  -5251  # 3865.0
FF_gain5_BS =      0  # 4378.9
FF_gain6_BS =      0  # 4358.5
FF_gain7_BS =      0  # 4312.9
FF_gain8_BS =      0  # 4405.3



Qubit_Readout = [1,2]
Qubit_Pulse = ['1H']


# simple population experiment after pulse state preparation
run_population_shots = False
population_shots_dict = {'reps': 5000, 'relax_delay': 200}

run_oscillation_population_shots = False
oscillation_population_shots_dict = {'reps': 5000,
                                     'start': 1, 'step': 8, 'expts': 201,
                                     'relax_delay': 200, 'res_length':10}



# experiment to measure population shots after adiabatic ramp
run_ramp_population_shots = True
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