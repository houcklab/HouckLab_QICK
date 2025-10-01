import numpy as np
from scipy.signal import lfilter
import matplotlib.pyplot as plt

def sinusoid(ampl, period, length=256, plot=False):
    gains = ampl*np.sin(2 * np.pi / (period) * np.arange(0, length, 1/16))
    if plot:
        plt.scatter(np.arange(0, length, 1), gains[::16], marker='o', color='red', s=10,zorder=1)
        plt.plot(np.arange(0, length, 1/16), gains, marker='o',zorder=-1, color='black',markersize=1)
        plt.xlabel("Cycles (4.65 ns)")
        plt.ylabel("Gain")
        plt.show(block=False)
    return gains

# sinusoid(1000, 50, 256)



def apply_IIR(ab, waveform):
    '''ab: array (2,N), a and b parameters of the IIR filter
       pulse_shape: waveform, each entry having a timestep of 0.145 ns
       offset: constant offset to add to'''
    a, b = ab
    y = lfilter(b, a, waveform)
    # print(np.max(np.abs(np.imag(y))))
    y = np.real(y)

    return y

DIR = r"Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\_IIR_PulseCompensations"
# Fudging factor (See "0918 Compensated Pulse Ramseys" in the Triangle_Lattice OneNote)
true_asmpytote = np.array([-9208, -9814, -7200, -9696, -8458, -8877, -6039, -7206])
comp_asymptote = np.array([-9216, -9838, -7218, -9695, -8487, -8845, -6066, -7221])
fudge_scaling = comp_asymptote / true_asmpytote

def Compensate(waveform, offset, Qubit):
    '''Compensate a waveform'''

    if isinstance(Qubit, str):
        try:
            Qubit = int(Qubit)
        except Exception as e:
            print(f'Qubit needs to be an integer, given {type(Qubit)}')
            raise e

    if Qubit in [1,2,3,4,5,6,8]:
        iir_files = [rf'{DIR}\ff{Qubit}_0.csv',
                    rf'{DIR}\ff{Qubit}_1.csv',
                     rf'{DIR}\ff{Qubit}_2.csv',]
    elif Qubit in [7]:
        iir_files = [rf'{DIR}\ff{Qubit}_0.csv',
                     rf'{DIR}\ff{Qubit}_1.csv',
                     rf'{DIR}\ff{Qubit}_2.csv',
                     rf'{DIR}\ff{Qubit}_3.csv',]
                     # rf'{DIR}\ff{Qubit}_R.csv',]


    # if Qubit in [1]:
    #     iir_files.append(rf'{DIR}\ffr{Qubit}.csv')

    for iir_file in iir_files:
        ab = load_ab_file(iir_file)
        waveform = apply_IIR(ab, waveform)


    waveform = waveform * fudge_scaling[Qubit-1]

    return waveform + offset


def Compensated_Pulse(final_gain, initial_gain, Qubit):
    '''Function to quickly generate a compensated step pulse.'''

    # print("Going to this part of the code.")
    # print(final_gain, initial_gain)
    waveform = np.full(65536, final_gain - initial_gain)

    return Compensate(waveform, initial_gain, Qubit)

def load_ab_file(ab_file):
    ab = np.loadtxt(ab_file, dtype=np.complex128)
    # ab = IIR_DICT.get(ab_file)
    # if ab is None:
    #     ab = np.loadtxt(ab_file, dtype=np.complex128)
    #     print("Triangle_Lattice_tProcV2\\Helpers\\Compensated_Pulse_Josh.py: To avoid the time cost "
    #            f"of np.loadtxt() (and this print statement), I suggest hardcoding {ab_file} "
    #            "at the bottom of this file.")

    return ab

# IMPORTANT: COPY OVER ALL DECIMAL PLACES or unexpected behavior may arise!
array = np.array
IIR_DICT = {}
# IIR_DICT = {'Z:\\Joshua\\5-20-25_4QS5_pulse_comp\\ff1_1_toff=3.csv': array([[ 1.8983868595538118+0.06320462695124143j ,
#         -7.558630414873882 -0.2516559853067484j  ,
#         11.287878405783353 +0.3758170470460223j  ,
#         -7.493398275972596 -0.24948415558524673j ,
#          1.8657634341999045+0.062118467184074704j,
#          0.                +0.j                  ],
#        [ 2.035346361974425 +0.06776453749547756j ,
#         -8.102463109434476 -0.2697622750814613j  ,
#         12.097794537019176 +0.40278228159710183j ,
#         -8.029570220430347 -0.2673353894160248j  ,
#          1.998892439561814 +0.06655084569425004j ,
#          0.                +0.j                  ]]),
#  'Z:\\Joshua\\5-20-25_4QS5_pulse_comp\\ff1_2_t=3.csv': array([[ 1.5315554689877495+0.04988571552352139j ,
#         -4.38418051457285  -0.14280121509298338j ,
#          4.1776070497149504+0.13607271892599737j ,
#         -1.3247685721001674-0.043150267463684666j,
#          0.                +0.j                  ,
#          0.                +0.j                  ],
#        [ 2.2176950864615965+0.07223460621655288j ,
#         -6.429803679937553 -0.20943110696569367j ,
#          6.211261938401483 +0.20231278094418217j ,
#         -1.9989399128958423-0.06510932830218999j ,
#          0.                +0.j                  ,
#          0.                +0.j                  ]]),
#  'Z:\\Joshua\\5-20-25_4QS5_pulse_comp\\ff1_3_t=3.csv': array([[ 2.045763464734503 +0.07426883988077226j,
#         -6.102996152122182 -0.22156151081414022j,
#          6.071552193502926 +0.22041997790079604j,
#         -2.0143003433125193-0.07312661128625475j,
#          0.                +0.j                 ,
#          0.                +0.j                 ],
#        [ 2.030666696938172 +0.07372077093267265j,
#         -6.057190382559587 -0.21989859062619915j,
#          6.025226189111049 +0.2187381712492427j ,
#         -1.9986833406869053-0.07255965587454281j,
#          0.                +0.j                 ,
#          0.                +0.j                 ]]),
#  'Z:\\Joshua\\5-20-25_4QS5_pulse_comp\\ff2_5_5_offset_1606.csv': array([[ 1.8171624973396832+0.0538423621253008j  ,
#         -7.228627728041854 -0.2141835924811435j  ,
#         10.784840459400245 +0.31955385736208886j ,
#         -7.152432380920777 -0.21192593116689107j ,
#          1.7790571617812643+0.052713304443862685j,
#          0.                +0.j                  ],
#        [ 2.0416288969396406+0.06049328145140049j ,
#         -8.12192347957079  -0.2406518656318467j  ,
#         12.118098676161615 +0.35905817897255243j ,
#         -8.036926730027119 -0.23813341955170605j ,
#          1.9991226460552132+0.059233825042819134j,
#          0.                +0.j                  ]]),
#  'Z:\\Joshua\\5-20-25_4QS5_pulse_comp\\ff2_2renorm.csv': array([[ 1.9689097492960974+0.057921900947021154j,
#         -7.825506101032493 -0.2302127811629493j  ,
#         11.665179297284762 +0.3431692895157334j  ,
#         -7.729467551444816 -0.22738749404234798j ,
#          1.9208846135320348+0.056509084967168485j,
#          0.                +0.j                  ],
#        [ 2.0483993096029227+0.06026034558119167j ,
#         -8.142176504286763 -0.23952867374598502j ,
#         12.13830176925198  +0.3570877298946688j  ,
#         -8.043659694177897 -0.23663048051047386j ,
#          1.99913512724534  +0.05881107900522399j ,
#          0.                +0.j                  ]]),
#  'Z:\\Joshua\\5-20-25_4QS5_pulse_comp\\ff2_3_renorm.csv': array([[  33.76783018286726  -2.2523022358030935e-03j,
#         -101.65036212414913  +6.7800429178049709e-03j,
#          103.29920712476375  -6.8900202915343073e-03j,
#          -36.71186086258765  +2.4486680326628284e-03j,
#            1.2951868795439576-8.6388503165570583e-05j,
#            0.                +0.0000000000000000e+00j],
#        [  35.34465551203837  -2.3574759231202564e-03j,
#         -107.07962524896746  +7.1421728327554501e-03j,
#          110.13220252895522  -7.3457786491591195e-03j,
#          -40.39723158713912  +2.6944809462057535e-03j,
#            1.9999999955511576-1.3339928675062523e-04j,
#            0.                +0.0000000000000000e+00j]])}