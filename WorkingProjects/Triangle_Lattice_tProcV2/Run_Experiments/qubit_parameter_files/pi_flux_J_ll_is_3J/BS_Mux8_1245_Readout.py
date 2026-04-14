from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np

from .BS_Mux8_2345_Readout import Readout_2345_FF, BS2345_Readout

# With the new beamsplitter points,
# can use same readouts as 2345 case

Readout_1245_FF = Readout_2345_FF
BS1245_Readout = BS2345_Readout

# (4200.0, 4424.4, 3800.0, 4050.0, 4300.0, 3534.5, 3900.0, 3650.0)
# Readout_1245_FF = FF_gains(
#     [6719, 29001, -7719, -718, 12011, -28060, -2498, -14219]
# )





# BS1245_Readout = {
#
#     '1': {'Readout': {'Frequency': 7121.5, 'Gain': 1120,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4194.4, 'sigma': 0.03, 'Gain': 4550},
#           'Pulse_FF': Readout_1245_FF},
#     '2': {'Readout': {'Frequency': 7078.1, 'Gain': 1100,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4421.6, 'sigma': 0.03, 'Gain': 4213},
#           'Pulse_FF': Readout_1245_FF},
#     '3': {'Readout': {'Frequency': 7510.5, 'Gain': 1120,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3786.7, 'sigma': 0.03, 'Gain': 14058},
#           'Pulse_FF': Readout_1245_FF},
#     '4': {'Readout': {'Frequency': 7568.4, 'Gain': 1100,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 2,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4037.8, 'sigma': 0.03, 'Gain': 7114},
#           'Pulse_FF': Readout_1245_FF},
#     '5': {'Readout': {'Frequency': 7363.4, 'Gain': 1140,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4305.3, 'sigma': 0.03, 'Gain': 5934},
#           'Pulse_FF': Readout_1245_FF},
#     '6': {'Readout': {'Frequency': 7440.6, 'Gain': 1140,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3521.3, 'sigma': 0.03, 'Gain': 5794},
#           'Pulse_FF': Readout_1245_FF},
#     '7': {'Readout': {'Frequency': 7253.7, 'Gain': 1160,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3896.2, 'sigma': 0.03, 'Gain': 5190},
#           'Pulse_FF': Readout_1245_FF},
#     '8': {'Readout': {'Frequency': 7308.7, 'Gain': 1080,
#                       'FF_Gains': Readout_1245_FF, 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3632.6, 'sigma': 0.03, 'Gain': 8506},
#           'Pulse_FF': Readout_1245_FF},
# }
#
