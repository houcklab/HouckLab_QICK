# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mFFRamseyCalibration import \
    FFRamseyCal
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mT1vsFF import FFvsT1
from WorkingProjects.Triangle_Lattice_tProcV2.Flux_Files.QbloxVoltageSet_function import spi_rack, set_voltages
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import Compensated_Pulse
import numpy as np



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.6, 'Gain': 4500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1., 'cavmin': True},
          'Qubit': {'Frequency': 4028.5, 'sigma': 0.05, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.7, 'Gain': 6500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1., 'cavmin': True},
          'Qubit': {'Frequency': 4029.7, 'sigma': 0.05, 'Gain': 2450},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7511.0, 'Gain': 5000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3.0, "ADC_Offset": 0.9, 'cavmin': True},
          'Qubit': {'Frequency': 3989.2, 'sigma': 0.05, 'Gain': 9730},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.5, 'Gain': 5000,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.9, 'cavmin': True},
              'Qubit': {'Frequency': 4047.7, 'sigma': 0.05, 'Gain': 4500},
            'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
}

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 0
FF_gain4_BS = 0
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0

voltage_arrays =[]
voltage_arrays.append(np.array([-0.4954, -1.2801, -0.9915, -1.4535, -0.9652, -1.3433, -1.0308,
       -1.1507, -0.167 , -0.2313, -0.2357, -0.2179, -0.2068, -0.0335]))
voltage_arrays.append(np.array([-1.0658, -0.6498, -0.9925, -1.4537, -0.9668, -1.3452, -1.0351,
       -1.1551, -0.166 , -0.2385, -0.2338, -0.2185, -0.2035, -0.0386]))
voltage_arrays.append(np.array([-1.0894, -1.2817, -0.4149, -1.4505, -0.9658, -1.3362, -1.0255,
       -1.1361, -0.143 , -0.238 , -0.2338, -0.2134, -0.2106, -0.0255]))
voltage_arrays.append(np.array([-1.0531, -1.2462, -0.9912, -0.8057, -0.9737, -1.3503, -1.0528,
       -1.1765, -0.1751, -0.2151, -0.2303, -0.2198, -0.1981, -0.0515]))

# 1 hr, 2 hrs, 4 hrs

for Q in [1,2,3,4]:
    set_voltages(voltage_arrays[Q-1])
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]
    exec(open("UPDATE_CONFIG.py").read())


    exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())
    T1TLS_params = {"FF_gain_start": -30000, "FF_gain_stop": 30000, "FF_gain_steps": 201,
                    "stop_delay_us": 100, "expts": 25, "reps": 400,
                    'qubitIndex': Qubit_Pulse[0]}

    FFvsT1(path="FFvsT1", outerFolder=outerFolder, prefix=f"Q={Q}",
               cfg=config | T1TLS_params, soc=soc, soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)
spi_rack.close()
plt.show()

