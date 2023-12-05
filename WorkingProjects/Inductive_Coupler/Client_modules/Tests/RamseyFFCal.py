import numpy as np
from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibrationR import RamseyFFCalR
import socket

# Save path
if 'Euler' in socket.gethostname() or 'euler' in socket.gethostname():
    outerFolder = "/Volumes/ourphoton-1/Christie/202210_Rhombus/"
else:
    outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

# [Normally Yoko parameters would get set here]

# Qubit 1 (Left)
resonator_frequency_center = 0  # 6952.45  # [MHz] offset from "cavity_LO" = 7e9
qubit_frequency_center = 4365.95  # 4516  # 4200  # 4599 + 100  # [MHz]
# qubit_frequency_center = 4582.5  # 4516  # 4200  # 4599 + 100  # [MHz]
cavity_gain = 10000
cavity_attenuation = 0

# Qubit 2 (Top)
# resonator_frequency_center = 556.9
# cavity_attenuation = 20 #12
# qubit_frequency_center = 5217.4

# Qubit 3 (Bottom)
# resonator_frequency_center = 617.5
# cavity_attenuation = 20
# qubit_frequency_center = 4610.2

# Qubit 4 (Right)
# resonator_frequency_center = 750.2
# cavity_attenuation = 18
# qubit_frequency_center = 4809.6

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 70, "SpecSpan": 5, "SpecNumPoints": 61}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": qubit_frequency_center, "sigma": 0.05, "max_gain": 2500}

RunT1 = False
RunT2 = False
T1T2_params = {"pi_gain": 1600, "pi2_gain": 800}

# Readout
FF_gain1 = 0  # 8000
FF_gain2 = 0
FF_gain3 = 0
FF_gain4 = 0
# Readout
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt}

trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    "pulse_gain": cavity_gain, #30000,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61,  ### number of points in the transmission frequecny
    "cav_Atten": cavity_attenuation,  #### cavity attenuator attenuation value
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
    config["reps"] = 40  # want more reps and rounds for qubit data
    config["rounds"] = 30
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

T2R_cfg = {"start": 0, "step": 0.7, "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
           "expts": 250, "reps": 50, "rounds": 50, "pi_gain": T1T2_params["pi_gain"],
           "pi2_gain": T1T2_params["pi2_gain"], "relax_delay": 300, 'f_ge': qubit_frequency_center + 0.1
           }

config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunT2:
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)


#Step is in Clock cycles!!!!!!!
RamseyCal_cfg = {"start": 0, "step": 1, "expts": 70 * 16, "SecondPulseAngle": 90,
                 "reps": 50, "rounds": 80, "pi2_gain": T1T2_params["pi2_gain"],
                 "relax_delay": 170, 'f_ge': qubit_frequency_center
                 }
config["FF_Qubits"][str(1)]['Gain_Expt'] = -15000
# config["FF_Qubits"][str(1)]['Gain_Expt'] = 0

config["FF_Qubits"][str(2)]['Gain_Expt'] = 0
config["FF_Qubits"][str(3)]['Gain_Expt'] = 0
config["FF_Qubits"][str(4)]['Gain_Expt'] = 0

config = config | RamseyCal_cfg
# list_of_idatas = []
# idata_array = list(np.concatenate([np.zeros(48* 1) , np.ones(320)]))
# idata_array = [x for x in idata_array]
# # idata_array = np.ones(320)
# for i in range(10):
#     list_of_idatas.append([idata_array[:16 * (i + 3)], idata_array[:16 * (i + 3)],
#                            idata_array[:16 * (i + 3)], idata_array[:16 * (i + 3)]])

idata_array = np.concatenate([np.zeros(48), np.ones(0)])
config['IDataArray'] = [idata_array, None, None, None]
# config['IDataArrayList'] = None
# print(idata_array[:16 * (i + 3)])

iRamsCal = RamseyFFCalR(path="RamseyFFCal", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
dRamsCal = RamseyFFCalR.acquire(iRamsCal)
RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=True, figNum=2)
# RamseyFFCal.save_data(iRamsCal, dRamsCal)
