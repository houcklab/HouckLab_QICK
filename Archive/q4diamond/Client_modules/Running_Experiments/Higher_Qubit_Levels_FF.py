# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF_HigherLevels import SpecSliceFF_HigherExc
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF_HigherLevels import AmplitudeRabiFF_HigherExc
from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift

#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# #Qubit 1
# yoko69.SetVoltage(-0.0676)
# yoko70.SetVoltage(0.0059)
# yoko71.SetVoltage(-0.0694)
# yoko72.SetVoltage(-0.0469)

#Qubit 2
# yoko69.SetVoltage(-0.374)
# yoko70.SetVoltage(-0.2878)
# yoko71.SetVoltage(-0.0637)
# yoko72.SetVoltage(-0.0572)


# #Qubit 3
yoko69.SetVoltage(0.2968)
yoko70.SetVoltage(0.0216)
yoko71.SetVoltage(-0.2999)
yoko72.SetVoltage(-0.0421)


# #Qubit 4
# yoko69.SetVoltage(-0.3738)
# yoko70.SetVoltage(0.0091)
# yoko71.SetVoltage(-0.069)
# yoko72.SetVoltage(0.3409)


# yoko69.SetVoltage(-0.1656)
# yoko70.SetVoltage(-0.1978)
# yoko71.SetVoltage(-0.0586)
# yoko72.SetVoltage(-0.0564)


#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.61, 'Gain': 8000}, 'Qubit01': {'Frequency': 4499.7, 'Gain': 790},
          'Qubit12': {'Frequency': 4343.6, 'Gain': 1830},
          'Pulse_FF': [0, 5000, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.44, 'Gain': 6000}, 'Qubit01': {'Frequency': 4389.73, 'Gain': 1650},
          'Qubit12': {'Frequency': 4231.8, 'Gain': 1160},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit01': {'Frequency': 4450, 'Gain': 2100},
          'Qubit12': {'Frequency': 4230.67, 'Gain': 1160},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7249.71, 'Gain': 6000}, 'Qubit01': {'Frequency': 4390.46, 'Gain': 2000},
          'Qubit12': {'Frequency': 4232.49, 'Gain': 1160},
          'Pulse_FF': [0, 0, 0, 0]}
    }

Qubit_Readout = 3
Qubit_Pulse = 3

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



FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
Spec_relevant_params = {"qubit_gain": 70, "SpecSpan": 4, "SpecNumPoints": 61, 'Gauss': True, "sigma": 0.05,
                    "gain": 500}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'],
                         "sigma": 0.05, "max_gain": 1100}

Run2ToneSpec_2nd = False
Spec_relevant_params_Higher = {"qubit_gain": 40, "SpecSpan": 5, "SpecNumPoints": 61, 'Gauss': False, "sigma": 0.05,
                    "gain": 1670}

RunAmplitudeRabi_2nd = False
Amplitude_Rabi_params_2nd = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'],
                         "sigma": 0.05, "max_gain": 2600}

RunT1 = False
RunT2 = False
T1T2_params = {"pi_gain": 820, "pi2_gain": 410}

RunChiShift = True
ChiShift_Params = {'pulse_expt': {'check_12': True},
                   'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'],
                   'qubit_gain01': Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain'],
                   'qubit_freq12': Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency'],
                   'qubit_gain12': Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']}


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}


cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']


qubit_gain01 = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
qubit_frequency_center01 = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']


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
    "qubit_gain01": qubit_gain01,
    "qubit_freq01": qubit_frequency_center01,
    "qubit_length": 40,
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
    config['sigma'] = Spec_relevant_params["sigma"]
    config['qubit_freq'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    if Spec_relevant_params['Gauss']:
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)

expt_cfg = {
    "step": 2 * Spec_relevant_params_Higher["SpecSpan"] / Spec_relevant_params_Higher["SpecNumPoints"],
    "start": Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency'] - Spec_relevant_params_Higher["SpecSpan"],
    "expts": Spec_relevant_params_Higher["SpecNumPoints"]
}
config = config | expt_cfg
if Run2ToneSpec_2nd:
    config["reps"] = 30  # want more reps and rounds for qubit data
    config["rounds"] = 30
    config["Gauss"] = Spec_relevant_params_Higher['Gauss']
    config['sigma'] = Spec_relevant_params_Higher["sigma"]
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    if Spec_relevant_params_Higher['Gauss']:
        config["qubit_gain"] = Spec_relevant_params_Higher['gain']
    Instance_specSlice = SpecSliceFF_HigherExc(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                               outerFolder=outerFolder)
    data_specSlice = SpecSliceFF_HigherExc.acquire(Instance_specSlice)
    SpecSliceFF_HigherExc.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    SpecSliceFF_HigherExc.save_data(Instance_specSlice, data_specSlice)

# Amplitude Rabi

if RunAmplitudeRabi:
    number_of_steps = 31
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": 300}
    config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
    iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
    AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)


if RunAmplitudeRabi_2nd:
    number_of_steps = 31
    step = int(Amplitude_Rabi_params_2nd["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params_2nd["sigma"],
                    "relax_delay": 300}
    config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    iAmpRabi = AmplitudeRabiFF_HigherExc(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF_HigherExc.acquire(iAmpRabi)
    AmplitudeRabiFF_HigherExc.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF_HigherExc.save_data(iAmpRabi, dAmpRabi)
config["sigma"] = Amplitude_Rabi_params["sigma"]

expt_cfg = {"start": 0, "step": 4, "expts": 40, "reps": 50, "rounds": 20,
            "pi_gain": T1T2_params["pi_gain"], "relax_delay": 300
            }

config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
#
if RunT1:
    iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT1 = T1FF.acquire(iT1)
    T1FF.display(iT1, dT1, plotDisp=True, figNum=2)
    T1FF.save_data(iT1, dT1)

T2R_cfg = {"start": 0, "step": 0.08, "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
           "expts": 85, "reps": 50, "rounds": 50, "pi_gain": T1T2_params["pi_gain"],
           "pi2_gain": T1T2_params["pi2_gain"], "relax_delay": 300, 'f_ge': qubit_frequency_center + 1.2
           }

config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunT2:
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)



if RunChiShift:
    config =  config | ChiShift_Params
    iChi = ChiShift(path="dataChiShift", cfg=config,soc=soc,soccfg=soccfg,
                                      outerFolder=outerFolder)
    dChi= ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)