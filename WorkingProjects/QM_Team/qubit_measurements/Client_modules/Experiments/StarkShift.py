# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mStarkShift import StarkShift
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChiShift import ChiShift

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1_SS import T1_SS
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF

soc, soccfg = makeProxy_RFSOC_11()

#### define the saving path

############### Start Can D ############################
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7074.212, 'Gain': 4000},
          'Qubit': {'Frequency': 5343.40, 'Gain': 6600, "sigma": 0.1, "flattop_length": 0.75}, #pi: 6600, pi/2: 3300
          'outerfoldername': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Siegert_02/BF2_test/Q1/"},
    '2': {'Readout': {'Frequency': 7191.452, 'Gain': 3700},
          'Qubit': {'Frequency': 5179.30, 'Gain': 8100, "sigma": 0.1, "flattop_length": 0.5}, #pi: 8100, pi/2: 4050
          'outerfoldername': "Z:/t1Team/Data/2024-12-22_CoolDown/TATCR02_Siegert_02/BF2_test/Q2/"},
    '3': {'Readout': {'Frequency': 7270.524, 'Gain': 4000},
          'Qubit': {'Frequency': 4685.7, 'Gain': 8000, "sigma": 0.1, "flattop_length": 0.75}, #pi: 8000, pi/2: 4000
          'outerfoldername': "Z:/t1Team/Data/2024-12-22_CoolDown/TATCR02_Siegert_02/BF2_test/Q3/"},
    '4': {'Readout': {'Frequency': 7371.936, 'Gain': 4400},
          'Qubit': {'Frequency': 4351.38, 'Gain': 7600, "sigma": 0.05, "flattop_length": 0.1}, #pi: 7600, pi/2: 3800
          'outerfoldername': "Z:/t1Team/Data/2024-12-22_CoolDown/TATCR02_Siegert_02/BF2_test/Q4/"}
    }
# ############### End Can D ############################

# Readout
Qubit_Readout = 1
Qubit_Pulse = 1
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

ConstantTone = False  # determine cavity frequency

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = True
RunStarkShift = False

cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']


trans_config = {
    "reps": 800,  # this will be used for all experiments below unless otherwise changed in between trials
    "rounds": 1,
    "pulse_style": "const",  # --Fixed
    "readout_length": 20,  # [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 1,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 201,  ### number of points in the transmission frequency
    "cav_relax_delay": 10
}
Spec_relevant_params = {"qubit_gain": 10000, "SpecSpan": 2, "SpecNumPoints": 501,
                        "reps": 400, 'rounds': 1,
                        'Gauss': False, "sigma": 2, "gain": 28000} # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse

qubit_config = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,
    "length": 20, # Cavity Length
    "qubit_length": 50,
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
}
spec_cfg = {
    "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

stark_shift_config = {
    'trans_gain_start': 100,
    'trans_gain_stop': 5000,
    'trans_gain_num': 5,
    'qb_periodic': False,
    'ro_periodic': True,
    'relax_delay': 20,
    "units" : 'DAC',
    'Gauss': False,
    'cavity_winding_freq' : 0,
    'cavity_winding_offset': 0
}


UpdateConfig = trans_config | qubit_config | spec_cfg | stark_shift_config
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
    CavitySpecFF.save_config(Instance_trans)

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
    config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']
    # config["pulse_gain"] =
    print("Cavity gain", config["pulse_gain"])
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
    QubitSpecSliceFF.save_config(Instance_specSlice)


# Stark Shift Experiment
if RunStarkShift:
    print("Running StarkShift")
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    inst_stark_shift = StarkShift(path="Stark_Shift", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_stark_shift = inst_stark_shift.acquire()
    inst_stark_shift.save_data(data = data_stark_shift)
    inst_stark_shift.save_config()