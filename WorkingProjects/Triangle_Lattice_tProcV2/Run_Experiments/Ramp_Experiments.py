# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import \
    (RampCurrentCalibrationGain, RampCurrentCalibration1D,RampCurrentCalibration1DShots, RampCurrentCalibrationOffset,
     RampCurrentCalibrationOffset_Multiple, RampCurrentCalibrationTime)
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import RampDurationVsPopulation, \
    FFExptVsPopulation, PopulationVsTime, PopulationVsTime_GainSweep, PopulationVsTime_Shots, \
    RampCheckDensityCorrelations, RampSweepLengthCorrelations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCorrelations import CurrentCorrelationMeasurement


from qubit_parameter_files.Qubit_Parameters_Master import *

Qubit_Readout = [1,2,3,4,5,6,7,8]
Qubit_Pulse = ['1_4QB', '4_4QB', '8_4QB', '5_4QB']

Qubit_Pulse = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']
# Qubit_Pulse = [1,4,8,5]
# Qubit_Pulse = ['1_4Q_readout', '8_4Q_readout', '5_4Q_readout']
# Qubit_Pulse = ['1_4Q_readout', '5_4Q_readout', '8_4Q_readout', '6_4Q_readout']
# Qubit_Pulse = ['2_4Q_readout','3_4Q_readout','6_4Q_readout','7_4Q_readout']

# Qubit_Pulse = ['4_4Q', '5_4Q', '8_4Q', '1_4Q']

# Qubit_Pulse = [2]
# Qubit_Readout = [3,4]

run_ramp_gain_calibration = False


# # Q4 --> Q2
ff_expt_vs_pop_dict = {'swept_qubit': str(3),
                       'reps': 1000, 'gain_start': -7228 - 1000, 'gain_end': -7228 + 1000, 'gain_num_points': 11,
                        'ramp_duration': 2000}



run_ramp_duration_calibration = False
ramp_duration_calibration_dict = {'reps': 2000, 'duration_start': int(0), 'duration_end': int(1500), 'duration_num_points': 21,
                                   'ramp_wait_timesteps': 0,
                                   'relax_delay': 200, 'double': True}




# ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(0), 'duration_end': int(5000), 'duration_num_points': 61,
#                                    'ramp_wait_timesteps': 100,
#                                    'relax_delay': 200, 'double': False}

# ramp_duration_calibration_dict = {'reps': 500, 'duration_start': int(2000), 'duration_end': int(4000), 'duration_num_points': 61,
#                                    'ramp_wait_timesteps': 0,
#                                    'relax_delay': 200, 'double': False}



# can plot populations during and after ramp
run_ramp_population_over_time = False
run_ramp_population_over_time_shots = False
population_vs_delay_dict = {'ramp_duration' : 1500, 'ramp_shape': 'cubic',
                            'time_start': 0, 'time_end' : 1500, 'time_num_points' : 21, 'reps': 1000,
                            'relax_delay':200, 'time_to_show_shots_samples': 0}


run_ramp_population_over_time_gain_sweep = False
population_vs_delay_gain_sweep_dict = {'ramp_duration' : 3000, 'ramp_shape': 'cubic', 'relax_delay': 100,
                                       'time_start': 0, 'time_end' : 4000, 'time_num_points' : 101, 'reps': 400,
                                       'gain_start': -2000, 'gain_end' : 2000, 'gain_num_points' : 11}

# population_vs_delay_gain_sweep_dict = {'ramp_duration' : 3000, 'ramp_shape': 'cubic', 'relax_delay': 100,
#                                        'time_start': 0, 'time_end' : 4000, 'time_num_points' : 11, 'reps': 100,
#                                        'gain_start': -2000, 'gain_end' : 2000, 'gain_num_points' : 3}

plot_population_sum = False


# experiment to measure population shots after adiabatic ramp
run_ramp_population_shots = False
ramp_population_shots_dict = {'reps': 5000, 'ramp_duration': 1000, 'relax_delay': 200}

run_ramp_density_correlations = False
ramp_density_correlations_dict = {'reps': 1000000, 'ramp_duration': 1000, 'relax_delay': 200,
                                  'pairs':[[1,2,3,4],[1,2,4,5],[1,2,5,6],[1,2,6,7],[1,2,7,8],
                                            [2,3,4,5],[2,3,5,6],[2,3,6,7],
                                            [3,4,5,6],
                                            [4,5,6,7]]
                                  }



run_ramp_density_sweep_ramp_duration = False
ramp_density_sweep_dict = {'duration_start':100, 'duration_end':3000, 'duration_num_points':11,}



RampCurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep  time
current_calibration_gain_dict = {'reps': 100, 'swept_index': 1,
                                 # 't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                 't_offset': [0, 1, -6, 7, 0, 0, 0, 0],
                                 'relax_delay': 100, 'ramp_time': 3000,
                                 'gainStart': 17000, 'gainStop': 19000, 'gainNumPoints': 11,
                                 'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,}

RampCurrentCalibration_OffsetSweep = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time
#


current_calibration_offset_dict = {'reps': 500, 'swept_index': 0,
                                   't_offset':  [-5,0,-7,7,0,0,0,0],
                                   'ramp_time': 2000, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}

current_calibration_offset_dict = {'reps': 500, 'swept_index': 0,
                                   't_offset':  [0,0,0,0,0,0,0,0],
                                   'ramp_time': 2000, 'relax_delay': 175,
                                   'timeStart': 0, 'timeStop': 250, 'timeNumPoints': 31,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}

#
# current_calibration_offset_dict = {'reps': 2000, 'swept_index': 2,
#                                    't_offset':  [-5,1,-6,7,0,0,0,0],
#                                    'ramp_time': 3000, 'relax_delay': 175,
#                                    'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101,
#                                    'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}
#
# current_calibration_offset_dict = {'reps': 4000, 'swept_index': 0,
#                                    't_offset':  [-5,1,-6,7,0,0,0,0],
#                                    'ramp_time': 3000, 'relax_delay': 175,
#                                    'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101,
#                                    'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}





run_1D_current_calib = False

current_calibration_dict = {'reps': 1000,
                            't_offset':  [12,14,3,14,10,10,9,0],
                            'ramp_time': 1000, 'relax_delay': 150,
                            'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 51}



run_1D_current_calib_shots = False

current_calibration_dict_shots = {'reps': 1000,
                                  't_offset': [24,26,15,26,10,10,9,0],
                                  'ramp_time': 1000, 'relax_delay': 150,
                                  'timeStart': 0, 'timeStop': 560, 'timeNumPoints': 71}



run_current_correlation_measurement = False
current_correlation_measurement_dict = {'reps': 1000,
                                        't_offset':  [0,0,0,0,0,0,0,0],
                                        'ramp_time': 3000, 'relax_delay': 200,
                                        'beamsplitter_time': 75}

ramp_current_calibration_time = True
ramp_current_calibration_time_dict =  {'reps': 1000,
                                       't_offset':  [23, 25, 14, 20, 9, 7, 7, 0],
                                       'ramp_time': 1000, 'relax_delay': 200,
                                       'timeStart': 0, 'timeStop': 1500, 'timeNumPoints': 301}

# run_ramp_oscillations = False
# # Ramp to FFExpts, then jump to FF_BS
# oscillation_single_dict = {'reps': 1000, 'start': int(0), 'step': int(10), 'expts': 200, 'relax_delay': 300,
#                            'ramp_duration': int(20000), 'ramp_shape': 'cubic'}

# This ends the working section of the file.
exec(open("UPDATE_CONFIG.py").read())
exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

# set ramp initial gain points from qubit parameters file
# config['ramp_initial_gains'] = ramp_initial_gains

if run_ramp_duration_calibration:
    RampDurationVsPopulation(path="RampDurationCalibration", outerFolder=outerFolder,
                      cfg=config | ramp_duration_calibration_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_ramp_gain_calibration:
    FFExptVsPopulation(path="RampGainCalibration", outerFolder=outerFolder,
                      cfg=config | ff_expt_vs_pop_dict, soc=soc, soccfg=soccfg).acquire_display_save(
        plotDisp=True)

if RampCurrentCalibration_GainSweep:
    RampCurrentCalibrationGain(path="RampCurrentCalibration_GainSweep", outerFolder=outerFolder,
                           cfg=config | current_calibration_gain_dict, soc=soc,
                           soccfg=soccfg).acquire_display_save(plotDisp=True)

if RampCurrentCalibration_OffsetSweep:
    if isinstance(current_calibration_offset_dict['swept_index'], int):
        RampCurrentCalibrationOffset(path="RampCurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                             cfg=config | current_calibration_offset_dict,
                             soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
    elif isinstance(current_calibration_offset_dict['swept_index'], (list, tuple)):
        RampCurrentCalibrationOffset_Multiple(path="RampCurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                                     cfg=config | current_calibration_offset_dict,
                                     soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if run_1D_current_calib:
    instance = RampCurrentCalibration1D(path="CurrentCalibration_1D", outerFolder=outerFolder,
                             cfg=config | current_calibration_dict,
                             soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)


if run_1D_current_calib_shots:
    instance = RampCurrentCalibration1DShots(path="CurrentCalibration_1D_Shots", outerFolder=outerFolder,
                             cfg=config | current_calibration_dict_shots,
                             soc=soc, soccfg=soccfg)
    instance.acquire_save(plotDisp=False, plotSave=False)

if run_ramp_population_over_time:
    instance = PopulationVsTime(path="PopulationVsTime", outerFolder=outerFolder,
                             cfg=config | population_vs_delay_dict,
                             soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True, block=False)

if run_ramp_population_over_time_shots:
    instance = PopulationVsTime_Shots(path="PopulationVsTimeShots", outerFolder=outerFolder,
                             cfg=config | population_vs_delay_dict,
                             soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True, block=False)

if run_ramp_density_correlations:
    RampCheckDensityCorrelations(path="RampDensityCorrelations", outerFolder=outerFolder,
                           cfg=config | ramp_density_correlations_dict,
                           soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=True)

if run_ramp_density_sweep_ramp_duration:
    RampSweepLengthCorrelations(path='RampSweepLengthCorrelations', outerFolder=outerFolder,
                                cfg=config | ramp_density_correlations_dict | ramp_density_sweep_dict,
                                soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=True)

if run_ramp_population_over_time_gain_sweep:
    instance = PopulationVsTime_GainSweep(path="PopulationVsTime_GainSweep", outerFolder=outerFolder,
                             cfg=config | population_vs_delay_gain_sweep_dict,
                             soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_current_correlation_measurement:
    instance = CurrentCorrelationMeasurement(path="CurrentCorrelations", outerFolder=outerFolder,
                             cfg=config | current_correlation_measurement_dict,
                             soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)
if ramp_current_calibration_time:
    instance = RampCurrentCalibrationTime(path="RampCurrentCalibrationTime", outerFolder=outerFolder,
                             cfg=config | ramp_current_calibration_time_dict,
                             soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)


import matplotlib.pyplot as plt

if plot_population_sum:
    populations_corrected = instance.data['data']['population_corrected']
    readout_list = instance.data['data']['readout_list']

    print(type(populations_corrected[0]))
    print(len(populations_corrected[0]))
    print(populations_corrected[0].shape)

    if len(populations_corrected[0].shape) == 1:

        # for i in range(len(populations_corrected)):
        #     plt.plot(instance.x_points, populations_corrected[i], label=readout_list[i])

        plt.plot(instance.x_points, np.sum(populations_corrected, axis=0), linestyle=':', color='black', label='total')

        plt.xlabel(instance.xlabel)
        plt.ylabel('Population')
        plt.title('Populations')
        plt.legend()
        plt.show()

    else:

        population_sum = sum(populations_corrected)

        x_values = instance.x_points
        x_step = instance.x_points[1] - instance.x_points[0]

        y_values = instance.y_points
        y_step = instance.y_points[1] - instance.y_points[0]

        z_values = population_sum

        extent = (instance.x_points[0] - x_step/2, instance.x_points[-1] + x_step/2, instance.y_points[0] - y_step/2, instance.y_points[-1] + y_step/2)

        plt.figure(figsize=(10, 8))
        plt.imshow(z_values, extent=extent, origin='lower', cmap='viridis', aspect='auto', interpolation='none')

        plt.xlabel(instance.xlabel)
        plt.ylabel(instance.ylabel)

        plt.title('Population sum over time vs constant gain offset')

        plt.colorbar(label='Population sum')

        plt.show()

print(config)
plt.show()