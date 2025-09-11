# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import TimeVsPopulation

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_1234 import *
import matplotlib.pyplot as plt

FF4 = [1,2,3,4]
FF8 = [5,6,7,8]

Qubit_Readout = FF4

for Q in ['1H', '2H', '3H', '4H']:
    Qubit_Pulse = [Q]


    # can plot populations during and after ramp
    run_ramp_population_over_time = True

    population_vs_delay_dict = {'ramp_duration' : 3000, 'ramp_shape': 'cubic',
                                'time_start': 80, 'time_end' : 4000, 'time_num_points' : 21, 'reps': 800 ,
                                'relax_delay':100}

    # This ends the working section of the file.
    exec(open("UPDATE_CONFIG.py").read())
    exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

    if run_ramp_population_over_time:
        instance = TimeVsPopulation(path="TimeVsPopulation", outerFolder=outerFolder,
                                 cfg=config | population_vs_delay_dict,
                                 soc=soc, soccfg=soccfg)
        instance.acquire_display_save(plotDisp=True, block=False)

print(config)
plt.show()