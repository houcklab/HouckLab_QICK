from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3900.0, 3730.0, 4160.0, 4380.0, 3830.0, 4050.0, 4270.0, 3600.0))
Readout_3467_FF = np.array(
    [ -4456, -14131,   5040,  27560,  -8393,   -121,  15256, -24395]
)

BS3467_Readout = {
    '1': {'Readout': {'Frequency': 7121.45, 'Gain': 650,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3934.1, 'sigma': 0.03, 'Gain': 4937},
          'Pulse_FF': Readout_3467_FF},
    '2': {'Readout': {'Frequency': 7077.0, 'Gain': 1033,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3714.6, 'sigma': 0.03, 'Gain': 11342},
          'Pulse_FF': Readout_3467_FF},
    '3': {'Readout': {'Frequency': 7510.9, 'Gain': 666,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4149.6, 'sigma': 0.03, 'Gain': 8330},
          'Pulse_FF': Readout_3467_FF},
    '4': {'Readout': {'Frequency': 7568.6, 'Gain': 1216,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4462.4, 'sigma': 0.03, 'Gain': 7394},
          'Pulse_FF': Readout_3467_FF},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 1016,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3823.6, 'sigma': 0.03, 'Gain': 12099},
          'Pulse_FF': Readout_3467_FF},
    '6': {'Readout': {'Frequency': 7441.2, 'Gain': 1033,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4033.9, 'sigma': 0.03, 'Gain': 7545},
          'Pulse_FF': Readout_3467_FF},
    '7': {'Readout': {'Frequency': 7254.2, 'Gain': 750,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4270.1, 'sigma': 0.03, 'Gain': 7097},
          'Pulse_FF': Readout_3467_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1216,
                      'FF_Gains': Readout_3467_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3533.9, 'sigma': 0.03, 'Gain': 4906},
          'Pulse_FF': Readout_3467_FF},

}

