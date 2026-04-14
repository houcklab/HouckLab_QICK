# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import TimeVsPopulation

import matplotlib.pyplot as plt

from qubit_parameter_files.Qubit_Parameters_Master import *

calibrated_ss = False
for Q in [1,2,3,4,5,6,7,8]:
    Qubit_Readout = [1,2,3,4,5,6,7,8]
    Qubit_Pulse = [f'{Q}H']


    # can plot populations during and after ramp
    run_ramp_population_over_time = True

    population_vs_delay_dict = {'ramp_duration' : 3000, 'ramp_shape': 'cubic',
                                'time_start': 80, 'time_end' : 4000, 'time_num_points' : 21, 'reps': 800 ,
                                'relax_delay':100}

    # This ends the working section of the file.
    exec(open("UPDATE_CONFIG.py").read())

    if not calibrated_ss:
        exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())
        angle, threshold = config['angle'], config['threshold']
        confusion_matrix = config['confusion_matrix']
        calibrated_ss = True
    else:
        config['angle'], config['threshold'] = angle, threshold
        config['confusion_matrix'] = confusion_matrix

    if run_ramp_population_over_time:
        instance = TimeVsPopulation(path="TimeVsPopulation", outerFolder=outerFolder,
                                 cfg=config | population_vs_delay_dict,
                                 soc=soc, soccfg=soccfg)
        instance.acquire_display_save(plotDisp=True, block=False)

print(config)
plt.show()