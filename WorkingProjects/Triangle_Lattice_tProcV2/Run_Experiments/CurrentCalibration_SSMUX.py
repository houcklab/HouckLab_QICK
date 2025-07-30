# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCalibration_SSMUX import \
    CurrentCalibrationGain, CurrentCalibrationOffset, CurrentCalibrationSingle
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

import numpy as np

mixer_freq = -1750
BaseConfig["mixer_freq"] = mixer_freq

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
          'Qubit': {'Frequency': 4101.3, 'sigma': 0.07, 'Gain': 4794},
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
}

FF_gain1_expt = 0
FF_gain2_expt = 20000
FF_gain3_expt = 16829
FF_gain4_expt = -4589
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = -7500
FF_gain2_BS = 22741
FF_gain3_BS = 7000
FF_gain4_BS = -15538
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0

FF_gain1_expt = -22765
FF_gain2_expt = -10000
FF_gain3_expt = 16720
FF_gain4_expt = 10000
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = -30000
FF_gain2_BS = -10000
FF_gain3_BS = 10237
FF_gain4_BS = 10000
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0

FF_gain1_BS = -27000
FF_gain2_BS = -10000
FF_gain3_BS = 13016
FF_gain4_BS = 10000
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0


Qubit_Readout = [1,3]
Qubit_Pulse = [1]


CurrentCalibration = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# t_BS: beam splitter interaction time in units of 1/16 clock cycles
# sweep gain during beamsplitter interaction
current_calibration_dict = {'reps': 1000, 't_evolve': 225,  't_offset': [0,0,0,-2,0,0,0,0],
                            'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 41}

CurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep time
# current_calibration_gain_dict = {'reps': 1000, 't_evolve': 0, 't_offset': 0, 'relax_delay': 150, "plotDisp": True,
#                             'gainStart': 5000, 'gainStop': 5400, 'gainNumPoints': 11, 'fixed_gain': -20000,
#                             'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,}


current_calibration_gain_dict = {'swept_index': 2,
                                'reps': 100, 't_evolve': 233, 't_offset': [0,0,0,0,0,0,0,0],
                                 'relax_delay': 100, "plotDisp": True,
                                'gainStart': 12800, 'gainStop': 13500, 'gainNumPoints': 11,
                                'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}


CurrentCalibration_OffsetSweep = True
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time


current_calibration_offset_dict = {'swept_index': 2, 't_offset': [0,0,0,0,0,0,0,0],
                                   'reps': 100, 't_evolve': 200*3//4, 'relax_delay': 100, "plotDisp": True,
                                   'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}

# current_calibration_offset_dict = {'swept_index': 2, 't_offset': [0,0,0,0,0,0,0,0],
#                                    'reps': 100, 't_evolve': 290*3//4, 'relax_delay': 200, "plotDisp": True,
#                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
#                                    'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}


# This ends the working section of the file.
#----------------------------------------

# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
# Update FF_Qubits dict
exec(open("UPDATE_CONFIG.py").read())
# This ends the translation of the Qubit_Parameters dict
#--------------------------------------------------

exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

print(config)

if CurrentCalibration:
    CurrentCalibrationSingle(path="CurrentCalibration_Single", outerFolder=outerFolder,
                          cfg=config | current_calibration_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if CurrentCalibration_GainSweep:
    CurrentCalibrationGain(path="CurrentCalibration_GainSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if CurrentCalibration_OffsetSweep:
    CurrentCalibrationOffset(path="CurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


