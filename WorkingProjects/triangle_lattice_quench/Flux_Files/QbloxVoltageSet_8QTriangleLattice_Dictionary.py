from WorkingProjects.triangle_lattice_quench.PythonDrivers.SPIRackvoltage import SPIRack, D5aModule
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
    'Q1': -0.4925,  # 4030.03
    'Q2': 0.0,  # 4407.44
    'Q3': -0.409,  # 3990.75
    'Q4': -0.8311,  # 4040.4
    'Q5': -0.3891,  # 4011.35
    'Q6': -0.7215,  # 4004.53
    'Q7': -0.4402,  # 3949.87
    'Q8': -0.5469,  # 4030.67
    'C1': -0.1604,  # 5898.14
    'C2': -0.2287,  # 5940.39
    'C3': -0.2355,  # 5865.91
    'C4': -0.2207,  # 5927.78
    'C5': -0.2165,  # 5852.44
    'C6': -0.0455,  # 5955.07
}

# Pi flux, J_|| = 1J
Voltage_Dictionary = {
     'Q1': -0.4651, #4030.03
     'Q2': 0.0, #4420.64
     'Q3': -0.4159, #3990.75
     'Q4': -0.8507, #4040.4
     'Q5': -0.4226, #4011.35
     'Q6': -0.7274, #4004.53
     'Q7': -0.5037, #3949.87
     'Q8': -0.504, #4030.67
     'C1': -1.6586, #1003.5
     'C2': -1.7438, #729.02
     'C3': -1.6802, #1081.79
     'C4': -1.8016, #1205.31
     'C5': -1.6397, #934.5
     'C6': -1.522, #578.31
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

