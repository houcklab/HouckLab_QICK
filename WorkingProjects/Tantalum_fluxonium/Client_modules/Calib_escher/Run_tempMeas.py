
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
# from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_ThermalPS_pulse import T1_ThermalPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotPS import SingleShotPS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT2R_PS import T2R_PS
from matplotlib import pyplot as plt
import datetime
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mRepeatReadout import RepeatReadout

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

print('program starting: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))



##### define basic parameters

# ####################################### code for running basic single shot exerpiment
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.58,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # [Clock ticks]
    "read_pulse_gain":  5000, # [DAC units]
    "read_pulse_freq": 7392.433, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 0,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025, ### in us
    "qubit_freq": 0.0,
    "relax_delay": 500,  ### turned into us inside the run function
    #### define shots
    "shots": 150000, ### this gets turned into "reps"
}
config = BaseConfig | UpdateConfig

##### define loop vectors
yoko_vec = np.array([-0.21, -0.22, -0.24, -0.29, -0.38, -0.434, -0.46, -0.5])
read_freq_vec = np.array([7392.2, 7392.05, 7392.0, 7392.15, 7392.4, 7391.65, 7392.05, 7392.25 ])
read_gain_vec = np.array([6000, 5000, 6000, 5000, 6000, 6000, 5000, 6000])
read_length_vec = np.array([40, 20, 20, 20, 20, 20, 20, 15])
wait_vec = np.array([25000, 25000, 25000, 25000, 25000, 25000, 20000, 10000])

print(yoko_vec)

for idx in range(len(yoko_vec)):
    ##### keep track of scans
    print("starting scan " + str(idx))
    print('start time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    ##### set new parameters
    config["yokoVoltage"] = yoko_vec[idx]
    config["read_pulse_freq"] = read_freq_vec[idx]
    config["read_pulse_gain"] = read_gain_vec[idx]
    config["read_length"] = read_length_vec[idx]
    config["relax_delay"] = wait_vec[idx]

    ##### set the yoko voltage
    yoko1.SetVoltage(config["yokoVoltage"])

    ###### pause for some seconds to let yoko settle
    time.sleep(30)

    Instance_SingleShotProgram = SingleShotProgram(path="dataSingleShot_TempMeas_20mK_overnight", outerFolder=outerFolder,
                                                   cfg=config,
                                                   soc=soc, soccfg=soccfg)
    data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
    SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram.save_config(Instance_SingleShotProgram)
    SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

    plt.clf()

    ####### run scan for measuring the rates with markov model
    config["relax_delay"] = 100 ### set 100us delay
    Instance_SingleShotProgram = SingleShotProgram(path="dataSingleShot_RateMeas_20mK_overnight", outerFolder=outerFolder,
                                                   cfg=config,
                                                   soc=soc, soccfg=soccfg)
    data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
    SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram.save_config(Instance_SingleShotProgram)
    SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

    plt.clf()


    # ######### if a low freq scan, attempt a thermal T1 measurmenet
    # if idx < 2:
    #     try:
    #         ################## code finding T1 of a thermal state
    #         UpdateConfig_T1 = {
    #             "relax_delay": 5000,
    #             ### define the wait times
    #             "wait_start": 0,
    #             "wait_stop": 20000,
    #             "wait_num": 41,
    #             ##### define number of clusters to use
    #             "cen_num": 2,
    #         }
    #         config = config | UpdateConfig
    #
    #         yoko1.SetVoltage(config["yokoVoltage"])
    #
    #         print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    #         Instance_T1_ThermalPS = T1_ThermalPS(path="dataTestT1_ThermalPS", outerFolder=outerFolder, cfg=config,
    #                                                        soc=soc, soccfg=soccfg)
    #         data_T1_ThermalPS = T1_ThermalPS.acquire(Instance_T1_ThermalPS)
    #         # T1_ThermalPS.display(Instance_T1_ThermalPS, data_T1_ThermalPS, plotDisp=True, save_fig=True)
    #         T1_ThermalPS.save_data(Instance_T1_ThermalPS, data_T1_ThermalPS)
    #     except:
    #         pass

    print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

    print('scan complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))


#####################################################################################################################
plt.show()
