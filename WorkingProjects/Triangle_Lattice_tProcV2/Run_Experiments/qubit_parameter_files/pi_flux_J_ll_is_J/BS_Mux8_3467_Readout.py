from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3900.0, 3730.0, 4160.0, 4380.0, 3830.0, 4050.0, 4270.0, 3600.0))
Readout_3467_FF = np.array(
    [-4000, -13242, 5443, 16460, -7783, 922, 15599, -16604]
)

BS3467_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 800,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3937.6, 'sigma': 0.03, 'Gain': 5291},
          'Pulse_FF': Readout_3467_FF},
    '2': {'Readout': {'Frequency': 7076.9, 'Gain': 1000,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3721.4, 'sigma': 0.03, 'Gain': 10519},
          'Pulse_FF': Readout_3467_FF},
    '3': {'Readout': {'Frequency': 7511.2, 'Gain': 800,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4143.6, 'sigma': 0.03, 'Gain': 9594},
          'Pulse_FF': Readout_3467_FF},
    '4': {'Readout': {'Frequency': 7568.9, 'Gain': 1000,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4378.8, 'sigma': 0.03, 'Gain': 9942},
          'Pulse_FF': Readout_3467_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1100,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3819.9, 'sigma': 0.03, 'Gain': 11545},
          'Pulse_FF': Readout_3467_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 800,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4039.6, 'sigma': 0.03, 'Gain': 7558},
          'Pulse_FF': Readout_3467_FF},
    '7': {'Readout': {'Frequency': 7254.1, 'Gain': 1100,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4267.6, 'sigma': 0.03, 'Gain': 6510},
          'Pulse_FF': Readout_3467_FF},
    '8': {'Readout': {'Frequency': 7308.4, 'Gain': 1100,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3583.2, 'sigma': 0.03, 'Gain': 6457},
          'Pulse_FF': Readout_3467_FF},
}

