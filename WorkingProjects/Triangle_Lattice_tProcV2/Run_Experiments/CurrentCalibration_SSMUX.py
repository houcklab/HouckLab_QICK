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
}


Qubit_Readout = [1,2]
Qubit_Pulse = [2]

FF_gain1_expt = -20622
FF_gain2_expt = -4200
FF_gain3_expt = 4254
FF_gain3_expt = -10000
FF_gain4_expt = -11705
FF_gain4_expt = -31705
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = -9484
FF_gain2_BS = 7000
FF_gain3_BS = 4345
FF_gain3_BS = -10000
FF_gain4_BS = -11743
FF_gain4_BS = -31705
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0



Oscillation_Gain = False
oscillation_gain_dict = {'reps': 1000, 'start': int(0), 'step': int(0.25 * 20), 'expts': 101, 'gainStart': -18700,
                         'gainStop': -17700, 'gainNumPoints': 21, 'relax_delay': 150}


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


current_calibration_gain_dict = {'swept_index': 0,
                                'reps': 100, 't_evolve': 270, 't_offset': [0,0,0,0,0,0,0,0],
                                 'relax_delay': 200, "plotDisp": True,
                                'gainStart': -10000, 'gainStop': -9000, 'gainNumPoints': 11,
                                'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}


CurrentCalibration_OffsetSweep = True
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time


current_calibration_offset_dict = {'swept_index': 0, 't_offset': [0,0,0,0,0,0,0,0],
                                   'reps': 100, 't_evolve': 240*3//4, 'relax_delay': 200, "plotDisp": True,
                                   'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}


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


