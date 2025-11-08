from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *

######################################################
################ SingleShot General ##################
######################################################

Q = 8
Qubit_Readout = [Q]
Qubit_Pulse = [f'{q}R' for q in Qubit_Readout]

# Qubit_Readout = [1,2,3,4,5,6,7,8]
# Qubit_Readout = ['4_4815_readout', '8_4815_readout', '1_4815_readout', '5_4815_readout']
# Qubit_Pulse = ['1_4815', '4_4815', '8_4815', '5_4815']

t = True
f = False

######################################################
############### Experiment Specific ##################
######################################################

#=================== RamseyVsFF ======================
FF_sweep_Ramsey_relevant_params = {
    "stop_delay_us": 4, "expts": 61, "reps": 200,
    "qubit_FF_index": int(str(Qubit_Readout[0])[0]),
    "FF_gain_start": Expt_FF[int(str(Qubit_Readout[0])[0])-1] - 100,
    "FF_gain_stop": Expt_FF[int(str(Qubit_Readout[0])[0])-1] + 100,
    "FF_gain_steps": 11,
    "relax_delay":100, 'populations':True# "qubit_drive_freq":3950.0
}

#=================== CavitySpecFFMUX ======================
Trans_relevant_params = {
    "reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
    "readout_length": 3, 'cav_relax_delay': 10
}

#=================== QubitSpecSliceFFMUX ======================
Spec_relevant_params = {
    'Gauss': True, "sigma": 0.015, "Gauss_gain": 11000,
    # "qubit_gain": 8000, "SpecSpan": 400, "SpecNumPoints": 71,
    "qubit_gain": 400, "SpecSpan": 200, "SpecNumPoints": 71,
    # "qubit_gain": 500, "SpecSpan": 50, "SpecNumPoints": 71,
    # "qubit_gain": 100, "SpecSpan": 10, "SpecNumPoints": 71,
    'reps': 200, 'rounds': 1
}

#=================== SpecVsFF ======================
FF_sweep_spec_relevant_params = {
    "qubit_FF_index": Q,
    "FF_gain_start": -10000 - 5000, "FF_gain_stop": -10000 + 5000, "FF_gain_steps": 11,
    'relax_delay': 100
}
center = Expt_FF[FF_sweep_spec_relevant_params['qubit_FF_index']-1]
FF_sweep_spec_relevant_params['FF_gain_start'] = center - 6000
FF_sweep_spec_relevant_params['FF_gain_stop'] = center + 6000

#=================== FluxStabilitySpec ======================
Flux_Stability_params = {"delay_minutes": 1/60, "num_steps": 60*1}

#=================== SpecVsQblox ======================
Spec_v_Qblox_params = {"Qblox_start": 0.4, "Qblox_stop": 1.2, "Qblox_steps": 6, "DAC": 9}

#=================== AmplitudeRabiFFMUX ======================
Amplitude_Rabi_params = {"max_gain": 10000, 'relax_delay':100}

#================= SingleShotFFMUX, SingleShotDecimate ====================
SS_params = {"Shots": 2000, 'number_of_pulses': 1, 'relax_delay': 200}

#================= ReadOpt_wSingleShotFFMUX ====================
SS_R_params = {
    "Shots": 500, 'number_of_pulses': 1,
    "gain_start": 2000, "gain_stop": 8000, "gain_pts": 8,
    "span": 1, "trans_pts": 6,
}

#================= QubitPulseOpt_wSingleShotFFMUX ====================
SS_Q_params = {
    "Shots": 500,'number_of_pulses': 1,
    "q_gain_span": 2000, "q_gain_pts": 7, "q_freq_span": 3.0, "q_freq_pts": 7,
    'qubit_sweep_index': -1
}
# if SS_Q_params['qubit_sweep_index'] >= len(Qubit_Pulse):
#     raise ValueError("Qubit optimize sweep index out of range")

#================= T1MUX ====================
T1_params = {"stop_delay_us": 300, "expts": 40, "reps": 150}

#================= T2RMUX ====================
T2R_params = {
    "stop_delay_us": 5, "expts": 125, "reps": 300,
    "freq_shift": 0.0, "phase_shift_cycles": -3, "relax_delay":200
}

#================= T1vsFF ====================
T1TLS_params = {
    "FF_gain_start": -8874 - 4000, "FF_gain_stop": -8874 + 4000, "FF_gain_steps": 301,
    "stop_delay_us": 10, "expts": 5, "reps": 300,
    'qubitIndex': int(str(Qubit_Pulse[0])[0])
}

#================= GainSweepOscillations, GainSweepOscillationsR, ====================
#================= QubitOscillations ====================
oscillation_gain_dict = {
    'qubit_FF_index': 2, 'reps': 200,
    'start': 0, 'step': 8, 'expts': 2000,
    'gainStart': - 500, 'gainStop': + 500, 'gainNumPoints': 16,
    'relax_delay': 200, 'fit': True
}

#================= CalibrateFFvsDriveTiming ====================
ff_drive_delay_dict = {
    'start':200, 'step':8, 'expts': 200, # delay of FF, units of samples
    'qubit_delay_cycles': 80, 'reps': 4000,
    'qubit_index': Qubit_Pulse[0],
}

#================= CalibrationFF_params ====================
CalibrationFF_params = {
    'FFQubitIndex': 3, 'FFQubitExpGain': 3000,
    "start": 0, "step": 1, "expts": 20 * 16 * 1,
    "reps": 100, "rounds": 200, "relax_delay": 100, "YPulseAngle": 93,
}

#================= SingleShot_2QFFMUX ===================
SS_2Q_params = {"Shots": 2500, 'number_of_pulses': 1, 'relax_delay': 300}


######################################################
################## Config Updates ####################
######################################################
from pathlib import Path
exec(Path("../UPDATE_CONFIG.py").resolve().read_text(), globals())
exec(Path("../CALIBRATE_SINGLESHOT_READOUTS.py").resolve().read_text(), globals())