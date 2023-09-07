import pickle
from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF


outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"


Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6953.0, 'Gain': 10000}, 'Qubit': {'Frequency': 4429, 'Gain': 770}},
    '2': {'Readout': {'Frequency': 7055.95, 'Gain': 8000}, 'Qubit': {'Frequency': 5252, 'Gain': 810}},
    '3': {'Readout': {'Frequency': 7117.55, 'Gain': 8000}, 'Qubit': {'Frequency': 5255, 'Gain': 840}},
    '4': {'Readout': {'Frequency': 7200, 'Gain': 8000}, 'Qubit': {'Frequency': 4470, 'Gain': 2630}}
    }


FF_Qubits[str(1)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(2)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(3)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}
FF_Qubits[str(4)] |= {'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}

Spec_relevant_params = {'qubit_gain': 38,'SpecSpan': 12, 'SpecNumPoints': 161}


trans_config = {
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    "TransSpan": 0.3,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 7,  ### number of points in the transmission frequecny
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

voltage_frequency_dict = pickle.load(open('./../Helpers/Yoko_Voltages.p', 'rb'))
yoko_voltages, qubit_frequencies = voltage_frequency_dict['yokoVs'], voltage_frequency_dict['qubitFreqs']
cavity_frequencies = voltage_frequency_dict['cavityFreqs']
index = 0
Qubit_Spec_Data = []
Cavity_IQ = []
j = 0
for yoko_vector, qubit_freqs, cav_freqs in zip(yoko_voltages[:], qubit_frequencies[:], cavity_frequencies[:]):
    print(j)
    j += 1
    yoko69.SetVoltage(yoko_vector[0])
    yoko70.SetVoltage(yoko_vector[1])
    yoko71.SetVoltage(yoko_vector[2])
    yoko72.SetVoltage(yoko_vector[3])
    Spec_Data = []
    Cavity_Data = []
    for i in range(len(yoko_vector)):
        config['pulse_freq'] = np.round(cav_freqs[i], 2)
        config['pulse_gain'] = Qubit_Parameters[str(i + 1)]['Readout']['Gain']
        config['qubit_freq'] = np.round(qubit_freqs[i] * 1e3, 1)
        config["reps"] = 20  # fast axis number of points
        config["rounds"] = 10  # slow axis number of points
        print(yoko_vector, config['pulse_freq'], config['pulse_gain'], config['qubit_freq'], )
        # Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
        #                               outerFolder=outerFolder)
        # data_trans = CavitySpecFF.acquire(Instance_trans)
        Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
        data_trans = CavitySpecFF.acquire(Instance_trans)
        CavitySpecFF.display(Instance_trans, data_trans, plotDisp=False, figNum=1)
        CavitySpecFF.save_data(Instance_trans, data_trans)
        Cavity_Data.append(data_trans)
        config["pulse_freq"] = Instance_trans.peakFreq_min
        # print(config["pulse_freq"])
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
        Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                              outerFolder=outerFolder)
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=False, figNum=2)
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        # Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
        #                                       outerFolder=outerFolder)
        # data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        Spec_Data.append(data_specSlice)
    Qubit_Spec_Data.append(Spec_Data)
    Cavity_IQ.append(Cavity_Data)
    pickle.dump([yoko_voltages, Qubit_Spec_Data, Cavity_IQ], open(
        'Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\Qubit_Yoko_Calibration\Qubit_Calibration_Data300.p', 'wb'))

yoko69.SetVoltage(0)
yoko70.SetVoltage(0)
yoko71.SetVoltage(0)
yoko72.SetVoltage(0)