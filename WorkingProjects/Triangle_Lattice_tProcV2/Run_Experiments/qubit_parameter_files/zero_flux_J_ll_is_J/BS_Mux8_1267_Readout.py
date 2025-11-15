from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (4125.0, 4424.4, 3790.0, 4050.0, 3534.4, 4280.0, 4000.0, 3700.0)
Readout_1267_FF = FF_gains(
    [3255, 29001, -8083, -1218, -17000, 12985, -800, -12165]
)

BS1267_Readout = {
    '1': {'Readout': {'Frequency': 7121.65, 'Gain': 500,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4120.3, 'sigma': 0.03, 'Gain': 8406},
          'Pulse_FF': Readout_1267_FF},
    '2': {'Readout': {'Frequency': 7078.1, 'Gain': 1228,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4429.0, 'sigma': 0.03, 'Gain': 4845},
          'Pulse_FF': Readout_1267_FF},
    '3': {'Readout': {'Frequency': 7510.8, 'Gain': 1228,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3792.0, 'sigma': 0.03, 'Gain': 12833},
          'Pulse_FF': Readout_1267_FF},
    '4': {'Readout': {'Frequency': 7568.0, 'Gain': 1400,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4035.2, 'sigma': 0.03, 'Gain': 6379},
          'Pulse_FF': Readout_1267_FF},
    '5': {'Readout': {'Frequency': 7362.65, 'Gain': 900,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3617.2, 'sigma': 0.03, 'Gain': 6315},
          'Pulse_FF': Readout_1267_FF},
    '6': {'Readout': {'Frequency': 7441.9, 'Gain': 1057,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4286.8, 'sigma': 0.03, 'Gain': 7436},
          'Pulse_FF': Readout_1267_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 542,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3948.9, 'sigma': 0.03, 'Gain': 6050},
          'Pulse_FF': Readout_1267_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1400,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3719.6, 'sigma': 0.03, 'Gain': 6395},
          'Pulse_FF': Readout_1267_FF},
}

