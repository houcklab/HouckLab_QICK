#### import packages
import os

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS_switch import \
    AmplitudeRabi_PS_switch
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotPS_switch import SingleShotPS_switch
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_ef_spectroscopy import Qubit_ef_spectroscopy

from matplotlib import pyplot as plt
import datetime

# setting up computer chit-chat hotline
import socket
import csv

# Print the start time
print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

# Disable the interactive mode
plt.ioff()

####################################################################################################################

# Adding config of the switch to the baseconfig
SwitchConfig = {
    "trig_buffer_start": 0.035,  # in us
    "trig_buffer_end": 0.024,  # in us
    "trig_delay": 0.07,  # in us
}

BaseConfig = BaseConfig | SwitchConfig

# Defining common experiment configurations
UpdateConfig = {
    # Set Yoko Voltage
    "yokoVoltage": -1.8,

    # Readout Parameters
    "read_pulse_style": "const",  # Constant Tone
    "read_length": 5,  # [us]
    "read_pulse_gain": 7400,  # [DAC units]
    "read_pulse_freq": 6437.4,  # [MHz]

    # qubit parameters
    "qubit_pulse_style": "arb",
    "sigma": 0.100,
    "qubit_ge_gain": 600,
    "qubit_ge_freq": 2243.4,
    "qubit_ef_gain": 8000,
    "qubit_ef_freq": 2081.5,
    "relax_delay": 500,

    # Experiment time
    "cen_num": 3,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\ TempChecks\\Yoko_" + str(
    config["yokoVoltage"]) + "\\"

#####################################################################
HOST = 'escher-pc'
PORT = 4000

tempr_list = [0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75]

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    print('Connected.')

    isRunning = 1
    while isRunning:
        print('Waiting to reach temperature setpoint...')
        indx_tempr = int(s.recv(1024).decode())
        print('Temperature setpoint = ' + str(tempr_list[indx_tempr]) + " reached")
        s.sendall("Roger.".encode())

        ### TITLE: Find the qubit ge frequency
        print('finding the qubit g-e frequency: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        # Defining the config for the spec slice experiment
        UpdateConfig_spec = {
            # Qubit Tone
            'qubit_gain': 600,

            # Define spec slice experiment parameters
            "qubit_freq_start": 2000,
            "qubit_freq_stop": 2500,
            "SpecNumPoints": 501,  # Number of points

            # Experiment type
            'spec_reps': 1000,  # Number of repetition
            "relax_delay": 10,  # [us] Delay post one experiment
        }
        config_spec = config | UpdateConfig_spec

        Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice_temp_" + str(tempr_list[indx_tempr]),
                                               cfg=config_spec,
                                               soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data_specSlice = SpecSlice_bkg_sub.acquire(Instance_specSlice)
        SpecSlice_bkg_sub.save_data(Instance_specSlice, data_specSlice)
        SpecSlice_bkg_sub.display(Instance_specSlice, data_specSlice, plotDisp=False)

        # Get the qubit frequency
        qubitFreq = data_specSlice["data"]["f_reqd"]
        print("qubit_frequency = " + str(qubitFreq) + " MHz")
        config["qubit_ge_freq"] = qubitFreq

        ### TITLE: Find the qubit e-f frequency
        print('finding the qubit e-f frequency: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        # Defining the config for the three tone spec slice experiment
        UpdateConfig_ef_spec = {
            # g-e parameters
            "qubit_ge_gain": 600,  # Gain for pi pulse in DAC units

            # e-f spec parameter
            "qubit_ef_freq_start": 2060,
            "qubit_ef_freq_step": 0.5,
            'qubit_ef_gain': 5000,
            "SpecNumPoints": 80,

            # Experiment details
            "relax_delay": 500,
            "reps": 1000,

        }
        config_ef_spec = config | UpdateConfig_ef_spec

        Instance_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy",
                                                               outerFolder=outerFolder, cfg=config_ef_spec, soc=soc,
                                                               soccfg=soccfg, progress=True)
        data_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy.acquire(Instance_Qubit_ef_spectroscopy)
        Qubit_ef_spectroscopy.save_data(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy)
        Qubit_ef_spectroscopy.save_config(Instance_Qubit_ef_spectroscopy)
        Qubit_ef_spectroscopy.display(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy, plotDisp=False)

        # Get the qubit ef frequency
        qubitFreq_ef = data_Qubit_ef_spectroscopy["data"]["f_reqd"]
        print("qubit_frequency ef = " + str(qubitFreq_ef) + " MHz")
        config["qubit_ef_freq"] = qubitFreq_ef

        ### TITLE: Run the T1 scan
        print('starting T1 scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Update_config_T1 = {
            # qubit parameters
            "qubit_pulse_style": "arb",
            "sigma": 0.100,
            "qubit_ge_gain": 250,
            "qubit_ef_gain": 8000,
            "relax_delay": 1500,

            # define shots
            "shots": 40000,

            # define the wait times
            "wait_start": 0,
            "wait_stop": 1200,
            "wait_num": 101,
        }

        config_T1 = config | Update_config_T1
        scan_time = (np.sum(np.linspace(config_T1["wait_start"], config_T1["wait_stop"], config_T1["wait_num"])) +
                     config_T1["relax_delay"]) * config_T1["shots"] * 1e-6 / 60

        print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

        Instance_T1_PS = T1_PS(path="dataTestT1_PS_temp_" + str(tempr_list[indx_tempr]), outerFolder=outerFolder,
                               cfg=config_T1,
                               soc=soc, soccfg=soccfg)
        data_T1_PS = T1_PS.acquire(Instance_T1_PS)
        T1_PS.save_data(Instance_T1_PS, data_T1_PS)
        T1_PS.save_config(Instance_T1_PS)
        print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        # T1_PS.process_data(Instance_T1_PS, data_T1_PS)

        ### TITLE: Run single shot scan for finding the temp
        Update_config_ss = {
            # qubit parameters
            "qubit_pulse_style": "arb",
            "sigma": 0.100,
            "qubit_ge_gain": 250,
            "qubit_ef_gain": 8000,

            # Experiment parameters
            'shots' : 1000000,
            'relax_delay' : 4000,
            'initialize_pulse' : True,
        }
        config_ss = config | Update_config_ss

        scan_time = (config_ss["relax_delay"] * config_ss["shots"] * 2) * 1e-6 / 60
        print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')
        Instance_SingleShotSSE = SingleShotSSE(path="dataSingleShot_TempCalc_temp_" + str(tempr_list[indx_tempr]),
                                               outerFolder=outerFolder,
                                               cfg=config_ss,
                                               soc=soc, soccfg=soccfg)
        data_SingleShotSSE = SingleShotSSE.acquire(Instance_SingleShotSSE)
        # SingleShotSSE.display(Instance_SingleShotSSE, data_SingleShotSSE, plotDisp=False, save_fig=True)
        SingleShotSSE.save_data(Instance_SingleShotSSE, data_SingleShotSSE)
        SingleShotSSE.save_config(Instance_SingleShotSSE)

        #######################
        # Saving the filenames to a csv file for post-processing
        path_csv = []
        path_csv.append(tempr_list[indx_tempr])
        path_csv.append(config["yokoVoltage"])
        path_csv.append(Instance_specSlice.fname)
        path_csv.append(Instance_T1_PS.fname)
        path_csv.append(Instance_SingleShotSSE.fname)
        path_csv.append(Instance_Qubit_ef_spectroscopy.fname)

        # Saving to a csv file
        loc = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\TempChecks\\summary\\"
        fname = "TF4_cooldown6_pathtodata.csv"

        # Open the existing CSV file in append mode
        with open(loc + fname, mode='a', newline='') as file:
            # Create a CSV writer object
            writer = csv.writer(file)

            # Write the list to the CSV file
            writer.writerow(path_csv)

        # Close the open csv
        file.close()

        print("Message sent:Client Ready")
        s.sendall("Client Ready".encode())

        message = s.recv(1024).decode()
        print("Message received:" + message)
        if message != "Server Ready":
            print("Communication error :(, was expecting \"Server Ready\"!")
            exit
        new_tempr_indx = int(s.recv(1024).decode())

        if new_tempr_indx >= len(tempr_list):
            isRunning = 0
