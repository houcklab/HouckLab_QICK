from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (4200.0, 4424.4, 3800.0, 4050.0, 4300.0, 3534.5, 3900.0, 3650.0)
Readout_1245_FF = FF_gains(
    [6719, 29001, -7719, -718, 12011, -28060, -2498, -14219]
)





BS1245_Readout = {
    '1': {'Readout': {'Frequency': 7121.6, 'Gain': 1057,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4193.9, 'sigma': 0.03, 'Gain': 4935},
          'Pulse_FF': Readout_1245_FF},
    '2': {'Readout': {'Frequency': 7078.2, 'Gain': 1100,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4421.3, 'sigma': 0.03, 'Gain': 4206},
          'Pulse_FF': Readout_1245_FF},
    '3': {'Readout': {'Frequency': 7510.6, 'Gain': 1057,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3786.8, 'sigma': 0.03, 'Gain': 12203},
          'Pulse_FF': Readout_1245_FF},
    '4': {'Readout': {'Frequency': 7568.2, 'Gain': 1100,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4038.8, 'sigma': 0.03, 'Gain': 7878},
          'Pulse_FF': Readout_1245_FF},
    '5': {'Readout': {'Frequency': 7363.8, 'Gain': 1100,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4305.3, 'sigma': 0.03, 'Gain': 5580},
          'Pulse_FF': Readout_1245_FF},
    '6': {'Readout': {'Frequency': 7441.0, 'Gain': 1100,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3521.6, 'sigma': 0.03, 'Gain': 6154},
          'Pulse_FF': Readout_1245_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 714,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3896.1, 'sigma': 0.03, 'Gain': 5285},
          'Pulse_FF': Readout_1245_FF},
    '8': {'Readout': {'Frequency': 7308.5, 'Gain': 1057,
                      'FF_Gains': Readout_1245_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3632.8, 'sigma': 0.03, 'Gain': 8952},
          'Pulse_FF': Readout_1245_FF},
}

