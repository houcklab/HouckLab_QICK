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
# J_|| = 2J
Voltage_Dictionary = {
    'Q1': -0.468,  # 4030.03
    'Q2': -0.6662,  # 4033.67
    'Q3': -0.4134,  # 3990.75
    'Q4': -0.8272,  # 4040.4
    'Q5': -0.4123,  # 4011.35
    'Q6': -0.7101,  # 4004.53
    'Q7': -0.4943,  # 3949.87
    'Q8': -0.4976,  # 4030.67
    'C1': -1.4398,  # 2906.89
    'C2': -1.468,  # 2865.19
    'C3': -1.4673,  # 2920.27
    'C4': -1.5251,  # 2954.99
    'C5': -1.431,  # 2883.2
    'C6': -1.302,  # 2840.05
}

print(list(Voltage_Dictionary.values()))



# Voltage_Dictionary = {
#     'Q1': -0.1588,  # 4335.88
#     'Q2': -0.2677,  # 4343.7
#     'Q3': -0.0542,  # 4301.97
#     'Q4': -0.432,  # 4358.8
#     'Q5': -0.0386,  # 4316.45
#     'Q6': -0.3296,  # 4304.66
#     'Q7': -0.0891,  # 4252.46
#     'Q8': -0.1958,  # 4341.38
#     'C1': -0.1512,  # 5898.14
#     'C2': -0.2127,  # 5940.39
#     'C3': -0.2311,  # 5865.91
#     'C4': -0.2155,  # 5927.78
#     'C5': -0.2207,  # 5852.44
#     'C6': -0.0452,  # 5955.07
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

