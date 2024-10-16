# -*- coding: utf-8 -*-

# This example configures the receiver for a basic sweep and
# plots the sweep. The x-axis frequency is derived from the start_freq
# and bin_size values returned after configuring the device.

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.sa_api import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mConstantTone import ConstantTone_Experiment
import time
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
import matplotlib as mpl
import seaborn as sns; sns.set() # styling

def connect():
    # Open device
    handle = sa_open_device()["handle"]

    return handle

def disconnect(handle):
    # Device no longer needed, close it
    sa_close_device(handle)



def sweep(handle, start = 1e9, stop = 2e9, ref = -30, rbw = 10e3, vbw = 10e3):

    # Convert start and stop to center and span
    center = (start+stop)/2
    span = (stop-start)/2

    # Configure device
    sa_config_center_span(handle, center, span)
    sa_config_level(handle, ref)
    sa_config_sweep_coupling(handle, rbw, vbw, 0)
    sa_config_acquisition(handle, SA_MIN_MAX, SA_LOG_SCALE)

    # Initialize
    sa_initiate(handle, SA_SWEEPING, 0)
    query = sa_query_sweep_info(handle)
    sweep_length = query["sweep_length"]
    start_freq = query["start_freq"]
    bin_size = query["bin_size"]

    # Get sweep
    sweep_max = sa_get_sweep_32f(handle)["max"]

    # return
    freqs = [start_freq + i * bin_size for i in range(sweep_length)]
    return freqs, sweep_max

class CalibrateRFSOCSignalHound(ConstantTone_Experiment):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def calibrate(self, meas_span = 1e6, debug = False):

        # Defining the sweep variables
        self.freq_vec = np.linspace(self.cfg['freq_start'], self.cfg['freq_stop'], self.cfg['freq_num'])
        self.gain_vec = np.linspace(self.cfg['gain_start'], self.cfg['gain_stop'], self.cfg['gain_num'])

        # Defining empty arrays to store data
        self.meas_power = np.full((self.freq_vec.size, self.gain_vec.size), np.nan)
        gain_ref = np.full(self.gain_vec.size, 0)

        # Connect to signal hound
        handle = connect()

        # Starting the loop
        for i in tqdm(range(self.freq_vec.size)):
            for j in range(self.gain_vec.size):
                # Setting the frequency and gain in the cfg
                self.cfg['freq'] = self.freq_vec[i]
                self.cfg['gain'] = int(self.gain_vec[j])

                # Running the constant tone
                self.acquire()

                # Wait for a second
                time.sleep(3)

                # Measuring the tone
                meas_start = self.freq_vec[i] * 1e6 - meas_span / 2
                meas_stop = self.freq_vec[i] * 1e6 + meas_span / 2

                # if i == 0:
                #     meas_freq, meas_power_data = sweep(handle,  meas_start, meas_stop, ref = 0, rbw = 5e3, vbw = 5e3)
                #
                #     # Find the index of the freq in meas_freq
                #     indx = np.argmin(np.abs(meas_freq - self.freq_vec[i]*1e6))
                #     gain_ref[j] = meas_power_data[indx] + 10

                # Measure again with correct reference
                meas_freq, meas_power_data = sweep(handle, meas_start, meas_stop, ref=gain_ref[j], rbw=5e3, vbw=5e3)

                # Plot the meas_freq vs meas_power_data if debug
                if debug:
                    fig, ax  = plt.subplots(1,1)
                    ax.scatter(np.array(meas_freq)/1e6, meas_power_data, c='r', s=10)
                    ax.set_xlabel('Frequency (in MHz)')
                    ax.set_ylabel('Power in dBm')
                    ax.set_ylim(-100,0)
                    ax.set_title("Gain is " + str(self.cfg['gain']) +
                                 " || Max at " + str(np.round(meas_freq[np.argmax(meas_power_data)]/1e6,1)) +
                                 " MHz and Value is "+ str(np.max(meas_power_data)))
                    plt.tight_layout()
                    plt.savefig(self.path_wDate + "_debug_"+str(i) + "_" + str(j) + ".png", dpi = 500)
                    plt.close(fig)

                indx = np.argmin(np.abs(meas_freq - self.freq_vec[i]*1e6))
                self.meas_power[i,j] = meas_power_data[indx]

        # Disconnect to signal hound
        disconnect(handle)

        self.data = {
            'config': self.cfg,
            'data': {
                'freq': self.freq_vec,
                'gain': self.gain_vec,
                'meas_power': self.meas_power
            }
        }

        return self.data

    def display_calibrated_data(self, data = None, plotDisp = False):
        if data is None:
            data = self.data

        # Unpack data
        freq_vec = data['data']['freq']
        gain_vec = data['data']['gain']
        meas_power = data['data']['meas_power']

        # Define figure and axes
        fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(12, 16))

        # Define colormap
        colors_gain = plt.cm.rainbow(np.linspace(0, 1, gain_vec.size))  # For gains
        colors_freq = plt.cm.viridis(np.linspace(0, 1, freq_vec.size))  # For frequencies

        # First subplot: freq_vec vs meas_power for different gains
        for i in range(gain_vec.size):
            ax1.scatter(freq_vec, meas_power[:, i], label=f'Gain {int(gain_vec[i] * 1e-3)}', color=colors_gain[i],
                        alpha=0.7)

        ax1.set_xlabel("Frequency (GHz)")
        ax1.set_ylabel("Output Power (dBm)")
        ax1.grid(which='major', color='#808080', linestyle=':', linewidth=0.5)
        ax1.set_title("Frequency vs Output Power for Different Gains")

        # Colorbar for first subplot
        norm_gain = mpl.colors.Normalize(vmin=np.min(gain_vec), vmax=np.max(gain_vec))
        cmap_gain = plt.cm.ScalarMappable(norm=norm_gain, cmap=plt.cm.rainbow)
        cbar1 = plt.colorbar(cmap_gain, ax=ax1, orientation='vertical')
        cbar1.set_label("Gain (dB)", labelpad=15)
        cbar1.set_ticks(np.linspace(np.min(gain_vec), np.max(gain_vec), num=5))

        # Second subplot: gain_vec vs meas_power for different frequencies
        for i in range(freq_vec.size):
            ax2.plot(gain_vec * 1e-3, meas_power[i, :], label=f'Frequency {freq_vec[i]} GHz', color=colors_freq[i],
                     alpha=0.7)

        ax2.set_xlabel("Gain (Thousands)")
        ax2.set_ylabel("Output Power (dBm)")
        ax2.grid(which='major', color='#808080', linestyle=':', linewidth=0.5)
        ax2.set_title("Gain vs Output Power for Different Frequencies")
        # ax2.legend(title="Frequency")

        # Colorbar for second subplot
        norm_freq = mpl.colors.Normalize(vmin=np.min(freq_vec), vmax=np.max(freq_vec))
        cmap_freq = plt.cm.ScalarMappable(norm=norm_freq, cmap=plt.cm.viridis)
        cbar2 = plt.colorbar(cmap_freq, ax=ax2, orientation='vertical')
        cbar2.set_label("Frequency (GHz)", labelpad=15)
        cbar2.set_ticks(np.linspace(np.min(freq_vec), np.max(freq_vec), num=5))

        # Adjust layout to prevent overlap
        fig.tight_layout(rect=[0, 0, 0.85, 0.96])  # Adjust right margin to fit colorbars

        # plt.tight_layout()
        plt.savefig(self.iname, dpi = 500)

        if plotDisp:
            plt.show(block = False)
        else:
            plt.close()

        return

if __name__ == "__main__":
    sweep()
