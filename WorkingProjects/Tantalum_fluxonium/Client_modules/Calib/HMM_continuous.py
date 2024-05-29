
import os
import numpy as np
os.environ["OMP_NUM_THREADS"] = '1'
import datetime
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram_hmm import SingleShotProgramHMM

#### define the switch config
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

UpdateConfig = {
    # Set Yoko Voltage
    "yokoVoltage": -1.8,
    "yokoVoltage_freqPoint": -0.24,
    # Readout Parameters
    "read_pulse_style": "const",  # Constant Tone
    "read_length": 25,  # [us]
    "read_pulse_gain": 7000,  # [DAC units]
    "read_pulse_freq": 7392.0,  # [MHz]

    # qubit parameters
    "qubit_pulse_style": "arb",
    "sigma": 0.100,
    "qubit_ge_gain": 600,
    "qubit_ge_freq": 809.5,
    "qubit_ef_gain": 8000,
    "qubit_ef_freq": 5000,
    "relax_delay": 500,

    # Experiment time
    "cen_num": 3,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

### Setting yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])

### Defining the location to store data
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_" + str(
    config["yokoVoltage_freqPoint"]) + "\\"

# Update temperature in the config file
UpdateConfig = {
    "fridge_temp": 20,
}
config = config | UpdateConfig

UpdateConfig = {
    ## qubit spec parameters
    # "qubit_pulse_style": "arb",  # no actual pulse applied. This is just for safety
    # "qubit_gain": 0,  # [in DAC Units]
    # "sigma": 0.005,  # [in us]
    ## define experiment parameters
    "shots": int(1e7),
    "use_switch": False,
    "relax_delay": 0.01,
}
config_hmm = config | UpdateConfig

# Estimating Time
time_required = config_hmm["shots"] * (config_hmm["relax_delay"] + config_hmm['read_length']) * 1e-6 / 60

# Set up the initial plot
fig, (ax1, ax2) = plt.subplots(2, 1, figsize = (14,8))

print("SingleShot for HMM : Total time estimate is ", time_required, " mins")
print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
Instance_SingleShotProgram_HMM = SingleShotProgramHMM(path="SingleShot_NoDelay_" + str(config_hmm["fridge_temp"]),
                                                      outerFolder=outerFolder, cfg=config_hmm,
                                                      soc=soc, soccfg=soccfg)
data_SingleShot_HMM = Instance_SingleShotProgram_HMM.acquire()
Instance_SingleShotProgram_HMM.save_data(data_SingleShot_HMM)
Instance_SingleShotProgram_HMM.save_config()
print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

i_arr = data_SingleShot_HMM['data']['i_arr']
q_arr = data_SingleShot_HMM['data']['q_arr']
x = np.arange(i_arr.size)

# Initial plot setup
line1 = ax1.plot(x, i_arr, 'r-')[0]
line2 = ax2.plot(x, q_arr, 'r-')[0]

data = {'i_arr': i_arr, 'q_arr': q_arr}

def update(frame):
    print("SingleShot for HMM : Total time estimate is ", time_required, " mins")
    print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    Instance_SingleShotProgram_HMM = SingleShotProgramHMM(path="SingleShot_NoDelay_" + str(config_hmm["fridge_temp"]),
                                                          outerFolder=outerFolder, cfg=config_hmm,
                                                          soc=soc, soccfg=soccfg)
    data_SingleShot_HMM = Instance_SingleShotProgram_HMM.acquire()
    Instance_SingleShotProgram_HMM.save_data(data_SingleShot_HMM)
    Instance_SingleShotProgram_HMM.save_config()
    print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

    data['i_arr'] = np.append(data['i_arr'],data_SingleShot_HMM['data']['i_arr'])
    data['q_arr'] = np.append(data['q_arr'],data_SingleShot_HMM['data']['q_arr'])
    x = np.arange(data['i_arr'].size)

    line1.set_data(x, data['i_arr'])
    line2.set_data(x, data['q_arr'])

    ax1.relim()
    ax1.autoscale_view()
    ax2.relim()
    ax2.autoscale_view()

    # time.sleep(3600)

    return line1, line2

# Use lambda to pass additional arguments to update
global ani
max_iteration = 10
ani = FuncAnimation(fig, update, blit=False, frames= max_iteration-1, interval=1, cache_frame_data=False, repeat=False)
plt.show()
