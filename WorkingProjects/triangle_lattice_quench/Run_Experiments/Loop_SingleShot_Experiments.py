# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.Readout_Crosstalk_Population import \
    ReadoutCrosstalkPopulation
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotDecimated import \
    SingleShotDecimated
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mT2EMUX import T2EMUX
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mChiShift import ChiShift
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mOptimizeSNR_TWPAPumpParams import \
    SNROpt_wSingleShot
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import RamseyVsFF
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mFluxStabilitySpec import \
    FluxStabilitySpec
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mSpecVsGain import SpecVsGain
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import SpecVsQblox

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import SpecVsFF
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mTransmissionVsPower_MUX import \
    TransmissionVsPower
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Second_Excited_State_Experiments.mSpecSliceMulti import \
    QubitSpecSlice2nd
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mGainSweepQubitOscillations import \
    GainSweepOscillations
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX, SingleShot_2QFFMUX
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mT1vsFF import T1vsFF

import matplotlib.pyplot as plt

from WorkingProjects.triangle_lattice_quench.build_config import build_config, outerFolder
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy


soc, soccfg = makeProxy()


# for det,Q in itertools.product([+20000, -20000],[1,2,3,4,5,6,7,8]):
for Q in [5]:
    Qubit_Readout = [Q]
    # Qubit_Pulse = [Q]
    Qubit_Pulse =   [f"{Q}_3800+"]

    config = build_config(
        Qubit_Readout=Qubit_Readout,  # required: list of readout-entry labels
        Qubit_Pulse=Qubit_Pulse,  # optional: list of drive-entry labels
        Ramp_State=None,  # optional: key in ramp_groups
        Dynamics_Point=None,  # optional: key in dynamics_groups
    )


    t = True
    f = False

    Run_FF_v_Ramsey = False
    FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 3, "expts": 61, "reps": 200,
                                        "qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                        "FF_gain_start": config["FF_Qubits"][str(Q)]["Gain_Expt"] - 100,
                                        "FF_gain_stop": config["FF_Qubits"][str(Q)]["Gain_Expt"] + 100,
                                        "FF_gain_steps": 11,
                                        "relax_delay":100, 'populations':False# "qubit_drive_freq":3950.0
                                       }

    RunTransmissionSweep = False # determine cavity frequency
    Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                            "readout_length": 3, 'cav_relax_delay': 10}

    RunChiShift = False
    # Trans_relevant_params = {"reps": 8000, "TransSpan": 1.5, "TransNumPoints": 141,
    #                             "readout_length": 3, 'cav_relax_delay': 10,
    #                          "cav_gain":150}

    RunTransmissionVsPower = False
    transmission_v_power_params = {"gain_start": 200, "gain_stop":32000, "gain_num_points":11}



    Run2ToneSpec = False
    Spec_relevant_params = {
                          # "qubit_gain": 200, "SpecSpan": 800, "SpecNumPoints": 1601,
                          #   "qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 71,
                             "qubit_gain": 200, "SpecSpan": 150, "SpecNumPoints": 2*71,
                          #   "qubit_gain": 199, "SpecSpan": 50, "SpecNumPoints": 71,
                            # "qubit_gain": 10, "SpecSpan": 10, "SpecNumPoints": 71,
                            'Gauss': False, "sigma": 0.03, "Gauss_gain": 32766*config['qubit_gains'][0],
                            'reps': 2*155, 'rounds': 1}

    Run_Spec_vs_FFgain = False # Inherit spec parameters from above

    RunSpecSliceSecond = False # Utilizes the first two drives in the qubit list, sweeps around the second drive

    FF_sweep_spec_relevant_params = {"qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                "FF_gain_start": config["FF_Qubits"][str(Q)]["Gain_Pulse"] - 8000,
                                "FF_gain_stop": config["FF_Qubits"][str(Q)]["Gain_Pulse"] + 8000,
                                     "FF_gain_steps": 7,
                                     'relax_delay':100}
    #
    # FF_sweep_spec_relevant_params = {"qubit_FF_index": int(str(Qubit_Readout[0])[0]),
    #                                 "FF_gain_start": -25000,
    #                                 "FF_gain_stop": 25000,
    #                                      "FF_gain_steps": 7,
    #                                      'relax_delay':100}
    Run_Spec_vs_Qubit_gain = False
    gain_sweep_spec_params = {"qubit_gain_start": 100,
                                     "qubit_gain_stop": 3000,
                                     "qubit_gain_steps": 11,
                                     'relax_delay': 100}

    FluxStability = True # Repeat SpecSlice over time
    Flux_Stability_params = {"delay_minutes": 10, "num_steps": 6 * 8} # 8 hours since 10*6*8, every 10 minutes


    Run_Spec_v_Qblox = False
    Spec_v_Qblox_params = {"Qblox_start": -1.6525-0.8, "Qblox_stop": -1.6525+0.8, "Qblox_steps": 31, "DAC": 9}

    RunAmplitudeRabi = False
    Amplitude_Rabi_params = {"max_gain": 15000, 'relax_delay':100}


    SingleShot = False
    SS_params = {"Shots": 2000, 'number_of_pulses': 1, 'relax_delay': 200,}
                 # "readout_lengths":[6],
                 # "adc_trig_delays":[0]}

    SingleShotDecimate = False

    SingleShot_ReadoutOptimize = False
    SS_R_params = {"Shots": 500,
                   "gain_start": 2000, "gain_stop": 8000, "gain_pts": 8, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}

    SingleShot_QubitOptimize = False
    SS_Q_params = {"Shots": 500,
                   "q_gain_span": 1000, "q_gain_pts": 7, "q_freq_span": 2.0, "q_freq_pts": 7,
                   'number_of_pulses': 1,
                   'qubit_sweep_index': -1}

    if SingleShot_QubitOptimize and SS_Q_params['qubit_sweep_index'] >= len(Qubit_Pulse):
        raise ValueError("Qubit optimize sweep index out of range")

    SingleShot_SNROptimize = False
    SNR_params = {'Shots': 1000,
                  'gain_start': -2.6, 'gain_stop': 0.5, 'gain_pts': 20,
                  'freq_start': 7700, 'freq_stop': 8000, 'freq_pts': 20,
                  'number_of_pulses': 1}
    # These T1 and T2R experiments are done at FFPulses!
    RunT1 = False
    RunT2 = False

    T1_params = {"stop_delay_us": 100, "expts": 40, "reps": 150}

    T2R_params = {"stop_delay_us": 5, "expts": 150, "reps": 300,
                  "freq_shift": 0.0, "phase_shift_cycles": 5, "relax_delay":200}

    RunT2E = False


    RunT1_TLS = False
    T1TLS_params = {"FF_gain_start": max(-32766, config["FF_Qubits"][str(Q)]["Gain_Readout"]-10000),
                    "FF_gain_stop": min(32766, config["FF_Qubits"][str(Q)]["Gain_Readout"]+10000),
                    "FF_gain_steps": 101,
                    "stop_delay_us": 5, "expts": 5, "reps": 2*300,
                    'qubitIndex': int(str(Qubit_Readout[0])[0])}

    T1TLS_params = {"FF_gain_start": -32000,
                        "FF_gain_stop": 32000,
                        "FF_gain_steps": 1001,
                        "stop_delay_us": 5, "expts": 4, "reps": 2*300,
                        'qubitIndex': int(str(Qubit_Readout[0])[0])}

    # SingleShot_ROTimingOptimize = False
    # SS_Timing_params = {"Shots": 500,
    #                   "read_length_start":1, "read_length_end":10, "read_length_points":5,
    #                   "trig_time_start":0.1, "trig_time_end":3, "trig_time_points":5}
    Run_Readout_Crosstalk = False
    ro_crosstalk_params = {"Shots": 4000, "Qubit_Pulse": Qubit_Pulse} # Second argument is only for plotting


    Oscillation_Gain = False
    oscillation_gain_dict = {'qubit_FF_index': Q+2, 'reps': 700,
                             'start': 1, 'step': 20, 'expts': 71,
                             'gainStart': -6000,
                             'gainStop': -4000, 'gainNumPoints': 11, 'relax_delay': 200,
                             'fit': True}
    Oscillation_Gain_QICK_sweep = True

    try:
        center = config["FF_Qubits"][str(Q)]["Gain_Expt"]
        # center = -13000
        oscillation_gain_dict['gainStart'] = center - 1000
        oscillation_gain_dict['gainStop'] = center + 1000
    except:
        pass


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
    SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400}


    SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400,
                    'second_qubit_freq': 3809.3, 'second_qubit_gain': 1140}

    # This ends the working section of the file.
    #----------------------------------------

    # This begins the booleans

    if RunTransmissionSweep:
        Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config | Trans_relevant_params,
                                         soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        Instance_trans.acquire_display_save(plotDisp=True, block=False)

        config["res_freqs"][0] = Instance_trans.peakFreq_min
        print("Cavity frequency found at: ", config["res_freqs"][0] + config["res_LO"])

    if RunTransmissionVsPower:
        TransmissionVsPower(path="TransmissionVsPower", cfg=config | Trans_relevant_params | transmission_v_power_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True,
                                                                                              block=False)

    if RunChiShift:
        Instance_trans = ChiShift(path="ChiShift", cfg=config | Trans_relevant_params,
                                         soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        Instance_trans.acquire_display_save(plotDisp=True, block=False)

    if Run2ToneSpec:
        QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Spec_relevant_params,
                            soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

    if RunSpecSliceSecond:
        QubitSpecSlice2nd(path="QubitSpec2nd", cfg=config | Spec_relevant_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True,
                                                                                              block=False)

    if Run_Spec_vs_FFgain:
            SpecVsFF(path="SpecVsFF", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
                                     soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)
    if Run_Spec_vs_Qubit_gain:
        SpecVsGain(path="SpecVsGain", cfg=config | Spec_relevant_params | gain_sweep_spec_params,
                  soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

    if Run_Spec_v_Qblox:
        SpecVsQblox(path="SpecVsQblox", cfg=config | Spec_relevant_params | Spec_v_Qblox_params,
                                 soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

    if FluxStability:
        FluxStabilitySpec(path="FluxStability", cfg=config | Spec_relevant_params | Flux_Stability_params,
                    soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

    if RunAmplitudeRabi:
        AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config | Amplitude_Rabi_params,
                            soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

    if RunT1:
        T1MUX(path="T1", cfg=config | T1_params, soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True, block=False)
    if RunT2:
        T2RMUX(path="T2R", cfg=config | T2R_params,
                  soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True, block=False)
    if RunT2E:
        T2EMUX(path="T2E", cfg=config | T2R_params,
                  soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True, block=False)

    if SingleShot:
        SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder,
                               cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)

    if SingleShotDecimate:
        SingleShotDecimated(path="SingleShotDecimated", outerFolder=outerFolder,
                               cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)
    if SingleShot_ReadoutOptimize:
        ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                                 cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
    if SingleShot_QubitOptimize:
        QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                       cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

    if SingleShot_SNROptimize:
        SNROpt_wSingleShot(path="SNR_OptPump", outerFolder=outerFolder,
                           cfg=config | SNR_params, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

    # if SingleShot_ROTimingOptimize:
    #     ROTimingOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
    #                              cfg=config | SS_params | SS_Timing_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

    if Run_Readout_Crosstalk or Oscillation_Single or Calib_FF_vs_drive_delay or RunT1_TLS or Run_FF_v_Ramsey and FF_sweep_Ramsey_relevant_params['populations']:
        exec(open("Legacy_CALIBRATE_SINGLESHOT_READOUTS.py").read())

    if Run_FF_v_Ramsey:
        RamseyVsFF(path="FF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params,
                                 soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)
    if Run_Readout_Crosstalk:
        ReadoutCrosstalkPopulation(path="ReadoutCrosstalk", cfg=config | ro_crosstalk_params,
                                 soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

    if Oscillation_Gain:
        if not Oscillation_Gain_QICK_sweep:
            GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                                  cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
        else:
            # raise AssertionError('this sweep not working yet.')
            print("Testing arbitrary waveform sweep")
            # GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                                  # cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=False)
            GainSweepOscillationsR(path="GainSweepOscillationsR", outerFolder=outerFolder,
                                  cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
    if Oscillation_Single:
        QubitOscillations(path="QubitOscillations", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

    if RunT1_TLS:
        T1vsFF(path="T1vsFF", outerFolder=outerFolder, cfg=config | T1TLS_params, soc=soc, soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)


    # TimeDomainSpec(path="TimeDomainSpec", outerFolder=outerFolder,
    #                           cfg=config | {'reps': 5,
    #                          'start':1, 'step': 16, 'expts': 50,}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)


    if SingleShot_2Qubit:
        SingleShot_2QFFMUX(path="SingleShot_2Qubit", outerFolder=outerFolder,
                               cfg=config | SS_2Q_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)

    if Calib_FF_vs_drive_delay:
        CalibrateFFvsDriveTiming(path="FF_drive_timing", outerFolder=outerFolder,
                               cfg=config | ff_drive_delay_dict, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)

    # import matplotlib.pyplot as plt
    # while True:
    #     plt.pause(50)
print(config)

plt.show()