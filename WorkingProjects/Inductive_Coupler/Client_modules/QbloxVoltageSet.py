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

DACs = [8, 2, 4, 6]
#0, 2 and right
#4, 6 are left
#4(number 3) is right coupler
#6(number 4) is right qubit

# % bottom left qubit
# qubit_2 = int8(0);

# % left coupler
# coupler_1 = int8(2);

# % right coupler
# coupler_2 = int8(4);
#
# % bottom right qubit
# qubit_4 = int8(6);
#

#


#[Left qubit, left coupler, right coupler, right qubit]
# after switching lines in fridge: [right qubit, left coupler, right coupler, left qubit]
voltages = [0, 0, -0.3, 1.4]
# voltages = [-0.6, 0.3, 0, 0]
voltages = [-0.8, 0, 0.549, 0]
voltages = [-1 + -0.01, 0, 0.64533 + (-1) * 0.11667, 0]

voltages = [-0.0, -0.0, 0.0, -0]

# voltages = [-0.59, 0, 0, 0]


set_unused_to_zero = False

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



