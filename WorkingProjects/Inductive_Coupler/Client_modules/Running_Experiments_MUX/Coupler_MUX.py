# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mCouplerSwap_SSMUX import CouplerSwapMUX, CouplerSwapGainSweepMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mCouplerSwap_SSMUX import CouplerSwapPhaseSweepMUX, CouplerSwapFrequencySweepMUX

import numpy as np
def coupler_pulse(t, gain, freq, phase):
    return gain * np.sin(freq * 2 * np.pi * t + phase)

print(soc)

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq


Qubit_Parameters = {
    '1': {
        'Readout': {'Frequency': 7192.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8800,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 5581.4, 'Gain': 1815},
          'Qubit12': {'Frequency': 4531.2, 'Gain': 0},
          'Pulse_FF': [0, 0, 0, 0],
          'Coupler': {'Frequency': 0, 'Gain': 0, 'Phase': 0}},
    '2': {
        'Readout': {'Frequency': 7091.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 5477.2, 'Gain': 1626},
          'Qubit12': {'Frequency': 4746, 'Gain': 0},
          'Pulse_FF': [0, 0, 0, 0],
          'Coupler': {'Frequency': 110, 'Gain': 6000, 'Phase': 0}},
    '3': {
        'Readout': {'Frequency': 7281.95 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 5258, 'Gain': 2030},
          'Qubit12': {'Frequency': 4746, 'Gain': 0},
          'Pulse_FF': [0, 0, 0, 0],
          'Coupler': {'Frequency': 0, 'Gain': 0, 'Phase': 0}},
    '4': {
        'Readout': {'Frequency': 7230.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0]},
          'Qubit01': {'Frequency': 5029.9, 'Gain': 1230},
          'Qubit12': {'Frequency': 4532.5, 'Gain': 0},
          'Pulse_FF':  [0, 0, 0, 0],
          'Coupler': {'Frequency': 0, 'Gain': 0, 'Phase': 0}}

    }

Qubit_Readout = [3]
Qubit_Pulse = [3]
Coupler_Drive = [2]

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

times = np.arange(0, 4, 2.32515 / 16 * 1e-3)
IDataArray = [np.zeros(len(times)) for Q_R in Qubit_Parameters]
for Q_R in Coupler_Drive:
    freq = Qubit_Parameters[str(Q_R)]['Coupler']['Frequency']
    gain = Qubit_Parameters[str(Q_R)]['Coupler']['Gain']
    phase = Qubit_Parameters[str(Q_R)]['Coupler']['Phase']


    IDataArray[Q_R - 1] = coupler_pulse(times, gain, freq, phase)

swept_qubit_index = 2 #1 indexed
Oscillation_Frequency = True  #MHz
oscillation_freq_dict = {'reps': 250, 'start': int(0), 'step': int(4 * 16), 'expts': 200, 'freqStart': 300,
                         'freqStop': 340, 'freqNumPoints': 21, 'relax_delay': 200}

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 250, 'start': int(0), 'step': int(4 * 16), 'expts': 200, 'gainStart': 3000,
                         'gainStop': 9000, 'gainNumPoints': 16, 'relax_delay': 200}

Oscillation_Phase = False
oscillation_phase_dict = {'reps': 250, 'start': int(0), 'step': int(4 * 16), 'expts': 400, 'phaseStart': -np.pi/3,
                         'phaseStop': 7 * np.pi / 3, 'phaseNumPoints': 121, 'relax_delay': 200}



Oscillation_Single = False
oscillation_single_dict = {'reps': 3000, 'start': int(400 * 16 * 0), 'step': int(1 * 16), 'expts': 2040, 'relax_delay': 200}

SS_params_2States = {"ground": 0, 'excited': 1, "Shots": 4000, "Readout_Time": 3, "ADC_Offset": 0.5}

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']["FF_Gains"]

resonator_frequencies = [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout]
gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

qubit_gains = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
qubit_frequency_centers = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]
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
    # "pulse_gain": cavity_gain,  # [DAC units]
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
config["sigma"] = 0.03

config["shots"] = SS_params_2States["Shots"]
config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Readout]
config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Readout]
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
print(Instance_SingleShotProgram.angle,Instance_SingleShotProgram.threshold)

# data_SingleShotProgram = SingleShotProgramFFMUX.analyze(Instance_SingleShotProgram, data_SingleShotProgram)

SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)


config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

config['ArrayTimes'] = times

if Oscillation_Frequency:
    config["reps"] = oscillation_freq_dict['reps']
    expt_cfg = {"start": oscillation_freq_dict['start'], "step": oscillation_freq_dict['step'],
                "expts": oscillation_freq_dict['expts'],
                "freqStart": oscillation_freq_dict['freqStart'],
                "freqStop": oscillation_freq_dict['freqStop'], "freqNumPoints": oscillation_freq_dict['freqNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_freq_dict['relax_delay'],
                "Swept_Coupler_Parameters": Qubit_Parameters[str(swept_qubit_index)]['Coupler']
                }
    config['IDataArray'] = IDataArray
    config = config | expt_cfg

    iOscillations = CouplerSwapFrequencySweepMUX(path="CouplerSwap_FrequencySweepMUX", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = CouplerSwapFrequencySweepMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    CouplerSwapFrequencySweepMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    CouplerSwapFrequencySweepMUX.save_data(iOscillations, dOscillations)

if Oscillation_Gain:
    config["reps"] = oscillation_gain_dict['reps']
    expt_cfg = {"start": oscillation_gain_dict['start'], "step": oscillation_gain_dict['step'],
                "expts": oscillation_gain_dict['expts'],
                "gainStart": oscillation_gain_dict['gainStart'],
                "gainStop": oscillation_gain_dict['gainStop'], "gainNumPoints": oscillation_gain_dict['gainNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_gain_dict['relax_delay'],
                "Swept_Coupler_Parameters": Qubit_Parameters[str(swept_qubit_index)]['Coupler']
                }
    config['IDataArray'] = IDataArray
    config = config | expt_cfg

    iOscillations = CouplerSwapGainSweepMUX(path="CouplerSwap_GainSweepMUX", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = CouplerSwapGainSweepMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    CouplerSwapGainSweepMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    CouplerSwapGainSweepMUX.save_data(iOscillations, dOscillations)

if Oscillation_Phase:
    config["reps"] = oscillation_phase_dict['reps']
    expt_cfg = {"start": oscillation_phase_dict['start'], "step": oscillation_phase_dict['step'],
                "expts": oscillation_phase_dict['expts'],
                "phaseStart": oscillation_phase_dict['phaseStart'],
                "phaseStop": oscillation_phase_dict['phaseStop'], "phaseNumPoints": oscillation_phase_dict['phaseNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_phase_dict['relax_delay'],
                "Swept_Coupler_Parameters": Qubit_Parameters[str(swept_qubit_index)]['Coupler']
                }
    config['IDataArray'] = IDataArray
    config = config | expt_cfg

    iOscillations = CouplerSwapPhaseSweepMUX(path="CouplerSwap_PhaseSweepMUX", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = CouplerSwapPhaseSweepMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    CouplerSwapPhaseSweepMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    CouplerSwapPhaseSweepMUX.save_data(iOscillations, dOscillations)


if Oscillation_Single:
    config["reps"] = oscillation_single_dict['reps']
    expt_cfg = {"start": oscillation_single_dict['start'], "step": oscillation_single_dict['step'],
                "expts": oscillation_single_dict['expts'], "relax_delay": oscillation_single_dict['relax_delay']}
    # config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    # config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    # config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    # config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']

    config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
    config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]

    config["FF_Qubits"]['1']['Gain_Expt'] = FF_gain1_expt
    config["FF_Qubits"]['2']['Gain_Expt'] = FF_gain2_expt
    config["FF_Qubits"]['3']['Gain_Expt'] = FF_gain3_expt
    config["FF_Qubits"]['4']['Gain_Expt'] = FF_gain4_expt
    #
    config = config | expt_cfg
    config['IDataArray'] = IDataArray

    iOscillations = CouplerSwapMUX(path="CouplerSwapMUX", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dOscillations = CouplerSwapMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    CouplerSwapMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    CouplerSwapMUX.save_data(iOscillations, dOscillations)
print(config)