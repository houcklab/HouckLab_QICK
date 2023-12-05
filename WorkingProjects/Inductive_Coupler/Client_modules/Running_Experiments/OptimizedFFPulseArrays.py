import numpy as np
import h5py
from scipy.optimize import curve_fit, minimize
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt


def get_data(file_location, file_name, i_data=False):
    Qubit = file_location + file_name

    with h5py.File(Qubit, "r") as f:
        delay_pts = f['delay_pts'][()]
        spec_freq = f['spec_fpts'][()]
        spec_Qmat = f['spec_Qmat'][()]
        spec_Imat = f['spec_Imat'][()]

    Xlist = spec_freq / 1e3
    Ylist = delay_pts

    X, Y = np.meshgrid(Xlist, Ylist)
    Z = spec_Qmat
    if i_data:
        Z = spec_Imat
    return list(X[0]), list(Y[:, 0]), Z.tolist()


def stitch_data(datdir, fns, i_data=False):
    if type(fns) == str:  # just one file
        q_freqs, q_delays, q_spec = get_data(datdir, fns, i_data=i_data)
        return [q_freqs], q_delays, [q_spec]
    for i, fn in enumerate(fns):
        if i == 0:
            q_freqs, q_delays, q_spec = get_data(datdir, fn, i_data=i_data)
            q_freqs = [q_freqs.copy() for _ in range(len(q_delays))]
        else:
            suppl_freqs, suppl_delays, suppl_spec = get_data(datdir, fn, i_data=i_data)
            # integrate dataset into first one
            for delay, spec in zip(suppl_delays, suppl_spec):
                if delay not in q_delays:  # add a new delay time
                    q_delays.append(delay)
                    q_freqs.append(suppl_freqs)
                    q_spec.append(spec)
                else:  # merge spec data into existing delay time
                    q_freqs[q_delays.index(delay)] += suppl_freqs
                    q_spec[q_delays.index(delay)] += spec
    # sort data by delays
    q_delays, q_freqs, q_spec = zip(*sorted(zip(q_delays, q_freqs, q_spec)))
    return q_freqs, q_delays, q_spec


def imshow(X, Y, Z, vmin=None, vmax=None):
    if vmin is None:
        vmin = np.min(Z)
    if vmax is None:
        vmax = np.max(Z)
    step = X[0][1] - X[0][0]
    step_y = Y[1][0] - Y[0][0]

    plt.imshow(
        Z,
        'summer',
        aspect='auto',
        extent=[np.min(X) - step / 2, np.max(X) + step / 2, np.min(Y) - step_y / 2, np.max(Y) + step_y / 2],
        vmin=vmin, vmax=vmax, origin='lower', interpolation='none'
    )
    plt.show()


def fit_function(x, x_0, a, b, c):
    return a * b / ((x - x_0) ** 2 + b ** 2) + c


def Lorentzian_fit(frequencies, points, guess, plot=False):
    if guess[1] < 0:  # negative amplitude --> look for minimum:
        guess[0] = frequencies[np.argmin(points)]  # put center frequency guess at minimum
    else:
        guess[0] = frequencies[np.argmax(points)]
    fit_params, pCov = curve_fit(fit_function, frequencies, points, p0=guess, maxfev=100000)
    if plot:
        df = frequencies[1] - frequencies[0]
        fitfreqs = list(df * np.arange(-int(fit_params[2]/df)*8, int(fit_params[2]/df)*8) + fit_params[0])
        fitdat = fit_function(fitfreqs, *fit_params)
        plt.plot(frequencies, points, '.')
        plt.plot(fitfreqs, fitdat, 'b', lw=0.5)
        xlim = plt.xlim()
        ylim = plt.ylim()
        plt.hlines(fit_params[3], xlim[0], xlim[1], ls='--', colors='gray', lw=0.5)
        plt.vlines(fit_params[0], ylim[0], ylim[1], ls='--', colors='gray', lw=0.5)
        plt.vlines(fit_params[0] - fit_params[2], ylim[0], ylim[1], ls=':', colors='gray', lw=0.5)
        plt.vlines(fit_params[0] + fit_params[2], ylim[0], ylim[1], ls=':', colors='gray', lw=0.5)
        plt.xlim(xlim)
        plt.ylim(ylim)
        plt.xlabel('frequency [GHz]')
        plt.ylabel('spec transmission [a.u.]')
        plt.show()

    # determine quality of fit
    ss_res = np.sum((points - fit_function(frequencies, *fit_params)) ** 2)
    ss_tot = np.sum((points - np.mean(points)) ** 2)
    rsq = 1 - (ss_res / ss_tot)

    return fit_params, pCov, rsq


def central_frequency(spec_Qmat, spec_freqs, guesses=None, minimum=True, plot=False):
    central_frequencies = []

    for i in range(len(spec_Qmat)):
        if minimum and guesses[0] is None:
            guesses[0] = spec_freqs[np.argmin(spec_Qmat[i])]
        elif guesses[0] is None:
            guesses[0] = spec_freqs[np.argmax(spec_Qmat[i])]
        plot = (True if i >= 30 else False) if plot else plot
        fit_params = Lorentzian_fit(spec_freqs, spec_Qmat[i], guesses, plot)
        frequency = fit_params[0]
        central_frequencies.append(frequency)
    return central_frequencies


def fitqubitfreqs(datdir, fn, guesses=None, endidx=None, isMin=True, plot=False):
    X, Y, Z = get_data(datdir, fn, i_data=False)  # FIXME: idata was set to True, but no idata arg
    spec_freqs = X[0]
    delay_times = Y[:, 0]
    spec_Qmat = Z
    if endidx:
        spec_freqs = spec_freqs[:endidx]
        delay_times = delay_times[:endidx]
        spec_Qmat = spec_Qmat[:endidx]

    # imshow(X, Y, Z)
    return np.array(delay_times), np.array(central_frequency(spec_Qmat, spec_freqs, guesses, minimum=isMin, plot=plot))


def get_qfreq(Ej, Ec):
    return (8 * Ej * Ec) ** 0.5 - Ec


def Ej_eff(phi_ext, Ej_max, d):
    # if Ej1 < Ej2:
    #     Ej1, Ej2 = Ej2, Ej1  # ensure that Ej1 >= Ej2
    # Ej_max = Ej1 + Ej2
    # d = (Ej1 - Ej2) / Ej_max
    return Ej_max * (np.cos(np.pi * phi_ext) ** 2 + d ** 2 * np.sin(np.pi * phi_ext) ** 2) ** 0.5


def estimatephi(qfreqs, qpars, phi_guess=0.5):
    Ej_max = qpars['Ej_max']
    d = qpars['d']
    Ec = qpars['Ec']
    phis = np.zeros_like(qfreqs)
    for i, qf in enumerate(qfreqs):
        res = minimize(lambda x: (get_qfreq(Ej_eff(x, Ej_max, d), Ec) - qf) ** 2,
                       phi_guess)
        phis[i] = res.x
    return phis % 1


def compensate_pulse(orig_in, orig_out, time_offset=0):
    # First take FFT of both
    orig_in_FFT = np.fft.rfft(orig_in[time_offset:])
    orig_out_FFT = np.fft.rfft(orig_out[time_offset:])
    plt.plot(np.abs(orig_in_FFT), 'b:')
    plt.plot(np.angle(orig_in_FFT), ':', c='orange')
    plt.plot(np.abs(orig_out_FFT), 'b')
    plt.plot(np.angle(orig_out_FFT), c='orange')
    plt.xlabel("FFT frequency [a.u.]")
    plt.ylabel("amplitude/phase")
    plt.show()

    # Second get inverse transfer fn by dividing
    invtrfn = orig_in_FFT / orig_out_FFT
    # invtrfn[120:] = 1.

    # Third compensate for inverse transfer fn in corrected input
    corr_in_FFT = orig_in_FFT * invtrfn
    corr_in = np.fft.irfft(corr_in_FFT, len(orig_in[time_offset:]))

    return corr_in


def compensate_pulse_testing(orig_in, orig_out, time_offset=0, plot=False):
    # First take FFT of both
    orig_in_FFT = np.fft.rfft(orig_in[time_offset:])
    orig_out_FFT = np.fft.rfft(orig_out[time_offset:])
    orig_out_FFT = [orig_out_FFT[0]] + \
                   [(orig_out_FFT[1] + 0.5 * orig_out_FFT[2])/1.5] + \
                   [(0.5 * orig_out_FFT[i - 1] + orig_out_FFT[i] + 0.5 * orig_out_FFT[i + 1])/2 for i in range(2, len(orig_out_FFT) - 1)] + \
                   [(orig_out_FFT[-1] + 0.5 * orig_out_FFT[-2])/1.5]
    if plot:
        plt.plot(np.abs(orig_in_FFT), 'b:')
        plt.plot(np.angle(orig_in_FFT), ':', c='orange')
        plt.plot(np.abs(orig_out_FFT), 'b')
        plt.plot(np.angle(orig_out_FFT), c='orange')
        plt.xlabel("FFT frequency [a.u.]")
        plt.ylabel("amplitude/phase")
        plt.show()

    # Second get inverse transfer fn by dividing
    invtrfn = orig_in_FFT / orig_out_FFT
    if plot:
        plt.plot(np.abs(invtrfn), ":", c='b', label='inverse transfer fn')
        plt.plot(np.angle(invtrfn), ":", c='orange')

    invtrfn[0] = 1  # do nothing to DC
    invtrfn[-19*len(invtrfn)//20:] = 1  # do nothing to high frequencies
    # invtrfn[120:] = 1.
    if plot:
        plt.plot(np.abs(invtrfn), c='b', label='inverse transfer fn, truncated')
        plt.plot(np.angle(invtrfn), c='orange')
        plt.legend()
        plt.show()

    # Third compensate for inverse transfer fn in corrected input
    corr_in_FFT = orig_in_FFT * invtrfn
    corr_in = np.fft.irfft(corr_in_FFT, len(orig_in[time_offset:]))
    trunc = [i for i in range(len(corr_in) - 1) if corr_in[i] > 1 and corr_in[i + 1] <= 1][0]
    corr_in = np.concatenate((corr_in[:trunc], np.ones(len(corr_in) - trunc)))

    return corr_in


def compensate_step_JM(datdir, fn, isMin=True, plot=False):
    x0 = 4.7  # [GHz] Lorentzian center
    a = -0.03  # 2 / 1e3  # [ADC units] lorentzian amplitude
    b = 0.07  # 8 / 1e3  # [GHz] lorentzian HWHM
    c = 0.20  # -0.2  # [ADC units] lorentzian offset
    guesses = [x0, a, b, c]
    delay_times, central_frequencies_3_clock = fitqubitfreqs(datdir, fn, guesses, isMin=isMin, plot=False)

    # add initial qubit freq buffer to beginning
    starting = 10
    ending = None
    added_zeros = np.concatenate([4.4992 * np.ones(starting), central_frequencies_3_clock[starting:ending]])

    # renormalize to amplitudes
    # added_zeros = np.concatenate([central_frequencies_3[0:ending],
    #                               central_frequencies_3_2[6:None]])
    amplitude_experiment = (added_zeros - 4.4992) / 0.202
    ideal_step = np.concatenate([np.zeros(starting), np.ones(len(amplitude_experiment) - starting)])

    # alternatively, solve for flux (which is linear with flux line current)
    phis = estimatephi(added_zeros, {'Ej_max': 23.6, 'd': 13.4 / 23.6, 'Ec': 0.200},  # Ej, Ec in GHz
                       phi_guess=0.33)
    phis_renorm = (phis - phis[0]) / np.mean((phis - phis[0])[-10:])
    # plt.plot(phis_renorm, label="phi")
    # plt.plot(amplitude_experiment, label='freq')
    # plt.legend()
    # plt.show()
    amplitude_experiment = phis_renorm

    # next three blocks determine the transfer-function-compensated step pulse
    offset = 6
    Fourier_transform_steps = np.fft.rfft(ideal_step[offset:])
    Fourier_transform_exp = np.fft.rfft(amplitude_experiment[offset:])
    if plot:
        freqs = np.fft.rfftfreq(len(delay_times[offset:]), 0.00235 * 3)  # dt = 3 clock cycles
        plt.plot(freqs, np.abs(Fourier_transform_steps))
        plt.plot(freqs, np.angle(Fourier_transform_steps))
        plt.plot(freqs, np.abs(Fourier_transform_exp))
        plt.plot(freqs, np.angle(Fourier_transform_exp))
        plt.ylim(-5, 5)
        plt.xlabel("FFT frequency [MHz]")
        plt.ylabel("amplitude/phase")
        plt.show()

    Inverse_Transfer_Function = Fourier_transform_steps / Fourier_transform_exp
    Inverse_Transfer_Function[80:] = 1.05
    # Inverse_Transfer_Function[47:50] *= np.exp(-1j * np.pi /12)

    Compensated_pulse = Fourier_transform_steps * Inverse_Transfer_Function
    fft_back_to_time = np.fft.irfft(Compensated_pulse, len(ideal_step[offset:]))  # vs back to time space

    # supersample by 3x to match clock cycles #FIXME correct?
    fft_lengthened = np.repeat(fft_back_to_time, 3)
    filtered_signal = savgol_filter(fft_lengthened, 3, 1)  # linear interpolation
    # filtered_signal = fft_lengthened  # linear interpolation

    # FIXME what are the next three lines for?
    filtered_signal = np.concatenate([np.zeros(3), filtered_signal])

    difference = filtered_signal[15:] - np.ones(len(filtered_signal[15:]))
    filtered_signal = np.concatenate([filtered_signal[:15], np.ones(len(difference)) + 1 * difference])
    return filtered_signal


def compensate_delta(datdir, fn, endidx=None, isMin=True, time_offset=0):
    x0 = 4.5  # [GHz] Lorentzian center
    a = -0.01  # 2 / 1e3  # [ADC units] lorentzian amplitude
    b = 0.08  # 8 / 1e3  # [GHz] lorentzian HWHM
    c = 0.02  # -0.2  # [ADC units] lorentzian offset
    guesses = [x0, a, b, c]
    delay_times, qfreqs = fitqubitfreqs(datdir, fn, guesses, endidx, isMin, plot=True)

    ideal_delta = np.concatenate([np.zeros(9), np.ones(3), np.zeros(len(delay_times)-9-3)])
    if endidx:
        ideal_delta = ideal_delta[:endidx]

    # solve for flux (which is linear with flux line current) and normalize
    phis = estimatephi(qfreqs, {'Ej_max': 23.6, 'd': 13.4 / 23.6, 'Ec': 0.200},  # Ej, Ec in GHz
                       phi_guess=0.33)
    phis_renorm = (phis - phis[0]) / np.min(phis - phis[0])
    # plt.plot(ideal_delta, label='in')
    # plt.plot(phis_renorm, label="phi")
    # plt.legend()
    # plt.show()

    corr_in = compensate_pulse(ideal_delta, phis_renorm, time_offset)
    # supersample by 3x to match clock cycles #FIXME correct?
    filtered_signal = savgol_filter(corr_in, 3, 1)  # linear interpolation
    # filtered_signal = fft_lengthened  # linear interpolation

    return filtered_signal


def compensate_step(datdir, fns, time_step=0, time_offset=0, plot=False, i_data=False):
    x0 = 4.9  # [GHz] Lorentzian center
    a = 0.08  # 2 / 1e3  # [ADC units] lorentzian amplitude
    b = 0.07  # 8 / 1e3  # [GHz] lorentzian HWHM
    c = 0.22  # -0.2  # [ADC units] lorentzian offset
    guess = [x0, a, b, c]
    q_freqs, q_delays, q_spec = stitch_data(datdir, fns, i_data=i_data)
    fitres = [Lorentzian_fit(f, s, guess, False) for f, s in zip(q_freqs, q_spec)]
    q_response = [f[0][0] for f in fitres]
    if plot:
        plt.plot([f[2] for f in fitres])
        plt.plot(*np.transpose([[i, f[2]] for i, f in enumerate(fitres) if f[2] < 0.75]), 'o')
        plt.show()
    # remove poor fits
    q_response = [0.5 * (q_response[i - 1] + q_response[i + 1]) if fitres[i][2] < 0.75 and i < len(q_response) - 1 else res
                  for i, res in enumerate(q_response)]

    ideal = np.concatenate([np.zeros(time_step), np.ones(len(q_delays)-time_step)])

    # solve for flux (which is linear with flux line current) and normalize
    phis = estimatephi(q_response, {'Ej_max': 23.6, 'd': 13.4 / 23.6, 'Ec': 0.200},  # Ej, Ec in GHz
                       phi_guess=0.33)
    phis_renorm = (phis - np.mean(phis[:5])) / (np.mean(phis[-10:]) - np.mean(phis[:5]))
    # phis_renorm = [phis_renorm[0]] + \
    #               [2 * phis_renorm[i] - 0.5 * phis_renorm[i-1] - 0.5 * phis_renorm[i+1] for i in range(1, len(q_delays) - 1)] + \
    #               [phis_renorm[-1]]
    if plot:
        plt.plot(ideal, label='in')
        plt.plot(phis_renorm, label="phi")
        plt.legend()
        plt.show()

    corr_in = compensate_pulse_testing(ideal, phis_renorm, time_offset, plot=plot)
    # supersample by 3x to match clock cycles
    # filtered_signal = savgol_filter(corr_in, 3, 1)  # linear interpolation
    # filtered_signal = fft_lengthened  # linear interpolation
    # filtered_signal[0] = 0  # FIXME: set first point to zero?
    # filtered_signal = np.concatenate((np.zeros(time_offset), corr_in))

    return corr_in  # filtered_signal


if __name__ == '__main__':
    plot = True
else:
    plot = False

# original step
vs_step_orig = np.ones(1500)  # clock cycles
# original step output
file_location = r"Z:\Jeronimo\Measurements\RFSOC_3Qubit\dataTestFFSpecCal\\"
# step_orig_out = r"dataTestFFSpecCal_2022_09_07\dataTestFFSpecCal_2022_09_07_17_09_06_data.h5"  # going from 20000 to 0
# step_orig_out = r"dataTestFFSpecCal_2022_09_12\dataTestFFSpecCal_2022_09_12_13_51_11_data.h5"  # going from 20000 to 0
# step_orig_out = r"dataTestFFSpecCal_2022_09_13\dataTestFFSpecCal_2022_09_13_16_52_32_data.h5"  # going from 20000 to 0
step_orig_out = [r'dataTestFFSpecCal_2022_09_28/dataTestFFSpecCal_2022_09_28_22_04_52_data.h5',
                 r'dataTestFFSpecCal_2022_09_29/dataTestFFSpecCal_2022_09_29_07_47_05_data.h5'
                ]
minimum = False
# corrected step--Okay this should now be the corrected form...
# vs_step_comp = compensate_step_JM(file_location, step_orig_out, isMin=minimum, plot=False)
vs_step_comp = compensate_step(file_location, step_orig_out, time_step=14, time_offset=13, i_data=True, plot=plot)
vs_step_comp_simple = np.concatenate([1.02 * np.ones(12), np.ones(1500)])

if plot:
    plt.plot(vs_step_orig)
    plt.plot(vs_step_comp)
    plt.plot(vs_step_comp_simple)
    plt.ylabel('pulse amplitude [a.u.]')
    plt.xlabel('time')
    plt.show()

# Just offset the total frequency and compensate in the other direction:


# plt.plot(vs_tosend_step, color = 'blue')
# plt.plot(new_step_function, color = 'red')
#
# fft_vs_step[(np.abs(fs_step-15.4) < 0.5)]  *= 1/1.2 #np.exp(1j * np.pi) * 0 #np.exp(1j * np.pi / 1) * 0  # cut signal around 14.12 MHz
# vs_tosend_step = np.fft.irfft(fft_vs_step)  # vs back to time space
# plt.plot(vs_tosend_step, color = 'orange')

# print(fft_vs_step)


# plt.show()

# plt.plot(vs, color = 'blue')
# plt.plot(vs_tosend, color = 'red')
# plt.show()

# idata = np.concatenate([np.array(vs_tosend[:200]), np.ones(20)])
# print(idata)
#
# print(vs_tosend)
#
# print(len(vs_tosend))
#
# print(np.max(np.abs(vs_tosend)))
#
# x_values = np.linspace(0, 500, 500)
#
# vs_tosend = np.sin(x_values / 50) ** 2
#
# length = int(0.05 // 0.0023)
# print(length)
# print(vs_tosend[:length])
#
# if length > len(vs_tosend):
#     additional_array = np.ones(length - len(vs_tosend))
# else:
#     additional_array = np.array([])
# idata = np.concatenate([vs_tosend[:length], additional_array])  # ensures
# print(idata)
# maximum_value = np.max(np.abs(idata))
# idata = idata.repeat(16)
# idata = idata / maximum_value
#
# qdata = np.zeros(length * 16)
# print(len(idata), len(qdata))
# print(idata)


#### Triple clock cycle step function

# original delta
# vs_delta_orig = np.concatenate([np.zeros(15), np.ones(3), np.zeros(1500)])
vs_delta_orig = np.concatenate([np.ones(15), np.zeros(3), np.ones(1500)])  # clock cycles
# original delta output
delta_orig_out = r'dataTestFFSpecCal_2022_09_09\dataTestFFSpecCal_2022_09_09_12_43_10_data.h5'
# vs_delta_comp = compensate_delta(file_location, delta_orig_out, isMin=minimum, time_offset=0)
# plt.plot(vs_step_orig)
# plt.plot(vs_step_comp)
# plt.plot(vs_delta_orig)
# plt.plot(vs_delta_comp)
# plt.show()

# # New single clock cycle with compensated inverse Fourier trasnform:
#
# def get_data(file_location, file_name, index_for_IQ=0, override=False, idata=True):
#     Qubit = file_location + file_name
#
#     with h5py.File(Qubit, "r") as f:
#         delay_pts = f['delay_pts'][()]
#         spec_freq = f['spec_fpts'][()]
#         spec_Qmat = f['spec_Qmat'][()]
#         spec_Imat = f['spec_Imat'][()]
#
#     Xlist = spec_freq / 1e3
#     Ylist = delay_pts
#
#     X, Y = np.meshgrid(Xlist, Ylist)
#
#     if override and idata:
#         Z = np.asarray(spec_Qmat)
#         return (X, Y, Z)
#     if override and not idata:
#         Z = np.asarray(spec_Imat)
#         return (X, Y, Z)
#
#     range_q = np.max(spec_Qmat[index_for_IQ]) - np.min(spec_Qmat[index_for_IQ])
#     range_i = np.max(spec_Imat[index_for_IQ]) - np.min(spec_Imat[index_for_IQ])
#
#     if range_q > range_i:
#         Z = np.asarray(spec_Qmat)
#         return (X, Y, Z)
#
#     Z = np.asarray(spec_Imat)
#     return (X, Y, Z)
#
#
# file_location = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\dataTestFFSpecCal\dataTestFFSpecCal_2022_08_28"
# file = "\dataTestFFSpecCal_2022_08_28_00_48_49_data.h5"  # going from 20000 to 0
# X, Y, Z = get_data(file_location, file, override=True, idata=True)
# spec_freqs = X[0]
# delay_times_1_step_3 = Y[:, 0]
# spec_Qmat = Z
#
# x_0 = spec_freqs[np.argmin(spec_Qmat[11])]
# a = 2 / 1e3
# b = 8 / 1e3
# c = -0.2
# guesses = [x_0, a, b, c]
# central_frequencies_1_step_3 = central_frequency(spec_Qmat, spec_freqs, guesses, minimum=True)
#
# file_location = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\dataTestFFSpecCal\dataTestFFSpecCal_2022_08_28"
# file = "\dataTestFFSpecCal_2022_08_28_14_19_21_data.h5"  # going from 20000 to 0
# X, Y, Z = get_data(file_location, file, override=True, idata=True)
# spec_freqs = X[0]
# delay_times_1_step_4 = Y[:, 0]
# spec_Qmat = Z
#
# x_0 = spec_freqs[np.argmax(spec_Qmat[11])]
# a = 2 / 1e3
# b = 8 / 1e3
# c = -0.2
# guesses = [x_0, a, b, c]
# central_frequencies_1_step_4 = central_frequency(spec_Qmat, spec_freqs, guesses, minimum=False)
#
# delay_times_1cycle = np.concatenate([delay_times_1_step_3[:111], delay_times_1_step_4[1:111]])
# central_1cycle = np.concatenate([central_frequencies_1_step_3[:111], central_frequencies_1_step_4[1:111]])
# starting_number = 17
# ideal_step = np.concatenate([np.zeros(starting_number), np.ones(1),
#                              np.zeros(len(central_1cycle) - starting_number - 1)])  # , np.zeros(100), np.ones(100)])
# amplitude_experiment = (central_1cycle - 4.5) / 0.208
#
# Fourier_transform_steps = np.fft.rfft(ideal_step)
# Fourier_transform_steps *= np.exp(-1j * np.pi / 12)
# Fourier_transform_exp = np.fft.rfft(amplitude_experiment)
#
# Inverse_Transfer_Function = Fourier_transform_steps / Fourier_transform_exp
#
# # Inverse_Transfer_Function[50:] = 1
#
# Inverse_Transfer_Function[:6] = 1
# Inverse_Transfer_Function[9:] = 1
# Inverse_Transfer_Function[6:9] *= 0.8
#
# compensated_pulse = Inverse_Transfer_Function * Fourier_transform_steps  # * Transfer_Function
# fft_back_to_time = np.fft.irfft(compensated_pulse, len(ideal_step))  # vs back to time space
# fft_back_to_time[:17] = 0
# # single_delta = np.concatenate([fft_back_to_time[12:], np.zeros(200)])
# # print(single_delta[:20])
