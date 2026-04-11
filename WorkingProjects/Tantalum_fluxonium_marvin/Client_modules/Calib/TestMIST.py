# %%

import os
from matplotlib import pyplot as plt
import datetime
import numpy as np
from tqdm import tqdm

# path = os.getcwd()
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift_PS import StarkShiftPS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift import StarkShift
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift_whitenoise_PS import StarkShiftwhitenoise_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift_whitenoise import StarkShift_whitenoise
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_Enhance import \
    Transmission_Enhance
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1Experiment import T1Experiment

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

SwitchConfig = {
    "trig_buffer_start": 0.035,  # in us
    "trig_buffer_end": 0.024,  # in us
    "trig_delay": 0.07,  # in us
}
BaseConfig = BaseConfig | SwitchConfig

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

#%% TITLE : Doing Stark Shift with Post Selection : Helpful at half flux
# Lot of fixed values have been parameterized. Open the experiment file to understand all of them
UpdateConfig = {

    # Readout Tone
    "read_pulse_style": "const",
    "read_length": 25,
    "read_pulse_gain": 7500,
    "read_pulse_freq": 6672.5512,
    "read_pulse_freq_resonant" : 6672.367,

    # Qubit Tone
    "qubit_pulse_style": "const",  # Fixed
    "qubit_gain": 1000,  # [DAC Units]
    "qubit_length": 0.8,  # [us]
    'use_switch': False,
    'qubit_freq_base' : 155.5,

    # Define qubit experiment parameters
    "qubit_freq_start": 147.5,
    "qubit_freq_stop": 160,
    "SpecNumPoints": 51,  # Number of points
    'spec_reps': 20000,

    # Define cavity experiment parameters
    "trans_gain_start" : 100,
    "trans_gain_stop" : 6000,
    "trans_gain_num" : 11,
    'units': 'DAC',
    'pop_length': 20,

    # Define experiment
    'qubit_periodic': False,
    'ro_periodic': False,
    'post_pop_tone_delay': 0.02,
    'pre_meas_delay': 10,
    'wait_before_exp': 10,
    'align': 'right',
    'simultaneous': True,

    # Other stuff
    'initialize_pulse' : True,
    'initialize_qubit_gain' : 2000,
    "yokoVoltage": -0.104,
    "relax_delay": 20,  # [us] Delay post one experiment
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
#%%
soc.reset_gens()
try:
    inst_stark_shift = StarkShiftPS(path="StarkShiftPS", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_stark_shift = inst_stark_shift.acquire()
inst_stark_shift.save_data(data = data_stark_shift)
# inst_stark_shift.save_data_pkl(data = data_stark_shift)
inst_stark_shift.save_config()

#%% TITLE : Stark Shift PS with Agilent
UpdateConfig = {
    # cavity
    "read_pulse_style": "const",
    "read_length": 25,
    "read_pulse_gain": 7500,
    "read_pulse_freq": 6672.5512,  # 6253.8,

    # qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 1000,  # [DAC Units]
    "qubit_length": 0.8,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 120,
    "qubit_freq_stop": 165,
    "qubit_freq_base": 155,
    "SpecNumPoints": 201,  # Number of points
    'spec_reps': 70000,  # Number of repetition
    'align': 'right',
    'pop_length': 20,
    "delay_btwn_pulses" : 10, # Delay between the qubit tone and the readout tone. If not defined it uses 50ns

    # Define agilent setting
    "units" : "DAC",
    "awg_start" : 0.001, # in Vpp
    "awg_stop" : 1, # in Vpp
    "awg_num" : 21, # in Vpp

    # Define the yoko voltage
    "yokoVoltage": -0.104,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': True, # This is for turning off the heating tone
    'initialize_pulse': False,
    'initialize_qubit_gain': 1000,
    'fridge_temp': 420,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

#%%
soc.reset_gens()
try:
    inst_stark_shift_wn = StarkShiftwhitenoise_PS(path="StarkShiftwhitenoise_PS", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_stark_shift_wn = inst_stark_shift_wn.acquire()
inst_stark_shift_wn.save_data(data = data_stark_shift_wn)
inst_stark_shift_wn.save_config()

#%%
#%%
# TITLE : Stark Shift

UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 6.6,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.6612,

    # Parameters
    "reps": 4000,  # Number of repetitions
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 51,  # number of points in the transmission frequency

    # Qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 800,  # [DAC Units]
    "qubit_length": 2,  # [us]
    "flat_top_length":5,
    'sigma': 1,

    # Define qubit experiment parameters
    "qubit_freq_start": 2180,
    "qubit_freq_stop": 2230,
    "SpecNumPoints": 301,  # Number of points
    'spec_reps': 20000,

    # Define cavity experiment parameters
    "trans_gain_start" : 0,
    "trans_gain_stop" : 4500,
    "trans_gain_num" :  31,
    "pop_pulse_length": 10,
    'align': 'right',

    # Define experiment
    "yokoVoltage": -0.42,
    "relax_delay": 10,  # [us] Delay post one experiment
    'wait_between_pulses': 0.05,
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "calibrate_cav": False,
    "simultaneous": True,
}
#%%
soc.reset_gens()
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
try:
    inst_stark_shift = StarkShift(path="StarkShift", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)

except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
try:
    data_stark_shift = inst_stark_shift.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

inst_stark_shift.save_data(data = data_stark_shift)
inst_stark_shift.save_config()

#%%
# TITLE : Stark Shift with Whitenoise

UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 6.6,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.6612,

    # Parameters
    "reps": 4000,  # Number of repetitions
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 51,  # number of points in the transmission frequency

    # Qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 1600,  # [DAC Units]
    "qubit_length": 1,  # [us]
    "flat_top_length":5,
    'sigma': 1,

    # Define qubit experiment parameters
    "qubit_freq_start": 2175,
    "qubit_freq_stop": 2200,
    "SpecNumPoints": 101,  # Number of points
    'spec_reps': 40000,

    # Define cavity experiment parameters
    "awg_gain_start" : 0,
    "awg_gain_stop" : 1,
    "awg_gain_num" :  51,
    "pop_pulse_length": 5,
    'align': 'right',

    # Define experiment
    "yokoVoltage": -0.42,
    "relax_delay": 12,  # [us] Delay post one experiment
    'wait_between_pulses': 0.05,
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "calibrate_cav": False,
    "simultaneous": True,
}
#%%
soc.reset_gens()
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
try:
    inst_stark_shift = StarkShift_whitenoise(path="StarkShift", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                     progress=True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
try:
    data_stark_shift = inst_stark_shift.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

inst_stark_shift.save_data(data = data_stark_shift)
inst_stark_shift.save_config()

#%%
# TITLE  : Sweep flux and get T1 (not post selected so not a single shot experiment)
from tqdm import tqdm

outerFolder += "T1sweep_3\\"
yoko_sweep = np.linspace(-0.16,-0.115, 201)

def freq_predictor(yoko_val):
    # Valid only between -0.11 and -0.16 for 3FLXM0_QCAGE
    return 1000*(-39.063*yoko_val - 4.039)

config = {
    "read_pulse_style": "const",
    "read_length": 20,  # us
    "read_pulse_gain": 2000,  # [DAC units]
    "read_pulse_freq": 6671,  # 6253.8,

    "qubit_freq": 420,
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 2000,  # [DAC Units]
    "qubit_length": 5,  # [us]

    "yokoVoltage": -0.42,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': False, # This is for turning off the heating tone
    'mode_periodic': False,
    'ro_periodic': False,
}

config_transm = {
    "reps": 2000,
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 201,  # number of points in the transmission frequency
    "meas_config": "hanger"
}

config_spec = {
    "qubit_freq_start": 200,
    "qubit_freq_stop": 2500,
    "SpecNumPoints": 101,  # Number of points
    'spec_reps': 20000,  # Number of repetition
    "delay_btwn_pulses" : 0.05, # Delay between the qubit tone and the readout tone. If not defined it uses 50ns
}

config_t1_crude = { # Assume T1 of 2000us
    "relax_delay": 6000,
    "start": 0,
    "step": 4,
    "expts": 251,
    "reps": 5000,
}

config_t1_fine = { # Assume T1 of 500us
    "relax_delay": 2500,
    "start": 0,
    "step": 50,
    "expts": 301,
    "reps": 40000,
}

cavity_freq = []
qubit_freq = []
t1_meas = []
t1_err_meas = []

print("STARTING EXPERIMENT")
for i in tqdm(range(yoko_sweep.size)):
    yoko1.SetVoltage(yoko_sweep[i])
    config['yokoVoltage'] = yoko_sweep[i]
    outerFolderyoko = outerFolder + "yoko_" + str(yoko_sweep[i]) + "\\"
    print(f"Saving to {outerFolderyoko}")

    # Perform a transmission
    config_transm = config_transm | config | BaseConfig

    if i == 0:
        tot_time = config_transm["reps"] * config_transm["TransNumPoints"] * (
                config_transm["relax_delay"] + config_transm["read_length"]) * 1e-6
        print(f"Transmission ETA {tot_time / 60} min")

    transm_exp = Transmission_Enhance(path="TransmisionEnhanced", cfg=config_transm, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolderyoko)
    data_transm = transm_exp.acquire()
    transm_exp.save_data(data_transm)
    transm_exp.save_config()
    transm_exp.display(data_transm, plotDisp=False)
    opt_freq = transm_exp.findOptimalFrequency(data=data_transm, debug=True, window_size=0.1)
    config["read_pulse_freq"] = opt_freq
    cavity_freq.append(opt_freq)

    # Perform a pulsed spec
    qubit_freq_pred = freq_predictor(yoko_sweep[i])
    config_spec['qubit_freq_start'] = qubit_freq_pred - 50
    config_spec['qubit_freq_stop'] = qubit_freq_pred + 50

    config_spec = config_spec | config | BaseConfig

    if i == 0:
        tot_time = config_spec["spec_reps"] * config_spec["SpecNumPoints"] * (
                config_spec["relax_delay"] + config_spec["qubit_length"] + config_spec["read_length"]) * 1e-6
        print(f"Spec ETA {tot_time / 60} min")

    inst_spec = SpecSlice(path="SpecSlice", cfg=config_spec, soc=soc, soccfg=soccfg, outerFolder=outerFolderyoko)
    data_specSlice = inst_spec.acquire()
    inst_spec.save_data(data_specSlice)
    inst_spec.display(data_specSlice, plotDisp=False)
    config['qubit_freq'] = inst_spec.qubitFreq
    qubit_freq.append(inst_spec.qubitFreq)
    print(f"Chosen qubit frequency is {config['qubit_freq']} MHz")

    # Perform a crude T1 experiment
    config_t1_crude = config_t1_crude | config | BaseConfig


    tot_time = (np.sum(np.linspace(config_t1_crude["start"], config_t1_crude['step'] * (config_t1_crude["expts"] - 1), config_t1_crude["expts"]))
                + config_t1_crude["expts"] * (config_t1_crude["relax_delay"] + config_t1_crude['read_length'] + config_t1_crude['qubit_length'])) * config_t1_crude["reps"] * 1e-6
    print(f"T1 crude ETA {tot_time/60} min")

    inst_t1 = T1Experiment(path="T1_crude", outerFolder=outerFolderyoko, cfg=config_t1_crude, soc=soc, soccfg=soccfg,
                           progress=True)
    data_t1 = inst_t1.acquire()
    inst_t1.display(data_t1, plotDisp=False)
    inst_t1.save_data(data_t1)
    inst_t1.save_config()
    T1 = inst_t1.T1_est
    if T1 > 100000 or T1 < 0:
        print("Couldn't find a T1")
        t1_meas.append(0)
        t1_err_meas.append(0)
        continue
    config_t1_fine['relax_delay'] = int(6*T1)
    config_t1_fine['step'] = 5*T1/(config_t1_fine['expts']-1)

    # Perform a fine t1 experiment
    config_t1_fine = config_t1_fine | config | BaseConfig

    if i == 0 :
        tot_time = (np.sum(np.linspace(config_t1_fine["start"], config_t1_fine['step'] * (config_t1_fine["expts"] - 1), config_t1_fine["expts"]))
                    + config_t1_fine["expts"] * (config_t1_fine["relax_delay"] + config_t1_fine['read_length'] + config_t1_fine['qubit_length'])) * config_t1_fine["reps"] * 1e-6
        print(f"T1 fine ETA{tot_time/60} min")

    inst_t1 = T1Experiment(path="T1_fine", outerFolder=outerFolderyoko, cfg=config_t1_fine, soc=soc, soccfg=soccfg,
                           progress=True)
    data_t1 = inst_t1.acquire()
    inst_t1.display(data_t1, plotDisp=False)
    inst_t1.save_data(data_t1)
    inst_t1.save_config()
    t1_meas.append(inst_t1.T1_est)
    t1_err_meas.append(inst_t1.T1_err[1,1])

#%%
fig, axs = plt.subplots(figsize = (15,10))
axs.errorbar(yoko_sweep,t1_meas, yerr=np.sqrt(t1_err_meas))
# axs.scatter(yoko_sweep, t1_meas)
axs.set_xlabel('yoko voltage (in V)')
axs.set_ylabel('T1 (in us)')
# axs.set_ylim([0,3000])
axs.set_yscale('log')
plt.show()
plt.savefig(outerFolder+"alldata.png", dpi = 600)
plt.savefig(outerFolder+"alldata.pdf")
#%%
fig, axs = plt.subplots(figsize = (15,10))
axs.scatter(yoko_sweep, qubit_freq)
axs.set_xlabel('yoko voltage (in V)')
axs.set_ylabel('Qubit Frequency')
plt.show()
