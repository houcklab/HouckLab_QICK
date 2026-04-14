'''
Helper to create adiabtic ramps of various shapes
'''

import numpy as np
import matplotlib.pyplot as plt

def generate_linear_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=0, reverse=False, flip=False):
    '''
    Creates a cubic ramp starting from initial gain at t = ramp_start_time ending at final gain at t = ramp_start_time
    + ramp_duration
    :param initial_gain: gain of ramp for t <= ramp_start_time
    :param final_gain: gain of ramp for t >= ramp_start_time + ramp_duration
    :param ramp_duration: total time to ramp between initial_gain and final_gain in clock cycles (4.65/16 ns)
    :param ramp_start_time: start time for ramp in clock cycles (4.65/16 ns)
    :param reverse: does nothing.
    :param flip: Flip the ramp so that it ramps from final_gain to initial_gain
    '''

    if ramp_start_time < 0:
        raise ValueError(f'ramp_start_time must be positive, given: {ramp_start_time}')
    if ramp_duration < 0:
        raise ValueError(f'ramp_duration must be positive, given: {ramp_duration}')

    total_duration = int(ramp_start_time + ramp_duration) + 1
    gains = np.interp(np.arange(-ramp_start_time,total_duration), xp=[0, total_duration],
                      fp=[initial_gain, final_gain] if not flip else [final_gain, initial_gain])

    return gains


def generate_cubic_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=0, reverse=False):
    '''
    Creates a cubic ramp starting from initial gain at t = ramp_start_time ending at final gain at t = ramp_start_time
    + ramp_duration
    :param initial_gain: gain of ramp for t <= ramp_start_time
    :param final_gain: gain of ramp for t >= ramp_start_time + ramp_duration
    :param ramp_duration: total time to ramp between initial_gain and final_gain in clock cycles (4.65/16 ns)
    :param ramp_start_time: start time for ramp in clock cycles (4.65/16 ns)
    :param reverse: if False (default), the ramp becomes flatter closer to final_gain at t =  ramp_start_time + ramp_duration
                    if True, the ramp is flat at the beginning and becomes steeper at the end
    '''

    if ramp_start_time < 0:
        raise ValueError(f'ramp_start_time must be positive, given: {ramp_start_time}')

    if ramp_duration < 0:
        raise ValueError(f'ramp_duration must be positive, given: {ramp_duration}')

    total_duration = int(ramp_start_time + ramp_duration) + 1
    gains = np.zeros(total_duration)

    for i in range(total_duration):
        if reverse:
            if i <= ramp_start_time:
                gains[i] = initial_gain
            elif i <= ramp_start_time + ramp_duration:
                t = i - ramp_start_time
                gains[i] = (final_gain - initial_gain) * np.power(t / ramp_duration, 3) + initial_gain
            else:
                gains[i] = final_gain
        else:
            if i <= ramp_start_time:
                gains[i] = initial_gain
            elif i <= ramp_start_time + ramp_duration:
                t = i - ramp_start_time - ramp_duration
                gains[i] = (final_gain - initial_gain) * np.power(t / ramp_duration, 3) + final_gain
            else:
                gains[i] = final_gain

    return gains

def generate_exp_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=0, reverse=False):
    '''
    Creates a cubic ramp starting from initial gain at t = ramp_start_time ending at final gain at t = ramp_start_time
    + ramp_duration
    :param initial_gain: gain of ramp for t <= ramp_start_time
    :param final_gain: gain of ramp for t >= ramp_start_time + ramp_duration
    :param ramp_duration: total time to ramp between initial_gain and final_gain in clock cycles (4.65/16 ns)
    :param ramp_start_time: start time for ramp in clock cycles (4.65/16 ns)
    :param reverse: if False (default), the ramp becomes flatter closer to final_gain at t =  ramp_start_time + ramp_duration
                    if True, the ramp is flat at the beginning and becomes steeper at the end
    '''

    if ramp_start_time < 0:
        raise ValueError(f'ramp_start_time must be positive, given: {ramp_start_time}')

    if ramp_duration < 0:
        raise ValueError(f'ramp_duration must be positive, given: {ramp_duration}')

    total_duration = int(ramp_start_time + ramp_duration) + 1
    gains = np.zeros(total_duration)

    tau_factor = 4 * (-1 if reverse else 1)

    for i in range(total_duration):

        if i <= ramp_start_time:
            gains[i] = initial_gain
        elif i <= ramp_start_time + ramp_duration:
            t = i - ramp_start_time
            gains[i] = (final_gain - initial_gain) * (np.exp(-t / ramp_duration * tau_factor) - 1) \
                       * (1/(np.exp(-tau_factor) - 1)) + initial_gain
        else:
            gains[i] = final_gain

    return gains

def generate_three_exp_ramp(initial_gain, final_gain, ramp_duration, reverse=False):
    tau1, A1, tau2, A2, tau3 = [ 2.00087636e+01, -6.70982023e-02,  4.67917212e+00, -5.44374547e+02, -1.17120788e-01]

    def func(t):
        if t == 0:
            return initial_gain
        elif t >= ramp_duration:
            return final_gain
        else:
            return initial_gain + (final_gain - initial_gain) * (
                        A1 * np.exp(-t / ramp_duration * tau1) + A2 * np.exp(-t / ramp_duration * tau2) + (1 - A1 - A2) * np.exp(
                    -t / ramp_duration * tau3) - 1) \
                / (A1 * np.exp(-tau1) + A2 * np.exp(-tau2) + (1 - A1 - A2) * np.exp(-tau3) - 1)

    gains = np.array([func(tt) for tt in range(ramp_duration)])
    if reverse:
        gains = np.flip(gains)
    return gains

def generate_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=0, reverse=False, ramp_shape='cubic'):
    if ramp_shape.lower() == 'cubic':
        return generate_cubic_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=ramp_start_time, reverse=reverse)
    if ramp_shape.lower() == 'exponential':
        return generate_exp_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=ramp_start_time, reverse=reverse)
    if ramp_shape.lower() == 'linear':
        return generate_linear_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=ramp_start_time)

if __name__ == '__main__':

    ramp_start_time = 50
    ramp_duration = 750

    initial_gain = 800
    final_gain = 4000

    # cubic_gains = generate_cubic_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time, reverse=True)
    # linear_gains = generate_linear_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time)
    exp_gains = generate_exp_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time, reverse=False)

    plt.plot(exp_gains)

    plt.axvline(ramp_start_time, color='black', linestyle=':', label='start time')
    plt.axvline(ramp_start_time+ramp_duration, color='black', linestyle=':', label='duration')

    plt.xlabel('Clock cycles')
    plt.ylabel('Gain (a.u.)')

    plt.legend()
    plt.show()
