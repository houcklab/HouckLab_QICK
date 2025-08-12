# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCalibration_SSMUX import \
    CurrentCalibrationGain, CurrentCalibrationOffset, CurrentCalibrationSingle
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

import numpy as np

mixer_freq = -1750
BaseConfig["mixer_freq"] = mixer_freq



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




FF_gain1_expt = -22657
FF_gain1_expt = 0
FF_gain2_expt = 7000
FF_gain2_expt = 0
FF_gain3_expt = 16829
# FF_gain3_expt = 0
FF_gain4_expt = -4702
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


Qubit_Readout = [3,4]
Qubit_Pulse = [3]


CurrentCalibration = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# t_BS: beam splitter interaction time in units of 1/16 clock cycles
# sweep gain during beamsplitter interaction
current_calibration_dict = {'reps': 1000, 't_evolve': 225,  't_offset': [0,0,0,-2,0,0,0,0],
                            'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 41}

CurrentCalibration_GainSweep = True
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep time
# current_calibration_gain_dict = {'reps': 1000, 't_evolve': 0, 't_offset': 0, 'relax_delay': 150, "plotDisp": True,
#                             'gainStart': 5000, 'gainStop': 5400, 'gainNumPoints': 11, 'fixed_gain': -20000,
#                             'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,}


current_calibration_gain_dict = {'swept_index': 1,
                                'reps': 100, 't_evolve': 280, 't_offset': [0,0,0,0,0,0,0,0],
                                 'relax_delay': 100, "plotDisp": True,
                                'gainStart': 22300, 'gainStop': 23000, 'gainNumPoints': 11,
                                'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}

current_calibration_gain_dict = {'swept_index': 3,
                                'reps': 100, 't_evolve': 280, 't_offset': [0,0,0,0,0,0,0,0],
                                 'relax_delay': 100, "plotDisp": True,
                                'gainStart': -16000, 'gainStop': -15000, 'gainNumPoints': 11,
                                'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}


CurrentCalibration_OffsetSweep = False
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


