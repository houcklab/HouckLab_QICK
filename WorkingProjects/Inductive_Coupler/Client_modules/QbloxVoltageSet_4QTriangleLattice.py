from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.SPIRackvoltage import SPIRack, D5aModule
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
# [Q1, Q2, Q3, Q4, C12, C13, C23, C24, C34]
# DACs = [10, 8, 5, 1, 14, 3, 9, 12]
# DACs = [8, 5, 1, 14, 3, 9, 12, 10]
DACs = [8, 3, 5, 1, 9, 12, 10, 14]

# [Q1, Q2, Q3, Q4, Q5, C1, C2, C3]

set_unused_to_zero = True

# voltages = [-0.35426907, -0.02715096,  0.86940978, -0.53871474, -0.90805125,  0.18447422, -0.01253328,  0.15292178]
voltages = [ 0.81378277, -0.69906829, -0.40077118, -0.48958588, -0.27726668,  0.40701021, -0.45454816,  0.21204609]
voltages = [1.117, 1.164, 1.835, 1.833, 1.726, 0.417, -0.486, 0.147]
voltages = [0.774, 0.794, 1.215, 1.178, 1.155, 0.415, -0.479, 0.167]
voltages = [0.774, 0.794, 1.215, 1.178, 1.02, 0.415, -0.479, 0.167]
# voltages = [1.429, 0.784, 1.225, 1.173, 1.165, 0.404, -0.485, 0.157]
voltages = [ 0.2096934 , -0.68737056, -0.41141405, -0.48374132, -0.28766228,  0.4193564 , -0.44729381,  0.2225933 ]
# voltages = [1.315, 0.435, 1.148, 1.101, 1.371, 0.413, -0.479, 0.16]
#
voltages = [ 0 , -0.68737056, -0.41141405, -0.48374132, -0.28766228,  0.4193564 , -0.44729381,  0.2225933 ]
voltages = [ 0 , 0.4, 0, 0, 0, 0, 0, 0 ]


# # for flux stability measurement
# voltages = [0, 0, 0, 0, -1.1, 0.5, -0.5, 0.4]
# # voltages = [-1.1, 0, 0, 0, 0, 0.5, -0.5, 0.4]
# voltages = [1, -1, 1, 1, -1.1, 0.5, -0.5, 0.4]
# voltages = [1, 1, 1, 1, -0.87, 0.5, -0.5, 0.4]
# voltages = [0, 0, 0, 0, -0.95, 0.5, -0.5, 0.4]
voltages = [0, 0, 0, 0, 0.4, 0.5, -0.5, 0.4]

voltages = [0, 0, 0, 0, 0, 0, 0, 0 ]


# voltages = [4, 0.784, 1.225, 1.173, 1.165, 0.404, -0.485, 0.157]
# voltages = [1.429, 0.784, 1.225, 1.173, 1.165, 0.404, -0.485, 0.157]
#voltages = [1.431, 1.411, 1.658, 1.597, 1.576, 0.404, -0.497, 0.143]
#voltages = [0.812, 1.423, 1.648, 1.603, 1.565, 0.417, -0.49, 0.154]
#voltages = [1.286, 1.414, 1.656, 1.598, 1.573, 0.407, -0.496, 0.146]
#voltages = [0, 0, 0, 0, 0, 0, 0, 0]

## FF4 compensation
# voltages = [-0.33612469, -0.66280266, -0.41855833,  0.15653027, -0.30701882,  0.42077926, -0.43229764,  0.24063139]
################
#
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



