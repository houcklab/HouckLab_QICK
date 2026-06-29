"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attenuators
- defining yoko name
- defining spirack and D5aModule
- defining the basic config dict that will state the channels used for all subsequent code
"""


#Define Save folder
outerFolder = "Z:\\QSimMeasurements\\Measurements\\8QV1_Triangle_Lattice\\"


###### define default configuration
BaseConfig = {
    "res_ch": 8,  # --Fixed
    "qubit_ch": 9,  # --Fixed
    "ro_chs": [0],  # --Fixed, overwritten if using MUX
    "fast_flux_chs": [0,1,2,3,4,5,6,7],
    "fast_flux_delays": [0,0,0,0,0,0,0,0], # Additional delays (us) for each fast flux channel non-"auto" t argument if desired
    "res_nqz": 1,
    "qubit_nqz": 2,
    "mixer_freq": -1750, # 7200  # MHz
    # "qubit_mixer_freq": -1000, # MHz with LO
    "qubit_mixer_freq": 4000, # MHz
    # range=1720.320 MHz, so allowed qubit freqs will be qubit_mixer_freq +- 860 MHz
    # e.g. 3140 MHz to 4860 MHz if mixer at 4000 MHz
    # Should write something to make this dependent on the target qubit frequency

    "relax_delay": 200,  # --Fixed
    "res_phase": 0,  # --Fixed
    "res_length":10,  # length of cavity pulse for readout in us
    "res_LO": 9000,  #in MHz
    "qubit_LO": 0,

}