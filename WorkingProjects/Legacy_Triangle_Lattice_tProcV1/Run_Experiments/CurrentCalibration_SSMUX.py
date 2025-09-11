# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Triangle_Lattice_tProcV1.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mCurrentCalibration_SSMUX import CurrentCalibrationOffset, CurrentCalibrationGain
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotFFMUX
import numpy as np

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6978.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 15000,
                      "FF_Gains": [0, 0, 8000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4392.0, 'sigma': 0.05, 'Gain': 14350},
          'Pulse_FF': [0, -10000, 8000, 0]},  # second index
    '2': {'Readout': {'Frequency': 7095.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5400,
                      "FF_Gains": [0, -20000, -2000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4439.0, 'sigma': 0.05, 'Gain': 3160},
          'Pulse_FF':[0, -20000, 0, 0]}, # third index
    '4': {'Readout': {'Frequency': 7269.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 18000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4035.7, 'sigma': 0.05, 'Gain': 9250},
          'Pulse_FF': [0, 0, 0, 0]},
    }

Qubit_Readout = [1]
Qubit_Pulse = [1]
# qubits involved in beamsplitter interaction
Qubit_BS = [1,2]

qubit_to_FF_dict = {1: 1, 2: 2}

# convert Qubit_BS to index based on the order [5, 1, 2, 4]
Qubit_BS_indices = [qubit_to_FF_dict[qubit] for qubit in Qubit_BS]
print(Qubit_BS_indices)

FF_gain1_expt = 0
FF_gain2_expt = 15000
# FF_gain2_expt = -10000
FF_gain3_expt = -4237
# FF_gain3_expt = 8000
FF_gain4_expt = 0


FF_gain1_BS = 0
FF_gain2_BS = -15000
FF_gain3_BS = 1670
FF_gain4_BS = 0

# swept_qubit_index = 3 #1 indexed

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 1000, 'start': int(0), 'step': int(0.25 * 20), 'expts': 400, 'gainStart': 1500,
                         'gainStop': 2500, 'gainNumPoints': 41, 'relax_delay': 150}


CurrentCalibration = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# t_BS: beam splitter interaction time in units of 1/16 clock cycles
# sweep gain during beamsplitter interaction
current_calibration_dict = {'reps': 1000, 't_evolve': 255, 't_BS': 255//2,  't_offset': 0, 'gainStart': 500,
                         'gainStop': 5000, 'gainNumPoints': 11, 'relax_delay': 150, "plotDisp": False}

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
FF_gain1_ro, FF_gain2_ro, FF_gain3_ro, FF_gain4_ro = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1_ro, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse, 'Gain_BS':FF_gain1_BS}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2_ro, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse, 'Gain_BS':FF_gain2_BS}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3_ro, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse, 'Gain_BS':FF_gain3_BS}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4_ro, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse, 'Gain_BS':FF_gain4_BS}

trans_config = {
    "res_gains": [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout],  # [DAC units]
    "res_freqs": [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout], # [MHz] actual frequency is this number + "cavity_LO"
    # "res_gain": Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain'],  # [DAC units]
    "readout_length":Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse],
    "sigma" : Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['sigma']
}
config = BaseConfig | trans_config | qubit_config
config["FF_Qubits"] = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout
config['ro_chs'] = [i for i in range(len(Qubit_Readout))]

# This ends the translation of the Qubit_Parameters dict
#--------------------------------------------------

def characterize_readout(config, Qubit_Readout):
    '''Characterize qubits at the current readout point to return angle, threshold, and confusion_matrix for each.
    trans_config remains the same because we want to know the readout error under the MUXed pulse we will use.'''
    angle, threshold, confusion_matrix = [], [], []

    new_config = config.copy()
    new_config["Shots"] = 2000

    for ro_ind, Qubit in enumerate(Qubit_Readout):
        '''Pulse each at a time, using the QubitParameters Pulse parameters'''
        new_config["qubit_freqs"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Frequency']]
        new_config["qubit_gains"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Gain']]
        new_config['sigma']       =  Qubit_Parameters[str(Qubit)]['Qubit']['sigma']

        FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit)]['Pulse_FF']
        new_config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
        new_config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
        new_config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
        new_config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

        SSExp = SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=new_config, soc=soc, soccfg=soccfg)
        data = SSExp.acquire_display_save(plotDisp=True, block=False, display_indices=[Qubit])

        angle.append(    data['data']['angle'][ro_ind])
        threshold.append(data['data']['threshold'][ro_ind])
        ng_contrast = data['data']['ng_contrast'][ro_ind]
        ne_contrast = data['data']['ne_contrast'][ro_ind]
        conf_mat = np.array([[1 - ng_contrast, ne_contrast],
                             [ng_contrast, 1 - ne_contrast]])
        confusion_matrix.append(conf_mat)

    return angle, threshold, confusion_matrix

angle, threshold, confusion_matrix = characterize_readout(config, Qubit_Readout)
config['angle'], config['threshold'], config['confusion_matrix'] = angle, threshold, confusion_matrix

print(config)


if CurrentCalibration_GainSweep:
    CurrentCalibrationGain(path="CurrentCalibration_GainSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_gain_dict | {"qubit_BS_indices": Qubit_BS_indices}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if CurrentCalibration_OffsetSweep:
    CurrentCalibrationOffset(path="CurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_offset_dict | {"qubit_BS_indices": Qubit_BS_indices}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
