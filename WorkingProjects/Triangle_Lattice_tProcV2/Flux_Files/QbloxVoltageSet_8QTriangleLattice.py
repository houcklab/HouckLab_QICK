from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.SPIRackvoltage import SPIRack, D5aModule
import numpy as np
COM_speed = 1e6  # Baud rate, doesn't matter much
timeout = 1  # In seconds
port = 'COM3'
spi_rack = SPIRack(port, COM_speed, timeout)
D5a = D5aModule(spi_rack, module=2, reset_voltages=False, ramp_step=0.003, ramp_interval=0.01)

span = D5a.range_4V_bi
# span = D5a.range_8V_uni

# span = D5a.range_2V_bi

for i in range(D5a._num_dacs):
    if not D5a.get_settings(i)[1] == span:
        current_settings = D5a.get_settings(i)
        D5a.change_span(i, span)
        D5a.set_voltage(i, current_settings[0])

################
# [Q1, Q2, Q3, Q4, C12, C13, C23, C24, C34]

# DACs = [9, 8, 5, 1, 3, 12, 10, 14]
# DACs = [9, 8, 5, 1, 3, 12, 10, 14]
# 9: left, Q1
# 10: top, Q2
# DACs = [9, 10]
# [Q1, Q2]

set_unused_to_zero = True

DACs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
voltages = [-0.65, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
voltages = [0, -0.65, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
voltages = [0, 0, 0, 0, -0.8, 0, 0, 0, 0, 0, 0, 0, 0, 0]
voltages = [0, 0, 0, 0, 0, -0.65, 0, 0, 0, 0, 0, 0, 0, 0]
voltages = [0, 0, 0, 0, 0, 0, -0.6, 0, 0, 0, 0, 0, 0, 0]
voltages = [0, 0, 0, 0, 0, -0.55, 0, 0, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5]


voltages = [-1.1,0, -1.1, -1.1, -1.1, -1.1, -1.1, -1.1,
            0., 0., 0., 0., 0., 0.]

voltages = [-1, 0, -0.6, 0, 0, 0, 0, 0,
            -0.8, 0, 0, 0, 0, 0]

voltages = [0.0743, 1.4213, -0.1825, 1.3751, 1.2473, 1.3359, 1.2115, 1.1834,
            0.5, 1.5641, 1.4432, 1.6475, 1.4175, 1.4889]

print(len(DACs))
print(len(voltages))




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

