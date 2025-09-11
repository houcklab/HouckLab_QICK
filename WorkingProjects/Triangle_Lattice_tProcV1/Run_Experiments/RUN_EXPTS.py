from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mGainSweepQubitOscillations import GainSweepOscillations
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mRampCurrentCalibration_SSMUX import \
    RampCurrentCalibrationGain, RampCurrentCalibrationOffset, RampCurrentCalibration1D
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mRampExperiments import RampDurationVsPopulation, \
    FFExptVsPopulation, TimeVsPopulation
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleQubitOscillations import QubitOscillations



from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mChiShiftMUX import ChiShift
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mOptimizeReadoutAndPulse import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFvsSpec import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV1.Run_Experiments.Ramp_Experiments import run_ramp_population_over_time

# from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT1_TLS_SSMUX import T1_TLS_SS
#----------------------------------------

# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
# Update FF_Qubits dict
FF_gain1_ro, FF_gain2_ro, FF_gain3_ro, FF_gain4_ro = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1_ro, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse, 'Gain_BS':FF_gain1_BS}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2_ro, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse, 'Gain_BS':FF_gain2_BS}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3_ro, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse, 'Gain_BS':FF_gain3_BS}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4_ro, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse, 'Gain_BS':FF_gain4_BS}

trans_config = {
    "res_gains": [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout],  # [DAC units]
    "res_freqs": [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout], # [MHz] actual frequency is this number + "cavity_LO"
    # "res_gain": Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain'],  # [DAC units]
    "readout_length":Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse],
    "sigma" : Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['sigma']
}
config = BaseConfig | trans_config | qubit_config
config["FF_Qubits"] = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout
config['ro_chs'] = [i for i in range(len(Qubit_Readout))]

# This ends the translation of the Qubit_Parameters dict
#--------------------------------------------------
# This begins the booleans

if RunTransmissionSweep:
    Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config | Trans_relevant_params,
                                     soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    Instance_trans.acquire_display_save(plotDisp=True)

    # update the transmission frequency to be the peak
    if Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['cavmin']:
        config["res_freqs"][0] += Instance_trans.peakFreq_min - mixer_freq
        config["mixer_freq"] = Instance_trans.peakFreq_min
    else:
        config["res_freqs"][0] += Instance_trans.peakFreq_max - mixer_freq
        config["mixer_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", config["res_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)
else:
    print("Cavity frequency set to: ", config["res_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)


if Run2ToneSpec:
    QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Spec_relevant_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Run_Spec_v_FFgain:
    FFvsSpec(path="FF_vs_Spec", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
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
if SingleShot_ReadoutOptimize:
    ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                             cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)
if SingleShot_QubitOptimize:
    QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                   cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)



def characterize_readout(config, Qubit_Readout):
    '''Characterize qubits at the current readout point to return angle, threshold, and confusion_matrix for each.
    trans_config remains the same because we want to know the readout error under the MUXed pulse we will use.'''
    angle, threshold, confusion_matrix = [], [], []

    import copy

    new_config = config.copy()
    new_config["FF_Qubits"] = copy.deepcopy(new_config["FF_Qubits"])
    new_config["Shots"] = 3000

    for ro_ind, Qubit in enumerate(Qubit_Readout):
        '''Pulse each at a time, using the QubitParameters Pulse parameters'''
        new_config["qubit_freqs"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Frequency']]
        new_config["qubit_gains"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Gain']]
        new_config['sigma']       =  Qubit_Parameters[str(Qubit)]['Qubit']['sigma']

        FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit)]['Pulse_FF']
        new_config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
        new_config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
        new_config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
        new_config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

        SSExp = SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=new_config, soc=soc, soccfg=soccfg)
        data = SSExp.acquire_display_save(plotDisp=True, block=False, display_indices=[Qubit])

        angle.append(    data['data']['angle'][ro_ind])
        threshold.append(data['data']['threshold'][ro_ind])
        ng_contrast = data['data']['ng_contrast'][ro_ind]
        ne_contrast = data['data']['ne_contrast'][ro_ind]
        conf_mat = np.array([[1 - ng_contrast, ne_contrast],
                             [ng_contrast, 1 - ne_contrast]])
        confusion_matrix.append(conf_mat)

    return angle, threshold, confusion_matrix

angle, threshold, confusion_matrix = characterize_readout(config, Qubit_Readout)
config['angle'], config['threshold'] = angle, threshold
config['confusion_matrix'] = confusion_matrix
if 'confusion_matrix' in config:
    print("Correcting using CONFUSION MATRIX")
# if Oscillation_Gain:
#     if Sweep2D:
#         GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
#                               cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
#     else:
#         GainSweepOscillationsR(path="GainSweepOscillations", outerFolder=outerFolder,
#                               cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
# if Oscillation_Single:
#     QubitOscillations(path="QubitOscillations", outerFolder=outerFolder,
#                           cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_ramp_duration_calibration:
    RampDurationVsPopulation(path="RampDurationCalibration", outerFolder=outerFolder,
                      cfg=config | ramp_duration_calibration_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_ramp_gain_calibration:
    FFExptVsPopulation(path="RampGainCalibration", outerFolder=outerFolder,
                      cfg=config | ff_expt_vs_pop_dict, soc=soc, soccfg=soccfg).acquire_display_save(
        plotDisp=True)

if RampCurrentCalibration_GainSweep:
    RampCurrentCalibrationGain(path="CurrentCalibration_GainSweep", outerFolder=outerFolder,
                           cfg=config | current_calibration_gain_dict | {"qubit_BS_indices": Qubit_BS_indices}, soc=soc,
                           soccfg=soccfg).acquire_display_save(plotDisp=True)

if RampCurrentCalibration_OffsetSweep:
    RampCurrentCalibrationOffset(path="CurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                             cfg=config | current_calibration_offset_dict | {"qubit_BS_indices": Qubit_BS_indices},
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_1D_current_calib:
    RampCurrentCalibration1D(path="CurrentCalibration_1D", outerFolder=outerFolder,
                             cfg=config | current_calibration_offset_dict | {"qubit_BS_indices": Qubit_BS_indices, "t_offset":t_offset},
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_ramp_population_over_time:
    TimeVsPopulation(path="TimeVsPopulation", outerFolder=outerFolder,
                             cfg=config | delay_vs_pop_dict | {"qubit_BS_indices": Qubit_BS_indices},
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
# import matplotlib.pyplot as plt
# while True:
#     plt.pause(50)
print(config)