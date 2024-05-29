#%%
import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.LS370 as lk
import pyvisa
import time
import numpy as np
import os
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.YOKOGS200 import *

########################################################################################################################
#                                              Connect to instruments                                                  #
########################################################################################################################
rm = pyvisa.ResourceManager()
LS370_connection = rm.open_resource('GPIB0::12::INSTR')
lakeshore = lk.Lakeshore370(LS370_connection)

# define yoko 1
# Cooldown 9: C1 on-chip flux bias line
yoko1 = YOKOGS200(VISAaddress = 'GPIB0::4::INSTR', rm = visa.ResourceManager())
yoko1.SetMode('voltage')

# define yoko 2
# Cooldown 9: C2 external magnet
yoko2 = YOKOGS200(VISAaddress = 'GPIB0::5::INSTR', rm = visa.ResourceManager())
yoko1.SetMode('voltage')

########################################################################################################################
#                                                  Set parameters                                                      #
########################################################################################################################
yoko = yoko1
delay = 5*60

foldername = r'Z:\TantalumFluxonium\Data\2024_04_12_BF2_cooldown_9\WTF\MeasureTempVsYoko'
filename_voltage = foldername + '\\' + 'on_chip' + time.strftime('%Y.%m.%d_%H.%M.%S_', time.localtime()) + 'voltage.csv'
filename_temp = foldername + '\\' + 'on_chip' + time.strftime('%Y.%m.%d_%H.%M.%S_', time.localtime()) + 'temp.csv'
filename_res = foldername + '\\' + 'on_chip' + time.strftime('%Y.%m.%d_%H.%M.%S_', time.localtime()) + 'res.csv'

NUM_PTS = 15 # Number of points at each yoko voltage


voltages_list = [-2.894e+1, -2.372e+1, -1.850e+1, -1.328e+1, -8.056e+0, -2.836e+0, 2.384e+0, 7.604e+0]
#voltages_list = [−2.792e+1, −2.004e+1, −1.216e+1, −4.280e+0, 3.600e+0, 1.148e+1]

voltages_meas_list = []
temps_meas_list = []
res_meas_list = []

yoko1.SetVoltage(0)
yoko2.SetVoltage(0)
lakeshore.set_temp_control_mode(4) # turn off PID

for voltage in voltages_list:
    yoko.SetVoltage(voltage)
    print('Current voltage: %.5f V' % yoko.GetVoltage())
    time.sleep(60)

    for i in range(NUM_PTS):
        print('Current voltage1: %.5f V' % yoko1.GetVoltage())
        print('Current voltage2: %.5f V' % yoko2.GetVoltage())
        voltages_meas_list.append(yoko.GetVoltage())
        print('Current temperature: %.5f K' % float(lakeshore.get_temp(7)))
        temps_meas_list.append(float(lakeshore.get_temp(7)))
        print('Current resistance: %.1f Ohm' % float(lakeshore.get_resistance(8)))
        res_meas_list.append(float(lakeshore.get_resistance(8)))
        os.makedirs(os.path.dirname(filename_temp), exist_ok=True) # Create necessary directories if the file path does not exist
        np.savetxt(filename_voltage, np.array(voltages_meas_list), delimiter = ',', fmt='%.5f')
        np.savetxt(filename_temp, np.array(temps_meas_list), delimiter = ',', fmt='%.5f')
        np.savetxt(filename_res, np.array(res_meas_list), delimiter=',', fmt='%.5f')
        time.sleep(delay)

yoko1.SetVoltage(0)
yoko2.SetVoltage(0)



time.sleep(600) # Time to cool back down


## External magnet
yoko = yoko2
delay = 20*60

NUM_PTS = 15

foldername = r'Z:\TantalumFluxonium\Data\2024_04_12_BF2_cooldown_9\WTF\MeasureTempVsYoko'
filename_voltage = foldername + '\\' + 'external' + time.strftime('%Y.%m.%d_%H.%M.%S_', time.localtime()) + 'voltage.csv'
filename_temp = foldername + '\\' + 'external' + time.strftime('%Y.%m.%d_%H.%M.%S_', time.localtime()) + 'temp.csv'
filename_res = foldername + '\\' + 'external' + time.strftime('%Y.%m.%d_%H.%M.%S_', time.localtime()) + 'res.csv'

voltages_list = [-2.792e+1, -2.004e+1, -1.216e+1, -4.280e+0, 3.600e+0, 1.148e+1]

voltages_meas_list = []
temps_meas_list = []
res_meas_list = []

yoko1.SetVoltage(0)
yoko2.SetVoltage(0)
lakeshore.set_temp_control_mode(4) # turn off PID

for voltage in voltages_list:
    print('Setting voltage to %.5f V' % voltage)
    yoko.SetVoltage(voltage)
    print('Current voltage: %.5f V' % yoko.GetVoltage())
    time.sleep(delay)

    for i in range(NUM_PTS):
        print('Current voltage1: %.5f V' % yoko1.GetVoltage())
        print('Current voltage2: %.5f V' % yoko2.GetVoltage())
        voltages_meas_list.append(yoko.GetVoltage())
        print('Current temperature: %.5f K' % float(lakeshore.get_temp(7)))
        temps_meas_list.append(float(lakeshore.get_temp(7)))
        print('Current resistance: %.1f Ohm' % float(lakeshore.get_resistance(8)))
        res_meas_list.append(float(lakeshore.get_resistance(8)))
        os.makedirs(os.path.dirname(filename_temp), exist_ok=True) # Create necessary directories if the file path does not exist
        np.savetxt(filename_voltage, np.array(voltages_meas_list), delimiter = ',', fmt='%.5f')
        np.savetxt(filename_temp, np.array(temps_meas_list), delimiter = ',', fmt='%.5f')
        np.savetxt(filename_res, np.array(res_meas_list), delimiter=',', fmt='%.5f')
        time.sleep(60)

yoko1.SetVoltage(0)
yoko2.SetVoltage(0)
