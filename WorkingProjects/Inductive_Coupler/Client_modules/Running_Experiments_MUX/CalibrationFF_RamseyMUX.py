from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mFFSpecCalibration_MUX import FFSpecCalibrationMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mRamseyFFCalibrationR import RamseyFFCalR

from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Compensated_Pulse_Generation import *


# flags for initial calibration scans
mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6998.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5502, 'Gain': 510},
          'Pulse_FF': [0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7088.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit': {'Frequency': 4679.7, 'Gain': 2100},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7104.63 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000, "FF_Gains": [0, 0, 11600, 0]},
          'Qubit': {'Frequency': 4663.13, 'Gain': 1770},
          'Pulse_FF': [0, 0, 15000, 0]},
    '4': {'Readout': {'Frequency': 7280.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4620, 'Gain': 1275},
          'Pulse_FF': [10000, 0, 0, 0]}
    }
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.79, 'Gain': 8000}, 'Qubit': {'Frequency': 4672, 'Gain': 1450}},
#     '2': {'Readout': {'Frequency': 7055.84, 'Gain': 6000}, 'Qubit': {'Frequency': 4757, 'Gain': 990}},
#     '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit': {'Frequency': 4390, 'Gain': 840}},
#     '4': {'Readout': {'Frequency': 7250.01, 'Gain': 6000}, 'Qubit': {'Frequency': 4700, 'Gain': 2630}}
#     }

Qubit_Pulse = 2
# gain_test = -15000 #15000  # 6000  # maximum gain +/-3e4  # -20000 for left qubit, 20000 mid/right
# initial (pre-step) values
FF_gain1_expt = 0  # Left Qubit
FF_gain2_expt = 0  # Middle Qubit
FF_gain3_expt = 0  # Right Qubit
FF_gain4_expt = 0  # Right Qubit

FF_gain1_step, FF_gain2_step, FF_gain3_step, FF_gain4_step = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
FF_gain1_read, FF_gain2_read, FF_gain3_read, FF_gain4_read = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['FF_Gains']

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1_read, 'Gain_Expt': FF_gain1_step, 'Gain_Init': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2_read, 'Gain_Expt': FF_gain2_step, 'Gain_Init': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3_read, 'Gain_Expt': FF_gain3_step, 'Gain_Init': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4_read, 'Gain_Expt': FF_gain4_step, 'Gain_Init': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}


RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False  # detrmine qubit frequency
Spec_relevant_params = {"qubit_gain": 50, "SpecSpan": 4, "SpecNumPoints": 51, 'Gauss': False, "sigma": 0.03,
                        "gain": 4900}
RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "sigma": 0.03, "max_gain": 3000}
RunCalibrationFF = True
CalibrationFF_params = {'FFQubitIndex': 4, 'FFQubitExpGain': 17000,
                        "start": 0, "step": 1, "expts": 10 * 16 * 10,
                        "reps": 100, "rounds": 200, "relax_delay": 250,
           }

cavity_gain = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Frequency']
resonator_frequencies = [Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Frequency']]
gains = [Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Gain'] / 32000.]
BaseConfig['ro_chs'] = [0]


qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']


# Spec_relevant_params = {"qubit_gain": 3000, "SpecSpan": 30, "SpecNumPoints": 76}

# # Christie wants to see initial qubit frequency (for delta fn measurement)
# # This is likely overkill, takes a long time...
# qubit_frequency_center = (qubit_frequency_center + 4492.2) / 2  # between initial & final qubit freqs
# Spec_relevant_params = {'qubit_gain': 10000, "SpecSpan": 280}  # increase range by 200 MHz (freq jump)
# Spec_relevant_params["SpecNumPoints"] = Spec_relevant_params["SpecSpan"]//2 + 1

# set qubit channels. 6:left; 4:middle; 5:right

# set parameters for transmission measurement
UpdateConfig_transmission = {
    "reps": 1000,  # this will be used for all experiments below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "pulse_gains": gains,  # [DAC units]
    "pulse_freqs": resonator_frequencies,
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61,  ### number of points in the transmission frequecny
    "cav_relax_delay": 30
}
# parameters for qubit spec
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,  # [MHz]
    "qubit_length": 100,
    "SpecSpan": Spec_relevant_params["SpecSpan"],  # [MHz] span will be center +/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  # number of points in the transmission frequecny
}
# parameters for fast flux
UpdateConfig_FF = {
    "ff_pulse_style": "const",  # pulse is a constant/step function
    "ff_additional_length": 1,  # [us]
    "ff_freq": 0,  # [MHz] actual frequency is this number + "cavity_LO"
    "ff_nqz": 1,  # [Nyquist zone]
    "relax_delay": 200,  # [us] buffer to ensure qubit frequency has settled at init flux
}
# parameters for experimental variables
expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],  # [MHz]
    "span": UpdateConfig_qubit["SpecSpan"],  # [MHz]
    "expts": UpdateConfig_qubit["SpecNumPoints"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF
if len(BaseConfig.keys() & UpdateConfig.keys()) > 0:
    print("WARNING: UpdateConfig keys overwriting BaseConfig: {}".format(BaseConfig.keys() & UpdateConfig.keys()))
config = BaseConfig | UpdateConfig  # note that UpdateConfig will overwrite elements in BaseConfig
# update the cavity attenuation
config["FF_Qubits"] = FF_Qubits

# ----------------------------------------------------
# initial calibration code to find cavity and qubit frequencies
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
    if cavity_min:
       config["pulse_freq"] = Instance_trans.peakFreq_min
    else:
       config["pulse_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", config["pulse_freq"])
else:
    print("Cavity frequency set to: ", config["pulse_freq"])

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment


# qubit spec experiment
if Run2ToneSpec:
    config["reps"] = 30  # want more reps and rounds for qubit data
    config["rounds"] = 30
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFFMUX(path="SpecSliceFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFFMUX.acquire(Instance_specSlice)
    QubitSpecSliceFFMUX.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFFMUX.save_data(Instance_specSlice, data_specSlice)

  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunAmplitudeRabi:
    number_of_steps = 31
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": 300}
    config = config | ARabi_config
    iAmpRabi = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFFMUX.acquire(iAmpRabi)
    AmplitudeRabiFFMUX.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFFMUX.save_data(iAmpRabi, dAmpRabi)


#Step and length are in Clock cycles!!!!!!!
RamseyCal_cfg = {"SecondPulseAngle": 0,
            "pi2_gain": qubit_gain // 2,
            'f_ge': qubit_frequency_center,
            "sigma": Amplitude_Rabi_params["sigma"]
           }

if RunCalibrationFF:
    RamseyCal_cfg['FFlength'] = int(np.ceil(CalibrationFF_params['expts'] / 16)) * 16
    config["FF_Qubits"][str(CalibrationFF_params['FFQubitIndex'])]['Gain_Expt'] = CalibrationFF_params['FFQubitExpGain']
    for i in range(len(Qubit_Parameters)):
        if i + 1 != CalibrationFF_params['FFQubitIndex']:
            config["FF_Qubits"][str(i + 1)]['Gain_Expt'] = 0

    print(config["FF_Qubits"])
    config = config | RamseyCal_cfg | CalibrationFF_params

    config['IDataArray'] = [None, None, None, None]
    # config['IDataArray'] = [-15000 * Compensated_AWG((20) * 16, Qubit1_parameters)[1], None, None, None]

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
# config['IDataArray'] = [None, None, None, None]


# config['IDataArrayList'] = None
# print(idata_array[:16 * (i + 3)])


# AverageProgram
# iRamsCal = RamseyFFCal(path="RamseyFFCal", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dRamsCal = RamseyFFCal.acquire(iRamsCal)
# RamseyFFCal.display(iRamsCal, dRamsCal, plotDisp=True, figNum=2)
# RamseyFFCal.save_data(iRamsCal, dRamsCal)

# print(config['pulse_freq'])
# # RAveragerProgram
# # iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# # dRamsCal = RamseyFFCalR.acquire(iRamsCal)
# # RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
# # RamseyFFCalR.save_data(iRamsCal, dRamsCal)
#
# config["SecondPulseAngle"] = 90
# print('90 degrees: ')

# soc.reset_gens()


# iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
# dRamsCal = RamseyFFCalR.acquire(iRamsCal)
# RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
# RamseyFFCalR.save_data(iRamsCal, dRamsCal)


Qubit1 = False
Qubit2 = False
Qubit4 = False


'''
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
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)'''