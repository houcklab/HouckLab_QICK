from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3900.0, 3730.0, 4160.0, 4380.0, 3830.0, 4050.0, 4270.0, 3600.0))
Readout_3467_FF = np.array(
    [-4000, -13242, 5443, 16460, -7783, 922, 15599, -16604]
)

BS3467_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 714,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3924.3, 'sigma': 0.03, 'Gain': 5001},
          'Pulse_FF': Readout_3467_FF},
    '2': {'Readout': {'Frequency': 7077.1, 'Gain': 1400,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3709.5, 'sigma': 0.03, 'Gain': 7978},
          'Pulse_FF': Readout_3467_FF},
    '3': {'Readout': {'Frequency': 7511.0, 'Gain': 885,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4106.5, 'sigma': 0.03, 'Gain': 18692},
          'Pulse_FF': Readout_3467_FF},
    '4': {'Readout': {'Frequency': 7568.6, 'Gain': 1228,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4326.5, 'sigma': 0.03, 'Gain': 6496},
          'Pulse_FF': Readout_3467_FF},
    '5': {'Readout': {'Frequency': 7363.1, 'Gain': 1057,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3792.0, 'sigma': 0.03, 'Gain': 7412},
          'Pulse_FF': Readout_3467_FF},
    '6': {'Readout': {'Frequency': 7441.4, 'Gain': 1400,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4007.0, 'sigma': 0.03, 'Gain': 9195},
          'Pulse_FF': Readout_3467_FF},
    '7': {'Readout': {'Frequency': 7254.2, 'Gain': 1400,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4242.5, 'sigma': 0.03, 'Gain': 4629},
          'Pulse_FF': Readout_3467_FF},
    '8': {'Readout': {'Frequency': 7308.5, 'Gain': 1057,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3591.6, 'sigma': 0.03, 'Gain': 7001},
          'Pulse_FF': Readout_3467_FF},
}

