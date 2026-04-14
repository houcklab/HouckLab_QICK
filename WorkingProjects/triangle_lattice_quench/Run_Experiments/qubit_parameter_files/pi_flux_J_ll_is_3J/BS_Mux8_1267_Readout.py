from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


# (4125.0, 4424.4, 3790.0, 4050.0, 3534.4, 4280.0, 4000.0, 3700.0)
Readout_1267_FF = FF_gains(
    # [3255, 29001, -8083, -1218, -17000, 15985, -800, -12165]
     [  3091,  29001,  -8000,  -1500, -25900,  28060,  -1049, -12989]
)

BS1267_Readout = {
    '1': {'Readout': {'Frequency': 7121.7, 'Gain': 700,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4120.8, 'sigma': 0.03, 'Gain': 7980},
          'Pulse_FF': Readout_1267_FF},
    '2': {'Readout': {'Frequency': 7078.1, 'Gain': 850,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4428.8, 'sigma': 0.03, 'Gain': 4785},
          'Pulse_FF': Readout_1267_FF},
    '3': {'Readout': {'Frequency': 7510.8, 'Gain': 830,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3803.2, 'sigma': 0.03, 'Gain': 14150},
          'Pulse_FF': Readout_1267_FF},
    '4': {'Readout': {'Frequency': 7568.2, 'Gain': 1000,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4034.0, 'sigma': 0.03, 'Gain': 6350},
          'Pulse_FF': Readout_1267_FF},
    '5': {'Readout': {'Frequency': 7362.65, 'Gain': 933,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3555.0, 'sigma': 0.03, 'Gain': 18400},
          'Pulse_FF': Readout_1267_FF},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 850,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4409.7, 'sigma': 0.03, 'Gain': 7613},
          'Pulse_FF': Readout_1267_FF},
    '7': {'Readout': {'Frequency': 7253.7, 'Gain': 466,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3943.7, 'sigma': 0.03, 'Gain': 7329},
          'Pulse_FF': Readout_1267_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1000,
                      'FF_Gains': Readout_1267_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3703.0, 'sigma': 0.03, 'Gain': 6731},
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