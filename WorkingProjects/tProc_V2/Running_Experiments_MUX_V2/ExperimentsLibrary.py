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



trans_config = {
    "pulse_style": "const",  # --Fixed
    "readout_length": 3,  # [us]
    "cavity_gain": cavity_gain,  # -1 to +1
    "cavity_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "cavity_gains": cavity_gains,  # -1 to +1
    "cavity_freqs": resonator_frequencies,
    "TransSpan": 1.5 * 1,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61 * 1,  ### number of points in the transmission frequecny
    "cav_relax_delay": 30  # [us]
}
qubit_config = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 100,  # us
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
}
expt_cfg = {
    "qubit_sweep_freq": QickSweep1D("qubit_freq_loop",
                                    start=qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
                                    end=qubit_config["qubit_freq"] + qubit_config["SpecSpan"]),
}


UpdateConfig = trans_config | qubit_config | expt_cfg
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indices'] = Qubit_Readout


cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
def RunTransmissionSweep():
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

# qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
# qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]
