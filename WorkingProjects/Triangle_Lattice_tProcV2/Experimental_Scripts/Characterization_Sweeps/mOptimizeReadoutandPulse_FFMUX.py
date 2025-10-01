#### this code optimizes readout by driving the qubit and finding optimal single shot seperation


# from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.MixedShots_analysis import *

# from WorkingProjects.Triangle_Lattice_tProcV2.mTransmissionFF import SingleToneSpectroscopyProgramFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotProgram
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mSingleShotProgramFF_HigherLevelsMUX import SingleShotProgramFF_2StatesMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.hist_analysis import *

import matplotlib; matplotlib.use('Qt5Agg')

import time
from tqdm.notebook import tqdm



class ReadOpt_wSingleShotFFMUX(ExperimentClass):
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
        expt_cfg = {
            ### define the attenuator parameters
            "cav_gain_Start": self.cfg["gain_start"],
            "cav_gain_Stop": self.cfg["gain_stop"],
            "cav_gain_Points": self.cfg["gain_pts"],
            ### transmission parameters
            "trans_freq_start": self.cfg["res_freqs"][opt_index] - self.cfg["span"]/2,  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["res_freqs"][opt_index] + self.cfg["span"]/2,  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["trans_pts"],  ### number of points in the transmission frequecny
        }
        self.gain_pts = np.linspace(expt_cfg["cav_gain_Start"], expt_cfg["cav_gain_Stop"], expt_cfg["cav_gain_Points"])
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])

        ####create arrays for storing the data
        X = self.trans_fpts + self.cfg["res_LO"]
        print(X)
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'fid_mat': Z_fid, 'overlap_mat': Z_overlap,
                     'trans_fpts':self.trans_fpts, 'gain_pts':self.gain_pts,
                     'ro_opt_index':opt_index,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        if ax is None:
            fig, axs = plt.subplots(1, 1, figsize=(8, 5), num=figNum)
            axs = [axs]
        else:
            print("using this ax")
            fig, axs = ax.get_figure(), [ax]
        axs[0].set_title(self.titlename)


        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        # print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over attenuations
        for idf_cavgain in range(len(self.gain_pts)):
            # start_2 = time.time()
            ### set the cavity attenuation
            self.cfg["res_gains"][opt_index] = self.gain_pts[idf_cavgain] / 32766. * len(self.cfg["Qubit_Readout_List"])
            ### start the loop over transmission points
            for idx_trans in range(len(self.trans_fpts)):
                self.cfg["res_freqs"][opt_index] = self.trans_fpts[idx_trans]

                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_envelopes=True)
                i_g, q_g, i_e, q_e = self._acquireSingleShotData()

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10, print_fidelities=False)


                Z_fid[idf_cavgain, idx_trans] = fid
                self.data['data']['fid_mat'][idf_cavgain, idx_trans] = fid

                #### plotting
                if idf_cavgain == 0 and idx_trans ==0:

                    ax_plot_0 = axs[0].imshow(
                        Z_fid*100,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)
                else:
                    ax_plot_0.set_data(Z_fid*100)
                    ax_plot_0.autoscale()
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)


                axs[0].set_ylabel("Cavity Gain (a.u.)")
                axs[0].set_xlabel("Cavity Frequency (GHz)")


                if plotDisp:
                    if idf_cavgain == 0 and idx_trans ==0:
                        plt.show(block=False)
                    else:
                        fig.canvas.draw()
                        fig.canvas.flush_events()


                if idf_cavgain == 0 and idx_trans ==0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * expt_cfg["cav_gain_Points"] * expt_cfg["TransNumPoints"]  ### estimate for full scan
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
        
class QubitPulseOpt_wSingleShotFFMUX(ExperimentClass):
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

    def acquire(self, progress=False, plotDisp = True, plotSave = True, calibrate=False,
                cavityAtten=None, figNum = 1, ax = None):

        Qubit_Sweep_Index = self.cfg.get('qubit_sweep_index', 0)
        self.Readout_Index = self.cfg.get('readout_index', 0)
        #### function used to actually find the cavity parameters
        expt_cfg = {
            ### define the attenuator parameters
            "qubit_gain_Start": self.cfg["qubit_gains"][Qubit_Sweep_Index]*32766 - self.cfg["q_gain_span"]/2,
            "qubit_gain_Stop": self.cfg["qubit_gains"][Qubit_Sweep_Index]*32766 + self.cfg["q_gain_span"]/2,
            "qubit_gain_Points": self.cfg["q_gain_pts"],
            ### transmission parameters
            "qubit_freq_start": self.cfg["qubit_freqs"][Qubit_Sweep_Index] - self.cfg["q_freq_span"]/2,
            "qubit_freq_stop": self.cfg["qubit_freqs"][Qubit_Sweep_Index] + self.cfg["q_freq_span"]/2,
            "QubitNumPoints": self.cfg["q_freq_pts"],  ### number of points in the transmission frequecny
        }
        self.gain_pts = np.linspace(expt_cfg["qubit_gain_Start"], expt_cfg["qubit_gain_Stop"], expt_cfg["qubit_gain_Points"])
        self.qubit_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["QubitNumPoints"])
        ####create arrays for storing the data
        X = self.qubit_fpts + self.cfg.get('qubit_LO', 0)
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'fid_mat': Z_fid, 'overlap_mat': Z_overlap,
                     'qubit_fpts':self.qubit_fpts, 'gain_pts':self.gain_pts,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        if ax is None:
            fig, axs = plt.subplots(1,1, figsize = (8,5), num = figNum)

            axs = [axs]
        else:
            fig, axs = ax.get_figure(), [ax]
        axs[0].set_title(self.titlename)


        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        # print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over attenuations
        for idf_qubitgain in range(len(self.gain_pts)):
            # start_2 = time.time()
            self.cfg["qubit_gains"][Qubit_Sweep_Index] = self.gain_pts[idf_qubitgain] / 32766.
            ### start the loop over transmission points
            for idx_qubit in range(len(self.qubit_fpts)):
                self.cfg["qubit_freqs"][Qubit_Sweep_Index] = self.qubit_fpts[idx_qubit]

                i_g, q_g, i_e, q_e = self._acquireSingleShotData()

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10)


                Z_fid[idf_qubitgain, idx_qubit] = fid
                self.data['data']['fid_mat'][idf_qubitgain, idx_qubit] = fid

                #### plotting
                if idf_qubitgain == 0 and idx_qubit ==0:

                    ax_plot_0 = axs[0].imshow(
                        Z_fid*100,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)
                else:
                    ax_plot_0.set_data(Z_fid*100)
                    ax_plot_0.autoscale()
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)




                axs[0].set_ylabel("Qubit Gain (a.u.)")
                axs[0].set_xlabel("Qubit Frequency (GHz)")


                if plotDisp:
                    if idf_qubitgain == 0 and idx_qubit ==0:
                        plt.show(block=False)
                    else:
                        fig.canvas.draw()
                        fig.canvas.flush_events()


                if idf_qubitgain == 0 and idx_qubit ==0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * expt_cfg["qubit_gain_Points"] * expt_cfg["QubitNumPoints"]  ### estimate for full scan
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
        shots_ig,shots_qg = prog.acquire_shots(self.soc, load_envelopes=True, progress=False)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ie,shots_qe = prog.acquire_shots(self.soc, load_envelopes=True, progress=False)
        print("RO index:", self.Readout_Index)
        i_g = shots_ig[self.Readout_Index]
        q_g = shots_qg[self.Readout_Index]
        i_e = shots_ie[self.Readout_Index]
        q_e = shots_qe[self.Readout_Index]

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

class ReadOpt_wSingleShotFF_HigherMUX(ExperimentClass):
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

    def acquire(self, ground = 0, excited = 1, progress=False, plotDisp = True, plotSave = True, calibrate=False, cavityAtten=None, figNum = 1):
        #### function used to actually find the cavity parameters
        expt_cfg = {
            ### define the attenuator parameters
            "cav_gain_Start": self.cfg["cav_gain_Start"],
            "cav_gain_Stop": self.cfg["cav_gain_Stop"],
            "cav_gain_Points": self.cfg["cav_gain_Points"],
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
        }
        self.gain_pts = np.linspace(expt_cfg["cav_gain_Start"], expt_cfg["cav_gain_Stop"], expt_cfg["cav_gain_Points"])
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])

        ####create arrays for storing the data
        X = self.trans_fpts + self.cfg['pulse_freqs'][0] + self.cfg['cavity_LO'] / 1e6
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'fid_mat': Z_fid, 'overlap_mat': Z_overlap,
                     'trans_fpts':self.trans_fpts, 'gain_pts':self.gain_pts,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
        plt.suptitle(self.titlename)


        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        # print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over attenuations
        for idf_cavgain in range(len(self.gain_pts)):
            # start_2 = time.time()
            ### set the cavity attenuation
            self.cfg["pulse_gains"] = [self.gain_pts[idf_cavgain] / 32766]
            ### start the loop over transmission points
            for idx_trans in range(len(self.trans_fpts)):
                self.cfg["mixer_freq"] = self.trans_fpts[idx_trans]
                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_envelopes=True)
                i_g, q_g, i_e, q_e = self._acquireSingleShotData_Higher(ground=ground, excited=excited)
                if plt.fignum_exists(10):
                    plt.close(10)

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10)

                # plt.show(block=False)
                # plt.pause(1)
                # plt.close(10)

                Z_fid[idf_cavgain, idx_trans] = fid
                self.data['data']['fid_mat'][idf_cavgain, idx_trans] = fid

                #### plotting
                if idf_cavgain == 0 and idx_trans ==0:

                    ax_plot_0 = axs[0].imshow(
                        Z_fid*100,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)
                else:
                    ax_plot_0.set_data(Z_fid*100)
                    ax_plot_0.autoscale()
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)




                axs[0].set_ylabel("Cavity Gain (a.u.)")
                axs[0].set_xlabel("Cavity Frequency (GHz)")
                axs[0].set_title("fidelity")

                #### perform a mixed shot analysis, decide to combine shots or not based on 'arb' or 'const' qubit drive

                if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
                    mixed_i = np.concatenate((i_g, i_e))
                    mixed_q = np.concatenate((q_g, q_e))

                    mixed = MixedShots(mixed_i, mixed_q)

                    overlapErr = mixed.OverlapErr

                    Z_overlap[idf_cavgain, idx_trans] = overlapErr
                    self.data['data']['overlap_mat'][idf_cavgain, idx_trans] = overlapErr

                    # while plt.fignum_exists(num=5):
                    #     plt.close(5)
                    # mixed.PlotGaussFit()
                elif self.cfg["qubit_pulse_style"] == "const":
                    mixed = MixedShots(i_e, q_e)

                    overlapErr = mixed.OverlapErr
                    Z_overlap[idf_cavgain, idx_trans] = overlapErr
                    self.data['data']['overlap_mat'][idf_cavgain, idx_trans] = overlapErr

                #### plotting
                if idf_cavgain == 0 and idx_trans ==0:
                    ax_plot_1 = axs[1].imshow(
                        Z_overlap,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('overlap err (a.u.)', rotation=90)
                else:
                    ax_plot_1.set_data(Z_overlap)
                    ax_plot_1.autoscale()
                    cbar1.remove()
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('overlap err (a.u.)', rotation=90)



                axs[1].set_ylabel("Cavity Atten (dB")
                axs[1].set_xlabel("Cavity Frequency (GHz)")
                axs[1].set_title("overlap err")

                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)


                if idf_cavgain == 0 and idx_trans ==0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * expt_cfg["cav_gain_Points"] * expt_cfg["TransNumPoints"]  ### estimate for full scan
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        plt.savefig(self.iname)  #### save the figure

        return self.data

    def _acquireSingleShotData(self):
        #### pull the data from the single hots
        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ig,shots_qg = prog.acquire(self.soc, load_envelopes=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_envelopes=True)

        i_g = shots_ig[0][0]
        q_g = shots_qg[0][0]
        i_e = shots_ie[0][0]
        q_e = shots_qe[0][0]

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e

    def _acquireSingleShotData_Higher(self, ground = 0, excited = 1):
        #### pull the data from the single hots
        self.cfg["pulse_expt"] = {}
        prog = SingleShotProgramFF_2StatesMUX(soc = self.soc, soccfg=self.soccfg, cfg=self.cfg)#cfg=config,soc=soc,soccfg=soccfg
        data = prog.acquire(ground_pulse=ground, excited_pulse=excited)

        # prog.display(data = data)

        i_g = data['I0']
        q_g = data['Q0']
        i_e = data['I1']
        q_e = data['Q1']

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e

    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])









class QubitPulseOpt_wSingleShotFF_HigherMUX(ExperimentClass):
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

    def acquire(self, ground = 0, excited = 1, progress=False, plotDisp = True, plotSave = True, calibrate=False,
                cavityAtten=None, figNum = 1, Qubit_Sweep_Index = 0):
        #### function used to actually find the cavity parameters
        expt_cfg = {
            ### define the attenuator parameters
            "qubit_gain_Start": self.cfg["qubit_gain_Start"],
            "qubit_gain_Stop": self.cfg["qubit_gain_Stop"],
            "qubit_gain_Points": self.cfg["qubit_gain_Points"],
            ### transmission parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "QubitNumPoints": self.cfg["QubitNumPoints"],  ### number of points in the transmission frequecny
        }
        self.gain_pts = np.linspace(expt_cfg["qubit_gain_Start"], expt_cfg["qubit_gain_Stop"], expt_cfg["qubit_gain_Points"])
        self.qubit_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["QubitNumPoints"])

        ####create arrays for storing the data
        X = self.qubit_fpts
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'fid_mat': Z_fid, 'overlap_mat': Z_overlap,
                     'qubit_fpts':self.qubit_fpts, 'gain_pts':self.gain_pts,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
        plt.suptitle(self.titlename)


        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        # print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over attenuations

        for idf_qubitgain in range(len(self.gain_pts)):
            # start_2 = time.time()
            ### set the cavity attenuation
            self.cfg["qubit_gain"] = self.gain_pts[idf_qubitgain]
            if excited == 2:
                self.cfg["qubit_gain12"] = self.gain_pts[idf_qubitgain]
            else:
                self.cfg["qubit_gain01"] = self.gain_pts[idf_qubitgain]
            ### start the loop over transmission points
            for idx_qubit in range(len(self.qubit_fpts)):
                if excited == 2:
                    self.cfg["qubit_freq12"] = self.qubit_fpts[idx_qubit]
                else:
                    self.cfg["qubit_freq01"] = self.qubit_fpts[idx_qubit]
                print(self.cfg["qubit_gain01"], self.cfg["qubit_gain12"], self.cfg["qubit_freq01"], self.cfg["qubit_freq12"])
                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_envelopes=True)
                i_g, q_g, i_e, q_e = self._acquireSingleShotData_Higher(ground = ground, excited = excited)
                if plt.fignum_exists(10):
                    plt.close(10)

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10)

                # plt.show(block=False)
                # plt.pause(1)
                # plt.close(10)

                Z_fid[idf_qubitgain, idx_qubit] = fid
                self.data['data']['fid_mat'][idf_qubitgain, idx_qubit] = fid

                #### plotting
                if idf_qubitgain == 0 and idx_qubit ==0:

                    ax_plot_0 = axs[0].imshow(
                        Z_fid*100,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)
                else:
                    ax_plot_0.set_data(Z_fid*100)
                    ax_plot_0.autoscale()
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)




                axs[0].set_ylabel("Cavity Atten (dB")
                axs[0].set_xlabel("Cavity Frequency (GHz)")
                axs[0].set_title("fidelity")

                #### perform a mixed shot analysis, decide to combine shots or not based on 'arb' or 'const' qubit drive

                if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
                    mixed_i = np.concatenate((i_g, i_e))
                    mixed_q = np.concatenate((q_g, q_e))

                    mixed = MixedShots(mixed_i, mixed_q)

                    overlapErr = mixed.OverlapErr

                    Z_overlap[idf_qubitgain, idx_qubit] = overlapErr
                    self.data['data']['overlap_mat'][idf_qubitgain, idx_qubit] = overlapErr

                    # while plt.fignum_exists(num=5):
                    #     plt.close(5)
                    # mixed.PlotGaussFit()
                elif self.cfg["qubit_pulse_style"] == "const":
                    mixed = MixedShots(i_e, q_e)

                    overlapErr = mixed.OverlapErr
                    Z_overlap[idf_qubitgain, idx_qubit] = overlapErr
                    self.data['data']['overlap_mat'][idf_qubitgain, idx_qubit] = overlapErr

                #### plotting
                if idf_qubitgain == 0 and idx_qubit ==0:
                    ax_plot_1 = axs[1].imshow(
                        Z_overlap,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('overlap err (a.u.)', rotation=90)
                else:
                    ax_plot_1.set_data(Z_overlap)
                    ax_plot_1.autoscale()
                    cbar1.remove()
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('overlap err (a.u.)', rotation=90)



                axs[1].set_ylabel("Qubit Gain (a.u.)")
                axs[1].set_xlabel("Qubit Frequency (GHz)")
                axs[1].set_title("overlap err")

                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)


                if idf_qubitgain == 0 and idx_qubit ==0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * expt_cfg["qubit_gain_Points"] * expt_cfg["QubitNumPoints"]  ### estimate for full scan
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        plt.savefig(self.iname)  #### save the figure

        return self.data



    def _acquireSingleShotData(self):
        #### pull the data from the single hots
        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ig,shots_qg = prog.acquire(self.soc, load_envelopes=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_envelopes=True)

        i_g = shots_ig[0][0]
        q_g = shots_qg[0][0]
        i_e = shots_ie[0][0]
        q_e = shots_qe[0][0]

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e

    def _acquireSingleShotData_Higher(self, ground = 0, excited = 1):
        #### pull the data from the single hots
        self.cfg["pulse_expt"] = {}
        prog = SingleShotProgramFF_2StatesMUX(soc = self.soc, soccfg=self.soccfg, cfg=self.cfg)#cfg=config,soc=soc,soccfg=soccfg
        data = prog.acquire(ground_pulse=ground, excited_pulse=excited)

        # prog.display(data = data)

        i_g = data['I0']
        q_g = data['Q0']
        i_e = data['I1']
        q_e = data['Q1']

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e

    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

class ROTimingOpt_wSingleShotFFMUX(ExperimentClass):
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

    def acquire(self, progress=False, plotDisp = True, plotSave = True, calibrate=False, cavityAtten=None, figNum = 1):
        #### function used to actually find the cavity parameters

        self.read_length_pts = np.linspace(self.cfg["read_length_start"], self.cfg["read_length_end"], self.cfg["read_length_points"])
        self.trig_time_pts = np.linspace(self.cfg["trig_time_start"], self.cfg["trig_time_end"], self.cfg["trig_time_points"])

        ####create arrays for storing the data
        X = self.read_length_pts
        print(X)
        X_step = X[1] - X[0]
        Y = self.trig_time_pts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'fid_mat': Z_fid,
                     'read_length_pts': self.read_length_pts,
                     'trig_time_pts':self.trig_time_pts,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (8,5), num = figNum)
        axs = [axs]
        plt.suptitle(self.titlename)


        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        # print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over attenuations
        for idx_trig_time in range(len(self.trig_time_pts)):
            # start_2 = time.time()
            ### set the cavity attenuation
            self.cfg["adc_trig_delays"][0] = self.trig_time_pts[idx_trig_time]
            ### start the loop over transmission points
            for idx_read_length in range(len(self.read_length_pts)):
                self.cfg["readout_lengths"][0] = self.read_length_pts[idx_read_length]

                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_envelopes=True)
                i_g, q_g, i_e, q_e = self._acquireSingleShotData()
                if plt.fignum_exists(10):
                    plt.close(10)

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10, print_fidelities=False)


                Z_fid[idx_trig_time, idx_read_length] = fid
                # self.data['data']['fid_mat'][idx_trig_time, idx_read_length] = fid

                #### plotting
                if idx_trig_time == 0 and idx_read_length ==0:

                    ax_plot_0 = axs[0].imshow(
                        Z_fid*100,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)
                else:
                    ax_plot_0.set_data(Z_fid*100)
                    ax_plot_0.autoscale()
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)


                axs[0].set_ylabel("ADC trigger offset (us)")
                axs[0].set_xlabel("Readout length (us)")
                axs[0].set_title("fidelity")


                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)

                if idx_trig_time == 0 and idx_read_length == 0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * self.cfg["read_length_points"] * self.cfg["trig_time_points"]  ### estimate for full scan
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        plt.savefig(self.iname)  #### save the figure
        plt.show(block=False)
        return self.data


    def _acquireSingleShotData(self):
        #### pull the data from the single hots
        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ig,shots_qg = prog.acquire(self.soc, load_envelopes=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ie,shots_qe = prog.acquire(self.soc, load_envelopes=True)
        # print(prog.__dict__['gen_chs'])
        # gencfg = self.soccfg['gens'][9]
        # print('mixmux gencfg["maxv"]:', gencfg['maxv'])

        i_g = shots_ig[0]
        q_g = shots_qg[0]
        i_e = shots_ie[0]
        q_e = shots_qe[0]

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