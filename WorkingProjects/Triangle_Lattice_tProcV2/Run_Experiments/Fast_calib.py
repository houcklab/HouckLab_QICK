# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import QubitConfig

from qubit_parameter_files.Qubit_Parameters_Master import *


f = False
t = True


Qubit_Pulse = ['4_4815', '8_4815', '1_4815', '5_4815']
Qubit_Pulse =   ['1_4815', '4_4815', '8_4815', '5_4815']
Qubit_Pulse =   ['4_4815']
# Qubit_Pulse = ['1_4QB', '4_4QB', '8_4QB', '5_4QB']

Qubit_Pulse = ['1_4Q_readout','4_4Q_readout','8_4Q_readout','5_4Q_readout']
# Qubit_Pulse = ['1_4Q_readout']
# Qubit_Pulse = ['4_4Q_readout']
# Qubit_Pulse = ['8_4Q_readout']
# Qubit_Pulse = ['5_4Q_readout']

# Qubit_Pulse = ['4_4Q', '5_4Q', '8_4Q', '1_4Q']


Qubit_configs = []

### !!! ###
varname_FF = 'Readout_1234_FF'

# Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])
# New_readout_FF = np.array([11035, 3643, 17468, -7290, -9683, -2912, 3665, 6214])
# # (4280.0, 4130.0, 4350.0, 3880.0, 3780.0, 3960.0, 4055.0, 4205.0)
# Qubit_Parameters = {
#     '4': {'Readout': {'Frequency': 7567.9, 'Gain': 1400,
#                       'FF_Gains': Readout_2345_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3870.3, 'sigma': 0.010, 'Gain':30000},
#           'Pulse_FF': Readout_2345_FF},
#     # '5': {'Readout': {'Frequency': 7362.5, 'Gain': 350,
#     #                   'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
#     #       'Qubit': {'Frequency': 3680.1, 'sigma': 0.015, 'Gain': 23333},
#     #       'Pulse_FF': Readout_2345_FF},
#     # '5': {'Readout': {'Frequency': 7362.6, 'Gain': 675,
#     #                   'FF_Gains': New_readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
#     #       'Qubit': {'Frequency': 3783.2, 'sigma': 0.03, 'Gain': 8572},
#     #       'Pulse_FF': New_readout_FF},
#     '5': {'Readout': {'Frequency': 7363.4, 'Gain': 1057,
#                       'FF_Gains': [-26873, -29001, -25392, -27560, 2500, -28060, -25722, -24395], 'Readout_Time': 3, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4139.0, 'sigma': 0.03, 'Gain': 7001},
#           'Pulse_FF': [-26873, -29001, -25392, -27560, 2500, -28060, -25722, -24395]},
# }

for Q in [6]:
    # Qubit_Readout = [1,2,3,4,5,6,7,8]
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]
    # Qubit_Pulse = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']

    # Qubit_Pulse = [f'{Q}L']
    # Qubit_Pulse = [f'{Q}R-']
    # Qubit_Pulse =   [f'{Q}_1854']
    # Qubit_Readout = [f'{Q}_4QB']
    # Qubit_Pulse =   [f'{Q}_4QB']
    # Qubit_Pulse = [f'{Q}_4Q_readout']

    pulse_numbers = [int(label[0]) if isinstance(label, str) else label for label in Qubit_Readout]
    OptReadout_index = pulse_numbers.index(Q) # Which readout index OptReadout should sweep
    pulse_numbers = [int(label[0]) if isinstance(label, str) else label for label in Qubit_Pulse]
    OptQubit_index = pulse_numbers.index(Q) # Which qubit index OptQubit should sweep

    print(f'OptQubit_index = {OptQubit_index}')

    RunTransmissionSweep =       t
    RunFirst2ToneSpec =          t
    RunSecond2ToneSpec =         t
    RunAmplitudeRabi =           t
    SingleShot_ReadoutOptimize = t
    SingleShot_QubitOptimize =   t
    SingleShot =                 t


    Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                            "readout_length": 2.5, 'cav_relax_delay': 10}

    First_Spec_params = {   "qubit_gain": 500, "SpecSpan": 100, "SpecNumPoints": 71,
                            'Gauss': False, "sigma": 0.07, "Gauss_gain": 3350,
                            'reps': 144, 'rounds': 1}


    Second_Spec_params = {"qubit_gain": 50, "SpecSpan": 10, "SpecNumPoints": 71,
                            'Gauss': False, "sigma": 0.05, "Gauss_gain": 1200,
                            'reps': 144, 'rounds': 1}


    Amplitude_Rabi_params = {"max_gain": 12000, 'relax_delay':100}

    if Q in [3, 5]:
        Amplitude_Rabi_params['max_gain'] *= 1.4


    SS_R_params = {"Shots": 500, 'relax_delay':150,
                   "gain_start": 200, "gain_stop": 1400, "gain_pts": 8,
                   "span": 1, "trans_pts": 5, 'number_of_pulses': 1,
                   'qubit_sweep_index':OptReadout_index}


    SS_Q_params = {"Shots": 500, 'relax_delay':150,
                   "q_gain_span": 2*1000, "q_gain_pts": 2+5,
                   "q_freq_span": 2*3, "q_freq_pts": 7,
                   'number_of_pulses': 1,
                   'readout_index': OptReadout_index,
                   'qubit_sweep_index': OptQubit_index}

    SS_params = {"Shots": 2500,
                 'number_of_pulses': 1, 'relax_delay': 200}


    # This ends the working section of the file.
    #----------------------------------------
    FF_gain1_BS = -5000
    FF_gain2_BS = -15000
    FF_gain3_BS = 0
    FF_gain4_BS = 0
    FF_gain5_BS = 0
    FF_gain6_BS = 0
    FF_gain7_BS = 0
    FF_gain8_BS = 0
    exec(open("UPDATE_CONFIG.py").read())
    #--------------------------------------------------
    # This begins the booleans
    bool_array = [RunTransmissionSweep, RunFirst2ToneSpec, RunSecond2ToneSpec,
                  RunAmplitudeRabi, SingleShot_ReadoutOptimize, SingleShot_QubitOptimize, SingleShot]

    if any(bool_array[:-1]):
        fig, axs = plt.subplots(2, 3, figsize=(12, 7), tight_layout=True)
        fig.suptitle(f"Qubit_Readout={Qubit_Readout}, Qubit_Pulse={Qubit_Pulse}")
        iter_axs = iter(axs.flatten())


    if RunTransmissionSweep:
        Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config | Trans_relevant_params,
                                         soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data = Instance_trans.acquire_display_save(plotDisp=True, block=False, ax = next(iter_axs))

        #update the transmission frequency to be the peak
        config["res_freqs"][0] = Instance_trans.peakFreq_min
        print("Cavity frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])

    if RunFirst2ToneSpec:
        Instance_spec = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | First_Spec_params,
                            soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data = Instance_spec.acquire_display_save(plotDisp=True, block=False, ax = next(iter_axs))
        config["qubit_freqs"][0] = Instance_spec.qubitFreq
        print("Qubit frequency found at: ", config["qubit_freqs"][0])

    if RunSecond2ToneSpec:
        Instance_spec = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Second_Spec_params,
                            soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data = Instance_spec.acquire_display_save(plotDisp=True, block=False, ax = next(iter_axs))
        config["qubit_freqs"][0] = Instance_spec.qubitFreq
        print("Qubit frequency found at: ", config["qubit_freqs"][0])

    if RunAmplitudeRabi:
        data = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config | Amplitude_Rabi_params,
                            soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False, ax = next(iter_axs))

        if 'ampl_fit' in data['data']:
            config["qubit_gains"][OptQubit_index] = data['data']['pi_gain_fit'] / 32766
        else:
            user_gain = input("Enter gain:")
            config["qubit_gains"][OptQubit_index] = int(user_gain) / 32766

        print("Qubit gain found at: ", config["qubit_gains"][0] * 32766)

    if SingleShot_ReadoutOptimize:
        ax = next(iter_axs)
        data = ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                                 cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_save(plotDisp=True, ax = ax)
        fid_mat, trans_fpts, gain_pts = (data['data'][key] for key in ('fid_mat', 'trans_fpts', 'gain_pts'))
        ro_opt_index = data['data']['ro_opt_index']
        ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)

        config["res_gains"][ro_opt_index] = gain_pts[ind[0]] / 32766. * len(Qubit_Readout)
        config["res_freqs"][ro_opt_index] = trans_fpts[ind[1]]

        best_gain = int(round(gain_pts[ind[0]]))
        best_freq = round(trans_fpts[ind[1]] + BaseConfig["res_LO"],2)
        ax.text(best_freq,best_gain,f"({best_freq}, {best_gain})", zorder=3,ha='center',va='center', color='black')
        fig.canvas.draw()
        fig.canvas.flush_events()

        print(f"Q{Qubit_Readout[ro_opt_index]} cavity gain found at: ", config["res_gains"][ro_opt_index] * 32766)
        print("Cavity frequency found at: ", config["res_freqs"][ro_opt_index] + BaseConfig["res_LO"])

    if SingleShot_QubitOptimize:
        ax = next(iter_axs)
        data = QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                       cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_save(plotDisp=True, ax = ax)
        fid_mat, trans_fpts, gain_pts = (data['data'][key] for key in ('fid_mat', 'qubit_fpts', 'gain_pts'))
        ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)

        sweep_index = SS_Q_params['qubit_sweep_index']
        config["qubit_gains"][sweep_index] = gain_pts[ind[0]] / 32766.
        config["qubit_freqs"][sweep_index] = trans_fpts[ind[1]]

        best_gain = int(round(gain_pts[ind[0]]))
        best_freq = round(trans_fpts[ind[1]], 2)
        ax.text(best_freq, best_gain, f"({best_freq}, {best_gain})", zorder=3, ha='center', va='center', color='black')
        fig.canvas.draw()
        fig.canvas.flush_events()

        print("Qubit gain found at: ", config["qubit_gains"][sweep_index] * 32766)
        print("Qubit frequency found at: ", config["qubit_freqs"][sweep_index])

    if SingleShot:
        ss = SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder,
                               cfg=config | SS_params, soc=soc,soccfg=soccfg)
        ss_data = ss.acquire()
        try:
            ss.display(ss_data, plotDisp=True, block=False, display_indices=[Q])
        except:
            ss.display(ss_data, plotDisp=True, block=False)
    Qubit_configs.append(QubitConfig(config, Q, len(Qubit_Readout), OptReadout_index, OptQubit_index, varname_FF))

    # TimeDomainSpec(path="TimeDomainSpec", outerFolder=outerFolder,
    #                           cfg=config | {'reps': 5,
    #                          'start':1, 'step': 16, 'expts': 50,}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


    # import matplotlib.pyplot as plt
    # while True:
    #     plt.pause(50)
    # print(config)
for qconf in Qubit_configs:
    print(qconf)

plt.show()

