# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAdiabticRampCalibration import AdiabticRampCalibration
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecVsAdiabaticRamp import SpecVsAdiabaticRamp
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAdiabaticRampOscillations import AdiabaticRampOscillations
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAdiabaticRampSingleShot import AdiabaticRampSingleShot
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mFFSweepARampSS import FFSweepAdiabaticRampSingleShot
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mFFSweepRampOsc import FFSweepRampOscillations

import numpy as np
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

# Matt parameters
# negative coupling
# voltages = [0.82,  0.60,  0.67,  0.07845723, -0.3328404 ,  0.14592326, -0.32117671] # negative coupling
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7322 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7300,
                      "FF_Gains": [0, 0, 2000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4585, 'Gain': 2023},
          'Pulse_FF': [0, 0, 2000, 0]},
    '2': {'Readout': {'Frequency': 7269.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4500,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4286.9, 'Gain': 3170},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7525.15 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6300,
                      "FF_Gains": [0, 0, 2000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4774.7, 'Gain': 1350},
          'Pulse_FF': [0, 0, 2000, 0]},
    '4': {'Readout': {'Frequency': 7459.85 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4372.9, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7325.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
              'Qubit': {'Frequency': 4047.84, 'Gain': 7500},
              'Pulse_FF': [0, 0, 0, 0]},
    'plus': {'Readout': {'Frequency': 7322 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4625.5, 'Gain': 1960},
          'Pulse_FF': [0, 0, 0, 0]},
    'minus': {'Readout': {'Frequency': 7525.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4655.3, 'Gain': 2900},
          'Pulse_FF': [0, 0, 0, 0]},
    }


# positive coupling
# voltages = [0.80,  0.60,  0.79,  0.07845723, 0.38,  0.14592326, -0.32117671] # positive coupling
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7322 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7300,
                      "FF_Gains": [0, 0, 3000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4589.3, 'Gain': 2370},
          'Pulse_FF': [0, 0, 3000, 0]},
    '2': {'Readout': {'Frequency': 7269.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
                      "FF_Gains": [0, 0, 3000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4317.3, 'Gain': 4440},
          'Pulse_FF': [0, 0, 3000, 0]},
    '3': {'Readout': {'Frequency': 7525.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6300,
                      "FF_Gains": [0, 0, 3000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4818.2, 'Gain': 1340},
          'Pulse_FF': [0, 0, 3000, 0]},
    '4': {'Readout': {'Frequency': 7459.85 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4372.9, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7325.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
              'Qubit': {'Frequency': 4047.84, 'Gain': 7500},
              'Pulse_FF': [0, 0, 0, 0]},
    'plus': {'Readout': {'Frequency': 7525.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6300,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4648.4, 'Gain': 2370},
          'Pulse_FF': [0, 0, 0, 0]},
    'minus': {'Readout': {'Frequency': 7322 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7300,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4589.3, 'Gain': 2370},
          'Pulse_FF': [0, 0, 0, 0]},
    }


# Joshua parameters
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7322.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [0, 0, 11000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4634.2, 'Gain': 3000},
          'Pulse_FF': [0, 3000, 6150, 0]},
    '2': {'Readout': {'Frequency': 7269.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
                      "FF_Gains": [0, 0, 11000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4491.8, 'Gain': 1390},
          'Pulse_FF': [0, 3000, 6150, 0]},
    '3': {'Readout': {'Frequency': 7525.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
                      "FF_Gains": [0, 0, 11000, 0], "Readout_Time": 2, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4713.0, 'Gain': 3150},
          'Pulse_FF': [0, 3000, 6150, 0]},
    '4': {'Readout': {'Frequency': 7459.85 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4372.9, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7325.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
              'Qubit': {'Frequency': 4047.84, 'Gain': 7500},
              'Pulse_FF': [0, 0, 0, 0]},
    }
Qubit_Parameters['plus'] = Qubit_Parameters['3']
Qubit_Parameters['minus'] = Qubit_Parameters['1']

Qubit_Readout = [1]
Qubit_Pulse = ['minus']

# final gain to ramp to after qubit pulse
FF_gain1_ramp = 0
FF_gain2_ramp = 3000
FF_gain3_ramp = 4805
FF_gain4_ramp = 0

# gain to jump to for swaps
FF_gain1_expt = 0
FF_gain2_expt = 5892
FF_gain3_expt = 4805
FF_gain4_expt = 0

# # final gain to ramp to after qubit pulse
# FF_gain1_ramp = 0
# FF_gain2_ramp = 0
# FF_gain3_ramp = -990
# FF_gain4_ramp = 0
#
# # gain to jump to for swaps
# FF_gain1_expt = 0
# FF_gain2_expt = 4874
# FF_gain3_expt = -990
# FF_gain4_expt = 0


runSpecVsAdiabatic = False
Spec_sweep_relevant_params = {"qubit_gain": 500, "SpecSpan": 250, "SpecNumPoints": 71, 'spec_center': 4500,
                              "ramp_duration": int(2*7000), "ramp_num_points": 11,
                              'reps': 10, 'rounds': 10, 'smart_normalize': True, 'Gauss': False,
                              'ramp_shape': 'cubic', 'double': True}


runAdiabaticRampCalibration = False
adiabatic_ramp_calibration_dict = {'reps': 500, 'duration_start': int(1), 'duration_end': int(1500), 'duration_num_points': 21,
                                   'relax_delay': 200, 'ramp_shape': 'cubic', 'double': False,
                                   'use_confusion_matrix': True}

runAdiabaticRampSingleShot = False
# this experiment will adiabatically prepare an initial state the same way as the AdiabaticRampOcillations experiment,
# then do single shot readout
adiabatic_ramp_single_shot_dict = {"Shots": 1000, "Readout_Time": 2.5, "ADC_Offset": 0.3, "Qubit_Pulse": Qubit_Pulse,
                                   'ramp_duration': int(2000), 'ramp_shape': 'cubic'}
FFSweepAdiabaticRampSS = False
# this experiment runs the above experiment multiple times, sweeping the FF gain of a particular index
# (uses the confusion matrix)
ff_sweep_adiabatic_ss_dict = {'swept_index': 3,
                              'gain_start': 4700, 'gain_end': 4900, 'num_points': 11}  # 1-indexed


runAdiabaticRampOscillations = True
# oscillation_single_dict = {'reps': 8000, 'start': int(0), 'step': int(0.25 * 40 *4), 'expts': 71*10, 'relax_delay': 400,
#                            'ramp_duration': int(2000), 'ramp_shape': 'cubic'}
oscillation_single_dict = {'reps': 3000, 'start': int(0), 'step': int(0.25 * 40), 'expts': 71+30, 'relax_delay': 300,
                           'ramp_duration': int(2200), 'ramp_shape': 'cubic'}
# oscillation_single_dict = {'reps': 500, 'start': int(0), 'step': int(0.25 * 20), 'expts': 501, 'relax_delay': 300,
#                            'ramp_duration': int(800), 'ramp_shape': 'cubic'}
# oscillation_single_dict = {'reps': 2000, 'start': int(0), 'step': int(0.25 * 20), 'expts': 1001, 'relax_delay': 200,
#                            'ramp_duration': int(800), 'ramp_shape': 'cubic'}
# oscillation_single_dict = {'reps': 2000, 'start': int(0), 'step': int(0.25 * 20), 'expts': 4001, 'relax_delay': 200,
#                            'ramp_duration': int(800), 'ramp_shape': 'cubic'}



runFFSweepRampOscillations = True
ff_sweep_ramp_osc_dict = {'swept_index': 2, # 1-indexed
                              'gain_start': 6000, 'gain_end': 8000, 'num_points': 21}


# SS params for reading out qubits after ramp or oscillations
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


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse, 'Gain_Ramp': FF_gain1_ramp}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse, 'Gain_Ramp': FF_gain2_ramp}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse, 'Gain_Ramp': FF_gain3_ramp}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse, 'Gain_Ramp': FF_gain4_ramp}

# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 1000,
    # "qubit_freq": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    "qubit_length": soc.us2cycles(40),
    ##### define spec slice experiment parameters
    "SpecSpan": Spec_sweep_relevant_params['SpecSpan'],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_sweep_relevant_params['SpecNumPoints'],  ### number of points in the transmission frequecny
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
config["sigma"] = 0.05

config["shots"] = 10000
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

Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                         soc=soc, soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
data_SingleShotProgram = Instance_SingleShotProgram.acquire()

angle, threshold = Instance_SingleShotProgram.angle, Instance_SingleShotProgram.threshold
print("angle and threshold:", Instance_SingleShotProgram.angle,Instance_SingleShotProgram.threshold)

ne_contrast, ng_contrast = Instance_SingleShotProgram.ne_contrast, Instance_SingleShotProgram.ng_contrast,
confusion_matrix = np.array([[1-ng_contrast, ne_contrast], [ng_contrast, 1-ne_contrast]])
print("Confusion_matrix:", confusion_matrix)
config['confusion_matrix'] = confusion_matrix

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

print("Starting adiabatic ramp experiments")

if runAdiabaticRampCalibration:
    config["reps"] = adiabatic_ramp_calibration_dict['reps']
    expt_cfg = {"duration_start": adiabatic_ramp_calibration_dict['duration_start'], "duration_end": adiabatic_ramp_calibration_dict['duration_end'],
                "duration_num_points": adiabatic_ramp_calibration_dict['duration_num_points'], "relax_delay": adiabatic_ramp_calibration_dict['relax_delay'],
                "ramp_shape": adiabatic_ramp_calibration_dict['ramp_shape'], "double_ramp": adiabatic_ramp_calibration_dict['double'],
                "use_confusion_matrix": adiabatic_ramp_calibration_dict["use_confusion_matrix"]}

    config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse]
    config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse]

    config["FF_Qubits"]['1']['Gain_Expt'] = FF_gain1_expt
    config["FF_Qubits"]['2']['Gain_Expt'] = FF_gain2_expt
    config["FF_Qubits"]['3']['Gain_Expt'] = FF_gain3_expt
    config["FF_Qubits"]['4']['Gain_Expt'] = FF_gain4_expt

    config['IDataArray'] = [0]*4
    config['IDataArrayReverse'] = [0]*4

    config = config | expt_cfg

    adiabatic_ramp_calibration_experiment = AdiabticRampCalibration(path="AdiabticRampCalibration", cfg=config, soc=soc, soccfg=soccfg,
                                outerFolder=outerFolder)
    adiabatic_ramp_data = adiabatic_ramp_calibration_experiment.acquire(angle=angle, threshold=threshold)
    adiabatic_ramp_calibration_experiment.display(adiabatic_ramp_data, plotDisp=True, figNum=2)
    adiabatic_ramp_calibration_experiment.save_data(adiabatic_ramp_data)


if runSpecVsAdiabatic:


    # update config with qubit spec parameters
    config['qubit_length'] = 100
    config['qubit_freq'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency']
    config['qubit_freq'] = Spec_sweep_relevant_params['spec_center']

    config["reps"] = Spec_sweep_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_sweep_relevant_params['rounds']
    config['sleep_time'] = 0
    config["ramp_duration"] = Spec_sweep_relevant_params['ramp_duration']
    config["ramp_num_points"] = Spec_sweep_relevant_params['ramp_num_points']

    config["Gauss"] = Spec_sweep_relevant_params['Gauss']

    config["qubit_gain"] = Spec_sweep_relevant_params["qubit_gain"]
    config["step"] = 2 * Spec_sweep_relevant_params["SpecSpan"] / (Spec_sweep_relevant_params["SpecNumPoints"] - 1)
    config["start"] = config['qubit_freq'] - Spec_sweep_relevant_params["SpecSpan"]
    config["expts"] = Spec_sweep_relevant_params["SpecNumPoints"]


    config["ramp_shape"] = Spec_sweep_relevant_params['ramp_shape']
    config["double_ramp"] = Spec_sweep_relevant_params['double']

    config['IDataArray'] = [None]*4

    spec_vs_adiabatic_ramp_experiment = SpecVsAdiabaticRamp(path="SpecVsAdiabaticRamp", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
    spec_vs_adiabatic_ramp_data = spec_vs_adiabatic_ramp_experiment.acquire( plotDisp=True)
                                      # smart_normalize=Spec_sweep_relevant_params['smart_normalize'])

    spec_vs_adiabatic_ramp_experiment.save_data(spec_vs_adiabatic_ramp_data)
    spec_vs_adiabatic_ramp_experiment.save_config()

if runAdiabaticRampSingleShot:
    config['Shots'] = adiabatic_ramp_single_shot_dict['Shots']
    config['Readout_Time'] = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
    config['ADC_Offset'] = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['ADC_Offset']

    config['ramp_duration'] = adiabatic_ramp_single_shot_dict['ramp_duration']
    config['ramp_shape'] = adiabatic_ramp_single_shot_dict['ramp_shape']


    adiabatic_ramp_single_shot_experiment = AdiabaticRampSingleShot(path="AdiabaticRampSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    adiabatic_ramp_single_shot_data = adiabatic_ramp_single_shot_experiment.acquire()
    adiabatic_ramp_single_shot_experiment.display(adiabatic_ramp_single_shot_data, plotDisp=True)

    adiabatic_ramp_single_shot_experiment.save_data(adiabatic_ramp_single_shot_data)
    adiabatic_ramp_single_shot_experiment.save_config()

if FFSweepAdiabaticRampSS:
    config['Shots'] = adiabatic_ramp_single_shot_dict['Shots']
    config['Readout_Time'] = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
    config['ADC_Offset'] = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['ADC_Offset']

    config['ramp_duration'] = adiabatic_ramp_single_shot_dict['ramp_duration']
    config['ramp_shape'] = adiabatic_ramp_single_shot_dict['ramp_shape']
    config['angle'] = angle
    config['threshold'] = threshold

    config = config | ff_sweep_adiabatic_ss_dict
    # Gets the keys 'swept_index', 'gain_start', 'gain_end', and 'num_points'

    ff_sweep_adiabatic_ss_experiment = FFSweepAdiabaticRampSingleShot(path="FFSweepAdiabaticRampSingleShot",
                                                                    outerFolder=outerFolder, cfg=config, soc=soc,
                                                                    soccfg=soccfg)
    ff_sweep_adiabatic_ss_experiment_data = ff_sweep_adiabatic_ss_experiment.acquire()
    ff_sweep_adiabatic_ss_experiment.display(ff_sweep_adiabatic_ss_experiment_data, plotDisp=True)

    ff_sweep_adiabatic_ss_experiment.save_data(ff_sweep_adiabatic_ss_experiment_data)
    ff_sweep_adiabatic_ss_experiment.save_config()

if runFFSweepRampOscillations:
    config["sigma"] = 0.05
    config["reps"] = oscillation_single_dict['reps']
    expt_cfg = {"start": oscillation_single_dict['start'], "step": oscillation_single_dict['step'],
                "expts": oscillation_single_dict['expts'], "relax_delay": oscillation_single_dict['relax_delay'],
                'ramp_duration': oscillation_single_dict['ramp_duration'], 'ramp_shape': oscillation_single_dict['ramp_shape']}

    config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse]
    config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse]

    config['angle'] = angle
    config['threshold'] = threshold

    config = config | ff_sweep_ramp_osc_dict
    # Gets the keys 'swept_index', 'gain_start', 'gain_end', and 'num_points'

    print(config["FF_Qubits"])

    config = config | expt_cfg

    ffsweep_oscillation_experiment = FFSweepRampOscillations(path="AdiabaticRampOscillationsGainSweep", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    ffsweep_oscillation_data = ffsweep_oscillation_experiment.acquire(angle=angle, threshold= threshold)
    ffsweep_oscillation_experiment.display(ffsweep_oscillation_data, plotDisp=True, figNum=2)
    ffsweep_oscillation_experiment.save_data(ffsweep_oscillation_data)


if runAdiabaticRampOscillations:
    config["sigma"] = 0.05
    config["reps"] = oscillation_single_dict['reps']
    expt_cfg = {"start": oscillation_single_dict['start'], "step": oscillation_single_dict['step'],
                "expts": oscillation_single_dict['expts'], "relax_delay": oscillation_single_dict['relax_delay'],
                'ramp_duration': oscillation_single_dict['ramp_duration'], 'ramp_shape': oscillation_single_dict['ramp_shape']}

    config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse]
    config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse]


    print(config["FF_Qubits"])

    config = config | expt_cfg
    print("THRESHOLD", threshold)
    adiabatic_oscillation_experiment = AdiabaticRampOscillations(path="AdiabaticRampOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    adiabatic_oscillation_data = adiabatic_oscillation_experiment.acquire(angle=angle, threshold= threshold)
    adiabatic_oscillation_experiment.display(adiabatic_oscillation_data, plotDisp=True, figNum=2)
    adiabatic_oscillation_experiment.save_data(adiabatic_oscillation_data)

print(config)
