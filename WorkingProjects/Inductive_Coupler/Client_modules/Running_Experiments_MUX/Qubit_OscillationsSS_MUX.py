# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_SSMUX import WalkFFSSMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_GainSweepSSMUX import Oscillations_Gain_SSMUX



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
    '1': {'Readout': {'Frequency': 6962.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [16000, 0, 0, 0], "Readout_Time": 3,
                      "ADC_Offset": 0.5},
          'Qubit01': {'Frequency': 4789.7, 'Gain': 800},
          'Qubit12': {'Frequency': 4531.2, 'Gain': 770 * 0},
          'Pulse_FF': [13000, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7107.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4000,
                      "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 4668.3, 'Gain': 8700},
          'Qubit12': {'Frequency': 4746, 'Gain': 750*0},
          'Pulse_FF': [0, -10000, 0, 0]},
    '3': {'Readout': {'Frequency': 7261.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6,
                      'Gain': 5500, "FF_Gains": [-30000, 0, 0, 0]},
          'Qubit01': {'Frequency': 5586.7, 'Gain': 840},
          'Qubit12': {'Frequency': 4504.8, 'Gain': 1000 * 0},
          'Pulse_FF': [-30000, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7195.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, -7000, 0, 0], 'cavmin': True},
          'Qubit01': {'Frequency': 4644.8, 'Gain': 2150},
          'Qubit12': {'Frequency': 4532.5, 'Gain': 700 * 0},
          'Pulse_FF': [0, -7000, 0, 0]}
    }

Qubit_Readout = [2]
Qubit_Pulse = [2]

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
#Changes for right to left
# FF_gain4_expt = -260
# FF_gain4_expt = 300

swept_qubit_index = 4 #1 indexed

Oscillation_Gain = True
oscillation_gain_dict = {'reps': 500, 'start': int(0), 'step': int(0.25 * 16), 'expts': 200, 'gainStart': -3000,
                         'gainStop': 3000, 'gainNumPoints': 51, 'relax_delay': 150}

Oscillation_Single = False
oscillation_single_dict = {'reps': 3000, 'start': int(400 * 16 * 0), 'step': int(1* 16), 'expts': 2040, 'relax_delay': 200}

SS_params_2States = {"ground": 0, 'excited': 1, "Shots": 4000, "Readout_Time": 2, "ADC_Offset": 0.3}

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']["FF_Gains"]


# cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
# resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
# qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']

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
config["sigma"] = 0.015

config["shots"] = 2000
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

    print(config["FF_Qubits"])

    config["FF_Qubits"]['1']['Gain_Expt'] = FF_gain1_expt
    config["FF_Qubits"]['2']['Gain_Expt'] = FF_gain2_expt
    config["FF_Qubits"]['3']['Gain_Expt'] = FF_gain3_expt
    config["FF_Qubits"]['4']['Gain_Expt'] = FF_gain4_expt
    #
    config = config | expt_cfg
    config['IDataArray'] = [1, None, None, None]

    iOscillations = WalkFFSSMUX(path="QubitOscillationsMUX", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dOscillations = WalkFFSSMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    WalkFFSSMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    WalkFFSSMUX.save_data(iOscillations, dOscillations)
print(config)