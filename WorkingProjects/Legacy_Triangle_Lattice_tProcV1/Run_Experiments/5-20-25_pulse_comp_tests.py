from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFCompOvershootTests import SweepFFInitPoint, \
    StarkShift_vs_qubit_gain, StarkShift_vs_Gauss_gain
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFSpecCalibration_MUX import FFSpecCalibrationMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.MUXInitialize import *

from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.Compensated_Pulse_Jero import *
import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6979.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 12500,
                      "FF_Gains": [0, 0, 2000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4475, 'sigma': 0.10, 'Gain': 1237},
          'Pulse_FF': [0, 0, 20000, 0]},  # FOURTH index
    '2': {'Readout': {'Frequency': 7095.687 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4000,
                      "FF_Gains": [0, 0, 2000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4500.6, 'sigma': 0.05, 'Gain': 3360},
          'Pulse_FF': [0, 0, 0, -30000]}, # third index
    }

Qubit_Readout = [1]
Qubit_Pulse = [1]

FF_gain1_init = 0
FF_gain2_init = 0
FF_gain3_init = 20000
FF_gain4_init = -30000

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 20000
FF_gain4_expt = 0

exec(open("UPDATE_CONFIG.py").read())

Run_FF_init_sweep = False
for delay in [12,100,200,500,1000]:
    FF_init_sweep_params = {"SpecStart": 4465, "SpecEnd": 4485, "SpecNumPoints": 71,
                            "Gauss_gain": int(2400), "sigma": 0.05,
                            "swept_qubit": '4',
                            'list_of_gain_init': np.array([-3e4, -1.5e4, 0, 1.5e4, 3e4], dtype=int),
                            # Delays are in units of clock cycles! delay must be an integer # one clock cycle is 2.3 ns
                            'delay': delay,
                            'reps': 12, 'rounds': 12,
                            # 'Compensate': [False, False, False, True],
                            'relax_delay': 200}
    SweepFFInitPoint(path="SweepFFInitPoint", cfg=config | FF_init_sweep_params,
                       soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix=f"delay={delay}").acquire_display_save(plotDisp=False)


Run_SpecSlice_gain_sweep = False
Spec_gain_sweep_params = {"SpecSpan":20, "SpecNumPoints": 71,
                          "qubit_gain_start": 100, "qubit_gain_stop":30000, "qubit_gain_steps":11,
                          "Gauss_gain_start": 1000, "Gauss_gain_stop":30000, "Gauss_gain_steps":11,
                          'reps': 1500, 'rounds': 1, 'relax_delay':200}



Run_FF_cal = False
FFCal_params = {"SpecStart":4300, "SpecEnd":4700, "SpecNumPoints": 71,
                "Gauss_gain": 3200, "sigma": 0.05,
                # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
                'delay_start': 10, 'delay_step': 10, 'delay_points': 30,
                'reps': 12, 'rounds': 12,
                'IDataArray': [None,
                               None, #Compensated_Pulse(FF_gain2_expt, FF_gain2_init, 2),
                               None,  #Compensated_Pulse(FF_gain3_expt, FF_gain3_init, 3),
                               None], 'relax_delay':200}

exec(open("UPDATE_CONFIG.py").read())

if Run_FF_init_sweep:
    SweepFFInitPoint(path="SweepFFInitPoint", cfg=config | FF_init_sweep_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Run_SpecSlice_gain_sweep:
    StarkShift_vs_qubit_gain(path="SpecSlice_gain_sweep", cfg=config | Spec_gain_sweep_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Run_FF_cal:
    FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)