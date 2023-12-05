import pickle
from q4diamond.Client_modules.Running_Experiments_MUX.MUXInitialize import *

from q4diamond.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX




mixer_freq = 500
BaseConfig['mixer_freq'] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6953.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}, 'Qubit': {'Frequency': 4429, 'Gain': 770}},
    '2': {'Readout': {'Frequency': 7055.95 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000}, 'Qubit': {'Frequency': 5252, 'Gain': 810}},
    '3': {'Readout': {'Frequency': 7117.55 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000}, 'Qubit': {'Frequency': 5255, 'Gain': 840}},
    '4': {'Readout': {'Frequency': 7200 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000}, 'Qubit': {'Frequency': 4470, 'Gain': 2630}}
    }


FF_Qubits[str(1)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(2)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(3)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(4)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}

Spec_relevant_params = {'qubit_gain': 38,'SpecSpan': 6.5, 'SpecNumPoints': 131}#131}


trans_config = {
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    "TransSpan": 0.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 10,  ### number of points in the transmission frequecny
    "cav_relax_delay": 30
}
qubit_config = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_length": 90,
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
    "relax_delay": 150
}

UpdateConfig = trans_config | qubit_config
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits

config['ro_chs'] = [0]


voltage_frequency_dict = pickle.load(open('./../Helpers/Yoko_Voltages_0F_300.p', 'rb'))
yoko_voltages, qubit_frequencies = voltage_frequency_dict['yokoVs'], voltage_frequency_dict['qubitFreqs']
cavity_frequencies = voltage_frequency_dict['cavityFreqs']
index = 0
Yoko_Voltages = []
Qubit_Spec_Data = []
Cavity_IQ = []
j = 0
for yoko_vector, qubit_freqs, cav_freqs in zip(yoko_voltages[:200], qubit_frequencies[:200], cavity_frequencies[:200]):
    print(j)
    j += 1
    yoko69.SetVoltage(yoko_vector[0])
    yoko70.SetVoltage(yoko_vector[1])
    yoko71.SetVoltage(yoko_vector[2])
    yoko72.SetVoltage(yoko_vector[3])
    Yoko_Voltages.append(yoko_vector)
    Spec_Data = []
    Cavity_Data = []
    for i in range(len(yoko_vector)):
        # config['pulse_freq'] = np.round(cav_freqs[i], 2)
        # config['pulse_gain'] = Qubit_Parameters[str(i + 1)]['Readout']['Gain']
        print(cav_freqs[i])
        config['mixer_freq'] = mixer_freq
        config['pulse_freqs'] = [np.round(cav_freqs[i], 2) - mixer_freq - BaseConfig["cavity_LO"] / 1e6]
        config['pulse_gains'] = [Qubit_Parameters[str(i + 1)]['Readout']['Gain'] / 32000.]
        # gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

        config['qubit_freq'] = np.round(qubit_freqs[i] * 1e3, 1)
        config["reps"] = 20  # fast axis number of points
        config["rounds"] = 10  # slow axis number of points
        print(yoko_vector, config['pulse_freqs'], config['pulse_gains'], config['qubit_freq'], )
        Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
        data_trans = CavitySpecFFMUX.acquire(Instance_trans)
        CavitySpecFFMUX.display(Instance_trans, data_trans, plotDisp=False, figNum=1)
        CavitySpecFFMUX.save_data(Instance_trans, data_trans)
        Cavity_Data.append(data_trans)
        if i == 0:
            config["pulse_freqs"][0] += Instance_trans.peakFreq_min - mixer_freq
            config["mixer_freq"] = Instance_trans.peakFreq_min
        else:
            config["pulse_freqs"][0] += (Instance_trans.peakFreq_max + Instance_trans.peakFreq_min) / 2 - mixer_freq
            config["mixer_freq"] = (Instance_trans.peakFreq_max + Instance_trans.peakFreq_min) / 2
        config["reps"] = 20  # want more reps and rounds for qubit data
        config["rounds"] = 25
        config["Gauss"] = False
        expt_cfg = {
            "step": 2 * config["SpecSpan"] / config["SpecNumPoints"],
            "start": config["qubit_freq"] - config["SpecSpan"],
            "expts": config["SpecNumPoints"]
        }
        config = config | expt_cfg
        # config['pulse_freq'] = np.round(cav_freqs[i], 2)
        Instance_specSlice = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                              outerFolder=outerFolder)
        data_specSlice = QubitSpecSliceFFMUX.acquire(Instance_specSlice)
        QubitSpecSliceFFMUX.display(Instance_specSlice, data_specSlice, plotDisp=False, figNum=2)
        QubitSpecSliceFFMUX.save_data(Instance_specSlice, data_specSlice)
        Spec_Data.append(data_specSlice)
    Qubit_Spec_Data.append(Spec_Data)
    Cavity_IQ.append(Cavity_Data)
    # pickle.dump([yoko_voltages, Qubit_Spec_Data, Cavity_IQ], open(
    #     'Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\Qubit_Yoko_Calibration\Qubit_Calibration_Data300.p', 'wb'))
    # pickle.dump([yoko_voltages, Qubit_Spec_Data, Cavity_IQ], open(
    #     'Z:\Jeronimo\Measurements\RFSOC_4Qubit_0F\Qubit_Yoko_Calibration\Qubit_Calibration_DataTest.p', 'wb'))
    # pickle.dump([yoko_voltages, Qubit_Spec_Data, Cavity_IQ], open(
    #     'Z:\Jeronimo\Measurements\RFSOC_4Qubit_0F\Qubit_Yoko_Calibration\Qubit_Calibration_30.p', 'wb'))
    pickle.dump([Yoko_Voltages, Qubit_Spec_Data, Cavity_IQ], open(
        'Z:\Jeronimo\Measurements\RFSOC_4Qubit_0F\Qubit_Yoko_Calibration\Qubit_Calibration_200.p', 'wb'))

yoko69.SetVoltage(0)
yoko70.SetVoltage(0)
yoko71.SetVoltage(0)
yoko72.SetVoltage(0)