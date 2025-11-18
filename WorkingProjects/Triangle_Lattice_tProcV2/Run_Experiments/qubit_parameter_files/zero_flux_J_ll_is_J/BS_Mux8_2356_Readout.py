from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 4000.0, 4280.0, 3690.0, 3850.0)
Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12985, -10406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12985, -12406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12000, -12406, -6771])


Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1000, 12000, -12406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 22495, -12609, -1000, 12000, -12406, -6771])



BS2356_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 885,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3562.0, 'sigma': 0.03, 'Gain': 8168},
          'Pulse_FF': Readout_2356_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 1400,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4125.2, 'sigma': 0.03, 'Gain': 7170},
          'Pulse_FF': Readout_2356_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1057,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4334.9, 'sigma': 0.03, 'Gain': 11654},
          'Pulse_FF': Readout_2356_FF},
    '4': {'Readout': {'Frequency': 7567.9, 'Gain': 1228,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3703.2, 'sigma': 0.03, 'Gain': 10327},
          'Pulse_FF': Readout_2356_FF},
    '5': {'Readout': {'Frequency': 7363.1, 'Gain': 900,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3971.3, 'sigma': 0.03, 'Gain': 9827},
          'Pulse_FF': Readout_2356_FF},
    '6': {'Readout': {'Frequency': 7441.8, 'Gain': 1228,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4217.7, 'sigma': 0.03, 'Gain': 5949},
          'Pulse_FF': Readout_2356_FF},
    '7': {'Readout': {'Frequency': 7253.7, 'Gain': 1000,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3620.8, 'sigma': 0.03, 'Gain': 5432},
          'Pulse_FF': Readout_2356_FF},
    '8': {'Readout': {'Frequency': 7309.1, 'Gain': 1057,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3846.9, 'sigma': 0.03, 'Gain': 7696},
          'Pulse_FF': Readout_2356_FF},
}

