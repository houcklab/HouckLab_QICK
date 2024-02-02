#### import packages
import os

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *

from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS_switch import AmplitudeRabi_PS_switch
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotPS_switch import SingleShotPS_switch
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE

from matplotlib import pyplot as plt
import datetime

#### setting up computer chit-chat hotline
import socket
import csv




# Print the start time
print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

# Disable the interactive mode
plt.ioff()

# ####################################################################################################################
#
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
#

################## code finding T1 of a thermal state using pulses
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -2.4 + 1.25,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 5, # us
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 6437.4,
    ####### spec parameters
    "qubit_freq_start": 4138 - 100,
    "qubit_freq_stop": 4138 + 100,
    "SpecNumPoints": 401,  ### number of points
    "spec_reps": 1000,
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 9000, #12000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.200,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.300,
    "qubit_freq": 4138.0,
    "relax_delay": 100,  ### turned into us inside the run function
    #### define shots
    "shots": 30000, ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0,
    "wait_stop": 2000,
    "wait_num": 51,
    ##### define number of clusters to use
    "cen_num": 3,
    "use_switch": True,
}
config = BaseConfig | UpdateConfig | SwitchConfig
yoko1.SetVoltage(config["yokoVoltage"])

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\ TempChecks\\Yoko_" + str(
    config["yokoVoltage"]) + "\\"

qubit_gain = config["qubit_gain"]
T1_shots = config["shots"]
relax_delay = config["relax_delay"]

#####################################################################
HOST = 'escher-pc'
PORT = 4000

tempr_list = [10,15,20,25,30,35,40,45,50,55,60]

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    print('Connected.')

    isRunning = 1
    while isRunning:
        print('Waiting to reach temperature setpoint...')
        indx_tempr = int(s.recv(1024).decode())
        print('Temperature setpoint = ' + str(tempr_list[indx_tempr]) + " reached")
        s.sendall("Roger.".encode())

        #### find the qubit frequency
        print('finding the qubit frequency: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        config["qubit_gain"] = qubit_gain
        config["shots"] = T1_shots
        config["relax_delay"] = relax_delay

        Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data_specSlice = SpecSlice_bkg_sub.acquire(Instance_specSlice)
        SpecSlice_bkg_sub.save_data(Instance_specSlice, data_specSlice)
        SpecSlice_bkg_sub.display(Instance_specSlice, data_specSlice, plotDisp=True)

        ### find the qubit frequency
        qubitFreq = data_specSlice["data"]["f_reqd"]
        print("qubit_frequency = " + str(qubitFreq) + " MHz")

        config["qubit_freq"] = qubitFreq


        # ###############################################################################
        ##### run the T1 scan
        print('starting T1 scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        scan_time = (np.sum(np.linspace(config["wait_start"], config["wait_stop"], config["wait_num"])) + config["relax_delay"])*config["shots"] *1e-6 / 60

        print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

        Instance_T1_PS = T1_PS(path="dataTestT1_PS", outerFolder=outerFolder, cfg=config,
                                                       soc=soc, soccfg=soccfg)
        data_T1_PS = T1_PS.acquire(Instance_T1_PS)
        T1_PS.save_data(Instance_T1_PS, data_T1_PS)
        T1_PS.save_config(Instance_T1_PS)
        print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        # print('starting data processing: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        # T1_PS.process_data(Instance_T1_PS, data_T1_PS)


        #######################
        ####### run a normal single shot scan for finding the temp
        config["shots"] = 500000
        config["relax_delay"] = 3000
        # config["qubit_gain"] = 0

        scan_time = (config["relax_delay"] * config["shots"] * 2) * 1e-6 / 60

        print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')

        # Instance_SingleShotProgram = SingleShotSSE(path="dataTestSingleShotProgram", outerFolder=outerFolder,
        #                                                cfg=config,
        #                                                soc=soc, soccfg=soccfg)
        # data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
        # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
        # SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
        # SingleShotProgram.save_config(Instance_SingleShotProgram)

        config["initialize_pulse"] = True

        Instance_SingleShotSSE = SingleShotSSE(path="dataSingleShot_TempCalc", outerFolder=outerFolder,
                                               cfg=config,
                                               soc=soc, soccfg=soccfg)
        data_SingleShotSSE = SingleShotSSE.acquire(Instance_SingleShotSSE)
        # SingleShotSSE.display(Instance_SingleShotSSE, data_SingleShotSSE, plotDisp=False, save_fig=True)
        SingleShotSSE.save_data(Instance_SingleShotSSE, data_SingleShotSSE)
        SingleShotSSE.save_config(Instance_SingleShotSSE)

        config["initialize_pulse"] = False
        #######################

        # Saving the filenames to a csv file for post processing
        path_csv = []
        path_csv.append(tempr_list[indx_tempr])
        path_csv.append(config["yokoVoltage"])
        path_csv.append(Instance_specSlice.fname)
        path_csv.append(Instance_T1_PS.fname)
        path_csv.append(Instance_SingleShotSSE.fname)

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

##################################################################################