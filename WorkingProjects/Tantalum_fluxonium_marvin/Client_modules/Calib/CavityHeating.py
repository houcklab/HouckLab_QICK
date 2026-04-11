#%%

# Importing all the packages

import os
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from matplotlib import pyplot as plt

# Importing all the experiements
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_Enhance import \
    Transmission_Enhance
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import \
    SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift_vs_general import StarkShift
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mCavityTransmission_vs_general import CavityInducedHeating
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

# %%
# # TITLE: Transmission + Spectroscopy
UpdateConfig_transmission = {
    # Parameters
    "reps": 6000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 900,
    "read_pulse_freq": 6671.855,  # 6253.8,

    # Experiment Parameter
    "TransSpan": 0.5,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 201,  # number of points in the transmission frequency
}

UpdateConfig_qubit = {
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 6000,  # [DAC Units]
    'sigma': 1,
    'flat_top_length': 5,
    "qubit_length": 25,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 1970,
    "qubit_freq_stop": 2000,
    "SpecNumPoints": 201,  # Number of points
    'spec_reps': 10000,  # Number of repetition

    # Define the yoko voltage
    "yokoVoltage": -0.465,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit

config = BaseConfig | UpdateConfig

# Set the yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])


# %%
# TITLE Perform the cavity transmission experiment

config = BaseConfig | UpdateConfig
Instance_trans = Transmission(path="dataTestTransmission", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_trans = Instance_trans.acquire()
Instance_trans.save_data(data_trans)
Instance_trans.display(data_trans, plotDisp=True)
plt.show()

# Update the transmission frequency to be the peak

config["read_pulse_freq"] = Instance_trans.peakFreq
print("Cavity freq IF [MHz] = {:.6f}".format(Instance_trans.peakFreq))

# %%
# TITLE: Cavity Transmission with phase calculated optimal point of measurement
transm_exp = Transmission_Enhance(path="TransmisionEnhanced", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
data_transm = transm_exp.acquire()
transm_exp.save_data(data_transm)
transm_exp.save_config()
transm_exp.display(data_transm, plotDisp=True)
opt_freq = transm_exp.findOptimalFrequency(data=data_transm, debug=True,window_size = 0.1)
config["read_pulse_freq"] = opt_freq
print(opt_freq)


# %%
# TITLE Perform the spec slice experiment

# Estimate Time
time = config["spec_reps"] * config["SpecNumPoints"] * (
            config["relax_delay"] + config["qubit_length"] + config["read_length"]) * 1e-6
# print("Time required for spec slice experiment is ", datetime.timedelta(seconds = time).strftime('%H::%M::%S'))
print(time)

Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice = SpecSlice.acquire(Instance_specSlice)
SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
SpecSlice.save_data(Instance_specSlice, data_specSlice)
print(Instance_specSlice.qubitFreq)
plt.show()

# %%
# TITLE Perform the spec slice with background subtracted
# config["relax_delay"] = 2000
# config["qubit_gain"] = 20000
time = config["spec_reps"] * config["SpecNumPoints"] * (
            config["relax_delay"] + config["flat_top_length"] + config["read_length"]) * 1e-6
print(time / 60)

Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice_temp", cfg=config,
                                       soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice = SpecSlice_bkg_sub.acquire(Instance_specSlice)
SpecSlice_bkg_sub.save_data(Instance_specSlice, data_specSlice)
SpecSlice_bkg_sub.display(Instance_specSlice, data_specSlice, plotDisp=True)


# %%
# TITLE: Basic Single Shot Experiment
UpdateConfig = {
    # define yoko
    "yokoVoltage": -0.465,

    # cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 50,  # us
    "read_pulse_gain": 2000,  # [DAC units]
    "read_pulse_freq": 6671.855,
    "mode_periodic": False,

    # qubit spec
    "qubit_pulse_style": "const",
    "qubit_freq": 1982.83,
    "qubit_gain": 6000,

    "qubit_length": 25,
    "sigma": 1,
    "flat_top_length": 60,

    "relax_delay": 50,

    # define shots
    "shots": 20000,  ### this gets turned into "reps"

    # Added for switch
    "use_switch": True,

}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
#%%
plt.close('all')
scan_time = (config["relax_delay"] * config["shots"] * 2) * 1e-6 / 60

print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
                                               soc=soc, soccfg=soccfg)
data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
SingleShotProgram.save_config(Instance_SingleShotProgram)
plt.show()

#%%
# Loop over parameters
loop_len = 41

freq_vec = config["read_pulse_freq"] + np.linspace(-0.5, 0.5, loop_len)
qubit_gain_vec = np.linspace(100, 2000, loop_len, dtype=int)
read_gain_vec = np.linspace(600, 3000, loop_len, dtype=int)
read_len_vec = np.linspace(5,80, loop_len)
qubit_freq_vec = np.linspace(-5,5,loop_len) + config["qubit_freq"]

from tqdm import tqdm
for idx in tqdm(range(loop_len)):
    config["read_pulse_freq"] = freq_vec[idx]
    # config["qubit_gain"] = qubit_gain_vec[idx]
    # config["read_pulse_gain"] = read_gain_vec[idx]
    # config["read_length"] = read_len_vec[idx]
    # yoko1.SetVoltage(yoko_vec[idx])
    # config["yokoVoltage"] = yoko_vec[idx]
    # config['qubit_freq'] = qubit_freq_vec[idx]

    Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram_paramSweep_6p75_7",
                                                   outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
    data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
    SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
    SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram.save_config(Instance_SingleShotProgram)

#%%
# TITLE : Stark Shift

UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 25,
    "read_pulse_gain": 5500,
    'cavity_pulse_gain': 1000,
    "read_pulse_freq": 6671.49,

    # Parameters
    "reps": 8000,  # Number of repetitions
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 51,  # number of points in the transmission frequency

    # Qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 20000,  # [DAC Units]
    "qubit_length": 0.5,  # [us]

    # Define qubit experiment parameters
    "qubit_freq_start": 2050,
    "qubit_freq_stop": 2200,
    "SpecNumPoints": 51,  # Number of points
    'spec_reps': 10000,

    # Define cavity experiment parameters
    "param_name": "cavity_pulse_gain",
    "param_start" : 0,
    "param_stop" : 7000,
    "param_num" : 15,

    # Define experiment
    "yokoVoltage": -0.148,
    "relax_delay": 200,  # [us] Delay post one experiment
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "calibrate_cav": False
}

config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
inst_stark_shift = StarkShift(path="StarkShift", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                 progress=True)
data_stark_shift = inst_stark_shift.acquire()
inst_stark_shift.save_data(data = data_stark_shift)
inst_stark_shift.save_config()

#%%
# TITLE : MIST

UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 6000,
    'cavity_pulse_gain': 300,
    "read_pulse_freq": 6432,

    # Parameters
    "reps": 1000,  # Number of repetitions
    "TransSpan": 3,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 101,  # number of points in the transmission frequency

    # Define cavity experiment parameters
    "param_name": "repeat",
    "param_start" : 1,
    "param_stop" : 101,
    "param_num" : 100,

    # Define experiment
    "yokoVoltage": -1.725,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "populate_cavity": False
}

config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
inst_cavity_study = CavityInducedHeating(path="CavityInducedHeating", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                 progress=True)
data_cavity_study = inst_cavity_study.acquire()
inst_cavity_study.save_data(data = data_cavity_study)
inst_cavity_study.save_config()

#%%