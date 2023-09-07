"""
file to create basic initialization of things used for RFSOC This will include: 
- defining names for the attneuators
- defining yoko name
- defining the basic config dict that will state the channels used for all subsequent code
"""

### import relevent libraries
from Protomon.Client_modules.PythonDrivers.control_atten import setatten
from Protomon.Client_modules.PythonDrivers.YOKOGS200 import *
import os
import pyvisa
from pathlib import Path
import Pyro4
from qick import QickConfig

def makeProxy():
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION=4

    ns_host = "192.168.1.7"
    ns_port = 8888
    server_name = "myqick"

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    # print the nameserver entries: you should see the QickSoc proxy
    for k,v in ns.list().items():
        print(k,v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return(soc, soccfg)

soc, soccfg = makeProxy()
# print("debug")

# sys.path.append('..\\ClientModules')

#### issue when adding PythonDrivers due to file location, adding a hacky solution for now
DriverFolderBool = Path(os.getcwd() + '\\PythonDrivers').is_dir()

if DriverFolderBool:
    os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
else:
    path = os.getcwd()
    os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')


#### define a attenuator class to change define attenuators for the setup
class attenuator:
    def __init__(self, serialNum, attenuation_int= 50, print_int = True):
        self.serialNum = serialNum
        self.attenuation = attenuation_int
        setatten(attenu = attenuation_int, serial = self.serialNum, printv = print_int)

    def SetAttenuation(self, attenuation, printOut = False):
        self.attenuation = attenuation
        setatten(attenu = attenuation, serial = self.serialNum, printv = printOut)

# ##### define the attenuators
# cavityAtten = attenuator(27787)
# qubitAtten = attenuator(27797)

##### define yoko
yoko1 = YOKOGS200(VISAaddress = 'USB0::0x0B21::0x0039::91T515414::0::INSTR', rm = pyvisa.ResourceManager())
yoko1.SetMode('voltage')

yoko2 = YOKOGS200(VISAaddress = 'USB0::0x0B21::0x0039::91S929901::0::INSTR', rm = pyvisa.ResourceManager())
yoko2.SetMode('voltage')


#### from jake
###### define default configuration
BaseConfig={
        "res_ch":1, # --Fixed
        "qubit_ch": 3, #3  # --Fixed
        "mixer_freq":0.0, # MHz
        "ro_chs":[0] , # --Fixed
        "reps":1000, # --Fixed
        "nqz": 1, #### refers to cavity
        "qubit_nqz": 2, #1
        "relax_delay": 100, # us
        "res_phase":0, # --Fixed
        "pulse_style": "const", # --Fixed
        "read_length": 5, # units us, previously this was just names "length"
        # Try varying length from 10-100 clock ticks
        "pulse_gain": 0, # [DAC units]
        # Try varying pulse_gain from 500 to 30000 DAC units
        "pulse_freq": 0.0, # [MHz]
        # In this program the signal is up and downconverted digitally so you won't see any frequency
        # components in the I/Q traces below. But since the signal gain depends on frequency,
        # if you lower pulse_freq you will see an increased gain.
        "adc_trig_offset": 0.51, #+ 1, #soc.us2cycles(0.468-0.02), # [Clock ticks]
        # Try varying adc_trig_offset from 100 to 220 clock ticks
        "cavity_LO": 0.0,
       }


