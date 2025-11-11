from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (4200.0, 4424.4, 3800.0, 4050.0, 4300.0, 3534.5, 3900.0, 3650.0)
Readout_1254_FF = FF_gains(
    [6719, 29001, -7719, -718, 12011, -28060, -2498, -14219]
)





BS1254_Readout = {
    '1': {'Readout': {'Frequency': 7122.0, 'Gain': 885,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4196.4, 'sigma': 0.03, 'Gain': 4665},
          'Pulse_FF': Readout_1254_FF},
    '2': {'Readout': {'Frequency': 7078.1, 'Gain': 1400,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4428.0, 'sigma': 0.03, 'Gain': 5057},
          'Pulse_FF': Readout_1254_FF},
    '3': {'Readout': {'Frequency': 7510.9, 'Gain': 1400,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3800.0, 'sigma': 0.03, 'Gain': 10500},
          'Pulse_FF': Readout_1254_FF},
    '4': {'Readout': {'Frequency': 7568.0, 'Gain': 885,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4051.1, 'sigma': 0.03, 'Gain': 7645},
          'Pulse_FF': Readout_1254_FF},
    '5': {'Readout': {'Frequency': 7363.6, 'Gain': 1228,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4316.3, 'sigma': 0.03, 'Gain': 7810},
          'Pulse_FF': Readout_1254_FF},
    '6': {'Readout': {'Frequency': 7440.9, 'Gain': 1100,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3538.9, 'sigma': 0.03, 'Gain': 3665},
          'Pulse_FF': Readout_1254_FF},
    '7': {'Readout': {'Frequency': 7254.1, 'Gain': 714,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3904.3, 'sigma': 0.03, 'Gain': 6596},
          'Pulse_FF': Readout_1254_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1100,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3666.9, 'sigma': 0.03, 'Gain': 5755},
          'Pulse_FF': Readout_1254_FF},
}

