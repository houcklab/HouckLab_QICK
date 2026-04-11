from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFTransmission import mFFTransmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecSliceReverse import FFSpecSliceReversed


class SpecVsFluxReversed(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum as a function of flux, specifically it uses a yoko to sweep
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through yoko
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)


    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1, individ_fit = False):
        expt_cfg = {
            ### define the yoko parameters
            "FFStart": self.cfg["FFStart"],
            "FFStop": self.cfg["FFStop"],
            "FFNumPoints": self.cfg["FFNumPoints"],
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }


        FFVec = np.linspace(expt_cfg["FFStart"],expt_cfg["FFStop"], expt_cfg["FFNumPoints"])
        self.fitted_qubit_freq = []
        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplot_mosaic([['a','a'],['b','c'],['d','e']], figsize = (8,10), num = figNum)
        ### create the frequency arrays for both transmission and spec
        ### also create empty array to fill with transmission and spec data
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        X_trans = (self.trans_fpts + self.cfg["cavity_LO"]/1e6) /1e3
        X_trans_step = X_trans[1] - X_trans[0]
        X_spec = self.spec_fpts/1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y = np.copy(FFVec)
        Y_step = Y[1] - Y[0]
        Z_trans = np.full((expt_cfg["FFNumPoints"], expt_cfg["TransNumPoints"]), np.nan)
        Z_specamp = np.full((expt_cfg["FFNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specphase = np.full((expt_cfg["FFNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specI = np.full((expt_cfg["FFNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specQ = np.full((expt_cfg["FFNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        cavity_freq = np.full((expt_cfg["FFNumPoints"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_Imat = np.zeros((expt_cfg["FFNumPoints"], expt_cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((expt_cfg["FFNumPoints"], expt_cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((expt_cfg["FFNumPoints"], expt_cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((expt_cfg["FFNumPoints"], expt_cfg["SpecNumPoints"]))
        self.data= {
            'config': self.cfg,
            'data': {'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'FFVec': FFVec
                     }
        }

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        #### loop over the yoko vector
        for i in range(expt_cfg["FFNumPoints"]):
            ### set the FF value for the specific run
            self.cfg["ff_gain"] = int(FFVec[i])
            self.cfg["ff_ramp_stop"] = int(FFVec[i])

            ### take the transmission data
            data_I, data_Q = self._acquireTransData()
            self.data['data']['trans_Imat'][i,:] = data_I
            self.data['data']['trans_Qmat'][i,:] = data_Q

            #### plot out the transmission data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig) #- np.mean(np.abs(sig))
            Z_trans[i, :] = avgamp0
            cavity_freq[i] = self.cfg["read_pulse_freq"]
            # print(cavity_freq[i])

            if i ==0: #### if first sweep add a colorbar
                ax_plot_0 = axs['b'].imshow(
                    Z_trans,
                    aspect='auto',
                    extent=[np.min(X_trans) - X_trans_step / 2, np.max(X_trans) + X_trans_step / 2,
                            np.min(Y) - Y_step / 2, np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar0 = fig.colorbar(ax_plot_0, ax=axs['b'], extend='both')
                cbar0.set_label('a.u.', rotation=90)
                # sc = axs['b'].scatter(cavity_freq, Y, s = 20)
            else:
                ax_plot_0.set_data(Z_trans)
                ax_plot_0.set_clim(vmin=np.nanmin(Z_trans))
                ax_plot_0.set_clim(vmax=np.nanmax(Z_trans))
                cbar0.remove()
                cbar0 = fig.colorbar(ax_plot_0, ax=axs['b'], extend='both')
                cbar0.set_label('a.u.', rotation=90)
                # sc.set_offsets(np.c_[cavity_freq, Y])

            axs['b'].set_ylabel("FF DAC")
            axs['b'].set_xlabel("Cavity Frequency (GHz)")
            axs['b'].set_title("Cavity Transmission")

            # Draw the chosen frequency point
            if self.cfg["draw_read_freq"]:
                axs['b'].scatter(self.cfg["read_pulse_freq"] / 1000, FFVec[i], 50, 'red', marker='*')

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            ### take the spec data
            data_I, data_Q = self._acquireSpecData(individ_fit= individ_fit)
            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig) #- np.mean(np.abs(sig))
            avgphase = np.angle(sig, deg = True) #- np.mean(np.angle(sig, deg = True))
            avgI = np.abs(data_I) #- np.mean(np.abs(data_I))
            avgQ = np.abs(data_Q) #- np.mean(np.abs(data_Q))
            ## Amplitude
            Z_specamp[i, :] = avgamp0

            if i ==0: #### if first sweep add a colorbar
                ax_plot_1 = axs['a'].imshow(
                    Z_specamp,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs['a'], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_specamp)
                ax_plot_1.set_clim(vmin=np.nanmin(Z_specamp))
                ax_plot_1.set_clim(vmax=np.nanmax(Z_specamp))
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs['a'], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            # Plot the qubit frequency point using the fitted frequency if individ_fit is True
            if individ_fit:
                axs['a'].scatter(self.fitted_qubit_freq[-1]/1e3, FFVec[i], 50, 'red', marker='*')

            axs['a'].set_ylabel("FF DAC")
            axs['a'].set_xlabel("Spec Frequency (GHz)")
            axs['a'].set_title("Qubit Spec : Amplitude")

            ## Phase
            Z_specphase[i, :] = avgphase

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_2 = axs['c'].imshow(
                    Z_specphase,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar2 = fig.colorbar(ax_plot_2, ax=axs['c'], extend='both')
                cbar2.set_label('Phase', rotation=90)
            else:
                ax_plot_2.set_data(Z_specphase)
                ax_plot_2.set_clim(vmin=np.nanmin(Z_specphase))
                ax_plot_2.set_clim(vmax=np.nanmax(Z_specphase))
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs['c'], extend='both')
                cbar2.set_label('Phase', rotation=90)

            axs['c'].set_ylabel("FF DAC")
            axs['c'].set_xlabel("Spec Frequency (GHz)")
            axs['c'].set_title("Qubit Spec : Phase")

            ## I
            Z_specI[i, :] = avgI

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_3 = axs['d'].imshow(
                    Z_specI,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar3 = fig.colorbar(ax_plot_3, ax=axs['d'], extend='both')
                cbar3.set_label('I', rotation=90)
            else:
                ax_plot_3.set_data(Z_specI)
                ax_plot_3.set_clim(vmin=np.nanmin(Z_specI))
                ax_plot_3.set_clim(vmax=np.nanmax(Z_specI))
                cbar3.remove()
                cbar3 = fig.colorbar(ax_plot_3, ax=axs['d'], extend='both')
                cbar3.set_label('I', rotation=90)

            axs['d'].set_ylabel("FF DAC")
            axs['d'].set_xlabel("Spec Frequency (GHz)")
            axs['d'].set_title("Qubit Spec : I")

            ## Q
            Z_specQ[i, :] = avgQ

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_4 = axs['e'].imshow(
                    Z_specQ,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar4 = fig.colorbar(ax_plot_4, ax=axs['e'], extend='both')
                cbar4.set_label('Q', rotation=90)
            else:
                ax_plot_4.set_data(Z_specQ)
                ax_plot_4.set_clim(vmin=np.nanmin(Z_specQ))
                ax_plot_4.set_clim(vmax=np.nanmax(Z_specQ))
                cbar4.remove()
                cbar4 = fig.colorbar(ax_plot_4, ax=axs['e'], extend='both')
                cbar4.set_label('Q', rotation=90)

            axs['e'].set_ylabel("FF DAC")
            axs['e'].set_xlabel("Spec Frequency (GHz)")
            axs['e'].set_title("Qubit Spec : Q")
            plt.tight_layout()

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start ### time for single full row in seconds
                timeEst = t_delta*expt_cfg["FFNumPoints"] ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: '+ datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname, dpi = 1000) #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)

        return self.data

    def search_frequency(self, target_freq = 1000, search_span = 1000, threshold = 5, num_trials = 5, plotDisp = True):
        """
        Function to search for a specific qubit frequency by sweeping the fast flux and finding the cavity peak
        Args:
            target_freq (float): target qubit frequency in MHz
            search_span (float): span in DAC to search around the guessed frequency
            threshold (float): threshold in MHz for acceptable frequency match
            num_trials (int): number of trials to attempt
        """
        def yoko_curve(freq):
            return (freq - self.cfg["c_yoko"])/self.cfg["m_yoko"]

        def del_yoko_2_del_FF(del_yoko):
            return del_yoko * self.cfg["m_yoko"]/self.cfg["m_ff"]

        # Find the probable dac value for the target frequency
        target_yoko = yoko_curve(target_freq)
        del_yoko = target_yoko - self.cfg["yokoVoltage"]
        ff_guess = del_yoko_2_del_FF(del_yoko)

        # Change the ffstart and ffstop to search around the guess
        self.cfg["FFStart"] = int(ff_guess - search_span/2)
        self.cfg["FFStop"] = int(ff_guess + search_span/2)

        num_run = 0
        while num_run < num_trials:
            num_run += 1

            # Do a spec vs ff in the search span
            data = self.acquire(progress=False, debug=False, plotDisp=True, plotSave=True, figNum = 9999, individ_fit = True)
            plt.close(9999)

            # Fit a line to the fitted qubit frequencies vs ff values
            from scipy.stats import linregress
            slope, intercept, r_value, p_value, std_err = linregress(np.linspace(self.cfg["FFStart"], self.cfg["FFStop"], self.cfg["FFNumPoints"]), self.fitted_qubit_freq)
            # Calculate the ff value that would give the target frequency
            ff_target = (target_freq - intercept)/slope

            # If the ff_target - ff_guess is within the search span, we are done or else change the ff_start and ff_stop and repeat
            if abs(ff_target - ff_guess) < search_span/2:
                print(f"Found target frequency {target_freq} MHz at ff value {ff_target}")
                # Do a trans and spec slice at the final ff_target to confirm
                self.cfg["ff_gain"] = int(ff_target)
                self.cfg["ff_ramp_stop"] = int(ff_target)
                self.fitted_qubit_freq = []
                datatrans_I, datatrans_Q = self._acquireTransData()
                dataspec_I, dataspec_Q = self._acquireSpecData(individ_fit= True)
                qubit_freq = self.fitted_qubit_freq[0]
                print(f"Confirmed qubit frequency at {qubit_freq} MHz")
                if np.abs(qubit_freq - target_freq) > threshold:
                    # Print the current difference
                    print(f"Current frequency difference is {np.abs(qubit_freq - target_freq)} MHz")
                    print(f"Warning: Target frequency not reached within threshold of {threshold} MHz")
                    # Update the ff_guess and reduce the search span by 50% and repeat
                    ff_guess = ff_target
                    search_span = search_span * 0.5
                    self.cfg["FFStart"] = int(ff_guess - search_span/2)
                    self.cfg["FFStop"] = int(ff_guess + search_span/2)
                    print(f"Updating search span to {search_span} and repeating")
                else:
                    print(f"Target frequency reached within threshold of {threshold} MHz")
                    print(f"Target ff value: {ff_target}, Target qubit frequency: {qubit_freq} MHz")
                    break
            else:
                print(f"Target frequency not found within span, updating search range and repeating")
                ff_guess = ff_target
                self.cfg["FFStart"] = int(ff_guess - search_span/2)
                self.cfg["FFStop"] = int(ff_guess + search_span/2)

        trans_fpts = np.linspace(self.cfg["trans_freq_start"], self.cfg["trans_freq_stop"],
                                      self.cfg["TransNumPoints"])
        spec_fpts = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                     self.cfg["SpecNumPoints"])

        # Update the "c_yoko" parameters based on the ff_target
        del_yoko = self.cfg["m_ff"] * ff_target / self.cfg["m_yoko"]
        new_c_yoko = target_freq - self.cfg["m_yoko"] * (self.cfg["yokoVoltage"] + del_yoko)
        print(f"Updating c_yoko from {self.cfg['c_yoko']} to {new_c_yoko}")
        self.cfg["c_yoko"] = new_c_yoko


        self.data = {
            "config": self.cfg,
            "data": {"trans_fpts" : trans_fpts, "spec_fpts": spec_fpts, "spec_I": dataspec_I, "spec_Q": dataspec_Q,
                     "trans_I" : datatrans_I, "trans_Q ": datatrans_Q, "ff_target": ff_target, "qubit_freq": qubit_freq,
                     "c_yoko": self.cfg["c_yoko"]}
        }

        # Create a plot with two subplots arranged vertically
        # In the top one plot the transmission amplitude vs trans_fpts
        # In the bottom one plot the spec amplitude vs spec_fpts
        # show the plot if plotDisp is True otherwise save the plot to a file and close it
        fig, axs = plt.subplots(2, 1, figsize=(8, 10))
        trans_mag = np.abs(datatrans_I + 1j * datatrans_Q)
        axs[0].plot(trans_fpts / 1e3, trans_mag, label="Transmission Amplitude")
        axs[0].set_xlabel("Frequency (GHz)")
        axs[0].set_ylabel("Amplitude (a.u.)")
        axs[0].legend()
        axs[0].set_title("Transmission Amplitude vs Frequency")

        # Spec plot
        spec_mag = np.abs(dataspec_I + 1j * dataspec_Q)
        axs[1].plot(spec_fpts / 1e3, spec_mag, label="Spec Amplitude")
        axs[1].set_xlabel("Frequency (GHz)")
        axs[1].set_ylabel("Amplitude (a.u.)")
        axs[1].legend()
        axs[1].set_title("Spec Amplitude vs Frequency")

        # Add a heading with the target frequency and found qubit frequency and target ff value
        fig.suptitle(f"Search for Target Frequency: {target_freq} MHz, Found Qubit Frequency: {qubit_freq} MHz, Target FF Value: {ff_target}", fontsize=16)
        plt.tight_layout()
        plt.savefig(self.iname.replace('.png', '_search.png'), dpi=1000)

        if plotDisp:
            plt.show()
        else:
            plt.close(fig)

        return self.data
    def _acquireTransData(self):
        self.cfg["read_pulse_freq"] = (self.cfg["trans_freq_start"]+self.cfg["trans_freq_stop"])/2
        self.cfg["TransSpan"] = (self.cfg["trans_freq_stop"] - self.cfg["trans_freq_start"])/2
        self.cfg['reps'] = self.cfg["trans_reps"]

        if 'pre_meas_delay' not in self.cfg.keys():
            self.cfg['pre_meas_delay'] = 1
        else:
            print(f"Pre Meas Delay = {self.cfg['pre_meas_delay']}")

        if 'negative_pulse' in self.cfg.keys():
            if self.cfg['negative_pulse']:
                print(f"Playing negative pulses for integration to be zero")
            else:
                print("Not playing negative pulses")
        else:
            self.cfg['negative_pulse'] = False
            print("Not playing negative pulses")

        expt_cfg = {
            "center": self.cfg["read_pulse_freq"],
            "span": self.cfg["TransSpan"],
            "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / (expt_cfg["expts"] - 1)
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results = []
        start = time.time()
        for f in fpts:
            self.cfg["read_pulse_freq"] = f
            prog = mFFTransmission(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True, progress=False))
            # time.sleep(0.01) # Added to wait for the RFSOC to send all data

        #### find the frequency corresponding to the peak
        data_I = np.array([elem[1] for elem in results])[:, 0, 0]
        data_Q = np.array([elem[2] for elem in results])[:, 0, 0]
        sig = data_I + 1j * data_Q
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.cfg["read_pulse_freq"] = fpts[peak_loc]

        return data_I, data_Q

    def _acquireSpecData(self, individ_fit = False):

        if self.cfg['qubit_spec_delay'] + self.cfg["qubit_length"] - self.cfg["pre_ff_delay"] - self.cfg["ff_length"] > 0:
            print("The qubit tone is on after the end of the fast flux pulse.")
        if self.cfg['qubit_spec_delay'] + self.cfg["qubit_length"] - self.cfg["pre_ff_delay"] < 0:
            print("The qubit tone starts before the beginning of the fast flux pulse.")
        if self.cfg["pre_meas_delay"] < self.cfg['qubit_spec_delay'] + self.cfg["qubit_length"]:
            print("Warning: Measurement starts before the end of the qubit pulse.")
        if self.cfg["pre_meas_delay"] > self.cfg["pre_ff_delay"] + self.cfg["ff_length"]:
            print("Warning: Measurement starts after the end of the fast flux pulse.")
        if self.cfg["pre_meas_delay"] + self.cfg["read_length"] > self.cfg["pre_ff_delay"] + self.cfg["ff_length"]:
            print("Warning: Measurement ends after the end of the fast flux pulse.")
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["qubit_freq_expts"] = self.cfg["SpecNumPoints"]
         # Create the experiment program
        prog = FFSpecSliceReversed(self.soccfg, self.cfg)
        # Collect the data
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)

        self.qubit_freqs = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                       self.cfg["qubit_freq_expts"])

        if individ_fit:
            # Fit the magnitiude data to find the qubit frequency with a gaussian fit in MHz
            from scipy.optimize import curve_fit
            def gaussian(x, a, x0, sigma, offset):
                return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2)) + offset

            sig = avgi[0][0] + 1j * avgq[0][0]
            avgamp0 = np.abs(sig)
            # Initial guess for the fit parameters
            initial_guess = [np.max(avgamp0) - np.min(avgamp0), self.qubit_freqs[np.argmax(avgamp0)], 30, np.min(avgamp0)]
            try:
                popt, pcov = curve_fit(gaussian, self.qubit_freqs, avgamp0, p0=initial_guess)
                fitted_freq = popt[1]
                print(f"Fitted qubit frequency: {fitted_freq} MHz")
            except RuntimeError:
                print("Error - curve_fit failed, using maximum point instead")
                fitted_freq = self.qubit_freqs[np.argmax(avgamp0)]
            self.fitted_qubit_freq.append(fitted_freq)

        return avgi[0][0], avgq[0][0]


    def save_data(self, data=None):
        if data is None:
            data = self.data
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


