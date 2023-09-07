# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift

#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"



cavity_gain = 20000
resonator_frequency_center = 7085

trans_config = {
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 20,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 601,  ### number of points in the transmission frequecny
    "cav_relax_delay": 3
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

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt}
UpdateConfig = trans_config
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
config["reps"] = 10  # fast axis number of points
config["rounds"] = 20  # slow axis number of points
Instance_trans = CavitySpecFF(path="Cavity_Wind", cfg=config, soc=soc, soccfg=soccfg,
                              outerFolder=outerFolder)
data_trans = CavitySpecFF.acquire(Instance_trans)
CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
CavitySpecFF.save_data(Instance_trans, data_trans)
