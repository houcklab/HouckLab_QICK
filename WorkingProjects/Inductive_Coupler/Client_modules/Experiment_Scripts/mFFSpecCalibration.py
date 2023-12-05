from qick import *
import matplotlib.pyplot as plt
from q4diamond.Client_modules.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import datetime
import time
from q4diamond.Client_modules.PythonDrivers.YOKOGS200 import *
from scipy.signal import savgol_filter
import q4diamond.Client_modules.Helpers.FF_utils as FF
from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFFProg

# ====================================================== #

class LoopbackProgramSpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        for ro_ch in cfg["ro_chs"]:
            # Sara: add ro_ch specification for us2cycles conversion for length of readout pulse
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
                                 length=self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch), gen_ch=cfg["res_ch"])
        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
        # Sara: add gen_ch specification for us2cycles conversion for length/sigma of qubit pulse
        self.qubit_length = self.us2cycles(cfg["sigma"] * 2, gen_ch=qubit_ch)
        # self.qubit_length = self.us2cycles(cfg["qubit_length"])
        self.sigma = self.us2cycles(cfg["sigma"], gen_ch=qubit_ch)

        FF.FFDefinitions(self)

        read_freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        self.delay = self.cfg["delay_time"] #Delay times are in clock cycles

        # print(self.qubit_length, self.sigma)
        # print("delay time", self.us2cycles(self.delay))
        # print("delay time (cycles)", self.delay)  # FIXME CLOCK

        # add qubit and readout pulses to respective channels
        # self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.sigma, length=self.qubit_length)
        gencfg = self.soccfg['gens'][cfg["qubit_ch"]]
        # idata = np.concatenate([np.ones(self.qubit_length * 16), np.zeros(16)])
        # qdata = np.zeros((self.qubit_length + 1) * 16)

        # idata = np.ones(self.qubit_length * 16)
        # idata = idata * gencfg['maxv'] * gencfg['maxv_scale']
        # qdata = np.zeros((self.qubit_length) * 16)
        #
        # self.add_pulse(ch=cfg["qubit_ch"], name='qubit',
        #                idata=idata, qdata=qdata)
        # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
        #                          phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
        #                          waveform="qubit")
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                 waveform="qubit")
        self.qubit_length_us = cfg["sigma"] * 4
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=read_freq, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch=res_ch))

    def body(self):
        print(self.delay, self.cfg["sigma"], self.pulse_qubit_lenth)
        self.sync_all(dac_t0=self.dac_t0)
        # self.FFPulses(self.FFRamp, 2)
        self.pulse(ch=self.cfg["qubit_ch"], t=self.delay)  # probe pulse at 2 us + delay FIXME CLOCK
        # self.FFPulses(self.FFRamp, self.qubit_length_us,
        #               t_start=self.us2cycles(2))  # Sara: Length specified in us in FFPulses argument; add 20 ns
        # self.FFPulses(self.FFExpts, 4 * self.cfg["sigma"] + self.cycles2us(self.delay)  # FIXME CLOCK
        #                         + 0.5, IQPulseArray=self.cfg["IDataArray"])
        self.FFPulses_direct(self.FFExpts, self.pulse_qubit_lenth * 16 + self.delay * 16  # FIXME CLOCK
                                + 200 * 16, self.FFRamp,
                             IQPulseArray = self.cfg["IDataArray"])
        # self.FFPulses(self.FFExpts, self.qubit_length_us + 1)
        # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        print(self.FFRamp, self.FFExpts)
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        # self.FFPulses(-1 * self.FFExpts, self.qubit_length_us + 0.1)
        self.FFPulses_direct(-1 * self.FFExpts, self.pulse_qubit_lenth * 16 + self.delay * 16  # FIXME CLOCK
                                + 200 * 16, self.FFRamp,
                             IQPulseArray = self.cfg["IDataArray"], waveform_label='FF2')
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)

    # def bodyOLD(self):
    #     print(self.delay)
    #     self.sync_all(self.us2cycles(0.05), dac_t0=self.dac_t0)  # align channels and wait 50ns
    #     self.FFPulses(self.FFRamp, 2)
    #     self.pulse(ch=self.cfg["qubit_ch"], t=self.delay + self.us2cycles(2))  # probe pulse at 2 us + delay FIXME CLOCK
    #     self.FFPulses(self.FFRamp, self.qubit_length_us,
    #                   t_start=self.us2cycles(2))  # Sara: Length specified in us in FFPulses argument; add 20 ns
    #
    #     # self.FFPulses_Optimized(self.FFExpts, 2 * self.cfg["sigma"] + self.delay
    #     #                         + 0.5, idata_pulse=True, IQPulseArray=self.cfg['IQPulseArray'])
    #     self.FFPulses(self.FFExpts, 2 * self.cfg["sigma"] + self.cycles2us(self.delay)  # FIXME CLOCK
    #                             + 0.5, IQPulseArray=self.cfg['IQPulseArray'])   # compensated step fn
    #     # self.FFPulses(self.FFExpts, 2 * self.cfg["sigma"] + self.delay
    #     #               + 0.5, idata_pulse=True, t_start=self.us2cycles(2 + 0.02))
    #
    #     # self.FFPulses_Optimized(self.FFExpts , 0.5, idata_pulse=True, IQPulseArray = self.cfg['IQPulseArray'])
    #     self.sync_all(dac_t0=self.dac_t0)  # reset t=0 to latest time
    #     self.FFPulses(self.FFReadouts, self.cfg["length"])
    #     self.measure(pulse_ch=self.cfg["res_ch"],
    #                  adcs=[0],
    #                  adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
    #                  wait=True,
    #                  syncdelay=self.us2cycles(10))
    #
    #     self.FFPulses(-1 * self.FFRamp, 2)  # Sara: Length specified in us in FFPulses argument; net 0-flux step
    #     self.FFPulses(-1 * self.FFRamp, 0.02)  # Sara: Length specified in us in FFPulses argument; net 0-flux step
    #     self.FFPulses(-1 * self.FFExpts, 2 * self.cfg["sigma"] + self.cycles2us(self.delay)  # FIXME CLOCK
    #                             + 0.5, waveform_label='FF2',
    #                             IQPulseArray=self.cfg['IQPulseArray'])  # net 0-flux step
    #     self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
    #
    #     self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)

    def FFPulses(self, list_of_gains, length_us, t_start = 'auto', IQPulseArray = None, waveform_label = "FF"):
        FF.FFPulses(self, list_of_gains, length_us, t_start, IQPulseArray, waveform_label)
    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None, waveform_label='FF'):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains = previous_gains, t_start=t_start,
                           IQPulseArray=IQPulseArray, waveform_label=waveform_label)

    # def FFPulses_Optimized(self, list_of_gains, length_us, t_start=None, idata_pulse=False,
    #                        IQPulseArray=[None, None, None, None], waveform_label="FF"):
    #     for i, gain in enumerate(list_of_gains):
    #         # Sara edited to correctly convert to cycles using the correct gen_ch
    #         length = self.us2cycles(length_us, gen_ch=self.FFChannels[i])
    #         gencfg = self.soccfg['gens'][self.FFChannels[i]]
    #         if not idata_pulse:
    #             self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
    #                                      gain=gain,
    #                                      length=length)
    #         if idata_pulse and IQPulseArray[i] is None:
    #             print('Using "arbitrary" array of ones')
    #             idata = np.ones(length * 16)
    #             idata = idata * gencfg['maxv'] * gencfg['maxv_scale']
    #             qdata = np.zeros(length * 16)
    #
    #             self.add_pulse(ch=self.FFChannels[i], name=waveform_label,
    #                            idata=idata, qdata=qdata)
    #             self.set_pulse_registers(ch=self.FFChannels[i], freq=0, style='arb',
    #                                      phase=0, gain=int(gain), waveform=waveform_label, outsel="input")
    #         if idata_pulse and IQPulseArray[i] is not None:
    #             print('Using IQPulseArray')
    #             if length > len(IQPulseArray[i]):
    #                 additional_array = np.ones(length - len(IQPulseArray[i]))
    #             else:
    #                 additional_array = np.array([])
    #             # print(np.array(IQPulseArray[i][:length]), additional_array)
    #             idata = np.concatenate([np.array(IQPulseArray[i][:length]), additional_array])  # ensures
    #             # print(idata)
    #             maximum_value = np.max(np.abs(idata))
    #             if maximum_value < 1:
    #                 maximum_value = 1
    #             idata = idata.repeat(16)
    #             idata = (idata * gencfg['maxv'] * gencfg['maxv_scale']) / maximum_value
    #             idata[idata > gencfg['maxv'] * gencfg['maxv_scale']] = gencfg['maxv'] * gencfg['maxv_scale']
    #             qdata = np.zeros(length * 16) * gencfg['maxv']
    #
    #             # print(max(idata), max(qdata), maximum_value)
    #
    #             # print(idata[:20], len(idata), maximum_value, gencfg['maxv'] * gencfg['maxv_scale'])
    #             self.add_pulse(ch=self.FFChannels[i], name=waveform_label,
    #                            idata=idata, qdata=qdata)
    #             self.set_pulse_registers(ch=self.FFChannels[i], freq=0, style='arb',
    #                                      phase=0, gain=int(gain * maximum_value),
    #                                      waveform=waveform_label, outsel="input")
    #     if t_start is None:
    #         self.pulse(ch=self.FF_Channel1)
    #         self.pulse(ch=self.FF_Channel2)
    #         self.pulse(ch=self.FF_Channel3)
    #         self.pulse(ch=self.FF_Channel4)
    #     else:
    #         self.pulse(ch=self.FF_Channel1, t=t_start)
    #         self.pulse(ch=self.FF_Channel2, t=t_start)
    #         self.pulse(ch=self.FF_Channel3, t=t_start)
    #         self.pulse(ch=self.FF_Channel4, t=t_start)

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


# ====================================================== #


class FFSpecCalibration(ExperimentClass):
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
        fig, axs = plt.subplots(2, 1, figsize=(8, 10), num=figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        # create the frequency arrays for both transmission and spec
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"],
                                      expt_cfg["TransNumPoints"])
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                     expt_cfg["SpecNumPoints"])
        X_trans = (self.trans_fpts + self.cfg["cavity_LO"] / 1e6) / 1e3  # trans_fpts in MHz, cavity_LO in Hz
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
            if i == 0:
                data_I_trans, data_Q_trans = self._acquireTransData()
                sig = data_I_trans + 1j * data_Q_trans
                avgamp0_trans = np.abs(sig)

                self.data['data']['trans_Imat'][i, :] = data_I_trans
                self.data['data']['trans_Qmat'][i, :] = data_Q_trans

                Z_trans[i, :] = avgamp0_trans

                axs[0].plot(X_trans, avgamp0_trans, label="Amplitude; ADC 0")
                axs[0].set_xlabel("Cavity Frequency (GHz)")
                axs[0].set_title("Cavity Transmission")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
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
            # rangeQ = np.max(data_Q) - np.min(data_Q)
            # rangeI = np.max(data_I) - np.min(data_I)
            # if rangeQ > rangeI:
            #     Z_spec[i, :] = (data_I - np.max(data_I)) / (np.max(data_I) - np.min(data_I))#- self.cfg["minADC"]
            # else:
            #     Z_spec[i, :] = (data_Q - np.max(data_Q)) / (np.max(data_Q) - np.min(data_Q))#- self.cfg["minADC"]
            if i_data:
                Z_spec[i, :] = data_I
            elif q_data:
                Z_spec[i, :] = data_Q
            else:
                Z_spec[i, :] = avgamp0  # - self.cfg["minADC"]

            # print('zspec', Z_spec)
            ax_plot_1 = axs[1].imshow(
                Z_spec,
                aspect='auto',
                extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                        np.max(Y) + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            if i == 0:  # if first sweep add a colorbar
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[1].set_ylabel("Delay Time (clock cycles (2.35 ns))")
            axs[1].set_xlabel("Spec Frequency (GHz)")
            axs[1].set_title("Qubit Spec")

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
        expt_cfg = {
            # transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  # number of points in the transmission frequecny
        }
        # take the transmission data
        self.cfg["reps"] = self.cfg["trans_reps"]
        self.cfg['rounds'] = 1
        fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        results = []
        for f in fpts:
            self.cfg["pulse_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)
        # pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]

        # find the frequency corresponding to the cavity peak and set as cavity transmission number
        sig = data_I + 1j * data_Q
        avgamp0 = np.abs(sig)
        filtered_amp = savgol_filter(avgamp0, 5, 2)
        if self.cfg["cavity_min"]:
            peak_loc = np.argmin(filtered_amp)
        else:
            peak_loc = np.argmax(filtered_amp)

        self.cfg["pulse_freq"] = self.trans_fpts[peak_loc]
        self.cfg['minADC'] = avgamp0[peak_loc]

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
