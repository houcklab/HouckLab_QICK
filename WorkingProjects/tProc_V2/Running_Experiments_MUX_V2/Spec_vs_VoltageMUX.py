# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.tProc_V2.Running_Experiments_MUX_V2.MUXInitialize import *

from WorkingProjects.tProc_V2.Experimental_Scripts_MUX_V2.mTransmissionFFMUX import \
    CavitySpecFFMUX
from WorkingProjects.tProc_V2.Experimental_Scripts_MUX_V2.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.tProc_V2.Experimental_Scripts_MUX_V2.mSpecVsQblox_MUX import \
    SpecVsQblox

from WorkingProjects.tProc_V2.Experimental_Scripts_MUX_V2.mAmplitudeRabiFFMUX import \
    AmplitudeRabiFFMUX

# for defining sweeps
from qick.asm_v2 import QickSpan, QickSweep1D

mixer_freq = 500
print(BaseConfig["cavity_LO"] / 1e6)
BaseConfig["mixer_freq"] = mixer_freq
BaseConfig["has_mixer"] = True
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6975.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4302.3, 'Gain': 740},
          'Pulse_FF': [0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7060.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5139.5, 'Gain': 1050},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7127.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8800,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 1.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5012.2, 'Gain': 1250},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7245.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4302.3, 'Gain': 1350},
          'Pulse_FF': [0, 0, 0, 0]}
}

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

Qubit_Readout = [1]
Qubit_Pulse = 1
Qubit_PulseSS = [1]

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]

RunTransmissionSweep = True  # determine cavity frequency
Run2ToneSpec = False

Spec_relevant_params = {"qubit_gain": 100, "SpecSpan": 30, "SpecNumPoints": 71, 'Gauss': False, "sigma": 0.05,
                        "gain": 600, 'reps': 15, 'rounds': 15}
Run_Spec_v_Voltage = False
Spec_sweep_relevant_params = {"qubit_gain": 1, "SpecSpan": 0.8, "SpecNumPoints": 3,
                              "DAC": [8],
                              "Qblox_Vmin": [0.42475],
                              "Qblox_Vmax": [0.42558], "Qblox_numpoints": 3,
                              'reps': 10, 'rounds': 10, 'smart_normalize': True}

### NOTE: +/- 1 in V2 is equivalent to +/- 32766 in V1 ###
RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "sigma": 0.05, "max_gain": 4000 / 32766}

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
    "qubit_sweep_freq": QickSweep1D("qubit_ch_freq_loop",
                                    start=qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
                                    end=qubit_config["qubit_freq"] + qubit_config["SpecSpan"]),
    # "step": 2 * qubit_config["SpecSpan"] / (qubit_config["SpecNumPoints"] - 1),
    # "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

print(expt_cfg)

UpdateConfig = trans_config | qubit_config | expt_cfg
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indices'] = Qubit_Readout

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

# TODO: test this, and also see if the "rounds" changes anything - Joshua
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

    expt_cfg = {
        "qubit_sweep_freq": QickSweep1D("qubit_ch_freq_loop",
                                        start=qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
                                        end=qubit_config["qubit_freq"] + qubit_config["SpecSpan"]),
        # "step": 2 * qubit_config["SpecSpan"] / (qubit_config["SpecNumPoints"] - 1),
        # "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
        "expts": qubit_config["SpecNumPoints"]
    }

    config["qubit_sweep_freq"] = QickSweep1D("qubit_ch_freq_loop",
                                             start=qubit_config["qubit_freq"] - Spec_sweep_relevant_params["SpecSpan"],
                                             end=qubit_config["qubit_freq"] + Spec_sweep_relevant_params["SpecSpan"])
    # Since V2, only for plotting
    config["step"] = 2 * Spec_sweep_relevant_params["SpecSpan"] / (Spec_sweep_relevant_params["SpecNumPoints"] - 1)
    config["start"] = qubit_config["qubit_freq"] - Spec_sweep_relevant_params["SpecSpan"]
    config["expts"] = Spec_sweep_relevant_params["SpecNumPoints"]

    Instance_SpecVQ = SpecVsQblox(path="SpecVsQblox", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
    data_SpecVQ = SpecVsQblox.acquire(Instance_SpecVQ, plotDisp=True,
                                      smart_normalize=Spec_sweep_relevant_params['smart_normalize'])
    # print(data_SingleShotProgram)
    # SpecVsQblox.display(Instance_SpecVQ, data_SpecVQ, plotDisp=False)

    SpecVsQblox.save_data(Instance_SpecVQ, data_SpecVQ)
    SpecVsQblox.save_config(Instance_SpecVQ)

# Amplitude Rabi
number_of_steps = 31
step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)

ARabi_config = {'gain_sweep': QickSweep1D("qubit_gain_loop", start=0, end=Amplitude_Rabi_params["max_gain"]),
                "expts": number_of_steps, "reps": 1, "rounds": 1,
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
