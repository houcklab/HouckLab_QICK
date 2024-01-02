from qick import *
import matplotlib.pyplot as plt
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import datetime
import time
from WorkingProjects.Inductive_Coupler.Client_modules.PythonDrivers.YOKOGS200 import *
from scipy.signal import savgol_filter
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFProg

# ====================================================== #

class LoopbackProgramSpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],  # gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch=self.cfg["res_ch"]))
                # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
        # Sara: add gen_ch specification for us2cycles conversion for length/sigma of qubit pulse
        # self.qubit_length = self.us2cycles(cfg["sigma"] * 2, gen_ch=qubit_ch)
        # self.qubit_length = self.us2cycles(cfg["qubit_length"])
        # self.sigma = self.us2cycles(cfg["sigma"], gen_ch=qubit_ch)

        FF.FFDefinitions(self)

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        self.delay = self.cfg["delay_time"] #Delay times are in clock cycles

        self.qubit_length_us = cfg["sigma"] * 3
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(self.qubit_length_us, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                 waveform="qubit")
        print(cfg["mixer_freq"], cfg["pulse_freqs"], cfg["pulse_gains"], cfg["length"], self.cfg["adc_trig_offset"])
    def body(self):
        print(self.FFRamp, self.FFExpts, self.FFReadouts, self.delay)
        self.sync_all(50, dac_t0=self.dac_t0)
        self.FFPulses(self.FFRamp, 2.02)
        self.FFPulses(self.FFExpts, 6)
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(2.0) + self.delay)  # play probe pulse
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFExpts, 2.05)
        self.FFPulses(-1 * self.FFExpts, 2)
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)

    # def body(self):
    #     print(self.delay, self.cfg["sigma"], self.pulse_qubit_lenth)
    #     print(self.FFRamp, self.FFExpts, self.FFReadouts)
    #     self.sync_all(50, dac_t0=self.dac_t0)
    #     self.FFPulses(self.FFExpts, 2)
    #     # self.FFPulses(self.FFRamp, self.qubit_length_us,
    #     #               t_start=self.us2cycles(2))  # Sara: Length specified in us in FFPulses argument; add 20 ns
    #     # self.pulse(ch=self.cfg["qubit_ch"], t=self.delay)  # probe pulse at 2 us + delay FIXME CLOCK
    #     # self.FFPulses(self.FFExpts, self.qubit_length_us + 0.05)
    #     # self.FFPulses_direct(1 * self.FFExpts, self.pulse_qubit_lenth * 16 + self.delay * 16  # FIXME CLOCK
    #     #                         + 200 * 16, self.FFRamp,
    #     #                      IQPulseArray = self.cfg["IDataArray"], waveform_label='FF2')
    #     # # self.FFPulses(self.FFPulse, self.qubit_length_us + 0.3)
    #     # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.26) + self.delay)  # play probe pulse
    #     self.FFPulses(self.FFExpts, self.qubit_length_us + self.delay + 0.3)
    #
    #     # self.FFPulses_direct(1 * self.FFExpts, self.pulse_qubit_lenth * 16 + self.delay * 16  # FIXME CLOCK
    #     #                         + 200 * 16, self.FFRamp,
    #     #                      IQPulseArray = self.cfg["IDataArray"], waveform_label='FF2', t_start= self.us2cycles(0.05))
    #     # self.FFPulses(self.FFPulse, self.qubit_length_us + 0.3)
    #     self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(2.02) + self.delay)  # play probe pulse
    #
    #     # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
    #     # trigger measurement, play measurement pulse, wait for qubit to relax
    #     print(self.FFRamp, self.FFExpts)
    #     self.sync_all(dac_t0=self.dac_t0)
    #     self.FFPulses(self.FFReadouts, self.cfg["length"])
    #     self.measure(pulse_ch=self.cfg["res_ch"],
    #                  adcs=self.cfg["ro_chs"], pins=[0],
    #                  adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
    #                  wait=False,
    #                  syncdelay=self.us2cycles(10))
    #     self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
    #     # self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 0.3)
    #     self.FFPulses_direct(-1 * self.FFExpts, self.pulse_qubit_lenth * 16 + self.delay * 16  # FIXME CLOCK
    #                             + 200 * 16, self.FFRamp,
    #                          IQPulseArray = self.cfg["IDataArray"], waveform_label='FF3')
    #     self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)

    def FFPulses(self, list_of_gains, length_us, t_start = 'auto', IQPulseArray = None, waveform_label = "FF"):
        FF.FFPulses(self, list_of_gains, length_us, t_start, IQPulseArray, waveform_label)
    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None, waveform_label='FF'):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains = previous_gains, t_start=t_start,
                           IQPulseArray=IQPulseArray, waveform_label=waveform_label)
    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


# ====================================================== #


class FFSpecCalibrationMUX(ExperimentClass):
    """
    Spec experiment that finds the qubit frequency during and after a fast-flux pulse
    Notes:
        - this is set up such that it plots out the rows of data as it sweeps through delay times
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=False):
        """
        :param soc: instance of RFSOC
        :param soccfg: rfsoc configuration
        :param path: path to save data; outerFolder + path is the full pathname
        :param outerFolder: path to save data; outerfolder + path is the full pathname
        :param prefix: filename prefix identifier
        :param cfg: configuration dictionary
        :param config_file: parameters for config file specified are loaded into the class dict
                            (name relative to expt_directory if no leading /)
                            Default = None looks for path/prefix.json
        :param progress: bool, show progress bars
        """
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, plotDisp=True, plotSave=True, figNum=1, i_data=False, q_data=False):
        """
        Wait variable time (delay) then measure qubit frequency via two-tone
        :param plotDisp: bool, if True: plots data while it comes in
        :param plotSave: bool, if True: saves plot
        :param figNum: int, figure number to use. If in use, will use next available integer
        :param i_data: bool, if True: use I quadrature of acquired data
        :param q_data: bool, if True (and i_data is False): use Q quadrature of acquired data. if both false, use amp
        :return:
        """
        expt_cfg = {
            # transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  # number of points in the transmission frequecny
            # spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  # number of points
        }

        delay_pts = self.cfg["delayStart"] + self.cfg["delayStep"] * np.arange(self.cfg["DelayPoints"])

        # create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 1, figsize=(10, 7), num=figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        # create the frequency arrays for both transmission and spec
        self.trans_fpts = np.linspace(self.cfg["mixer_freq"] - self.cfg["TransSpan"],
                           self.cfg["mixer_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])

        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                     expt_cfg["SpecNumPoints"])
        X_trans = (self.trans_fpts + self.cfg["cavity_LO"] / 1e6 + self.cfg['pulse_freqs'][0]) / 1e3  # trans_fpts in MHz, cavity_LO in Hz
        X_trans_step = X_trans[1] - X_trans[0]
        X_spec = self.spec_fpts / 1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y = delay_pts
        Y_step = Y[1] - Y[0]
        Z_trans = np.full((self.cfg["DelayPoints"], self.cfg["TransNumPoints"]), np.nan)
        Z_spec = np.full((self.cfg["DelayPoints"], self.cfg["SpecNumPoints"]), np.nan)

        # create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_Imat = np.zeros((self.cfg["DelayPoints"], self.cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((self.cfg["DelayPoints"], self.cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((self.cfg["DelayPoints"], self.cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((self.cfg["DelayPoints"], self.cfg["SpecNumPoints"]))
        self.data = {
            'config': self.cfg,
            'data': {'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts': self.trans_fpts,
                     'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                     'delay_pts': delay_pts,
                     }
        }
        # start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('\nstarting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        # loop over the DelayPoints vector
        for i in tqdm(range(self.cfg["DelayPoints"]), position=0, leave=True):
            if i != 0 and i % 5 == 1:
                self.save_data(self.data)
            self.cfg["delay_time"] = delay_pts[i]
            # print('delay_time: ', self.cfg["delay_time"])
            # tqdm.set_postfix_str("delay time: {}".format(self.cfg['delay_time']))
            # take the transmission data. only need once because qubit frequency at readout invariant
            # if i == 0:
            #     data_I_trans, data_Q_trans = self._acquireTransData()
            #     sig = data_I_trans + 1j * data_Q_trans
            #     avgamp0_trans = np.abs(sig)
            #
            #     self.data['data']['trans_Imat'][i, :] = data_I_trans
            #     self.data['data']['trans_Qmat'][i, :] = data_Q_trans
            #
            #     Z_trans[i, :] = avgamp0_trans
            #
            #     axs[0].plot(X_trans, avgamp0_trans, label="Amplitude; ADC 0")
            #     axs[0].set_xlabel("Cavity Frequency (GHz)")
            #     axs[0].set_title("Cavity Transmission")
            #     self.cfg["mixer_freq"] -= self.cfg["TransSpan"]
            #
            # if plotDisp:
            #     plt.show(block=False)
            #     plt.pause(0.1)
            if i == 0:
                start = time.time()


            # take the spec data
            data_I, data_Q = self._acquireSpecData()

            self.data['data']['spec_Imat'][i, :] = data_I
            self.data['data']['spec_Qmat'][i, :] = data_Q

            # plot out the spec data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig)
            Z_spec[i, :] = avgamp0  # - self.cfg["minADC"]
            if i == 0:
                rangeQ = np.max(data_Q) - np.min(data_Q)
                rangeI = np.max(data_I) - np.min(data_I)
                if rangeQ > rangeI:
                    q_data = True
                    i_data = False
                    # Z_spec[i, :] = (data_I - np.max(data_I)) / (np.max(data_I) - np.min(data_I))#- self.cfg["minADC"]
                else:
                    q_data = False
                    i_data = True
                    # Z_spec[i, :] = (data_Q - np.max(data_Q)) / (np.max(data_Q) - np.min(data_Q))#- self.cfg["minADC"]
            if i_data:
                Z_spec[i, :] = data_I
            elif q_data:
                Z_spec[i, :] = data_Q
            else:
                Z_spec[i, :] = avgamp0  # - self.cfg["minADC"]

            # print('zspec', Z_spec)
            ax_plot_1 = axs.imshow(
                Z_spec,
                aspect='auto',
                extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                        np.max(Y) + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            if i == 0:  # if first sweep add a colorbar
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs.set_ylabel("Delay Time (clock cycles (2.35 ns))")
            axs.set_xlabel("Spec Frequency (GHz)")
            axs.set_title("Qubit Spec")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i == 0:  # during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  # time for single full row in seconds
                timeEst = 2 * (t_delta) * self.cfg["DelayPoints"]  # estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname)  # save the figure

        if not plotDisp:
            fig.clf(True)
            plt.close(fig)

        return self.data

    def _acquireTransData(self):
        # code to acquire just the cavity transmission data
        # take the transmission data
        self.cfg["reps"] = self.cfg["trans_reps"]
        self.cfg['rounds'] = 1
        fpts = np.linspace(self.cfg["mixer_freq"] - self.cfg["TransSpan"],
                           self.cfg["mixer_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        for f in fpts:
            self.cfg["mixer_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)
        # pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]
        #
        # # find the frequency corresponding to the cavity peak and set as cavity transmission number
        # sig = data_I + 1j * data_Q
        # avgamp0 = np.abs(sig)
        # filtered_amp = savgol_filter(avgamp0, 5, 2)
        # if self.cfg["cavity_min"]:
        #     peak_loc = np.argmin(filtered_amp)
        # else:
        #     peak_loc = np.argmax(filtered_amp)
        #
        # self.cfg["mixer_freq"] = self.trans_fpts[peak_loc]
        # self.cfg['minADC'] = avgamp0[peak_loc]

        # print(self.cfg["pulse_freq"])

        return data_I, data_Q

    def _acquireSpecData(self):
        """
        code to acquire just the cavity transmission data
        """
        # take the transmission data
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["rounds"] = self.cfg["spec_rounds"]

        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=self.progress, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}

        data_I = data['data']['avgi'][0][0]
        data_Q = data['data']['avgq'][0][0]

        return data_I, data_Q

    def save_data(self, data=None):
        # save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
