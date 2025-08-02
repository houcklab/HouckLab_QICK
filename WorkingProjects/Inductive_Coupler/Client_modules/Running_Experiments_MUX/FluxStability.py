from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mFluxStabilitySpec import FluxStability
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Compensated_Pulse_Generation import *

# flags for initial calibration scans
mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    # '1': {'Readout': {'Frequency': 6978.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 15000,
    #                   "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
    #       'Qubit': {'Frequency': 4441.5, 'Gain': 4800},
    #       'Pulse_FF': [0, 0, 0, 0]},  # second index
    '1': {'Readout': {'Frequency': 6978.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 11000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4401.7, 'Gain': 10000},
          'Pulse_FF': [0, 0, 0, 0]},  #second index' for flux stability
    # '2': {'Readout': {'Frequency': 7092.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000, "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
    #       # 'Qubit': {'Frequency': 5107.4, 'Gain': 1150},
    #       'Qubit': {'Frequency': 4724.7, 'Gain': 1150},
    #       # 'Qubit': {'Frequency': 5256.4, 'Gain': 1500},
    #       # 'Qubit': {'Frequency': 5100, 'Gain': 1150},
    #       'Pulse_FF': [0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7095.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4554.3, 'Gain': 4740},
          'Pulse_FF':[0, 0, 0, 0]}, #Third index
    '3': {'Readout': {'Frequency': 7127.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 9000, "FF_Gains": [0, 0, 0, 0]},
          'Qubit': {'Frequency': 5096.2, 'Gain': 1400},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7458.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000, "FF_Gains": [0, 0, 0, 0]},
          'Qubit': {'Frequency': 4280, 'Gain': 1650},
          'Pulse_FF': [0, 0, 0, 10000]},
    '5': {'Readout': {'Frequency': 7325.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
              'Qubit': {'Frequency': 4047.84, 'Gain': 4000},
              'Pulse_FF': [0, 0, 0, 0]}
    }

Qubit_Pulse = 1

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False # determine qubit frequency
RunAmplitudeRabi = False
RunFluxStability = True

Spec_relevant_params = {"qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 61, 'Gauss': False, "sigma": 0.15,
                        "gain": 1000, 'reps': 30, 'rounds': 30}
# Spec_relevant_params = {"qubit_gain": 50, "SpecSpan": 20, "SpecNumPoints": 61, 'Gauss': True, "sigma": 0.5,
#                         "gain": 200, 'reps': 60, 'rounds': 30}
Spec_relevant_params = {"qubit_gain": 1000, "SpecSpan": 5, "SpecNumPoints": 91, 'Gauss': True, "sigma": 0.2,
                        "gain": 1500, 'reps': 30, 'rounds': 30}

# Spec_relevant_params = {"qubit_gain": 100, "SpecSpan": 10, "SpecNumPoints": 61, 'Gauss': True, "sigma": 0.2,
#                         "gain": 2000, 'reps': 30, 'rounds': 30}

Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "sigma": 0.2, "max_gain": 10000}

hours = 16
Flux_Stability_params = {'delaystep': 1}  #DelayStep in minutes
delay_points = int(hours * 60 // Flux_Stability_params['delaystep'])
Flux_Stability_params['delaypoints'] = delay_points


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



cavity_gain = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Frequency']
resonator_frequencies = [Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Frequency']]
gains = [Qubit_Parameters[str(Qubit_Pulse)]['Readout']['Gain'] / 32000.]
BaseConfig['ro_chs'] = [0]


qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

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
    config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_relevant_params['rounds']
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

# ----------------------------------------------------
# Calibration experiment!

if RunFluxStability:
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']

    experiment = {
        "delayStart": 0,  # [clock cycles] = 0.00235 us each #FIXME CLOCK
        "delayStep": Flux_Stability_params['delaystep'],  # time between experiments (minutes)
        "DelayPoints": Flux_Stability_params['delaypoints']  # 400  # 28
    }
    frequencies_dictionary = {
        "trans_freq_start": config["pulse_freq"] - config["TransSpan"],  # [MHz] frequency offset from "cavity_LO" = 7e9
        "trans_freq_stop": config["pulse_freq"] + config["TransSpan"],  # [MHz] frequency offset from "cavity_LO" = 7e9
        "qubit_freq_start": config["qubit_freq"] - config["SpecSpan"],  # [MHz]
        "qubit_freq_stop": config["qubit_freq"] + config["SpecSpan"],  # [MHz]
        "trans_reps": 500,
        "spec_reps": Spec_relevant_params['reps'] ,
        "spec_rounds": Spec_relevant_params['rounds']   # 40  #
    }
    config = config | experiment | frequencies_dictionary

    config['IDataArray'] = [None, None, None, None]

# run FF qubit frequency calibration scan
    Instance_FluxStability = FluxStability(path="FluxStability", cfg=config, soc=soc, soccfg=soccfg,
                                           outerFolder=outerFolder, progress=True)
    data_FluxStability = Instance_FluxStability.acquire() #i_data=True, q_data=False)
    Instance_FluxStability.save_data(data_FluxStability)
