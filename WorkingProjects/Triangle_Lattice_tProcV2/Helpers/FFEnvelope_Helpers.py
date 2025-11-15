from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FF_Crosstalk_Helper

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import *

'''
Quickly generates IQDataArrays for each fast flux channel.

Usage:
    IQDataArray = StepPulseArrays(self.cfg, "Gain_Pulse", "Gain_Expt")
'''


def get_gains(cfg, key) -> (list):
    '''Helper function to retrieve gains and apply crosstalk correction'''
    N = len(cfg['fast_flux_chs'])
    gains = [cfg['FF_Qubits'][str(Q)][key] for Q in range(1 ,N + 1)]
    gains = FF_Crosstalk_Helper.correct(gains)

    return np.array(gains, int)

# --------------------------------------------

def StepPulseArrays(cfg, initial_key, final_key) -> list:
    '''Output: list of IQArrays'''
    initial_gains = get_gains(cfg, initial_key)
    final_gains = get_gains(cfg, final_key)
    # print(initial_gains)
    # print("StepPulseArrays:", final_gains)
    return [Compensated_Pulse(fgain, igain, Qubit=j+1) for j, (igain, fgain) in enumerate(zip(initial_gains, final_gains))]

def CubicRampArrays(cfg, initial_key, final_key, ramp_duration, reverse=False) -> list:
    '''Output: list of IQArrays'''
    N = len(cfg['fast_flux_chs'])

    # print(f'initial gains: {list([int(cfg["FF_Qubits"][str(Q)][initial_key]) for Q in range(1, N+1)])}')
    # print(f'final gains: {list([int(cfg["FF_Qubits"][str(Q)][final_key]) for Q in range(1, N+1)])}')

    initial_gains = get_gains(cfg, initial_key)
    final_gains = get_gains(cfg, final_key)

    return [generate_cubic_ramp(igain, fgain, ramp_duration, reverse=reverse) for igain, fgain in zip(initial_gains, final_gains)]

def CompensatedRampArrays(cfg, prev_key, initial_key, final_key, ramp_duration, reverse=False) -> list:
    '''Ramp with possible jump at the beginning, e.g. jump from FFPulse to FFInit, then ramp from FFinit to FFExpts'''

    N = len(cfg['fast_flux_chs'])
    prev_gains = get_gains(cfg, prev_key)
    initial_gains = get_gains(cfg, initial_key)
    final_gains = get_gains(cfg, final_key)

    # print(f'prev_gains: {prev_gains}')
    # print(f'initial_gains: {initial_gains}')
    # print(f'final_gains: {final_gains}')
    # print(f'ramp_duration: {ramp_duration}')

    IQArray = []
    for j, Q in enumerate(range(1, N+1)):
        arr = generate_cubic_ramp(initial_gains[j], final_gains[j], ramp_duration, reverse=reverse)
        # arr = generate_three_exp_ramp(initial_gains[j], final_gains[j], ramp_duration, reverse=reverse)

        arr = Compensate(arr - prev_gains[j], prev_gains[j], Q)
        IQArray.append(arr)
        # Let's do compensated jumps and uncompensated ramps
        # if np.abs(prev_gains[j] - initial_gains[j]) > 100:
        #     arr = Compensated_Pulse(final_gains[j], prev_gains[j], Q)
        # else:
        #     arr = generate_cubic_ramp(initial_gains[j], final_gains[j], ramp_duration, reverse=reverse)
        # IQArray.append(arr)

    return IQArray

def LinearRampArrays(cfg, initial_key, final_key, ramp_duration, reverse=False) -> list:
    '''Output: list of IQArrays'''
    initial_gains = get_gains(cfg, initial_key)
    final_gains = get_gains(cfg, final_key)

    return [generate_linear_ramp(igain, fgain, ramp_duration, reverse=reverse) for igain, fgain in
            zip(initial_gains, final_gains)]

def ThreeExpRampArrays(cfg, initial_key, final_key, ramp_duration, reverse=False) -> list:
    '''Output: list of IQArrays'''
    initial_gains = get_gains(cfg, initial_key)
    final_gains = get_gains(cfg, final_key)

    return [generate_three_exp_ramp(igain, fgain, ramp_duration, reverse=reverse) for igain, fgain in
            zip(initial_gains, final_gains)]