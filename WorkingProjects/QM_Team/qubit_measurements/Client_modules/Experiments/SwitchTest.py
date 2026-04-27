# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTestSwitch import SwitchTest
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone

soc, soccfg = makeProxy()

#### define the saving path

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6730.58, 'Gain': int(6500 / 1.6)},
          'Qubit': {'Frequency': 3124, 'Gain': int(9000), "sigma": 0.03, "flattop_length": None},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q1_6p730//"},
    '2': {#'Readout': {'Frequency': 6842.95, 'Gain': 5000},
          'Readout': {'Frequency': 6843.05, 'Gain': 5000},
          # 'Qubit': {'Frequency': 3108.16, 'Gain': 450}, #0.4 sigma
          'Qubit': {'Frequency': 3108.16, 'Gain': 6400, "sigma": 0.01, "flattop_length": 0.04}, #0.03 sigma
          'QubitPi2_gain': 280,
          'QubitPi2_gain': 3200,
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q2_6p843//"},
    '3': {'Readout': {'Frequency': 6932.3, 'Gain': 5000},
          'Qubit': {'Frequency': 3437.6, 'Gain': 4000, "sigma": 0.03, "flattop_length": None},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q3_6p9325//"},
    '4': {'Readout': {'Frequency': 7214.9, 'Gain': 6000},
          'Qubit': {'Frequency': 3824.2, 'Gain': 3900, "sigma": 0.03, "flattop_length": None},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q4_7p21//"},
    }
# Readout
Qubit_Readout = 2
Qubit_Pulse = 2
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

ConstantTone = False  # determine cavity frequency
RunSwitchTest = True  # determine cavity frequency
switch_rel_params = {"qubit_gain":1000,  'f_ge': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                        "reps": 1000000, 'rounds': 1,
                        'trig_buffer_start': 0.08, "trig_buffer_end": 0.03,
                        'trig_delay': 0.082, 'pulse_start_time': 0,
                     'flattop_length': 0.05, 'sigma': 0.01,
                     'relax_delay': 5} # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse


cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']

trans_config = {
    "reps": 10000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 20,  # [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
}

UpdateConfig = trans_config
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig

if ConstantTone:
    Instance_trans = SingleTone(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SingleTone.acquire(Instance_trans)

if RunSwitchTest:
    config = BaseConfig | switch_rel_params
    Instance_switch = SwitchTest(cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SwitchTest.acquire(Instance_switch)

