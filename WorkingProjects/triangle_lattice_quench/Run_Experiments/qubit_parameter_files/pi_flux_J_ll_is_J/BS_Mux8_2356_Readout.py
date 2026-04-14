from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 4000.0, 4280.0, 3690.0, 3850.0)
Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12985, -10406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12985, -12406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12000, -12406, -6771])


Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1000, 12000, -12406, -6771])

Readout_2356_FF = np.array([-20357, 4582, 22495, -12609, -1000, 12000, -12406, -6771])



BS2356_Readout = {
    '1': {'Readout': {'Frequency': 7120.9, 'Gain': 1000,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3570.4, 'sigma': 0.03, 'Gain': 8194},
          'Pulse_FF': Readout_2356_FF},
    '2': {'Readout': {'Frequency': 7077.8, 'Gain': 1300,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4143.5, 'sigma': 0.03, 'Gain': 4862},
          'Pulse_FF': Readout_2356_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1057,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4388.6, 'sigma': 0.03, 'Gain': 12828},
          'Pulse_FF': Readout_2356_FF},
    '4': {'Readout': {'Frequency': 7567.9, 'Gain': 1200,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3727.9, 'sigma': 0.03, 'Gain': 11200},
          'Pulse_FF': Readout_2356_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1000,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4000.0, 'sigma': 0.03, 'Gain': 7465},
          'Pulse_FF': Readout_2356_FF},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 800,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4260.7, 'sigma': 0.03, 'Gain': 9854},
          'Pulse_FF': Readout_2356_FF},
    '7': {'Readout': {'Frequency': 7253.6, 'Gain': 800,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3635.2, 'sigma': 0.03, 'Gain': 7783},
          'Pulse_FF': Readout_2356_FF},
    '8': {'Readout': {'Frequency': 7308.7, 'Gain': 1200,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3830.3, 'sigma': 0.03, 'Gain': 6075},
          'Pulse_FF': Readout_2356_FF},
}

