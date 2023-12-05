# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_2nd_SSMUX import WalkFFSSMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_2nd_GainSweepMUX import Oscillations_Gain_2nd_SSMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFF_HigherLevelsMUX import SingleShotProgramFF_2StatesMUX

print(soc)

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# yoko69.SetVoltage(-0.1368)
# yoko70.SetVoltage(-0.1542)
# yoko71.SetVoltage(-0.2343)
# yoko72.SetVoltage(0.1055)

# yoko69.SetVoltage(-0.1167)
# yoko70.SetVoltage(-0.1266)
# yoko71.SetVoltage(-0.2437)
# yoko72.SetVoltage(0.1134)

yoko69.SetVoltage(0)
yoko70.SetVoltage(0)
yoko71.SetVoltage(0)
yoko72.SetVoltage(0)
#Reading out T1T2 parameters at physics frequency
mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {
        'Readout': {'Frequency': 6962.1 + 0.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': False},
        # 'Readout': {'Frequency': 6962.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
        #             "FF_Gains": [15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': False},
          'Qubit01': {'Frequency': 4688.7, 'Gain': 1100},
          'Qubit12': {'Frequency':4535.1, 'Gain': 850 * 0},
          'Pulse_FF': [9500, 0, 0, 0]},
    '2': {
        'Readout': {'Frequency': 7033.45 + 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700,
                    "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
        # 'Readout': {'Frequency': 7033.45 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #             "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01':  {'Frequency': 4811.2, 'Gain': 860},
          'Qubit12': {'Frequency': 4654.5, 'Gain': 1300},
          'Pulse_FF': [0, 13000, 0, 0]},
    '3': {
        'Readout': {'Frequency': 7104.5 + 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700,
                    "FF_Gains": [0, 0, 30000, 0], 'cavmin': True},
        # 'Readout': {'Frequency': 7104.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #             "FF_Gains": [0, 0, 30000, 0], 'cavmin': True},
          'Qubit01': {'Frequency': 4806.1, 'Gain': 980},
          'Qubit12': {'Frequency': 4649.5, 'Gain': 1470},
          'Pulse_FF': [0, 0, 15000, 0]},
    '4': {
        'Readout': {'Frequency': 7230. + 0.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
                    "FF_Gains": [0, 0, 0, -20000], 'cavmin': True}, #Optimize 12
        # 'Readout': {'Frequency': 7230. - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
        #             "FF_Gains": [0, 0, 0, -20000], 'cavmin': True}, #Optimize 12
          'Qubit01': {'Frequency': 4761.8, 'Gain': 1250},
          'Qubit12': {'Frequency': 4606.5, 'Gain': 2000},
          'Pulse_FF': [0, 0, 0, -13000]}
    }

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {
        'Readout': {'Frequency': 6962.3 - 0. - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
        'Readout': {'Frequency': 6962.3 - 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [15900, -10000, -9000, 10000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 4688.3, 'Gain': 1100},
          'Qubit12': {'Frequency':4534.8, 'Gain': 820},
          'Pulse_FF': [9500, 0, 0, 0]},
    '2': {
        'Readout': {'Frequency': 7033.4 + 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700,
                    "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
        # 'Readout': {'Frequency': 7033.45 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #             "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01':  {'Frequency': 4811.2, 'Gain': 860},
          'Qubit12': {'Frequency': 4654.5, 'Gain': 1300},
          'Pulse_FF': [0, 13000, 0, 0]},
    '3': {
        'Readout': {'Frequency': 7104.4 + 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700,
                    "FF_Gains": [0, 0, 30000, 0], 'cavmin': True},
        # 'Readout': {'Frequency': 7104.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #             "FF_Gains": [0, 0, 30000, 0], 'cavmin': True},
          'Qubit01': {'Frequency': 4806.1, 'Gain': 980},
          'Qubit12': {'Frequency': 4649.5, 'Gain': 1470},
          'Pulse_FF': [0, 0, 15000, 0]},
    '4': {
        # 'Readout': {'Frequency': 7230. + 0.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
        #             "FF_Gains": [0, 0, 0, -20000], 'cavmin': True}, #Optimize 12
        'Readout': {'Frequency': 7230.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                    "FF_Gains": [0, 0, 0, -20000], 'cavmin': True}, #Optimize 12
          'Qubit01': {'Frequency': 4761.8, 'Gain': 1250},
          'Qubit12': {'Frequency': 4606.5, 'Gain': 2000},
          'Pulse_FF': [0, 0, 0, -13000]}
    }

Qubit_Readout = [1]
Qubit_Pulse = 1


FF_gain1_expt = -20# 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0




swept_qubit_index = 1 #1 indexed

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 500, 'start': int(0 * 16), 'step': int(4 * 16), 'expts': 200, 'gainStart': -60,
                         'gainStop': 60, 'gainNumPoints': 13, 'relax_delay': 200}

Oscillation_Single = False
oscillation_single_dict = {'reps': 1500, 'start': int(0 * 16), 'step': int(0.5 * 16), 'expts': 300, 'relax_delay': 300}

SS_params_2States = {"ground": 1, 'excited': 2, "Shots": 4000, "Readout_Time": 2.5, "ADC_Offset": 0.3}



FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']


cavity_gain = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']

resonator_frequencies = [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout]
gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]
BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]

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
    "ff_freq": 0,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1,  ### MHz, span will be center+/- this parameter
    "relax_delay": 300,  ### in units us
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

config["shots"] = 2000
config['pulse_expt'] = {"pulse_01": False, "pulse_12": False}
config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Readout[0])]['Qubit01']['Frequency']
config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Readout[0])]['Qubit01']['Gain']
config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Readout[0])]['Qubit12']['Frequency']
config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Readout[0])]['Qubit12']['Gain']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout[0])]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

config["readout_length"] = SS_params_2States["Readout_Time"]  # us (length of the pulse applied)
config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]

Instance_SingleShotProgram = SingleShotProgramFF_2StatesMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                         soc=soc, soccfg=soccfg)
data_SingleShotProgram = SingleShotProgramFF_2StatesMUX.acquire(Instance_SingleShotProgram,
                                                             ground_pulse=SS_params_2States["ground"],
                                                             excited_pulse=SS_params_2States["excited"])
data_SingleShotProgram = SingleShotProgramFF_2StatesMUX.analyze(Instance_SingleShotProgram, data_SingleShotProgram)

SingleShotProgramFF_2StatesMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

SingleShotProgramFF_2StatesMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
SingleShotProgramFF_2StatesMUX.save_config(Instance_SingleShotProgram)
angle, threshold = data_SingleShotProgram['angle'], data_SingleShotProgram['threshold']
print(angle, threshold)


config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

if Oscillation_Gain:
    config["reps"] = oscillation_gain_dict['reps']
    expt_cfg = {"start": oscillation_gain_dict['start'], "step": oscillation_gain_dict['step'],
                "expts": oscillation_gain_dict['expts'],
                "pi_gain": qubit_gain, "gainStart": oscillation_gain_dict['gainStart'],
                "gainStop": oscillation_gain_dict['gainStop'], "gainNumPoints": oscillation_gain_dict['gainNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_gain_dict['relax_delay'],
                }
    config['IDataArray'] = [1, None, None, None]
    config = config | expt_cfg

    iOscillations = Oscillations_Gain_2nd_SSMUX(path="QubitOscillations_GainSweep_2nd", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = Oscillations_Gain_2nd_SSMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    # Oscillations_Gain_2nd_SS.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    Oscillations_Gain_2nd_SSMUX.save_data(iOscillations, dOscillations)


if Oscillation_Single:
    config["reps"] = oscillation_single_dict['reps']
    expt_cfg = {"start": oscillation_single_dict['start'], "step": oscillation_single_dict['step'],
                "expts": oscillation_single_dict['expts'], "relax_delay": oscillation_single_dict['relax_delay']}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']

    config["FF_Qubits"]['1']['Gain_Expt'] = FF_gain1_expt
    config["FF_Qubits"]['2']['Gain_Expt'] = FF_gain2_expt
    config["FF_Qubits"]['3']['Gain_Expt'] = FF_gain3_expt
    config["FF_Qubits"]['4']['Gain_Expt'] = FF_gain4_expt
    #
    config = config | expt_cfg
    config['IDataArray'] = [1, None, None, None]

    iOscillations = WalkFFSSMUX(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dOscillations = WalkFFSSMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    WalkFFSSMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    WalkFFSSMUX.save_data(iOscillations, dOscillations)
print(config)
#
# config['IDataArray'] = [None, None, None, None]


# iOscillations = WalkFF(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder,
#                        I_Excited=i_excited, I_Ground=i_ground, Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = WalkFF.acquire(iOscillations)
# WalkFF.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# WalkFF.save_data(iOscillations, dOscillations)


# config["reps"] = 1300
# expt_cfg = {"start": 0, "step": int(1 * 16) , "expts": 300,
#             "pi_gain": qubit_gain, "relax_delay": 160, 'f_ge': qubit_frequency_center
#             }
#
# config = config | expt_cfg
# print(config)
#
# config['IDataArray'] = [None, None, None, None]


# iOscillations = WalkFF(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder,
#                        I_Excited=i_excited, I_Ground=i_ground, Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = WalkFF.acquire(iOscillations)
# WalkFF.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# WalkFF.save_data(iOscillations, dOscillations)

# qubit_index = 2
# expt_cfg = {"start": 0, "step": int(4 * 16), "expts": 100,
#             "pi_gain": qubit_gain, "gainStart": -400, "gainStop": 0, "gainNumPoints": 25,
#             "qubitIndex": qubit_index, "relax_delay": 150,
#             }
# config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
# config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
# config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
# config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
#
# config['IDataArray'] = [1, None, None, None]
#
# config = config | expt_cfg
#
# iOscillations = Oscillations_Gain_2nd(path="QubitOscillations_GainSweep_2nd", cfg=config, soc=soc, soccfg=soccfg,
#                                   outerFolder=outerFolder, I_Excited=1, I_Ground=0,
#                                   Q_Excited=1, Q_Ground=0)
# dOscillations = Oscillations_Gain_2nd.acquire(iOscillations)
# # Oscillations_Gain_2nd.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# Oscillations_Gain_2nd.save_data(iOscillations, dOscillations)




# ARabi_config = {"sigma": 0.05, "f_ge": qubit_frequency_center}
#
# # config = config | ARabi_config
#
# qubit_gain = Qubit_Parameters[str(Qubit_Readout)]['Qubit']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Qubit']['Frequency']
# FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout)]['Pulse_FF']
# config["FF_Qubits"][str(1)]["Gain_Pulse"] = FF_gain1_pulse
# config["FF_Qubits"][str(2)]["Gain_Pulse"] = FF_gain2_pulse
# config["FF_Qubits"][str(3)]["Gain_Pulse"] = FF_gain3_pulse
# config["FF_Qubits"][str(4)]["Gain_Pulse"] = FF_gain4_pulse

#
# number_of_steps = 2
# config["reps"] = 3000
# step = int(qubit_gain * 2 / number_of_steps)
# ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
#                 "sigma":ARabi_config["sigma"],"f_ge": qubit_frequency_center, "relax_delay": 250}
# config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig
# iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg,
#                             outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
# AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
# avgi = dAmpRabi['data']['avgi'][0][0]
# avgq = dAmpRabi['data']['avgq'][0][0]
# i_ground, i_excited = avgi[0], avgi[1]
# q_ground, q_excited = avgq[0], avgq[1]
#
# i_data_range = np.abs(i_excited - i_ground)
# q_data_range = np.abs(q_excited - q_ground)
# if i_data_range > q_data_range:
#     IData = True
#     ADC_ground = i_ground
#     ADC_excited = i_excited
# else:
#     IData = False
#     ADC_ground = q_ground
#     ADC_excited = q_excited


# qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
# FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
# config["FF_Qubits"][str(1)]["Gain_Pulse"] = FF_gain1_pulse
# config["FF_Qubits"][str(2)]["Gain_Pulse"] = FF_gain2_pulse
# config["FF_Qubits"][str(3)]["Gain_Pulse"] = FF_gain3_pulse
# config["FF_Qubits"][str(4)]["Gain_Pulse"] = FF_gain4_pulse

# config["reps"] = 1300
# expt_cfg = {"start": 0, "step": int(1 * 16) , "expts": 300,
#             "pi_gain": qubit_gain, "relax_delay": 160, 'f_ge': qubit_frequency_center
#             }
#
# config = config | expt_cfg
# print(config)
#
# config['IDataArray'] = [None, None, None, None]


# iOscillations = WalkFF(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder,
#                        I_Excited=i_excited, I_Ground=i_ground, Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = WalkFF.acquire(iOscillations)
# WalkFF.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# WalkFF.save_data(iOscillations, dOscillations)


#
# qubit_index = 1 #1 indexed
#
# expt_cfg = {"start": 4000, "step": int(1 * 16), "expts": 300,
#             "pi_gain": qubit_gain, "gainStart": -50, "gainStop": 250, "gainNumPoints": 7,
#             "qubitIndex": qubit_index, "relax_delay": 150,
#             }
# # expt_cfg = {"start": 0, "step": int(1.5 * 16), "expts": 250,
# #             "pi_gain": qubit_gain, "gainStart": -1000, "gainStop": 1000, "gainNumPoints": 81,
# #             "qubitIndex": qubit_index, "relax_delay": 150,
# #             }
# config['f_ge'] = qubit_frequency_center
#
#
# config['IDataArray'] = [None, None, None, None]
# # config['IDataArray'] = [None, None, None, None]
# config["reps"] = 50
#
#
#
# config = config | expt_cfg
# print(config)
#
# iOscillations = Oscillations_Gain(path="QubitOscillations_GainSweep", cfg=config, soc=soc, soccfg=soccfg,
#                                   outerFolder=outerFolder, I_Excited=i_excited, I_Ground=i_ground,
#                                   Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = Oscillations_Gain.acquire(iOscillations)
# Oscillations_Gain.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# Oscillations_Gain.save_data(iOscillations, dOscillations)
#

