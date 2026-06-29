# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mSweepXPhase import SweepXPhase
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mQuenchExperiment import RampQuenchDynamics, RampQuenchFreq, RampQuenchRabi, RampQuenchSweepQuenchTime, RampQuenchSweepRampTime
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mQuenchDynamicsSweeps import QuenchDynamicsSweepGain

from WorkingProjects.triangle_lattice_quench.build_config import build_config
from Calibrate_muxed_readouts import characterize_readout
from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy
soc, soccfg = makeProxy()

Qubit_Readout = [3,4,5,6,7,8]
Qubit_Pulse = [3]
Ramp_State = "6Q_highest"
Dynamics_Point = "Q1_quench"

config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse,
                      Ramp_State=Ramp_State, Dynamics_Point=Dynamics_Point)
config |= characterize_readout(Qubit_Readout, soc=soc, soccfg=soccfg)

run_sweep_x_phase = False

sweep_x_phase_dict =  {'swept_qubit': 1, 'reps': 5000,
                       'phase_start': 0, 'phase_end': 360 * 2, 'phase_num_points': 41,
                       'qubit_gains_matrix': 2567//2}


quench_base_dict =  {'quench_gain': 0.55, 'quench_freq': 3792.5, 'quench_phase': 0,
                         'reps': 500,
                         'expt_samples_ramp': 0,
                         'expt_samples_quench': 110,
                         'expt_samples_dynamics': 0,
                         'init_pulse': False,
                     }



run_quench_freq = False
center_freq = 4102.7
center_freq = 3800
freq_range = 100
quench_freq_dict =  {'freq_start': center_freq - freq_range, 'freq_end': center_freq + freq_range,
                     'freq_num_points': 81,
                     }


run_quench_gain = False
quench_gain_dict =  {'gain_start': 0, 'gain_end': 20000 / 32766,
                     'gain_num_points': 31,
                     }

run_quench_sweep_quench_time = False
quench_sweep_quench_time_dict =  {'samples_start': 0, 'samples_end': 200,
                     'samples_num_points': 21,
                     }

run_quench_sweep_ramp_time = False
quench_sweep_ramp_time_dict =  {'samples_start': 0, 'samples_end': 1000,
                     'samples_num_points': 101,
                     }

run_quench_dynamics = False
quench_dynamics_dict = {'samples_start': 0, 'samples_end': 10000,
                        'samples_num_points': 101
                        }


run_quench_dynamics_sweep_gain = True
quench_dynamics_sweep_gain_dict = {'qubit_FF_index': 3,
                                   'samples_start': 0, 'samples_end': 1000,
                                   'samples_num_points': 51,
                                   'gain_start': 0, 'gain_end': 10000,
                                   'gain_num_points': 21
                        }

swept_qubit = str(quench_dynamics_sweep_gain_dict['qubit_FF_index'])
gain_range = 2000
quench_dynamics_sweep_gain_dict['gain_start'] = config["FF_Qubits"][swept_qubit]["Gain_Dynamics"] - gain_range//2
quench_dynamics_sweep_gain_dict['gain_end'] = config["FF_Qubits"][swept_qubit]["Gain_Dynamics"] + gain_range//2


# This ends the working section of the file.
# ----------------------------------------

for label in ['Gain_Readout', 'Gain_Expt', 'Gain_Pulse', 'Gain_BS', 'Gain_Dynamics', 'Gain_RampInit']:
    print(f'{label}: {[int(config["FF_Qubits"][q][label]) for q in config["FF_Qubits"]]}')

# This ends the translation of the Qubit_Parameters dict
# --------------------------------------------------

if run_sweep_x_phase:
    SweepXPhase(path="SweepXPhase", outerFolder=outerFolder,
                      cfg=config | sweep_x_phase_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if run_quench_freq:
    RampQuenchFreq(path="RampQuenchFreqSweep", outerFolder=outerFolder,
                      cfg=config | quench_base_dict | quench_freq_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_quench_gain:
    RampQuenchRabi(path="RampQuenchRabi", outerFolder=outerFolder,
                      cfg=config | quench_base_dict | quench_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_quench_sweep_ramp_time:
    RampQuenchSweepRampTime(path="RampQuenchSweepRampTime", outerFolder=outerFolder,
                      cfg=config | quench_base_dict | quench_sweep_ramp_time_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_quench_sweep_quench_time:
    RampQuenchSweepQuenchTime(path="RampQuenchSweepQuenchTime", outerFolder=outerFolder,
                      cfg=config | quench_base_dict | quench_sweep_quench_time_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if run_quench_dynamics:
    RampQuenchDynamics(path="RampQuenchDynamics", outerFolder=outerFolder,
                      cfg=config | quench_base_dict | quench_dynamics_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_quench_dynamics_sweep_gain:
    QuenchDynamicsSweepGain(path="QuenchDynamicsSweepGain", outerFolder=outerFolder,
                      cfg=config | quench_base_dict | quench_dynamics_sweep_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)



print(config)
