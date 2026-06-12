#%%
import os
import time
from matplotlib import pyplot as plt
import Pyro4.util
import numpy as np

path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFSpecVsDelay_wPulsePreDist import FFSpecVsDelay_wPPD_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFSpecSlice_wPulsePreDist import FFSpecSlice_Experiment_wPPD
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFSpecSlice_wPulsePreDist_studyZeroing import FFSpecSlice_Experiment_wPPD_studyzeroing
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFSpecVsFlux_wPulsePreDist import FFSpecVsFlux_wPulsePreDist
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFRampTest_corrected import FFRampTest_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFF_T1_wPulsePreDist import FF_T1_wPulsePreDist
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFSingleShot_wPulsePreDist import FFSingleShot_wPPD
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFTransmission_wPulsePreDist import FFTransmission
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFTransmission_wPulsePreDist_wPS import FFTransmission_PS
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFPopulateProbe_wPulsePreDist import FFPopulateProbe
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFStarkShift_wPulsePreDist import FFStarkShift_Experiment_wPPD

# Define the saving path
outerFolder = r"Z:\\TantalumFluxonium\\Data\\2026_03_31_cooldown\\HouckCage_dev\\" # end in '\\'

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
    "read_length": 30,                # [us]
    "read_pulse_gain": 2500,         # [DAC units]
    "read_pulse_freq": 6826.943,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 2600,        # [MHz]
    "qubit_freq_stop": 2900,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 2,               # [us], used with "const"
    "flat_top_length": 10,        # [us], used with "flat_top"
    "qubit_gain":30000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    'qubit_spec_buffer':10,

    # Fast flux pulse parameters
    "ff_gain": 0,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 30,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "yokoVoltage": -0.6225,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 20,               # [us]
    "qubit_freq_expts": 101,         # number of points
    "reps": 1000,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
    "use_switch": False,
    'negative_pulse': False,
    'dt_pulseplay': 0.5,

}

config = BaseConfig | UpdateConfig
# yoko.SetVoltage(config["yokoVoltage"])
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
    "read_pulse_gain": 2500,         # [DAC units]
    "read_pulse_freq": 6826.943,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 2700,        # [MHz]
    "qubit_freq_stop": 2800,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.02,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 5,               # [us], used with "const"
    "flat_top_length": 0.020,        # [us], used with "flat_top"
    "qubit_gain": 30000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # Fast flux pulse parameters
    "ff_gain": 6000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 5000,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

    "yokoVoltage": -0.6225,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 20,               # [us]
    "qubit_freq_expts": 41,         # number of points
    "reps": 500,
    "use_switch": False,
    "pre_meas_delay": 5,

    # post_ff_delay sweep parameters: delay after fast flux pulse (before qubit pulse)
    "qubit_spec_delay_start": 5001,  # [us] Initial value
    "qubit_spec_delay_stop": 7000,      # [us] Final value
    "qubit_spec_delay_steps": 31,# number of post_ff_delay points to take
    "spacing": 'linear',
    "negative_pulse": False,
    "pulse_pre_dist": False,
    'dt_pulseplay': 10, # This should be proportional to the qubit spec delay definitions
    'dt_set_auto': True,
    "zeroing_pulse": False,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
    "qubit_spec_buffer" : 10, # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)
}
config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])
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
    data_FFSpecVsDelay = Instance_FFSpecVsDelay_wPPD.acquire( progress = True, custom_delay_array = None, plot_debug = False)
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
    "read_length": 30,                # [us]
    "read_pulse_gain": 2500,         # [DAC units]
    "read_pulse_freq": 6826.943,     # [MHz]
    "ro_mode_periodic" : False,

    # Qubit spec parameters
    "qubit_freq_start": 2700,        # [MHz]
    "qubit_freq_stop": 3500,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 5,               # [us], used with "const"
    "flat_top_length": 10,        # [us], used with "flat_top"
    "qubit_gain": 30000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive
    "qubit_spec_delay": 5,          # [us] Delay before qubit pulse
    "qubit_spec_buffer": 1,

    # Fast flux pulse parameters
    "ff_gain": 10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 10,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "yokoVoltage": -0.6225,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 50,               # [us]
    "qubit_freq_expts": 101,         # number of points
    "reps": 400,
    "pulse_pre_dist": False,
    "use_switch": False,
    'negative_pulse': False,
    'dt_pulseplay': 0.5,
    "zeroing_pulse": False,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,

    # Sweep through the dac values for ff
    "ff_gain_start": -1000,
    "ff_gain_stop": 1000,
    "ff_gain_num_points": 11,
}
config = BaseConfig | UpdateConfig
# yoko.SetVoltage(config["yokoVoltage"])

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
        "read_length": 8,  # [us]
        "read_pulse_gain": 5000, #5600,  # [DAC units]
        "read_pulse_freq": 7391.96,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "linear",  # one of ["linear"]
        "ff_ramp_start": 0, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": -1000, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 0, # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

        # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
        "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 973,  # [MHz] Frequency of qubit pulse
        "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.50,  # [us], used with "arb" and "flat_top"
        "qubit_length": 4,  # [us], used with "const"
        "flat_top_length": 1,  # [us], used with "flat_top"
        "qubit_gain": 30000,  # [DAC units]
        "qubit_ch": 1,  # RFSOC output channel of qubit drive
        "qubit_nqz": 1,  # Nyquist zone to use for qubit drive

        # Ramp sweep parameters
        "ff_ramp_length_start": 0.02,  # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 1,  # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_length_expts": 11, # [int] Number of points in the ff ramp length sweep
        "yokoVoltage": -1.128,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 0.1, # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
        "relax_delay_2": 10, #- BaseConfig["adc_trig_offset"], # [us] Relax delay after second readout

        # Gain sweep parameters
        "ff_gain_expts": 15,    # [int] How many different ff ramp gains to use
        "ff_ramp_length": 0.02,    # [us] Half-length of ramp to use when sweeping gain

        # Number of cycle repetitions sweep parameters
        "cycle_number_expts": 11,     # [int] How many different values for number of cycles around to use in this experiment
        "max_cycle_number": 100,        # [int] What is the largest number of cycles to use in sweep? Smallest value always 1
        "cycle_delay": 0.005,          # [us] How long to wait between cycles in one experiment?

        # General parameters
        "sweep_type": 'cycle_number',  # [str] What to sweep? 'ramp_length', 'ff_gain', 'cycle_number'
        "reps": 300000,
        "angle": None, # [radians] Angle of rotation for readout
        "cen_num": 2,
        "threshold": None, # [DAC units] Threshold between g and e
        "confidence": 0.999,
        "plot_all_points": False,
        "plot_all_lengths": True,
        "verbose": False,

    }

# We have 65536 samples (9.524 us) wave memory on the FF channel (and all other channels)

yoko.SetVoltage(config["yokoVoltage"])
config = BaseConfig | config
Instance_FFRampTest = FFRampTest_Experiment(path="FFRampTest", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)
# Estimate Time

print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFRampTest = FFRampTest_Experiment.acquire(Instance_FFRampTest, progress = False)
    data_FFRampTest = FFRampTest_Experiment.process(Instance_FFRampTest, data_FFRampTest)
    FFRampTest_Experiment.display(Instance_FFRampTest, data_FFRampTest, plot_disp=True)
    FFRampTest_Experiment.save_data(Instance_FFRampTest, data_FFRampTest['data'])
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
    "read_length": 35,  # [us]
    "read_pulse_gain": 3500,  # 5600,  # [DAC units]
    "read_pulse_freq": 6826.78,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 0,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 200,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 2595,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq" : 2595,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 3,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 30000,  # [DAC units]

    # Wait sweep parameters
    "yokoVoltage": -1.349,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 10,  # Relax delay after the first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout
    "wait_start": 2,
    "wait_stop": 3000,
    "wait_num": 21,
    "wait_type": 'log',

    # General parameters
    "reps": 30000,
    "cen_num":2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage_freqPoint": -1.349,
    "pre_meas_delay": 6,
    "pulse_pre_dist": False,
    'dt_pulseplay': 20,  # This should be proportional to the qubit spec delay definition
    "auto_dt_pulseplay": True,
    "zeroing_pulse": False,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
}
config = BaseConfig | UpdateConfig
# yoko.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
inst_ff_t1 = FF_T1_wPulsePreDist(path="FF_T1_PS_wPPD", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)

#%%
try:
    inst_ff_t1.acquire(plot_predist=False)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_ff_t1 = inst_ff_t1.process_data()
inst_ff_t1.save_data(data_ff_t1)
inst_ff_t1.display(data_ff_t1, plotDisp=True)
# inst_ff_t1.display_all_data(data_ff_t1)
inst_ff_t1.save_config()
print(data_ff_t1['data']['centers_list'][-1])
plt.show()

#%%
# TITLE  : Measure Steady State Populations with Pulse Predistortion
UpdateConfig = {
    "read_pulse_style": "const",  # --Fixed
    "read_length" : 9,  # [us]
    "read_pulse_gain": 5500,  # 5600,  # [DAC units]
    "read_pulse_freq": 7392,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -3000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 13235.138477098331,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 967,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 2444,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 3,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain":30000,  # [DAC units]

    # Ramp sweep parameters
    "yokoVoltage": -1.128,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 20,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout
    "pre_meas_delay" : 0.5,

    # General parameters
    "reps": 10000,
    "cen_num":2,
    "initialize_pulse": True,
    "pulse_pre_dist": True,
    'dt_pulseplay': 66,  # This should be proportional to the qubit spec delay definitions
    'factor_dist_rlxdlay' : 0.1,  # Portion of relax delay to be distorted
    "zeroing_pulse": True,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,

}
config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
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
    "read_length": 40,  # [us]
    "read_pulse_gain": 200,  # 5600,  # [DAC units]
    "read_pulse_freq": 6826.943,  # [MHz]
    "TransSpan": 0.5,
    "TransNumPoints": 101,

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 0,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

    # Qubit Param
    "qubit_freq": 1622.5,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 1622.5,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 20,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 0,  # [DAC units]
    "qubit_mode_periodic": False,  # Currently unused, applies to "const" drive

    # Ramp sweep parameters
    "yokoVoltage": -0.622,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay": 100,  # [us] Relax delay after second readout

    # General parameters
    "reps": 2000,
    "cen_num": 2,
    "initialize_pulse": True,
    "negative_pulse": False,
    "pre_meas_delay": 5,
    "post_meas_delay" : 5,
    "pulse_pre_dist": False,
    'dt_pulseplay': 1,  # This should be proportional to the qubit spec delay definitions
    "zeroing_pulse": False,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
}
config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])
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
# Acquire 2d
sweep_key = "ff_ramp_stop"
sweep_var = np.linspace(0,-3000, 101)
inst_ff_trans = FFTransmission(path="FF_Transmission", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)
inst_ff_trans.acquire_2d(sweep_key = sweep_key, sweep_values = sweep_var)

#%%
# TITLE : FF Transmission with post selection
UpdateConfig = {
    "read_pulse_style": "const",  # --Fixed
    "read_length": 40,  # [us]
    "read_pulse_gain": 2500,  # 5600,  # [DAC units]
    "read_pulse_freq": 6826.943,  # [MHz]
    "scan_length": 30,  # [us]
    "scan_pulse_gain": 1000,  # 5600,  # [DAC units]
    "scan_pulse_freq": 6826.943,  # [MHz]
    "TransSpan": 0.5,
    "TransNumPoints": 51,

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 0,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

    # Qubit
    "qubit_freq": 2760,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 2760,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 10,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 0,  # [DAC units]
    "qubit_mode_periodic": False,  # Currently unused, applies to "const" drive

    # Ramp sweep parameters
    "yokoVoltage": -0.624,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay": 10,  # [us] Relax delay after second readout

    # General parameters
    "reps": 3000,
    "cen_num": 2,
    "initialize_pulse": True,
    "negative_pulse": False,
    "pre_meas_delay": 5,
    "post_meas_delay" : 5,
    "pulse_pre_dist": False,
    'dt_pulseplay': 1,  # This should be proportional to the qubit spec delay definitions
    "zeroing_pulse": False,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
}
config = BaseConfig | UpdateConfig
yoko.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
#%%
plt.close('all')
inst_ff_trans = FFTransmission_PS(path="FF_Transmission_PS", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)
try:
    data_ff_trans = inst_ff_trans.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_ff_trans = inst_ff_trans.process(data= data_ff_trans)
inst_ff_trans.display(data = data_ff_trans,plotDisp = True)
inst_ff_trans.save_data(data_ff_trans)
inst_ff_trans.save_config()

#%%
# TITLE : FF - HOLD - Populate - FF - Measure Experiment with Pulse Predistortion
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 15,  # [us]
    "read_pulse_gain": 5000,  # 5600,  # [DAC units]
    "read_pulse_freq": 7392,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 00,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 5000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 965,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq": 2444,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 3,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 30000,  # [DAC units]

    # Populate Pulse Details
    "pop_pulse_length": 50,  # [us]
    "pop_pulse_gain": 5000,  # [DAC units]
    "pop_pulse_freq": 7392,  # [MHz]

    # Ramp sweep parameters
    "yokoVoltage": -1.128,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay_1": 20,  # Relax delay after first readout
    "relax_delay_2": 25,  # [us] Relax delay after second readout

    # General parameters
    "reps": 3000000,
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
# yoko1.SetVoltage(config["yokoVoltage"])
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
# TITLE :  Stark shift slice with Pulse Predistortion
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 40,  # [us]
    "read_pulse_gain": 2500,  # 5600,  # [DAC units]
    "read_pulse_freq": 6826.78,  # [MHz]

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 0,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 20,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 2609,  # [MHz] Frequency of qubit pulse
    "sigma": 0.5,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "qubit_length": 3,  # [us], used with "const"
    "qubit_gain": 30000,  # [DAC units]

    # Populate Pulse Details
    "pop_pulse_length": 20,  # [us]
    "pop_pulse_gain": 1500,  # [DAC units]
    "pop_pulse_freq": 6826.94,  # [MHz]
    'pop_relax_delay' : 5,

    # Qubit frequency sweep
    "qubit_freq_start": 2560,  # [MHz]
    "qubit_freq_stop": 2660,  # [MHz]
    "qubit_freq_expts": 51,  # number of points

    # General parameters
    "relax_delay_2": 200,  # [us] Relax delay after second readout
    "reps": 2000,
    "pulse_pre_dist": False,
    'dt_pulseplay': 0.5,  # This should be proportional to the qubit spec delay definitions
    "zeroing_pulse": False,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
    'yokoVoltage': -1.349,
}
config = BaseConfig | UpdateConfig
# yoko.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
#%%
inst_ffstark = FFStarkShift_Experiment_wPPD(path="FFStarkShift_wPPD", cfg=config,soc=soc,soccfg=soccfg,
                                            outerFolder = outerFolder, progress = True)
data_ffstark = inst_ffstark.acquire(progress = True, plot_debug=False)
inst_ffstark.display(data_ffstark, plot_disp=True)
inst_ffstark.save_data(data_ffstark)
inst_ffstark.save_config()
print(inst_ffstark.qubit_peak_freq)
plt.show()
 #%%
# TITLE : Stark shift vs pop gain
inst_ffstark_popgain = FFStarkShift_Experiment_wPPD(path="FFStarkShift_wPPD", cfg=config,soc=soc,soccfg=soccfg,
                                            outerFolder = outerFolder, progress = True)
sweep_key = 'pop_pulse_gain'
sweep_values = np.linspace(0,5000, 31, dtype = int)
data_ffstark_popgain = inst_ffstark_popgain.acquire_2d(sweep_key=sweep_key, sweep_values=sweep_values)
inst_ffstark_popgain.save_data(data_ffstark_popgain)
inst_ffstark_popgain.save_config()

#%%
# TITLE : Sweeping flux

from tqdm import tqdm
import sys

outerFolder = "Z:\\TantalumFluxonium\\Data\\2026_03_31_cooldown\\HouckCage_dev\\Bath_Characterization\\Sweep_11April_2143\\"
FF_sweep = np.linspace(364, -3000,  117)
# add a point at zero to the beginning
FF_sweep = np.insert(FF_sweep, 0, 0)

pop_pulse_gain = 2000
pop_pulse_gain2 = 500
pop_pulse_gain3 = 1000
drift_tol = 12

def freq_predictor(ff_dac_val, curr_freq = 2765):
    return 0.871*ff_dac_val + curr_freq

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # [us]
    "read_pulse_gain": 2500,  # 5600,  # [DAC units]
    "read_pulse_freq": 6826.943,  # [MHz]

    # Qubit Tone
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 2765,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq" : 2765,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 20,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 30000,  # [DAC units]
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # General parameters
    "reps": 25000,
    "cen_num": 2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage": -0.6225,
    "yokoVoltage_freqPoint": -0.6225,
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "use_switch": False,
    "ro_mode_periodic": False,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    "qubit_spec_buffer": 10,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
    "pre_meas_delay": 4,
}

config = BaseConfig | UpdateConfig

UpdateConfig_spec_noff = {
    # Qubit spec parameters
    "qubit_freq_start": 2665,        # [MHz]
    "qubit_freq_stop": 2865,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    "qubit_freq_expts": 101,  # number of points
    "qubit_gain": 10000,            # [DAC units]
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": 0,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 6,

    "relax_delay": 10,               # [us]
    "reps": 1000,
    'dt_pulseplay': 1,
}
config_spec_noff = config | UpdateConfig_spec_noff

UpdateConfig_spec_ff_beg = {
    # Qubit spec parameters
    "qubit_gain": 10000,  # [DAC units]
    "qubit_freq_start": 2665,        # [MHz]
    "qubit_freq_stop": 2865,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    "qubit_freq_expts": 101,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 6,

    "relax_delay": 10,               # [us]
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
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

    # Number of cycle repetitions sweep parameters
    "cycle_number_expts": 11,  # [int] How many different values for number of cycles around to use in this experiment
    "max_cycle_number": 100,  # [int] What is the largest number of cycles to use in sweep? Smallest value always 1
    "cycle_delay": 0.2,  # [us] How long to wait between cycles in one experiment?

    # General parameters
    "sweep_type": 'cycle_number',  # [str] What to sweep? 'ramp_length', 'ff_gain', 'cycle_number'
    "reps": 30000,
    "sets": 5,
    "angle": None,  # [radians] Angle of rotation for readout
    "threshold": None,  # [DAC units] Threshold between g and e
    "confidence": 0.98,
    "plot_all_points": False,
    "plot_all_lengths": False,
    "verbose": False,
    "relax_delay": 100,               # [us]
    "cen_num": 2,
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
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

    # Experiment parameters
    "relax_delay_1": 20,  # Relax delay after the first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout
    "wait_start": 2,
    "wait_stop": 2000,
    "wait_num":  31,
    "wait_type": 'log',

    # General parameters
    "reps": 10000,
    "cen_num":2,
    "initialize_pulse": True,
    "fridge_temp": 7,
    "yokoVoltage_freqPoint": -1.3439,
    "pre_meas_delay": 6,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
    "auto_dt_pulseplay": True,
}

config_t1 = config | UpdateConfig_t1

UpdateConfig_spec_ff_end = {
    # Qubit spec parameters
    "qubit_freq_start": 2665,        # [MHz]
    "qubit_freq_stop": 2865,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse = 5*T1
    "qubit_freq_expts": 101,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse 5*t1 + 10
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 6,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    "relax_delay": 20,               # [us]
    "reps": 2000,
    'dt_pulseplay': 2,              # This should be proportional to the qubit spec delay definitions. Setting it to 5*T1/1000
}
config_spec_ff_end = config | UpdateConfig_spec_ff_end

UpdateConfig_spec_post_ff = {
    # Qubit spec parameters
    "qubit_freq_start": 2665,        # [MHz]
    "qubit_freq_stop": 2865,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse = 5*T1 + 10
    "qubit_freq_expts": 101,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -10000,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse 5*t1
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 6,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,

    "relax_delay": 20,               # [us]
    "reps": 1000,
    'dt_pulseplay': 2,              # This should be proportional to the qubit spec delay definitions. Setting it to 5*T1/1000
}
config_spec_post_ff = config | UpdateConfig_spec_post_ff
#
# UpdateConfig_spec_post_zeroing = {
#     # Qubit spec parameters
#     "qubit_freq_start": 870,  # [MHz]
#     "qubit_freq_stop": 1070,  # [MHz]
#     "qubit_spec_delay": 10,  # [us] Delay before qubit pulse = 5*T1 + 10
#     "qubit_freq_expts": 51,  # number of points
#     "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)
#
#     # Fast flux pulse parameters
#     "ff_gain": -10000,  # [DAC units] Gain for fast flux pulse
#     "ff_length": 20,  # [us] Total length of positive fast flux pulse 5*t1
#     "pre_ff_delay": 0,  # [us] Delay before the fast flux pulse
#     "ff_pulse_style": "ramp",
#     "ff_ramp_length": 0.02,
#     "ff_ch": 6,  # RFSOC output channel of fast flux drive
#     "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
#     "pre_meas_delay": 6,
#
#     "relax_delay": 20,  # [us]
#     "pulse_pre_dist": True,
#     "zeroing_pulse": True,
#     "reps": 1000,
#     'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions. Setting it to 5*T1/1000
# }
# config_spec_post_zeroing = config | UpdateConfig_spec_post_zeroing

UpdateConfig_ss = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 1125,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain
    "qubit_ge_freq": 2765,

    # Ramp sweep parameters
    "relax_delay_1": 20,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout

    # General parameters
    "reps": 20000,
    "cen_num":2,
    "initialize_pulse": True,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    "pre_meas_delay": 4,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
}
config_ss = config | UpdateConfig_ss

UpdateConfig_transmission = {
    # Readout section
    "read_pulse_freq": 6826.78,  # [MHz]
    "read_pulse_gain": 1000,
    "TransSpan": 2,
    "TransNumPoints": 601,

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

   # General Parameters
    "relax_delay": 20,  # [us] Relax delay after second readouts
    "reps": 1000,
    "cen_num": 2,
    "pre_meas_delay": 6,
    "post_meas_delay" : 5,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    'dt_pulseplay': 1,  # This should be proportional to the qubit spec delay definitions
}

config_transmission = config | UpdateConfig_transmission

# UpdateConfig_stark = {
#
#     # Fast flux pulse parameters
#     "ff_ramp_style": "linear",  # one of ["linear"]
#     "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
#     "ff_ramp_stop": 4000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
#     "ff_hold": 20,  # [us] Delay between fast flux ramps
#     "ff_ch": 6,  # RFSOC output channel of fast flux drive
#     "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
#     "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain
#
#     # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
#     "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
#     "qubit_freq": 2620,  # [MHz] Frequency of qubit pulse
#     "sigma": 0.5,
#     "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
#     "qubit_length": 3,  # [us], used with "const"
#     "qubit_gain": 30000,  # [DAC units]
#
#     # Populate Pulse Details
#     "pop_pulse_length": 30,  # [us]
#     "pop_pulse_gain": pop_pulse_gain,  # [DAC units]
#     "pop_pulse_freq": 6826.78,  # [MHz]
#     'pop_relax_delay' : 5,
#
#     # Qubit frequency sweep
#     "qubit_freq_start": 2520,  # [MHz]
#     "qubit_freq_stop": 2620,  # [MHz]
#     "qubit_freq_expts": 51,  # number of points
#
#     # General parameters
#     "relax_delay_2": 50,  # [us] Relax delay after second readout
#     "reps": 3000,
#     "pulse_pre_dist": False,
#     'dt_pulseplay': 0.5,  # This should be proportional to the qubit spec delay definitions
#     "zeroing_pulse": False,
#     'dt_pulsedef': 0.01,
#     "zeroing_a_max": 30000,
#     "pre_meas_delay": 6,
# }
# config_stark = config | UpdateConfig_stark


UpdateConfig_popnprobe = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -25000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 1000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.2,  # [us] Half-length of ramp to use when sweeping gain

    # Populate Pulse Details
    "pop_pulse_length": 30,  # [us]
    "pop_pulse_gain": pop_pulse_gain,  # [DAC units]
    "pop_pulse_freq": 6826.78,  # [MHz]
    'pop_relax_delay': 5,

    # Ramp sweep parameters
    "relax_delay_1": 20,  # Relax delay after first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout

    # General parameters
    "reps": 100000,
    "cen_num":2,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    'dt_pulseplay': 2,  # This should be proportional to the qubit spec delay definitions
    "pre_meas_delay": 6,
}
config_popnprobe = config | UpdateConfig_popnprobe

#%%
qubit_freq_readout_list = []
all_qubit_freqs_readout = []
qubit_freq_ff_beg_list = []
qnd_list = []
fid_list = []
t1_meas_list = []
t1_err_meas_list = []
temp_rate_meas_list = []
g01_rate_list = []
g01_err_rate_list = []
g10_rate_list = []
g10_err_rate_list = []
temp_rate_err_meas_list = []
qubit_freq_ff_end_list  = []
qubit_freq_post_ff_list = []
qubit_freq_post_relax_list = []
pop_meas_list = []
pop_meas_err_list = []
temp_ss_meas_list = []
temp_ss_err_meas_list = []
tranmsission_freq_list = []
stark_shift_list = []
temp_popnprobe_meas_list = []
temp_popnprobe_err_meas_list = []
pop_popnprobe_meas_list = []
pop_popnprobe_err_meas_list = []
temp_popnprobe_meas_list2 = []
temp_popnprobe_err_meas_list2 = []
pop_popnprobe_meas_list2 = []
pop_popnprobe_err_meas_list2 = []
temp_popnprobe_meas_list3 = []
temp_popnprobe_err_meas_list3 = []
pop_popnprobe_meas_list3 = []
pop_popnprobe_err_meas_list3 = []
centers = None
centers_list = []

#%%
print("========== STARTING EXPERIMENTS =============")
for i in tqdm(range(FF_sweep.size)):
    qubit_is_not_steady = True
    max_iterations = 5
    curr_iterations = 0
    while qubit_is_not_steady :

        if curr_iterations > max_iterations:
            sys.exit("Qubit is not steady after maximum iterations. Ending experiment.")

        if curr_iterations > 0:
            # Make sure all the data collecting lists are of size i+1 before appending new data in the next iteration and remove the last element which is from the previous failed iteration
            qubit_freq_readout_list = qubit_freq_readout_list[:i]
            qubit_freq_ff_beg_list = qubit_freq_ff_beg_list[:i]
            qnd_list = qnd_list[:i]
            fid_list = fid_list[:i]
            t1_meas_list = t1_meas_list[:i]
            t1_err_meas_list = t1_err_meas_list[:i]
            temp_rate_meas_list = temp_rate_meas_list[:i]
            g01_rate_list = g01_rate_list[:i]
            g01_err_rate_list = g01_err_rate_list[:i]
            g10_rate_list = g10_rate_list[:i]
            g10_err_rate_list = g10_err_rate_list[:i]
            temp_rate_err_meas_list = temp_rate_err_meas_list[:i]
            qubit_freq_ff_end_list = qubit_freq_ff_end_list[:i]
            qubit_freq_post_ff_list = qubit_freq_post_ff_list[:i]
            pop_meas_list = pop_meas_list[:i]
            pop_meas_err_list = pop_meas_err_list[:i]
            temp_ss_meas_list = temp_ss_meas_list[:i]
            temp_ss_err_meas_list = temp_ss_err_meas_list[:i]
            tranmsission_freq_list = tranmsission_freq_list[:i]
            stark_shift_list = stark_shift_list[:i]
            temp_popnprobe_meas_list = temp_popnprobe_meas_list[:i]
            temp_popnprobe_err_meas_list = temp_popnprobe_err_meas_list[:i]
            pop_popnprobe_meas_list = pop_popnprobe_meas_list[:i]
            pop_popnprobe_err_meas_list = pop_popnprobe_err_meas_list[:i]
            temp_popnprobe_meas_list2 = temp_popnprobe_meas_list2[:i]
            temp_popnprobe_err_meas_list2 = temp_popnprobe_err_meas_list2[:i]
            pop_popnprobe_meas_list2 = pop_popnprobe_meas_list2[:i]
            pop_popnprobe_err_meas_list2 = pop_popnprobe_err_meas_list2[:i]
            temp_popnprobe_meas_list3 = temp_popnprobe_meas_list3[:i]
            temp_popnprobe_err_meas_list3 = temp_popnprobe_err_meas_list3[:i]
            pop_popnprobe_meas_list3 = pop_popnprobe_meas_list3[:i]
            pop_popnprobe_err_meas_list3 = pop_popnprobe_err_meas_list3[:i]
            centers_list = centers_list[:i]

        print(f"----- Starting experiments for FF DAC value {FF_sweep[i]} -----")
        config_transmission = config | UpdateConfig_transmission
        # Update the DAC value in all three experiments
        config_spec_ff_beg['ff_gain'] = FF_sweep[i]
        config_ff_fid['ff_ramp_stop'] = FF_sweep[i]
        config_t1['ff_ramp_stop'] = FF_sweep[i]
        config_spec_ff_end['ff_gain'] = FF_sweep[i]
        config_spec_post_ff['ff_gain'] = FF_sweep[i]
        # config_spec_post_zeroing['ff_gain'] = FF_sweep[i]
        config_ss['ff_ramp_stop'] = FF_sweep[i]
        config_transmission['ff_ramp_stop'] = FF_sweep[i]
        # config_stark['ff_ramp_stop'] = FF_sweep[i]
        config_popnprobe['ff_ramp_stop'] = FF_sweep[i]

        # Create a new directory
        outerFolderDac = outerFolder + "dac_" + str(FF_sweep[i]) + "\\"

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
        all_qubit_freqs_readout.append(qubit_freq)

        # Update the qubit frequency in other config
        config_ff_fid['qubit_freq'] = qubit_freq
        config_t1['qubit_freq'] = qubit_freq
        config_ss['qubit_freq'] = qubit_freq
        config_popnprobe['qubit_freq'] = qubit_freq


        # Using the freq predictor update the span of the frequency for the spec slice
        qubit_ge_freq = freq_predictor(FF_sweep[i], curr_freq = qubit_freq)
        print(f"Qubit's predicted frequency is {qubit_ge_freq}")
        config_spec_ff_beg['qubit_freq_start'] = qubit_ge_freq - 100
        config_spec_ff_beg['qubit_freq_stop'] = qubit_ge_freq + 100
        config_spec_ff_end['qubit_freq_start'] = qubit_ge_freq - 100
        config_spec_ff_end['qubit_freq_stop'] = qubit_ge_freq + 100
        # config_stark['qubit_freq_start'] = qubit_ge_freq - 60
        # config_stark['qubit_freq_stop'] = qubit_ge_freq + 60

        # Update qubit_ge_freq in other configs
        config_t1['qubit_ge_freq'] = qubit_ge_freq
        config_ss['qubit_ge_freq'] = qubit_ge_freq
        config_popnprobe['qubit_ge_freq'] = qubit_ge_freq

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
        # config_stark['qubit_freq_start'] = qubit_ge_freq - 60
        # config_stark['qubit_freq_stop'] = qubit_ge_freq + 60

        # TITLE : Run the FF fidelity check
        soc.reset_gens()
        Instance_FFRampTest = FFRampTest_Experiment(path="FFRampTest", cfg=config_ff_fid, soc=soc, soccfg=soccfg,
                                                    outerFolder=outerFolderDac, short_directory_names=True)
        # Estimate Time
        try:
            data_FFRampTest = FFRampTest_Experiment.acquire(Instance_FFRampTest, progress=False)
            data_FFRampTest = FFRampTest_Experiment.process(Instance_FFRampTest, data_FFRampTest)
            FFRampTest_Experiment.display(Instance_FFRampTest, data_FFRampTest, plot_disp=False)
            FFRampTest_Experiment.save_data(Instance_FFRampTest, data_FFRampTest['data'])
            FFRampTest_Experiment.save_config(Instance_FFRampTest)
            qnd = data_FFRampTest['data']['fid_list'][0]
            qnd_list.append(qnd)
            fid = data_FFRampTest['data']['popt'][2]
            if fid is not None:
                fid_list.append(fid)
            else:
                fid_list.append(0)
        except Exception:
            print("Pyro traceback:")
            print("".join(Pyro4.util.getPyroTraceback()))
        plt.close('all')

        # TITLE : Run the spec slice without fast flux to get the qubit frequency
        soc.reset_gens()
        inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
                                                     outerFolder=outerFolderDac, short_directory_names=True)
        data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        inst_spec_noff.save_data(data_FFSpecSlice)
        inst_spec_noff.save_config()

        # Get the qubit frequency
        qubit_freq1 = inst_spec_noff.qubit_peak_freq
        all_qubit_freqs_readout.append(qubit_freq1)
        if abs(qubit_freq - qubit_freq1) > drift_tol:
            curr_iterations += 1
            print(f"Warning: Qubit frequency changed significantly before T1 experiment. Initial: {qubit_freq} MHz, Current: {qubit_freq1} MHz")
            # Start the loop again without running the rest of the experiments
            continue



        # TITLE : Run T1
        soc.reset_gens()
        inst_ff_t1 = FF_T1_wPulsePreDist(path="FF_T1_PS_wPPD", cfg=config_t1, soc=soc, soccfg=soccfg,
                                         outerFolder=outerFolderDac)
        try:
            inst_ff_t1.acquire(plot_predist=False)
        except Exception:
            print("Pyro traceback:")
            print("".join(Pyro4.util.getPyroTraceback()))
        data_ff_t1 = inst_ff_t1.process_data(centers = centers)
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
        if i == 0:
            g = np.array([data_ff_t1['data']['g01'], data_ff_t1['data']['g10']])
            err = np.array([data_ff_t1['data']['err01'], data_ff_t1['data']['err10']])
            sort_index = np.argsort(g)
            g = g[sort_index]
            err = err[sort_index]
            g01_rate_list.append(g[1])
            g01_err_rate_list.append(err[1])
            g10_rate_list.append(g[0])
            g10_err_rate_list.append(err[0])
        else:
            g01_rate_list.append(data_ff_t1['data']['g01'])
            g01_err_rate_list.append(data_ff_t1['data']['err01'])
            g10_rate_list.append(data_ff_t1['data']['g10'])
            g10_err_rate_list.append(data_ff_t1['data']['err10'])

        # TITLE : Run the spec slice without fast flux to get the qubit frequency
        soc.reset_gens()
        inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
                                                     outerFolder=outerFolderDac, short_directory_names=True)
        data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        inst_spec_noff.save_data(data_FFSpecSlice)
        inst_spec_noff.save_config()

        # Get the qubit frequency
        qubit_freq2 = inst_spec_noff.qubit_peak_freq
        all_qubit_freqs_readout.append(qubit_freq2)

        if abs(qubit_freq - qubit_freq2) > drift_tol:
            curr_iterations += 1
            print(f"Warning: Qubit frequency changed significantly during T1 measurement. Initial: {qubit_freq} MHz, Current: {qubit_freq2} MHz")
            # Start the loop again without running the rest of the experiments
            continue
        #
        #
        # if i%5 == 0:
        #     # TITLE : Run spec slice at end of fast flux pulse
        #     soc.reset_gens()
        #     # Updating the length based on t1
        #     config_spec_ff_end['dt_pulseplay'] = max(1, int((5*t1 + 10)/1000))
        #     config_spec_ff_end['ff_length'] = 5*t1 + 10
        #     config_spec_ff_end['qubit_spec_delay'] = 5*t1
        #     inst_spec_ff_end = FFSpecSlice_Experiment_wPPD(path="Spec_FF_end", cfg=config_spec_ff_end, soc=soc, soccfg=soccfg,
        #                                                  outerFolder=outerFolderDac, short_directory_names=True)
        #     data_FFSpecSlice = inst_spec_ff_end.acquire(progress=False)
        #     inst_spec_ff_end.display(data_FFSpecSlice, plot_disp=False)
        #     inst_spec_ff_end.save_data(data_FFSpecSlice)
        #     inst_spec_ff_end.save_config()
        #     qubit_freq_ff_end_list.append(inst_spec_ff_end.qubit_peak_freq)
        # else:
        #     qubit_freq_ff_end_list.append(qubit_ge_freq)
        #
        # # TITLE : Run spec slice after the fast flux pulse
        # if i%5 == 0:
        #     soc.reset_gens()
        #     # Updating the length based on t1
        #     config_spec_post_ff['dt_pulseplay'] = max(1, int((5*t1 + 30)/1000))
        #     config_spec_post_ff['ff_length'] = 5*t1
        #     config_spec_post_ff['qubit_spec_delay'] = 5*t1 + 30
        #     inst_spec_post_ff = FFSpecSlice_Experiment_wPPD(path="Spec_post_FF", cfg=config_spec_post_ff, soc=soc, soccfg=soccfg,
        #                                                     outerFolder=outerFolderDac, short_directory_names=True)
        #     data_FFSpecSlice = inst_spec_post_ff.acquire(progress=False)
        #     inst_spec_post_ff.display(data_FFSpecSlice, plot_disp=False)
        #     inst_spec_post_ff.save_data(data_FFSpecSlice)
        #     inst_spec_post_ff.save_config()
        #     qubit_freq_post_ff_list.append(inst_spec_post_ff.qubit_peak_freq)
        # else:
        #     qubit_freq_post_ff_list.append(qubit_freq)

        # # TITLE : Run Spec slice after the relax delay
        # if i%5 == 0:
        #     soc.reset_gens()
        #     # Updating the length based on t1
        #     config_spec_post_zeroing['ff_length'] = 5*t1
        #     config_spec_post_zeroing['dt_pulseplay'] = max(1, int((5*t1 + config_spec_post_ff['relax_delay'])/1000))
        #     inst_spec_post_relax = FFSpecSlice_Experiment_wPPD_studyzeroing(path="Spec_post_zeroing", cfg=config_spec_post_zeroing, soc=soc, soccfg=soccfg,
        #                                                     outerFolder=outerFolderDac, short_directory_names=True)
        #     data_FFSpecSlice = inst_spec_post_relax.acquire(progress=False)
        #     inst_spec_post_relax.display(data_FFSpecSlice, plot_disp=False)
        #     inst_spec_post_relax.save_data(data_FFSpecSlice)
        #     inst_spec_post_relax.save_config()
        #     qubit_freq_post_relax_list.append(inst_spec_post_relax.qubit_peak_freq)
        # else:
        #     qubit_freq_post_relax_list.append(qubit_freq)

        # # TITLE : Run the spec slice without fast flux to get the qubit frequency
        # soc.reset_gens()
        # inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
        #                                              outerFolder=outerFolderDac, short_directory_names=True)
        # data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        # inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        # inst_spec_noff.save_data(data_FFSpecSlice)
        # inst_spec_noff.save_config()
        #
        # # Get the qubit frequency
        # qubit_freq3 = inst_spec_noff.qubit_peak_freq
        # all_qubit_freqs_readout.append(qubit_freq3)
        # if abs(qubit_freq - qubit_freq3) > drift_tol:
        #     curr_iterations += 1
        #     print(f"Warning: Qubit frequency changed significantly at before SingleShot. Initial: {qubit_freq} MHz, Current: {qubit_freq3} MHz")
        #     # Start the loop again without running the rest of the experiments
        #     continue
        #
        #
        # TITLE : Run Single Shot
        soc.reset_gens()
        # Updating the ff_hold based on t1
        config_ss['ff_hold'] = 5 * t1
        config_ss['dt_pulseplay'] = max(1, int((5*t1)/1000))
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

        # TITLE : Run the spec slice without fast flux to get the qubit frequency
        soc.reset_gens()
        inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
                                                     outerFolder=outerFolderDac, short_directory_names=True)
        data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        inst_spec_noff.save_data(data_FFSpecSlice)
        inst_spec_noff.save_config()

        # Get the qubit frequency
        qubit_freq4 = inst_spec_noff.qubit_peak_freq
        all_qubit_freqs_readout.append(qubit_freq4)
        if abs(qubit_freq - qubit_freq4) > drift_tol:
            curr_iterations += 1
            print(f"Warning: Qubit frequency changed significantly at after SingleShot. Initial: {qubit_freq} MHz, Current: {qubit_freq4} MHz")
            # Start the loop again without running the rest of the experiments
            continue


        # # TITLE : Running Transmission
        # soc.reset_gens()
        # inst_ff_trans = FFTransmission(path="FF_Transmission", cfg=config_transmission, soc=soc, soccfg=soccfg,
        #                                outerFolder=outerFolderDac)
        # try:
        #     data_ff_trans = inst_ff_trans.acquire()
        # except Exception:
        #     print("Pyro traceback:")
        #     print("".join(Pyro4.util.getPyroTraceback()))
        # inst_ff_trans.display(data=data_ff_trans, plotDisp=False)
        # inst_ff_trans.save_data(data_ff_trans)
        # inst_ff_trans.save_config()
        # trans_peak = inst_ff_trans.peakFreq
        # print(f"The populating frequency is set to {trans_peak} MHz")
        # config_popnprobe['pop_pulse_freq'] = trans_peak
        # # config_stark['pop_pulse_freq'] = trans_peak
        #
        # # Updating the lists
        # tranmsission_freq_list.append(inst_ff_trans.peakFreq)
        #
        # # # TITLE : Running stark shift
        # # soc.reset_gens()
        # # qubit_freq_starks = []
        # # # Get the stark shift without pop_pulse_gain
        # # config_stark['pop_pulse_gain'] = 0
        # # inst_ffstark = FFStarkShift_Experiment_wPPD(path="FFStarkShift_wPPD", cfg=config_stark, soc=soc, soccfg=soccfg,
        # #                                             outerFolder=outerFolderDac, progress=False)
        # # data_ffstark = inst_ffstark.acquire(progress=False, plot_debug=False)
        # # inst_ffstark.display(data_ffstark, plot_disp=False)
        # # inst_ffstark.save_data(data_ffstark)
        # # inst_ffstark.save_config()
        # # qubit_freq_0 = inst_ffstark.qubit_peak_freq
        # # # Get the stark shift with pop_pulse_gain/4
        # # config_stark['pop_pulse_gain'] = int(pop_pulse_gain / 4)
        # # inst_ffstark = FFStarkShift_Experiment_wPPD(path="FFStarkShift_wPPD", cfg=config_stark, soc=soc, soccfg=soccfg,
        # #                                             outerFolder=outerFolderDac, progress=False)
        # # data_ffstark = inst_ffstark.acquire(progress=False, plot_debug=False)
        # # inst_ffstark.display(data_ffstark, plot_disp=False)
        # # inst_ffstark.save_data(data_ffstark)
        # # inst_ffstark.save_config()
        # # qubit_freq_starks.append(inst_ffstark.qubit_peak_freq - qubit_freq_0)
        # # # Get the stark shift with pop_pulse_gain/2
        # # config_stark['pop_pulse_gain'] = int(pop_pulse_gain/2)
        # # inst_ffstark = FFStarkShift_Experiment_wPPD(path="FFStarkShift_wPPD", cfg=config_stark, soc=soc, soccfg=soccfg,
        # #                                             outerFolder=outerFolderDac, progress=False)
        # # data_ffstark = inst_ffstark.acquire(progress=False, plot_debug=False)
        # # inst_ffstark.display(data_ffstark, plot_disp=False)
        # # inst_ffstark.save_data(data_ffstark)
        # # inst_ffstark.save_config()
        # # qubit_freq_starks.append(inst_ffstark.qubit_peak_freq - qubit_freq_0)
        # # # Get the stark shift with 3*pop_pulse_gain/4
        # # config_stark['pop_pulse_gain'] = int(3*pop_pulse_gain/4)
        # # inst_ffstark = FFStarkShift_Experiment_wPPD(path="FFStarkShift_wPPD", cfg=config_stark, soc=soc, soccfg=soccfg,
        # #                                             outerFolder=outerFolderDac, progress=False)
        # # data_ffstark = inst_ffstark.acquire(progress=False, plot_debug=False)
        # # inst_ffstark.display(data_ffstark, plot_disp=False)
        # # inst_ffstark.save_data(data_ffstark)
        # # inst_ffstark.save_config()
        # # qubit_freq_starks.append(inst_ffstark.qubit_peak_freq - qubit_freq_0)
        # #
        # # # Get the stark shift with pop_pulse_gain
        # # config_stark['pop_pulse_gain'] = pop_pulse_gain
        # # inst_ffstark = FFStarkShift_Experiment_wPPD(path="FFStarkShift_wPPD", cfg=config_stark, soc=soc, soccfg=soccfg,
        # #                                             outerFolder=outerFolderDac, progress=False)
        # # data_ffstark = inst_ffstark.acquire(progress=False, plot_debug=False)
        # # inst_ffstark.display(data_ffstark, plot_disp=False)
        # # inst_ffstark.save_data(data_ffstark)
        # # inst_ffstark.save_config()
        # # qubit_freq_starks.append(inst_ffstark.qubit_peak_freq - qubit_freq_0)
        # #
        # # # Fit qubit_freq_starks vs pop_pulse_gain points to a parabola y = a*x^2 and get the a
        # # from scipy.optimize import curve_fit
        # # def parabola(x, a):
        # #     return a * x**2
        # # pop_gains = np.array([ pop_pulse_gain/4, pop_pulse_gain/2, 3*pop_pulse_gain/4, pop_pulse_gain])
        # # qubit_freq_starks = np.array(qubit_freq_starks)
        # # try:
        # #     popt, pcov = curve_fit(parabola, pop_gains, qubit_freq_starks)
        # #     a = popt[0]
        # #     print(f"Fitted parabola coefficient a: {a}")
        # #     stark_shift_list.append(a)
        # # except Exception as e:
        # #     print(f"Error in curve fitting: {e}")
        # #     stark_shift_list.append(0)
        #
        # # # TITLE : Run the spec slice without fast flux to get the qubit frequency
        # # soc.reset_gens()
        # # inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
        # #                                              outerFolder=outerFolderDac, short_directory_names=True)
        # # data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        # # inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        # # inst_spec_noff.save_data(data_FFSpecSlice)
        # # inst_spec_noff.save_config()
        # #
        # # # Get the qubit frequency
        # # qubit_freq5 = inst_spec_noff.qubit_peak_freq
        # # all_qubit_freqs_readout.append(qubit_freq5)
        # # if abs(qubit_freq - qubit_freq5) > drift_tol:
        # #     curr_iterations += 1
        # #     print(f"Warning: Qubit frequency changed significantly at after StarkShift and Transmission. Initial: {qubit_freq} MHz, Current: {qubit_freq5} MHz")
        # #     # Start the loop again without running the rest of the experiments
        # #     continue
        #
        #
        # # TITLE : Running Populate Probe Experiment
        # soc.reset_gens()
        # config_popnprobe['pop_pulse_gain'] = pop_pulse_gain
        # config_popnprobe['ff_hold'] = 5 * t1
        # config_popnprobe['dt_pulseplay'] = max(1, int((5 * t1) / 1000))
        # print(f"Setting ff_hold to {config_popnprobe['ff_hold']} us and dt_pulseplay to {config_popnprobe['dt_pulseplay']} us")
        # inst_FFPopulateProbe = FFPopulateProbe(path="FFPopulateProbe", cfg=config_popnprobe, soc=soc, soccfg=soccfg,
        #                                        outerFolder=outerFolderDac, progress=False)
        # try:
        #     inst_FFPopulateProbe.acquire()
        # except Exception:
        #     print("Pyro traceback:")
        #     print("".join(Pyro4.util.getPyroTraceback()))
        # data_ffpopprob = inst_FFPopulateProbe.process(centers=centers)
        # inst_FFPopulateProbe.save_data(data_ffpopprob)
        # inst_FFPopulateProbe.save_config()
        # print(f"Temperature is {data_ffpopprob['data']['mean_temp'][1, 0]} mK")
        #
        # # Updating the lists
        # pop_popnprobe_meas_list.append(data_ffpopprob['data']['mean_pop'])
        # pop_popnprobe_err_meas_list.append(data_ffpopprob['data']['std_pop'])
        # temp_popnprobe_meas_list.append(data_ffpopprob['data']['mean_temp'][1, 0])
        # temp_popnprobe_err_meas_list.append(data_ffpopprob['data']['std_temp'][1, 0])
        #
        # # TITLE : Run the spec slice without fast flux to get the qubit frequency
        # soc.reset_gens()
        # inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
        #                                              outerFolder=outerFolderDac, short_directory_names=True)
        # data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        # inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        # inst_spec_noff.save_data(data_FFSpecSlice)
        # inst_spec_noff.save_config()
        #
        # # Get the qubit frequency
        # qubit_freq6 = inst_spec_noff.qubit_peak_freq
        # all_qubit_freqs_readout.append(qubit_freq6)
        # if abs(qubit_freq - qubit_freq6) > drift_tol:
        #     curr_iterations += 1
        #     print(
        #         f"Warning: Qubit frequency changed significantly at after PopnProbe1. Initial: {qubit_freq} MHz, Current: {qubit_freq6} MHz")
        #     # Start the loop again without running the rest of the experiments
        #     continue
        #
        # # TITLE : Running Populate Probe Experiment 2
        # soc.reset_gens()
        # config_popnprobe['pop_pulse_gain'] = pop_pulse_gain2
        # print(f"Setting ff_hold to {config_popnprobe['ff_hold']} us and dt_pulseplay to {config_popnprobe['dt_pulseplay']} us")
        # inst_FFPopulateProbe = FFPopulateProbe(path="FFPopulateProbe2", cfg=config_popnprobe, soc=soc, soccfg=soccfg,
        #                                        outerFolder=outerFolderDac, progress=False)
        # try:
        #     inst_FFPopulateProbe.acquire()
        # except Exception:
        #     print("Pyro traceback:")
        #     print("".join(Pyro4.util.getPyroTraceback()))
        # data_ffpopprob = inst_FFPopulateProbe.process(centers=centers)
        # inst_FFPopulateProbe.save_data(data_ffpopprob)
        # inst_FFPopulateProbe.save_config()
        # print(f"Temperature is {data_ffpopprob['data']['mean_temp'][1, 0]} mK")
        #
        # # Updating the lists
        # pop_popnprobe_meas_list2.append(data_ffpopprob['data']['mean_pop'])
        # pop_popnprobe_err_meas_list2.append(data_ffpopprob['data']['std_pop'])
        # temp_popnprobe_meas_list2.append(data_ffpopprob['data']['mean_temp'][1, 0])
        # temp_popnprobe_err_meas_list2.append(data_ffpopprob['data']['std_temp'][1, 0])
        #
        # # TITLE : Run the spec slice without fast flux to get the qubit frequency
        # soc.reset_gens()
        # inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
        #                                              outerFolder=outerFolderDac, short_directory_names=True)
        # data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        # inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        # inst_spec_noff.save_data(data_FFSpecSlice)
        # inst_spec_noff.save_config()
        #
        # # Get the qubit frequency
        # qubit_freq7 = inst_spec_noff.qubit_peak_freq
        # all_qubit_freqs_readout.append(qubit_freq7)
        # if abs(qubit_freq - qubit_freq7) > drift_tol:
        #     curr_iterations += 1
        #     print(
        #         f"Warning: Qubit frequency changed significantly at after PopnProbe2. Initial: {qubit_freq} MHz, Current: {qubit_freq7} MHz")
        #     # Start the loop again without running the rest of the experiments
        #     continue
        #
        # # TITLE : Running Populate Probe Experiment 3
        # soc.reset_gens()
        # config_popnprobe['pop_pulse_gain'] = pop_pulse_gain3
        # print(f"Setting ff_hold to {config_popnprobe['ff_hold']} us and dt_pulseplay to {config_popnprobe['dt_pulseplay']} us")
        # inst_FFPopulateProbe = FFPopulateProbe(path="FFPopulateProbe3", cfg=config_popnprobe, soc=soc, soccfg=soccfg,
        #                                        outerFolder=outerFolderDac, progress=False)
        # try:
        #     inst_FFPopulateProbe.acquire()
        # except Exception:
        #     print("Pyro traceback:")
        #     print("".join(Pyro4.util.getPyroTraceback()))
        # data_ffpopprob = inst_FFPopulateProbe.process(centers=centers)
        # inst_FFPopulateProbe.save_data(data_ffpopprob)
        # inst_FFPopulateProbe.save_config()
        # print(f"Temperature is {data_ffpopprob['data']['mean_temp'][1, 0]} mK")
        #
        # # Updating the lists
        # pop_popnprobe_meas_list3.append(data_ffpopprob['data']['mean_pop'])
        # pop_popnprobe_err_meas_list3.append(data_ffpopprob['data']['std_pop'])
        # temp_popnprobe_meas_list3.append(data_ffpopprob['data']['mean_temp'][1, 0])
        # temp_popnprobe_err_meas_list3.append(data_ffpopprob['data']['std_temp'][1, 0])
        #
        # # TITLE : Run the spec slice without fast flux to get the qubit frequency
        # soc.reset_gens()
        # inst_spec_noff = FFSpecSlice_Experiment_wPPD(path="Spec_noFF", cfg=config_spec_noff, soc=soc, soccfg=soccfg,
        #                                              outerFolder=outerFolderDac, short_directory_names=True)
        # data_FFSpecSlice = inst_spec_noff.acquire(progress=False)
        # inst_spec_noff.display(data_FFSpecSlice, plot_disp=False)
        # inst_spec_noff.save_data(data_FFSpecSlice)
        # inst_spec_noff.save_config()
        #
        # # Get the qubit frequency
        # qubit_freq8 = inst_spec_noff.qubit_peak_freq
        # all_qubit_freqs_readout.append(qubit_freq8)
        # if abs(qubit_freq - qubit_freq8) > drift_tol:
        #     curr_iterations += 1
        #     print(
        #         f"Warning: Qubit frequency changed significantly at after PopnProbe3. Initial: {qubit_freq} MHz, Current: {qubit_freq8} MHz")
        #     # Start the loop again without running the rest of the experiments
        #     continue

        # THe qubit has been steady
        qubit_is_not_steady = False

#%%
index_max = None
# Saving all the lists
collated_data = {
    "FF_sweep": FF_sweep[:index_max],
    "qubit_freq_readout_list": qubit_freq_readout_list[:index_max],
    "qubit_freq_ff_beg_list": qubit_freq_ff_beg_list[:index_max],
    "qnd_list": qnd_list[:index_max],
    "fid_list": fid_list[:index_max],
    "t1_meas_list": t1_meas_list[:index_max],
    "t1_err_meas_list": t1_err_meas_list[:index_max],
    "temp_rate_meas_list": temp_rate_meas_list[:index_max],
    "temp_rate_err_meas_list": temp_rate_err_meas_list[:index_max],
    "g01_rate_list": g01_rate_list[:index_max],
    "g01_err_rate_list": g01_err_rate_list[:index_max],
    "g10_rate_list": g10_rate_list[:index_max],
    "g10_err_rate_list": g10_err_rate_list[:index_max],
    "qubit_freq_ff_end_list": qubit_freq_ff_end_list[:index_max],
    "qubit_freq_post_ff_list": qubit_freq_post_ff_list[:index_max],
    "qubit_freq_post_relax_list": qubit_freq_post_relax_list[:index_max],
    "pop_meas_list": pop_meas_list[:index_max],
    "pop_meas_err_list": pop_meas_err_list[:index_max],
    "temp_ss_meas_list": temp_ss_meas_list[:index_max],
    "temp_ss_err_meas_list": temp_ss_err_meas_list[:index_max],
    "tranmsission_freq_list": tranmsission_freq_list[:index_max],
    "stark_shift_list": stark_shift_list[:index_max],
    "temp_popnprobe_meas_list": temp_popnprobe_meas_list[:index_max],
    "temp_popnprobe_err_meas_list": temp_popnprobe_err_meas_list[:index_max],
    "pop_popnprobe_meas_list": pop_popnprobe_meas_list[:index_max],
    "pop_popnprobe_err_meas_list": pop_popnprobe_err_meas_list[:index_max],
    "pop_pulse_gain" : pop_pulse_gain,
    "temp_popnprobe_meas_list2": temp_popnprobe_meas_list2[:index_max],
    "temp_popnprobe_err_meas_list2": temp_popnprobe_err_meas_list2[:index_max],
    "pop_popnprobe_meas_list2": pop_popnprobe_meas_list2[:index_max],
    "pop_popnprobe_err_meas_list2": pop_popnprobe_err_meas_list2[:index_max],
    "pop_pulse_gain2" : pop_pulse_gain2,
    "temp_popnprobe_meas_list3": temp_popnprobe_meas_list3[:index_max],
    "temp_popnprobe_err_meas_list3": temp_popnprobe_err_meas_list3[:index_max],
    "pop_popnprobe_meas_list3": pop_popnprobe_meas_list3[:index_max],
    "pop_popnprobe_err_meas_list3": pop_popnprobe_err_meas_list3[:index_max],
    "pop_pulse_gain3": pop_pulse_gain3,
}

# Save the data using h5
import h5py
def save_collated_h5(collated_data, path="collated_data.h5"):
    with h5py.File(path, "w") as f:
        # Stack the special ones
        # f.create_dataset("pop_meas_list", data=np.stack(collated_data["pop_meas_list"]))
        # f.create_dataset("pop_meas_err_list", data=np.stack(collated_data["pop_meas_err_list"]))
        # f.create_dataset("pop_popnprobe_meas_list", data=np.stack(collated_data["pop_popnprobe_meas_list"]))
        # f.create_dataset("pop_popnprobe_err_meas_list", data=np.stack(collated_data["pop_popnprobe_err_meas_list"]))
        # f.create_dataset("pop_popnprobe_meas_list2", data=np.stack(collated_data["pop_popnprobe_meas_list2"]))
        # f.create_dataset("pop_popnprobe_err_meas_list2", data=np.stack(collated_data["pop_popnprobe_err_meas_list2"]))

        # Everything else straight to dataset
        skip = {"pop_meas_list", "pop_meas_err_list", "pop_popnprobe_meas_list", "pop_popnprobe_err_meas_list","pop_popnprobe_meas_list2", "pop_popnprobe_err_meas_list2"}
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
fid_list = np.array(collated_data["fid_list"])
temp_ss = np.abs(np.array(collated_data["temp_ss_meas_list"]) * 1000)
temp_ss_err = np.array(collated_data["temp_ss_err_meas_list"]) * 1000
temp_rate = np.abs(np.array(collated_data["temp_rate_meas_list"]) * 1000)
temp_rate_err = np.array(collated_data["temp_rate_err_meas_list"]) * 1000
t1 = np.array(collated_data["t1_meas_list"])
t1_err = np.array(collated_data["t1_err_meas_list"])
# pop_meas = np.stack(collated_data["pop_meas_list"])          # shape (N, 2)
# pop_meas_err = np.stack(collated_data["pop_meas_err_list"])  # shape (N, 2)
qubit_freq = np.array(collated_data["qubit_freq_ff_beg_list"])
qubit_freq_readout = np.array(collated_data["qubit_freq_readout_list"])
# qubit_freq_ff_end = np.array(collated_data["qubit_freq_ff_end_list"])
# qubit_freq_post_ff = np.array(collated_data["qubit_freq_post_ff_list"])
# qubit_freq_post_relax = np.array(collated_data["qubit_freq_post_relax_list"])
# transmission_freq = np.array(collated_data["tranmsission_freq_list"])
# stark_shift = np.array(collated_data["stark_shift_list"])
# pop_popnprobe_meas = np.stack(collated_data["pop_popnprobe_meas_list"])          # shape (N, 2)
# pop_popnprobe_err = np.stack(collated_data["pop_popnprobe_err_meas_list"])  # shape (N, 2)
# temp_popnprobe = np.abs(np.array(collated_data["temp_popnprobe_meas_list"]) * 1000)
# temp_popnprobe_err = np.array(collated_data["temp_popnprobe_err_meas_list"]) * 1000
# pop_popnprobe_meas2 = np.stack(collated_data["pop_popnprobe_meas_list2"])          # shape (N, 2)
# pop_popnprobe_err2 = np.stack(collated_data["pop_popnprobe_err_meas_list2"])  # shape (N, 2)
# temp_popnprobe2 = np.abs(np.array(collated_data["temp_popnprobe_meas_list2"]) * 1000)
# temp_popnprobe_err2 = np.array(collated_data["temp_popnprobe_err_meas_list2"]) * 1000
# pop_popnprobe_meas3 = np.stack(collated_data["pop_popnprobe_meas_list3"])          # shape (N, 2)
# pop_popnprobe_err3 = np.stack(collated_data["pop_popnprobe_err_meas_list3"])  # shape (N, 2)
# temp_popnprobe3 = np.abs(np.array(collated_data["temp_popnprobe_meas_list3"]) * 1000)
# temp_popnprobe_err3 = np.array(collated_data["temp_popnprobe_err_meas_list3"]) * 1000
all_qubit_freqs_readout = np.array(all_qubit_freqs_readout)
#
# # Excited state = the smaller of g/e
# min_pop = np.min(pop_meas, axis=1)
# min_pop_err = np.take_along_axis(pop_meas_err, np.argmin(pop_meas, axis=1)[:, np.newaxis], axis=1).flatten()
# min_popnprobe = np.min(pop_popnprobe_meas, axis=1)
# min_popnprobe_err = np.take_along_axis(pop_popnprobe_err, np.argmin(pop_popnprobe_meas, axis=1)[:, np.newaxis], axis=1).flatten()
#
# # Excited states with fix
# excited_pop = pop_meas[:,0]
# excited_pop_err = pop_meas_err[:,0]
# excited_popnprobe = pop_popnprobe_meas[:,0]
# excited_popnprobe_err = pop_popnprobe_err[:,0]
# excited_popnprobe2 = pop_popnprobe_meas2[:,0]
# excited_popnprobe_err2 = pop_popnprobe_err2[:,0]
# excited_popnprobe3 = pop_popnprobe_meas3[:,0]
# excited_popnprobe_err3 = pop_popnprobe_err3[:,0]
#

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

#-----------------------------
# Plot all qubit freqeuncy readout
#-----------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(all_qubit_freqs_readout, "o-", label="Qubit frequency at readout")
make_pretty(ax, "Measurement Index", "Qubit Frequency at Readout [MHz]")
ax.legend()
save_fig(fig, "all_qubit_freqs_readout")



# -------------------------
# 1. temp_ss vs FF
# -------------------------
# fig, ax = plt.subplots(figsize=(6, 4))
# ax.errorbar(FF_sweep, temp_ss, yerr=temp_ss_err,
#             fmt="o", capsize=3, label="Single shot")
# make_pretty(ax, "FF DAC Value", "Temperature (measured through single shot) [mK]")
# ax.legend()
# save_fig(fig, "temperature_single_shot")

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
# 3.1  Both temperatures vs FF with qubit freq
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(qubit_freq, temp_ss, yerr=temp_ss_err,
            fmt="o", capsize=3, label="Single shot")
ax.errorbar(qubit_freq, temp_rate, yerr=temp_rate_err,
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
# fig, ax = plt.subplots(figsize=(6, 4))
# ax.errorbar(FF_sweep, excited_pop, yerr=excited_pop_err,
#             fmt="^", capsize=3, color="C3", label="Excited state population")
# make_pretty(ax, "FF DAC Value", "Excited State Population")
# ax.legend()
# save_fig(fig, "excited_population_vs_ff")

# -------------------------
# 5.1  Min state population vs FF
# -------------------------
# fig, ax = plt.subplots(figsize=(6, 4))
# ax.errorbar(FF_sweep, min_pop, yerr=min_pop_err,
#             fmt="^", capsize=3, color="C3", label="minimum state population")
# make_pretty(ax, "FF DAC Value", "Minimum State Population")
# ax.legend()
# save_fig(fig, "minimum_population_vs_ff")


# -------------------------
# 6. Qubit frequency vs FF
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, qubit_freq, "o", color="C4", label="Qubit frequency")
make_pretty(ax, "FF DAC Value", "Qubit Frequency [GHz]")
ax.legend()
save_fig(fig, "qubit_frequency_vs_ff")
#%%
# -------------------------
# 7. Transmission frequency vs FF
# -------------------------
# fig, ax = plt.subplots(figsize=(6, 4))
# ax.plot(FF_sweep, transmission_freq, "o", color="C5", label="Transmission peak frequency")
# make_pretty(ax, "FF DAC Value", "Transmission Peak Frequency [GHz]")
# ax.legend()
# save_fig(fig, "transmission_frequency_vs_ff")

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
            fmt="v", capsize=3, label=f"Populate-probe {pop_pulse_gain}")
ax.errorbar(FF_sweep, excited_popnprobe2, yerr=excited_popnprobe_err2,
            fmt="v", capsize=3, label=f"Populate-probe {pop_pulse_gain2}")
ax.errorbar(FF_sweep, excited_popnprobe3, yerr=excited_popnprobe_err3,
            fmt="v", capsize=3, label=f"Populate-probe {pop_pulse_gain3}")
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

# #------------------------
# # CHecking if qubit freq at readout and post relax are the same
# #------------------------
# fig, ax = plt.subplots(figsize=(6, 4))
# ax.plot(FF_sweep, qubit_freq_readout - qubit_freq_post_relax, "o-", label="No FF - Post Relax")
# make_pretty(ax, "FF DAC Value", "Qubit Frequency difference of No FF - Post Relax [MHz]")
# ax.legend()
# save_fig(fig, "qubit_freq_noff_postrelax_difference")

#--------------------------
# Plotting stark shift vs FF
# #-------------------------
# fig, ax = plt.subplots(figsize=(6, 4))
# ax.plot(FF_sweep, stark_shift*pop_pulse_gain**2, "o-", label="Stark Shift")
# make_pretty(ax, "FF DAC Value", "Stark Shift at pop_pulse_gain [MHz]")
# ax.legend()
# save_fig(fig, "stark_shift_vs_ff")

#--------------------------
# Plotting Fidelity vs FF
# #-------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_sweep, np.array(fid_list), "o-", label="Fidelity")
make_pretty(ax, "FF DAC Value", "Fidelity vs FF")
ax.legend()
save_fig(fig, "Fidelity_vs_FF")

plt.show()

#%%
# TITLE : Sweeping MIST Parameters

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 9,  # [us]
    "read_pulse_gain": 5500,  # 5600,  # [DAC units]
    "read_pulse_freq": 7392,  # [MHz]

    # Qubit Tone
    "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
    "qubit_freq": 971,  # [MHz] Frequency of qubit pulse
    "qubit_ge_freq" : 1135.9,
    "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,  # [us], used with "arb" and "flat_top"
    "qubit_length": 3,  # [us], used with "const"
    "flat_top_length": 1,  # [us], used with "flat_top"
    "qubit_gain": 30000,  # [DAC units]
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive

    # General parameters
    "initialize_pulse": True,
    "cen_num": 2,
    "fridge_temp": 7,
    "yokoVoltage": -1.127,
    "yokoVoltage_freqPoint": -1.127,
    "use_switch": False,
    "ro_mode_periodic": False,
    "zeroing_pulse": True,
    "pulse_pre_dist": True,
    "qubit_spec_buffer": 10,
    'dt_pulsedef': 0.01,
    "zeroing_a_max": 30000,
    "pre_meas_delay": 6,
}

UpdateConfig_spec_ff_beg = {
    # Qubit spec parameters
    "qubit_freq_start": 1035,        # [MHz]
    "qubit_freq_stop":  1235,         # [MHz]
    "qubit_spec_delay": 10,          # [us] Delay before qubit pulse
    "qubit_freq_expts": 101,  # number of points
    "qubit_spec_buffer": 10,  # Extra buffer fast flux pulse will be on after the qubit pulse (not more than ff_length)

    # Fast flux pulse parameters
    "ff_gain": -1150,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 20,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.02,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 2,

    "relax_delay": 500,               # [us]
    "reps": 1000,
    'dt_pulseplay': 2,
}

config_spec_ff_beg = BaseConfig | UpdateConfig | UpdateConfig_spec_ff_beg

UpdateConfig_ss = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -1150,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 2000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain
    "qubit_ge_freq": 1135,

    # Ramp sweep parameters
    "relax_delay_1": 5,  # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout

    # General parameters
    "reps": 30000,
    "cen_num":2,
    "initialize_pulse": True,
    "pulse_pre_dist": True,
    'dt_pulseplay': 1,  # This should be proportional to the qubit spec delay definitions
}
config_ss = BaseConfig | UpdateConfig | UpdateConfig_ss


UpdateConfig_popnprobe = {
    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": -1150,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_hold": 2000,  # [us] Delay between fast flux ramps
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.02,  # [us] Half-length of ramp to use when sweeping gain

    # Populate Pulse Details
    "pop_pulse_length": 30,  # [us]
    "pop_pulse_gain": 5000,  # [DAC units]
    "pop_pulse_freq": 7392.23,  # [MHz]
    'pop_relax_delay': 5,

    # Ramp sweep parameters
    "relax_delay_1": 5,  # Relax delay after first readout
    "relax_delay_2": 20,  # [us] Relax delay after second readout

    # General parameters
    "reps": 30000,
    "cen_num":2,
    "pulse_pre_dist": True,
    'dt_pulseplay': 1,  # This should be proportional to the qubit spec delay definitions
}
config_popnprobe = BaseConfig | UpdateConfig | UpdateConfig_popnprobe

#%%
swp_params = "pop_pulse_length"
swp_vals = np.linspace(1, 101, 25, dtype = int)  # [MHz]
qubit_freq_ff_beg_list = []
pop_meas_list = []
pop_meas_err_list = []
temp_ss_meas_list = []
temp_ss_err_meas_list = []
temp_popnprobe_meas_list = []
temp_popnprobe_err_meas_list = []
pop_popnprobe_meas_list = []
pop_popnprobe_err_meas_list = []
centers = None
centers_list = []
outerFolder = r"Z:\\TantalumFluxonium\\Data\\2026_03_31_cooldown\\HouckCage_dev\\MIST_Sweep_Test\\"

#%%
for i in range(swp_vals.size):
    config_popnprobe[swp_params] = swp_vals[i]
    print(f"Setting {swp_params} to {swp_vals[i]} MHz")
    outerFolderDac = outerFolder + f"{swp_params}_{swp_vals[i]:.4f}\\"

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
    config_ss['qubit_ge_freq'] = qubit_ge_freq
    config_popnprobe['qubit_ge_freq'] = qubit_ge_freq


    # TITLE : Run Single Shot
    soc.reset_gens()
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

    # TITLE : Running Populate Probe Experiment
    soc.reset_gens()

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
    centers = data_ffpopprob['data']['centers']
    centers_list.append(centers)
    # Updating the lists
    pop_popnprobe_meas_list.append(data_ffpopprob['data']['mean_pop'])
    pop_popnprobe_err_meas_list.append(data_ffpopprob['data']['std_pop'])
    temp_popnprobe_meas_list.append(data_ffpopprob['data']['mean_temp'][1, 0])
    temp_popnprobe_err_meas_list.append(data_ffpopprob['data']['std_temp'][1, 0])

#%%
# Saving all the lists
collated_data = {
    swp_params: swp_vals,
    "qubit_freq_ff_beg_list": qubit_freq_ff_beg_list,
    "pop_meas_list": pop_meas_list,
    "pop_meas_err_list": pop_meas_err_list,
    "temp_ss_meas_list": temp_ss_meas_list,
    "temp_ss_err_meas_list": temp_ss_err_meas_list,
    "temp_popnprobe_meas_list": temp_popnprobe_meas_list,
    "temp_popnprobe_err_meas_list": temp_popnprobe_err_meas_list,
    "pop_popnprobe_meas_list": pop_popnprobe_meas_list,
    "pop_popnprobe_err_meas_list": pop_popnprobe_err_meas_list,
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

swp_vals = np.array(collated_data[swp_params])
pop_popnprobe_meas = np.stack(collated_data["pop_popnprobe_meas_list"])          # shape (N, 2)
pop_popnprobe_err = np.stack(collated_data["pop_popnprobe_err_meas_list"])  # shape (N, 2)
temp_popnprobe = np.abs(np.array(collated_data["temp_popnprobe_meas_list"]) * 1000)
temp_popnprobe_err = np.array(collated_data["temp_popnprobe_err_meas_list"]) * 1000
pop_meas = np.stack(collated_data["pop_meas_list"])          # shape (N, 2)
pop_meas_err = np.stack(collated_data["pop_meas_err_list"])  # shape (N, 2)


excited_popnprobe = pop_popnprobe_meas[:,0]
excited_popnprobe_err = pop_popnprobe_err[:,0]
excited_pop = pop_meas[:,0]
excited_pop_err = pop_meas_err[:,0]


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
# Excited state population from populate-probe vs sweep parameter
# -------------------------
fig, ax = plt.subplots(figsize=(6, 4))
ax.errorbar(swp_vals, excited_popnprobe, yerr=excited_popnprobe_err,
            fmt="v", capsize=3, color="r", label="Excited state population (populate-probe)")
ax.errorbar(swp_vals, excited_pop, yerr=excited_pop_err,
            fmt="^", capsize=3, color="b", label="Excited state population (single-shot)")
make_pretty(ax, f"{swp_params}", "Excited State Population (populate-probe)")
ax.legend()
save_fig(fig, f"excited_population_populate_probe_vs_{swp_params}")
plt.show()
# -------------------------

#%%
# TITLE : Double-loop MIST sweep v2
#
# Per FF (outer loop):
#   1. Spec_no_ff (ch1, ge)        →  qubit_freq_noff   (ge freq at readout flux point)
#   2. Spec_no_ff (ch2, gf)        →  qubit_gf_freq     (g→f freq for optical pumping,
#                                                          1000–1200 MHz, upconverted via LO)
#   3. Spec_ff_beg (ch1, ge)       →  qubit_ge_freq     (ge freq at MIST flux point)
#   4. Transmission_g (gain=0)     →  f_cav_g, I_g, Q_g (cavity when qubit in g)
#   5. Transmission_e (gain=30000, →  f_cav_e, I_e, Q_e (cavity when qubit in e,
#         ch2, optical pump g→f→e)                        via optical pumping)
# Per (FF, swp_val) (inner loop):
#   6. MIST popnprobe at f_cav_g   →  P_g_gcav, P_e_gcav
#   7. MIST popnprobe at f_cav_e   →  P_g_ecav, P_e_ecav
#
# T1 at FF=0 run once at the very start to calibrate g/e IQ blob centers.

# Resonator details
kappa = 1.129 # 10^6 rad/s

# ---- Sweep definitions (edit these) ----
FF_sweep_v2    =  np.linspace(-500, -2500,101)  # FF DAC values (outer loop)
swp_params_v2  = "pop_pulse_length"                  # Config key to sweep (inner loop)
short_name_v2 = "length"
swp_vals_v2    = np.linspace(1, 101, 11, dtype=int)  # Values to sweep
active_subtraction = True

outerFolder_v2 = "Z:\\TantalumFluxonium\\Data\\2026_03_31_cooldown\\HouckCage_dev\\MIST_length_Sweep_2000gain_activesubtraction\\"

# Qubit ge-freq predictor for MIST flux point (calibrate slope from spec_ff_beg)
slope_v2 = 0.871   # [MHz/DAC]

def freq_predictor_v2(ff_dac_val, noff_freq = 2833):
    """Predict qubit ge frequency at ff_dac_val from the no-FF frequency."""
    return noff_freq + slope_v2 * ff_dac_val

# ---- Base config shared by all experiments ----
UpdateConfig_base_v2 = {
    # Readout
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 2500,
    "read_pulse_freq": 6826.943,

    # Qubit drive defaults (ch1, ge; overwritten per experiment/FF)
    "qubit_pulse": True,
    "qubit_ch": 1,
    "qubit_nqz": 1,
    "qubit_freq": 2833,        # [MHz] — overwritten each FF from spec_noff_ge
    "qubit_ge_freq": 2833,  # [MHz] — overwritten each FF from spec_ff_beg
    "qubit_pulse_style": "const",
    "sigma": 0.50,
    "qubit_length": 20,
    "flat_top_length": 1,
    "qubit_gain": 30000,
    "qubit_mode_periodic": False,

    # General
    "initialize_pulse": True,
    "cen_num": 2,
    "fridge_temp": 7,
    "yokoVoltage": -0.622,
    "yokoVoltage_freqPoint": -0.622,
    "ff_ch": 6,
    "ff_nqz": 1,
    "use_switch": False,
    "ro_mode_periodic": False,
    "zeroing_pulse": False,
    "pulse_pre_dist": False,
    "qubit_spec_buffer": 10,
    "dt_pulsedef": 0.01,
    "zeroing_a_max": 30000,
    "pre_meas_delay": 6,
}
config_base_v2 = BaseConfig | UpdateConfig_base_v2

# ---- 1. Spec no FF (ch1, ge frequency) ----
UpdateConfig_spec_noff_ge_v2 = {
    "qubit_ch": 1,
    "qubit_nqz": 1,
    "qubit_freq_start": 2733,
    "qubit_freq_stop": 2933,
    "qubit_spec_delay": 10,
    "qubit_freq_expts": 101,
    "qubit_gain": 15000,
    "qubit_spec_buffer": 10,

    "ff_gain": 0,
    "ff_length": 20,
    "pre_ff_delay": 0,
    "ff_pulse_style": "ramp",
    "ff_ramp_length": 0.2,
    "pre_meas_delay": 6,
    "relax_delay": 20,
    "reps": 1000,
    "dt_pulseplay": 1,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
}
config_spec_noff_ge_v2 = config_base_v2 | UpdateConfig_spec_noff_ge_v2

# ---- 2. Spec no FF (ch2, gf frequency, 1000–1200 MHz upconverted via LO at 10000 MHz) ----
UpdateConfig_spec_noff_gf_v2 = {
    "qubit_ch": 2,
    "qubit_nqz": 1,
    "qubit_freq_start": 1521,
    "qubit_freq_stop": 1721,
    "qubit_spec_delay": 10,
    "qubit_freq_expts": 101,
    "qubit_gain": 30000,
    "qubit_spec_buffer": 10,

    "ff_gain": 0,
    "ff_length": 20,
    "pre_ff_delay": 0,
    "ff_pulse_style": "ramp",
    "ff_ramp_length": 0.2,
    "pre_meas_delay": 6,
    "relax_delay": 20,
    "reps": 1000,
    "dt_pulseplay": 1,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
}
config_spec_noff_gf_v2 = config_base_v2 | UpdateConfig_spec_noff_gf_v2

# ---- 3. Spec FF beg (ch1, ge frequency at MIST flux point) ----
UpdateConfig_spec_ff_beg_v2 = {
    "qubit_ch": 1,
    "qubit_nqz": 1,
    "qubit_freq_start": 2733,   # updated each FF from freq_predictor_v2
    "qubit_freq_stop": 2933,    # updated each FF from freq_predictor_v2
    "qubit_spec_delay": 10,
    "qubit_freq_expts": 101,
    "qubit_gain": 15000,
    "qubit_spec_buffer": 10,

    "ff_gain": 0,           # updated each FF
    "ff_length": 20,
    "pre_ff_delay": 0,
    "ff_pulse_style": "ramp",
    "ff_ramp_length": 0.2,
    "pre_meas_delay": 2,
    "relax_delay": 20,
    "reps": 1000,
    "dt_pulseplay": 2,
}
config_spec_ff_beg_v2 = config_base_v2 | UpdateConfig_spec_ff_beg_v2

# ---- T1 (once at FF=0 to calibrate g/e IQ blob centers) ----
UpdateConfig_t1_v2 = {
    "ff_ramp_style": "linear",
    "ff_ramp_start": 0,
    "ff_ramp_stop": 0,
    "ff_hold": 200,
    "ff_ramp_length": 0.2,

    "qubit_ch": 1,
    "qubit_nqz": 1,
    "qubit_ge_freq": 2833,
    "relax_delay_1": 5,
    "relax_delay_2": 20,
    "wait_start": 2,
    "wait_stop": 2000,
    "wait_num": 21,
    "wait_type": "log",

    "reps": 10000,
    "cen_num": 2,
    "initialize_pulse": True,
    "pre_meas_delay": 6,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    "dt_pulseplay": 2,
    "auto_dt_pulseplay": True,
}
config_t1_v2 = config_base_v2 | UpdateConfig_t1_v2

# ---- 4. Transmission_g (qubit_gain=0 → qubit stays in g, no optical pumping) ----
UpdateConfig_trans_g_v2 = {
    "TransSpan": 0.5,
    "TransNumPoints": 101,
    "read_pulse_gain": 200,

    "ff_ramp_style": "linear",
    "ff_ramp_start": 0,
    "ff_ramp_stop": 0,          # updated each FF
    "ff_ramp_length": 0.2,

    "qubit_ch": 1,
    "qubit_nqz": 1,
    "qubit_gain": 0,            # zero gain → no pulse → qubit in g
    "qubit_length": 20,
    "initialize_pulse": True,

    "relax_delay": 300,
    "reps": 1500,
    "pre_meas_delay": 5,
    "post_meas_delay": 5,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    "dt_pulseplay": 0.2,
    "negative_pulse": False,
}
config_trans_g_v2 = config_base_v2 | UpdateConfig_trans_g_v2

# ---- 5. Transmission_e (qubit_gain=30000, ch2, optical pumping g→f→e) ----
UpdateConfig_trans_e_v2 = {
    "TransSpan": 0.5,
    "TransNumPoints": 101,
    "read_pulse_gain": 200,

    "ff_ramp_style": "linear",
    "ff_ramp_start": 0,
    "ff_ramp_stop": 0,          # updated each FF (same flux point as trans_g)
    "ff_ramp_length": 0.2,

    "qubit_ch": 2,              # ch2 drives g→f; f decays to e (optical pumping)
    "qubit_nqz": 1,
    "qubit_freq": 1621,       # [MHz] g→f freq — overwritten each FF from spec_noff_gf
    "qubit_gain": 30000,
    "qubit_length": 20,         # long pulse for optical pumping
    "initialize_pulse": True,

    "relax_delay": 20,
    "reps": 2000,
    "pre_meas_delay": 5,
    "post_meas_delay": 5,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    "dt_pulseplay": 0.2,
    "negative_pulse": False,
}
config_trans_e_v2 = config_base_v2 | UpdateConfig_trans_e_v2

# ---- 6/7. MIST popnprobe base (pop_pulse_freq swapped to f_cav_g or f_cav_e per run) ----
UpdateConfig_popnprobe_v2 = {
    "ff_ramp_style": "linear",
    "ff_ramp_start": 0,
    "ff_ramp_stop": 0,      # updated each FF
    "ff_hold": 0,
    "ff_ramp_length": 0.02,

    "qubit_ch": 1,
    "qubit_nqz": 1,

    "pop_pulse_length": 10/kappa,     # swept in inner loop
    "pop_pulse_gain": 2000,
    "pop_pulse_freq": 6826.943,  # overwritten before each run (f_cav_g or f_cav_e)
    "pop_relax_delay": 5/kappa,

    "relax_delay_1": 5/kappa,
    "relax_delay_2": 20,

    "reps": 30000,
    "cen_num": 2,
    "pulse_pre_dist": False,
    "zeroing_pulse": False,
    "dt_pulseplay": 0.2,
    "pre_meas_delay": 6,
}
config_popnprobe_v2 = config_base_v2 | UpdateConfig_popnprobe_v2

#%%
# ---- Initialize data storage ----
centers_v2 = None

# Per-FF (one entry per FF DAC value)
qubit_freq_noff_vs_ff_v2        = []   # ge freq at readout flux point (ch1) [MHz]
qubit_gf_freq_vs_ff_v2          = []   # gf freq for optical pumping (ch2) [MHz]
qubit_freq_ff_beg_vs_ff_v2      = []   # ge freq at MIST flux point (ch1) [MHz]
f_cav_g_vs_ff_v2                = []   # cavity peak freq | qubit in g [MHz]
f_cav_e_vs_ff_v2                = []   # cavity peak freq | qubit in e [MHz]
trans_g_I_vs_ff_v2              = []   # I trace from Transmission_g
trans_g_Q_vs_ff_v2              = []   # Q trace from Transmission_g
trans_e_I_vs_ff_v2              = []   # I trace from Transmission_e
trans_e_Q_vs_ff_v2              = []   # Q trace from Transmission_e
trans_freq_axis_vs_ff_v2        = []   # Freq axis shared by both transmissions [MHz]

# 2D (n_FF × n_swp) — g-cavity MIST
pg_gcav_vs_ff_vs_swp_v2 = []
pg_err_gcav_vs_ff_vs_swp_v2 = []
pe_gcav_vs_ff_vs_swp_v2 = []
pe_err_gcav_vs_ff_vs_swp_v2 = []
# 2D (n_FF × n_swp) — e-cavity MIST
pg_ecav_vs_ff_vs_swp_v2 = []
pg_err_ecav_vs_ff_vs_swp_v2 = []
pe_ecav_vs_ff_vs_swp_v2 = []
pe_err_ecav_vs_ff_vs_swp_v2 = []

# 2D (n_FF × n_swp) — g-cavity MIST active subtraction
pg_gcav_vs_ff_vs_swp_as_v2 = []
pg_err_gcav_vs_ff_vs_swp_as_v2 = []
pe_gcav_vs_ff_vs_swp_as_v2 = []
pe_err_gcav_vs_ff_vs_swp_as_v2 = []
# 2D (n_FF × n_swp) — e-cavity MIST active subtraction
pg_ecav_vs_ff_vs_swp_as_v2 = []
pg_err_ecav_vs_ff_vs_swp_as_v2 = []
pe_ecav_vs_ff_vs_swp_as_v2 = []
pe_err_ecav_vs_ff_vs_swp_as_v2 = []

#%%
from tqdm import tqdm
# ---- Step 1: T1 at FF=0 — calibrate g/e IQ blob centers ----
print("========== Running T1 at FF=0 to calibrate g/e centers (v2) =============")
outerFolder_t1_v2 = outerFolder_v2 + "T1_initial\\"

soc.reset_gens()
inst_spec_noff_ge_v2 = FFSpecSlice_Experiment_wPPD(
    path="Spec_noFF_ge", cfg=config_spec_noff_ge_v2,
    soc=soc, soccfg=soccfg,
    outerFolder=outerFolder_t1_v2, short_directory_names=True)
data_spec_noff_ge_v2 = inst_spec_noff_ge_v2.acquire(progress=False)
inst_spec_noff_ge_v2.display(data_spec_noff_ge_v2, plot_disp=False)
inst_spec_noff_ge_v2.save_data(data_spec_noff_ge_v2)
inst_spec_noff_ge_v2.save_config()
qubit_freq_noff_v2 = inst_spec_noff_ge_v2.qubit_peak_freq
qubit_freq_noff_vs_ff_v2.append(qubit_freq_noff_v2)
print(f"  Spec no FF (ge, ch1): {qubit_freq_noff_v2:.2f} MHz")
plt.close('all')

soc.reset_gens()
config_t1_v2['qubit_freq'] = qubit_freq_noff_v2
inst_t1_v2 = FF_T1_wPulsePreDist(path="FF_T1_initial", cfg=config_t1_v2,
                                   soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder_t1_v2)
try:
    inst_t1_v2.acquire(plot_predist=False)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
data_t1_v2 = inst_t1_v2.process_data()
inst_t1_v2.save_data(data_t1_v2)
inst_t1_v2.display(data_t1_v2, plotDisp=False)
inst_t1_v2.display_all_data(data_t1_v2)
inst_t1_v2.save_config()
centers_v2 = data_t1_v2['data']['centers_list'][-1]
g = np.array([data_t1_v2['data']['g01'], data_t1_v2['data']['g10']])
sort_index = np.argsort(g)
centers_v2 = centers_v2[sort_index]
print(f"Calibrated centers (index 0 = g, index 1 = e): {centers_v2}")
plt.close('all')

# ---- Step 2: Double loop ----
print("========== STARTING DOUBLE-LOOP MIST SWEEP v2 =============")
for i_ff_v2, ff_val_v2 in enumerate(tqdm(FF_sweep_v2, desc="FF DAC sweep v2")):
    print(f"\n----- FF DAC = {ff_val_v2} -----")
    outerFolder_ff_v2 = outerFolder_v2 + f"dac_{ff_val_v2:.0f}\\"

    # ---- 2a. Spec no FF (ch1, ge) ----
    soc.reset_gens()
    inst_spec_noff_ge_v2 = FFSpecSlice_Experiment_wPPD(
        path="Spec_noFF_ge", cfg=config_spec_noff_ge_v2,
        soc=soc, soccfg=soccfg,
        outerFolder=outerFolder_ff_v2, short_directory_names=True)
    data_spec_noff_ge_v2 = inst_spec_noff_ge_v2.acquire(progress=False)
    inst_spec_noff_ge_v2.display(data_spec_noff_ge_v2, plot_disp=False)
    inst_spec_noff_ge_v2.save_data(data_spec_noff_ge_v2)
    inst_spec_noff_ge_v2.save_config()
    qubit_freq_noff_v2 = inst_spec_noff_ge_v2.qubit_peak_freq
    qubit_freq_noff_vs_ff_v2.append(qubit_freq_noff_v2)
    print(f"  Spec no FF (ge, ch1): {qubit_freq_noff_v2:.2f} MHz")
    plt.close('all')

    # ---- 2b. Spec no FF (ch2, gf) ----
    soc.reset_gens()
    inst_spec_noff_gf_v2 = FFSpecSlice_Experiment_wPPD(
        path="Spec_noFF_gf", cfg=config_spec_noff_gf_v2,
        soc=soc, soccfg=soccfg,
        outerFolder=outerFolder_ff_v2, short_directory_names=True)
    data_spec_noff_gf_v2 = inst_spec_noff_gf_v2.acquire(progress=False)
    inst_spec_noff_gf_v2.display(data_spec_noff_gf_v2, plot_disp=False)
    inst_spec_noff_gf_v2.save_data(data_spec_noff_gf_v2)
    inst_spec_noff_gf_v2.save_config()
    qubit_gf_freq_v2 = inst_spec_noff_gf_v2.qubit_peak_freq
    qubit_gf_freq_vs_ff_v2.append(qubit_gf_freq_v2)
    print(f"  Spec no FF (gf, ch2): {qubit_gf_freq_v2:.2f} MHz")
    plt.close('all')

    # Update Transmission_e to drive at the measured g→f frequency
    config_trans_e_v2['qubit_freq'] = qubit_gf_freq_v2

    # ---- 2c. Spec FF beg (ch1, ge at MIST flux point) ----
    predicted_ge_v2 = freq_predictor_v2(ff_val_v2, qubit_freq_noff_v2)
    config_spec_ff_beg_v2['ff_gain']          = int(ff_val_v2)
    config_spec_ff_beg_v2['qubit_freq_start'] = predicted_ge_v2 - 100
    config_spec_ff_beg_v2['qubit_freq_stop']  = predicted_ge_v2 + 100
    soc.reset_gens()
    inst_spec_ff_beg_v2 = FFSpecSlice_Experiment_wPPD(
        path="Spec_FF_beg", cfg=config_spec_ff_beg_v2,
        soc=soc, soccfg=soccfg,
        outerFolder=outerFolder_ff_v2, short_directory_names=True)
    data_spec_ff_beg_v2 = inst_spec_ff_beg_v2.acquire(progress=False)
    inst_spec_ff_beg_v2.display(data_spec_ff_beg_v2, plot_disp=False)
    inst_spec_ff_beg_v2.save_data(data_spec_ff_beg_v2)
    inst_spec_ff_beg_v2.save_config()
    qubit_ge_freq_v2 = inst_spec_ff_beg_v2.qubit_peak_freq
    qubit_freq_ff_beg_vs_ff_v2.append(qubit_ge_freq_v2)
    print(f"  Spec FF beg (ge, ch1): {qubit_ge_freq_v2:.2f} MHz")
    plt.close('all')

    # Propagate ge freq at MIST flux point and no-FF drive freq into popnprobe
    config_popnprobe_v2['qubit_ge_freq'] = qubit_ge_freq_v2
    config_popnprobe_v2['qubit_freq']    = qubit_freq_noff_v2
    config_popnprobe_v2['ff_ramp_stop']  = int(ff_val_v2)

    # ---- 2d. Transmission_g (qubit_gain=0 → cavity freq when qubit in g) ----
    config_trans_g_v2['ff_ramp_stop'] = int(ff_val_v2)
    soc.reset_gens()
    inst_trans_g_v2 = FFTransmission(
        path="Transmission_g", cfg=config_trans_g_v2,
        soc=soc, soccfg=soccfg, outerFolder=outerFolder_ff_v2)
    try:
        data_trans_g_v2 = inst_trans_g_v2.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
        data_trans_g_v2 = None
    inst_trans_g_v2.display(data=data_trans_g_v2, plotDisp=False)
    inst_trans_g_v2.save_data(data_trans_g_v2)
    inst_trans_g_v2.save_config()
    f_cav_g_v2 = inst_trans_g_v2.peakFreq
    f_cav_g_vs_ff_v2.append(f_cav_g_v2)
    # NOTE: verify 'I', 'Q', 'freq_pts' match the FFTransmission data dict structure
    trans_g_I_vs_ff_v2.append(data_trans_g_v2['data']['avgi'])
    trans_g_Q_vs_ff_v2.append(data_trans_g_v2['data']['avgq'])
    trans_freq_axis_vs_ff_v2.append(data_trans_g_v2['data']['fpts'])
    print(f"  Transmission_g peak: {f_cav_g_v2:.4f} MHz")
    plt.close('all')

    # ---- 2e. Transmission_e (qubit_gain=30000, ch2, optical pumping g→f→e) ----
    config_trans_e_v2['ff_ramp_stop'] = int(ff_val_v2)
    soc.reset_gens()
    inst_trans_e_v2 = FFTransmission(
        path="Transmission_e", cfg=config_trans_e_v2,
        soc=soc, soccfg=soccfg, outerFolder=outerFolder_ff_v2)
    try:
        data_trans_e_v2 = inst_trans_e_v2.acquire()
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))
        data_trans_e_v2 = None
    inst_trans_e_v2.display(data=data_trans_e_v2, plotDisp=False)
    inst_trans_e_v2.save_data(data_trans_e_v2)
    inst_trans_e_v2.save_config()
    f_cav_e_v2 = inst_trans_e_v2.peakFreq
    f_cav_e_vs_ff_v2.append(f_cav_e_v2)
    trans_e_I_vs_ff_v2.append(data_trans_e_v2['data']['avgi'])
    trans_e_Q_vs_ff_v2.append(data_trans_e_v2['data']['avgq'])
    print(f"  Transmission_e peak: {f_cav_e_v2:.4f} MHz")
    plt.close('all')

    # ---- 2f/2g. Inner loop: MIST popnprobe at f_cav_g and f_cav_e ----
    pg_gcav_vs_swp_v2 = []
    pg_err_gcav_vs_swp_v2 = []
    pe_gcav_vs_swp_v2 = []
    pe_err_gcav_vs_swp_v2 = []
    pg_ecav_vs_swp_v2 = []
    pg_err_ecav_vs_swp_v2 = []
    pe_ecav_vs_swp_v2 = []
    pe_err_ecav_vs_swp_v2 = []

    pg_gcav_vs_swp_as_v2 = []
    pg_err_gcav_vs_swp_as_v2 = []
    pe_gcav_vs_swp_as_v2 = []
    pe_err_gcav_vs_swp_as_v2 = []
    pg_ecav_vs_swp_as_v2 = []
    pg_err_ecav_vs_swp_as_v2 = []
    pe_ecav_vs_swp_as_v2 = []
    pe_err_ecav_vs_swp_as_v2 = []

    for i_swp_v2, swp_val_v2 in enumerate(swp_vals_v2):
        config_popnprobe_v2[swp_params_v2] = swp_val_v2
        print(f"    {swp_params_v2} = {swp_val_v2}")

        # -- 2f. popnprobe at f_cav_g --
        config_popnprobe_v2['pop_pulse_freq'] = f_cav_g_v2
        outerFolder_gcav_v2 = outerFolder_ff_v2 + f"MIST_g\\"
        soc.reset_gens()
        inst_pop_gcav_v2 = FFPopulateProbe(
            path="FFPopProbe_g_"+short_name_v2+"_"+str(i_swp_v2) , cfg=config_popnprobe_v2,
            soc=soc, soccfg=soccfg,
            outerFolder=outerFolder_gcav_v2, progress=False)
        try:
            inst_pop_gcav_v2.acquire()
        except Exception:
            print("Pyro traceback:")
            print("".join(Pyro4.util.getPyroTraceback()))
        data_pop_gcav_v2 = inst_pop_gcav_v2.process_v2(centers=centers_v2, confidence = 0.98)
        inst_pop_gcav_v2.save_data(data_pop_gcav_v2)
        inst_pop_gcav_v2.save_config()
        pop_gcav_v2 = data_pop_gcav_v2['data']['mean_pop']   # (cen_num,)
        pop_err_gcav_v2 = data_pop_gcav_v2['data']['std_pop']    # (cen_num,)

        pg_gcav_vs_swp_v2.append(pop_gcav_v2[0][0])
        pg_err_gcav_vs_swp_v2.append(pop_err_gcav_v2[0][0])
        pe_gcav_vs_swp_v2.append(pop_gcav_v2[1][1])
        pe_err_gcav_vs_swp_v2.append(pop_err_gcav_v2[1][1])

        if active_subtraction :
            gain_val = config_popnprobe_v2["pop_pulse_gain"]
            config_popnprobe_v2["pop_pulse_gain"] = 0
            soc.reset_gens()
            inst_pop_gcav_v2 = FFPopulateProbe(
                path="FFPopProbe_gbase_" + short_name_v2 + "_" + str(i_swp_v2), cfg=config_popnprobe_v2,
                soc=soc, soccfg=soccfg,
                outerFolder=outerFolder_gcav_v2, progress=False)
            try:
                inst_pop_gcav_v2.acquire()
            except Exception:
                print("Pyro traceback:")
                print("".join(Pyro4.util.getPyroTraceback()))
            data_pop_gcav_v2_base = inst_pop_gcav_v2.process_v2(centers=centers_v2, confidence = 0.98)
            inst_pop_gcav_v2.save_data(data_pop_gcav_v2_base)
            inst_pop_gcav_v2.save_config()
            pop_gcav_v2_base = data_pop_gcav_v2_base['data']['mean_pop']  # (cen_num,)
            pop_err_gcav_v2_base = data_pop_gcav_v2_base['data']['std_pop']  # (cen_num,)
            config_popnprobe_v2["pop_pulse_gain"] = gain_val

            pg_gcav_vs_swp_as_v2.append(pop_gcav_v2[0][0] - pop_gcav_v2_base[0][0])
            pg_err_gcav_vs_swp_as_v2.append(np.sqrt(pop_err_gcav_v2[0][0]**2 + pop_err_gcav_v2_base[0][0]**2))
            pe_gcav_vs_swp_as_v2.append(pop_gcav_v2[1][1] - pop_gcav_v2_base[1][1] )
            pe_err_gcav_vs_swp_as_v2.append(np.sqrt(pop_err_gcav_v2[1][1]**2 + pop_err_gcav_v2_base[1][1]**2))

        plt.close('all')

        # -- 2g. popnprobe at f_cav_e --
        config_popnprobe_v2['pop_pulse_freq'] = f_cav_e_v2
        outerFolder_ecav_v2 = outerFolder_ff_v2 + f"MIST_e\\"
        soc.reset_gens()
        inst_pop_ecav_v2 = FFPopulateProbe(
            path="FFPopProbe_e_"+short_name_v2+"_"+str(i_swp_v2), cfg=config_popnprobe_v2,
            soc=soc, soccfg=soccfg,
            outerFolder=outerFolder_ecav_v2, progress=False)
        try:
            inst_pop_ecav_v2.acquire()
        except Exception:
            print("Pyro traceback:")
            print("".join(Pyro4.util.getPyroTraceback()))
        data_pop_ecav_v2 = inst_pop_ecav_v2.process_v2(centers=centers_v2, confidence = 0.98)
        inst_pop_ecav_v2.save_data(data_pop_ecav_v2)
        inst_pop_ecav_v2.save_config()
        pop_ecav_v2 = data_pop_ecav_v2['data']['mean_pop']
        pop_err_ecav_v2 = data_pop_ecav_v2['data']['std_pop']

        pg_ecav_vs_swp_v2.append(pop_ecav_v2[0][0])
        pg_err_ecav_vs_swp_v2.append(pop_err_ecav_v2[0][0])
        pe_ecav_vs_swp_v2.append(pop_ecav_v2[1][1])
        pe_err_ecav_vs_swp_v2.append(pop_err_ecav_v2[1][1])

        if active_subtraction :
            gain_val = config_popnprobe_v2["pop_pulse_gain"]
            config_popnprobe_v2["pop_pulse_gain"] = 0
            soc.reset_gens()
            inst_pop_ecav_v2 = FFPopulateProbe(
                path="FFPopProbe_ebase_" + short_name_v2 + "_" + str(i_swp_v2), cfg=config_popnprobe_v2,
                soc=soc, soccfg=soccfg,
                outerFolder=outerFolder_ecav_v2, progress=False)
            try:
                inst_pop_ecav_v2.acquire()
            except Exception:
                print("Pyro traceback:")
                print("".join(Pyro4.util.getPyroTraceback()))
            data_pop_ecav_v2_base = inst_pop_ecav_v2.process_v2(centers=centers_v2, confidence = 0.98)
            inst_pop_ecav_v2.save_data(data_pop_ecav_v2_base)
            inst_pop_ecav_v2.save_config()
            pop_ecav_v2_base = data_pop_ecav_v2_base['data']['mean_pop']  # (cen_num,)
            pop_err_ecav_v2_base = data_pop_ecav_v2_base['data']['std_pop']  # (cen_num,)
            config_popnprobe_v2["pop_pulse_gain"] = gain_val

            pg_ecav_vs_swp_as_v2.append(pop_ecav_v2[0][0] - pop_ecav_v2_base[0][0])
            pg_err_ecav_vs_swp_as_v2.append(np.sqrt(pop_err_ecav_v2[0][0]**2 + pop_err_ecav_v2_base[0][0]**2))
            pe_ecav_vs_swp_as_v2.append(pop_ecav_v2[1][1] - pop_ecav_v2_base[1][1])
            pe_err_ecav_vs_swp_as_v2.append(np.sqrt(pop_err_ecav_v2[1][1]**2 + pop_err_ecav_v2_base[1][1]**2))
        plt.close('all')

    pg_gcav_vs_ff_vs_swp_v2.append(pg_gcav_vs_swp_v2)
    pg_err_gcav_vs_ff_vs_swp_v2.append(pg_err_gcav_vs_swp_v2)
    pe_gcav_vs_ff_vs_swp_v2.append(pe_gcav_vs_swp_v2)
    pe_err_gcav_vs_ff_vs_swp_v2.append(pe_err_gcav_vs_swp_v2)
    pg_ecav_vs_ff_vs_swp_v2.append(pg_ecav_vs_swp_v2)
    pg_err_ecav_vs_ff_vs_swp_v2.append(pg_err_ecav_vs_swp_v2)
    pe_ecav_vs_ff_vs_swp_v2.append(pe_ecav_vs_swp_v2)
    pe_err_ecav_vs_ff_vs_swp_v2.append(pe_err_ecav_vs_swp_v2)

    if active_subtraction:
        pg_gcav_vs_ff_vs_swp_as_v2.append(pg_gcav_vs_swp_as_v2)
        pg_err_gcav_vs_ff_vs_swp_as_v2.append(pg_err_gcav_vs_swp_as_v2)
        pe_gcav_vs_ff_vs_swp_as_v2.append(pe_gcav_vs_swp_as_v2)
        pe_err_gcav_vs_ff_vs_swp_as_v2.append(pe_err_gcav_vs_swp_as_v2)
        pg_ecav_vs_ff_vs_swp_as_v2.append(pg_ecav_vs_swp_as_v2)
        pg_err_ecav_vs_ff_vs_swp_as_v2.append(pg_err_ecav_vs_swp_as_v2)
        pe_ecav_vs_ff_vs_swp_as_v2.append(pe_ecav_vs_swp_as_v2)
        pe_err_ecav_vs_ff_vs_swp_as_v2.append(pe_err_ecav_vs_swp_as_v2)

#%%
# ---- Step 3: Collate and save to HDF5 ----
import h5py

pg_gcav_arr_v2 = np.array(pg_gcav_vs_ff_vs_swp_v2)   # (n_FF, n_swp)
pg_err_gcav_arr_v2 = np.array(pg_err_gcav_vs_ff_vs_swp_v2)
pe_gcav_arr_v2 = np.array(pe_gcav_vs_ff_vs_swp_v2)
pe_err_gcav_arr_v2 = np.array(pe_err_gcav_vs_ff_vs_swp_v2)
pg_ecav_arr_v2 = np.array(pg_ecav_vs_ff_vs_swp_v2)
pg_err_ecav_arr_v2 = np.array(pg_err_ecav_vs_ff_vs_swp_v2)
pe_ecav_arr_v2 = np.array(pe_ecav_vs_ff_vs_swp_v2)
pe_err_ecav_arr_v2 = np.array(pe_err_ecav_vs_ff_vs_swp_v2)


collated_v2 = {
    "FF_sweep":                     np.array(FF_sweep_v2),
    swp_params_v2:                  np.array(swp_vals_v2),
    "T1":                           np.array(data_t1_v2['data']['T1']),
    "qubit_freq_noff_vs_ff":        np.array(qubit_freq_noff_vs_ff_v2),
    "qubit_gf_freq_vs_ff":          np.array(qubit_gf_freq_vs_ff_v2),
    "qubit_freq_ff_beg_vs_ff":      np.array(qubit_freq_ff_beg_vs_ff_v2),
    "f_cav_g_vs_ff":                np.array(f_cav_g_vs_ff_v2),
    "f_cav_e_vs_ff":                np.array(f_cav_e_vs_ff_v2),
    "pg_gcav_vs_ff_vs_swp":         pg_gcav_arr_v2,
    "pg_err_gcav_vs_ff_vs_swp":     pg_err_gcav_arr_v2,
    "pe_gcav_vs_ff_vs_swp":         pe_gcav_arr_v2,
    "pe_err_gcav_vs_ff_vs_swp":     pe_err_gcav_arr_v2,
    "pg_ecav_vs_ff_vs_swp":         pg_ecav_arr_v2,
    "pg_err_ecav_vs_ff_vs_swp":     pg_err_ecav_arr_v2,
    "pe_ecav_vs_ff_vs_swp":         pe_ecav_arr_v2,
    "pe_err_ecav_vs_ff_vs_swp":     pe_err_ecav_arr_v2,
}

if active_subtraction:
    pg_gcav_as_arr_v2 = np.array(pg_gcav_vs_ff_vs_swp_as_v2)
    pg_err_gcav_as_arr_v2 = np.array(pg_err_gcav_vs_ff_vs_swp_as_v2)
    pe_gcav_as_arr_v2 = np.array(pe_gcav_vs_ff_vs_swp_as_v2)
    pe_err_gcav_as_arr_v2 = np.array(pe_err_gcav_vs_ff_vs_swp_as_v2)
    pg_ecav_as_arr_v2 = np.array(pg_ecav_vs_ff_vs_swp_as_v2)
    pg_err_ecav_as_arr_v2 = np.array(pg_err_ecav_vs_ff_vs_swp_as_v2)
    pe_ecav_as_arr_v2 = np.array(pe_ecav_vs_ff_vs_swp_as_v2)
    pe_err_ecav_as_arr_v2 = np.array(pe_err_ecav_vs_ff_vs_swp_as_v2)
    collated_v2.update({
        "pg_gcav_vs_ff_vs_swp_as": pg_gcav_as_arr_v2,
        "pg_err_gcav_vs_ff_vs_swp_as": pg_err_gcav_as_arr_v2,
        "pe_gcav_vs_ff_vs_swp_as": pe_gcav_as_arr_v2,
        "pe_err_gcav_vs_ff_vs_swp_as": pe_err_gcav_as_arr_v2,
        "pg_ecav_vs_ff_vs_swp_as": pg_ecav_as_arr_v2,
        "pg_err_ecav_vs_ff_vs_swp_as": pg_err_ecav_as_arr_v2,
        "pe_ecav_vs_ff_vs_swp_as": pe_ecav_as_arr_v2,
        "pe_err_ecav_vs_ff_vs_swp_as": pe_err_ecav_as_arr_v2,
    })

file_loc_v2 = outerFolder_v2 + "collated_data_v2.h5"
with h5py.File(file_loc_v2, "w") as f:
    for key, val in collated_v2.items():
        f.create_dataset(key, data=val)
    # Transmission I/Q saved separately (can be None on acquisition failure)
    Ig_clean_v2 = [x for x in trans_g_I_vs_ff_v2 if x is not None]
    Qg_clean_v2 = [x for x in trans_g_Q_vs_ff_v2 if x is not None]
    Ie_clean_v2 = [x for x in trans_e_I_vs_ff_v2 if x is not None]
    Qe_clean_v2 = [x for x in trans_e_Q_vs_ff_v2 if x is not None]
    fa_clean_v2 = [x for x in trans_freq_axis_vs_ff_v2 if x is not None]
    if Ig_clean_v2:
        f.create_dataset("trans_g_I_vs_ff",       data=np.array(Ig_clean_v2))
        f.create_dataset("trans_g_Q_vs_ff",       data=np.array(Qg_clean_v2))
    if Ie_clean_v2:
        f.create_dataset("trans_e_I_vs_ff",       data=np.array(Ie_clean_v2))
        f.create_dataset("trans_e_Q_vs_ff",       data=np.array(Qe_clean_v2))
    if fa_clean_v2:
        f.create_dataset("trans_freq_axis_vs_ff", data=np.array(fa_clean_v2))
print(f"Saved v2 collated data to {file_loc_v2}")

#%%
# ---- Step 4: Plot results ----
FF_plt_v2       = np.array(collated_v2["FF_sweep"])
swp_plt_v2      = np.array(collated_v2[swp_params_v2])
qf_noff_v2      = np.array(collated_v2["qubit_freq_noff_vs_ff"])
qf_gf_v2        = np.array(collated_v2["qubit_gf_freq_vs_ff"])
qf_ffbeg_v2     = np.array(collated_v2["qubit_freq_ff_beg_vs_ff"])
f_cav_g_plt_v2  = np.array(collated_v2["f_cav_g_vs_ff"])
f_cav_e_plt_v2  = np.array(collated_v2["f_cav_e_vs_ff"])
pg_gcav_plt_v2  = np.array(collated_v2["pg_gcav_vs_ff_vs_swp"])   # (n_FF, n_swp)
pe_gcav_plt_v2  = np.array(collated_v2["pe_gcav_vs_ff_vs_swp"])
pg_ecav_plt_v2  = np.array(collated_v2["pg_ecav_vs_ff_vs_swp"])
pe_ecav_plt_v2  = np.array(collated_v2["pe_ecav_vs_ff_vs_swp"])


def make_pretty_v2(ax, xlabel, ylabel, title=None):
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    if title:
        ax.set_title(title, fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=10)


def save_fig_v2(fig, name):
    os.makedirs(outerFolder_v2, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(outerFolder_v2, f"{name}.png"), dpi=300)
    fig.savefig(os.path.join(outerFolder_v2, f"{name}.pdf"))


# ge (no FF, ch1)
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(qf_noff_v2, "o-", color="C0")
make_pretty_v2(ax, "FF DAC Value", "Qubit Frequency [MHz]", "ge Qubit Frequency vs FF DAC (no FF, ch1)")
save_fig_v2(fig, "qubit_freqs_vs_ff_ge_noff")

# gf (no FF, ch2)
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(FF_plt_v2, qf_gf_v2, "s-", color="C1")
make_pretty_v2(ax, "FF DAC Value", "Qubit Frequency [MHz]", "gf Qubit Frequency vs FF DAC (no FF, ch2)")
save_fig_v2(fig, "qubit_freqs_vs_ff_gf_noff")

# ge (FF beg, ch1)
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(FF_plt_v2, qf_ffbeg_v2, "^-", color="C2")
make_pretty_v2(ax, "FF DAC Value", "Qubit Frequency [MHz]", "ge Qubit Frequency vs FF DAC (FF beg, ch1)")
save_fig_v2(fig, "qubit_freqs_vs_ff_ge_ffbeg")

# Cavity frequencies vs FF DAC
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_plt_v2, f_cav_g_plt_v2, "o-", color="C3", label="$f_{cav}$ | qubit in g")
ax.plot(FF_plt_v2, f_cav_e_plt_v2, "s-", color="C4", label="$f_{cav}$ | qubit in e")
make_pretty_v2(ax, "FF DAC Value", "Cavity Frequency [MHz]", "Cavity Frequencies vs FF DAC")
ax.legend()
save_fig_v2(fig, "cavity_freqs_vs_ff")

# Dispersive shift (f_cav_e - f_cav_g) vs FF DAC
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(FF_plt_v2, f_cav_e_plt_v2 - f_cav_g_plt_v2, "d-", color="C5")
make_pretty_v2(ax, "FF DAC Value", "$f_{cav,e} - f_{cav,g}$ [MHz]",
               "Dispersive Shift vs FF DAC")
save_fig_v2(fig, "dispersive_shift_vs_ff")

# Transmission magnitude spectra — g-state and e-state, 2D colorplot (freq × FF)
if trans_g_I_vs_ff_v2 and trans_g_I_vs_ff_v2[0] is not None:
    fig, axes = plt.subplots(2, 1, figsize=(10, 8))

    fa = trans_freq_axis_vs_ff_v2[0]
    valid = [i for i, v in enumerate(trans_g_I_vs_ff_v2) if v is not None]

    g_mag = np.array([trans_g_I_vs_ff_v2[i]**2 + trans_g_Q_vs_ff_v2[i]**2 for i in valid])
    e_mag = np.array([trans_e_I_vs_ff_v2[i]**2 + trans_e_Q_vs_ff_v2[i]**2 for i in valid if trans_e_I_vs_ff_v2[i] is not None])
    ff_vals = [FF_plt_v2[i] for i in valid]

    for ax, arr, title in zip(
        axes,
        [g_mag, e_mag],
        ["Trans |g|² (qubit in g)", "Trans |e|² (qubit in e)"],
    ):
        im = ax.pcolormesh(fa, ff_vals, arr, shading="nearest", cmap="RdBu_r")
        fig.colorbar(im, ax=ax, label="I²+Q² [a.u.]")
        make_pretty_v2(ax, "Freq [MHz]", "FF value", title)

    plt.tight_layout()
    save_fig_v2(fig, "transmission_mag_g_and_e_per_FF")

# Pg and Pe 2D heatmaps for g-cavity MIST with DAC valuue
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
im0 = axes[0].pcolormesh(FF_plt_v2, swp_plt_v2, np.transpose(pg_gcav_plt_v2), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0],  "FF DAC Value", swp_params_v2,f"$P_g$ (MIST at $f_{{cav,g}}$)")
# axes[0].invert_yaxis()

im1 = axes[1].pcolormesh( FF_plt_v2, swp_plt_v2, np.transpose(pe_gcav_plt_v2), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1], "FF DAC Value",  swp_params_v2,f"$P_e$ (MIST at $f_{{cav,g}}$)")
# axes[1].invert_yaxis()
save_fig_v2(fig, "P_2d_gcav_dac")

# Pg and Pe 2D heatmaps for e-cavity MIST
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
im0 = axes[0].pcolormesh( FF_plt_v2, swp_plt_v2, np.transpose(pg_ecav_plt_v2), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0],  "FF DAC Value", swp_params_v2,f"$P_g$ (MIST at $f_{{cav,e}}$)")
# axes[0].invert_yaxis()

im1 = axes[1].pcolormesh( FF_plt_v2, swp_plt_v2, np.transpose(pe_ecav_plt_v2), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1],  "FF DAC Value", swp_params_v2,f"$P_e$ (MIST at $f_{{cav,e}}$)")
# axes[1].invert_yaxis()
save_fig_v2(fig, "P_2d_ecav_dac")

# Pg and Pe 2D heatmaps for g-cavity MIST with qubit_freq
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
im0 = axes[0].pcolormesh(qf_ffbeg_v2, swp_plt_v2, np.transpose(pg_gcav_plt_v2), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0],  "Qubit Freq (in MHz)", swp_params_v2,f"$P_g$ (MIST at $f_{{cav,g}}$)")
# axes[0].invert_yaxis()

im1 = axes[1].pcolormesh( qf_ffbeg_v2, swp_plt_v2, np.transpose(pe_gcav_plt_v2), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1], "Qubit Freq (in MHz)",  swp_params_v2,f"$P_e$ (MIST at $f_{{cav,g}}$)")
# axes[1].invert_yaxis()
save_fig_v2(fig, "P_2d_gcav_qfreq")

# Pg and Pe 2D heatmaps for e-cavity MIST
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
im0 = axes[0].pcolormesh( qf_ffbeg_v2, swp_plt_v2, np.transpose(pg_ecav_plt_v2), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0],  "Qubit Freq (in MHz)", swp_params_v2,f"$P_g$ (MIST at $f_{{cav,e}}$)")
# axes[0].invert_yaxis()

im1 = axes[1].pcolormesh( qf_ffbeg_v2, swp_plt_v2, np.transpose(pe_ecav_plt_v2), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1],  "Qubit Freq (in MHz)", swp_params_v2,f"$P_e$ (MIST at $f_{{cav,e}}$)")
# axes[1].invert_yaxis()
save_fig_v2(fig, "P_2d_ecav_qfreq")

plt.show()
#%%
# Removing effect of qubit decay
# Pg and Pe 2D heatmaps for g-cavity MIST with qubit_freq
pg_gcav_sub = pg_gcav_plt_v2 - pg_gcav_plt_v2[:, 0:1]
pe_gcav_sub = pe_gcav_plt_v2 - pe_gcav_plt_v2[:, 0:1]
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
im0 = axes[0].pcolormesh(qf_ffbeg_v2, swp_plt_v2, np.transpose(pg_gcav_sub), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0],  "Qubit Freq (in MHz)", swp_params_v2,f"$P_g$ (MIST at $f_{{cav,g}}$) -$P_g (power = 0)$")
# axes[0].invert_yaxis()

im1 = axes[1].pcolormesh( qf_ffbeg_v2, swp_plt_v2, np.transpose(pe_gcav_sub), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1], "Qubit Freq (in MHz)",  swp_params_v2,f"$P_e$ (MIST at $f_{{cav,g}}$)-$P_e (power = 0)$")
# axes[1].invert_yaxis()
save_fig_v2(fig, "P_2d_gcav_qfreq_subtr")

# Pg and Pe 2D heatmaps for e-cavity MIST
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
pg_ecav_sub = pg_ecav_plt_v2 - pg_ecav_plt_v2[:, 0:1]
pe_ecav_sub = pe_ecav_plt_v2 - pe_ecav_plt_v2[:, 0:1]

im0 = axes[0].pcolormesh(qf_ffbeg_v2, swp_plt_v2, np.transpose(pg_ecav_sub), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0], "Qubit Freq (in MHz)", swp_params_v2, f"$P_g$ (MIST at $f_{{cav,e}}$)-$P_g (power = 0)$")

im1 = axes[1].pcolormesh(qf_ffbeg_v2, swp_plt_v2, np.transpose(pe_ecav_sub), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1], "Qubit Freq (in MHz)", swp_params_v2, f"$P_e$ (MIST at $f_{{cav,e}}$)-$P_e (power = 0)$")
save_fig_v2(fig, "P_2d_ecav_qfreq_subtr")
plt.show()

#%% Given active subtraction run this
pg_gcav_plt_v2  = np.array(collated_v2["pg_gcav_vs_ff_vs_swp_as"])   # (n_FF, n_swp)
pe_gcav_plt_v2  = np.array(collated_v2["pe_gcav_vs_ff_vs_swp_as"])
pg_ecav_plt_v2  = np.array(collated_v2["pg_ecav_vs_ff_vs_swp_as"])
pe_ecav_plt_v2  = np.array(collated_v2["pe_ecav_vs_ff_vs_swp_as"])

# Pg and Pe 2D heatmaps for g-cavity MIST with qubit_freq
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
im0 = axes[0].pcolormesh(qf_ffbeg_v2, swp_plt_v2, np.transpose(pg_gcav_plt_v2), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0],  "Qubit Freq (in MHz)", swp_params_v2,f"$P_g$ (MIST at $f_{{cav,g}}$)")
# axes[0].invert_yaxis()

im1 = axes[1].pcolormesh( qf_ffbeg_v2, swp_plt_v2, np.transpose(pe_gcav_plt_v2), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1], "Qubit Freq (in MHz)",  swp_params_v2,f"$P_e$ (MIST at $f_{{cav,g}}$)")
# axes[1].invert_yaxis()
save_fig_v2(fig, "P_2d_gcav_qfreq_as")

# Pg and Pe 2D heatmaps for e-cavity MIST
fig, axes = plt.subplots(2, 1, figsize=(14, 5))
im0 = axes[0].pcolormesh( qf_ffbeg_v2, swp_plt_v2, np.transpose(pg_ecav_plt_v2), shading="nearest")
plt.colorbar(im0, ax=axes[0], label="$P_g$")
make_pretty_v2(axes[0],  "Qubit Freq (in MHz)", swp_params_v2,f"$P_g$ (MIST at $f_{{cav,e}}$)")
# axes[0].invert_yaxis()

im1 = axes[1].pcolormesh( qf_ffbeg_v2, swp_plt_v2, np.transpose(pe_ecav_plt_v2), shading="nearest")
plt.colorbar(im1, ax=axes[1], label="$P_e$")
make_pretty_v2(axes[1],  "Qubit Freq (in MHz)", swp_params_v2,f"$P_e$ (MIST at $f_{{cav,e}}$)")
# axes[1].invert_yaxis()
save_fig_v2(fig, "P_2d_ecav_qfreq_as")

plt.show()