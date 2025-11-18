from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (4125.0, 4424.4, 3790.0, 4050.0, 3534.4, 4280.0, 4000.0, 3700.0)
Readout_1267_FF = FF_gains(
    # [3255, 29001, -8083, -1218, -17000, 12985, -800, -12165]
    [3255, 29001, -8083, -1218, -17000, 15985, -800, -12165]
)

BS1267_Readout = {
    '1': {'Readout': {'Frequency': 7121.8, 'Gain': 885,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4101.0, 'sigma': 0.03, 'Gain': 10000},
          'Pulse_FF': Readout_1267_FF},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 1228,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4393.7, 'sigma': 0.03, 'Gain': 6796},
          'Pulse_FF': Readout_1267_FF},
    '3': {'Readout': {'Frequency': 7510.8, 'Gain': 714,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3751.7, 'sigma': 0.03, 'Gain': 12166},
          'Pulse_FF': Readout_1267_FF},
    '4': {'Readout': {'Frequency': 7568.5, 'Gain': 1400,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3991.6, 'sigma': 0.03, 'Gain': 13364},
          'Pulse_FF': Readout_1267_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1400,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3576.2, 'sigma': 0.03, 'Gain': 14166},
          'Pulse_FF': Readout_1267_FF},
    '6': {'Readout': {'Frequency': 7442.2, 'Gain': 1400,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4270.6, 'sigma': 0.03, 'Gain': 10036},
          'Pulse_FF': Readout_1267_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 1057,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3922.0, 'sigma': 0.03, 'Gain': 6645},
          'Pulse_FF': Readout_1267_FF},
    '8': {'Readout': {'Frequency': 7308.9, 'Gain': 1057,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3696.6, 'sigma': 0.03, 'Gain': 7173},
          'Pulse_FF': Readout_1267_FF},
}

