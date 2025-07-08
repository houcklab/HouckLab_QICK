# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCalibration_SSMUX import \
    CurrentCalibrationGain, CurrentCalibrationOffset
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

import numpy as np

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.75 - BaseConfig["res_LO"] , 'Gain': 13900,
                      "FF_Gains": [0, -15000, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4077, 'sigma': 0.05, 'Gain': 1120},
          'Pulse_FF': [-5000, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.659 - BaseConfig["res_LO"] , 'Gain': 4000,
                  "FF_Gains": [0, -15000, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4200, 'sigma': 0.05, 'Gain': 2260},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"] , 'Gain': 4000,
                  "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3780, 'sigma': 0.05, 'Gain': 3500},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.1 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4000, 'sigma': 0.05, 'Gain': 3350},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    }

Qubit_Readout = [1]
Qubit_Pulse = [1]
# qubits involved in beamsplitter interaction
Qubit_BS = [1,2]

qubit_to_FF_dict = {1: 1, 2: 2}

# convert Qubit_BS to index based on the order [5, 1, 2, 4]
Qubit_BS_indices = [qubit_to_FF_dict[qubit] for qubit in Qubit_BS]
print(Qubit_BS_indices)

FF_gain1_expt = -5000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0


FF_gain1_BS = -5000
FF_gain2_BS = -15000
FF_gain3_BS = 0
FF_gain4_BS = 0
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0

# swept_qubit_index = 3 #1 indexed

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 1000, 'start': int(0), 'step': int(0.25 * 20), 'expts': 400, 'gainStart': 1500,
                         'gainStop': 2500, 'gainNumPoints': 41, 'relax_delay': 150}


CurrentCalibration = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# t_BS: beam splitter interaction time in units of 1/16 clock cycles
# sweep gain during beamsplitter interaction
current_calibration_dict = {'reps': 1000, 't_evolve': 255,  't_offset': 0,
                            'gainNumPoints': 11, 'relax_delay': 150, "plotDisp": False}

CurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep  time
# current_calibration_gain_dict = {'reps': 1000, 't_evolve': 0, 't_offset': 0, 'relax_delay': 150, "plotDisp": True,
#                             'gainStart': 5000, 'gainStop': 5400, 'gainNumPoints': 11, 'fixed_gain': -20000,
#                             'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,}

CurrentCalibration_OffsetSweep = True
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time

current_calibration_gain_dict = {'swept_index':2,
                                'reps': 200, 't_evolve': 280//4, 't_offset': 0, 'relax_delay': 180, "plotDisp": True,
                            'gainStart': 1500, 'gainStop': 1700, 'gainNumPoints': 6,
                            'timeStart': 1, 'timeStop': 1000, 'timeNumPoints': 51,}

current_calibration_offset_dict = {'reps': 200, 't_evolve': 1875, 'relax_delay': 180, "plotDisp": True,
                                   'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 11,
                                   'offsetStart': -50, 'offsetStop': 50, 'offsetNumPoints': 11}

# current_calibration_offset_dict = {'reps': 100, 't_evolve': 0, 'relax_delay': 200, "plotDisp": True,
#                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 41,
#                                    'offsetStart': -50, 'offsetStop': 50, 'offsetNumPoints': 51}


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


if CurrentCalibration_GainSweep:
    CurrentCalibrationGain(path="CurrentCalibration_GainSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_gain_dict | {"qubit_BS_indices": Qubit_BS_indices}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if CurrentCalibration_OffsetSweep:
    CurrentCalibrationOffset(path="CurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_offset_dict | {"qubit_BS_indices": Qubit_BS_indices}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
