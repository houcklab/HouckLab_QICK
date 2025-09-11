from WorkingProjects.Triangle_Lattice_tProcV2.PythonDrivers.SPIRackvoltage import SPIRack, D5aModule
import numpy as np
COM_speed = 1e6  # Baud rate, doesn't matter much
timeout = 1  # In seconds
port = 'COM3'
spi_rack = SPIRack(port, COM_speed, timeout)
D5a = D5aModule(spi_rack, module=2, reset_voltages=False)

span = D5a.range_4V_bi
# span = D5a.range_8V_uni
# span = D5a.range_2V_bi

for i in range(D5a._num_dacs):
    if not D5a.get_settings(i)[1] == span:
        current_settings = D5a.get_settings(i)
        D5a.change_span(i, span)
        D5a.set_voltage(i, current_settings[0])

################

# [Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, C1, C2, C3, C4, C5, C6]
DACs = [1,2,3,4,5,6,7,8,9,10,11,12,13,14]


set_unused_to_zero = True

voltages= [0, 0, 0, 0, 0, 0, 0,
             0, 0, 0, 0, 0, 0, 0]


for DA, vol in zip(DACs, voltages):
    D5a.set_voltage_ramp(DA, vol)

if set_unused_to_zero:
    for i in range(D5a._num_dacs):
        if i not in DACs:
            D5a.set_voltage(i, 0)

for i in range(D5a._num_dacs):
    print(f'{i}: {np.round(D5a.get_settings(i)[0], 4)} V')
spi_rack.close()

# print(spi_rack.get_temperature())
# print(spi_rack.get_battery())
# print(spi_rack.get_firmware_version())

# 0 to 4 Volt: range_4V_uni (span 0)
# -4 to 4 Volt: range_4V_bi (span 2)
# -2 to 2 Volt: range_2V_bi (span 4)

