# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mFFSpecCalibration_MUX import \
    FFSpecCalibrationMUX
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *



# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
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
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    }


Qubit_Readout = [4]
Qubit_Pulse = [4]

'''Usage: jump from gain_expt to gain_BS. Pulse_FF is not used'''
FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = -30000
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

FFCal_params = {"SpecStart":4000, "SpecEnd":4200, "SpecNumPoints": 151,
                "Gauss_gain": 32000, "sigma": 0.005,
                # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
                'delay_start': 8, 'delay_step': 50, 'delay_points': 5,
                'reps': 300, 'relax_delay':200,
                'IDataArray': [None,
                               None, #Compensated_Pulse(FF_gain2_expt, FF_gain2_init, 2),
                               None,  #Compensated_Pulse(FF_gain3_expt, FF_gain3_init, 3),
                               Compensated_Pulse(FF_gain4_BS, FF_gain4_expt, 2),
                               None,None, None, None],
                                }

FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix='Q1_compensated_index2').acquire_display_save(plotDisp=True)

# Qubit_Readout = [2]
# Qubit_Pulse = [2]
#
# exec(open("UPDATE_CONFIG.py").read())
#
# FFCal_params = {"SpecStart":4550, "SpecEnd":4720, "SpecNumPoints": 171,
#                 "Gauss_gain": 32000, "sigma": 0.005,
#                 # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
#                 'delay_start': 0, 'delay_step': 1, 'delay_points': 150,
#                 'reps': 20, 'rounds': 20,
#                 'IDataArray': [None,
#                                None, #Compensated_Pulse(FF_gain2_expt, FF_gain2_init, 2),
#                                Compensated_Pulse(FF_gain3_expt, FF_gain3_init, 3),
#                                None], 'relax_delay':200}
# FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
#                    soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix='Q2_compensated').acquire_display_save(plotDisp=False)


