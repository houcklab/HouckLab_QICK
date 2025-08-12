# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mFFRamseyCalibration import \
    FFRamseyCal
from WorkingProjects.Triangle_Lattice_tProcV2.Flux_Files.QbloxVoltageSet_function import spi_rack, set_voltages
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import Compensated_Pulse
import numpy as np



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4393.76, 'sigma': 0.07, 'Gain': 3920},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 3920},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3829.9, 'sigma': 0.07, 'Gain': 4300},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 4240},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},

    '4': {'Readout': {'Frequency': 7568.8 - BaseConfig["res_LO"], 'Gain': 6750,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4421.0, 'sigma': 0.05, 'Gain': 4800},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 6400},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
}

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.4 - BaseConfig["res_LO"], 'Gain': 2100,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 1.7, "ADC_Offset": 1.5, 'cavmin': True},
          'Qubit': {'Frequency': 4398.8, 'sigma': 0.05, 'Gain': 2000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7078.5 - BaseConfig["res_LO"], 'Gain': 2200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.4, "ADC_Offset": 1.4, 'cavmin': True},
          'Qubit': {'Frequency': 4406.2, 'sigma': 0.05, 'Gain': 1350},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7511.6 - BaseConfig["res_LO"], 'Gain': 2050,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.0, "ADC_Offset": 0.9, 'cavmin': True},
          'Qubit': {'Frequency': 4366.4, 'sigma': 0.05, 'Gain': 2550},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7569.0 - BaseConfig["res_LO"], 'Gain': 1340,
                          "FF_Gains": [0, 0, 0, -677, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.9,
                          'cavmin': True},
              'Qubit': {'Frequency': 4420.86, 'sigma': 0.05, 'Gain': 1026 * 2},
            'Pulse_FF': [0, 0, 0, -677, 0, 0, 0, 0]},
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
voltage_arrays.append(np.array([ 0.0815, -1.2941, -0.9849, -1.4614, -0.9581, -1.3472, -1.0206,
       -1.1514, -0.1732, -0.2337, -0.2427, -0.2234, -0.214 , -0.0329]))
voltage_arrays.append(np.array([-1.0594, -0.0334, -0.9869, -1.4618, -0.9613, -1.351 , -1.0293,
       -1.1603, -0.1712, -0.2481, -0.2389, -0.2247, -0.2073, -0.0432]))
voltage_arrays.append(np.array([-1.1065, -1.2972,  0.1683, -1.4555, -0.9591, -1.333 , -1.0101,
       -1.1223, -0.1251, -0.2471, -0.2389, -0.2145, -0.2216, -0.017 ]))
voltage_arrays.append(np.array([-1.034 , -1.2262, -0.9843, -0.1658, -0.9749, -1.3613, -1.0647,
       -1.2031, -0.1893, -0.2014, -0.2319, -0.2272, -0.1965, -0.069 ]))

# 1 hr, 2 hrs, 4 hrs

for Q in [4]:
    set_voltages(voltage_arrays[Q-1])
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]
    exec(open("UPDATE_CONFIG.py").read())
    config['FF_Qubits'][str(Q)]['Gain_Expt'] = -20000

    idataArray = [None] * 8
    idataArray[Q-1] = Compensated_Pulse(config['FF_Qubits'][str(Q)]['Gain_Expt'],0, Q)

    exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())
    RamseyCal_cfg = {
                            "start": 0, "step": 1, "expts": 14 * 16,
                            "reps":128000, "relax_delay": 200, "YPulseAngle": 90,
                    'IDataArray': idataArray}

    FFRamseyCal(path="FFRamseyCal", cfg=config | RamseyCal_cfg,
                         soc=soc, soccfg=soccfg, outerFolder=outerFolder,
                         prefix=f'Q{Q}_ramsey0').acquire_display_save(plotDisp=True, block=False)

plt.show()
spi_rack.close()
