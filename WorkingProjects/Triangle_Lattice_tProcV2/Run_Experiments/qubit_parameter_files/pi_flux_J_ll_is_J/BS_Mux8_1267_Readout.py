from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


# (4125.0, 4424.4, 3790.0, 4050.0, 3534.4, 4280.0, 4000.0, 3700.0)
Readout_1267_FF = FF_gains(
    # [3255, 29001, -8083, -1218, -17000, 12985, -800, -12165]
    [3255, 29001, -8083, -1218, -17000, 15985, -800, -12165]
)

BS1267_Readout = {
    '1': {'Readout': {'Frequency': 7121.6, 'Gain': 800,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4117.0, 'sigma': 0.03, 'Gain': 9269},
          'Pulse_FF': Readout_1267_FF},
    '2': {'Readout': {'Frequency': 7078.1, 'Gain': 1000,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4421.1, 'sigma': 0.03, 'Gain': 4508},
          'Pulse_FF': Readout_1267_FF},
    '3': {'Readout': {'Frequency': 7510.5, 'Gain': 1000,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3777.4, 'sigma': 0.03, 'Gain': 14209},
          'Pulse_FF': Readout_1267_FF},
    '4': {'Readout': {'Frequency': 7568.2, 'Gain': 1200,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4024.6, 'sigma': 0.03, 'Gain': 6666},
          'Pulse_FF': Readout_1267_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 800,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3599.1, 'sigma': 0.03, 'Gain': 8000},
          'Pulse_FF': Readout_1267_FF},
    '6': {'Readout': {'Frequency': 7441.67, 'Gain': 1000,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4318.3, 'sigma': 0.03, 'Gain': 6823},
          'Pulse_FF': Readout_1267_FF},
    '7': {'Readout': {'Frequency': 7253.6, 'Gain': 1000,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3940.8, 'sigma': 0.03, 'Gain': 6740},
          'Pulse_FF': Readout_1267_FF},
    '8': {'Readout': {'Frequency': 7308.67, 'Gain': 1000,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3683.7, 'sigma': 0.03, 'Gain': 5982},
          'Pulse_FF': Readout_1267_FF},

}

# At the alternate beamsplitter point
# [-9729, -10312, 25392, -26783, -23537, -8518, -5572, -22064]
# (3790.0, 3790.0, 4380.0, 3520.0, 3520.0, 3810.0, 3810.0, 3520.0)
# use same readout as 2345 case

# from .BS_Mux8_2345_Readout import Readout_2345_FF, BS2345_Readout
# Readout_1267_FF = Readout_2345_FF
# BS1267_Readout = BS2345_Readout

# This beamsplitter point ended up being worse than the one already used