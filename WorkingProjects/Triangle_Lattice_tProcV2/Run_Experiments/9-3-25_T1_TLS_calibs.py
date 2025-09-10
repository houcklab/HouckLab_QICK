# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsT1 import FFvsT1

# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS


from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_1234 import *

# 1 hr, 2 hrs, 4 hrs

for Q in [1,2,3,4,5,6,7,8]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [f'{Q}R']
    exec(open("UPDATE_CONFIG.py").read())


    exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())
    T1TLS_params = {"FF_gain_start": -8000, "FF_gain_stop": 8000, "FF_gain_steps": 201,
                    "stop_delay_us": 10, "expts": 5, "reps": 400,
                    'qubitIndex': Qubit_Readout[0]}

    FFvsT1(path="FFvsT1", outerFolder=outerFolder, prefix=f"Q={Q}",
               cfg=config | T1TLS_params, soc=soc, soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)
# spi_rack.close()
plt.show()

