# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations import WalkFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations_GainSweep import Oscillations_Gain
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillationsR_GainSweep import OscillationsR_Gain

print(soc)

#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# yoko69.SetVoltage(-0.061)
# yoko70.SetVoltage(-0.279)
# yoko71.SetVoltage(-0.358)
# yoko72.SetVoltage(0.340)
#
#
# #Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.87, 'Gain': 8000}, 'Qubit': {'Frequency': 4597.6, 'Gain': 1670},
#           'Pulse_FF': [-11000, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7056.08, 'Gain': 6000}, 'Qubit': {'Frequency': 4609.2, 'Gain': 1820},
#           'Pulse_FF': [0, 10000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit': {'Frequency': 4599.5, 'Gain': 2600},
#           'Pulse_FF': [0, 0, 10000, 0]},
#     '4': {'Readout': {'Frequency': 7249.89, 'Gain': 6000}, 'Qubit': {'Frequency': 4571.4, 'Gain': 1160},
#           'Pulse_FF': [0, 0, 0, -14000]}
#     }
# # Readout
# FF_gain1 = -15000  # 8000
# FF_gain2 = 20000
# FF_gain3 = 0
# FF_gain4 = -16000
# # expt
# FF_gain1_expt = -150  # 8000
# FF_gain2_expt = -250
# FF_gain3_expt = 0
# FF_gain4_expt = 0
#
# Qubit_Readout = 2
# Qubit_Pulse = 3

# yoko69.SetVoltage(0.0894)
# yoko70.SetVoltage(0.0091)
# yoko71.SetVoltage(-0.3549)
# yoko72.SetVoltage(-0.0022)

# yoko69.SetVoltage(-0.2923)
# yoko70.SetVoltage(0.0079)
# yoko71.SetVoltage(-0.3571)
# yoko72.SetVoltage(0.2951)

# yoko69.SetVoltage(-0.2743)
# yoko70.SetVoltage(-0.2606)
# yoko71.SetVoltage(-0.05)
# yoko72.SetVoltage(0.301)

yoko69.SetVoltage(-0.0789)
yoko70.SetVoltage(-0.086)
yoko71.SetVoltage(-0.0127)
yoko72.SetVoltage(-0.1081)

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.45, 'Gain': 12500}, 'Qubit': {'Frequency': 4399.5, 'Gain': 1170},
          'Pulse_FF': [14000, 0, 0, 0]},
    # '2': {'Readout': {'Frequency': 7055.45, 'Gain': 6000}, 'Qubit': {'Frequency': 4403.6, 'Gain': 1300},
    #       'Pulse_FF': [0, 0, 0, -8000]},
    '2': {'Readout': {'Frequency': 7055.45, 'Gain': 6000}, 'Qubit': {'Frequency': 4403.3, 'Gain': 1150},
          'Pulse_FF': [-6000, 0, 0, 0]},
    # '3': {'Readout': {'Frequency': 7117.04, 'Gain': 6000}, 'Qubit': {'Frequency': 4400.6, 'Gain': 1450},
    #       'Pulse_FF': [6000, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit': {'Frequency': 4398.5, 'Gain': 1650},
          'Pulse_FF': [0, 0, 0, -8000]},
    '4': {'Readout': {'Frequency': 7249.89, 'Gain': 6000}, 'Qubit': {'Frequency': 4571.4, 'Gain': 1160},
          'Pulse_FF': [0, 0, 0, -14000]}
    }
# Readout
FF_gain1 = -14000  # 8000
FF_gain2 = 0
FF_gain3 = 0
FF_gain4 = 0

# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

Qubit_Readout = 1
Qubit_Pulse = 1

FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 1000,
    "qubit_freq": qubit_frequency_center,
    "qubit_length": soc.us2cycles(40),
    ##### define spec slice experiment parameters
    "SpecSpan": 12,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 60,  ### number of points in the transmission frequecny
}
UpdateConfig_FF = {
    "ff_pulse_style": "const",  # --Fixed
    "ff_additional_length": soc.us2cycles(1),  # [Clock ticks]
    "ff_freq": 0,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1,  ### MHz, span will be center+/- this parameter
    "relax_delay": 200,  ### in units us
}
expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],
    "span": UpdateConfig_qubit["SpecSpan"],
    "expts": UpdateConfig_qubit["SpecNumPoints"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}

UpdateConfig_transmission = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60,  ### number of points in the transmission frequecny
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation

config["reps"] = 1000
config["rounds"] = 1

ARabi_config = {"sigma": 0.05, "f_ge": qubit_frequency_center}

config = config | ARabi_config

qubit_gain = Qubit_Parameters[str(Qubit_Readout)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Qubit']['Frequency']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout)]['Pulse_FF']
config["FF_Qubits"][str(1)]["Gain_Pulse"] = FF_gain1_pulse
config["FF_Qubits"][str(2)]["Gain_Pulse"] = FF_gain2_pulse
config["FF_Qubits"][str(3)]["Gain_Pulse"] = FF_gain3_pulse
config["FF_Qubits"][str(4)]["Gain_Pulse"] = FF_gain4_pulse


number_of_steps = 2
config["reps"] = 3000
step = int(qubit_gain * 2 / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
                "sigma":ARabi_config["sigma"],"f_ge": qubit_frequency_center, "relax_delay": 250}
config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig
iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg,
                            outerFolder=outerFolder)
dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
avgi = dAmpRabi['data']['avgi'][0][0]
avgq = dAmpRabi['data']['avgq'][0][0]
i_ground, i_excited = avgi[0], avgi[1]
q_ground, q_excited = avgq[0], avgq[1]

i_data_range = np.abs(i_excited - i_ground)
q_data_range = np.abs(q_excited - q_ground)
if i_data_range > q_data_range:
    IData = True
    ADC_ground = i_ground
    ADC_excited = i_excited
else:
    IData = False
    ADC_ground = q_ground
    ADC_excited = q_excited


qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
config["FF_Qubits"][str(1)]["Gain_Pulse"] = FF_gain1_pulse
config["FF_Qubits"][str(2)]["Gain_Pulse"] = FF_gain2_pulse
config["FF_Qubits"][str(3)]["Gain_Pulse"] = FF_gain3_pulse
config["FF_Qubits"][str(4)]["Gain_Pulse"] = FF_gain4_pulse

config["reps"] = 1300
expt_cfg = {"start": 0, "step": int(1 * 16) , "expts": 300,
            "pi_gain": qubit_gain, "relax_delay": 160, 'f_ge': qubit_frequency_center
            }

config = config | expt_cfg
print(config)

config['IDataArray'] = [None, None, None, None]


# iOscillations = WalkFF(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder,
#                        I_Excited=i_excited, I_Ground=i_ground, Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = WalkFF.acquire(iOscillations)
# WalkFF.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# WalkFF.save_data(iOscillations, dOscillations)



qubit_index = 1 #1 indexed

expt_cfg = {"start": 0, "step": int(2 * 16), "expts": 100,
            "pi_gain": qubit_gain, "gainStart": -13000, "gainStop": -14000, "gainNumPoints": 11,
            "qubitIndex": qubit_index, "relax_delay": 150,
            }
# expt_cfg = {"start": 0, "step": int(1.5 * 16), "expts": 250,
#             "pi_gain": qubit_gain, "gainStart": -1000, "gainStop": 1000, "gainNumPoints": 81,
#             "qubitIndex": qubit_index, "relax_delay": 150,
#             }
config['f_ge'] = qubit_frequency_center


config['IDataArray'] = [None, None, None, None]
# config['IDataArray'] = [None, None, None, None]
config["reps"] = 50



config = config | expt_cfg
print(config)

RAvg = False

if not RAvg:
    iOscillations = Oscillations_Gain(path="QubitOscillations_GainSweep", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder, I_Excited=i_excited, I_Ground=i_ground,
                                      Q_Excited=q_excited, Q_Ground=q_ground)
    dOscillations = Oscillations_Gain.acquire(iOscillations)
    # Oscillations_Gain.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    Oscillations_Gain.save_data(iOscillations, dOscillations)
else:
    config['start'] = 4000#250 * 16
    config['step'] = 1
    config['expts'] = 300 * 16
    config['FFlength'] = 16  # must be 16
    config['reps'] = 50
    config['rounds'] = 1  # 30
    iOscillations = OscillationsR_Gain(path="QubitOscillationsR_GainSweep", cfg=config, soc=soc, soccfg=soccfg,
                                       outerFolder=outerFolder, I_Excited=i_excited, I_Ground=i_ground,
                                       Q_Excited=q_excited, Q_Ground=q_ground)
    dOscillations = OscillationsR_Gain.acquire(iOscillations)
    OscillationsR_Gain.save_data(iOscillations, dOscillations)

