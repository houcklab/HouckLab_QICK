from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np

Readout_1278FF = np.array([-9336, -23027, 1858, 11543, -16892, -6878, 5939, 14410])
# (3800.0, 3550.0, 4050.0, 4300.0, 3600.0, 3850.0, 4100.0, 4350.0)
BS1278_Readout = {
    '1': {'Readout': {'Frequency': 7121.25, 'Gain': 750,
                      "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3798.2, 'sigma': 0.03, 'Gain': 4715},
          'Pulse_FF': Readout_1278FF},
    '2': {'Readout': {'Frequency': 7077.05, 'Gain': 1200,
                      "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3603.6, 'sigma': 0.03, 'Gain': 7000},
          'Pulse_FF': Readout_1278FF + [0, 4000, 0, 0, 4000, 0 ,0, 0]},
    '3': {'Readout': {'Frequency': 7511.1, 'Gain': 1000,
                          "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 4054.4, 'sigma': 0.07, 'Gain': 4112},
              'Pulse_FF': Readout_1278FF},
    '4': {'Readout': {'Frequency': 7568.6, 'Gain': 1300,
                      "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4305.4, 'sigma': 0.07, 'Gain': 3105},
          'Pulse_FF': Readout_1278FF},
    '5': {'Readout': {'Frequency': 7362.64, 'Gain': 1200,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 2, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3601.9, 'sigma': 0.07, 'Gain': 3000},
          'Pulse_FF': Readout_1278FF },
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 1000,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3850.2, 'sigma': 0.07, 'Gain': 3463},
          'Pulse_FF': Readout_1278FF},
    '7': {'Readout': {'Frequency': 7254.05, 'Gain': 800,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4103.1, 'sigma': 0.07, 'Gain': 2300},
          'Pulse_FF': Readout_1278FF},
    '8': {'Readout': {'Frequency': 7309.6, 'Gain': 971,
                      'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4338.14, 'sigma': 0.07, 'Gain': 2585},
          'Pulse_FF': Readout_1278FF},
}


# for key in BS1278_Readout:
#     BS1278_Readout[key]['Readout']['Gain'] *= 0.2

# (3550.0, 3800.0, 4300.0, 4150.0, 4000.0, 3900.0, 3650.0, 4200.0)
Readout_1254FF = np.array([-22047, -9897, 16124, 3954, -1024, -6341, -13053, 10250])
Readout_1254FF = np.array([-22047, -9897, 16124, 4554, -1024, -6341, -13053, 10250])
Readout_1254FF = np.array([-22047, -9897, 16124, 5700, -1024, -6341, -13053, 10250]) # Q4 good
Readout_1254FF = np.array([-22047, -9897, 16124, 5700, -2000, -6341, -13053, 10250])
BS1254_Readout = {
    '1': {'Readout': {'Frequency': 7120.95, 'Gain': 1000,
                      "FF_Gains": Readout_1254FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3551.0, 'sigma': 0.03, 'Gain': 4715},
          'Pulse_FF': Readout_1254FF},
    '2': {'Readout': {'Frequency': 7077.15, 'Gain': 1000,
                      "FF_Gains": Readout_1254FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3897, 'sigma': 0.03, 'Gain': 4600},
          'Pulse_FF': Readout_1254FF + [0, 4000, 0, 0, 4000, 0 ,0, 0]},
    '3': {'Readout': {'Frequency': 7511.25, 'Gain': 750,
                          "FF_Gains": Readout_1254FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 4336, 'sigma': 0.07, 'Gain': 3992},
              'Pulse_FF': Readout_1254FF},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 1200,
                      "FF_Gains": Readout_1254FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4191.0, 'sigma': 0.07, 'Gain': 2850},
          'Pulse_FF': Readout_1254FF},
    '5': {'Readout': {'Frequency': 7363.3, 'Gain': 1000,
                      'FF_Gains': Readout_1254FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3976.76, 'sigma': 0.07, 'Gain': 4674},
          'Pulse_FF': Readout_1254FF },
    '6': {'Readout': {'Frequency': 7441.2, 'Gain': 1250,
                      'FF_Gains': Readout_1254FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3862.9, 'sigma': 0.07, 'Gain': 3400},
          'Pulse_FF': Readout_1254FF},
    '7': {'Readout': {'Frequency': 7253.6, 'Gain': 1000,
                      'FF_Gains': Readout_1254FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3619.2, 'sigma': 0.07, 'Gain': 2618},
          'Pulse_FF': Readout_1254FF},
    '8': {'Readout': {'Frequency': 7309.4, 'Gain': 1000,
                      'FF_Gains': Readout_1254FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4266.14, 'sigma': 0.07, 'Gain': 3500},
          'Pulse_FF': Readout_1254FF},
}


# Readout_1278FF = np.array([-9336, -23027, 25392, 27560, -25700, -28060, 25722, 24395])
# # (4245.0, 4245.0, 4380.0, 4435.8, 3514.6, 3514.6, 4325.6, 4418.0)
# BS1278_Readout ={
#     '1': {'Readout': {'Frequency': 7121.0, 'Gain': 1000 - 400,
#                       "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
#           'Qubit': {'Frequency': 3799.2, 'sigma': 0.03, 'Gain': 4715},
#           'Pulse_FF': Readout_1278FF},
#     '2': {'Readout': {'Frequency': 7076.8, 'Gain': 1200 - 300,
#                       "FF_Gains": Readout_1278FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
#           'Qubit': {'Frequency': 3604.6, 'sigma': 0.03, 'Gain': 6500},
#           'Pulse_FF': Readout_1278FF + [0, 4000, 0, 0, 4000, 0 ,0, 0]},
#     '7': {'Readout': {'Frequency': 7254.3, 'Gain': 1000//2,
#                       'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
#           'Qubit': {'Frequency': 4103.1, 'sigma': 0.07, 'Gain': 2300},
#           'Pulse_FF': Readout_1278FF},
#     '8': {'Readout': {'Frequency': 7309.6, 'Gain': 971//2,
#                       'FF_Gains': Readout_1278FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
#           'Qubit': {'Frequency': 4337.14, 'sigma': 0.07, 'Gain': 2585},
#           'Pulse_FF': Readout_1278FF},
#      }