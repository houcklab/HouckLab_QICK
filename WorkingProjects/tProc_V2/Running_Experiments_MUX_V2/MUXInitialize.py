"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attenuators
- defining spirack and D5aModule
- defining the basic config dict that will state the channels used for all subsequent code
"""

### import relevent libraries
from WorkingProjects.tProc_V2.socProxy import makeProxy, soc, soccfg
import os
import platform


#Define Save folder
outerFolder = r"Z:\QSimMeasurements\Measurements\RFSOC_tProcV2_test\\"

###### define default configuration
BaseConfig = {
    "res_ch": 4,  # --Fixed
    "no_mux_ch": 1,  # --Fixed
    "qubit_ch": 0,  # --Fixed
    "mixer_freq": 7200,  # MHz
    "ro_chs": [0],  # --Fixed
    "mux_ro_chs": [2, 3, 4, 5, 6, 7, 8, 9],  # -- Fixed
    "reps": 1000,  # --Fixed
    "nqz": 2, #1,  #### refers to cavity
    "qubit_nqz": 2,
    "relax_delay": 200,  # --Fixed
    "res_phase": 0,  # --Fixed
    "pulse_style": "const",  # --Fixed
    "length": 20,  # length of cavity pulse for readout in us
    "pulse_gain": 30000,  # [DAC units]
    "adc_trig_offset": 0.5,  # [us]
    # Try varying adc_trig_offset from 100 to 220 clock ticks
    "cavity_LO": 0, ## 6.50e9,  #in Hz
    "cavity_winding_freq": 1.0903695,
    'cavity_winding_offset': -15.77597
}
FF_channel1 = 8
FF_channel2 = 9
FF_channel3 = 10
FF_channel4 = 11
# FF_channel5 = 12
# FF_channel6 = 13
# FF_channel7 = 14
# FF_channel8 = 15



FF_Qubits = {
    str(1): {'channel': FF_channel1, 'delay_time': 0.005},
    str(2): {'channel': FF_channel2, 'delay_time': 0.00},
    str(3): {'channel': FF_channel3, 'delay_time': 0.002},
    str(4): {'channel': FF_channel4, 'delay_time': 0.00},
}


Additional_Delays = {
    str(1): {'channel': 4, 'delay_time': 0}
}

BaseConfig["Additional_Delays"] = Additional_Delays