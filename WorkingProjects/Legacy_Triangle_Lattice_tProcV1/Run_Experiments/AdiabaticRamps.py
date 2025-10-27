# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.MUXInitialize import *
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mAdiabticRampCalibration import AdiabticRampCalibration
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mSpecVsAdiabaticRamp import SpecVsAdiabaticRamp
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mAdiabaticRampOscillations import AdiabaticRampOscillations
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mAdiabaticRampSingleShot import AdiabaticRampSingleShot
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mFFSweepARampSS import FFSweepAdiabaticRampSingleShot
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mFFSweepRampOsc import FFSweepRampOscillations
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mAdiabaticT1 import AdiabaticRampT1SS
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mRampDelayVsPopulation import SweepDelayVsPopulation

import numpy as np


mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6978.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 15000,
                      "FF_Gains": [0, 0, 8000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4392.0, 'sigma': 0.05, 'Gain': 14350},
          'Pulse_FF': [0, -10000, 8000, 0]},  # second index
    '2': {'Readout': {'Frequency': 7095.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7350,
                      "FF_Gains": [0, -20000, -2000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4438.8, 'sigma': 0.05, 'Gain': 3330},
          'Pulse_FF':[0, -20000, 0, 0]}, # third index
    '4': {'Readout': {'Frequency': 7269.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 18000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4035.7, 'sigma': 0.05, 'Gain': 9250},
          'Pulse_FF': [0, 0, 0, 0]},
    }


FF_gain1_ramp = 0  # 8000
FF_gain2_ramp = 5000
FF_gain3_ramp = -2000
FF_gain4_ramp = 0

FF_gain1_expt = 0
FF_gain2_expt = -15000
FF_gain3_expt = 1670
FF_gain4_expt = 0


Qubit_Readout = [1]
Qubit_Pulse = [1]



runSpecVsAdiabatic = False
Spec_sweep_relevant_params = {"qubit_gain": 500, "SpecSpan": 180, "SpecNumPoints": 201, 'spec_center': 4700,
                              "ramp_duration": int(6000), "ramp_num_points": 11,
                              'reps': 10, 'rounds': 10, 'smart_normalize': True, 'Gauss': False,
                              'ramp_shape': 'cubic', 'double': True}


runAdiabaticRampCalibration = False
adiabatic_ramp_calibration_dict = {'reps': 1000, 'duration_start': int(1), 'duration_end': int(1250), 'duration_num_points': 61,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'ramp_shape': 'cubic', 'double': True,
                                   'use_confusion_matrix': True}

runAdiabaticRampSingleShot = True
# this experiment will adiabatically prepare an initial state the same way as the AdiabaticRampOcillations experiment,
# then do single shot readout
adiabatic_ramp_single_shot_dict = {"Shots": 1200, "Readout_Time": 2.5, "ADC_Offset": 0.3, "Qubit_Pulse": Qubit_Pulse,
                                   'ramp_duration': int(16 * 500), 'ramp_shape': 'cubic'}
FFSweepAdiabaticRampSS = False
# this experiment runs the above experiment multiple times, sweeping the FF gain of a particular index
# (uses the confusion matrix)
ff_sweep_adiabatic_ss_dict = {'swept_index': 3,
                              'gain_start': -100, 'gain_end': 200, 'num_points': 11, "fit_point": 0.5}  # 1-indexed
# ff_sweep_adiabatic_ss_dict = {'swept_index': 1,
#                               'gain_start': -1330, 'gain_end': -1230, 'num_points': 8, "fit_point": 0.5}  # 1-indexed

runDelayVsPopulation = False
delay_vs_pop_dict = {'ramp_duration' : 10000, 'ramp_shape': 'cubic',
        'delay_start': 0, 'delay_stop' : 20000, 'delay_steps' : 20,
                     'shots':4000}

runAdiabaticRampOscillations = False
oscillation_single_dict = {'reps': 1000, 'start': int(0), 'step': int(10), 'expts': 200, 'relax_delay': 300,
                           'ramp_duration': int(20000), 'ramp_shape': 'cubic'}

runAdiabaticT1 = False
# AdiabaticT1Params = {'wait_times': np.linspace(0, 150, 21),
#                 'meas_shots': 200, 'repeated_nums': 10, 'ramp_duration': int(16 * 500), 'ramp_shape': 'cubic',
#                 'qubitIndex': int(Qubit_Pulse[0]), 'relax_delay': 200}


runFFSweepRampOscillations = False
ff_sweep_ramp_osc_dict = {'swept_index': 2, # 1-indexed
                              'gain_start': 6000, 'gain_end': 8000, 'num_points': 21}


# SS params for reading out qubits after ramp or oscillations
SS_params_2States = {"ground": 0, 'excited': 1, "shots": 4000, "Readout_Time": 2.5, "ADC_Offset": 0.3}



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
    "res_pulse_style": "const",  # --Fixed
    "readout_length": 3,  # [Clock ticks]
    "res_gain": int(cavity_gain),  # [DAC units]
    # "res_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "res_gains": gains,  # [DAC units]
    "res_freqs": resonator_frequencies,
    ##### define tranmission experiment parameters
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60,  ### number of points in the transmission frequecny
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout


#### update the qubit and cavity attenuation

config["rounds"] = 1
config["sigma"] = 0.05



### Calculate confusion matrices, assuming error is mostly due to readout and not pulses
config["shots"] = 5000
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout[0])]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

config["readout_length"] = SS_params_2States["Readout_Time"]  # us (length of the pulse applied)
config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]
print(config["res_freqs"])

angle = []
threshold = []
confusion_matrix = []
# Do SingleShots for each qubit separately, otherwise the fidelities will be affected by the ZZ interaction
for j, Q in enumerate(Qubit_Readout):
    config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain']]
    config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit']['Frequency']]

    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                             soc=soc, soccfg=soccfg)
    # data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    data_SingleShotProgram = Instance_SingleShotProgram.acquire()

    angle.append(Instance_SingleShotProgram.angle[j])
    threshold.append(Instance_SingleShotProgram.threshold[j])
    print("angle and threshold:", Instance_SingleShotProgram.angle[j],Instance_SingleShotProgram.threshold[j])

    ne_contrast, ng_contrast = Instance_SingleShotProgram.ne_contrast, Instance_SingleShotProgram.ng_contrast
    conf_mat = np.array([[1-ng_contrast[j], ne_contrast[j]],
                         [ng_contrast[j], 1-ne_contrast[j]]])
    print("Confusion_matrix:", conf_mat)
    confusion_matrix.append(conf_mat)

    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True, display_indices=[Q])
    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)

config['confusion_matrix'] = confusion_matrix

# data_SingleShotProgram = SingleShotProgramFFMUX.analyze(Instance_SingleShotProgram, data_SingleShotProgram)



config["Qubit_Readout_List"] = Qubit_Readout
config['qubit_gains'] = [int(Qubit_Parameters[str(Q)]['Qubit']['Gain']) for Q in Qubit_Pulse]
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
                "use_confusion_matrix": adiabatic_ramp_calibration_dict["use_confusion_matrix"],
                "ramp_wait_timesteps": adiabatic_ramp_calibration_dict['ramp_wait_timesteps']}

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

    config["qubit_gain"] = int(Spec_sweep_relevant_params["qubit_gain"])
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
    config['shots'] = adiabatic_ramp_single_shot_dict['Shots']
    config['Readout_Time'] = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
    config['ADC_Offset'] = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['ADC_Offset']

    config['ramp_duration'] = adiabatic_ramp_single_shot_dict['ramp_duration']
    config['ramp_shape'] = adiabatic_ramp_single_shot_dict['ramp_shape']


    adiabatic_ramp_single_shot_experiment = AdiabaticRampSingleShot(path="AdiabaticRampSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    adiabatic_ramp_single_shot_data = adiabatic_ramp_single_shot_experiment.acquire()

    adiabatic_ramp_single_shot_experiment.save_data(adiabatic_ramp_single_shot_data)
    adiabatic_ramp_single_shot_experiment.save_config()
    adiabatic_ramp_single_shot_experiment.display(adiabatic_ramp_single_shot_data, plotDisp=True)

if FFSweepAdiabaticRampSS:
    config['shots'] = adiabatic_ramp_single_shot_dict['Shots']
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

    ff_sweep_adiabatic_ss_experiment.save_data(ff_sweep_adiabatic_ss_experiment_data)
    ff_sweep_adiabatic_ss_experiment.save_config()
    ff_sweep_adiabatic_ss_experiment.display(ff_sweep_adiabatic_ss_experiment_data, plotDisp=True)



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

if runAdiabaticT1:
    config["FF_Qubits"] = FF_Qubits
    config["reps"] = AdiabaticT1Params['meas_shots']

    for key in config["FF_Qubits"].keys():
        config["FF_Qubits"][key]['Gain_Expt'] = config["FF_Qubits"][key]['Gain_Pulse']
    config = config | AdiabaticT1Params

    Instance_T1_SS = AdiabaticRampT1SS(path="Adiabatic_T1", outerFolder=outerFolder, cfg=config,
                                                        soc=soc, soccfg=soccfg)
    data_T1_SS = Instance_T1_SS.acquire(angle = angle, threshold = threshold)
    print()
    # SingleShotProgramFFMUX.display(Instance_T1_TLS, data_T1_TLS, plotDisp=True)
    AdiabaticRampT1SS.save_data(Instance_T1_SS, data_T1_SS)
    AdiabaticRampT1SS.save_config(Instance_T1_SS)

if runDelayVsPopulation:
    config = config | delay_vs_pop_dict
    config = config | {"threshold": threshold, "angle": angle, "confusion_matrix": confusion_matrix}

    DelayVsPop_Exp = SweepDelayVsPopulation(path="SweepDelayVsPopulation", outerFolder=outerFolder, cfg=config,
                                       soc=soc, soccfg=soccfg)
    DelayVsPop_Exp.acquire_save_display(plotDisp=True)

print(config)
