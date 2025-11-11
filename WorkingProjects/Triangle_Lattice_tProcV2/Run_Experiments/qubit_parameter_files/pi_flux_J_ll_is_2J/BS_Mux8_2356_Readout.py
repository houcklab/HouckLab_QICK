from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 4000.0, 4280.0, 3690.0, 3850.0)
Readout_2356_FF = np.array([-20357, 4582, 21495, -11609, -1488, 12985, -10406, -6771])



BS2356_Readout = {
    '1': {'Readout': {'Frequency': 7120.9, 'Gain': 1057,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3576.0, 'sigma': 0.03, 'Gain': 7738},
          'Pulse_FF': Readout_2356_FF},
    '2': {'Readout': {'Frequency': 7077.5, 'Gain': 1000,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4148.1, 'sigma': 0.03, 'Gain': 4501},
          'Pulse_FF': Readout_2356_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1228,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4391.6, 'sigma': 0.03, 'Gain': 11999},
          'Pulse_FF': Readout_2356_FF},
    '4': {'Readout': {'Frequency': 7567.8, 'Gain': 1228,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3766.0, 'sigma': 0.03, 'Gain': 6969},
          'Pulse_FF': Readout_2356_FF},
    '5': {'Readout': {'Frequency': 7363.0, 'Gain': 885,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4000.7, 'sigma': 0.03, 'Gain': 7478},
          'Pulse_FF': Readout_2356_FF},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 1228,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4285.4, 'sigma': 0.03, 'Gain': 7899},
          'Pulse_FF': Readout_2356_FF},
    '7': {'Readout': {'Frequency': 7253.6, 'Gain': 1057,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3694.6, 'sigma': 0.03, 'Gain': 8332},
          'Pulse_FF': Readout_2356_FF},
    '8': {'Readout': {'Frequency': 7308.8, 'Gain': 885,
                      'FF_Gains': Readout_2356_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3868.6, 'sigma': 0.03, 'Gain': 5550},
          'Pulse_FF': Readout_2356_FF},
}

