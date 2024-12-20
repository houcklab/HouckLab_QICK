# Import standard packages
import os
import time
import numpy as np
from matplotlib import pyplot as plt
import datetime
import json
from tqdm import tqdm
import random

# Import Experiments
path = r'/WorkingProjects/Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_shots import SpecSlice_shots
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShotProgram_hmm import SingleShotProgramHMM


# Defining the standard config files
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

# Defining common experiment configurations
UpdateConfig = {
    ## set yoko
    "yokoVoltage": -0.2068,  # [in V]
    "yokoVoltage_freqPoint": -0.2068,  # [in V] used for naming the file systems
    ## cavity
    "reps": 2000,  # placeholder for reps. Cannot be undefined
    "read_pulse_style": "const",
    "read_length": 10,  # [in us]
    "read_pulse_gain": 7000,  # [in DAC units]
    "read_pulse_freq": 892.0,  # [in MHz]
    ## qubit drive parameters
    "qubit_freq": 2820.65,  # [in MHz]
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 4000,
    "sigma": 2,  ### units us, define a 20ns sigma
    "flat_top_length": 8.0,  ### in us
    ## experiment parameters
    "cen_num": 2,  # Number of states expected
    "relax_delay": 100,
}
config = BaseConfig | UpdateConfig

# Setting yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])

# Get the current date and time
now = datetime.datetime.now()

# Format the date and time as requested
formatted_datetime = now.strftime("%Yy%mm%dd_%Hh_%Mm")
formatted_datetime

# Defining the outerfolder
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TLS_check\\"+formatted_datetime+"\\"+str(config["yokoVoltage_freqPoint"]) + "\\" #\\"+formatted_datetime+"

UpdateConfig = {
    "fridge_temp": 20,
}
config = config | UpdateConfig

for i in tqdm(range(50)):
    # UpdateConfig = {
    #     "qubit_freq_start": config["qubit_freq"] - 20,
    #     "qubit_freq_stop": config["qubit_freq"] + 20,
    #     "SpecNumPoints": 51,  ### number of points
    #     ##### define spec slice experiment parameters
    #     "qubit_gain": 4000,
    #     "spec_reps": 10000,
    #     "use_switch": True,
    # }
    # config_rc = config | UpdateConfig
    #
    # time_required = config_rc["spec_reps"]*config_rc["SpecNumPoints"]*(config_rc["read_length"]+config_rc["flat_top_length"]+config_rc["relax_delay"])/1e6/60
    # print("Time required for one Spec Slice is ", str(time_required)," in min")
    # print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    # Instance_specSlice = SpecSlice_shots(path="SpecSlice_" + str(config_rc["fridge_temp"]), cfg=config_rc, soc=soc, soccfg=soccfg, outerFolder = outerFolder)
    # data_specSlice= Instance_specSlice.acquire()
    # Instance_specSlice.display(data_specSlice, plotDisp=False)
    # Instance_specSlice.save_config()
    # Instance_specSlice.save_data(data_specSlice)
    # print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

    UpdateConfig = {
        ## qubit spec parameters
        # "qubit_pulse_style": "arb",  # no actual pulse applied. This is just for safety
        # "qubit_gain": 0,  # [in DAC Units]
        # "sigma": 0.005,  # [in us]
        ## define experiment parameters
        "shots": int(1e6),
        "use_switch": False,
        "relax_delay": 100,
    }
    config_hmm = config | UpdateConfig
    #%%
    if True:
        # TITLE: Run SingleShotNoDelay continuously
        # Estimating Time
        time_required = config_hmm["shots"] * (config_hmm["relax_delay"] + config_hmm['read_length']) * 1e-6 / 60

        print("SingleShot for HMM : Total time estimate is ", time_required, " mins")
        print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Instance_SingleShotProgram_HMM = SingleShotProgramHMM(path="SingleShot_NoDelay_" + str(config_hmm["fridge_temp"]),
                                                              outerFolder=outerFolder, cfg=config_hmm,
                                                              soc=soc, soccfg=soccfg)
        data_SingleShot_HMM = Instance_SingleShotProgram_HMM.acquire()
        Instance_SingleShotProgram_HMM.save_data(data_SingleShot_HMM)
        Instance_SingleShotProgram_HMM.save_config()
        Instance_SingleShotProgram_HMM.display(data_SingleShot_HMM, plotDisp=False)
        print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    time.sleep(1200)
#%%
#TITLE: RUN SingleshotNoDelay at different YokoVoltages

# # Run the code 3 times
# for run_code_idx in range(3):
#
#     # Defining the outerfolder
#     outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TLS_check\\"+formatted_datetime+"\\Flux_Sweep\\"
#
#     fname = r'Z:\TantalumFluxonium\Data\2023_10_31_BF2_cooldown_6\WTF\TempChecks\Summary\WTF_cooldown6_master_config.json'
#     with open(fname, 'r') as f:
#         master_config = json.load(f)
#
#     yoko_voltage_vec_str = master_config['yoko_voltage']
#     print("The voltages are : ", yoko_voltage_vec_str)
#     yoko_voltage_vec_str_random = yoko_voltage_vec_str.copy()
#     random.shuffle(yoko_voltage_vec_str_random)
#     print("The shuffled voltages are : ", yoko_voltage_vec_str_random)
#
#     for i in tqdm(range(len(yoko_voltage_vec_str_random))):
#         print("Voltage is being set to ", str(float(yoko_voltage_vec_str_random[i])))
#         config['yokoVoltage'] = float(yoko_voltage_vec_str_random[i])
#         config['yokoVoltage_freqPoint'] = config['yokoVoltage']
#
#         # Setting yoko voltage
#         yoko1.SetVoltage(config["yokoVoltage"])
#         print("Yoko Voltage set to " + str(config["yokoVoltage"]) + " V")
#         print("Waiting for 5 minutes. Please be patient")
#         time.sleep(300)
#
#         # Getting the config
#         config_voltage = master_config[yoko_voltage_vec_str_random[i]]
#         print("The new config parameter")
#         print(config_voltage)
#         config = config | config_voltage
#
#         # Updating the config for hmm
#         UpdateConfig = {
#             ## qubit spec parameters
#             "qubit_pulse_style": "arb",  # no actual pulse applied. This is just for safety
#             "qubit_gain": 0,  # [in DAC Units]
#             "sigma": 0.005,  # [in us]
#             ## define experiment parameters
#             "shots": int(4e7),
#             "use_switch": False,
#             "relax_delay": 0.01,
#         }
#         config_hmm = config | UpdateConfig
#
#         # Running the HMM Code
#         time_required = config_hmm["shots"] * (config_hmm["relax_delay"] + config_hmm['read_length']) * 1e-6 / 60
#
#         print("SingleShot for HMM : Total time estimate is ", time_required, " mins")
#         print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#         Instance_SingleShotProgram_HMM = SingleShotProgramHMM(path="SingleShot_NoDelay_" + str(config_hmm["fridge_temp"]),
#                                                               outerFolder=outerFolder, cfg=config_hmm,
#                                                               soc=soc, soccfg=soccfg)
#         data_SingleShot_HMM = Instance_SingleShotProgram_HMM.acquire()
#         Instance_SingleShotProgram_HMM.save_data(data_SingleShot_HMM)
#         Instance_SingleShotProgram_HMM.save_config()
#         print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
