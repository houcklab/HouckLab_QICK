from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


# [4015, 4240, 3750, 3918, 3498, 4163, 3817, 3586]
Readout_1267_FF = FF_gains(
     [   229,   13526, -7751,  -2091, -22969,  11356,  -4545, -16089]
)

BS1267_Readout = {
    '1': {'Readout': {'Frequency': 7121.65, 'Gain': 1500,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4011.1, 'sigma': 0.01, 'Gain': 10443},
          'Pulse_FF': Readout_1267_FF},
    '2': {'Readout': {'Frequency': 7078.1, 'Gain': 1500,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4253.7, 'sigma': 0.01, 'Gain': 12000},
          'Pulse_FF': Readout_1267_FF},
    '3': {'Readout': {'Frequency': 7510.65, 'Gain': 1500,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3743.9, 'sigma': 0.015, 'Gain': 16000},
          'Pulse_FF': Readout_1267_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 2400,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3946.4, 'sigma': 0.01, 'Gain': 12561},
          'Pulse_FF': Readout_1267_FF},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 1500,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3507.7, 'sigma': 0.01, 'Gain': 21563},
          'Pulse_FF': Readout_1267_FF},
    '6': {'Readout': {'Frequency': 7441.65, 'Gain': 1750,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4160.9, 'sigma': 0.01, 'Gain': 16000},
          'Pulse_FF': Readout_1267_FF},
    '7': {'Readout': {'Frequency': 7253.85, 'Gain': 1800,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3819.3, 'sigma': 0.01, 'Gain': 9742},
          'Pulse_FF': Readout_1267_FF},
    '8': {'Readout': {'Frequency': 7308.55, 'Gain': 1700,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3598.6, 'sigma': 0.01, 'Gain': 11980},
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