"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attenuators
- defining yoko name
- defining spirack and D5aModule
- defining the basic config dict that will state the channels used for all subsequent code
"""

from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy, soc, soccfg
import os
import platform

try:
    if 'macOS' in platform.platform():
        if "LD_LIBRARY_PATH" in os.environ.keys():
            os.environ["LD_LIBRARY_PATH"] += ":.\\..\\PythonDrivers"
        else:
            os.environ["LD_LIBRARY_PATH"] = ".\\..\\PythonDrivers"
    else:
        os.add_dll_directory(os.getcwd() + '\\..\\PythonDrivers')
except:
    pass

#Define Save folder
outerFolder = "Z:\\QSimMeasurements\\Measurements\\8QV1_Triangle_Lattice\\"


###### define default configuration
BaseConfig = {
    "res_ch": 8,  # --Fixed
    "qubit_ch": 9,  # --Fixed
    "ro_chs": [0, 1, 2, 3],  # --Fixed
    "fast_flux_chs": [0,1,2,3,4,5,6,7],
    "res_nqz": 1,
    "qubit_nqz": 2,
    "mixer_freq": -1200, # 7200  # MHz
    # "qubit_mixer_freq": -1000, # MHz with LO
    "qubit_mixer_freq": 4000, # MHz
    # range=1720.320 MHz, so allowed qubit freqs will be qubit_mixer_freq +- 860 MHz
    # e.g. 3140 MHz to 4860 MHz if mixer at 4000 MHz
    # Should write something to make this dependent on the target qubit frequency

    "relax_delay": 200,  # --Fixed
    "res_phase": 0,  # --Fixed
    "res_length": 20,  # length of cavity pulse for readout in us
    # "adc_trig_delay": 0.3,  # Between 0.3 and 0.5 usually [us]
    "res_LO": 9000,  #in MHz
    "qubit_LO": 0,
}



### Lets do this within the waveform from now on instead, since it gives better resolution
FF_Qubits = {
    str(1): {'channel': 0, 'delay_time': 0.000},
    str(2): {'channel': 1, 'delay_time': 0.000},
    str(3): {'channel': 2, 'delay_time': 0.000},
    str(4): {'channel': 3, 'delay_time': 0.000},
    str(5): {'channel': 4, 'delay_time': 0.000},
    str(6): {'channel': 5, 'delay_time': 0.000},
    str(7): {'channel': 6, 'delay_time': 0.000},
    str(8): {'channel': 7, 'delay_time': 0.000},
}

Additional_Delays = {
    str(1): {'channel': 4, 'delay_time': 0}
}

BaseConfig["Additional_Delays"] = Additional_Delays