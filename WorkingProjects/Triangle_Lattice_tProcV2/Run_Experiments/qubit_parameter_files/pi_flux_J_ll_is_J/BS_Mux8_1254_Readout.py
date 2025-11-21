from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (4200.0, 4424.4, 3800.0, 4050.0, 4300.0, 3534.5, 3900.0, 3650.0)
Readout_1254_FF = FF_gains(
    [6719, 29001, -7719, -718, 12011, -28060, -2498, -14219]
)





BS1254_Readout = {
    '1': {'Readout': {'Frequency': 7121.9, 'Gain': 885,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4175.3, 'sigma': 0.03, 'Gain': 5729},
          'Pulse_FF': Readout_1254_FF},
    '2': {'Readout': {'Frequency': 7078.2, 'Gain': 1057,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4395.0, 'sigma': 0.03, 'Gain': 6467},
          'Pulse_FF': Readout_1254_FF},
    '3': {'Readout': {'Frequency': 7511.1, 'Gain': 1228,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3761.1, 'sigma': 0.03, 'Gain': 7256},
          'Pulse_FF': Readout_1254_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1400,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4004.2, 'sigma': 0.03, 'Gain': 10649},
          'Pulse_FF': Readout_1254_FF},
    '5': {'Readout': {'Frequency': 7363.6, 'Gain': 1057,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4258.4, 'sigma': 0.03, 'Gain': 6442},
          'Pulse_FF': Readout_1254_FF},
    '6': {'Readout': {'Frequency': 7440.8, 'Gain': 1057,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3502.3, 'sigma': 0.03, 'Gain': 12093},
          'Pulse_FF': Readout_1254_FF},
    '7': {'Readout': {'Frequency': 7254.0, 'Gain': 714,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3877.0, 'sigma': 0.03, 'Gain': 3826},
          'Pulse_FF': Readout_1254_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1057,
                      'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3644.2, 'sigma': 0.03, 'Gain': 9577},
          'Pulse_FF': Readout_1254_FF},

}

