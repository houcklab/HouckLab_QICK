# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_SSMUX import WalkFFSSMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_GainSweepSSMUX import Oscillations_Gain_SSMUX



print(soc)

#### define the saving path

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

yoko69.SetVoltage(-0.1368)
yoko70.SetVoltage(-0.1542)
yoko71.SetVoltage(-0.2343)
yoko72.SetVoltage(0.1055)


mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '12': {'Readout_FF': [25000, 10000, 0, 0], 'Pulse_FF': [18000, 5000, 0, 0],
           'Readout': {'1': {'Frequency': 6963.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700},
                       '2': {'Frequency': 7033.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
           'Qubit': {'1': {'Frequency': 4940, 'Gain': 1400}, '2': {'Frequency': 4579.8, 'Gain': 1250}}
           },
    '13': {'Readout_FF': [25000, 0, 17000, 0], 'Pulse_FF': [18000, 0, 7000, 0],
           'Readout': {'1': {'Frequency': 6963.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000},
                       '3': {'Frequency': 7104.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
           'Qubit': {'1': {'Frequency': 4936.8, 'Gain': 1400}, '3': {'Frequency': 4590.4, 'Gain': 2200}}
           },
    '14': {'Readout_FF': [18000, 0, 0, -22000], 'Pulse_FF': [5900, 0, 0, -7200],
        'Readout': {'1': {'Frequency': 6962.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000},
                    '4': {'Frequency': 7230.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500}},
           'Qubit': {'1': {'Frequency': 4589.2, 'Gain': 1620}, '4': {'Frequency': 4617.3, 'Gain': 2900}}
           },

    '23': {'Readout_FF': [0, 13900, 20000, 0], 'Pulse_FF': [0, 8200, 8000, 0],
        'Readout': {'2': {'Frequency': 7033.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000},
                    '3': {'Frequency': 7104.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6200}},
           'Qubit': {'2': {'Frequency': 4670.9, 'Gain': 1600}, '3': {'Frequency': 4613.9, 'Gain': 3050}}
           },
    '24': {'Readout_FF': [0, 9300, 0, -25000], 'Pulse_FF': [0, 5000, 0, -19000],
           'Readout': {'2': {'Frequency': 7033.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500},
                       '4': {'Frequency': 7230.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
           'Qubit': {'2': {'Frequency': 4582, 'Gain': 1350}, '4': {'Frequency': 4915.4, 'Gain': 2750}}
           },
    '34': {'Readout_FF': [0, 0, 17000, -28000], 'Pulse_FF': [0, 0, 6500, -19000],
           'Readout': {'3': {'Frequency': 7104.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000},
                       '4': {'Frequency': 7230.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
           'Qubit': {'3': {'Frequency': 4572.8, 'Gain': 1800}, '4': {'Frequency': 4916.5, 'Gain': 2750}}
           }
    }


Qubit_Readout = 34
Qubit_Readout_Specific = [3, 4]
Qubit_Pulse = 14
Qubit_Pulse_Specific = [1]

FF_gain1_expt = -25 - 50  # 8000
FF_gain2_expt = -100
FF_gain3_expt = 5
FF_gain4_expt = -10

FF_gain2_expt = -120
FF_gain3_expt = 0

swept_qubit_index = 1 #1 indexed

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 1000, 'start': 0, 'step': int(3 * 16), 'expts': 200, 'gainStart': -240,
                         'gainStop': -100, 'gainNumPoints': 8, 'relax_delay': 200}

Oscillation_Single = True
oscillation_single_dict = {'reps': 250, 'start': 0, 'step': int(2 * 16), 'expts': 500, 'relax_delay': 300}

SS_params_2States = {"ground": 0, 'excited': 1, "Shots": 2500, "Readout_Time": 3, "ADC_Offset": 0.5}

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout)]['Readout_FF']


# cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
# resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
# qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']

resonator_frequencies = [Qubit_Parameters[str(Qubit_Readout)]['Readout'][str(Q_R)]['Frequency'] for Q_R in Qubit_Readout_Specific]
gains = [Qubit_Parameters[str(Qubit_Readout)]['Readout'][str(Q_R)]['Gain'] / 32000. * len(Qubit_Readout_Specific) for Q_R in Qubit_Readout_Specific]
qubit_gains = [Qubit_Parameters[str(Qubit_Pulse)]['Qubit'][str(Q_R)]['Gain'] for Q_R in Qubit_Pulse_Specific]
qubit_frequency_centers = [Qubit_Parameters[str(Qubit_Pulse)]['Qubit'][str(Q_R)]['Frequency'] for Q_R in Qubit_Pulse_Specific]

FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout_Specific))]


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
config['Read_Indeces'] = Qubit_Readout_Specific


#### update the qubit and cavity attenuation

config["rounds"] = 1
config["sigma"] = 0.05

config["shots"] = 2000

config['qubit_gains'] = [Qubit_Parameters[str(Qubit_Readout)]['Qubit'][str(Q_R)]['Gain'] for Q_R in
                         Qubit_Readout_Specific]
config['f_ges'] = [Qubit_Parameters[str(Qubit_Readout)]['Qubit'][str(Q_R)]['Frequency'] for Q_R in
                         Qubit_Readout_Specific]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout)]['Pulse_FF']

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


config['qubit_gains'] = [Qubit_Parameters[str(Qubit_Pulse)]['Qubit'][str(Q_R)]['Gain'] for Q_R in
                         Qubit_Pulse_Specific]
config['f_ges'] = [Qubit_Parameters[str(Qubit_Pulse)]['Qubit'][str(Q_R)]['Frequency'] for Q_R in
                         Qubit_Pulse_Specific]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

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
    config = config | expt_cfg

    iOscillations = Oscillations_Gain_SSMUX(path="QubitOscillations_GainSweepMUX", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = Oscillations_Gain_SSMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    Oscillations_Gain_SSMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    Oscillations_Gain_SSMUX.save_data(iOscillations, dOscillations)


if Oscillation_Single:
    config["reps"] = oscillation_single_dict['reps']
    expt_cfg = {"start": oscillation_single_dict['start'], "step": oscillation_single_dict['step'],
                "expts": oscillation_single_dict['expts'], "relax_delay": oscillation_single_dict['relax_delay']}
    # config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    # config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    # config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    # config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']

    # config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
    # config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]
    config['qubit_gains'] = [Qubit_Parameters[str(Qubit_Pulse)]['Qubit'][str(Q_R)]['Gain'] for Q_R in
                             Qubit_Pulse_Specific]
    config['f_ges'] = [Qubit_Parameters[str(Qubit_Pulse)]['Qubit'][str(Q_R)]['Frequency'] for Q_R in
                       Qubit_Pulse_Specific]

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