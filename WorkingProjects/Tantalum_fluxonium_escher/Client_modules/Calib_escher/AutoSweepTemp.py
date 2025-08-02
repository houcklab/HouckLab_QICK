import os
os.environ["OMP_NUM_THREADS"] = '1'
import sys
import csv
import time

path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.LS370 as lk
import pyvisa
import datetime

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mT1_PS_sse import T1_PS_sse
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQND import QNDmeas
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTimeOfFlight_PS import TimeOfFlightPS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mAmplitudeRabiBlob_PS_sse import AmplitudeRabi_PS_sse
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub

###########
#### define the switch cofidg
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig
######################

### Set up the Lakeshore
rm = pyvisa.ResourceManager()
LS370_connection = rm.open_resource('GPIB0::12::INSTR')
lakeshore = lk.Lakeshore370(LS370_connection)

### Defining temperature sweep configuration
tempr_cfg = {
    'tempr_list': [10,15,20,25,30,35,40,45,50,55,60],  # [in mK]
    'wait_time': 15 * 60,  # [in seconds]
    'max_deviation': 5,  # [in mK] maximum instability of temperature allowed
    'patience_ctr': 3,  # Number of tries an experiment be retried
}
# Defining initial T1
T1_meas = 6000

### Defining common experiment configurations
UpdateConfig = {
    ## set yoko
    "yokoVoltage": -0.37,  # [in V]
    "yokoVoltage_freqPoint": -0.37,  # [in V] used for naming the file systems
    ## cavity
    "reps": 2000,  # placeholder for reps. Cannot be undefined
    "read_pulse_style": "const",
    "read_length": 10,  # [in us]
    "read_pulse_gain": 7000,  # [in DAC units]
    "read_pulse_freq": 7392.36,  # [in MHz]
    ## qubit drive parameters
    "qubit_freq": 2815.65,  # [in MHz]
    "qubit_pulse_style": "flat_top",
    "qubit_gain": 10000,
    "sigma": 0.5,  ### units us, define a 20ns sigma
    "flat_top_length": 20.0,  ### in us
    ## experiment parameters
    "cen_num": 2,  # Number of states expected
    "relax_delay": 5*T1_meas,
}
config = BaseConfig | UpdateConfig



### Setting yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])

### Defining the location to store data
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Yoko_" + str(
    config["yokoVoltage_freqPoint"]) + "\\"

### TITLE : Beginning the sweep
for i in range(len(tempr_cfg["tempr_list"])):
    ## Set temperature and wait for 'wait_time' for the fridge to thermalize
    # TODO : Generalize the wait_time for hot and cold thermalization
    lakeshore.set_temp(tempr_cfg["tempr_list"][i])
    time.sleep(tempr_cfg["wait_time"])
    # Update temperature in the config file
    UpdateConfig = {
        "fridge_temp": tempr_cfg["tempr_list"][i],
    }
    config = config | UpdateConfig

    ### Defining the data entry list and path list
    data_csv = []
    path_csv = []

    ###region TITLE: QND Measurement
    UpdateConfig = {
        ##### qubit spec parameters
        # "qubit_pulse_style": "arb",
        # "qubit_gain": 0,
        # "sigma": 0.005,  ### units us, define a 20ns sigma
        # "flat_top_length": 10.0,  ### in us
        "relax_delay": 0.01,  ### turned into us inside the run function
        #### define shots
        "shots": 4000000,  ### this gets turned into "reps"

        "use_switch": True,
    }
    config_qnd = config | UpdateConfig

    time_required = config_qnd["relax_delay"] * config_qnd["shots"] / 1e6 / 60

    # Measuring
    is_fluctuating = 1
    ctr = 1
    while is_fluctuating:
        if ctr > tempr_cfg["patience_ctr"]:
            lakeshore.set_setpoint(5)
            lakeshore.set_heater_range(0)
            sys.exit("Lakeshore has run out of patience. Human required!")


        print("QND : Total time estimate is " + str(time_required) + " min")
        print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Instance_QNDmeas = QNDmeas(path="QND_Meas_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder,
                                   cfg=config_qnd,
                                   soc=soc, soccfg=soccfg)
        data_QNDmeas = Instance_QNDmeas.acquire()
        data_QNDmeas = Instance_QNDmeas.process_data(data_QNDmeas, toPrint=False, confidence_selection=0.99)
        Instance_QNDmeas.save_data(data_QNDmeas)
        Instance_QNDmeas.save_config()
        Instance_QNDmeas.display(data_QNDmeas, plotDisp=False)
        print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        # Checking if temperature is stable if not then run again
        if np.abs(float(lakeshore.get_temp(7)) * 1e3 - tempr_cfg["tempr_list"][i]) < tempr_cfg["max_deviation"]:
            is_fluctuating = 0
        else:
            print("WARNING : Temperature not stable. Trying again")
            lakeshore.set_temp(tempr_cfg["tempr_list"][i])
            time.sleep(tempr_cfg["wait_time"])

        ctr += 1
    ###endregion
#TODO this measurement is not time of flight at all, I guess the name migrated from a previous expt for historical reasons
# I don't want to rename it in the middle of measurements but we absolutely need to change it. Lev 12/24/2023
    ##region TITLE: Time of Flight Measurement
    UpdateConfig = {
        ### cavity spec parameters
        "read_length_tof": 2,  # [us]
        # ### qubit spec parameters
        # "qubit_pulse_style": "arb",
        # "qubit_gain": 0,
        # "sigma": 0.005,
        ### define experiment specific parameters
        "shots": 200000,
        "offset": 0,  # [us] placeholder for actual value
        "offset_start": 0,  # [us]
        "offset_end": 50,  # [us]
        "offset_num": 15,  # [Number of points]
        "max_pulse_length": 5,

        "use_switch": True,
        "relax_delay": 10,
    }
    config_tof = config | UpdateConfig

    # Estimating Time
    time_required = np.sum(
        (np.linspace(config_tof["offset"], config_tof["offset_end"], config_tof["offset_num"]) +
         2 * config_tof["max_pulse_length"]) * config_tof["shots"] + config_tof["relax_delay"]) * 1e-6 / 60


    # Measuring
    is_fluctuating = 1
    ctr = 1
    while is_fluctuating:
        if ctr > tempr_cfg["patience_ctr"]:
            lakeshore.set_setpoint(5)
            lakeshore.set_heater_range(0)
            sys.exit("Lakeshore has run out of patience. Human required!")

        print("TOF : Total time estimate is " + str(time_required) + " min")
        print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Instance_TimeOfFlightPS = TimeOfFlightPS(path="TimeOfFlightPS_temp_" + str(config["fridge_temp"]),
                                                 outerFolder=outerFolder, cfg=config_tof,
                                                 soc=soc, soccfg=soccfg)
        data_TimeOfFlightPS = Instance_TimeOfFlightPS.acquire()
        data_TimeOfFlightPS = Instance_TimeOfFlightPS.processData(data_TimeOfFlightPS, save_all=False)
        Instance_TimeOfFlightPS.save_data(data_TimeOfFlightPS)
        Instance_TimeOfFlightPS.save_config()
        Instance_TimeOfFlightPS.display(data=data_TimeOfFlightPS, plotDisp=False, save_all=False)
        print('stopping scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        # Checking if temperature is stable if not then run again
        if np.abs(float(lakeshore.get_temp(7)) * 1e3 - tempr_cfg["tempr_list"][i]) < tempr_cfg["max_deviation"]:
            is_fluctuating = 0
        else:
            print("WARNING : Temperature not stable. Trying again")
            lakeshore.set_temp(tempr_cfg["tempr_list"][i])
            time.sleep(tempr_cfg["wait_time"])

        ctr += 1

    ##endregion

    ##region TITLE: Rabi Chevron
    UpdateConfig = {
        "qubit_freq_start": config["qubit_freq"] - 100,
        "qubit_freq_stop": config["qubit_freq"] + 100,
        "SpecNumPoints": 41,  ### number of points
        ##### define spec slice experiment parameters
        "qubit_gain": 4000,
        "spec_reps": 800,
        "use_switch": True,
    }
    config_rc = config | UpdateConfig

    # Estimating Time
    time_required = config_rc["relax_delay"]*config_rc["spec_reps"]*config_rc["SpecNumPoints"]/1e6/60


    # Measuring
    is_fluctuating = 1
    ctr = 1
    while is_fluctuating:
        if ctr > tempr_cfg["patience_ctr"]:
            lakeshore.set_setpoint(5)
            lakeshore.set_heater_range(0)
            sys.exit("Lakeshore has run out of patience. Human required!")

        print('Rabi Chevron : Total time estimate: ' + str(time_required) + " minutes")
        print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Instance_SpecSlice = SpecSlice_bkg_sub(path="Rabi_Chevron_temp_" + str(config["fridge_temp"]),
                                                         outerFolder=outerFolder, cfg=config_rc, soc=soc, soccfg=soccfg,
                                                         progress=True)
        data_SpecSlice = Instance_SpecSlice.acquire()
        Instance_SpecSlice.save_data(data_SpecSlice)
        Instance_SpecSlice.save_config()
        Instance_SpecSlice.display(data_SpecSlice, plotDisp=False)
        print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        # Checking if temperature is stable if not then run again
        if np.abs(float(lakeshore.get_temp(7)) * 1e3 - tempr_cfg["tempr_list"][i]) < tempr_cfg["max_deviation"]:
            is_fluctuating = 0
            config["qubit_freq"] = data_SpecSlice['data']['f_reqd'].round(2)
        else:
            print("WARNING : Temperature not stable. Trying again")
            lakeshore.set_temp(tempr_cfg["tempr_list"][i])
            time.sleep(tempr_cfg["wait_time"])

        ctr += 1

    ##endregion

    ##region TITLE: Measure T1
    UpdateConfig = {
        # ## qubit parameters
        # "qubit_pulse_style": "arb",  # Pulse Type
        # "qubit_gain": 0,  # [in DAC units]
        # "sigma": 0.005,  # [in us]
        ## experiment parameters
        "shots": 40000,  # Number of shots
        "wait_start": 0,  # [in us]
        "wait_stop": config["relax_delay"],  # [in us]
        "wait_num": 25,  # number of points in logspace
        'wait_type': 'linear',
        "use_switch": True,
        "relax_delay": 10,
    }
    config_t1 = config | UpdateConfig

    # Estimating Time
    time_per_scan = config_t1["shots"] * (
            np.linspace(config_t1["wait_start"], config_t1["wait_stop"], config_t1["wait_num"])
            + config_t1["relax_delay"]) * 1e-6
    total_time = np.sum(time_per_scan) / 60


    # Measuring
    is_fluctuating = 1
    ctr = 1
    while is_fluctuating:
        if ctr > tempr_cfg["patience_ctr"]:
            lakeshore.set_setpoint(5)
            lakeshore.set_heater_range(0)
            sys.exit("Lakeshore has run out of patience. Human required!")

        print('T1 : Total time estimate: ' + str(total_time) + " minutes")
        print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Instance_T1_PS = T1_PS_sse(path="T1_PS_temp_" + str(config["fridge_temp"]), outerFolder=outerFolder,
                                   cfg=config_t1,
                                   soc=soc, soccfg=soccfg)
        data_T1_PS = Instance_T1_PS.acquire()
        data_T1_PS = Instance_T1_PS.process_data(data_T1_PS)
        Instance_T1_PS.save_data(data_T1_PS)
        Instance_T1_PS.save_config()
        Instance_T1_PS.display(data_T1_PS, plotDisp=False)
        print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        # updating the relax delay
        if data_T1_PS["data"]["T1"] < 10000:
            if data_T1_PS["data"]["T1_guess"]*5 > 1000:
                config["relax_delay"] = data_T1_PS["data"]["T1_guess"] * 5  ## TITLE: Very important line
            else:
                config["relax_delay"] = 1000
            T1_meas = data_T1_PS["data"]["T1"]
            T1_meas_err = data_T1_PS["data"]["T1_err"]
            rate_tempr = data_T1_PS["data"]["temp_rate"]
            rate_tempr_std =data_T1_PS["data"]["temp_std_rate"]
        else:
            print("Error: T1 is too big")
            sys.exit("What nonsense is this! Human required!")

        # Checking if temperature is stable if not then run again
        if np.abs(float(lakeshore.get_temp(7)) * 1e3 - tempr_cfg["tempr_list"][i]) < tempr_cfg["max_deviation"]:
            is_fluctuating = 0
        else:
            print("WARNING : Temperature not stable. Trying again")
            lakeshore.set_temp(tempr_cfg["tempr_list"][i])
            time.sleep(tempr_cfg["wait_time"])

        ctr += 1
    ##endregion

    ##region TITLE: Measure SingleShot for Temperature Calculation
    UpdateConfig = {
        ## qubit spec parameters
        # "qubit_pulse_style": "arb",  # no actual pulse applied. This is just for safety
        # "qubit_gain": 0,  # [in DAC Units]
        # "sigma": 0.005,  # [in us]
        ## define experiment parameters
        "shots": 1000000,
        "use_switch": True,
        "initialize_pulse": True
    }
    config_ss = config | UpdateConfig

    # Estimating Time
    time_required = config_ss["shots"] * config_ss["relax_delay"] * 1e-6 / 60


    # Measuring
    is_fluctuating = 1
    ctr = 1
    while is_fluctuating:
        if ctr > tempr_cfg["patience_ctr"]:
            lakeshore.set_setpoint(5)
            lakeshore.set_heater_range(0)
            sys.exit("Lakeshore has run out of patience. Human required!")

        print("SingleShot : Total time estimate is ", time_required, " mins")
        print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Instance_SingleShotProgram = SingleShotSSE(path="TempMeas_temp_" + str(config_ss["fridge_temp"]),
                                                   outerFolder=outerFolder, cfg=config_ss,
                                                   soc=soc, soccfg=soccfg)
        data_SingleShot = Instance_SingleShotProgram.acquire()
        data_SingleShot = Instance_SingleShotProgram.process_data(data_SingleShot, bin_size=51)
        Instance_SingleShotProgram.save_data(data_SingleShot)
        Instance_SingleShotProgram.save_config()
        Instance_SingleShotProgram.display(data_SingleShot, plotDisp=False, save_fig=True)
        print('end of scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        # Getting the temperatures
        state_prob = data_SingleShot["data"]["prob"]
        state_prob_std = data_SingleShot["data"]["prob_std"]
        state_tempr = data_SingleShot["data"]["tempr"]
        state_tempr_std = data_SingleShot["data"]["tempr_std"]

        # Checking if temperature is stable if not then run again
        if np.abs(float(lakeshore.get_temp(7)) * 1e3 - tempr_cfg["tempr_list"][i]) < tempr_cfg["max_deviation"]:
            is_fluctuating = 0
        else:
            print("WARNING : Temperature not stable. Trying again")
            lakeshore.set_temp(tempr_cfg["tempr_list"][i])
            time.sleep(tempr_cfg["wait_time"])
        ctr += 1
    ##endregion

    ### Saving the data to a csv
    # getting all the data
    data_csv.append(tempr_cfg["tempr_list"][i])  # [mK] Temperature
    data_csv.append(config["yokoVoltage_freqPoint"])  # [V] Yoko Voltage
    data_csv.append(config["qubit_freq"])  # [MHz] Qubit Frequency
    data_csv.append(T1_meas.round(4))  # [in us] T1
    data_csv.append(T1_meas_err.round(4))  # [in us] T1 std
    indx_min = np.argmin(np.array(state_prob))
    data_csv.append((state_prob[indx_min]*1e2).round(4))  # Thermal excitation
    data_csv.append((state_prob_std[indx_min]*1e2).round(4))  # Thermal excitation std
    data_csv.append((state_tempr*1e3).round(4))  # [in mK] Temperature of qubit
    data_csv.append((state_tempr_std*1e3).round(4))  # [in mK] Std of temperature of qubit
    data_csv.append(rate_tempr.round(4))
    data_csv.append(rate_tempr_std.round(4))
    today = datetime.datetime.today()
    formatted_date = today.strftime("%m/%d/%Y")
    data_csv.append(formatted_date)  # today's date in mm/dd/yyyy format

    # Saving to a csv file
    loc = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Summary\\"
    fname = "WTF_cooldown6_allData.csv"

    # Open the existing CSV file in append mode
    with open(loc+fname, mode='a', newline='') as file:
        # Create a CSV writer object
        writer = csv.writer(file)

        # Write the list to the CSV file
        writer.writerow(data_csv)

    # Close the open csv
    file.close()

    path_csv.append(tempr_cfg["tempr_list"][i])
    path_csv.append(config["yokoVoltage_freqPoint"])
    path_csv.append(Instance_QNDmeas.fname)
    path_csv.append(Instance_TimeOfFlightPS.fname)
    path_csv.append(Instance_T1_PS.fname)
    path_csv.append(Instance_SingleShotProgram.fname)

    # Saving to a csv file
    loc = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\TempChecks\\Summary\\"
    fname = "WTF_cooldown6_pathtodata.csv"

    # Open the existing CSV file in append mode
    with open(loc + fname, mode='a', newline='') as file:
        # Create a CSV writer object
        writer = csv.writer(file)

        # Write the list to the CSV file
        writer.writerow(path_csv)

    # Close the open csv
    file.close()

# Turn off the heater with lakeshore
lakeshore.set_setpoint(5)
lakeshore.set_heater_range(0)
time.sleep(60)
