# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_SSMUX import WalkFFSSMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_GainSweepSSMUX import Oscillations_Gain_SSMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mCurrentCalibration_SSMUX import \
    CurrentCalibration_SSMUX, CurrentCalibration_OffsetSweep_SSMUX, CurrentCalibration_GainSweep_SSMUX

# yoko69.rampstep = 0.0005
# yoko70.rampstep = 0.0005
# yoko71.rampstep = 0.0005
# yoko72.rampstep = 0.0005
#
# # yoko69.SetVoltage(-0.0479)
# # yoko70.SetVoltage(0.0904)
# # yoko71.SetVoltage(-0.1262)
# # yoko72.SetVoltage(0.0051)
#
# yoko69.SetVoltage(-0.1368)
# yoko70.SetVoltage(-0.1542)
# yoko71.SetVoltage(-0.2343)
# yoko72.SetVoltage(0.1055)

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7321.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 3,
                      "ADC_Offset": 0.5},
          'Qubit': {'Frequency': 4789.7, 'Gain': 800},
          'Pulse_FF': [0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7269.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4668.3, 'Gain': 8700},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7524.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3,},
          'Qubit': {'Frequency': 4488, 'Gain': 10900},
          'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7305.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5130,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4625.1, 'Gain': 28000},
          'Pulse_FF': [0, 0, 0, 0]}
    }



Qubit_Readout = [5]
Qubit_Pulse = [5]
# qubits involved in beamsplitter interaction
Qubit_BS = [3, 5]

qubit_to_FF_dict = {5: 0, 2: 1, 3: 2, 4: 3}

# convert Qubit_BS to index based on the order [5, 2, 3, 4]
Qubit_BS_indices = [qubit_to_FF_dict[qubit] for qubit in Qubit_BS]
print(Qubit_BS_indices)

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 2020
FF_gain4_expt = 0

swept_qubit_index = 3 #1 indexed

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 1000, 'start': int(0), 'step': int(0.25 * 20), 'expts': 400, 'gainStart': 1500,
                         'gainStop': 2500, 'gainNumPoints': 41, 'relax_delay': 150}


CurrentCalibration = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# t_BS: beam splitter interaction time in units of 1/16 clock cycles
current_calibration_dict = {'reps': 2000, 't_evolve': 125, 't_BS': 125,  't_offset': 0, 'gainStart': 500,
                         'gainStop': 5000, 'gainNumPoints': 21, 'relax_delay': 150, "plotDisp": False}

CurrentCalibration_GainSweep = True
current_calibration_gain_dict = {'reps': 1000, 't_evolve': 350//2, 't_offset': 0, 'relax_delay': 150, "plotDisp": True,
                            'gainStart': 0, 'gainStop': 5000, 'gainNumPoints': 21, 'fixed_gain': 3000,
                            'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,}

CurrentCalibration_OffsetSweep = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# t_BS: beam splitter interaction time in units of 1/16 clock cycles
current_calibration_offset_dict = {'reps': 2000, 't_evolve': 350, 't_BS': 350, 'relax_delay': 150, "plotDisp": True,
                            'gainStart': 0, 'gainStop': 5000, 'gainNumPoints': 41,
                            'offsetStart': -100, 'offsetStop': 100, 'offsetNumPoints': 11,}
current_calibration_offset_dict = {'reps': 1000, 't_evolve': 350, 't_BS': 350, 'relax_delay': 150, "plotDisp": True,
                            'gainStart': 0, 'gainStop': 5000, 'gainNumPoints': 21,
                            'offsetStart': -100, 'offsetStop': 100, 'offsetNumPoints': 3,}

SS_params_2States = {"ground": 0, 'excited': 1, "Shots": 4000, "Readout_Time": 2.5, "ADC_Offset": 0.3}

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']["FF_Gains"]


cavity_gain = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain']
# resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
# qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']

resonator_frequencies = [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout]
gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

qubit_gains = [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse]
qubit_frequency_centers = [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 1000,
    # "qubit_freq": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    "qubit_length": soc.us2cycles(40),
    ##### define spec slice experiment parameters
    "SpecSpan": 12,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 60,  ### number of points in the transmission frequecny
}
UpdateConfig_FF = {
    "ff_pulse_style": "const",  # --Fixed
    "ff_freq": 0,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1,  ### MHz, span will be center+/- this parameter
    "relax_delay": 300,  ### in units us
}

UpdateConfig_transmission = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    "pulse_gain": cavity_gain,  # [DAC units]
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "pulse_gains": gains,  # [DAC units]
    "pulse_freqs": resonator_frequencies,
    ##### define tranmission experiment parameters
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60,  ### number of points in the transmission frequecny
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout


#### update the qubit and cavity attenuation

config["rounds"] = 1
config["sigma"] = 0.007

config["shots"] = 2000
config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Readout]
config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Readout]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout[0])]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

config["readout_length"] = SS_params_2States["Readout_Time"]  # us (length of the pulse applied)
config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]
print(config["pulse_freqs"])

print('!!!')
print(config)
Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                         soc=soc, soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
data_SingleShotProgram = Instance_SingleShotProgram.acquire()

angle, threshold = Instance_SingleShotProgram.angle, Instance_SingleShotProgram.threshold
print(Instance_SingleShotProgram.angle,Instance_SingleShotProgram.threshold)

# data_SingleShotProgram = SingleShotProgramFFMUX.analyze(Instance_SingleShotProgram, data_SingleShotProgram)

SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)


config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse]
config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

if Oscillation_Gain:
    config["reps"] = oscillation_gain_dict['reps']
    expt_cfg = {"start": oscillation_gain_dict['start'], "step": oscillation_gain_dict['step'],
                "expts": oscillation_gain_dict['expts'],
                "gainStart": oscillation_gain_dict['gainStart'],
                "gainStop": oscillation_gain_dict['gainStop'], "gainNumPoints": oscillation_gain_dict['gainNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_gain_dict['relax_delay'],
                }
    config['IDataArray'] = [1, None, None, None]
    # config['IDataArray'] = [None, None, None, None]

    config = config | expt_cfg
    print(config["FF_Qubits"])


    iOscillations = Oscillations_Gain_SSMUX(path="QubitOscillations_GainSweepMUX", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = Oscillations_Gain_SSMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    Oscillations_Gain_SSMUX.save_data(iOscillations, dOscillations)
    Oscillations_Gain_SSMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)


if CurrentCalibration:
    # current_calibration_dict = {'reps': 1000, 't_evolve': (2.32 / 16) * 125, 'gainStart': 500,
    #                             'gainStop': 1500, 'gainNumPoints': 21, 'relax_delay': 150}

    config["reps"] = current_calibration_dict['reps']
    expt_cfg = {"t_evolve": current_calibration_dict["t_evolve"], "t_BS": current_calibration_dict["t_BS"], "t_offset": current_calibration_dict["t_offset"], "gainStart": current_calibration_dict['gainStart'],
                "gainStop": current_calibration_dict['gainStop'], "gainNumPoints": current_calibration_dict['gainNumPoints'],
                "qubit_BS_indices": Qubit_BS_indices, "relax_delay": current_calibration_dict['relax_delay'],
                }
    config['IDataArray'] = [1, None, None, None]
    config['IDataArrayBS'] = [1, None, None, None]
    # config['IDataArray'] = [None, None, None, None]

    config = config | expt_cfg


    current_calibration = CurrentCalibration_SSMUX(path="CurrentCalibration", cfg=config, soc=soc, soccfg=soccfg,
                                            outerFolder=outerFolder)
    current_calibration_data = current_calibration.acquire(angle=angle, threshold=threshold, plotDisp=current_calibration_dict["plotDisp"])
    current_calibration.save_data(current_calibration_data)
    current_calibration.display(current_calibration_data, plotDisp=True, figNum=2)


if CurrentCalibration_GainSweep:
    # current_calibration_dict = {'reps': 1000, 't_evolve': (2.32 / 16) * 125, 'gainStart': 500,
    #                             'gainStop': 1500, 'gainNumPoints': 21, 'relax_delay': 150}

    config["reps"] = current_calibration_gain_dict['reps']
    expt_cfg = {"t_evolve": current_calibration_gain_dict["t_evolve"], "t_offset": current_calibration_gain_dict["t_offset"], "gainStart": current_calibration_gain_dict['gainStart'],
                "gainStop": current_calibration_gain_dict['gainStop'], "gainNumPoints": current_calibration_gain_dict['gainNumPoints'], "timeStart": current_calibration_gain_dict['timeStart'],
                "timeStop": current_calibration_gain_dict['timeStop'], "timeNumPoints": current_calibration_gain_dict['timeNumPoints'], "fixed_gain": current_calibration_gain_dict['fixed_gain'],
                "qubit_BS_indices": Qubit_BS_indices, "relax_delay": current_calibration_gain_dict['relax_delay'],
                }
    config['IDataArray'] = [1, None, None, None]
    config['IDataArrayBS'] = [1, None, None, None]
    # config['IDataArray'] = [None, None, None, None]

    config = config | expt_cfg


    current_calibration = CurrentCalibration_GainSweep_SSMUX(path="CurrentCalibration_GainSweep", cfg=config, soc=soc, soccfg=soccfg,
                                            outerFolder=outerFolder)
    current_calibration_data = current_calibration.acquire(angle=angle, threshold=threshold, plotDisp=current_calibration_gain_dict["plotDisp"])
    current_calibration.save_data(current_calibration_data)
    current_calibration.display(current_calibration_data, plotDisp=True, figNum=2)

if CurrentCalibration_OffsetSweep:
    # current_calibration_offset_dict = {'reps': 1000, 't_evolve': (2.32 / 16) * 125, 'gainStart': 500,
    #                             'gainStop': 1500, 'gainNumPoints': 21, 'relax_delay': 150}

    config["reps"] = current_calibration_offset_dict['reps']
    expt_cfg = {"t_evolve": current_calibration_offset_dict["t_evolve"], "t_BS": current_calibration_offset_dict["t_BS"], "gainStart": current_calibration_offset_dict['gainStart'],
                "gainStop": current_calibration_offset_dict['gainStop'], "gainNumPoints": current_calibration_offset_dict['gainNumPoints'], "offsetStart": current_calibration_offset_dict['offsetStart'],
                "offsetStop": current_calibration_offset_dict['offsetStop'], "offsetNumPoints": current_calibration_offset_dict['offsetNumPoints'],
                "qubit_BS_indices": Qubit_BS_indices, "relax_delay": current_calibration_offset_dict['relax_delay'],
                }
    config['IDataArray'] = [1, None, None, None]
    config['IDataArrayBS'] = [1, None, None, None]
    # config['IDataArray'] = [None, None, None, None]

    config = config | expt_cfg


    current_calibration = CurrentCalibration_OffsetSweep_SSMUX(path="CurrentCalibration_OffsetSweep", cfg=config, soc=soc, soccfg=soccfg,
                                            outerFolder=outerFolder)
    current_calibration_data = current_calibration.acquire(angle=angle, threshold=threshold, plotDisp=current_calibration_offset_dict["plotDisp"])
    current_calibration.save_data(current_calibration_data)
    current_calibration.display(current_calibration_data, plotDisp=True, figNum=2)

print(config)