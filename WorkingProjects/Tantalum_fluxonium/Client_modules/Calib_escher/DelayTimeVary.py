
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
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

print('program starting: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

##### define basic parameters

# ####################################### code for running basic single shot exerpiment
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": -0.38,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 20, # [Clock ticks]
    "read_pulse_gain":  6000, # [DAC units]
    "read_pulse_freq": 7392.4, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 0,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.005,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025, ### in us
    "qubit_freq": 0.0,
    "relax_delay": 500,  ### turned into us inside the run function
    #### define shots
    "shots": 50000, ### this gets turned into "reps"
}
config = BaseConfig | UpdateConfig

delay_vec = np.array([0.1, 1, 10, 50, 100, 500, 1000, 5000, 10000, 50000])

##### set the yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])

for idx in range(len(delay_vec)):
    ##### keep track of scans
    print("starting scan " + str(idx))
    print('start time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    ##### set new parameters
    config["relax_delay"] = delay_vec[idx]

    Instance_SingleShotProgram = SingleShotProgram(path="dataSingleShot_delayVary", outerFolder=outerFolder,
                                                   cfg=config,
                                                   soc=soc, soccfg=soccfg)
    data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
    SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram.save_config(Instance_SingleShotProgram)
    SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

    print('scan complete: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    time.sleep(10)

    plt.clf()
