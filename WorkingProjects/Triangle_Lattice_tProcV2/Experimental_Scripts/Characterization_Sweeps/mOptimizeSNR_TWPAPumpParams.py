#### this code optimizes readout by driving the qubit and finding optimal single shot seperation
from matplotlib.pyplot import tight_layout

# from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.MixedShots_analysis import *

# from WorkingProjects.Triangle_Lattice_tProcV2.mTransmissionFF import SingleToneSpectroscopyProgramFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotProgram
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mSingleShotProgramFF_HigherLevelsMUX import SingleShotProgramFF_2StatesMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.hist_analysis import *

import matplotlib; matplotlib.use('Qt5Agg')

import time
from tqdm.notebook import tqdm
from windfreak import SynthHD


class SNROpt_wSingleShot(ExperimentClass):
    """
    This experiment optimizes the cavity readout parameters by driving the qubit and looking at the blobs in single shot
    It does this in multiple steps to ensure that it continues driving the qubit at the correct point for the optimization
        - option to perform a calibration for finding the qubit frequency before and during the experiment
        - starts with a default transmission scan at a known cavity power to find the cavity
        - with initial cavity frequency find, perform a spec measurement to find the qubit drive frequency, note that
            you can do the drive on the qubit in either a quasi-spec (long const pulse) or a pi pulse fashion
        - Once qubit parameters are found, the cavity attenuation and frequency are swept while monitoring the single
            shot blobs.
        - after a full frequency sweep for a given cavity attenuation, the user has to option to refind the qubit freq
            this option is given in the case that drift could be an issue

    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 calibrate = True, cavityAtten =None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, plotDisp = True, plotSave = True, calibrate=False, cavityAtten=None, figNum = 1, ax=None):
        #### function used to actually find the cavity parameters
        opt_index = self.cfg.get('qubit_sweep_index', 0)
        self.opt_index = opt_index
        self.gain_pts = np.linspace(self.cfg["gain_start"], self.cfg["gain_stop"], self.cfg["gain_pts"])
        self.fpts     = np.linspace(self.cfg["freq_start"], self.cfg["freq_stop"], self.cfg["freq_pts"])

        ####create arrays for storing the data
        X = self.fpts
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        Z_snr = np.full((len(Y), len(X)), np.nan)
        Z_fid = np.full((len(Y), len(X)), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'snr_mat': Z_snr, 'fid_mat': Z_fid,
                     'fpts':self.fpts, 'gain_pts':self.gain_pts,
                     'ro_opt_index':opt_index,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        if ax is None:
            fig, axs = plt.subplots(1, 2, figsize=(16, 5), num=figNum, tight_layout=True)
        else:
            print("using this ax")
            fig, axs = ax.get_figure(), [ax]
        fig.suptitle(self.titlename)


        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        # print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        # Connect to SynthHD
        synth = SynthHD(r'COM4')
        synth.init()
        synth[0].enable = True

        # Perform sweep
        for idx_gain in range(len(self.gain_pts)):
            # start_2 = time.time()
            ### set the cavity attenuation
            synth[0].power = self.gain_pts[idx_gain]
            ### start the loop over transmission points
            for idx_freq in range(len(self.fpts)):
                synth[0].frequency = self.fpts[idx_freq] * 1e6
                synth[0].enable = True

                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_envelopes=True)
                i_g, q_g, i_e, q_e = self._acquireSingleShotData()

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10,
                                                     print_fidelities=False)
                means, variances = multivariate_gaussian(data=[i_g, q_g, i_e, q_e])
                signal = np.linalg.norm(means[0] - means[1])
                noise = max(variances)
                snr = signal / noise

                self.data['data']['snr_mat'][idx_gain, idx_freq] = snr
                self.data['data']['fid_mat'][idx_gain, idx_freq] = fid

                #### plotting
                if idx_gain == 0 and idx_freq ==0:

                    ax_plot_0 = axs[0].imshow(
                        Z_snr,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)

                    ax_plot_1 = axs[1].imshow(
                        Z_fid * 100,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('fidelity (%)', rotation=90)
                else:
                    ax_plot_0.set_data(Z_snr)
                    ax_plot_0.autoscale()
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('SNR', rotation=90)

                    ax_plot_1.set_data(Z_fid)
                    ax_plot_1.autoscale()
                    cbar1.remove()
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('fidelity (%)', rotation=90)


                axs[0].set_ylabel("Pump Gain (a.u.)")
                axs[0].set_xlabel("Pump Frequency (GHz)")
                axs[1].set_ylabel("Pump Gain (a.u.)")
                axs[1].set_xlabel("Pump Frequency (GHz)")


                if plotDisp:
                    if idx_gain == 0 and idx_freq ==0:
                        plt.show(block=False)
                    else:
                        fig.canvas.draw()
                        fig.canvas.flush_events()


                if idx_gain == 0 and idx_freq ==0:  ### during the first run create a time estimate for the data acquisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * len(self.gain_pts) * len(self.fpts)  ### estimate for full scan
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        plt.savefig(self.iname)  #### save the figure
        # plt.show(block=False)
        return self.data


    def _acquireSingleShotData(self):
        #### pull the data from the single hots
        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ig, shots_qg = prog.acquire_shots(self.soc, load_envelopes=True, progress=False)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ie,shots_qe = prog.acquire_shots(self.soc, load_envelopes=True, progress=False)
        # print(prog.__dict__['gen_chs'])
        # gencfg = self.soccfg['gens'][9]
        # print('mixmux gencfg["maxv"]:', gencfg['maxv'])

        i_g = shots_ig[self.opt_index]
        q_g = shots_qg[self.opt_index]
        i_e = shots_ie[self.opt_index]
        q_e = shots_qe[self.opt_index]

        ### use the helper histogram to find the fidelity and such
        # fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, print_fidelities=False)
        #
        # self.fid = fid
        # self.threshold = threshold
        # self.angle = angle

        return i_g, q_g, i_e, q_e


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])