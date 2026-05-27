#### this code optimizes readout by driving the qubit and finding optimal single shot seperation

from qick import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.MixedShots_analysis import *

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgram

from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.hist_analysis import *
# from WorkingProjects.Inductive_Coupler.Client_modules.Experiment_Scripts.mSingleShotProgramFF_HigherLevels import * #SingleShotProgramFF_2States, hist
import time
from tqdm.notebook import tqdm



class ReadOpt_wSingleShotFF(ExperimentClass):
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
        X = self.trans_fpts
        print(X)
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)
        print(X)
        print(Y)
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
            self.cfg["pulse_gains"] = [self.gain_pts[idf_cavgain] / 32000]
            self.cfg["pulse_gain"] = int(self.gain_pts[idf_cavgain])

            ### start the loop over transmission points
            for idx_trans in range(len(self.trans_fpts)):
                self.cfg["pulse_freq"] = self.trans_fpts[idx_trans]
                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
                i_g, q_g, i_e, q_e = self._acquireSingleShotData()
                if plt.fignum_exists(10):
                    plt.close(10)

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10, print_fidelities=False)

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
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

        i_g = shots_ig[0][0]
        q_g = shots_qg[0][0]
        i_e = shots_ie[0][0]
        q_e = shots_qe[0][0]

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, print_fidelities=False)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
        
class QubitPulseOpt_wSingleShotFF(ExperimentClass):
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
            self.cfg["qubit_gain"] = int(self.gain_pts[idf_qubitgain])
            ### start the loop over transmission points
            for idx_qubit in range(len(self.qubit_fpts)):
                self.cfg["f_ge"] = self.qubit_fpts[idx_qubit]
                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
                i_g, q_g, i_e, q_e = self._acquireSingleShotData()
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




                axs[0].set_ylabel("Qubit Gain (a.u.)")
                axs[0].set_xlabel("Qubit Frequency (GHz)")
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
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

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
    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

class ReadOpt_wSingleShotFF_Higher(ExperimentClass):
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
            self.cfg["pulse_gains"] = [self.gain_pts[idf_cavgain] / 32000]
            ### start the loop over transmission points
            for idx_trans in range(len(self.trans_fpts)):
                self.cfg["mixer_freq"] = self.trans_fpts[idx_trans]
                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
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
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

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


class ReadOpt_wSingleShotFF_HigherMUXOLD(ExperimentClass):
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
            self.cfg["pulse_gains"] = [self.gain_pts[idf_cavgain] / 32000]
            ### start the loop over transmission points
            for idx_trans in range(len(self.trans_fpts)):
                self.cfg["mixer_freq"] = self.trans_fpts[idx_trans]
                # prog = SingleShotProgram(self.soccfg, self.cfg)
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
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
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

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
                # shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
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
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

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



# class ReadOpt_wSingleShotFF_Higher(ExperimentClass):
#     """
#     This experiment optimizes the cavity readout parameters by driving the qubit and looking at the blobs in single shot
#     It does this in multiple steps to ensure that it continues driving the qubit at the correct point for the optimization
#         - option to perform a calibration for finding the qubit frequency before and during the experiment
#         - starts with a default transmission scan at a known cavity power to find the cavity
#         - with initial cavity frequency find, perform a spec measurement to find the qubit drive frequency, note that
#             you can do the drive on the qubit in either a quasi-spec (long const pulse) or a pi pulse fashion
#         - Once qubit parameters are found, the cavity attenuation and frequency are swept while monitoring the single
#             shot blobs.
#         - after a full frequency sweep for a given cavity attenuation, the user has to option to refind the qubit freq
#             this option is given in the case that drift could be an issue
#
#     """
#
#     def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
#                  calibrate = True, cavityAtten =None):
#         super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)
#
#     def acquire(self, ground = 0, excited = 1, progress=False, plotDisp = True, plotSave = True, calibrate=False, cavityAtten=None, figNum = 1):
#         #### function used to actually find the cavity parameters
#         expt_cfg = {
#             ### define the attenuator parameters
#             "cav_gain_Start": self.cfg["cav_gain_Start"],
#             "cav_gain_Stop": self.cfg["cav_gain_Stop"],
#             "cav_gain_Points": self.cfg["cav_gain_Points"],
#             ### transmission parameters
#             "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
#         }
#         self.gain_pts = np.linspace(expt_cfg["cav_gain_Start"], expt_cfg["cav_gain_Stop"], expt_cfg["cav_gain_Points"])
#         self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
#
#         ####create arrays for storing the data
#         X = self.trans_fpts
#         X_step = X[1] - X[0]
#         Y = self.gain_pts
#         Y_step = Y[1] - Y[0]
#         Z_fid = np.full((len(Y), len(X)), np.nan)
#         Z_overlap = np.full((len(Y), len(X)), np.nan)
#
#         self.data= {
#             'config': self.cfg,
#             'data': {'fid_mat': Z_fid, 'overlap_mat': Z_overlap,
#                      'trans_fpts':self.trans_fpts, 'gain_pts':self.gain_pts,
#                      }
#         }
#
#         ### create the figure and subplots that data will be plotted on
#         while plt.fignum_exists(num = figNum):
#             figNum += 1
#         fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
#         plt.suptitle(self.titlename)
#
#
#         #### start a timer for estimating the time for the scan
#         startTime = datetime.datetime.now()
#         # print('') ### print empty row for spacing
#         print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
#         start = time.time()
#
#         ### start the loop over attenuations
#         for idf_cavgain in range(len(self.gain_pts)):
#             # start_2 = time.time()
#             ### set the cavity attenuation
#             self.cfg["pulse_gain"] = self.gain_pts[idf_cavgain]
#             ### start the loop over transmission points
#             for idx_trans in range(len(self.trans_fpts)):
#                 self.cfg["pulse_freq"] = self.trans_fpts[idx_trans]
#                 # prog = SingleShotProgram(self.soccfg, self.cfg)
#                 # shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
#                 i_g, q_g, i_e, q_e = self._acquireSingleShotData_Higher(ground=ground, excited=excited)
#                 if plt.fignum_exists(10):
#                     plt.close(10)
#
#                 fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10)
#
#                 # plt.show(block=False)
#                 # plt.pause(1)
#                 # plt.close(10)
#
#                 Z_fid[idf_cavgain, idx_trans] = fid
#                 self.data['data']['fid_mat'][idf_cavgain, idx_trans] = fid
#
#                 #### plotting
#                 if idf_cavgain == 0 and idx_trans ==0:
#
#                     ax_plot_0 = axs[0].imshow(
#                         Z_fid*100,
#                         aspect='auto',
#                         extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
#                                 Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
#                         origin='lower',
#                         interpolation='none',
#                     )
#                     cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
#                     cbar0.set_label('fidelity (%)', rotation=90)
#                 else:
#                     ax_plot_0.set_data(Z_fid*100)
#                     ax_plot_0.autoscale()
#                     cbar0.remove()
#                     cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
#                     cbar0.set_label('fidelity (%)', rotation=90)
#
#
#
#
#                 axs[0].set_ylabel("Cavity Gain (a.u.)")
#                 axs[0].set_xlabel("Cavity Frequency (GHz)")
#                 axs[0].set_title("fidelity")
#
#                 #### perform a mixed shot analysis, decide to combine shots or not based on 'arb' or 'const' qubit drive
#
#                 if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
#                     mixed_i = np.concatenate((i_g, i_e))
#                     mixed_q = np.concatenate((q_g, q_e))
#
#                     mixed = MixedShots(mixed_i, mixed_q)
#
#                     overlapErr = mixed.OverlapErr
#
#                     Z_overlap[idf_cavgain, idx_trans] = overlapErr
#                     self.data['data']['overlap_mat'][idf_cavgain, idx_trans] = overlapErr
#
#                     # while plt.fignum_exists(num=5):
#                     #     plt.close(5)
#                     # mixed.PlotGaussFit()
#                 elif self.cfg["qubit_pulse_style"] == "const":
#                     mixed = MixedShots(i_e, q_e)
#
#                     overlapErr = mixed.OverlapErr
#                     Z_overlap[idf_cavgain, idx_trans] = overlapErr
#                     self.data['data']['overlap_mat'][idf_cavgain, idx_trans] = overlapErr
#
#                 #### plotting
#                 if idf_cavgain == 0 and idx_trans ==0:
#                     ax_plot_1 = axs[1].imshow(
#                         Z_overlap,
#                         aspect='auto',
#                         extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
#                                 Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
#                         origin='lower',
#                         interpolation='none',
#                     )
#                     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
#                     cbar1.set_label('overlap err (a.u.)', rotation=90)
#                 else:
#                     ax_plot_1.set_data(Z_overlap)
#                     ax_plot_1.autoscale()
#                     cbar1.remove()
#                     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
#                     cbar1.set_label('overlap err (a.u.)', rotation=90)
#
#
#
#                 axs[1].set_ylabel("Cavity Atten (dB")
#                 axs[1].set_xlabel("Cavity Frequency (GHz)")
#                 axs[1].set_title("overlap err")
#
#                 if plotDisp:
#                     plt.show(block=False)
#                     plt.pause(0.1)
#
#
#                 if idf_cavgain == 0 and idx_trans ==0:  ### during the first run create a time estimate for the data aqcuisition
#                     t_delta = time.time() - start  ### time for single full row in seconds
#                     timeEst = t_delta * expt_cfg["cav_gain_Points"] * expt_cfg["TransNumPoints"]  ### estimate for full scan
#                     StopTime = startTime + datetime.timedelta(seconds=timeEst)
#                     print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
#                     print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
#                     print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))
#
#
#         print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
#         plt.savefig(self.iname)  #### save the figure
#
#         return self.data
#
#     def _acquireSingleShotData(self):
#         #### pull the data from the single hots
#         prog = SingleShotProgram(self.soccfg, self.cfg)
#         shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)
#
#         i_g = shots_i0[0]
#         q_g = shots_q0[0]
#         i_e = shots_i0[1]
#         q_e = shots_q0[1]
#
#         ### use the helper histogram to find the fidelity and such
#         fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)
#
#         self.fid = fid
#         self.threshold = threshold
#         self.angle = angle
#
#         return i_g, q_g, i_e, q_e
#
#     def _acquireSingleShotData_Higher(self, ground = 0, excited = 1):
#         #### pull the data from the single hots
#         self.cfg["pulse_expt"] = {}
#         prog = SingleShotProgramFF_2StatesMUX(soc = self.soc, soccfg=self.soccfg, cfg=self.cfg)#cfg=config,soc=soc,soccfg=soccfg
#         data = prog.acquire(ground_pulse=ground, excited_pulse=excited)
#
#         # prog.display(data = data)
#
#         i_g = data['I0']
#         q_g = data['Q0']
#         i_e = data['I1']
#         q_e = data['Q1']
#
#         ### use the helper histogram to find the fidelity and such
#         fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)
#
#         self.fid = fid
#         self.threshold = threshold
#         self.angle = angle
#
#         return i_g, q_g, i_e, q_e
#
#
#     def save_data(self, data=None):
#         ##### save the data to a .h5 file
#         print(f'Saving {self.fname}')
#         super().save_data(data=data['data'])





# class QubitPulseOpt_wSingleShotFF_Higher(ExperimentClass):
#     """
#     This experiment optimizes the cavity readout parameters by driving the qubit and looking at the blobs in single shot
#     It does this in multiple steps to ensure that it continues driving the qubit at the correct point for the optimization
#         - option to perform a calibration for finding the qubit frequency before and during the experiment
#         - starts with a default transmission scan at a known cavity power to find the cavity
#         - with initial cavity frequency find, perform a spec measurement to find the qubit drive frequency, note that
#             you can do the drive on the qubit in either a quasi-spec (long const pulse) or a pi pulse fashion
#         - Once qubit parameters are found, the cavity attenuation and frequency are swept while monitoring the single
#             shot blobs.
#         - after a full frequency sweep for a given cavity attenuation, the user has to option to refind the qubit freq
#             this option is given in the case that drift could be an issue
#
#     """
#
#     def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
#                  calibrate = True, cavityAtten =None):
#         super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)
#
#     def acquire(self, ground = 0, excited = 1, progress=False, plotDisp = True, plotSave = True, calibrate=False, figNum = 1):
#         #### function used to actually find the cavity parameters
#         expt_cfg = {
#             ### define the attenuator parameters
#             "qubit_gain_Start": self.cfg["qubit_gain_Start"],
#             "qubit_gain_Stop": self.cfg["qubit_gain_Stop"],
#             "qubit_gain_Points": self.cfg["qubit_gain_Points"],
#             ### transmission parameters
#             "qubit_freq_start": self.cfg["qubit_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "qubit_freq_stop": self.cfg["qubit_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "QubitNumPoints": self.cfg["QubitNumPoints"],  ### number of points in the transmission frequecny
#         }
#         self.gain_pts = np.linspace(expt_cfg["qubit_gain_Start"], expt_cfg["qubit_gain_Stop"], expt_cfg["qubit_gain_Points"])
#         self.qubit_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["QubitNumPoints"])
#
#         ####create arrays for storing the data
#         X = self.qubit_fpts
#         X_step = X[1] - X[0]
#         Y = self.gain_pts
#         Y_step = Y[1] - Y[0]
#         Z_fid = np.full((len(Y), len(X)), np.nan)
#         Z_overlap = np.full((len(Y), len(X)), np.nan)
#
#         self.data= {
#             'config': self.cfg,
#             'data': {'fid_mat': Z_fid, 'overlap_mat': Z_overlap,
#                      'qubit_fpts':self.qubit_fpts, 'gain_pts':self.gain_pts,
#                      }
#         }
#
#         ### create the figure and subplots that data will be plotted on
#         while plt.fignum_exists(num = figNum):
#             figNum += 1
#         fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
#         plt.suptitle(self.titlename)
#
#
#         #### start a timer for estimating the time for the scan
#         startTime = datetime.datetime.now()
#         # print('') ### print empty row for spacing
#         print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
#         start = time.time()
#
#         ### start the loop over attenuations
#         for idf_qubitgain in range(len(self.gain_pts)):
#             # start_2 = time.time()
#             ### set the cavity attenuation
#             self.cfg["qubit_gain"] = self.gain_pts[idf_qubitgain]
#             if excited == 2:
#                 self.cfg["qubit_gain12"] = self.gain_pts[idf_qubitgain]
#             else:
#                 self.cfg["qubit_gain01"] = self.gain_pts[idf_qubitgain]
#             ### start the loop over transmission points
#             for idx_qubit in range(len(self.qubit_fpts)):
#                 if excited == 2:
#                     self.cfg["qubit_freq12"] = self.qubit_fpts[idx_qubit]
#                 else:
#                     self.cfg["qubit_freq01"] = self.qubit_fpts[idx_qubit]
#                 print(self.cfg["qubit_gain01"], self.cfg["qubit_gain12"], self.cfg["qubit_freq01"], self.cfg["qubit_freq12"])
#                 # prog = SingleShotProgram(self.soccfg, self.cfg)
#                 # shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
#                 i_g, q_g, i_e, q_e = self._acquireSingleShotData_Higher(ground = ground, excited = excited)
#                 if plt.fignum_exists(10):
#                     plt.close(10)
#
#                 fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10)
#
#                 # plt.show(block=False)
#                 # plt.pause(1)
#                 # plt.close(10)
#
#                 Z_fid[idf_qubitgain, idx_qubit] = fid
#                 self.data['data']['fid_mat'][idf_qubitgain, idx_qubit] = fid
#
#                 #### plotting
#                 if idf_qubitgain == 0 and idx_qubit ==0:
#
#                     ax_plot_0 = axs[0].imshow(
#                         Z_fid*100,
#                         aspect='auto',
#                         extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
#                                 Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
#                         origin='lower',
#                         interpolation='none',
#                     )
#                     cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
#                     cbar0.set_label('fidelity (%)', rotation=90)
#                 else:
#                     ax_plot_0.set_data(Z_fid*100)
#                     ax_plot_0.autoscale()
#                     cbar0.remove()
#                     cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
#                     cbar0.set_label('fidelity (%)', rotation=90)
#
#
#
#
#                 axs[0].set_ylabel("Cavity Atten (dB")
#                 axs[0].set_xlabel("Cavity Frequency (GHz)")
#                 axs[0].set_title("fidelity")
#
#                 #### perform a mixed shot analysis, decide to combine shots or not based on 'arb' or 'const' qubit drive
#
#                 if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
#                     mixed_i = np.concatenate((i_g, i_e))
#                     mixed_q = np.concatenate((q_g, q_e))
#
#                     mixed = MixedShots(mixed_i, mixed_q)
#
#                     overlapErr = mixed.OverlapErr
#
#                     Z_overlap[idf_qubitgain, idx_qubit] = overlapErr
#                     self.data['data']['overlap_mat'][idf_qubitgain, idx_qubit] = overlapErr
#
#                     # while plt.fignum_exists(num=5):
#                     #     plt.close(5)
#                     # mixed.PlotGaussFit()
#                 elif self.cfg["qubit_pulse_style"] == "const":
#                     mixed = MixedShots(i_e, q_e)
#
#                     overlapErr = mixed.OverlapErr
#                     Z_overlap[idf_qubitgain, idx_qubit] = overlapErr
#                     self.data['data']['overlap_mat'][idf_qubitgain, idx_qubit] = overlapErr
#
#                 #### plotting
#                 if idf_qubitgain == 0 and idx_qubit ==0:
#                     ax_plot_1 = axs[1].imshow(
#                         Z_overlap,
#                         aspect='auto',
#                         extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
#                                 Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
#                         origin='lower',
#                         interpolation='none',
#                     )
#                     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
#                     cbar1.set_label('overlap err (a.u.)', rotation=90)
#                 else:
#                     ax_plot_1.set_data(Z_overlap)
#                     ax_plot_1.autoscale()
#                     cbar1.remove()
#                     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
#                     cbar1.set_label('overlap err (a.u.)', rotation=90)
#
#
#
#                 axs[1].set_ylabel("Qubit Gain (a.u.)")
#                 axs[1].set_xlabel("Qubit Frequency (GHz)")
#                 axs[1].set_title("overlap err")
#
#                 if plotDisp:
#                     plt.show(block=False)
#                     plt.pause(0.1)
#
#
#                 if idf_qubitgain == 0 and idx_qubit ==0:  ### during the first run create a time estimate for the data aqcuisition
#                     t_delta = time.time() - start  ### time for single full row in seconds
#                     timeEst = t_delta * expt_cfg["qubit_gain_Points"] * expt_cfg["QubitNumPoints"]  ### estimate for full scan
#                     StopTime = startTime + datetime.timedelta(seconds=timeEst)
#                     print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
#                     print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
#                     print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))
#
#
#         print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
#
#         plt.savefig(self.iname)  #### save the figure
#
#         return self.data
#
#
#     def _calibrate(self, progress=False, plotDisp = True, plotSave = True, figNum = 1, cavityAtten = None):
#         #### create a calibration function that is used to find the qubit frequency
#         expt_cfg = {
#             ### transmission parameters
#             "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
#             ### spec parameters
#             "qubit_freq_start": self.cfg["qubit_freq_start"],
#             "qubit_freq_stop": self.cfg["qubit_freq_stop"],
#             "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
#         }
#
#         ### define the yoko vector for the voltages, note this assumes that yoko1 already exists
#         cavityAtten.SetAttenuation(self.cfg["cav_Atten"])
#
#
#         ### create the figure and subplots that data will be plotted on
#         while plt.fignum_exists(num = figNum):
#             figNum += 1
#         fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
#
#         ### create the frequency arrays for both transmission and spec and attenuation arrays
#         ### also create empty array to fill with transmission and spec data
#         self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
#         self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
#         X_trans = (self.trans_fpts + self.cfg["cavity_LO"]/1e6) /1e3
#         X_spec = self.spec_fpts/1e3
#
#         #### aquire the transmission data
#         data_I, data_Q = self._acquireTransData()
#         sig = data_I + 1j * data_Q
#         avgamp0 = np.abs(sig)
#
#         axs[0].plot(X_trans, avgamp0, label="trans")
#         axs[0].set_ylabel("a.u.")
#         axs[0].set_xlabel("Cavity Frequency (GHz)")
#         axs[0].set_title("Cavity Transmission, Averages = " + str(self.cfg["reps"]))
#
#         #### aquire the spec data
#         data_I, data_Q = self._acquireSpecData()
#         sig = data_I + 1j * data_Q
#         avgamp0 = np.abs(sig)
#
#         axs[1].plot(X_spec, avgamp0, label="spec")
#         axs[1].set_ylabel("a.u.")
#         axs[1].set_xlabel("Qubit Frequency (GHz)")
#         axs[1].set_title("Qubit Spec, Averages = " + str(self.cfg["reps"]))
#
#
#
#     def _acquireTransData(self):
#         ##### code to aquire just the cavity transmission data
#         expt_cfg = {
#             ### transmission parameters
#             "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
#             "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
#         }
#         ### take the transmission data
#         self.cfg["reps"] = self.cfg["trans_reps"]
#         fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
#         results = []
#         start = time.time()
#         for f in tqdm(fpts, position=0, disable=True):
#             self.cfg["pulse_freq"] = f
#             prog = SingleToneSpectroscopyProgramFF(self.soccfg, self.cfg)
#             results.append(prog.acquire(self.soc, load_pulses=True))
#         results = np.transpose(results)
#         #### pull out I and Q data
#         data_I = results[0][0][0]
#         data_Q = results[0][0][1]
#
#         #### find the frequency corresponding to the cavity peak and set as cavity transmission number
#         sig = data_I + 1j * data_Q
#         avgamp0 = np.abs(sig)
#         peak_loc = np.argmax(avgamp0)
#         self.cfg["pulse_freq"] = self.trans_fpts[peak_loc]
#
#         return data_I, data_Q
#
#     def _acquireSpecData(self):
#         ##### code to aquire just the qubit spec data
#         expt_cfg = {
#             ### spec parameters
#             "qubit_freq_start": self.cfg["qubit_freq_start"],
#             "qubit_freq_stop": self.cfg["qubit_freq_stop"],
#             "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
#         }
#         ### take the transmission data
#         self.cfg["reps"] = self.cfg["spec_reps"]
#         fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
#         results = []
#         start = time.time()
#         for f in tqdm(fpts, position=0, disable=True):
#             self.cfg["qubit_freq"] = f
#             prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
#             results.append(prog.acquire(self.soc, load_pulses=True))
#         results = np.transpose(results)
#         #### pull out I and Q data
#         data_I = results[0][0][0]
#         data_Q = results[0][0][1]
#
#         #### find the frequency corresponding to the qubit dip
#         sig = data_I + 1j * data_Q
#         avgamp0 = np.abs(sig)
#         peak_loc = np.argmin(avgamp0)
#         self.qubitFreq = self.spec_fpts[peak_loc]
#         self.cfg["qubit_freq"] = self.qubitFreq
#
#         return data_I, data_Q
#
#     def _acquireSingleShotData(self):
#         #### pull the data from the single hots
#         prog = SingleShotProgram(self.soccfg, self.cfg)
#         shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)
#
#         i_g = shots_i0[0]
#         q_g = shots_q0[0]
#         i_e = shots_i0[1]
#         q_e = shots_q0[1]
#
#         ### use the helper histogram to find the fidelity and such
#         fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)
#
#         self.fid = fid
#         self.threshold = threshold
#         self.angle = angle
#
#         return i_g, q_g, i_e, q_e
#
#     def _acquireSingleShotData_Higher(self, ground = 0, excited = 1):
#         #### pull the data from the single hots
#         self.cfg["pulse_expt"] = {}
#         prog = SingleShotProgramFF_2States(soc = self.soc, soccfg=self.soccfg, cfg=self.cfg)#cfg=config,soc=soc,soccfg=soccfg
#         data = prog.acquire(ground_pulse=ground, excited_pulse=excited)
#
#         # prog.display(data = data)
#
#         i_g = data['I0']
#         q_g = data['Q0']
#         i_e = data['I1']
#         q_e = data['Q1']
#
#         ### use the helper histogram to find the fidelity and such
#         fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)
#
#         self.fid = fid
#         self.threshold = threshold
#         self.angle = angle
#
#         return i_g, q_g, i_e, q_e
#
#     def save_data(self, data=None):
#         ##### save the data to a .h5 file
#         print(f'Saving {self.fname}')
#         super().save_data(data=data['data'])