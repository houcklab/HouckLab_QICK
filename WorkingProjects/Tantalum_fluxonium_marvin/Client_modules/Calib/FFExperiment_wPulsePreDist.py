#%%
import os
import time
from matplotlib import pyplot as plt
import Pyro4.util
import numpy as np

path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(path)

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecVsDelay_wPulsePreDist import FFSpecVsDelay_wPPD_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecSlice_wPulsePreDist import FFSpecSlice_Experiment_wPPD
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecSlice_wPulsePreDist_studyZeroing import FFSpecSlice_Experiment_wPPD_studyzeroing
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecVsFlux_wPulsePreDist import FFSpecVsFlux_wPulsePreDist
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFRampTest import FFRampTest_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFF_T1_wPulsePreDist import FF_T1_wPulsePreDist
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSingleShot_wPulsePreDist import FFSingleShot_wPPD
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFTransmission_wPulsePreDist import FFTransmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFPopulateProbe_wPulsePreDist import FFPopulateProbe

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
# TITLE: Fast Flux DC voltage Spec Slice with Pulse Predistortion

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 35,                # [us]
    "read_pulse_gain": 10000,         # [DAC units]
    "read_pulse_freq": 6671.25,#6670.85,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 850,        # [MHz]
    "qubit_freq_stop": 1100,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 1,               # [us], used with "const"
    "flat_top_length": 10,        # [us], used with "flat_top"
    "qubit_gain": 15000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    'qubit_spec_buffer':10,

    # Fast flux pulse parameters
    "ff_gain": 1000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.05,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "yokoVoltage": -0.1202,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 2000,               # [us]
    "qubit_freq_expts": 101,         # number of points
    "reps": 1000,
    "pulse_pre_dist": True,
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
    "use_switch": False,
    'negative_pulse': True,
    'dt_pulseplay': 2,

}

config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
inst_spec_wppd = FFSpecSlice_Experiment_wPPD(path="FFSpecSlice_wPPD", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = inst_spec_wppd.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

data_FFSpecSlice = inst_spec_wppd.acquire(progress = True, plot_debug=True)
inst_spec_wppd.display(data_FFSpecSlice, plot_disp=True)
inst_spec_wppd.save_data(data_FFSpecSlice)
inst_spec_wppd.save_config()
# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
#TITLE: Fast Flux DC voltage Spec vs Delay with Pulse Predistortion

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 30,                # [us]
    "read_pulse_gain": 9000,         # [DAC units]
    "read_pulse_freq": 6671.25,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 400,        # [MHz]
    "qubit_freq_stop": 1700,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.02,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,               # [us], used with "const"
    "flat_top_length": 0.020,        # [us], used with "flat_top"
    "qubit_gain": 30000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # Fast flux pulse parameters
    "ff_gain": -2500,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 50,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 10,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.05,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

    "yokoVoltage": -0.1202,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 50,               # [us]
    "qubit_freq_expts": 101,         # number of points
    "reps": 2000,
    "use_switch": False,
    "pre_meas_delay": 5,

    # post_ff_delay sweep parameters: delay after fast flux pulse (before qubit pulse)
    "qubit_spec_delay_start": 1,  # [us] Initial value
    "qubit_spec_delay_stop": 400,      # [us] Final value
    "qubit_spec_delay_steps": 21,# number of post_ff_delay points to take
    "spacing": 'linear',
    "negative_pulse": False,
    "pulse_pre_dist": True,
    'dt_pulseplay': 1, # This should be proportional to the qubit spec delay definitions
    'dt_set_auto': False,
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
    "qubit_spec_buffer" : 10, # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
Instance_FFSpecVsDelay_wPPD = FFSpecVsDelay_wPPD_Experiment(path="FFSpecVsDelay_wPPD", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
est_time = Instance_FFSpecVsDelay_wPPD.estimate_runtime()
print("Time for ff spec experiment is about ", est_time, " s")

#%%
start_delay = 1
stop_delay = config["qubit_spec_delay_stop"] - config["qubit_spec_delay_start"] + 1
custom_delay_array = np.logspace(np.log10(start_delay), np.log10(stop_delay), config["qubit_spec_delay_steps"]) + config["qubit_spec_delay_start"] - 1

# print("Using custom delay array: ", custom_delay_array)

try:
    data_FFSpecVsDelay = Instance_FFSpecVsDelay_wPPD.acquire( progress = True, custom_delay_array = None, plot_debug = True)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

Instance_FFSpecVsDelay_wPPD.display(data_FFSpecVsDelay, plot_disp=True)
Instance_FFSpecVsDelay_wPPD.save_data(data_FFSpecVsDelay)
Instance_FFSpecVsDelay_wPPD.save_config()
# print(Instance_specSlice.qubitFreq)
plt.show()
#%%
# TITLE : Spec vs FF
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 25,                # [us]
    "read_pulse_gain": 9500,         # [DAC units]
    "read_pulse_freq": 6671.25,     # [MHz]
    "ro_mode_periodic" : False,

    # Qubit spec parameters
    "qubit_freq_start": 950,        # [MHz]
    "qubit_freq_stop": 1100,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,               # [us], used with "const"
    "flat_top_length": 10,        # [us], used with "flat_top"
    "qubit_gain": 25000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    "qubit_spec_buffer": 5,

    # Fast flux pulse parameters
    "ff_gain": 10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 10000,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.05,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "yokoVoltage": -0.1202,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 20,               # [us]
    "qubit_freq_expts": 31,         # number of points
    "reps": 500,
    "pulse_pre_dist": True,
    "use_switch": False,
    'negative_pulse': False,
    'dt_pulseplay': 5,
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,

    # Sweep through the dac values for ff
    "ff_gain_start": 0,
    "ff_gain_stop": -25000,
    "ff_gain_num_points": 3,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])

inst_spec_flux = FFSpecVsFlux_wPulsePreDist(path="FFSpecVsFlux_wPrePulseDist", cfg=config,soc=soc,soccfg=soccfg,
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
# TITLE : FF Ramp Test

config = {
        # Readout section
        "read_pulse_style": "const",  # --Fixed
        "read_length": 25,  # [us]
        "read_pulse_gain": 8800, #5600,  # [DAC units]
        "read_pulse_freq": 6671.25,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "linear",  # one of ["linear"]
        "ff_ramp_start": 0, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": -25000, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 0, # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

        # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
        "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 1010,  # [MHz] Frequency of qubit pulse
        "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.50,  # [us], used with "arb" and "flat_top"
        "qubit_length": 2,  # [us], used with "const"
        "flat_top_length": 1,  # [us], used with "flat_top"
        "qubit_gain": 15000,  # [DAC units]
        "qubit_ch": 1,  # RFSOC output channel of qubit drive
        "qubit_nqz": 1,  # Nyquist zone to use for qubit drive

        # Ramp sweep parameters
        "ff_ramp_length_start": 0.02,  # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 1,  # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_length_expts": 11, # [int] Number of points in the ff ramp length sweep
        "yokoVoltage": -0.1202,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 0.1, # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
        "relax_delay_2": 10, #- BaseConfig["adc_trig_offset"], # [us] Relax delay after second readout

        # Gain sweep parameters
        "ff_gain_expts": 15,    # [int] How many different ff ramp gains to use
        "ff_ramp_length": 0.02,    # [us] Half-length of ramp to use when sweeping gain

        # Number of cycle repetitions sweep parameters
        "cycle_number_expts": 21,     # [int] How many different values for number of cycles around to use in this experiment
        "max_cycle_number": 100,        # [int] What is the largest number of cycles to use in sweep? Smallest value always 1
        "cycle_delay": 0.02,          # [us] How long to wait between cycles in one experiment?

        # General parameters
        "sweep_type": 'cycle_number',  # [str] What to sweep? 'ramp_length', 'ff_gain', 'cycle_number'
        "reps": 100000,
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
    data_FFRampTest = FFRampTest_Experiment.acquire(Instance_FFRampTest, progress = False)
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
# TITLE : T1 Experiment with Pulse Predistortion
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length" : 35,  # [us]
    "read_pulse_gain": 10000,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.25,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -12500,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 200,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 1024,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq" : 2444,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 2,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 20000,  # [DAC units]

    # Wait sweep parameters
    "yokoVoltage": -0.1202,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 10,  # Relax delay after the first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout
    "wait_start": 2,
    "wait_stop": 500,
    "wait_num": 21,
    "wait_type": 'log',

    # General parameters
    "reps": 20000,
    "cen_num":2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage_freqPoint": -0.1202,
    "pre_meas_delay": 2,
    "pulse_pre_dist": True,
    'dt_pulseplay': 0.5,  # This should be proportional to the qubit spec delay definition
    "auto_dt_pulseplay": True,
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
inst_ff_t1 = FF_T1_wPulsePreDist(path="FF_T1_PS_wPPD", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)
try:
    inst_ff_t1.acquire(plot_predist=False)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_ff_t1 = inst_ff_t1.process_data()
inst_ff_t1.save_data(data_ff_t1)
inst_ff_t1.display(data_ff_t1, plotDisp=True)
inst_ff_t1.display_all_data(data_ff_t1)
inst_ff_t1.save_config()
print(data_ff_t1['data']['centers_list'][-1])
plt.show()

#%%
# TITLE  : Measure Steady State Populations with Pulse Predistortion
UpdateConfig = {
    "read_pulse_style": "const",  # --Fixed
    "read_length" : 35,  # [us]
    "read_pulse_gain": 9500,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.25,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 1000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 1010,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 2444,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain":15000,  # [DAC units]

    # Ramp sweep parameters
    "yokoVoltage": -0.1202,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 5,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 5000,  # [us] Relax delay after second readout
    "pre_meas_delay" : 0.5,

    # General parameters
    "reps": 40000,
    "cen_num":2,
    "initialize_pulse": True,
    "pulse_pre_dist": True,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
    'factor_dist_rlxdlay' : 0.1,  # Portion of relax delay to be distorted
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,

}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
inst_ffsingleshot = FFSingleShot_wPPD(path="FFSingleShot_wPPD", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, progress = True, fast_analysis = True)
try:
    inst_ffsingleshot.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_ffsingle = inst_ffsingleshot.process()
inst_ffsingleshot.save_data(data_ffsingle)
inst_ffsingleshot.save_config()
print(f"Temperature is {data_ffsingle['data']['mean_temp'][1,0]*1e3} mK")
#%%
# TITLE : FF Transmission
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 25,  # [us]
    "read_pulse_gain": 8800,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.25,  # [MHz]
    "TransSpan": 2,
    "TransNumPoints": 101,

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Ramp sweep parameters
    "yokoVoltage": -0.1202,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay": 2000,  # [us] Relax delay after second readout

    # General parameters
    "reps": 1000,
    "cen_num": 2,
    "initialize_pulse": True,
    "negative_pulse": True,
    "pre_meas_delay": 5,
    "post_meas_delay" : 5,
    "pulse_pre_dist": True,
    'dt_pulseplay': 1,  # This should be proportional to the qubit spec delay definitions
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
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
# TITLE : FF - HOLD - Populate - FF - Measure Experiment with Pulse Predistortion
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 25,  # [us]
    "read_pulse_gain": 8800,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.25,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 1000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 1010,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 2444,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 0.5,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 15000,  # [DAC units]

    # Populate Pulse Details
    "pop_pulse_length": 50,  # [us]
    "pop_pulse_gain": 5000,  # [DAC units]
    "pop_pulse_freq": 6671.46,  # [MHz]

    # Ramp sweep parameters
    "yokoVoltage": -0.1202,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 5,  # Relax delay after first readout
    "relax_delay_2": 2500,  # [us] Relax delay after second readout

    # General parameters
    "reps": 30000,
    "cen_num":2,
    "pulse_pre_dist": True,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
    'pop_relax_delay' : 20,
    'factor_dist_rlxdlay': 0.1,  # Portion of relax delay to be distorted
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
inst_FFPopulateProbe = FFPopulateProbe(path="FFPopulateProbe", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, progress = True)
try:
    inst_FFPopulateProbe.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_ffpopprob = inst_FFPopulateProbe.process()
inst_FFPopulateProbe.save_data(data_ffpopprob)
inst_FFPopulateProbe.save_config()
print(f"Temperature is {data_ffpopprob['data']['mean_temp'][1,0]} mK")

#%%
# TITLE : Sweeping flux

from tqdm import tqdm

outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\FF_sweep_30Nov_1012\\"
FF_sweep = np.linspace(14700, 17700, 6)
# add a point at zero to the beginning
# FF_sweep = np.insert(FF_sweep, 0, 0)

def freq_predictor(ff_dac_val):
    return -0.052*ff_dac_val + 1024

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 35,  # [us]
    "read_pulse_gain": 10000,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.25,  # [MHz]

    # Qubit Tone
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 1024,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq" : 69,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 1,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 15000,  # [DAC units]
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # General parameters
    "reps": 25000,
    "cen_num": 2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage": -0.1202,
    "yokoVoltage_freqPoint": -0.1202,
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "use_switch": False,
    "ro_mode_periodic": False,
    "pulse_pre_dist": True,
    "zeroing_pulse": True,
    "qubit_spec_buffer": 10,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
}

config = BaseConfig | UpdateConfig

UpdateConfig_spec_noff = {
    # Qubit spec parameters
    "qubit_freq_start": 900,        # [MHz]
    "qubit_freq_stop": 1150,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    "qubit_freq_expts": 101,  # number of points
    "qubit_gain": 10000,            # [DAC units]
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": 0,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.02,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "relax_delay": 2000,               # [us]
    "reps": 1000,
    'dt_pulseplay': 1,
}
config_spec_noff = config | UpdateConfig_spec_noff

UpdateConfig_spec_ff_beg = {
    # Qubit spec parameters
    "qubit_freq_start": 900,        # [MHz]
    "qubit_freq_stop": 1150,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    "qubit_freq_expts": 101,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.02,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "relax_delay": 2000,               # [us]
    "reps": 1000,
    'dt_pulseplay': 2,
}

config_spec_ff_beg = config | UpdateConfig_spec_ff_beg

UpdateConfig_ff_fid = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 10000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_delay": 0,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

    "relax_delay_1": 1,  # [us] Relax delay after first readout
    "relax_delay_2": 100,  # - BaseConfig["adc_trig_offset"], # [us] Relax delay after second readout
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Number of cycle repetitions sweep parameters
    "cycle_number_expts": 21,  # [int] How many different values for number of cycles around to use in this experiment
    "max_cycle_number": 50,  # [int] What is the largest number of cycles to use in sweep? Smallest value always 1
    "cycle_delay": 0.02,  # [us] How long to wait between cycles in one experiment?

    # General parameters
    "sweep_type": 'cycle_number',  # [str] What to sweep? 'ramp_length', 'ff_gain', 'cycle_number'
    "reps": 20000,
    "sets": 5,
    "angle": None,  # [radians] Angle of rotation for readout
    "threshold": None,  # [DAC units] Threshold between g and e
    "confidence": 0.98,
    "plot_all_points": False,
    "plot_all_lengths": False,
    "verbose": False,
    "relax_delay": 100,               # [us]
}

config_ff_fid = config | UpdateConfig_ff_fid

UpdateConfig_t1 = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 200,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Experiment parameters
    "relax_delay_1": 5,  # Relax delay after the first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout
    "wait_start": 10,
    "wait_stop": 1600,
    "wait_num": 15,
    "wait_type": 'log',

    # General parameters
    "reps": 30000,
    "cen_num":2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage_freqPoint": -0.1202,
    "pre_meas_delay": 2,
    "pulse_pre_dist": True,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
    "auto_dt_pulseplay": True,
}

config_t1 = config | UpdateConfig_t1

UpdateConfig_spec_ff_end = {
    # Qubit spec parameters
    "qubit_freq_start": 980,        # [MHz]
    "qubit_freq_stop": 1080,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse = 5*T1
    "qubit_freq_expts": 51,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse 5*t1 + 10
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.02,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "relax_delay": 20,               # [us]
    "reps": 2000,
    'dt_pulseplay': 2,              # This should be proportional to the qubit spec delay definitions. Setting it to 5*T1/1000
}
config_spec_ff_end = config | UpdateConfig_spec_ff_end

UpdateConfig_spec_post_ff = {
    # Qubit spec parameters
    "qubit_freq_start": 900,        # [MHz]
    "qubit_freq_stop": 1150,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse = 5*T1 + 10
    "qubit_freq_expts": 101,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse 5*t1
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.02,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "relax_delay": 20,               # [us]
    "reps": 1000,
    'dt_pulseplay': 2,              # This should be proportional to the qubit spec delay definitions. Setting it to 5*T1/1000
}
config_spec_post_ff = config | UpdateConfig_spec_post_ff

UpdateConfig_spec_post_zeroing = {
    # Qubit spec parameters
    "qubit_freq_start": 900,  # [MHz]
    "qubit_freq_stop": 1150,  # [MHz]
    "qubit_spec_delay": 10,  # [us] Delay before qubit pulse = 5*T1 + 10
    "qubit_freq_expts": 101,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -10000,  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,  # [us] Total length of positive fast flux pulse 5*t1
    "pre_ff_delay": 0,  # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length": 0.02,
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "relax_delay": 20,  # [us]
    "reps": 1000,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions. Setting it to 5*T1/1000
}
config_spec_post_zeroing = config | UpdateConfig_spec_post_zeroing

UpdateConfig_ss = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 1125,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain
    "qubit_ge_freq": 2444,

    # Ramp sweep parameters
    "relax_delay_1": 5,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout

    # General parameters
    "reps": 100000,
    "cen_num":2,
    "initialize_pulse": True,
    "pulse_pre_dist": True,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
}
config_ss = config | UpdateConfig_ss

UpdateConfig_transmission = {
    # Readout section
    "read_pulse_freq": 6671.5,  # [MHz]
    "read_pulse_gain": 3000,
    "TransSpan": 1,
    "TransNumPoints": 101,

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

   # General Parameters
    "relax_delay": 20,  # [us] Relax delay after second readouts
    "reps": 1000,
    "cen_num": 2,
    "pre_meas_delay": 5,
    "post_meas_delay" : 5,
    "pulse_pre_dist": True,
    'dt_pulseplay': 1,  # This should be proportional to the qubit spec delay definitions
}

config_transmission = config | UpdateConfig_transmission

UpdateConfig_popnprobe = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 1000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Populate Pulse Details
    "pop_pulse_length": 30,  # [us]
    "pop_pulse_gain": 5000,  # [DAC units]
    "pop_pulse_freq": 6671.46,  # [MHz]
    'pop_relax_delay': 5,

    # Ramp sweep parameters
    "relax_delay_1": 5,  # Relax delay after first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout

    # General parameters
    "reps": 100000,
    "cen_num":2,
    "pulse_pre_dist": True,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
}
config_popnprobe = config | UpdateConfig_popnprobe

#%%
qubit_freq_readout_list = []
qubit_freq_ff_beg_list = []
fid_list = []
t1_meas_list = []
t1_err_meas_list = []
temp_rate_meas_list = []
temp_rate_err_meas_list = []
qubit_freq_ff_end_list  = []
qubit_freq_post_ff_list = []
qubit_freq_post_relax_list = []
pop_meas_list = []
pop_meas_err_list = []
temp_ss_meas_list = []
temp_ss_err_meas_list = []
tranmsission_freq_list = []
temp_popnprobe_meas_list = []
temp_popnprobe_err_meas_list = []
pop_popnprobe_meas_list = []
pop_popnprobe_err_meas_list = []
centers = [[ 3.47040081, -3.8108755 ], [3.6454694, -2.14590693]]
centers_list = []

#%%
print("========== STARTING EXPERIMENTS =============")
for i in tqdm(range(FF_sweep.size)):

    print(f"----- Starting experiments for FF DAC value {FF_sweep[i]} -----")
    config_transmission = config | UpdateConfig_transmission
    # Update the DAC value in all three experiments
    config_spec_ff_beg['ff_gain'] = FF_sweep[i]
    config_ff_fid['ff_ramp_stop'] = FF_sweep[i]
    config_t1['ff_ramp_stop'] = FF_sweep[i]
    config_spec_ff_end['ff_gain'] = FF_sweep[i]
    config_spec_post_ff['ff_gain'] = FF_sweep[i]
    config_spec_post_zeroing['ff_gain'] = FF_sweep[i]
    config_ss['ff_ramp_stop'] = FF_sweep[i]
    config_transmission['ff_ramp_stop'] = FF_sweep[i]
    config_popnprobe['ff_ramp_stop'] = FF_sweep[i]

    # Create a new directory
    outerFolderDac = outerFolder + "dac_" + str(FF_sweep[i]) + "\\"

    # Using the freq predictor update the span of the frequency for the spec slice
    qubit_ge_freq = freq_predictor(FF_sweep[i])
    print(f"Qubit's predicted frequency is {qubit_ge_freq}")
    config_spec_ff_beg['qubit_freq_start'] = qubit_ge_freq - 100
    config_spec_ff_beg['qubit_freq_stop'] = qubit_ge_freq + 100
    config_spec_ff_end['qubit_freq_start'] = qubit_ge_freq - 100
    config_spec_ff_end['qubit_freq_stop'] = qubit_ge_freq + 100

    # Update qubit_ge_freq in other configs
    config_t1['qubit_ge_freq'] = qubit_ge_freq
    config_ss['qubit_ge_freq'] = qubit_ge_freq
    config_popnprobe['qubit_ge_freq'] = qubit_ge_freq

    # TITLE : Run the spec slice without fast flux to get the qubit frequency
    soc.reset_gens()
    inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
                                                 outerFolder=outerFolderDac, short_directory_names=True)
    data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
    inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
    inst_spec_noff.save_data(data_FFSpecSlice)
    inst_spec_noff.save_config()

    # Get the qubit frequency
    qubit_freq = inst_spec_noff.qubit_peak_freq
    qubit_freq_readout_list.append(qubit_freq)

    # Update the qubit frequency in other config
    config_ff_fid['qubit_freq'] = qubit_freq
    config_t1['qubit_freq'] = qubit_freq
    config_ss['qubit_freq'] = qubit_freq
    config_popnprobe['qubit_freq'] = qubit_freq

    # TITLE : Run the spec slice at beginning of a fast flux pulse
    soc.reset_gens()
    inst_spec_ff_beg = FFSpecSlice_Experiment_wPPD(path="Spec_FF_beg", cfg=config_spec_ff_beg, soc=soc, soccfg=soccfg,
                                                 outerFolder=outerFolderDac, short_directory_names=True)
    data_FFSpecSlice = inst_spec_ff_beg.acquire(progress=False)
    inst_spec_ff_beg.display(data_FFSpecSlice, plot_disp=False)
    inst_spec_ff_beg.save_data(data_FFSpecSlice)
    inst_spec_ff_beg.save_config()

    # Get the qubit frequency qnd update the configs
    qubit_ge_freq = inst_spec_ff_beg.qubit_peak_freq
    qubit_freq_ff_beg_list.append(qubit_ge_freq)
    print(f"Qubit's measured frequency is {qubit_ge_freq}")
    config_t1['qubit_ge_freq'] = qubit_ge_freq
    config_ss['qubit_ge_freq'] = qubit_ge_freq
    config_popnprobe['qubit_ge_freq'] = qubit_ge_freq

    # TITLE : Run the FF fidelity check
    soc.reset_gens()
    Instance_FFRampTest = FFRampTest_Experiment(path="FFRampTest", cfg=config_ff_fid, soc=soc, soccfg=soccfg,
                                                outerFolder=outerFolderDac, short_directory_names=True)
    # Estimate Time
    try:
        data_FFRampTest = FFRampTest_Experiment.acquire(Instance_FFRampTest, progress=False)
        FFRampTest_Experiment.display(Instance_FFRampTest, data_FFRampTest, plot_disp=False,
                                      plot_all_lengths=config_ff_fid['plot_all_lengths'])
        FFRampTest_Experiment.save_data(Instance_FFRampTest, data_FFRampTest)
        FFRampTest_Experiment.save_config(Instance_FFRampTest)
        fid_list.append((data_FFRampTest['data']['pop'][0, 0, 1] + data_FFRampTest['data']['pop'][0, 1, 0]) / 2)
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    plt.close('all')

    # TITLE : Run T1
    soc.reset_gens()
    inst_ff_t1 = FF_T1_wPulsePreDist(path="FF_T1_PS_wPPD", cfg=config_t1, soc=soc, soccfg=soccfg,
                                     outerFolder=outerFolderDac)
    try:
        inst_ff_t1.acquire(plot_predist=False)
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    data_ff_t1 = inst_ff_t1.process_data()
    inst_ff_t1.save_data(data_ff_t1)
    inst_ff_t1.display(data_ff_t1, plotDisp=True)
    inst_ff_t1.display_all_data(data_ff_t1)
    inst_ff_t1.save_config()

    # Get the T1 and update the ff_hold in config_ss
    # t1 = t1_meas_list[i]
    t1 = data_ff_t1['data']['T1']
    t1_err = data_ff_t1['data']['T1_err']

    # Update the lists
    t1_meas_list.append(t1)
    t1_err_meas_list.append(t1_err)
    temp_rate_meas_list.append(data_ff_t1['data']['temp_rate'])
    temp_rate_err_meas_list.append(data_ff_t1['data']['temp_std_rate'])

    # TITLE : Run spec slice at end of fast flux pulse
    soc.reset_gens()
    # Updating the length based on t1
    config_spec_ff_end['ff_length'] = 5*t1 + 10
    config_spec_ff_end['qubit_spec_delay'] = 5*t1
    config_spec_ff_end['dt_pulseplay'] = max(1, int((5*t1)/1000))
    inst_spec_ff_end = FFSpecSlice_Experiment_wPPD(path="Spec_FF_end", cfg=config_spec_ff_end, soc=soc, soccfg=soccfg,
                                                 outerFolder=outerFolderDac, short_directory_names=True)
    data_FFSpecSlice = inst_spec_ff_end.acquire(progress=False)
    inst_spec_ff_end.display(data_FFSpecSlice, plot_disp=False)
    inst_spec_ff_end.save_data(data_FFSpecSlice)
    inst_spec_ff_end.save_config()
    qubit_freq_ff_end_list.append(inst_spec_ff_end.qubit_peak_freq)

    # TITLE : Run spec slice after the fast flux pulse
    soc.reset_gens()
    # Updating the length based on t1
    config_spec_post_ff['ff_length'] = 5*t1
    config_spec_post_ff['qubit_spec_delay'] = 5*t1 + 10
    config_spec_post_ff['dt_pulseplay'] = max(1, int((5*t1 + 10)/1000))
    inst_spec_post_ff = FFSpecSlice_Experiment_wPPD(path="Spec_post_FF", cfg=config_spec_post_ff, soc=soc, soccfg=soccfg,
                                                    outerFolder=outerFolderDac, short_directory_names=True)
    data_FFSpecSlice = inst_spec_post_ff.acquire(progress=False)
    inst_spec_post_ff.display(data_FFSpecSlice, plot_disp=False)
    inst_spec_post_ff.save_data(data_FFSpecSlice)
    inst_spec_post_ff.save_config()
    qubit_freq_post_ff_list.append(inst_spec_post_ff.qubit_peak_freq)

    # TITLE : Run Spec slice after the relax delay
    soc.reset_gens()
    # Updating the length based on t1
    config_spec_post_zeroing['ff_length'] = 5*t1
    config_spec_post_zeroing['dt_pulseplay'] = max(1, int((5*t1 + config_spec_post_ff['relax_delay'])/1000))
    inst_spec_post_relax = FFSpecSlice_Experiment_wPPD_studyzeroing(path="Spec_post_zeroing", cfg=config_spec_post_zeroing, soc=soc, soccfg=soccfg,
                                                    outerFolder=outerFolderDac, short_directory_names=True)
    data_FFSpecSlice = inst_spec_post_relax.acquire(progress=False)
    inst_spec_post_relax.display(data_FFSpecSlice, plot_disp=False)
    inst_spec_post_relax.save_data(data_FFSpecSlice)
    inst_spec_post_relax.save_config()
    qubit_freq_post_relax_list.append(inst_spec_post_relax.qubit_peak_freq)

    # TITLE : Run Single Shot
    soc.reset_gens()
    # Updating the ff_hold based on t1
    config_ss['ff_hold'] = 5 * t1
    config_ss['dt_pulseplay'] = max(1, int((5*t1)/200))
    print(f"Setting ff_hold to {config_ss['ff_hold']} us and dt_pulseplay to {config_ss['dt_pulseplay']} us")
    inst_ffsingleshot = FFSingleShot_wPPD(path="FFSingleShot_wPPD", cfg=config_ss, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolderDac, progress=False, fast_analysis=False)
    try:
        inst_ffsingleshot.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    data_ffsingle = inst_ffsingleshot.process(centers=centers)
    inst_ffsingleshot.save_data(data_ffsingle)
    inst_ffsingleshot.save_config()
    if i == 0:
        centers = data_ffsingle['data']['centers']
        pop_mean = data_ffsingle['data']['mean_pop']

        # Rearrange the centers so that the first center is the ground state
        # Use the pop_mean which is an array of cen_num length of populations of each state.
        # The highest population state is the ground state
        sorted_indices = np.argsort(pop_mean)
        centers = centers[sorted_indices]
        centers_list.append(centers)

        print(f"Centers are {centers}")

        # Updating the lists
        pop_meas_list.append(data_ffsingle['data']['mean_pop'][sorted_indices])
        pop_meas_err_list.append(data_ffsingle['data']['std_pop'][sorted_indices])
        temp_ss_meas_list.append(data_ffsingle['data']['mean_temp'][1,0])
        temp_ss_err_meas_list.append(data_ffsingle['data']['std_temp'][1,0])

    else:
        # Updating the lists
        pop_meas_list.append(data_ffsingle['data']['mean_pop'])
        pop_meas_err_list.append(data_ffsingle['data']['std_pop'])
        temp_ss_meas_list.append(data_ffsingle['data']['mean_temp'][1,0])
        temp_ss_err_meas_list.append(data_ffsingle['data']['std_temp'][1,0])

        # Using the new centers for next iterations
        centers = data_ffsingle['data']['centers']
        centers_list.append(centers)

    # TITLE : Running Transmission
    soc.reset_gens()
    inst_ff_trans = FFTransmission(path="FF_Transmission", cfg=config_transmission, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolderDac)
    try:
        data_ff_trans = inst_ff_trans.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    inst_ff_trans.display(data=data_ff_trans, plotDisp=False)
    inst_ff_trans.save_data(data_ff_trans)
    inst_ff_trans.save_config()
    trans_peak = inst_ff_trans.peakFreq
    print(f"The populating frequency is set to {trans_peak} MHz")
    config_popnprobe['pop_pulse_freq'] = trans_peak

    # Updating the lists
    tranmsission_freq_list.append(inst_ff_trans.peakFreq)

    # TITLE : Running Populate Probe Experiment
    soc.reset_gens()
    config_popnprobe['ff_hold'] = 5 * t1
    config_popnprobe['dt_pulseplay'] = max(1, int((5 * t1) / 200))
    print(f"Setting ff_hold to {config_popnprobe['ff_hold']} us and dt_pulseplay to {config_popnprobe['dt_pulseplay']} us")
    inst_FFPopulateProbe = FFPopulateProbe(path="FFPopulateProbe", cfg=config_popnprobe, soc=soc, soccfg=soccfg,
                                           outerFolder=outerFolderDac, progress=False)
    try:
        inst_FFPopulateProbe.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
    data_ffpopprob = inst_FFPopulateProbe.process(centers=centers)
    inst_FFPopulateProbe.save_data(data_ffpopprob)
    inst_FFPopulateProbe.save_config()
    print(f"Temperature is {data_ffpopprob['data']['mean_temp'][1, 0]} mK")

    # Updating the lists
    pop_popnprobe_meas_list.append(data_ffpopprob['data']['mean_pop'])
    pop_popnprobe_err_meas_list.append(data_ffpopprob['data']['std_pop'])
    temp_popnprobe_meas_list.append(data_ffpopprob['data']['mean_temp'][1, 0])
    temp_popnprobe_err_meas_list.append(data_ffpopprob['data']['std_temp'][1, 0])

# Saving all the lists
collated_data = {
    "FF_sweep": FF_sweep,
    "qubit_freq_readout_list": qubit_freq_readout_list,
    "qubit_freq_ff_beg_list": qubit_freq_ff_beg_list,
    "fid_list": fid_list,
    "t1_meas_list": t1_meas_list,
    "t1_err_meas_list": t1_err_meas_list,
    "temp_rate_meas_list": temp_rate_meas_list,
    "temp_rate_err_meas_list": temp_rate_err_meas_list,
    "qubit_freq_ff_end_list": qubit_freq_ff_end_list,
    "qubit_freq_post_ff_list": qubit_freq_post_ff_list,
    "qubit_freq_post_relax_list": qubit_freq_post_relax_list,
    "pop_meas_list": pop_meas_list,
    "pop_meas_err_list": pop_meas_err_list,
    "temp_ss_meas_list": temp_ss_meas_list,
    "temp_ss_err_meas_list": temp_ss_err_meas_list,
    "tranmsission_freq_list": tranmsission_freq_list,
    "temp_popnprobe_meas_list": temp_popnprobe_meas_list,
    "temp_popnprobe_err_meas_list": temp_popnprobe_err_meas_list,
    "pop_popnprobe_meas_list": pop_popnprobe_meas_list,
    "pop_popnprobe_err_meas_list": pop_popnprobe_err_meas_list,
    "pop_pulse_gain" : config_popnprobe['pop_pulse_gain'],
}

# Save the data using h5
import h5py
def save_collated_h5(collated_data, path="collated_data.h5"):
    with h5py.File(path, "w") as f:
        # Stack the special ones
        f.create_dataset("pop_meas_list", data=np.stack(collated_data["pop_meas_list"]))
        f.create_dataset("pop_meas_err_list", data=np.stack(collated_data["pop_meas_err_list"]))
        f.create_dataset("pop_popnprobe_meas_list", data=np.stack(collated_data["pop_popnprobe_meas_list"]))
        f.create_dataset("pop_popnprobe_err_meas_list", data=np.stack(collated_data["pop_popnprobe_err_meas_list"]))

        # Everything else straight to dataset
        skip = {"pop_meas_list", "pop_meas_err_list", "pop_popnprobe_meas_list", "pop_popnprobe_err_meas_list"}
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
qubit_freq = np.array(collated_data["qubit_freq_ff_beg_list"])
qubit_freq_readout = np.array(collated_data["qubit_freq_readout_list"])
qubit_freq_ff_end = np.array(collated_data["qubit_freq_ff_end_list"])
qubit_freq_post_ff = np.array(collated_data["qubit_freq_post_ff_list"])
qubit_freq_post_relax = np.array(collated_data["qubit_freq_post_relax_list"])
transmission_freq = np.array(collated_data["tranmsission_freq_list"])
pop_popnprobe_meas = np.stack(collated_data["pop_popnprobe_meas_list"])          # shape (N, 2)
pop_popnprobe_err = np.stack(collated_data["pop_popnprobe_err_meas_list"])  # shape (N, 2)
temp_popnprobe = np.abs(np.array(collated_data["temp_popnprobe_meas_list"]) * 1000)
temp_popnprobe_err = np.array(collated_data["temp_popnprobe_err_meas_list"]) * 1000

# Excited state = the smaller of g/e
min_pop = np.min(pop_meas, axis=1)
min_pop_err = np.take_along_axis(pop_meas_err, np.argmin(pop_meas, axis=1)[:, np.newaxis], axis=1).flatten()
min_popnprobe = np.min(pop_popnprobe_meas, axis=1)
min_popnprobe_err = np.take_along_axis(pop_popnprobe_err, np.argmin(pop_popnprobe_meas, axis=1)[:, np.newaxis], axis=1).flatten()

# Excited states with fix
excited_pop = pop_meas[:,0]
excited_pop_err = pop_meas_err[:,0]
excited_popnprobe = pop_popnprobe_meas[:,0]
excited_popnprobe_err = pop_popnprobe_err[:,0]


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
            fmt="o", capsize=3, label="Single shot")
make_pretty(ax, "FF DAC Value", "Temperature (measured through single shot) [mK]")
ax.legend()
save_fig(fig, "temperature_single_shot")

# -------------------------
# 2. temp_rate vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, temp_rate, yerr=temp_rate_err,
            fmt="s", capsize=3, color="C1", label="Rate-based")
make_pretty(ax, "FF DAC Value", "Temperature (measured through Rates) [mK]")
ax.legend()
save_fig(fig, "temperature_rates")

# -------------------------
# 3. Both temperatures vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, temp_ss, yerr=temp_ss_err,
            fmt="o", capsize=3, label="Single shot")
ax.errorbar(FF_sweep, temp_rate, yerr=temp_rate_err,
            fmt="s", capsize=3, label="Rate-based")
make_pretty(ax, "FF DAC Value", "Temperature [mK]")
ax.legend()
save_fig(fig, "temperature_comparison")

# -------------------------
# 4. T1 vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, t1, yerr=t1_err,
            fmt="d", capsize=3, color="C2", label="T1")
make_pretty(ax, "FF DAC Value", "T1 [µs]")
ax.legend()
save_fig(fig, "t1_vs_ff")

# -------------------------
# 5. Excited state population vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, excited_pop, yerr=excited_pop_err,
            fmt="^", capsize=3, color="C3", label="Excited state population")
make_pretty(ax, "FF DAC Value", "Excited State Population")
ax.legend()
save_fig(fig, "excited_population_vs_ff")

# -------------------------
# 5.1  Min state population vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, min_pop, yerr=min_pop_err,
            fmt="^", capsize=3, color="C3", label="minimum state population")
make_pretty(ax, "FF DAC Value", "Minimum State Population")
ax.legend()
save_fig(fig, "minimum_population_vs_ff")


# -------------------------
# 6. Qubit frequency vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, qubit_freq, "o", color="C4", label="Qubit frequency")
make_pretty(ax, "FF DAC Value", "Qubit Frequency [GHz]")
ax.legend()
save_fig(fig, "qubit_frequency_vs_ff")

# -------------------------
# 7. Transmission frequency vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, transmission_freq, "o", color="C5", label="Transmission peak frequency")
make_pretty(ax, "FF DAC Value", "Transmission Peak Frequency [GHz]")
ax.legend()
save_fig(fig, "transmission_frequency_vs_ff")

# -------------------------
# 8. Excited state population from populate-probe vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, excited_popnprobe, yerr=excited_popnprobe_err,
            fmt="v", capsize=3, color="C6", label="Excited state population (populate-probe)")
make_pretty(ax, "FF DAC Value", "Excited State Population (populate-probe)")
ax.legend()
save_fig(fig, "excited_population_populate_probe_vs_ff")

# -------------------------
# 8. Minimum state population from populate-probe vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, min_popnprobe, yerr=min_popnprobe_err,
            fmt="v", capsize=3, color="C6", label="Minimum state population (populate-probe)")
make_pretty(ax, "FF DAC Value", "Minimum State Population (populate-probe)")
ax.legend()
save_fig(fig, "min_population_populate_probe_vs_ff")


# -------------------------
# 9. Temperature from populate-probe vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, temp_popnprobe, yerr=temp_popnprobe_err,
            fmt="D", capsize=3, color="C7", label="Temperature (populate-probe)")
make_pretty(ax, "FF DAC Value", "Temperature (populate-probe) [mK]")
ax.legend()
save_fig(fig, "temperature_populate_probe")

# ------------------------
# 10. Excited state population comparison from populate-probe and single-shot
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(FF_sweep, excited_pop, yerr=excited_pop_err,
            fmt="^", capsize=3, label="Single shot")
ax.errorbar(FF_sweep, excited_popnprobe, yerr=excited_popnprobe_err,
            fmt="v", capsize=3, label="Populate-probe")
make_pretty(ax, "FF DAC Value", "Excited State Population")
ax.legend()
save_fig(fig, "excited_population_comparison")

#------------------------
# Checking if qubit freq ff beg and ff end are the same
#------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, qubit_freq - qubit_freq_ff_end, "o-", label="FF begin - FF end")
make_pretty(ax, "FF DAC Value", "Qubit Frequency difference of FF begin - FF end [MHz]")
ax.legend()
save_fig(fig, "qubit_freq_ff_beg_end_difference")

# ----------------------
# Checking if qubit freq at readout and post FF are the same
#----------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, qubit_freq_readout - qubit_freq_post_ff, "o-", label="No FF - Post FF")
make_pretty(ax, "FF DAC Value", "Qubit Frequency Difference of No FF and Post FF [MHz]")
ax.legend()
save_fig(fig, "qubit_freq_noff_postff_difference")

#------------------------
# CHecking if qubit freq at readout and post relax are the same
#------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, qubit_freq_readout - qubit_freq_post_relax, "o-", label="No FF - Post Relax")
make_pretty(ax, "FF DAC Value", "Qubit Frequency difference of No FF - Post Relax [MHz]")
ax.legend()
save_fig(fig, "qubit_freq_noff_postrelax_difference")

plt.show()

#%%