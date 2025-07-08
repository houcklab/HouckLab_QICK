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
set_unused_to_zero = True

DAC_Definitions = {
    'Q1': 1,
    'Q2': 2,
    'Q3': 3,
    'Q4': 4,
    'Q5': 5,
    'Q6': 6,
    'Q7': 7,
    'Q8': 8,
    'C1': 9,
    'C2': 10,
    'C3': 11,
    'C4': 12,
    'C5': 13,
    'C6': 14,
}

Voltage_Dictionary = {
    'Q1': 0,
    'Q2': 0,
    'Q3': 0,
    'Q4': 0,
    'Q5': 0,
    'Q6': 0,
    'Q7': 0,
    'Q8': 0,
    'C1': 0,
    'C2': 0,
    'C3': 0,
    'C4': 0,
    'C5': 0,
    'C6': 0
}

Voltage_Dictionary = {
    'Q1': -1.051,  # 3518.8
    'Q2': -0.8461,  # 3699.97
    'Q3': -0.6212,  # 3899.99
    'Q4': -0.5251,  # 4099.98
    'Q5': -1.1352,  # 3503.55
    'Q6': -1.1923,  # 3507.7
    'Q7': -1.1785,  # 3442.08
    'Q8': -1.1936,  # 3506.04
    'C1': -0.1852,  # 5850.93
    'C2': -0.2132,  # 6055.73
    'C3': -0.2413,  # 5782.42
    'C4': -0.2256,  # 5807.07
    'C5': -0.2009,  # 6135.67
    'C6': -0.0939,  # 5884.6
}

# voltages = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
for qubit_labels in DAC_Definitions.keys():
    D5a.set_voltage_ramp(DAC_Definitions[qubit_labels], Voltage_Dictionary[qubit_labels])

if set_unused_to_zero:
    for i in range(D5a._num_dacs):
        if i not in DAC_Definitions.values():
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

