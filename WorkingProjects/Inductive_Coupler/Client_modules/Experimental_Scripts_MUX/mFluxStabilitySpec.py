from qick import *
import matplotlib.pyplot as plt
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import datetime
import time
import numpy as np
from scipy.signal import savgol_filter
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFProg

# ====================================================== #

class LoopbackProgramSpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        res_ch = cfg["res_ch"]

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

        # self.qubit_length_us = cfg["sigma"] * 3
        # self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        # self.pulse_qubit_lenth = self.us2cycles(self.qubit_length_us, gen_ch=self.cfg["qubit_ch"])
        # self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)
        # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
        #                          phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
        #                          waveform="qubit")
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.qubit_length_us = cfg["qubit_length"]

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, self.qubit_length_us + 3)
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(3))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 3)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start = 'auto', IQPulseArray = None, waveform_label = "FF"):
        FF.FFPulses(self, list_of_gains, length_us, t_start, IQPulseArray, waveform_label)
    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None, waveform_label='FF'):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains = previous_gains, t_start=t_start,
                           IQPulseArray=IQPulseArray, waveform_label=waveform_label)
    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


# ====================================================== #


class FluxStability(ExperimentClass):
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

    def acquire(self, plotDisp=True, plotSave=True, figNum=1, i_data=False, q_data=False,
                smart_normalize = True):
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

        delay_pts = self.cfg["delayStep"] * np.arange(self.cfg["DelayPoints"])

        # create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize=(8, 10), num=figNum)
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
            if i % 5 == 1:
                self.save_data(self.data)
                self.soc.reset_gens()
            if i != 0:
                time.sleep(max(0, self.cfg["delayStep"] * 60 - spec_time))
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
            start_spec = time.time()
            data_I, data_Q = self._acquireSpecData()
            end_spec = time.time()
            spec_time = end_spec - start_spec

            sig = data_I + 1j * data_Q
            if i == 0:
                angle = Amplitude_IQ_angle(data_I, data_Q)
            sig_all_i = sig * np.exp(1j * angle)

            self.data['data']['spec_Imat'][i, :] = sig_all_i.real
            self.data['data']['spec_Qmat'][i, :] = sig_all_i.imag




            # plot out the spec data


            # avgamp0 = np.abs(sig)
            # print(sig[10:20], sig_i[10:20])
            Z_spec[i, :] = sig_all_i.real  # - self.cfg["minADC"]

            # if i == 0:
            #     rangeQ = np.max(data_Q) - np.min(data_Q)
            #     rangeI = np.max(data_I) - np.min(data_I)
            #     if rangeQ > rangeI:
            #         q_data = True
            #         i_data = False
            #         # Z_spec[i, :] = (data_I - np.max(data_I)) / (np.max(data_I) - np.min(data_I))#- self.cfg["minADC"]
            #     else:
            #         q_data = False
            #         i_data = True
            #         # Z_spec[i, :] = (data_Q - np.max(data_Q)) / (np.max(data_Q) - np.min(data_Q))#- self.cfg["minADC"]
            # if i_data:
            #     Z_spec[i, :] = data_I
            # elif q_data:
            #     Z_spec[i, :] = data_Q
            # else:
            #     Z_spec[i, :] = avgamp0  # - self.cfg["minADC"]

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

            axs[1].set_ylabel("Delay Time (min)")
            axs[1].set_xlabel("Spec Frequency (GHz)")
            axs[1].set_title("Qubit Spec Flux Stability")

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

        initial_mixer_freq = self.cfg["mixer_freq"]
        for f in fpts:
            self.cfg["mixer_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        self.cfg["mixer_freq"] = initial_mixer_freq

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
                                         start_src="internal", progress=self.progress)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}

        data_I = data['data']['avgi'][0][0]
        data_Q = data['data']['avgq'][0][0]

        return data_I, data_Q

    def save_data(self, data=None):
        # save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

def Amplitude_IQ_angle(I, Q, phase_num_points = 200):
    '''
    IQ data is inputted and it will multiply by a phase such that all of the
    information is in I
    :param I:
    :param Q:
    :param phase_num_points:
    :return:
    '''
    complex = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complex * np.exp(1j * phase) for phase in phase_values]
    Q_range = np.array([np.max(IQPhase.imag) - np.min(IQPhase.imag) for IQPhase in multiplied_phase])
    phase_index = np.argmin(Q_range)
    angle = phase_values[phase_index]
    return(angle)