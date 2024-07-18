from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.YOKOGS200 import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice import LoopbackProgramSpecSlice
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransmission_SaraTest import LoopbackProgramTrans
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import yoko1
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub

class SpecVsFlux(ExperimentClass):
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
    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        expt_cfg = {
            ### define the yoko parameters
            "yokoVoltageStart": self.cfg["yokoVoltageStart"],
            "yokoVoltageStop": self.cfg["yokoVoltageStop"],
            "yokoVoltageNumPoints": self.cfg["yokoVoltageNumPoints"],
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }

        ### define the yoko vector for the voltages, note this assumes that yoko1 already exists
        #yoko1 = YOKOGS200(VISAaddress='GPIB0::7::INSTR', rm=visa.ResourceManager())

        voltVec = np.linspace(expt_cfg["yokoVoltageStart"],expt_cfg["yokoVoltageStop"], expt_cfg["yokoVoltageNumPoints"])
        yoko1.SetVoltage(expt_cfg["yokoVoltageStart"])

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
        Y = voltVec
        Y_step = Y[1] - Y[0]
        Z_trans = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["TransNumPoints"]), np.nan)
        Z_specamp = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specphase = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specI = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specQ = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_Imat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]))
        self.data= {
            'config': self.cfg,
            'data': {'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'voltVec': voltVec
                     }
        }

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        #### loop over the yoko vector
        for i in range(expt_cfg["yokoVoltageNumPoints"]):
            ### set the yoko voltage for the specific run
            yoko1.SetVoltage(voltVec[i])

            ### take the transmission data
            data_I, data_Q = self._aquireTransData()
            self.data['data']['trans_Imat'][i,:] = data_I
            self.data['data']['trans_Qmat'][i,:] = data_Q

            #### plot out the transmission data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig) - np.mean(np.abs(sig))
            Z_trans[i, :] = avgamp0

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_0 = axs['b'].imshow(
                    Z_trans,
                    aspect='auto',
                    extent=[np.min(X_trans) - X_trans_step / 2, np.max(X_trans) + X_trans_step / 2,np.min(Y) - Y_step / 2, np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar0 = fig.colorbar(ax_plot_0, ax=axs['b'], extend='both')
                cbar0.set_label('a.u.', rotation=90)
            else:
                ax_plot_0.set_data(Z_trans)
                ax_plot_0.set_clim(vmin=np.nanmin(Z_trans))
                ax_plot_0.set_clim(vmax=np.nanmax(Z_trans))
                cbar0.remove()
                cbar0 = fig.colorbar(ax_plot_0, ax=axs['b'], extend='both')
                cbar0.set_label('a.u.', rotation=90)

            axs['b'].set_ylabel("yoko voltage (V)")
            axs['b'].set_xlabel("Cavity Frequency (GHz)")
            axs['b'].set_title("Cavity Transmission")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            ### take the spec data
            data_I, data_Q = self._aquireSpecData()
            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig) - np.mean(np.abs(sig))
            avgphase = np.angle(sig, deg = True) - np.mean(np.angle(sig, deg = True))
            avgI = np.abs(data_I) - np.mean(np.abs(data_I))
            avgQ = np.abs(data_Q) - np.mean(np.abs(data_Q))
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

            axs['a'].set_ylabel("yoko voltage (V)")
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

            axs['c'].set_ylabel("yoko voltage (V)")
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

            axs['d'].set_ylabel("yoko voltage (V)")
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

            axs['e'].set_ylabel("yoko voltage (V)")
            axs['e'].set_xlabel("Spec Frequency (GHz)")
            axs['e'].set_title("Qubit Spec : Q")
            plt.tight_layout()

            if plotDisp:# and i == 0:
                plt.show(block=False)
                plt.pause(0.1)
            #else:
            #    fig.canvas.draw()

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start ### time for single full row in seconds
                timeEst = t_delta*expt_cfg["yokoVoltageNumPoints"] ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: '+ datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname) #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)

        return self.data

    def _aquireTransData(self):
        ##### code to aquire just the cavity transmission data
        expt_cfg = {
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
        }
        ### take the transmission data
        self.cfg["reps"] = self.cfg["trans_reps"]
        fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            # prog = LoopbackProgramTransFF(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)
        #### pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]

        #### find the frequency corresponding to the cavity peak and set as cavity transmission number
        sig = data_I + 1j * data_Q
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        # peak_loc = np.argmax(avgamp0)
        self.cfg["read_pulse_freq"] = self.trans_fpts[peak_loc]

        return data_I, data_Q

    def _aquireSpecData(self):
        ##### code to aquire just the qubit spec data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        ### take the transmission data
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / expt_cfg["SpecNumPoints"]
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]
        fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        results = []
        start = time.time()
        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        #Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=self.cfg, soc=self.soc, soccfg=self.soccfg,
        #                                       outerFolder=r'Z:\TantalumFluxonium\Data\2024_06_29_cooldown\HouckCage_dev\dataTestSpecVsFlux', progress=True)
        #data = Instance_specSlice.acquire()
        # Instance_specSlice.display(data, plotDisp=False)
        data_I = data['data']['avgi']
        data_Q = data['data']['avgq']

        return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


