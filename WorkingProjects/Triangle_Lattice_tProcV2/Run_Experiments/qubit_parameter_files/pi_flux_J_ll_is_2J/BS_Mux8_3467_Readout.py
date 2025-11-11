from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3900.0, 3730.0, 4160.0, 4380.0, 3830.0, 4050.0, 4270.0, 3600.0))
Readout_3467_FF = np.array(
    [-4000, -13242, 5443, 16460, -7783, 922, 15599, -16604]
)

BS3467_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 885,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3940.9, 'sigma': 0.03, 'Gain': 4999},
          'Pulse_FF': Readout_3467_FF},
    '2': {'Readout': {'Frequency': 7077.1, 'Gain': 1400,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3726.2, 'sigma': 0.03, 'Gain': 9666},
          'Pulse_FF': Readout_3467_FF},
    '3': {'Readout': {'Frequency': 7511.2, 'Gain': 1057,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4154.4, 'sigma': 0.03, 'Gain': 7643},
          'Pulse_FF': Readout_3467_FF},
    '4': {'Readout': {'Frequency': 7568.8, 'Gain': 1057,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4387.4, 'sigma': 0.03, 'Gain': 10166},
          'Pulse_FF': Readout_3467_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1400,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3833.4, 'sigma': 0.03, 'Gain': 12814},
          'Pulse_FF': Readout_3467_FF},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 714,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4051.7, 'sigma': 0.03, 'Gain': 7486},
          'Pulse_FF': Readout_3467_FF},
    '7': {'Readout': {'Frequency': 7254.5, 'Gain': 1057,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4272.2, 'sigma': 0.03, 'Gain': 6558},
          'Pulse_FF': Readout_3467_FF},
    '8': {'Readout': {'Frequency': 7308.8, 'Gain': 885,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3615.5, 'sigma': 0.03, 'Gain': 6306},
          'Pulse_FF': Readout_3467_FF},
}

