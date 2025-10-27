from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


# (3950.0, 3700.0, 4380.0, 4150.0, 3550.0, 3800.0, 4300.0, 4050.0)
Readout_1234_FF = np.array([-3580, -14218, 25392, 3954, -20123, -8932, 19191, 371])
Readout_1234_FF = np.array([-3580, -17218, 25392, 3954, -20123, -13000, 19191, 371]) # Q2,Q3,Q6

Readout_1234_FF = np.array([-4000, -17218, 25392, 3954, -20123, -13000, 19191, 371]) # 1 good

Readout_1234_FF = np.array([-4000, -17218, 25392, 5500, -20123, -13000, 19191, 371]) # 4 good

Readout_1234_FF = np.array([-4000, -17218, 25392, 5500, -8000, -13000, 19191, 371])


BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.3, 'Gain': 885,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3942.0, 'sigma': 0.03, 'Gain': 5266},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7077.3, 'Gain': 1700,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3646.3, 'sigma': 0.03, 'Gain': 5456},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 970,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4403.8, 'sigma': 0.03, 'Gain': 10665},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.6, 'Gain': 1750,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4195.5, 'sigma': 0.03, 'Gain': 6581},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1228,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3829.0, 'sigma': 0.03, 'Gain': 12999},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 1230,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3720.6, 'sigma': 0.03, 'Gain': 7832},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7254.4, 'Gain': 530,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4308.1, 'sigma': 0.03, 'Gain': 6871},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7309.0, 'Gain': 714,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4061.3, 'sigma': 0.03, 'Gain': 8832},
          'Pulse_FF': Readout_1234_FF},
}



Readout_1278FF = np.array([-9336, -23027, 1858, 11543, -16892, -6878, 5939, 14410])
# (3800.0, 3550.0, 4050.0, 4300.0, 3600.0, 3850.0, 4100.0, 4350.0)



BS1278_Readout = {
    '1': {'Readout': {'Frequency': 7121.25, 'Gain': 750,
                      "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3804.5, 'sigma': 0.03, 'Gain': 4375},
          'Pulse_FF': Readout_1278FF},
    '2': {'Readout': {'Frequency': 7077.05, 'Gain': 1200,
                      "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3611.3, 'sigma': 0.03, 'Gain': 6000},
          'Pulse_FF': Readout_1278FF + [0, 4000, 0, 0, 4000, 0 ,0, 0]},
    '3': {'Readout': {'Frequency': 7511.1, 'Gain': 1000,
                          "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 4067, 'sigma': 0.03, 'Gain': 9000},
              'Pulse_FF': Readout_1278FF},
    '4': {'Readout': {'Frequency': 7568.6, 'Gain': 1300,
                      "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4312, 'sigma': 0.07, 'Gain': 3300},
          'Pulse_FF': Readout_1278FF},
    '5': {'Readout': {'Frequency': 7362.64, 'Gain': 1200,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 2, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3619, 'sigma': 0.07, 'Gain': 3000},
          'Pulse_FF': Readout_1278FF },
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 1000,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3860, 'sigma': 0.07, 'Gain': 3463},
          'Pulse_FF': Readout_1278FF},
    '7': {'Readout': {'Frequency': 7254.05, 'Gain': 800,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4108.5, 'sigma': 0.07, 'Gain': 2050},
          'Pulse_FF': Readout_1278FF},
    '8': {'Readout': {'Frequency': 7309.6, 'Gain': 971,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4356.71, 'sigma': 0.07, 'Gain': 2200},
          'Pulse_FF': Readout_1278FF},
}


