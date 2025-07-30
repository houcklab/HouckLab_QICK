# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mFFRamseyCalibration import \
    FFRamseyCal
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import Compensated_Pulse
# from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Jero import Compensated_Pulse
import numpy as np



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4393.76, 'sigma': 0.07, 'Gain': 3920},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 3920},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3829.2, 'sigma': 0.07, 'Gain': 4240},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 4240},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4116.7, 'sigma': 0.07, 'Gain': 6400},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 6400},
          'Pulse_FF': [0, -5000, 0, 0, 0, 0, 0, 0]},
}


Qubit_Readout = [4]
Qubit_Pulse = [4]

FF_gain1_expt = 0
FF_gain2_expt = -5000
FF_gain3_expt = 0
FF_gain4_expt = -5000
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
exec(open("UPDATE_CONFIG.py").read())

RunCalibrationFF = True
RamseyCal_cfg = {
                        "start": 0, "step": 1, "expts": 10 * 16,
                        "reps":64000, "relax_delay": 100, "YPulseAngle": 90,
                'IDataArray': [None,
                               None, #Compensated_Pulse(FF_gain2_expt, FF_gain2_init, 2),
                               None, #Compensated_Step(FF_gain3_expt, FF_gain3_init, 2),
                               None,
                               None, None, None, None]}
if RunCalibrationFF:
    # RamseyCal_cfg['FFlength'] = int(np.ceil(CalibrationFF_params['expts'] / 16)) * 16
    #
    # print(config["FF_Qubits"])
    # config = config | RamseyCal_cfg


    # RAveragerProgram
    FFRamseyCal(path="FFRamseyCal", cfg=config | RamseyCal_cfg,
                         soc=soc, soccfg=soccfg, outerFolder=outerFolder,
                         prefix='Q1_compensated_index2').acquire_display_save(plotDisp=True)
