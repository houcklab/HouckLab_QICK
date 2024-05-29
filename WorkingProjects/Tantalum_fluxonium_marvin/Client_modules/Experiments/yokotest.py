#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *

volt = 0
yoko1.SetVoltage(volt)
print("Voltage is ", yoko1.GetVoltage(), " Volts")