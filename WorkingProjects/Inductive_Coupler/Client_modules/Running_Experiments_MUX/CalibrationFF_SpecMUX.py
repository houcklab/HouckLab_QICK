from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mFFSpecCalibration_MUX import FFSpecCalibrationMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Compensated_Pulse_Generation import *

# define the save path

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

yoko69.SetVoltage(-0.1799)
yoko70.SetVoltage(-0.1897)
yoko71.SetVoltage(-0.3098)
yoko72.SetVoltage(0.1408)

# flags for initial calibration scans
mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6962.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000, "FF_Gains": [11600, 0, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit': {'Frequency': 4665, 'Gain': 1200},
          'Pulse_FF': [11600, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7033.68 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000, "FF_Gains": [0, 10500, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit': {'Frequency': 4665.09, 'Gain': 1820},
          'Pulse_FF': [0, 10500, 0, 0]},
    '3': {'Readout': {'Frequency': 7104.63 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000, "FF_Gains": [0, 0, 11600, 0]},
          'Qubit': {'Frequency': 4663.13, 'Gain': 1770},
          'Pulse_FF': [0, 0, 15000, 0]},
    '4': {'Readout': {'Frequency': 7230.34 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000, "FF_Gains": [0, 0, 0, -11600]},
          'Qubit': {'Frequency': 4659.32, 'Gain': 1650},
          'Pulse_FF': [0, 0, 0, -11600]}
    }


# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.79, 'Gain': 8000}, 'Qubit': {'Frequency': 4672, 'Gain': 1450}},
#     '2': {'Readout': {'Frequency': 7055.84, 'Gain': 6000}, 'Qubit': {'Frequency': 4757, 'Gain': 990}},
#     '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit': {'Frequency': 4390, 'Gain': 840}},
#     '4': {'Readout': {'Frequency': 7250.01, 'Gain': 6000}, 'Qubit': {'Frequency': 4700, 'Gain': 2630}}
#     }

Qubit_Pulse = 4
# gain_test = -15000 #15000  # 6000  # maximum gain +/-3e4  # -20000 for left qubit, 20000 mid/right
# initial (pre-step) values
FF_gain1_init = 0  # Left Qubit
FF_gain2_init = 0  # Middle Qubit
FF_gain3_init = 0  # Right Qubit
FF_gain4_init = 0  # Right Qubit

FF_gain1_step, FF_gain2_step, FF_gain3_step, FF_gain4_step = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
FF_gain1_read, FF_gain2_read, FF_gain3_read, FF_gain4_read = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['FF_Gains']

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1_read, 'Gain_Expt': FF_gain1_step, 'Gain_Init': FF_gain1_init, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2_read, 'Gain_Expt': FF_gain2_step, 'Gain_Init': FF_gain2_init, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3_read, 'Gain_Expt': FF_gain3_step, 'Gain_Init': FF_gain3_init, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4_read, 'Gain_Expt': FF_gain4_step, 'Gain_Init': FF_gain4_init, 'Gain_Pulse': FF_gain4_pulse}


RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False  # determine qubit frequency
RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "sigma": 0.012, "max_gain": 8000}

cavity_gain = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Frequency']
resonator_frequencies = [Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Frequency']]
gains = [Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Gain'] / 32000.]
BaseConfig['ro_chs'] = [0]


qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

Spec_relevant_params = {"qubit_gain": 500, "SpecSpan": 35, "SpecNumPoints": 36, 'Gauss': True, "sigma": 0.012,
                        "gain": 4900}
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
    config["reps"] = 40  # want more reps and rounds for qubit data
    config["rounds"] = 50
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
    iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
    AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)

# ----------------------------------------------------
# Calibration experiment!

experiment = {
    "delayStart": 0,  # [clock cycles] = 0.00235 us each #FIXME CLOCK
    "delayStep": 10 ,  # [clock cycles] = 0.00235 us each #FIXME CLOCK
    "DelayPoints": 120  # 400  # 28
}
# experiment = {
#     "delayStart": 0,  # [clock cycles] = 0.00235 us each #FIXME CLOCK
#     "delayStep": 70,  # [clock cycles] = 0.00235 us each #FIXME CLOCK
#     "DelayPoints": 10  # 400  # 28
# }
frequencies_dictionary = {
    "trans_freq_start": config["pulse_freq"] - config["TransSpan"],  # [MHz] frequency offset from "cavity_LO" = 7e9
    "trans_freq_stop": config["pulse_freq"] + config["TransSpan"],  # [MHz] frequency offset from "cavity_LO" = 7e9
    "qubit_freq_start": config["qubit_freq"] - config["SpecSpan"],  # [MHz]
    "qubit_freq_stop": config["qubit_freq"] + config["SpecSpan"],  # [MHz]
    "trans_reps": 500,
    "spec_reps": 40,
    "spec_rounds": 40  # 40  #
}
config = config | experiment | frequencies_dictionary

# ARabi_config = {  # long time, low-amplitude pi pulse
#     "sigma": 0.015,  # [us] qubit pulse width
#     "qubit_gain": 8000  # arbitrary units
# }
ARabi_config = {  # short time, high-amplitude pi pulse
    "sigma": 0.007,  # [us] qubit pulse width
    "qubit_gain": 8400 #2380  # arbitrary units
}
ARabi_config = {  # short time, high-amplitude pi pulse
    "sigma": 0.007,  # [us] qubit pulse width
    "qubit_gain": 7960 #2380  # arbitrary units
}
sigma = 0.008
ARabi_config = {  # short time, high-amplitude pi pulse
    "sigma": sigma,  # [us] qubit pulse width
    "qubit_gain": int(qubit_gain * 0.05 / sigma  * 2.5) #2380  # arbitrary units
}
#
# ARabi_config = {  # short time, high-amplitude pi pulse
#     "sigma": 0.007,  # [us] qubit pulse width
#     "qubit_gain": 7500 #2380  # arbitrary units
# }
#
# ARabi_config = {  # short time, high-amplitude pi pulse
#     "sigma": 0.007,  # [us] qubit pulse width
#     "qubit_gain": 9000 #2380  # arbitrary units
# }
config = config | ARabi_config

# pick what pulse to send, module imports
# vs_tosend_step = vs_step_orig  # uncompensated step
# vs_tosend_step = vs_step_comp  # fancy transfer-function-compensated pulse
# vs_tosend_step = vs_delta_orig  # uncompensated delta
# vs_tosend_step = np.zeros(10)  # sanity check
# vs_tosend_step = vs_step_comp_simple  # simple compensated pulse

# set and plot pulse
# vs_tosend_step1 = np.concatenate([np.zeros(7), vs_tosend_step[:-7]])
# config['IQPulseArray'] = [vs_tosend_step, vs_tosend_step, vs_tosend_step, vs_tosend_step]
# config['IDataArray'] = [-15000 * Compensated_AWG((30 * 30 + 2)* 16, Qubit1_parameters)[1], None, None, None]
# config['IDataArray'] = [-15000 * Compensated_AWG_LongTimes((50 * 50 + 2)* 16, Qubit1_parameters_long2)[1], None, None, None]

config['IDataArray'] = [None, None, None, None]
# config['IDataArray'] = [None, 15000 * Compensated_AWG((50 * 50 + 2)* 16, Qubit2_parameters)[1], None, None]

# config['IDataArray'] = [None, 15000 * Compensated_AWG_LongTimes((50 * 50 + 2)* 16, Qubit2_parameters_long)[1], None, None]
# config['IDataArray'] = [None, 15000 * Compensated_AWG_LongTimes((50 * 50 + 2)* 16, Qubit2_parameters_long)[1], None, None]
# config['IDataArray'] = [None, None, None, None]
# config['IDataArray'] = [None, None, None, -20000 * Compensated_AWG_LongTimes((50 * 50 + 2)* 16, Qubit4_parameters_long)[1]]

config['IDataArray'] = [v_awg_Q1 * FF_gain1_pulse, v_awg_Q2 * FF_gain2_pulse, v_awg_Q2 * FF_gain3_pulse, v_awg_Q4 * FF_gain4_pulse]
# FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse
# plt.plot(vs_tosend_step)
# plt.show()

print(config['IDataArray'][1])

# run FF qubit frequency calibration scan
Instance_FFSpecCal = FFSpecCalibrationMUX(path="FFSpecCal", cfg=config, soc=soc, soccfg=soccfg,
                                       outerFolder=outerFolder, progress=True)
data_FFSpecCal = Instance_FFSpecCal.acquire(i_data=True, q_data=False)
Instance_FFSpecCal.save_data(data_FFSpecCal)
