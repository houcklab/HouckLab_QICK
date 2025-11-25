# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotDecimated import \
    SingleShotDecimated
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeSNR_TWPAPumpParams import \
    SNROpt_wSingleShot
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import RamseyVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFluxStabilitySpec import \
    FluxStabilitySpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import SpecVsQblox

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import SpecVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillations import \
    GainSweepOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX, SingleShot_2QFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mT1vsFF import T1vsFF

from qubit_parameter_files.Qubit_Parameters_Master import *

Qubit_Readout = [5]
Qubit_Pulse   = [5]




# Qubit_Readout = [1,2,3,4,5,6,7,8]
# Qubit_Pulse = ['4_4Q', '5_4Q', '8_4Q', '1_4Q']

# Qubit_Readout = [5]
# Qubit_Pulse = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']

# Qubit_Parameters = {
#     '5': {'Readout': {'Frequency': 7363.4, 'Gain': 1057,
#                       'FF_Gains': [-26873, -29001, -25392, -27560, 2500, -28060, -25722, -24395], 'Readout_Time': 3,
#                       'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4139.0, 'sigma': 0.03, 'Gain': 7001},
#           'Pulse_FF': [-26873, -29001, -25392, -27560, 2500, -28060, -25722, -24395]},
# }

# Qubit_Parameters |= {
#     '6P': {'Readout': {'Frequency': 7442.1, 'Gain': 1057,
#                       'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4271.6, 'sigma': 0.03, 'Gain': 9914/4},
#           'Pulse_FF': Readout_2345_FF},
# }

t = True
f = False

Run_FF_v_Ramsey = False
FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 4, "expts": 61, "reps": 200,
                                    "qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                    "FF_gain_start": Expt_FF[int(str(Qubit_Readout[0])[0])-1] - 100,
                                    "FF_gain_stop": Expt_FF[int(str(Qubit_Readout[0])[0])-1] + 100,
                                    "FF_gain_steps": 11,
                                    "relax_delay":100, 'populations':True# "qubit_drive_freq":3950.0
                                   }

RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 3, 'cav_relax_delay': 10}
Run2ToneSpec = False
Spec_relevant_params = {
                        'Gauss': True, "sigma": 0.015, "Gauss_gain": 11000,
                      # "qubit_gain": 8000, "SpecSpan": 400, "SpecNumPoints": 71,
                        "qubit_gain": 400, "SpecSpan": 200, "SpecNumPoints": 71,
                        # "qubit_gain": 500, "SpecSpan": 50, "SpecNumPoints": 71,
                      #   "qubit_gain": 100, "SpecSpan": 10, "SpecNumPoints": 71,
                        'reps': 200, 'rounds': 1}

Q = 8
# Qubit_Pulse = [f'{Q}R']
# Qubit_Pulse = [Q]
# Qubit_Readout = [Q]

Run_Spec_vs_FFgain = False # Inherit spec parameters from above
FF_sweep_spec_relevant_params = {"qubit_FF_index": 5,
                            "FF_gain_start": -10000, "FF_gain_stop": 0, "FF_gain_steps": 11,
                                 'relax_delay': 100}

# center = Expt_FF[FF_sweep_spec_relevant_params['qubit_FF_index']-1]
# FF_sweep_spec_relevant_params['FF_gain_start'] = center - 6000
# FF_sweep_spec_relevant_params['FF_gain_stop'] = center + 6000

FluxStability = False # Repeat SpecSlice over time
Flux_Stability_params = {"delay_minutes": 1/60, "num_steps": 60*60}


Run_Spec_vs_Qblox = False
Spec_v_Qblox_params = {"Qblox_start": 0.4, "Qblox_stop": 1.2, "Qblox_steps": 6, "DAC": 9}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"max_gain": 2*12000, 'relax_delay':100}


SingleShot = True
SS_params = {"Shots": 2000, 'number_of_pulses': 1, 'relax_delay': 200}

SingleShotDecimate = False

SingleShot_ReadoutOptimize = False
SS_R_params = {"Shots": 500,
               "gain_start": 2000, "gain_stop": 8000, "gain_pts": 8, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}

SingleShot_QubitOptimize = False
SS_Q_params = {"Shots": 500,
               "q_gain_span": 8000, "q_gain_pts": 7, "q_freq_span": 6.0, "q_freq_pts": 7,
               'number_of_pulses': 1,
               'qubit_sweep_index': -1}

SingleShot_SNROptimize = False
SNR_params = {'Shots': 1000,
              'gain_start': -2, 'gain_stop':0.5, 'gain_pts': 10,
              'freq_start': 7800, 'freq_stop': 8000, 'freq_pts': 10,
              'number_of_pulses': 1}

# SS_Q_params = {"Shots": 500,
#                "q_gain_span": 4000, "q_gain_pts": 7, "q_freq_span": 8.0, "q_freq_pts": 11,
#                'number_of_pulses': 1,
#                'qubit_sweep_index': -1}


if SingleShot_QubitOptimize and SS_Q_params['qubit_sweep_index'] >= len(Qubit_Pulse):
    raise ValueError("Qubit optimize sweep index out of range")

# These T1 and T2R experiments are done at FFPulses!
RunT1 = False
RunT2 = False

T1_params = {"stop_delay_us": 100, "expts": 40, "reps": 150}

T2R_params = {"stop_delay_us": 5, "expts": 125, "reps": 300,
              "freq_shift": 0.0, "phase_shift_cycles": -3, "relax_delay":150}



RunT1_TLS = False
T1TLS_params = {"FF_gain_start": -10000, "FF_gain_stop": 0, "FF_gain_steps": 301,
                    "stop_delay_us": 10, "expts": 5, "reps": 300,
                    'qubitIndex': int(str(Qubit_Pulse[0])[0])}

# SingleShot_ROTimingOptimize = False
# SS_Timing_params = {"Shots": 500,
#                   "read_length_start":1, "read_length_end":10, "read_length_points":5,
#                   "trig_time_start":0.1, "trig_time_end":3, "trig_time_points":5}

Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 6, 'reps': 1000,
                         'start': 0, 'step': 4, 'expts': 141,
                         'gainStart': - 9500,
                         'gainStop':  - 8500, 'gainNumPoints': 9, 'relax_delay': 200,
                         'fit': True}
Oscillation_Gain_QICK_sweep = False

Oscillation_Single = False # uses same dict as gain sweep

Calib_FF_vs_drive_delay = False
ff_drive_delay_dict = {'start':200, 'step':8, 'expts': 200, # delay of FF, units of samples
                       'qubit_delay_cycles': 80,
                       'reps': 4000,
                        'qubit_index': Qubit_Pulse[0],}

# RunChiShift = False
# ChiShift_Params = {'pulse_expt': {'check_12': False},
#                    'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'], 'qubit_gain01': 1670 // 2,
#                    'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'],  'qubit_gain12': 1670 // 2}


CalibrationFF_params = {'FFQubitIndex': 3, 'FFQubitExpGain': 3000,
                        "start": 0, "step": 1, "expts": 20 * 16 * 1,
                        "reps": 100, "rounds": 200, "relax_delay": 100, "YPulseAngle": 93,
           }


SingleShot_2Qubit = False
SS_2Q_params = {"Shots": 2500, 'number_of_pulses': 1, 'relax_delay': 300}


SS_2Q_params = {"Shots": 2500, 'number_of_pulses': 1, 'relax_delay': 300,
                'second_qubit_freq': 4271.5, 'second_qubit_gain': 8000}

# This ends the working section of the file.
#----------------------------------------
# Not used

exec(open("UPDATE_CONFIG.py").read())
#--------------------------------------------------
# This begins the booleans
soc.reset_gens()
if RunTransmissionSweep:
    Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config | Trans_relevant_params,
                                     soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    Instance_trans.acquire_display_save(plotDisp=True)

    #update the transmission frequency to be the peak
    # if Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['cavmin']:
    #     config["res_freqs"][0] = Instance_trans.peakFreq_min
    # else:
    #     config["res_freqs"][0] = Instance_trans.peakFreq_max

    print("Cavity frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])
else:
    print("Cavity frequency set to: ", config["res_freqs"][0] + BaseConfig["res_LO"])
    pass

if Run2ToneSpec:
    QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Spec_relevant_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Run_Spec_vs_FFgain:
    SpecVsFF(path="SpecVsFF", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
                             soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Run_Spec_vs_Qblox:
    SpecVsQblox(path="SpecVsQblox", cfg=config | Spec_relevant_params | Spec_v_Qblox_params,
                             soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if FluxStability:
    FluxStabilitySpec(path="FluxStability", cfg=config | Spec_relevant_params | Flux_Stability_params,
                soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if RunAmplitudeRabi:
    AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config | Amplitude_Rabi_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if RunT1:
    T1MUX(path="T1", cfg=config | T1_params, soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True)
if RunT2:
    T2RMUX(path="T2R", cfg=config | T2R_params,
              soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True)

if SingleShot:
    SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder,
                           cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)

if SingleShotDecimate:
    SingleShotDecimated(path="SingleShotDecimated", outerFolder=outerFolder,
                           cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)
if SingleShot_ReadoutOptimize:
    ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                             cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)
if SingleShot_QubitOptimize:
    QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                   cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)

# if SingleShot_ROTimingOptimize:
#     ROTimingOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
#                              cfg=config | SS_params | SS_Timing_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)

if SingleShot_SNROptimize:
    SNROpt_wSingleShot(path="SNR_OptPump", outerFolder=outerFolder,
                                   cfg=config | SNR_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)


if Oscillation_Gain or Oscillation_Single or Calib_FF_vs_drive_delay or RunT1_TLS or Run_FF_v_Ramsey and FF_sweep_Ramsey_relevant_params['populations']:
    exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

if Run_FF_v_Ramsey:
    RamseyVsFF(path="RamseyVsFF", cfg=config | FF_sweep_Ramsey_relevant_params,
                             soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Oscillation_Gain:
    if not Oscillation_Gain_QICK_sweep:
        GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
    else:
        # raise AssertionError('this sweep not working yet.')
        print("Testing arbitrary waveform sweep")
        # GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              # cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=False)
        GainSweepOscillationsR(path="GainSweepOscillationsR", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
if Oscillation_Single:
    QubitOscillations(path="QubitOscillations", outerFolder=outerFolder,
                          cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if RunT1_TLS:
    T1vsFF(path="T1vsFF", outerFolder=outerFolder, cfg=config | T1TLS_params, soc=soc, soccfg=soccfg).acquire_save_display(plotDisp=True)


# TimeDomainSpec(path="TimeDomainSpec", outerFolder=outerFolder,
#                           cfg=config | {'reps': 5,
#                          'start':1, 'step': 16, 'expts': 50,}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if SingleShot_2Qubit:
    SingleShot_2QFFMUX(path="SingleShot_2Qubit", outerFolder=outerFolder,
                           cfg=config | SS_2Q_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)

if Calib_FF_vs_drive_delay:
    CalibrateFFvsDriveTiming(path="FF_drive_timing", outerFolder=outerFolder,
                           cfg=config | ff_drive_delay_dict, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)

# import matplotlib.pyplot as plt
# while True:
#     plt.pause(50)
print(config)
plt.show()

