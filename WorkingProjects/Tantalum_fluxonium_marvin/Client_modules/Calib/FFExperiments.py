#%%
import os
import time
from matplotlib import pyplot as plt
import Pyro4.util
import numpy as np

path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(path)

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecVsDelay import FFSpecVsDelay_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFRampTest import FFRampTest_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecSlice import FFSpecSlice_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecVsFlux import FFSpecVsFlux_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSingleShot import FFSingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFF_T1_PS_sse import FF_T1_PS_sse
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFHoldTransmission import FFTransmission
# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\" # end in \\

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
soc.reset_gens()
# print(soccfg)


# plt.ioff()

# Defining the switch configuration
SwitchConfig = {
    "trig_buffer_start": 0.05, #0.035, # in us
    "trig_buffer_end": 0.04, #0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

#%%
# TITLE: Fast Flux DC voltage Spec Slice

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 20,                # [us]
    "read_pulse_gain": 4500,         # [DAC units]
    "read_pulse_freq": 6671.71,#6670.85,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 450,        # [MHz]
    "qubit_freq_stop": 570,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 4,               # [us], used with "const"
    "flat_top_length": 10,        # [us], used with "flat_top"
    "qubit_gain": 1000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive
    "qubit_spec_delay": 105,          # [us] Delay before qubit pulse

    # Fast flux pulse parameters
    "ff_gain":-23000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 100,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "const",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 3,

    "yokoVoltage": -0.115,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 20,               # [us]
    "qubit_freq_expts": 101,         # number of points
    "reps": 1200000,
    "use_switch": False,
    'negative_pulse': True,
}

config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
Instance_FFSpecSlice = FFSpecSlice_Experiment(path="FFSpecSlice", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFSpecSlice.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

data_FFSpecSlice = FFSpecSlice_Experiment.acquire(Instance_FFSpecSlice, progress = True)
FFSpecSlice_Experiment.display(Instance_FFSpecSlice, data_FFSpecSlice, plot_disp=True)
FFSpecSlice_Experiment.save_data(Instance_FFSpecSlice, data_FFSpecSlice)
FFSpecSlice_Experiment.save_config(Instance_FFSpecSlice)
# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
#TITLE: Fast Flux DC voltage Spec vs Delay

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 20,                # [us]
    "read_pulse_gain": 5000,         # [DAC units]
    "read_pulse_freq": 6671.71,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 450,        # [MHz]
    "qubit_freq_stop": 1400,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.02,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.01,               # [us], used with "const"
    "flat_top_length": 0.050,        # [us], used with "flat_top"
    "qubit_gain": 32000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # Fast flux pulse parameters
    "ff_gain": -10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 1,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0.5,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.02,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

    "yokoVoltage": -0.115,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 10,               # [us]
    "qubit_freq_expts": 101,         # number of points
    "reps": 9000,
    "use_switch": False,
    "pre_meas_delay": 2,

    # post_ff_delay sweep parameters: delay after fast flux pulse (before qubit pulse)
    "qubit_spec_delay_start": 0.75,  # [us] Initial value
    "qubit_spec_delay_stop": 0.825,      # [us] Final value
    "qubit_spec_delay_steps": 31,    # number of post_ff_delay points to take
}


config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
Instance_FFSpecVsDelay = FFSpecVsDelay_Experiment(path="FFSpecVsDelay", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFSpecVsDelay.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFSpecVsDelay = FFSpecVsDelay_Experiment.acquire(Instance_FFSpecVsDelay, progress = True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

FFSpecVsDelay_Experiment.display(Instance_FFSpecVsDelay, data_FFSpecVsDelay, plot_disp=True)
FFSpecVsDelay_Experiment.save_data(Instance_FFSpecVsDelay, data_FFSpecVsDelay)
FFSpecVsDelay_Experiment.save_config(Instance_FFSpecVsDelay)
# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
# TITLE: Spec vs Flux where the flux is changed using fast flux
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # [us]
    "read_pulse_gain": 5000,  # [DAC units]
    "read_pulse_freq": 6671.71,  # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 450,  # [MHz]
    "qubit_freq_stop": 2500,  # [MHz]
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.02,  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.1,  # [us], used with "const"
    "flat_top_length": 0.050,  # [us], used with "flat_top"
    "qubit_gain": 10000,  # [DAC units]
    "qubit_ch": 1,  # RFSOC output channel of qubit drive
    "qubit_nqz": 1,  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,  # Currently unused, applies to "const" drive
    "qubit_spec_delay": 1,

    # Fast flux pulse parameters
    "ff_gain": 500,  # [DAC units] Gain for fast flux pulse
    "ff_length": 2,  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,
    "pre_meas_delay": 1,
    # [us] Delay before the fast flux pulse, Ideally has to be zero, just setting it to a minimal valye for now
    "ff_pulse_style": "ramp",
    "ff_ramp_length": 0.05,
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

    "yokoVoltage": -0.115,  # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 30,  # [us]
    "qubit_freq_expts": 101,  # number of points
    "reps": 5000,
    "use_switch": False,

    # Sweep through the dac values for ff
    "ff_gain_start": 0,
    "ff_gain_stop": -30000,
    "ff_gain_num_points": 11,
    "negative_pulse": True,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

inst_spec_flux = FFSpecVsFlux_Experiment(path="FFSpecVsFlux", cfg=config,soc=soc,soccfg=soccfg,
                                         outerFolder = outerFolder, short_directory_names = True)

# Estimate time
time_to_run = inst_spec_flux.estimate_runtime()
print("Time for ff spec experiment is about ", time_to_run, " s")
soc.reset_gens()
try:
    data_spec_flux= inst_spec_flux.acquire(progress = True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
inst_spec_flux.display(data_spec_flux, plot_disp=True)
inst_spec_flux.save_data(data_spec_flux)
inst_spec_flux.save_config()
plt.show()


#%%
# TITLE: Fast flux ramp test experiment

config = {
        # Readout section
        "read_pulse_style": "const",  # --Fixed
        "read_length": 20,  # [us]
        "read_pulse_gain": 30000, #5600,  # [DAC units]
        "read_pulse_freq": 6671.71,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "linear",  # one of ["linear"]
        "ff_ramp_start": 0, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": -25000, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 0, # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

        # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
        "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 512,  # [MHz] Frequency of qubit pulse
        "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.50,  # [us], used with "arb" and "flat_top"
        "qubit_length": 0.5,  # [us], used with "const"
        "flat_top_length": 1,  # [us], used with "flat_top"
        "qubit_gain": 1000,  # [DAC units]
        "qubit_ch": 1,  # RFSOC output channel of qubit drive
        "qubit_nqz": 1,  # Nyquist zone to use for qubit drive

        # Ramp sweep parameters
        "ff_ramp_length_start": 0.02,  # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 10,  # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_length_expts": 11, # [int] Number of points in the ff ramp length sweep
        "yokoVoltage": -0.115,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 0.1, # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
        "relax_delay_2": 10 - BaseConfig["adc_trig_offset"], # [us] Relax delay after second readout

        # Gain sweep parameters
        "ff_gain_expts": 15,    # [int] How many different ff ramp gains to use
        "ff_ramp_length": 0.01,    # [us] Half-length of ramp to use when sweeping gain

        # Number of cycle repetitions sweep parameters
        "cycle_number_expts": 2,     # [int] How many different values for number of cycles around to use in this experiment
        "max_cycle_number": 50,        # [int] What is the largest number of cycles to use in sweep? Smallest value always 1
        "cycle_delay": 0.05,          # [us] How long to wait between cycles in one experiment?

        # General parameters
        "sweep_type": 'ramp_length',  # [str] What to sweep? 'ramp_length', 'ff_gain', 'cycle_number'
        "reps": 100000,
        "sets": 5,
        "angle": None, # [radians] Angle of rotation for readout
        "threshold": None, # [DAC units] Threshold between g and e
        "confidence": 0.99,
        "plot_all_points": False,
        "plot_all_lengths": True,
        "verbose": False,
    }

# We have 65536 samples (9.524 us) wave memory on the FF channel (and all other channels)

yoko1.SetVoltage(config["yokoVoltage"])
config = BaseConfig | config
Instance_FFRampTest = FFRampTest_Experiment(path="FFRampTest", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)
# Estimate Time
time = Instance_FFRampTest.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFRampTest = FFRampTest_Experiment.acquire(Instance_FFRampTest, progress = True)
    FFRampTest_Experiment.display(Instance_FFRampTest, data_FFRampTest, plot_disp=True,
                                  plot_all_lengths=config['plot_all_lengths'])
    FFRampTest_Experiment.save_data(Instance_FFRampTest, data_FFRampTest)
    FFRampTest_Experiment.save_config(Instance_FFRampTest)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
# TITLE : Measure Steady State Population
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # [us]
    "read_pulse_gain": 5000,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.71,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -20000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 250,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 512,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 690,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 1000,  # [DAC units]

    # Ramp sweep parameters
    "yokoVoltage": -0.115,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 0.05,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 10,  # [us] Relax delay after second readout

    # General parameters
    "reps": 5000000,
    "cen_num":2,
    "initialize_pulse": True,
    "negative_pulse": True,
    "neg_init_fact" : 1,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
inst_ffsingleshot = FFSingleShotSSE(path="FFSingleShot", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, progress = True)
try:
    inst_ffsingleshot.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_ffsingle = inst_ffsingleshot.process()
inst_ffsingleshot.save_data(data_ffsingle)
inst_ffsingleshot.save_config()
print(f"Temperature is {data_ffsingle['data']['mean_temp'][1,0]} mK")
#%%
# TITLE : Measure T1 at a FF place
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # [us]
    "read_pulse_gain": 5000,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.71,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 20000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 2000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 514,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq" : 2000,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 6000,  # [DAC units]

    # Wait sweep parameters
    "yokoVoltage": -0.115,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 0.05,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 10,  # [us] Relax delay after second readout
    "wait_start": 10,
    "wait_stop": 400,
    "wait_num": 5,
    "wait_type": 'linear',

    # General parameters
    "reps": 20000,
    "cen_num":2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage_freqPoint": -0.115,
    "negative_pulse": True,
    "neg_init_fact" : 0,
    "multiplier": 1.0,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
inst_ff_t1 = FF_T1_PS_sse(path="FF_T1_PS", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)
try:
    inst_ff_t1.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_ff_t1 = inst_ff_t1.process_data()
inst_ff_t1.save_data(data_ff_t1)
inst_ff_t1.display(data_ff_t1, plotDisp=True)
inst_ff_t1.display_all_data(data_ff_t1)
inst_ff_t1.save_config()

#%%
# TITLE : Sweeping flux

from tqdm import tqdm

outerFolder  = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\FF_sweep_22Sept_1527\\"
FF_sweep = np.linspace(0,-20000, 200, dtype = int)

def freq_predictor(ff_dac_val):
    return -0.06*ff_dac_val + 510

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # [us]
    "read_pulse_gain": 4600,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.71,  # [MHz]

    # Qubit Tone
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 512,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq" : 690,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 1500,  # [DAC units]
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # General parameters
    "reps": 25000,
    "cen_num": 2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage": -0.115,
    "yokoVoltage_freqPoint": -0.115,
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "use_switch": False,
    "ro_mode_periodic": False,
    "negative_pulse": True,
}

config = BaseConfig | UpdateConfig

UpdateConfig_spec = {
    # Qubit spec parameters
    "qubit_freq_start": 500,        # [MHz]
    "qubit_freq_stop": 600,         # [MHz]
    "qubit_spec_delay": 1,          # [us] Delay before qubit pulse
    "qubit_freq_expts": 101,  # number of points

    # Fast flux pulse parameters
    "ff_gain": -3000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 2,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0.05,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "const",
    "ff_ramp_length" : 0.2,
    "pre_meas_delay": 0.01,
    "reps": 8000,
}

config_spec = config | UpdateConfig_spec

UpdateConfig_ss = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -3000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 2000,  # [us] Delay between fast flux ramps
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # General parameters
    "reps": 30000,
    "initialize_pulse": True,
    "relax_delay_1": 0.05,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 10 ,  # [us] Relax delay after second readout
}

config_ss = config | UpdateConfig_ss

UpdateConfig_t1 = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -3000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 2000,  # [us] Delay between fast flux ramps
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Wait sweep parameters
    "relax_delay_1": 0.05,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 10 - BaseConfig["adc_trig_offset"],  # [us] Relax delay after second readout
    "wait_start": 0,
    "wait_stop": 3000,
    "wait_num": 11,
    "wait_type": 'linear',

    # General parameters
    "reps": 10000,
    "cen_num": 2,
    "initialize_pulse": True,
}

config_t1 = config | UpdateConfig_t1

qubit_freq_list = []
pop_meas_list = []
pop_meas_err_list = []
temp_ss_meas_list = []
temp_ss_err_meas_list = []
t1_meas_list = []
t1_err_meas_list = []
temp_rate_meas_list = []
temp_rate_err_meas_list = []

print("========== STARTING EXPERIMENTS =============")
for i in tqdm(range(FF_sweep.size)):

    # Update the DAC value in all three experiments
    config_spec['ff_gain'] = FF_sweep[i]
    config_t1['ff_ramp_stop'] = FF_sweep[i]
    config_ss['ff_ramp_stop'] = FF_sweep[i]

    # Create a new directory
    outerFolderDac = outerFolder + "dac_" + str(FF_sweep[i]) + "\\"

    # Using the freq predictor update the span of the frequency for the spec slice
    qubit_ge_freq = freq_predictor(FF_sweep[i])
    print(f"Qubit's predicted frequency is {qubit_ge_freq}")
    config_spec['qubit_freq_start'] = qubit_ge_freq - 100
    config_spec['qubit_freq_stop'] = qubit_ge_freq + 100

    # Update qubit_ge_freq in other configs - this is temporary till I know that spec slice will always work
    config_t1['qubit_ge_freq'] = qubit_ge_freq
    config_ss['qubit_ge_freq'] = qubit_ge_freq

    # Now Run the spec slice
    soc.reset_gens()
    Instance_FFSpecSlice = FFSpecSlice_Experiment(path="FFSpecSlice", cfg=config_spec, soc=soc, soccfg=soccfg,
                                                  outerFolder=outerFolderDac, short_directory_names=True)

    data_FFSpecSlice = Instance_FFSpecSlice.acquire(progress=True)
    Instance_FFSpecSlice.display(data_FFSpecSlice, plot_disp=False)
    Instance_FFSpecSlice.save_data(data_FFSpecSlice)
    Instance_FFSpecSlice.save_config()

    # Get the qubit frequency qnd update the configs
    qubit_ge_freq = Instance_FFSpecSlice.qubit_peak_freq
    qubit_freq_list.append(qubit_ge_freq)
    print(f"Qubit's measured frequency is {qubit_ge_freq}")
    # config_t1['qubit_ge_freq'] = qubit_ge_freq
    # config_ss['qubit_ge_freq'] = qubit_ge_freq

    # Run T1
    soc.reset_gens()
    inst_ff_t1 = FF_T1_PS_sse(path="FF_T1_PS", cfg=config_t1, soc=soc, soccfg=soccfg,
                              outerFolder=outerFolderDac)
    try:
        inst_ff_t1.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    data_ff_t1 = inst_ff_t1.process_data()
    inst_ff_t1.display(data_ff_t1, plotDisp=False)
    inst_ff_t1.save_data(data_ff_t1)
    inst_ff_t1.save_config()

    # Get the T1 and update the ff_hold in config_ss
    t1 = data_ff_t1['data']['T1']
    t1_err = data_ff_t1['data']['T1_err']
    config_ss['ff_hold'] = 5*t1

    # Update the lists
    t1_meas_list.append(t1)
    t1_err_meas_list.append(t1_err)
    temp_rate_meas_list.append(data_ff_t1['data']['temp_rate'])
    temp_rate_err_meas_list.append(data_ff_t1['data']['temp_std_rate'])

    # Run Single Shot
    soc.reset_gens()
    inst_ffsingleshot = FFSingleShotSSE(path="FFSingleShot", cfg=config_ss, soc=soc, soccfg=soccfg,
                                        outerFolder=outerFolderDac)
    try:
        inst_ffsingleshot.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    data_ffsingle = inst_ffsingleshot.process()
    inst_ffsingleshot.save_data(data_ffsingle)
    inst_ffsingleshot.save_config()

    # Updating the lists
    pop_meas_list.append(data_ffsingle['data']['mean_pop'])
    pop_meas_err_list.append(data_ffsingle['data']['std_pop'])
    temp_ss_meas_list.append(data_ffsingle['data']['mean_temp'][1,0])
    temp_ss_err_meas_list.append(data_ffsingle['data']['std_temp'][1,0])
#%%
# Saving all the lists
collated_data = {
    "qubit_freq_list" : qubit_freq_list,
    "pop_meas_list" : pop_meas_list,
    "pop_meas_err_list": pop_meas_err_list,
    "temp_ss_meas_list" : temp_ss_meas_list,
    "temp_ss_err_meas_list" : temp_ss_err_meas_list,
    "t1_meas_list" : t1_meas_list,
    "t1_err_meas_list" : t1_err_meas_list,
    "temp_rate_meas_list" : temp_rate_meas_list,
    "temp_rate_err_meas_list" : temp_rate_err_meas_list,
    "FF_sweep": FF_sweep,
}

# Save the data using h5
import h5py
def save_collated_h5(collated_data, path="collated_data.h5"):
    with h5py.File(path, "w") as f:
        # Stack the special ones
        f.create_dataset("pop_meas_list", data=np.stack(collated_data["pop_meas_list"]))
        f.create_dataset("pop_meas_err_list", data=np.stack(collated_data["pop_meas_err_list"]))

        # Everything else straight to dataset
        skip = {"pop_meas_list", "pop_meas_err_list"}
        for key, value in collated_data.items():
            if key in skip:
                continue
            f.create_dataset(key, data=np.array(value))

file_loc = outerFolder + "collated_data.h5"
save_collated_h5(collated_data, path = file_loc)
#%%
# Plot all the data
import numpy as np
import matplotlib.pyplot as plt
import os

# Example assumes collated_data and outerFolder are already defined
# collated_data = {...}
# outerFolder = "/path/to/folder"

FF_sweep = np.array(collated_data["FF_sweep"])
temp_ss = np.abs(np.array(collated_data["temp_ss_meas_list"]) * 1000)
temp_ss_err = np.array(collated_data["temp_ss_err_meas_list"]) * 1000
temp_rate = np.abs(np.array(collated_data["temp_rate_meas_list"]) * 1000)
temp_rate_err = np.array(collated_data["temp_rate_err_meas_list"]) * 1000
t1 = np.array(collated_data["t1_meas_list"])
t1_err = np.array(collated_data["t1_err_meas_list"])
pop_meas = np.stack(collated_data["pop_meas_list"])          # shape (N, 2)
pop_meas_err = np.stack(collated_data["pop_meas_err_list"])  # shape (N, 2)
qubit_freq = np.array(collated_data["qubit_freq_list"])

# Excited state = the smaller of g/e
excited_pop = np.min(pop_meas, axis=1)
excited_pop_err = np.min(pop_meas_err, axis=1)


def make_pretty(ax, xlabel, ylabel, title=None):
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    if title:
        ax.set_title(title, fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=10)


def save_fig(fig, name):
    os.makedirs(outerFolder, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(outerFolder, f"{name}.png"), dpi=300)
    fig.savefig(os.path.join(outerFolder, f"{name}.pdf"))


# -------------------------
# 1. temp_ss vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, temp_ss, yerr=temp_ss_err,
            fmt="o-", capsize=3, label="Single shot")
make_pretty(ax, "FF DAC Value", "Temperature (measured through single shot) [mK]")
ax.legend()
save_fig(fig, "temperature_single_shot")

# -------------------------
# 2. temp_rate vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, temp_rate, yerr=temp_rate_err,
            fmt="s-", capsize=3, color="C1", label="Rate-based")
make_pretty(ax, "FF DAC Value", "Temperature (measured through Rates) [mK]")
ax.legend()
save_fig(fig, "temperature_rates")

# -------------------------
# 3. Both temperatures vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, temp_ss, yerr=temp_ss_err,
            fmt="o-", capsize=3, label="Single shot")
ax.errorbar(FF_sweep, temp_rate, yerr=temp_rate_err,
            fmt="s-", capsize=3, label="Rate-based")
make_pretty(ax, "FF DAC Value", "Temperature [mK]")
ax.legend()
save_fig(fig, "temperature_comparison")

# -------------------------
# 4. T1 vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, t1, yerr=t1_err,
            fmt="d-", capsize=3, color="C2", label="T1")
make_pretty(ax, "FF DAC Value", "T1 [µs]")
ax.legend()
save_fig(fig, "t1_vs_ff")

# -------------------------
# 5. Excited state population vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, excited_pop, yerr=excited_pop_err,
            fmt="^-", capsize=3, color="C3", label="Excited state population")
make_pretty(ax, "FF DAC Value", "Excited State Population")
ax.legend()
save_fig(fig, "excited_population_vs_ff")

# -------------------------
# 6. Qubit frequency vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, qubit_freq, "o-", color="C4", label="Qubit frequency")
make_pretty(ax, "FF DAC Value", "Qubit Frequency [GHz]")
ax.legend()
save_fig(fig, "qubit_frequency_vs_ff")

plt.show()

#%%
from tqdm import tqdm
# TITLE: Understanding phase accumulation in fast flux
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # [us]
    "read_pulse_gain": 5000,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.71,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 100,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": False,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 512,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 690,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 0,  # [DAC units]

    # Ramp sweep parameters
    "yokoVoltage": -0.115,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 1,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 4000,  # [us] Relax delay after second readout

    # General parameters
    "reps": 8000,
    "cen_num":2,
    "initialize_pulse": True,
    'negative_pulse': True,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

ff_hold_vec = np.linspace(10,2000,11)
centers = []

for i in tqdm(range(ff_hold_vec.size)):
    config['ff_hold'] = ff_hold_vec[i]
    soc.reset_gens()
    inst_ffsingleshot = FFSingleShotSSE(path="Phase_Study_neg_pulse4", cfg=config,soc=soc,soccfg=soccfg, progress=False,
                                                  outerFolder = outerFolder, fast_analysis=False, disp_image = False)
    try:
        inst_ffsingleshot.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    data_ffsingle = inst_ffsingleshot.process()
    inst_ffsingleshot.save_data(data_ffsingle)
    inst_ffsingleshot.save_config()
    centers.append(inst_ffsingleshot.analysis.centers)


#%%
def track_and_plot_centers(centers_list, ff_hold_vec, outerFolder,
                           title_prefix="FF hold study", plot_radius=False):
    """
    centers_list: list of arrays, each shape (2, 2): [[x1, y1], [x2, y2]]
    ff_hold_vec: 1D array-like of same length as centers_list
    outerFolder: directory where figures are saved
    title_prefix: prefix for figure titles and filenames
    plot_radius: if True, also saves radius vs ff_hold

    Produces and saves:
      - <prefix>_iq_trajectory.{png,pdf}
      - <prefix>_angle_vs_hold.{png,pdf}
      - (optional) <prefix>_radius_vs_hold.{png,pdf}
    """
    os.makedirs(outerFolder, exist_ok=True)

    # ---------- Prepare data ----------
    centers_arr = np.asarray([np.asarray(c).reshape(2, 2) for c in centers_list])  # (N, 2, 2)
    ff_hold_vec = np.asarray(ff_hold_vec).reshape(-1)
    assert centers_arr.shape[0] == ff_hold_vec.size, "Length mismatch between centers_list and ff_hold_vec."

    # Use a fixed origin to measure angles (midpoint averaged over all times)
    all_pts = centers_arr.reshape(-1, 2)
    origin = all_pts.mean(axis=0)  # (x0, y0)

    # ---------- Branch tracking by continuity ----------
    N = centers_arr.shape[0]
    branch1 = np.zeros((N, 2))
    branch2 = np.zeros((N, 2))

    # Initialize from the first frame (keep given order)
    branch1[0] = centers_arr[0, 0]
    branch2[0] = centers_arr[0, 1]

    for t in range(1, N):
        prev1 = branch1[t-1]
        prev2 = branch2[t-1]
        c0, c1 = centers_arr[t, 0], centers_arr[t, 1]

        # Cost if we keep the current order vs if we swap
        cost_keep = np.linalg.norm(c0 - prev1) + np.linalg.norm(c1 - prev2)
        cost_swap = np.linalg.norm(c1 - prev1) + np.linalg.norm(c0 - prev2)

        if cost_swap < cost_keep:
            branch1[t] = c1
            branch2[t] = c0
        else:
            branch1[t] = c0
            branch2[t] = c1

    # ---------- Compute angles (unwrap) and radius ----------
    def angles_and_radius(points, origin):
        vx = points[:, 0] - origin[0]
        vy = points[:, 1] - origin[1]
        ang = np.arctan2(vy, vx)  # radians
        ang_unwrapped = np.unwrap(ang)              # keep rotation continuous
        ang_deg = np.degrees(ang_unwrapped)         # convert to degrees
        r = np.hypot(vx, vy)
        return ang_deg, r

    ang1_deg, r1 = angles_and_radius(branch1, origin)
    ang2_deg, r2 = angles_and_radius(branch2, origin)

    # ---------- Pretty helpers ----------
    def make_pretty(ax, xlabel, ylabel, title=None):
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        if title:
            ax.set_title(title, fontsize=14)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="both", labelsize=10)

    def save_fig(fig, stem):
        fig.tight_layout()
        fig.savefig(os.path.join(outerFolder, f"{stem}.png"), dpi=300)
        fig.savefig(os.path.join(outerFolder, f"{stem}.pdf"))

    # ---------- Plot 1: IQ trajectory ----------
    fig, ax = plt.subplots(figsize=(6.2, 4.8))
    ax.plot(branch1[:, 0], branch1[:, 1], "o-", label="Branch 1")
    ax.plot(branch2[:, 0], branch2[:, 1], "s-", label="Branch 2")

    # Mark start/end
    ax.plot(branch1[0, 0], branch1[0, 1], "o", ms=10, fillstyle="none", label="Start B1")
    ax.plot(branch2[0, 0], branch2[0, 1], "s", ms=10, fillstyle="none", label="Start B2")
    ax.plot(branch1[-1, 0], branch1[-1, 1], "o", ms=10, label="End B1")
    ax.plot(branch2[-1, 0], branch2[-1, 1], "s", ms=10, label="End B2")

    # Draw origin
    ax.axhline(origin[1], lw=0.8, alpha=0.3)
    ax.axvline(origin[0], lw=0.8, alpha=0.3)

    make_pretty(ax, "I", "Q", title=f"{title_prefix}: IQ Trajectory")
    ax.legend(ncol=2)
    save_fig(fig, f"{title_prefix.replace(' ', '_').lower()}_iq_trajectory")

    # ---------- Plot 2: Angle vs ff_hold ----------
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    ax.plot(ff_hold_vec, ang1_deg, "o-", label="Branch 1 angle")
    ax.plot(ff_hold_vec, ang2_deg, "s-", label="Branch 2 angle")

    make_pretty(ax, "FF hold [µs]", "Angle [deg]", title=f"{title_prefix}: Angle vs Hold")
    ax.legend()
    save_fig(fig, f"{title_prefix.replace(' ', '_').lower()}_angle_vs_hold")

    # ---------- Plot 3 (optional): Radius vs ff_hold ----------
    if plot_radius:
        fig, ax = plt.subplots(figsize=(6.2, 4.2))
        ax.plot(ff_hold_vec, r1, "o-", label="Branch 1 radius")
        ax.plot(ff_hold_vec, r2, "s-", label="Branch 2 radius")
        make_pretty(ax, "FF hold [µs]", "Radius [arb.]", title=f"{title_prefix}: Radius vs Hold")
        ax.legend()
        save_fig(fig, f"{title_prefix.replace(' ', '_').lower()}_radius_vs_hold")

    return {
        "branch1": branch1, "branch2": branch2,
        "angle_deg": (ang1_deg, ang2_deg),
        "radius": (r1, r2),
        "origin": origin
    }

# Example call (with your existing variables):
result = track_and_plot_centers(centers, ff_hold_vec, outerFolder + "//Phase_Study//",
                                title_prefix="Phase accumulation 5", plot_radius=False)
#%%
#TITLE : Post FF Transmission
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # [us]
    "read_pulse_gain": 4600,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.71,  # [MHz]
    "TransSpan": 0.25,
    "TransNumPoints": 51,

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 20000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 1000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain
    "pre_meas_delay": 1,

    # Ramp sweep parameters
    "yokoVoltage": -0.115,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 0.05,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 10,  # [us] Relax delay after second readout

    # General parameters
    "reps": 2000,
    "cen_num": 2,
    "initialize_pulse": True,
    "negative_pulse": True,
    "neg_offset": 0,
    "multiplier": 1,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
#%%
inst_ff_trans = FFTransmission(path="FF_Transmission", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)
try:
    data_ff_trans = inst_ff_trans.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
inst_ff_trans.display(data = data_ff_trans,plotDisp = True)
inst_ff_trans.save_data(data_ff_trans)
inst_ff_trans.save_config()
print(inst_ff_trans.peakFreq)

#%%
config["ff_ramp_stop"] = 0
config['ff_hold'] = 0
config['negative_pulse'] = False

inst_ff_trans = FFTransmission(path="FF_Transmission", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)
try:
    data_ff_trans_base = inst_ff_trans.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
inst_ff_trans.display(data = data_ff_trans_base,plotDisp = True)
inst_ff_trans.save_data(data_ff_trans_base)
inst_ff_trans.save_config()
print(inst_ff_trans.peakFreq)
#%%
# Vary the offset for 30000 ramp_stop to see when it matches to the base
vary_vec = np.linspace(-config["ff_hold"]/2, +config["ff_hold"]/2, 11)
key = "neg_offset"
avgi_data_arr = np.zeros((config["TransNumPoints"], vary_vec.size))
avgq_data_arr = np.zeros((config["TransNumPoints"], vary_vec.size))
amp_data_arr =  np.zeros((config["TransNumPoints"], vary_vec.size))

for i in range(vary_vec.size):
    config = BaseConfig | UpdateConfig
    config[key] = vary_vec[i]
    print(f"Running for {key} = {vary_vec[i]}")
    print(f"Config {key} is {config[key]}")
    inst_ff_trans = FFTransmission(path="FF_Transmission_neg_offset", cfg=config, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder)
    try:
        data_ff_trans = inst_ff_trans.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    inst_ff_trans.display(data=data_ff_trans, plotDisp=False)
    inst_ff_trans.save_data(data_ff_trans)
    inst_ff_trans.save_config()
    print(inst_ff_trans.peakFreq)
    avgi_data_arr[:,i] = data_ff_trans["data"]["avgi"]
    avgq_data_arr[:,i] = data_ff_trans["data"]["avgq"]
    amp_data_arr[:,i] = data_ff_trans["data"]["amp0"]

#%%
base_amp = data_ff_trans_base["data"]["amp0"]
amp_data_arr_base_sub = amp_data_arr - base_amp[:, np.newaxis]
fpts = data_ff_trans['data']['fpts']

# Ensure X, Y have matching dimensions
X, Y = np.meshgrid(fpts, vary_vec)

# Check dimensions to make sure the shape is correct
print(f"X shape: {X.shape}")
print(f"Y shape: {Y.shape}")
print(f"amp_data_arr shape: {amp_data_arr.shape}")
# print(f"amp_data_arr_base_sub shape: {amp_data_arr_base_sub.shape}")

fig, axs = plt.subplots(2, 1, figsize=(8, 8))

# Plot the first pcolormesh
c1 = axs[0].pcolormesh(X, Y, np.transpose(amp_data_arr), shading='nearest', cmap='viridis')
fig.colorbar(c1, ax=axs[0], label='DAC Units')
axs[0].set_title("Amplitude vs negative offset")
axs[0].set_ylabel(key)
axs[0].set_xlabel("Frequency")

# Plot the second pcolormesh with base subtracted
c2 = axs[1].pcolormesh(X, Y, np.transpose(amp_data_arr_base_sub), shading='auto', cmap='viridis')
fig.colorbar(c2, ax=axs[1], label='Z2 value')
axs[1].set_title("Amplitude vs negative offset with base subtracted")
axs[1].set_ylabel(key)
axs[1].set_xlabel("Frequency")

plt.tight_layout()
plt.show()