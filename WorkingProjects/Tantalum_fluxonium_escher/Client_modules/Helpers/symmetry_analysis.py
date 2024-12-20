# Lev
# This file takes a 2d array stored in an h5py representing a flux sweep, and finds the index of the axis of highest symmetry.
# It then displays the data subtracted from its reversed version to see how symmetric it actually is.

########################################################################################################################
#                                                       Imports                                                        #
########################################################################################################################
import matplotlib.pyplot as plt
import h5py
import numpy as np
import scipy.signal

########################################################################################################################
#                                                    Read in data                                                      #
########################################################################################################################
fname = r'Z:\TantalumFluxonium\Data\2024_07_29_cooldown\HouckCage_dev\dataTestSpecVsFlux\dataTestSpecVsFlux_2024_08_30\dataTestSpecVsFlux_2024_08_30_22_44_29_data.h5'
f1 = h5py.File(fname, 'r')

trans_is = f1['trans_Imat'][()]
trans_qs = f1['trans_Qmat'][()]
trans = trans_is + 1j * trans_qs
voltages = f1['voltVec'][()]
trans_fpts = f1['trans_fpts'][()]

f1.close()

########################################################################################################################
#                                                    Symmetry analysis                                                 #
########################################################################################################################

# Find the index of the axis of highest symmetry by looping over all possible values and comparing the data to its
# reversed version. Yes, this is super inefficient, you can write your own if you want.
trans_rev = trans[-1::-1][:] # Data reversed along voltage axis
norms = []
norm_indices = []

# Move the reversed array up from the bottom until the two are even
for i in range(np.floor(len(voltages)/4).astype(int), len(voltages)): # Don't start at 0, symmetry should be not at edge
    # Divide by size to normalise for number of rows.
    norms.append(np.linalg.norm(trans[0:i][:] - trans_rev[-i:][:]) / (i + 1))
    norm_indices.append(i)
# Keep moving the reversed array up past the original array
for i in reversed(range(np.floor(len(voltages) / 4).astype(int), len(voltages))):
    norms.append(np.linalg.norm(trans[-i:][:] - trans_rev[0:i][:]) / (i + 1))
    norm_indices.append(i)

# How many positions we had to shift the data and reversed data to see the symmetry -- this is NOT the symmetry axis
shift_index = np.argmin(norms)
# Correct the index for the fact that we didn't start at 0
shift_index = shift_index + np.floor(len(voltages) / 4)
# The value at which to draw the symmetry line. Note that this rounds to closest index, although the actual point may
# lie in between two indices. Can fix if necessary, a little extra work. Won't matter for large enough len(voltages)
symm_value = voltages[np.round(shift_index/2).astype(int)]
#print(voltages[np.round(shift_index / 2).astype(int)])


########################################################################################################################
#                                                       Plot data                                                      #
########################################################################################################################

# Matrix distance plot
plt.figure()
plt.plot(norms)
plt.axvline(x=np.argmin(norms), linewidth = 1.5, color='red', linestyle='--')
plt.title('Distance between data and reversed data around pivot (does not start at 0)')

# Original data (magnitude and phase) plot with symmetry line
plt.figure()
plt.subplot(1, 2, 1)
plt.imshow(np.abs(trans), aspect='auto', origin='lower', extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])
#plt.plot([[1, trans_fpts[0]], [1, trans_fpts[-1]]], 'r')
plt.axhline(y=symm_value, linewidth=2, color='red', linestyle='--')
plt.title('Magnitude')

plt.subplot(1, 2, 2)
plt.imshow(scipy.signal.detrend(np.unwrap(np.angle(trans), np.pi), axis=0), aspect='auto', origin='lower',
           extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])
plt.axhline(y=symm_value, linewidth=2, color='red', linestyle='--')
plt.title('Phase')

# Original data, reversed data, and difference plot
plt.figure()
# Magnitude
ax_original = plt.subplot(2, 3, 1)
plt.imshow(np.abs(trans), aspect='auto', origin='lower', extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])
plt.title('Original')

plt.subplot(2, 3, 2, sharex = ax_original, sharey = ax_original)
nans = np.zeros([np.abs(shift_index.astype(int) - len(voltages)), len(trans_fpts)])
nans[:] = np.nan  # Because python
if shift_index > len(voltages): # The reversed data is above the original
    trans_rev_cut =  np.concatenate((nans, trans_rev[:len(voltages) - shift_index.astype(int)][:]))
else:  # We HAVE shifted the reversed data below the original
    trans_rev_cut = np.concatenate(trans_rev[shift_index.astype(int) - len(voltages):], nans)
plt.imshow(np.abs(trans_rev_cut), aspect='auto', origin='lower', extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])
plt.title('Reversed')


plt.subplot(2, 3, 3, sharex = ax_original, sharey = ax_original)
plt.imshow(np.abs(trans - trans_rev_cut), aspect='auto', origin='lower', extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])
plt.title('Difference')

# Phase
plt.subplot(2, 3, 4, sharex = ax_original, sharey = ax_original)
plt.imshow(np.unwrap(np.angle(trans)), aspect='auto', origin='lower', extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])
plt.title('Original')

plt.subplot(2, 3, 5, sharex = ax_original, sharey = ax_original)
nans = np.zeros([np.abs(shift_index.astype(int) - len(voltages)), len(trans_fpts)])
nans[:] = np.nan  # Because python
if shift_index > len(voltages): # The reversed data is above the original
    trans_rev_cut =  np.concatenate((nans, trans_rev[:len(voltages) - shift_index.astype(int)][:]))
else:  # We HAVE shifted the reversed data below the original
    trans_rev_cut = np.concatenate(trans_rev[shift_index.astype(int) - len(voltages):], nans)
plt.imshow(np.unwrap(np.angle(trans_rev_cut)), aspect='auto', origin='lower', extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])
plt.title('Reversed')


plt.subplot(2, 3, 6, sharex = ax_original, sharey = ax_original)
plt.imshow(np.unwrap(np.angle(trans - trans_rev_cut)), aspect='auto', origin='lower', extent=[trans_fpts[0], trans_fpts[-1], voltages[0], voltages[-1]])


plt.show()
