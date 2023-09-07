# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibration import RamseyFFCal
from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibrationR import RamseyFFCalR
# from q4diamond.Client_modules.Helpers.Compensated_Pulse_Generation import Comp_Step, Comp_Step_Gain, Comp_Step3

outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# yoko69.SetVoltage(-0.007)
# yoko70.SetVoltage(0.2845)
# yoko71.SetVoltage(0.1893)
# yoko72.SetVoltage(-0.215)

# yoko69.SetVoltage(-0.4263)
# yoko70.SetVoltage(-0.3917)
# yoko71.SetVoltage(-0.0075)
# yoko72.SetVoltage(-0.1196)

# yoko69.SetVoltage(0.003)
# yoko70.SetVoltage(0)
# yoko71.SetVoltage(0)
# yoko72.SetVoltage(0)
yoko69.SetVoltage(-0.4064)
yoko70.SetVoltage(0.0868)
yoko71.SetVoltage(0.0053)
yoko72.SetVoltage(0.2774)


# yoko69.SetVoltage(-0.329)
# yoko70.SetVoltage(.016)
# yoko71.SetVoltage(-0.0632)
# yoko72.SetVoltage(0.361)

# Qubit 1 (Left)
resonator_frequency_center = 6952.4  # [MHz] offset from "cavity_LO" = 7e9
qubit_frequency_center = 4365.83  # 4516  # 4200  # 4599 + 100  # [MHz]
# qubit_frequency_center = 4582.5  # 4516  # 4200  # 4599 + 100  # [MHz]
cavity_gain = 17000
cavity_attenuation = 0

# Qubit 2 (Top)
resonator_frequency_center = 7055.35
cavity_gain = 10500
qubit_frequency_center = 4339.06
# qubit_frequency_center = 4559.5 #4338.89 + 215


# Qubit 3 (Bottom)
# resonator_frequency_center = 617.5
# cavity_attenuation = 20
# qubit_frequency_center = 4610.2

# Qubit 4 (Right)
resonator_frequency_center = 7249.71  # [MHz] offset from "cavity_LO" = 7e9
qubit_frequency_center = 4419.43  # 4516  # 4200  # 4599 + 100  # [MHz]
# resonator_frequency_center = 7249.88  # [MHz] offset from "cavity_LO" = 7e9
# qubit_frequency_center = 4566.4  # 4516  # 4200  # 4599 + 100  # [MHz]
cavity_gain = 8000

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 40, "SpecSpan": 1.5, "SpecNumPoints": 61}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": qubit_frequency_center, "sigma": 0.05, "max_gain": 1700}

RunT1 = False
RunT2 = False
# T1T2_params = {"pi_gain": 1600, "pi2_gain": 800} #Qubit 1

# T1T2_params = {"pi_gain": 1650, "pi2_gain": 825} #Qubit 1
# T1T2_params = {"pi_gain": 1550, "pi2_gain": 775} #Qubit 1
#
T1T2_params = {"pi_gain": 2450, "pi2_gain": 1225} #Qubit 2
# T1T2_params = {"pi_gain": 2070, "pi2_gain": 1035} #Qubit 4

# Readout
FF_gain1 = 0  # 8000
FF_gain2 = 0
FF_gain3 = 0
FF_gain4 = 0 #-15000
# Expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0 #-15000

FF_gain1_pulse = 0  # 8000
FF_gain2_pulse = 0
FF_gain3_pulse = 0
FF_gain4_pulse = 0 #-15000

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 3,  # [Clock ticks]
    "pulse_gain": cavity_gain, #30000,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61,  ### number of points in the transmission frequecny
    "cav_Atten": 0,  #### cavity attenuator attenuation value
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
config['Gauss'] = False

#### update the qubit and cavity attenuation

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
           "expts": 50, "reps": 30, "rounds": 50, "pi_gain": T1T2_params["pi_gain"],
           "pi2_gain": T1T2_params["pi2_gain"], "relax_delay": 300, 'f_ge': qubit_frequency_center + 0.3
           }

config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunT2:
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)


#Step and length are in Clock cycles!!!!!!!
RamseyCal_cfg = {"start": 0, "step": 1, "expts": 3*16, "SecondPulseAngle": 0,
           "reps": 100, "rounds": 50, "pi2_gain": T1T2_params["pi2_gain"],
                 "relax_delay": 170, 'f_ge': qubit_frequency_center,
           }
RamseyCal_cfg['FFlength'] = int(np.ceil(RamseyCal_cfg['expts'] / 16)) * 16
print("pulse length: ", RamseyCal_cfg['FFlength'] // 16 + 2)
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

# idata_array = np.concatenate([np.zeros(48), np.ones(0)])
# config['IDataArray'] = [None, Comp_Step3 * 15000, None, None] #this time no averaging before hand

# config['IDataArray'] = [Comp_Step * -15000, None, None, None]
config['IDataArray'] = [None, None, None, None]


# config['IDataArrayList'] = None
# print(idata_array[:16 * (i + 3)])


# AverageProgram
# iRamsCal = RamseyFFCal(path="RamseyFFCal", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dRamsCal = RamseyFFCal.acquire(iRamsCal)
# RamseyFFCal.display(iRamsCal, dRamsCal, plotDisp=True, figNum=2)
# RamseyFFCal.save_data(iRamsCal, dRamsCal)

print(config['pulse_freq'])
# RAveragerProgram
# iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dRamsCal = RamseyFFCalR.acquire(iRamsCal)
# RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
# RamseyFFCalR.save_data(iRamsCal, dRamsCal)

config["SecondPulseAngle"] = 90
print('90 degrees: ')

soc.reset_gens()


# iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dRamsCal = RamseyFFCalR.acquire(iRamsCal)
# RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
# RamseyFFCalR.save_data(iRamsCal, dRamsCal)


Qubit1 = False
Qubit2 = False
Qubit4 = True



#~~~~~~~~~~~~~~~~~~~~~~~Qubit 1 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if Qubit1:
    from q4diamond.Client_modules.initialize import *
    from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
    from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
    from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
    from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
    from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
    from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibration import RamseyFFCal
    from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibrationR import RamseyFFCalR
    from q4diamond.Client_modules.Helpers.Compensated_Pulse_Generation import *

    outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

    yoko69.rampstep = 0.0005
    yoko70.rampstep = 0.0005
    yoko71.rampstep = 0.0005
    yoko72.rampstep = 0.0005

    yoko69.SetVoltage(0.003)
    yoko70.SetVoltage(0)
    yoko71.SetVoltage(0)
    yoko72.SetVoltage(0)

    # Qubit 1 (Left)
    resonator_frequency_center = 6952.45  # [MHz] offset from "cavity_LO" = 7e9
    qubit_frequency_center = 4365.95  # 4516  # 4200  # 4599 + 100  # [MHz]
    # qubit_frequency_center = 4582.5  # 4516  # 4200  # 4599 + 100  # [MHz]
    cavity_gain = 10000
    cavity_attenuation = 0

    T1T2_params = {"pi_gain": 1650, "pi2_gain": 825} #Qubit 1
    # Readout
    FF_gain1 = 0  # 8000
    FF_gain2 = 0
    FF_gain3 = 0
    FF_gain4 = 0 #-15000
    # Expt
    FF_gain1_expt = 0  # 8000
    FF_gain2_expt = 0
    FF_gain3_expt = 0
    FF_gain4_expt = 0 #-15000


    FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Init': 0}
    FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Init': 0}
    FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Init': 0}
    FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Init': 0}

    trans_config = {
        "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
        "pulse_style": "const",  # --Fixed
        "readout_length": 3,  # [Clock ticks]
        "pulse_gain": cavity_gain, #30000,  # [DAC units]
        "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
        "TransNumPoints": 61,  ### number of points in the transmission frequecny
        "cav_Atten": 0,  #### cavity attenuator attenuation value
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

    cavity_min = True
    config["cavity_min"] = cavity_min  # look for dip, not peak
    Amplitude_Rabi_params = {"qubit_freq": qubit_frequency_center, "sigma": 0.05, "max_gain": 3500}
    number_of_steps = 31
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": 300}
    config = config | ARabi_config

    #Step and length are in Clock cycles!!!!!!!
    RamseyCal_cfg = {"start": 0, "step": 1, "expts": 20*16, "SecondPulseAngle": 0,
               "reps": 200, "rounds": 800, "pi2_gain": T1T2_params["pi2_gain"],
                     "relax_delay": 160, 'f_ge': qubit_frequency_center,
               }
    RamseyCal_cfg['FFlength'] = int(np.ceil(RamseyCal_cfg['expts'] / 16)) * 16
    print("pulse length: ", RamseyCal_cfg['FFlength'] // 16 + 2)
    config["FF_Qubits"][str(1)]['Gain_Expt'] = -15000
    # config["FF_Qubits"][str(1)]['Gain_Expt'] = 0

    config["FF_Qubits"][str(2)]['Gain_Expt'] = 0 #15000
    config["FF_Qubits"][str(3)]['Gain_Expt'] = 0
    config["FF_Qubits"][str(4)]['Gain_Expt'] = 0

    config = config | RamseyCal_cfg

    config['IDataArray'] = [None, None, None, None]
    config['IDataArray'] = [-15000 * Compensated_AWG((20) * 16, Qubit1_parameters)[1], None, None, None]

    print(config['pulse_freq'])

    # RAveragerProgram
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)
    soc.reset_gens()

    config["SecondPulseAngle"] = 90
    print('90 degrees: ')
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)

#~~~~~~~~~~~~~~~~~~~~~~~Qubit 2 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if Qubit2:
    from q4diamond.Client_modules.initialize import *
    from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
    from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
    from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
    from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
    from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
    from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibration import RamseyFFCal
    from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibrationR import RamseyFFCalR
    from q4diamond.Client_modules.Helpers.Compensated_Pulse_Generation import *

    outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

    yoko69.rampstep = 0.0005
    yoko70.rampstep = 0.0005
    yoko71.rampstep = 0.0005
    yoko72.rampstep = 0.0005

    yoko69.SetVoltage(-0.4263)
    yoko70.SetVoltage(-0.3917)
    yoko71.SetVoltage(-0.0075)
    yoko72.SetVoltage(-0.1196)

    # Qubit 1 (Left)
    resonator_frequency_center = 7055.3
    cavity_gain = 10500
    qubit_frequency_center = 4339.06 + 0.01

    T1T2_params = {"pi_gain": 2450, "pi2_gain": 1225}  # Qubit 2
    # Readout
    FF_gain1 = 0  # 8000
    FF_gain2 = 0
    FF_gain3 = 0
    FF_gain4 = 0 #-15000
    # Expt
    FF_gain1_expt = 0  # 8000
    FF_gain2_expt = 0
    FF_gain3_expt = 0
    FF_gain4_expt = 0 #-15000


    FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Init': 0}
    FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Init': 0}
    FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Init': 0}
    FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Init': 0}

    trans_config = {
        "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
        "pulse_style": "const",  # --Fixed
        "readout_length": 3,  # [Clock ticks]
        "pulse_gain": cavity_gain, #30000,  # [DAC units]
        "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
        "TransNumPoints": 61,  ### number of points in the transmission frequecny
        "cav_Atten": 0,  #### cavity attenuator attenuation value
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

    cavity_min = True
    config["cavity_min"] = cavity_min  # look for dip, not peak
    Amplitude_Rabi_params = {"qubit_freq": qubit_frequency_center, "sigma": 0.05, "max_gain": 3500}
    number_of_steps = 31
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": 300}
    config = config | ARabi_config

    #Step and length are in Clock cycles!!!!!!!
    RamseyCal_cfg = {"start": 0, "step": 1, "expts": 100*16, "SecondPulseAngle": 0,
               "reps": 100, "rounds": 400, "pi2_gain": T1T2_params["pi2_gain"],
                     "relax_delay": 200, 'f_ge': qubit_frequency_center,
               }
    RamseyCal_cfg['FFlength'] = int(np.ceil(RamseyCal_cfg['expts'] / 16)) * 16
    print("pulse length: ", RamseyCal_cfg['FFlength'] // 16 + 2)
    config["FF_Qubits"][str(1)]['Gain_Expt'] = 0
    config["FF_Qubits"][str(2)]['Gain_Expt'] = 15000
    config["FF_Qubits"][str(3)]['Gain_Expt'] = 0
    config["FF_Qubits"][str(4)]['Gain_Expt'] = 0

    config = config | RamseyCal_cfg

    config['IDataArray'] = [None, None, None, None]
    # config['IDataArray'] = [None, 15000 * Compensated_AWG((25) * 16, Qubit2_parameters)[1], None, None]

    print(config['pulse_freq'])

    # iRamsCal = RamseyFFCal(path="RamseyFFCal", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    # dRamsCal = RamseyFFCal.acquire(iRamsCal)
    # RamseyFFCal.display(iRamsCal, dRamsCal, plotDisp=True, figNum=2)
    # RamseyFFCal.save_data(iRamsCal, dRamsCal)

    # RAveragerProgram
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)
    soc.reset_gens()

    config["SecondPulseAngle"] = 90
    print('90 degrees: ')
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)



#~~~~~~~~~~~~~~~~~~~~~~~
if Qubit4:

    from q4diamond.Client_modules.initialize import *
    from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
    from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
    from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
    from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
    from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
    from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibration import RamseyFFCal
    from q4diamond.Client_modules.Experiment_Scripts.mRamseyFFCalibrationR import RamseyFFCalR
    from q4diamond.Client_modules.Helpers.Compensated_Pulse_Generation import *

    outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

    yoko69.rampstep = 0.0005
    yoko70.rampstep = 0.0005
    yoko71.rampstep = 0.0005
    yoko72.rampstep = 0.0005


    # yoko69.SetVoltage(-0.329)
    # yoko70.SetVoltage(.016)
    # yoko71.SetVoltage(-0.0632)
    # yoko72.SetVoltage(0.361)

    yoko69.SetVoltage(-0.4064)
    yoko70.SetVoltage(0.0868)
    yoko71.SetVoltage(0.0053)
    yoko72.SetVoltage(0.2774)

    # Qubit 4 (Right)
    resonator_frequency_center = 7249.52  # [MHz] offset from "cavity_LO" = 7e9
    qubit_frequency_center = 4419.43 + 0.07#4387.9  # 4516  # 4200  # 4599 + 100  # [MHz]
    # resonator_frequency_center = 7249.88  # [MHz] offset from "cavity_LO" = 7e9
    # qubit_frequency_center = 4566.4  # 4516  # 4200  # 4599 + 100  # [MHz]
    cavity_gain = 6000 #10500

    T1T2_params = {"pi_gain": 2170, "pi2_gain": 1085} #Qubit 4
    T1T2_params = {"pi_gain": 1270, "pi2_gain": 635} #Qubit 4

    # Readout
    FF_gain1 = 0  # 8000
    FF_gain2 = 0
    FF_gain3 = 0
    FF_gain4 = 0 #-15000
    # Expt
    FF_gain1_expt = 0  # 8000
    FF_gain2_expt = 0
    FF_gain3_expt = 0
    FF_gain4_expt = -15000 #-15000


    FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Init': 0}
    FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Init': 0}
    FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Init': 0}
    FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Init': 0}

    trans_config = {
        "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
        "pulse_style": "const",  # --Fixed
        "readout_length": 3,  # [Clock ticks]
        "pulse_gain": cavity_gain, #30000,  # [DAC units]
        "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
        "TransNumPoints": 61,  ### number of points in the transmission frequecny
        "cav_Atten": 0,  #### cavity attenuator attenuation value
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

    cavity_min = True
    config["cavity_min"] = cavity_min  # look for dip, not peak
    Amplitude_Rabi_params = {"qubit_freq": qubit_frequency_center, "sigma": 0.05, "max_gain": 3500}
    number_of_steps = 31
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": 300}
    config = config | ARabi_config

    #Step and length are in Clock cycles!!!!!!!
    RamseyCal_cfg = {"start": 0, "step": 1 , "expts": 100*16, "SecondPulseAngle": 0,
               "reps": 100, "rounds": 400, "pi2_gain": T1T2_params["pi2_gain"],
                     "relax_delay": 200, 'f_ge': qubit_frequency_center,
               }
    RamseyCal_cfg['FFlength'] = int(np.ceil(RamseyCal_cfg['expts'] / 16)) * 16
    print("pulse length: ", RamseyCal_cfg['FFlength'] // 16 + 2)
    config["FF_Qubits"][str(1)]['Gain_Expt'] = 0 #-15000
    # config["FF_Qubits"][str(1)]['Gain_Expt'] = 0

    config["FF_Qubits"][str(2)]['Gain_Expt'] = 0 #15000
    config["FF_Qubits"][str(3)]['Gain_Expt'] = 0
    config["FF_Qubits"][str(4)]['Gain_Expt'] = -15000

    config = config | RamseyCal_cfg

    config['IDataArray'] = [None, None, None, None]
    print(config['pulse_freq'])

    # iRamsCal = RamseyFFCal(path="RamseyFFCal", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    # dRamsCal = RamseyFFCal.acquire(iRamsCal)
    # RamseyFFCal.display(iRamsCal, dRamsCal, plotDisp=True, figNum=2)
    # RamseyFFCal.save_data(iRamsCal, dRamsCal)


    # RAveragerProgram
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)

    soc.reset_gens()

    config["SecondPulseAngle"] = 90
    print('90 degrees: ')
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)
