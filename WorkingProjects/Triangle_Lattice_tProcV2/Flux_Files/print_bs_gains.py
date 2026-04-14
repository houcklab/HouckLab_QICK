from Calculate_FF import *

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *

bs_params = {
    '1234_correlations': (3900, 3900, 3550, 3550, 4300, 4300, 4000.0, 4000.0),

    '1245_correlations': [3550, 3550, 3950., 4300, 4300, -0.5, -0.5,  -0.5],

    '1267_correlations': (3700.0, 3700.0, 0, 0, 0, 3600.0, 3600.0, 0),

    '2345_correlations': (-0.5, 3900.0, 3900.0, 4300, 4300, 3700.0, 3700.0, 0),

    '2356_correlations': (0, 3550.0, 3550.0, 3925, 4300, 4300, -0.5, -0.5),

    '2378_correlations': (0, 3800.0, 3800.0, 0, 0, 0, 3700, 3700),

    '3467_correlations': (0, 0, 3550, 3550, 0, 3950, 3950, 0),

    '4578_correlations': (-0.5, -0.5, 3925, 4300, 4300, 3925, 3550, 3550)
}


for key, value in bs_params.items():
    print(f"{key}:{repr(get_gains(value))}")
    # print(f"{key}:{repr((get_gains(value) + Expt_FF.arr.astype(int))//2)}")

readouts_list = [BS1234_Readout,
                 BS1245_Readout,
                 BS1267_Readout,
                 BS2356_Readout,
                 BS2345_Readout,
                 BS2378_Readout,
                 BS3467_Readout,
                 BS4578_Readout,]

names = ["BS1234_Readout",
         "BS1245_Readout",
         "BS1267_Readout",
         "BS2356_Readout",
         "BS2345_Readout",
         "BS2378_Readout",
         "BS3467_Readout",
         "BS4578_Readout"]


# for ro, name in zip(readouts_list, names):
#     all_freqs = [ro[str(Q)]['Qubit']['Frequency'] for Q in range(1,9)]
#     for i in range(len(all_freqs)):
#         if all_freqs[i] > 4240:
#             all_freqs[i] = 4240
#         elif all_freqs[i] < 3540:
#             all_freqs[i] = -0.5
#     # print(all_freqs)
#     print(f"{name}:{repr(get_gains(all_freqs))}")