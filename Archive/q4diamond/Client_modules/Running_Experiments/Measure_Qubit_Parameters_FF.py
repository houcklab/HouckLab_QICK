# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
from q4diamond.Client_modules.Experiment_Scripts.T2_Measurement_FF import T2FF

#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# #Qubit 1:
# yoko69.SetVoltage(-0.126)
# yoko70.SetVoltage(0.0171)
# yoko71.SetVoltage(-0.0514)
# yoko72.SetVoltage(-0.0493)

# #Qubit 2:
# yoko69.SetVoltage(-0.2748)
# yoko70.SetVoltage(-0.2268)
# yoko71.SetVoltage(-0.0448)
# yoko72.SetVoltage(-0.055)

# #Qubit 3
# yoko69.SetVoltage(0.2968)
# yoko70.SetVoltage(0.0216)
# yoko71.SetVoltage(-0.2999)
# yoko72.SetVoltage(-0.0421)

#Qubit 4:
# yoko69.SetVoltage(-0.2756)
# yoko70.SetVoltage(0.0217)
# yoko71.SetVoltage(-0.0499)
# yoko72.SetVoltage(0.2457)

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.51, 'Gain': 10000}, 'Qubit': {'Frequency': 4450.2, 'Gain': 880},
          'Pulse_FF': [0, 0, 0, 0]},
    # '2': {'Readout': {'Frequency': 7055.45, 'Gain': 6000}, 'Qubit': {'Frequency': 4403.6, 'Gain': 1300},
    #       'Pulse_FF': [0, 0, 0, -8000]},
    '2': {'Readout': {'Frequency': 7055.8, 'Gain': 6000}, 'Qubit': {'Frequency': 4449.8, 'Gain': 1110},
          'Pulse_FF': [0, 0, 0, 0]},
    # '3': {'Readout': {'Frequency': 7117.04, 'Gain': 6000}, 'Qubit': {'Frequency': 4400.6, 'Gain': 1450},
    #       'Pulse_FF': [6000, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.05, 'Gain': 6000}, 'Qubit': {'Frequency': 4449.2, 'Gain': 1730},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7249.77, 'Gain': 6000}, 'Qubit': {'Frequency': 4448.7, 'Gain': 1160},
          'Pulse_FF': [0, 0, 0, 0]}
    }



# Qubit 1
# yoko69.SetVoltage(-0.3186)
# yoko70.SetVoltage(0.0603)
# yoko71.SetVoltage(-0.008)
# yoko72.SetVoltage(-0.1089)

# Qubit 2
# yoko69.SetVoltage(-0.0718)
# yoko70.SetVoltage(-0.0707)
# yoko71.SetVoltage(0.0015)
# yoko72.SetVoltage(-0.1032)

# Qubit 3
# yoko69.SetVoltage(-0.0818)
# yoko70.SetVoltage(0.1114)
# yoko71.SetVoltage(-0.1003)
# yoko72.SetVoltage(-0.1615)

# Qubit 4
yoko69.SetVoltage(0)
yoko70.SetVoltage(0)
yoko71.SetVoltage(0)
yoko72.SetVoltage(0)

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.45, 'Gain': 7000, "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit': {'Frequency':  4770.8, 'Gain': 890},
          'Pulse_FF': [0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7056.0, 'Gain': 6500, "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit': {'Frequency': 4716.6, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.9, 'Gain': 8000, "FF_Gains": [0, 0, 0, 0]},
          'Qubit': {'Frequency': 4818, 'Gain': 1280},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7250.2, 'Gain': 6500, "FF_Gains": [0, 0, 0, 0]},
          'Qubit': {'Frequency': 4798, 'Gain': 1170},
          'Pulse_FF': [0, 0, 0, 0]}
    }
# Readout
FF_gain1 = 0  # 8000
FF_gain2 = 0
FF_gain3 = 0
FF_gain4 = 0

# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

Qubit_Readout = 4
Qubit_Pulse = 4

FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

RunTransmissionSweep = True  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain":60, "SpecSpan": 5, "SpecNumPoints": 61, 'Gauss': False, "sigma": 0.05,
                        "gain": 800}

# RunAmplitudeRabi = False
# Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
#                          "sigma": 0.05, "max_gain": 1900}

RunT1 = False
RunT2 = False
RunT2FF = False
#Qubit 1
T1T2_params = {"pi_gain": 620, "pi2_gain": 310, 't1step': 4, 't1expt': 80,
               't2step': 0.2, 't2expt': 60, 't2freqdiff': 0.8,
               'T2FFstep': int(85 * 16), 'T2FFexpts': 40}
# #Qubit 2
# T1T2_params = {"pi_gain": 900, "pi2_gain": 450, 't1step': 4, 't1expt': 80,
#                't2step': 0.15, 't2expt': 60, 't2freqdiff': 0.9,
#                'T2FFstep': int(85 * 16), 'T2FFexpts': 60}

# #Qubit 3
T1T2_params = {"pi_gain": 1000, "pi2_gain": 500, 't1step': 4, 't1expt': 80,
               't2step': 0.1, 't2expt': 60, 't2freqdiff': 1,
               'T2FFstep': int(85 * 16), 'T2FFexpts': 60}
#
# #Qubit 4
T1T2_params = {"pi_gain": 950, "pi2_gain": 475, 't1step': 4, 't1expt': 80,
               't2step': 0.2, 't2expt': 60, 't2freqdiff': 0.7,
               'T2FFstep': int(85 * 16), 'T2FFexpts': 60}

FF_gain1_init = 0  # 8000
FF_gain2_init = 0
FF_gain3_init = 0
FF_gain4_init = 0

# RunChiShift = False
# ChiShift_Params = {'pulse_expt': {'check_12': False},
#                    'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'], 'qubit_gain01': T1T2_params['pi_gain'],
#                    'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],  'qubit_gain12': 0}


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse, 'Gain_Init': FF_gain1_init}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse, 'Gain_Init': FF_gain2_init}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse, 'Gain_Init': FF_gain3_init}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse, 'Gain_Init': FF_gain4_init}


cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']


# FF_Qubits[str(Swept_Qubit)]['Gain_Readout'] = Swept_Qubit_Gain
# FF_Qubits[str(Swept_Qubit)]['Gain_Expt'] = Swept_Qubit_Gain
# FF_Qubits[str(Qubit_Readout)]['Gain_Readout'] = Read_Qubit_Gain
# FF_Qubits[str(Qubit_Readout)]['Gain_Expt'] = Read_Qubit_Gain
# for i in range(4):
#     if i + 1 == Swept_Qubit or i + 1 == Qubit_Readout:
#         continue
#     FF_Qubits[str(i + 1)]['Gain_Readout'] = Bias_Qubit_Gain
#     FF_Qubits[str(i + 1)]['Gain_Expt'] = Bias_Qubit_Gain
#
# print(FF_Qubits)


trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61,  ### number of points in the transmission frequecny
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
    "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

UpdateConfig = trans_config | qubit_config | expt_cfg
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
if RunTransmissionSweep:
    config["reps"] = 20  # fast axis number of points
    config["rounds"] = 20  # slow axis number of points
    Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    # update the transmission frequency to be the peak
    if cavity_min:
        config["pulse_freq"] = Instance_trans.peakFreq_min
    else:
        config["pulse_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", config["pulse_freq"])
else:
    print("Cavity frequency set to: ", config["pulse_freq"])

# qubit spec experiment
if Run2ToneSpec:
    config["reps"] = 30  # want more reps and rounds for qubit data
    config["rounds"] = 30
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)

# Amplitude Rabi
number_of_steps = 31
step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                "relax_delay": 300}
config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunAmplitudeRabi:
    iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
    AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)

expt_cfg = {"start": 0, "step": T1T2_params['t1step'], "expts": T1T2_params['t1expt'], "reps": 50, "rounds": 30,
            "pi_gain": T1T2_params["pi_gain"], "relax_delay": 300
            }

config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
#
if RunT1:
    iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT1 = T1FF.acquire(iT1)
    T1FF.display(iT1, dT1, plotDisp=True, figNum=2)
    T1FF.save_data(iT1, dT1)

T2R_cfg = {"start": 0, "step": T1T2_params['t2step'], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
           "expts": T1T2_params['t2expt'], "reps": 50, "rounds": 50, "pi_gain": T1T2_params["pi_gain"],
           "pi2_gain": T1T2_params["pi2_gain"], "relax_delay": 300,
           'f_ge': qubit_frequency_center + T1T2_params["t2freqdiff"]
           }

config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunT2:
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)

T2R_cfg = {"start": 0, "step": T1T2_params['T2FFstep'], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
           "expts": T1T2_params['T2FFexpts'], "reps": 50, "rounds": 20, "pi_gain": T1T2_params["pi_gain"],
           "pi2_gain": T1T2_params["pi2_gain"], "relax_delay": 300,
           'f_ge': qubit_frequency_center + T1T2_params["t2freqdiff"]
           }

config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
config['IDataArray'] = [1, None, None, None]

if RunT2FF:
    iT2R = T2FF(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2FF.acquire(iT2R)
    T2FF.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2FF.save_data(iT2R, dT2R)



if RunChiShift:
    config =  config | ChiShift_Params
    iChi = ChiShift(path="dataChiShift", cfg=config,soc=soc,soccfg=soccfg,
                                      outerFolder=outerFolder)
    dChi= ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)