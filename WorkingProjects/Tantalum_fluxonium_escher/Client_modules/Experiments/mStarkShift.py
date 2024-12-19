# This code performs qubit spectroscopy while sweeping cavity power to see the AC Stark shift on the qubit.
# This allows calibration of photon number in the readout resonator. Make sure to use qubit powers sufficiently low
# to not populate the qubit significantly.

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib.initialize import *
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
# from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransmission import LoopbackProgramTrans
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransmission_SaraTest import LoopbackProgramTrans
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice import LoopbackProgramSpecSlice
from tqdm.notebook import tqdm
import time
import datetime

class StarkShift(ExperimentClass):
    """
    to write
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)


    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        expt_cfg = {
            ### define the gainuator parameters
            "trans_gain_start": self.cfg["trans_gain_start"],
            "trans_gain_stop": self.cfg["trans_gain_stop"],
            "trans_gain_num": self.cfg["trans_gain_num"],
            #spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "SpecNumPoints": self.cfg["SpecNumPoints"],
        }

        if self.cfg["units"] == "DAC":
            gainVec = np.linspace(expt_cfg["trans_gain_start"], expt_cfg["trans_gain_stop"], expt_cfg["trans_gain_num"],
                                   dtype=int) ### for current simplicity set it to an int
        else:
            gainVec = np.logspace(np.log10(expt_cfg["trans_gain_start"]), np.log10(expt_cfg["trans_gain_stop"]), num= expt_cfg["trans_gain_num"],
                                   dtype = int)

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 2, figsize = (16,10), num = figNum)

        ### create the frequency array
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])

        Y = gainVec
        print(gainVec)
        Y_step = Y[1] - Y[0]

        self.spec_Imat = np.zeros((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]))
        self.data = {
            'config': self.cfg,
            'data': {'gain_fpts': gainVec,
                     'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                     }
        }

        X_spec = self.spec_fpts / 1e3
        X_spec_step = X_spec[1] - X_spec[0]

        Z_specamp = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specphase = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specI = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specQ = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        # Creating the extents of the plot
        if self.cfg['units'] == 'DAC':
            extents = [X_spec[0] - X_spec_step / 2, X_spec[-1] + X_spec_step / 2, Y[0] - Y_step / 2, Y[-1] + Y_step / 2]
        else:
            print(Y[-1]**2/Y[-2])
            extents = [X_spec[0] - X_spec_step / 2, X_spec[-1] + X_spec_step / 2, 10*np.log10(Y[0]**2/Y[1]), 10*np.log10(Y[-1]**2/Y[-2])]

        for i in range(expt_cfg["trans_gain_num"]):
            self.cfg["read_pulse_gain"] = gainVec[i]

            data_I, data_Q = self._acquireSpecData()

            data_I = np.array(data_I)  # This broke after the qick update to 0.2.287. Returns I, Q as lists instead of np arrays
            data_Q = np.array(data_Q)

            self.data['data']['spec_Imat'][i, :] = data_I
            self.data['data']['spec_Qmat'][i, :] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q


            avgamp0 = np.abs(sig)
            avgphase = np.angle(sig, deg=True)
            avgI = data_I
            avgQ = data_Q

                ## Amplitude
            Z_specamp[i, :] = avgamp0/np.mean(avgamp0)

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_1 = axs[0,0].imshow(
                    Z_specamp,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0,0], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_specamp)
                ax_plot_1.set_clim(vmin=np.nanmin(Z_specamp))
                ax_plot_1.set_clim(vmax=np.nanmax(Z_specamp))
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0,0], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[0,0].set_ylabel("RO gain (DAC)")
            axs[0,0].set_xlabel("Spec Frequency (GHz)")
            axs[0,0].set_title("Qubit Spec : Amplitude")

            ## Phase
            Z_specphase[i, :] = avgphase

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_2 = axs[1,0].imshow(
                    Z_specphase,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1,0], extend='both')
                cbar2.set_label('Phase', rotation=90)
            else:
                ax_plot_2.set_data(Z_specphase)
                ax_plot_2.set_clim(vmin=np.nanmin(Z_specphase))
                ax_plot_2.set_clim(vmax=np.nanmax(Z_specphase))
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1,0], extend='both')
                cbar2.set_label('Phase', rotation=90)

            axs[1,0].set_ylabel("RO gain (DAC)")
            axs[1,0].set_xlabel("Spec Frequency (GHz)")
            axs[1,0].set_title("Qubit Spec : Phase")

            ## I
            Z_specI[i, :] = avgI

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_3 = axs[0,1].imshow(
                    Z_specI,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[0,1], extend='both')
                cbar3.set_label('I', rotation=90)
            else:
                ax_plot_3.set_data(Z_specI)
                ax_plot_3.set_clim(vmin=np.nanmin(Z_specI))
                ax_plot_3.set_clim(vmax=np.nanmax(Z_specI))
                cbar3.remove()
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[0,1], extend='both')
                cbar3.set_label('I', rotation=90)

            axs[0,1].set_ylabel("RO gain (DAC)")
            axs[0,1].set_xlabel("Spec Frequency (GHz)")
            axs[0,1].set_title("Qubit Spec : I")

            ## Q
            Z_specQ[i, :] = avgQ

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_4 = axs[1,1].imshow(
                    Z_specQ,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar4 = fig.colorbar(ax_plot_4, ax=axs[1,1], extend='both')
                cbar4.set_label('Q', rotation=90)
            else:
                ax_plot_4.set_data(Z_specQ)
                ax_plot_4.set_clim(vmin=np.nanmin(Z_specQ))
                ax_plot_4.set_clim(vmax=np.nanmax(Z_specQ))
                cbar4.remove()
                cbar4 = fig.colorbar(ax_plot_4, ax=axs[1,1], extend='both')
                cbar4.set_label('Q', rotation=90)

            axs[1,1].set_ylabel("RO gain (DAC)")
            axs[1,1].set_xlabel("Spec Frequency (GHz)")
            axs[1,1].set_title("Qubit Spec : Q")
            plt.suptitle(self.iname)

            plt.tight_layout()

            if plotDisp and i == 0:
                plt.show(block=False)
                # Parth's fix
                plt.pause(5)
            elif plotDisp:
                plt.draw()
                plt.pause(5)

            if i == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  ### time for single full row in seconds
                timeEst = t_delta * expt_cfg["trans_gain_num"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname)  #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)

        return self.data

    def _acquireSpecData(self):
        ##### code to aquire just the cavity transmission data

        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / expt_cfg["SpecNumPoints"]
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                       expt_cfg["SpecNumPoints"])

        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal",
                                         progress=False)  # qick update deprecated ? , debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=self.cfg, soc=self.soc, soccfg=self.soccfg,
        #                                       outerFolder=r'Z:\TantalumFluxonium\Data\2024_06_29_cooldown\HouckCage_dev\dataTestSpecVsFlux', progress=True)
        # data = Instance_specSlice.acquire()
        # Instance_specSlice.display(data, plotDisp=False)
        data_I = data['data']['avgi']
        data_Q = data['data']['avgq']

        return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])




