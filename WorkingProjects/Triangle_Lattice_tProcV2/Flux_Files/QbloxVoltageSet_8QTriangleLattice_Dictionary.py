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

# 8 qubits, 0 flux
# J_|| = J
Voltage_Dictionary = {
    'Q1': -0.4806,  # 4030.03
    'Q2': -0.6578,  # 4033.67
    'Q3': -0.4143,  # 3990.75
    'Q4': -0.8261,  # 4040.4
    'Q5': -0.4059,  # 4011.35
    'Q6': -0.7114,  # 4004.53
    'Q7': -0.4754,  # 3949.87
    'Q8': -0.5132,  # 4030.67
    'C1': -0.9076,  # 4846.99
    'C2': -0.9753,  # 4881.87
    'C3': -0.9507,  # 4835.27
    'C4': -0.9903,  # 4815.59
    'C5': -0.9176,  # 4856.66
    'C6': -0.8186,  # 4895.26
}
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
     'C4': -1.795, # 1205.31
     'C5': -1.6362, #934.5
     'C6': -1.5171, #578.31
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

