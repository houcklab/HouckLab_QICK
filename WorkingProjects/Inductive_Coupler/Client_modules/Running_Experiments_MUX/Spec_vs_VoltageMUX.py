# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecVsQblox_MUX import SpecVsQblox
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransVsQblox_MUX import TransVsQblox
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransVsPower_MUX import TransVsPower
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecVsResonatorPower_MUX import SpecVsResonatorPower

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import \
    AmplitudeRabiFFMUX

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import \
    SingleShotProgramFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX

mixer_freq = 500
print(BaseConfig["cavity_LO"] / 1e6)
BaseConfig["mixer_freq"] = mixer_freq
BaseConfig["has_mixer"] = True
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6978.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 15000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4441.5, 'Gain': 4800},
          'Pulse_FF': [0, 0, 0, 0]},  # second index
    '2': {'Readout': {'Frequency': 7269.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 9000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4280, 'Gain': 3380},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7524.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6,
                      'Gain': 5500, "FF_Gains": [0, 0, 8000, 0]},
          'Qubit': {'Frequency': 4400, 'Gain': 1420},
          'Pulse_FF': [0, 0, 3899, 0]},
    '4': {'Readout': {'Frequency': 7459.65 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4238.8, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7305.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
              'Qubit': {'Frequency': 4700, 'Gain': 7500},
              'Pulse_FF': [0, 0, 0, 0]},
    }

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7322.56 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7200,
                      "FF_Gains": [0, 0, 12000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4639.0, 'Gain': 2828},
          'Qubit12': {'Frequency': 4452.9, 'Gain': 1130},
          'Pulse_FF': [0, 0, 9000, 0]},
    '2': {'Readout': {'Frequency': 7269.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                      "FF_Gains": [0, 0, 12000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4315.4, 'Gain': 4590},
          'Qubit12': {'Frequency': 4330.4, 'Gain': 1700},
          'Pulse_FF': [0, 0, 9000, 0]},
    '3': {'Readout': {'Frequency': 7525.55 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4320,
                      "FF_Gains": [0, 0, 12000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4867.0, 'Gain': 1700},
          'Qubit12': {'Frequency': 4686.0, 'Gain': 1700},
          'Pulse_FF': [0, 0, 9000, 0]},
}

#Hybridization of Q1 and Q3, with Q2 far, to find T1 & T2 of + and -
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 7321.45 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7200,
#                       "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
#           'Qubit': {'Frequency': 4390, 'Gain': 2828},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '3': {'Readout': {'Frequency': 7524.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4320,
#                       "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
#           'Qubit': {'Frequency': 4390, 'Gain': 1700},
#           'Pulse_FF': [0, 0, 0, 0]},
# }


Qubit_Parameters = {
    # Locations for readout and readout fidelity characterization
    '1': {'Readout': {'Frequency': 7322.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [-4500, -9000, 15000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5032.5, 'Gain': 1150},
          'Pulse_FF': [-4500, -9000, 15000, 0]},
    '2': {'Readout': {'Frequency': 7269.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6200,
                      "FF_Gains": [-5500, -9000, 15000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4614.9, 'Gain': 2575},
          'Pulse_FF': [-4500, -9000, 15000, 0]},
    '3': {'Readout': {'Frequency': 7526.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                      "FF_Gains": [-5500, -9000, 15000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5373.5, 'Gain': 1340},
          'Pulse_FF': [-4500, -9000, 15000, 0]},
    '5': {'Readout': {'Frequency': 7305.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [-4500, -9000, 15000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4746.6, 'Gain': 1350},
          'Pulse_FF': [-4500, -9000, 15000, 0]},
    # Location for preparing the 3 eigenstates
    'A': {'Qubit': {'Frequency': 5028.25, 'Gain': 1050},
          'Pulse_FF': [0, -4000, 1400, 0]},
    'B': {'Qubit': {'Frequency': 5081.3, 'Gain': 1716},
          'Pulse_FF': [0, -4000, 1400, 0]},
    'C': {'Qubit': {'Frequency': 4975.6, 'Gain': 1630},
          'Pulse_FF': [0, -4000, 1400, 0]}
    }


Qubit_Parameters = {
    # Locations for readout and readout fidelity characterization
    '1': {'Readout': {'Frequency': 7322.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [-4500, -9000, 8000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5032.5, 'Gain': 1150},
          'Pulse_FF': [-4500, -9000, 8000, 0]},
    '2': {'Readout': {'Frequency': 7270.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4000,
                      "FF_Gains": [0, 5000, -5000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4525.3, 'Gain': 1350},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7525.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 5000, -5000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4485, 'Gain': 1400},
          'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7305.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [-4500, -9000, 8000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4746.6, 'Gain': 1350},
          'Pulse_FF': [-4500, -9000, 8000, 0]},
    # Location for preparing the 3 eigenstates
    'A': {'Qubit': {'Frequency': 5028.25, 'Gain': 1050},
          'Pulse_FF': [0, -4000, 1400, 0]},
    'B': {'Qubit': {'Frequency': 5032.5, 'Gain': 1540},
          'Pulse_FF': [0, -4000, -965, 0]},
    'C': {'Qubit': {'Frequency': 4975.6, 'Gain': 1630},
          'Pulse_FF': [0, -4000, 1400, 0]}
    }

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6978.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 11000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4401.7, 'Gain': 10000},
          'Pulse_FF': [0, 0, 0, 0]},  #second index'
    '2': {'Readout': {'Frequency': 7095.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4500, 'Gain': 3400},
          'Pulse_FF':[0, 0, 0, 0]}, #Third index
    '3': {'Readout': {'Frequency': 7526.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4500,
                      "FF_Gains": [-7000, -9000, 15000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 5081.3, 'Gain': 1716},
          'Pulse_FF': [0, -4000, 1400, 0]},
    '5': {'Readout': {'Frequency': 7305.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [-7000, -9000, 15000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4970.3, 'Gain': 1600},
          'Pulse_FF': [0, -4000, 1400, 0]}
}




# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

Q = 2
Qubit_Readout = [Q]
Qubit_Pulse = Q
Qubit_PulseSS = [Q]


FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']


gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]

RunTransmissionSweep = False # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 1, "SpecSpan": 5, "SpecNumPoints": 71, 'Gauss': False, "sigma": 0.01,
                        "gain": 8000, 'reps': 15, 'rounds': 15}

Run_Spec_v_Voltage = True
Spec_sweep_relevant_params = {"qubit_gain": 500, "SpecSpan": 50, "SpecNumPoints": 101,
                              "DAC": [10],
                              "Qblox_Vmin": [0.6],
                              "Qblox_Vmax": [0.7], "Qblox_numpoints": 21,
                              'reps': 30, 'rounds': 30, 'smart_normalize': True}

Run_Trans_v_Voltage = False
Trans_sweep_relevant_params = {
    "reps": 100, "readout_length": 3,  # [us]
    "TransSpan": 3,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61 * 1,  ### number of points in the transmission frequecny
    "cav_relax_delay": 5
}
Run_Trans_v_Power = False
Trans_power_relevant_params = {"gain_min": [2000],
                              "gain_max": [12000], "gain_numpoints": 11}

Run_Spec_v_ResonatorGain = False
Spec_ResonatorGain_relevant_params = {"gain_min": [1000],
                              "gain_max": [1040], "gain_numpoints": 31}


RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "sigma": 0.05, "max_gain": 3000}

SingleShot =False
SS_params = {"Shots": 2000, "Readout_Time": 2.5, "ADC_Offset": 0.3, "Qubit_Pulse": Qubit_PulseSS}


SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 500, "gain_stop": 6000, "gain_pts": 7, "span": 1.2, "trans_pts": 7}

SingleShot_QubitOptimize = False
SS_Q_params = {"Optimize_Index": 0, "q_gain_span": 1000, "q_gain_pts": 9, "q_freq_span": 4, "q_freq_pts": 7}

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

cavity_gain = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
resonator_frequencies = [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout]

trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 3,  # [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "pulse_gains": gains,  # [DAC units]
    "pulse_freqs": resonator_frequencies,
    "TransSpan": 1.5 * 1,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61 * 1,  ### number of points in the transmission frequecny
    "cav_relax_delay": 30
}
qubit_config = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 100,
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
}
expt_cfg = {
    "step": 2 * qubit_config["SpecSpan"] / (qubit_config["SpecNumPoints"] - 1),
    "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

print(expt_cfg)

UpdateConfig = trans_config | qubit_config | expt_cfg
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
if RunTransmissionSweep:
    config["reps"] = 20  # fast axis number of points
    config["rounds"] = 20  # slow axis number of points
    Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                     outerFolder=outerFolder)
    data_trans = CavitySpecFFMUX.acquire(Instance_trans)
    CavitySpecFFMUX.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFFMUX.save_data(Instance_trans, data_trans)
    # update the transmission frequency to be the peak
    print('freqs before: ', config["pulse_freqs"])

    if Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['cavmin']:
        config["pulse_freqs"][0] += Instance_trans.peakFreq_min - mixer_freq
        config["mixer_freq"] = Instance_trans.peakFreq_min
    else:
        config["pulse_freqs"][0] += Instance_trans.peakFreq_max - mixer_freq + 0.3
        config["mixer_freq"] = Instance_trans.peakFreq_max

    print('min freq; ', Instance_trans.peakFreq_min)
    print('freqs after: ', config["pulse_freqs"])
    print("Cavity frequency found at: ", config["pulse_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)
else:
    print("Cavity frequency set to: ", config["pulse_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)

# qubit spec experiment
if Run2ToneSpec:
    config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                             outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFFMUX.acquire(Instance_specSlice)
    QubitSpecSliceFFMUX.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFFMUX.save_data(Instance_specSlice, data_specSlice)

if Run_Spec_v_Voltage:
    # config["reps"] = 30  # want more reps and rounds for qubit data
    # config["rounds"] = 30
    config["reps"] = Spec_sweep_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_sweep_relevant_params['rounds']
    config["qbloxNumPoints"] = Spec_sweep_relevant_params["Qblox_numpoints"]
    config['sleep_time'] = 0
    config['DACs'] = Spec_sweep_relevant_params["DAC"]
    config["qbloxStart"] = Spec_sweep_relevant_params["Qblox_Vmin"]
    config["qbloxStop"] = Spec_sweep_relevant_params["Qblox_Vmax"]

    config["Gauss"] = False

    config["qubit_gain"] = Spec_sweep_relevant_params["qubit_gain"]
    config["step"] = 2 * Spec_sweep_relevant_params["SpecSpan"] / (Spec_sweep_relevant_params["SpecNumPoints"] - 1)
    config["start"] = qubit_config["qubit_freq"] - Spec_sweep_relevant_params["SpecSpan"]
    config["expts"] = Spec_sweep_relevant_params["SpecNumPoints"]
    # expt_cfg = {
    #     "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    #     "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    #     "expts": qubit_config["SpecNumPoints"]
    # }

    Instance_SpecVQ = SpecVsQblox(path="SpecVsQblox", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
    data_SpecVQ = SpecVsQblox.acquire(Instance_SpecVQ, plotDisp=True,
                                      smart_normalize=Spec_sweep_relevant_params['smart_normalize'])
    # print(data_SingleShotProgram)
    # SpecVsQblox.display(Instance_SpecVQ, data_SpecVQ, plotDisp=False)

    SpecVsQblox.save_data(Instance_SpecVQ, data_SpecVQ)
    SpecVsQblox.save_config(Instance_SpecVQ)

if Run_Trans_v_Voltage:
    # config["reps"] = 30  # want more reps and rounds for qubit data
    # config["rounds"] = 30
    config |= Trans_sweep_relevant_params
    config["rounds"] = 1
    config["qbloxNumPoints"] = Spec_sweep_relevant_params["Qblox_numpoints"]
    config['sleep_time'] = 0
    config['DACs'] = Spec_sweep_relevant_params["DAC"]
    config["qbloxStart"] = Spec_sweep_relevant_params["Qblox_Vmin"]
    config["qbloxStop"] = Spec_sweep_relevant_params["Qblox_Vmax"]

    config["Gauss"] = False

    config["qubit_gain"] = Spec_sweep_relevant_params["qubit_gain"]
    config["step"] = 2 * Spec_sweep_relevant_params["SpecSpan"] / (Spec_sweep_relevant_params["SpecNumPoints"] - 1)
    config["start"] = qubit_config["qubit_freq"] - Spec_sweep_relevant_params["SpecSpan"]
    config["expts"] = Spec_sweep_relevant_params["SpecNumPoints"]
    # expt_cfg = {
    #     "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    #     "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    #     "expts": qubit_config["SpecNumPoints"]
    # }

    Instance_TransVQ = TransVsQblox(path="TransVsQblox", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
    data_TransVQ = TransVsQblox.acquire(Instance_TransVQ, plotDisp=True,
                                      smart_normalize=Spec_sweep_relevant_params['smart_normalize'])
    # print(data_SingleShotProgram)
    # SpecVsQblox.display(Instance_SpecVQ, data_SpecVQ, plotDisp=False)

    TransVsQblox.save_data(Instance_TransVQ, data_TransVQ)
    TransVsQblox.save_config(Instance_TransVQ)

if Run_Trans_v_Power:
    config |= Trans_sweep_relevant_params
    config["rounds"] = 1
    config["gainNumPoints"] = Trans_power_relevant_params["gain_numpoints"]
    config['sleep_time'] = 0
    config["gainStart"] = Trans_power_relevant_params["gain_min"]
    config["gainStop"] = Trans_power_relevant_params["gain_max"]

    config["Gauss"] = False

    config["qubit_gain"] = Spec_sweep_relevant_params["qubit_gain"]
    config["step"] = 2 * Spec_sweep_relevant_params["SpecSpan"] / (Spec_sweep_relevant_params["SpecNumPoints"] - 1)
    config["start"] = qubit_config["qubit_freq"] - Spec_sweep_relevant_params["SpecSpan"]
    config["expts"] = Spec_sweep_relevant_params["SpecNumPoints"]


    Instance_TransVG = TransVsPower(path="TransVsPower", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
    data_TransVG = TransVsPower.acquire(Instance_TransVG, plotDisp=True,
                                      smart_normalize=Spec_sweep_relevant_params['smart_normalize'])

    TransVsPower.save_data(Instance_TransVG, data_TransVG)
    TransVsPower.save_config(Instance_TransVG)

if Run_Spec_v_ResonatorGain:
    config["gainNumPoints"] = Spec_ResonatorGain_relevant_params["gain_numpoints"]
    config['sleep_time'] = 0
    config["gainStart"] = Spec_ResonatorGain_relevant_params["gain_min"]
    config["gainStop"] = Spec_ResonatorGain_relevant_params["gain_max"]

    config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']

    Instance_SpecVG = SpecVsResonatorPower(path="SpecVsResonatorGain", outerFolder=outerFolder, cfg=config, soc=soc,
                                    soccfg=soccfg)
    data_SpecVG = SpecVsResonatorPower.acquire(Instance_SpecVG, plotDisp=True,
                                        smart_normalize=Spec_sweep_relevant_params['smart_normalize'])

    SpecVsResonatorPower.save_data(Instance_SpecVG, data_SpecVG)
    SpecVsResonatorPower.save_config(Instance_SpecVG)

# Amplitude Rabi
number_of_steps = 31
step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 30,
                "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                "relax_delay": 200}
config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunAmplitudeRabi:
    iAmpRabi = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFFMUX.acquire(iAmpRabi)
    AmplitudeRabiFFMUX.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFFMUX.save_data(iAmpRabi, dAmpRabi)

qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]

UpdateConfig = {
    ###### cavity
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const",  # --Fixed
    "readout_length": SS_params["Readout_Time"],  # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
    # "pulse_gain": cavity_gain, # [DAC units]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "pulse_gains": gains,  # [DAC units]
    "pulse_freqs": resonator_frequencies,
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": config["sigma"],  ### units us, define a 20ns sigma
    "qubit_gain": qubit_gain,
    "f_ge": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    ##### define shots
    "shots": SS_params["Shots"],  ### this gets turned into "reps"
    "relax_delay": 200,  # us
}

config = BaseConfig | UpdateConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout

print(config)
if SingleShot:
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config, soc=soc,
                                                        soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)

if SingleShot_ReadoutOptimize:
    span = SS_R_params['span']
    cav_gain_start = SS_R_params['gain_start']
    cav_gain_stop = SS_R_params['gain_stop']
    cav_gain_pts = SS_R_params['gain_pts']
    cav_trans_pts = SS_R_params['trans_pts']

    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": config["mixer_freq"] - span / 2,  # 249.6,
        "trans_freq_stop": config["mixer_freq"] + span / 2,  # 250.3,
        "TransNumPoints": cav_trans_pts,
    }
    config = config | exp_parameters
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                                                           cfg=config, soc=soc, soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize,
                                                                      )
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFFMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFFMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFFMUX.save_config(Instance_SingleShotOptimize)

if SingleShot_QubitOptimize:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    Qubit_Pulse_Index = SS_Q_params['Optimize_Index']
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": qubit_gains[Qubit_Pulse_Index] - q_gain_span / 2,
        "qubit_gain_Stop": qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span / 2,  # 249.6,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span / 2,  # 250.3,
        "QubitNumPoints": q_freq_pts,
    }
    config = config | exp_parameters
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                                                 cfg=config, soc=soc, soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize,
                                                                            Qubit_Sweep_Index=Qubit_Pulse_Index)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFFMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFFMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFFMUX.save_config(Instance_SingleShotOptimize)
