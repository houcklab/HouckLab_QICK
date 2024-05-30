from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import savgol_filter
from tqdm.notebook import tqdm
import time
import datetime
from tqdm import tqdm

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.YOKOGS200 import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import LoopbackProgramSpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import LoopbackProgramTrans

class CalibratedFlux(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self):
        # Define the yoko
        yoko1 = YOKOGS200(VISAaddress='GPIB1::2::INSTR', rm=visa.ResourceManager())
        yoko1.SetMode('voltage')

        # Define the yoko voltage vector
        volt_vec = np.linspace(self.cfg["yokoVoltageStart"],self.cfg["yokoVoltageStop"], self.cfg["yokoVoltageNumPoints"])

        # Define the frequency vector
        trans_freq = np.linspace(self.cfg["trans_freq_start"], self.cfg["trans_freq_stop"], self.cfg["TransNumPoints"])

        # Define the variables to store the data
        trans_I = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["TransNumPoints"]))
        trans_Q = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["TransNumPoints"]))

        # Get the data
        for i in tqdm(range(volt_vec.size)):

            # Set the yoko voltage
            yoko1.SetVoltage(volt_vec[i], toPrint = False)

            # take the transmission data
            data_I, data_Q = self._aquireTransData()
            trans_I[i, :] = data_I
            trans_Q[i, :] = data_Q

        # Save the data
        self.data = {'trans_I': trans_I, 'trans_Q': trans_Q, 'volt_vec': volt_vec, "trans_freq": trans_freq}

        return self.data

    def _aquireTransData(self):
        """
        Measure cavity transmission
        """

        expt_cfg = {
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  # number of points in the transmission frequecny
        }

        # Take the transmission data
        self.cfg["reps"] = self.cfg["trans_reps"]
        fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        results = []
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)

        # pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]

        return data_I, data_Q

    def calibrate(self, half_flux = 'min'):
        """
        Calibrate the flux
        :param half_flux: Can be 'min' or 'max'. Default is 'min'. Zero flux is assumed to be the opposite
        """

        # Get the data
        data = self.acquire()

        # Calculate the amplitude from I and Q data
        self.trans_amp = np.sqrt(data["trans_I"]**2 + data["trans_Q"]**2)

        # Find the frequency corresponding to the minimum amplitude
        self.resonant_freq = data["trans_freq"][np.argmin(self.trans_amp, axis = 1)]

        # Smoothen the resonant frequency
        self.resonant_freq_smooth = savgol_filter(self.resonant_freq, int(data["trans_freq"].size/10), 1)

        # Find the half flux point
        if half_flux == 'min':
            self.half_flux = data["volt_vec"][np.argmin(self.resonant_freq_smooth)]
        elif half_flux == 'max':
            self.half_flux = data["volt_vec"][np.argmax(self.resonant_freq_smooth)]
        else:
            raise Exception("Invalid Half flux extrema")

        self.zero_flux = self.half_flux - self.cfg["flux_quantum"] / 2
        # Update self.data and add resonant_freq, resonant_freq_smooth
        update_data = {"resonant_freq": self.resonant_freq, "resonant_freq_smooth": self.resonant_freq_smooth,
                       "trans_amp": self.trans_amp, "half_flux": self.half_flux, "zero_flux": self.zero_flux}
        self.data = self.data | update_data

        return self.data

    def display(self, data=None, **kwargs):
        if data is None:
            data = self.data

        fig, axs = plt.subplots(nrows=2, ncols=1, figsize=(14,10))

        # Plot 1 transmission vs flux
        im = axs[0].imshow(data["trans_amp"].T, aspect = 'auto',
                           extent=[data["volt_vec"][0], data["volt_vec"][-1], data["trans_freq"][0], data["trans_freq"][-1]],
                           origin='lower')
        axs[0].set_title("Transmission vs Flux")
        axs[0].set_xlabel("Voltage (V)")
        axs[0].set_ylabel("Frequency (MHz)")
        cbar = fig.colorbar(im, ax=axs[0])
        cbar.set_label("Transmission Amplitude")

        # Plot 2 Smoothened resonant frequency vs flux
        axs[1].plot(data["volt_vec"], data["resonant_freq_smooth"])
        axs[1].set_title("Smoothened Resonant Frequency")
        axs[1].set_xlabel("Voltage (in V)")
        axs[1].set_ylabel("Frequency (in MHz)")

        # Save the data
        plt.tight_layout()
        plt.savefig(self.iname + "_resonant.png" , dpi = 400)
        plt.close()

    def flux_to_yoko(self, phase):
        """
        Converts flux defined in flux quantum to yoko voltage
        """
        self.voltage_quantum = (self.half_flux - self.zero_flux)*2
        self.yoko_voltage = phase * self.voltage_quantum + self.zero_flux

        return self.yoko_voltage

    def yoko_to_flux(self, yoko_voltage, zero_flux, half_flux):
        """
        Converts yoko voltage to flux defined in flux quantum
        """
        voltage_quantum = (half_flux - zero_flux)*2
        flux = (yoko_voltage - zero_flux)/voltage_quantum

        return flux

    def save_data(self, data=None):
        # save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data)


