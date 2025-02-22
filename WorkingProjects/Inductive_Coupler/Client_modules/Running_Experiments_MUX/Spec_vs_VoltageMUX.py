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
    '1': {'Readout': {'Frequency': 7344.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3600, 'Gain': 1500},
          'Pulse_FF': [0, 10000, 10000, 10000]},
    '2': {'Readout': {'Frequency': 7289 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 11000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4200, 'Gain': 1400},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7126.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8800,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 1.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4450, 'Gain': 1250},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7459.65 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4238.8, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7325.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
              'Qubit': {'Frequency': 4063, 'Gain': 4000},
              'Pulse_FF': [0, 0, 0, 0]}
    }


# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0


Qubit_Readout = [2]
Qubit_Pulse = 2
Qubit_PulseSS = [2]


FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

# Qubit_Read_Gain = 0
# Qubit_Sweep = 4
# Qubit_Sweep_Gain = 13000
# FF_Gains = [-30000, -30000, -30000, -30000]
# # FF_Gains = [0, 0, 0, 0]
# FF_Gains[Qubit_Readout[0] - 1] = Qubit_Read_Gain
# FF_Gains[Qubit_Sweep - 1] = Qubit_Sweep_Gain
# FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = FF_Gains
# FF_Gains[Qubit_Readout[0] - 1] = 0
# FF_gain1, FF_gain2, FF_gain3, FF_gain4 = FF_Gains


gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]

RunTransmissionSweep = False # determine cavity frequency
Run2ToneSpec = True

Spec_relevant_params = {"qubit_gain": 1000, "SpecSpan": 200, "SpecNumPoints": 101, 'Gauss': False, "sigma": 0.01,
                        "gain": 8000, 'reps': 30, 'rounds': 30}

Run_Spec_v_Voltage = False
Spec_sweep_relevant_params = {"qubit_gain": 1500, "SpecSpan": 200, "SpecNumPoints": 71,
                              "DAC": [5],
                              "Qblox_Vmin": [-0.5],
                              "Qblox_Vmax": [0], "Qblox_numpoints": 11,
                              'reps': 20, 'rounds': 20, 'smart_normalize': True}

Run_Trans_v_Voltage = False
Trans_sweep_relevant_params = {
    "reps": 200, "readout_length": 3,  # [us]
    "TransSpan": 3 * 1,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61 * 1,  ### number of points in the transmission frequecny
    "cav_relax_delay": 20
}
Run_Trans_v_Power = False
Trans_power_relevant_params = {"gain_min": [1000],
                              "gain_max": [15000], "gain_numpoints": 11}

Run_Spec_v_ResonatorGain = False
Spec_ResonatorGain_relevant_params = {"gain_min": [1000],
                              "gain_max": [1040], "gain_numpoints": 31}


RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "sigma": 0.03, "max_gain": 5000}

SingleShot = False
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
    "relax_delay": 1000,  # us
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
