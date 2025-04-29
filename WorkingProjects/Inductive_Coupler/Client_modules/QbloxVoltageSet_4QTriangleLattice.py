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

# DACs = [9, 8, 5, 1, 3, 12, 10, 14]
DACs = [9, 8, 5, 3, 12, 10, 14]
# 9: left, Q1
# 10: top, Q2

# [Q1, Q2, Q3, Q5, C1, C2, C3]

set_unused_to_zero = True

# for FF comp:
# Q1 point:
# voltages = [ 0.7807963 ,  0.04647115,  0.18626436,  0.08030817, -0.35637378,  0.1416076 , -0.32872708]
# Q2 point:
voltages = [ 0.25878357,  0.62457148,  0.18415756,  0.07845723, -0.35202233,  0.13412093, -0.32358324]
# Q3 point:
# voltages = [ 0.23573584,  0.04690102,  0.71012556,  0.08396278, -0.33299538,  0.14450404, -0.334722  ]
# Q5 point:
# voltages = [ 0.23324958,  0.04924085,  0.17553734,  0.56689095, -0.3328404 ,  0.14592326, -0.32117671]

# Q3 near Q5
# voltages = [ 0.23324958,  0.04924085,  0.7,  0.7, -0.3328404 ,  0.14592326, -0.32117671]

# Q1, Q2, Q3 near resonance
voltages = [0.82,  0.67,  0.67,  0.07845723, -0.3328404 ,  0.14592326, -0.32117671]
voltages = [0.82,  0.60,  0.67,  0.07845723, -0.3328404 ,  0.14592326, -0.32117671] # negative coupling
voltages = [0.82,  0.60,  0.67,  0.07845723, 0.38,  0.14592326, -0.32117671] # positive coupling

# new Q1, Q2, Q3 near point
# voltages = [0.80,  0.60,  0.77,  0.07845723, -0.3328404 ,  0.14592326, -0.32117671] # negative coupling
# voltages = [0.80,  0.60,  0.79,  0.07845723, 0.38,  0.14592326, -0.32117671] # positive coupling

# # Q1, Q3, Q5 near point
# voltages = [0.80,  0.60,  0.70,  0.7, 0.38,  0.14592326, -0.32117671]
# voltages = [0.78,  0.60,  0.72,  0.73, 0.38,  0.14592326, -0.32117671]

# voltages = [0.82,  0,  0.7,  0.07845723, 0.3,  0.14592326, -0.32117671]

# Q1 near Q3
# voltages = [0.82,  0,  0.67,  0.07845723, -0.3328404 ,  0.14592326, -0.32117671]
# new coupler point
# voltages = [0.82,  0,  0.7,  0.07845723, 0.3,  0.14592326, -0.32117671]
# new coupler point
# voltages = [0.82,  0,  0.7,  0.07845723, 0.5,  0.14592326, -0.32117671]

# new coupler point
# voltages = [0.82,  0,  0.60,  0.07845723, -0.5,  0.14592326, -0.32117671]

# Q1 near Q2
# voltages = [0.82,  0.6,  0,  0.07845723, -0.6,  0.14592326, -0.32117671]
# Q2 near Q3
# voltages = [0,  0.6,  0.7,  0.07845723, -0.6,  0.14592326, -0.32117671]

#Q1, Q3, Q5 at 5 GHz
voltages = [ 0.96677828,  0.91902409,  0.9317937 ,  0.87345167, -0.18654002,  0.1141391 , -0.2204914 ]# voltages = [ 0.2,  0.2,  -0.4 ,  0.2, 0.5, -0.6, 0.5]

# voltages = [ 0.2,  -0.5925,  -0.4 ,  0.2, 0.5, -0.6, 0.5]
voltages = [ 0.2,  0.2,  -0.4 ,  0.2, 0.5, -0.6, 0.5]
voltages = [0]*7
voltages = [0, 0, 0, 0, 0, 0.65, 0]
voltages = [-1.174, 0, 0, 0, 0, 0.65, 0]
voltages = [-1.14, 0, 0, 0, 0, 0.65, 0]
# voltages = [-0.35, 0, 0, 0, 0, 0, 0]
voltages = [0, 0, 0, 0, 0, 0.7, 0]

# flux stability scans
voltages = [-0.6, 0, 0, 0, 0, 0, 0]
# voltages = [-0.52, 0, 0, 0, 0, 0, 0]

# currents
voltages = [-0.6, 0, 0, 0, 0, 0.64, 0]


# voltage = {'Q1': 0,
#            'Q2': 0}

# voltages = [0, 0, 0, 0, 0, 0, 0]


# voltages = [-0.4, 0, 0, 0, 0, 0, 0]
# voltages = [-0.52, 0, 0, 0, 0, 0, 0]


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

