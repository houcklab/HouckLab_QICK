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

# 8 Qubits, Pi Flux
Voltage_Dictionary = {
     'Q1': -0.4631, #4030.03
     'Q2': -0.6709, #4033.67
     'Q3': -0.4132, #3990.75
     'Q4': -0.8283, #4040.4
     'Q5': -0.415, #4011.35
     'Q6': -0.7096, #4004.53
     'Q7': -0.5018, #3949.87
     'Q8': -0.5162, #4030.67
     'C1': -1.6525, #1003.5
     'C2': -1.7336, #729.02
     'C3': -1.6746, #1081.79
     'C4': -1.795, #1205.31
     'C5': -1.6362, #934.5
     'C6': -1.5171, #578.31
}


# Voltage_Dictionary = {
#     'Q1': -0.7153,  # 3800.0
#     'Q2': -1.6453,  # 3802.15
#     'Q3': 0.1514,  # 4366.39
#     'Q4': -0.1567,  # 4424.81
#     'Q5': 0.1643,  # 4379.97
#     'Q6': -0.0636,  # 4367.24
#     'Q7': 0.1193,  # 4315.28
#     'Q8': 0.0823,  # 4405.78
#     'C1': -0.1271,  # 5898.14
#     'C2': -0.1792,  # 5940.39
#     'C3': -0.2087,  # 5865.91
#     'C4': -0.1921,  # 5927.78
#     'C5': -0.2058,  # 5852.44
#     'C6': -0.0361,  # 5955.07
# }



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

