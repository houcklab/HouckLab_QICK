# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCalibration_SSMUX import \
    CurrentCalibrationGain, CurrentCalibrationOffset, CurrentCalibrationSingle
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

import numpy as np

mixer_freq = -1750
BaseConfig["mixer_freq"] = mixer_freq


# Josh parameters
Readout_FF = [5660, 26575, -17231, -5017, 0, 0, 0, 0]
# Readout_FF = [56, 26575, -314, -241, 0, 0, 0, 0]
# (4088.0, 4380.0, 3520.0, 3820.0, 3500.9, 3501.5, 3441.8, 3506.0)

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.8, 'Gain': 4200,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4084.7, 'sigma': 0.07, 'Gain': 2450},
          'Pulse_FF': Readout_FF},
    '2': {'Readout': {'Frequency': 7078.3, 'Gain': 5200,
                      "FF_Gains": Readout_FF, "Readout_Time": 3.5, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 4379.2, 'sigma': 0.07, 'Gain': 3200},
          'Pulse_FF': Readout_FF},
    '3': {'Readout': {'Frequency': 7510.55, 'Gain': 3800,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3626.6, 'sigma': 0.07, 'Gain': 5250},
          'Pulse_FF': [5660, 26575, -17231 + 5000, -5017, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 6000,
                      "FF_Gains": Readout_FF, "Readout_Time": 3.5, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 3824.7, 'sigma': 0.07, 'Gain': 3260},
          'Pulse_FF': Readout_FF},
    # Resonant points. Guess: [0,0,0,0]
    '1H': {'Qubit': {'Frequency': 4048.4, 'sigma': 0.07, 'Gain': 3000},
           'Pulse_FF': [56 + 4000, 5, -314, -241, 0, 0, 0, 0]},
    '2H': {'Qubit': {'Frequency': 4043.8, 'sigma': 0.07, 'Gain': 3080},
           'Pulse_FF': [56, 5 + 4000, -314, -241, 0, 0, 0, 0]},
    '3H': {'Qubit': {'Frequency': 3949.6, 'sigma': 0.07, 'Gain': 4220},
           'Pulse_FF': [139- 8000, 160 - 8000, -310, -189 - 4000, 0, 0, 0, 0]},
    '4H': {'Qubit': {'Frequency': 3846.1, 'sigma': 0.07, 'Gain': 4500},
           'Pulse_FF': [139 - 8000, 160 - 8000, -310, -189 - 4000, 0, 0, 0, 0]},
    '1L': {'Qubit': {'Frequency': 3844.9, 'sigma': 0.07, 'Gain': 4700},
           'Pulse_FF': [56 - 4000, 5, -314, -241, 0, 0, 0, 0]},

    '1HH': {'Qubit': {'Frequency': 4050.3, 'sigma': 0.07, 'Gain': 3000},
            'Pulse_FF': [139 + 4000, 160, -310, -184 + 2000, 0, 0, 0, 0]},
    '4HH': {'Qubit': {'Frequency': 4001.3, 'sigma': 0.07, 'Gain': 3400},
            'Pulse_FF': [139 + 4000, 160, -310, -184 + 2000, 0, 0, 0, 0]},


    '2below': {'Qubit': {'Frequency': 3848, 'sigma': 0.07, 'Gain': 4140},
           'Pulse_FF': [75, 64 - 4000, -10000, -241, 0, 0, 0, 0]},
    '3below': {'Qubit': {'Frequency': 3848, 'sigma': 0.07, 'Gain': 4140},
           'Pulse_FF': [75, 64 - 4000, -10000, -241, 0, 0, 0, 0]},
    # Resonant points. Guess: [0,0,0,0]
    '1R': {'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 2388},
           'Pulse_FF': [75, 64 - 4000, -131 + 4000, -314 - 4000, 0, 0, 0, 0]},
    '2R': {'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 3200},
           'Pulse_FF': [75 - 4000, 64, -131 + 4000, -314 - 4000, 0, 0, 0, 0]},
    '3R': {'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 5000},
           'Pulse_FF': [75 - 4000, 64 - 4000, -314, -314 - 4000, 0, 0, 0, 0]},
    '4R': {'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 3600},
           'Pulse_FF': [75 + 4000, 64 - 4000, -131 - 4000, -241, 0, 0, 0, 0]},
}

FF_gain1_expt =  139 # resonance
FF_gain1_expt =  139 + 4000 # pulse
FF_gain1_expt =  Readout_FF[0] # readout


FF_gain2_expt =  160 # resonance
FF_gain2_expt =  160 - 4000 # pulse
FF_gain2_expt =  Readout_FF[1] # readout

FF_gain3_expt = -310 # resonance
FF_gain3_expt = -100 # Q4 resonance
# FF_gain3_expt = -310 - 4000 # pulse
# FF_gain3_expt =  Readout_FF[2] # readout

FF_gain4_expt = -184 # resonance
# FF_gain4_expt = -184 + 2000 # pulse
# FF_gain4_expt =  Readout_FF[3] # readout


FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

# FF_gain1_BS =  17375  # 4300.0
# FF_gain2_BS =  17930  # 4300.0
FF_gain1_BS =   139 + 1000 - 9000  # 4125.0
FF_gain2_BS =   160 + 1000 - 9000  # 4125.0

# FF_gain3_BS =  -310  # 3700.0
# FF_gain4_BS =  -184  # 3700.0
FF_gain3_BS =  -8900  # 3700.0
FF_gain4_BS =  -9834  # 3700.0
FF_gain4_BS =  -9550  # 3700.0
# FF_gain3_BS =  -4303  # 3825.0
# FF_gain4_BS =  -4823  # 3825.0
FF_gain5_BS =      0  # 3500.9
FF_gain6_BS =      0  # 3501.5
FF_gain7_BS =      0  # 3441.8
FF_gain8_BS =      0  # 3506.0


Qubit_Readout = [3,4]
Qubit_Pulse = [4]


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


# current_calibration_gain_dict = {'swept_index': 1,
#                                 'reps': 100, 't_evolve': 280, 't_offset': [0,0,0,0,0,0,0,0],
#                                  'relax_delay': 100, "plotDisp": True,
#                                 'gainStart': 22300, 'gainStop': 23000, 'gainNumPoints': 11,
#                                 'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}

current_calibration_gain_dict = {'swept_index': 3,
                                'reps': 100, 't_evolve': 250, 't_offset': [0,0,0,0,0,0,0,0],
                                 'relax_delay': 100, "plotDisp": True,
                                'gainStart': -10000, 'gainStop': -9200, 'gainNumPoints': 11,
                                'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}


CurrentCalibration_OffsetSweep = True
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time


# current_calibration_offset_dict = {'swept_index': 2, 't_offset': [0,0,0,0,0,0,0,0],
#                                    'reps': 100, 't_evolve': 200*3//4, 'relax_delay': 100, "plotDisp": True,
#                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
#                                    'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}

current_calibration_offset_dict = {'swept_index': 3, 't_offset': [0,0,0,0,0,0,0,0],
                                   'reps': 100, 't_evolve': 321*3//4, 'relax_delay': 200, "plotDisp": True,
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


