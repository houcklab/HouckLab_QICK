from qick import *
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.tProc_V2.Helpers_V2.FF_utils as FF

# seems to not depend on tProc version
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Qblox_Functions import Qblox

from qick.asm_v2 import AveragerProgramV2

class CavitySpecFFProg(AveragerProgramV2):
    def initialize(self, cfg):
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name='res_pulse', style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=cfg["length"])

        FF.FFDefinitions(self)
        #self.synci(200)  # give processor some time to configure pulses

    def body(self, cfg):
        #self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])

        # measure
        self.trigger(ros=self.cfg["ro_chs"], pins=[0],
                     t=self.cfg["adc_trig_offset"])
        self.pulse(self.cfg["res_ch"], name='res_pulse')
        self.delay_auto(10)

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        #self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)
# ====================================================== #
class QubitSpecSliceFFProg(AveragerProgramV2):
    def initialize(self, cfg):

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name='res_pulse', style="const", mask=cfg["ro_chs"],  # gain=cfg["pulse_gain"],
                       length=cfg["length"])


        #self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        #self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        FF.FFDefinitions(self)
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        #self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        #self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        self.add_loop("qubit_ch_freq_loop", self.cfg["SpecNumPoints"])

        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
            #                          phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
            #                          waveform="qubit")
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_pulse', style="arb", freq=cfg["qubit_sweep_freq"],
                           phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                           waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            # self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
            #                          length=self.us2cycles(cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_pulse', style="const", freq=cfg["qubit_sweep_freq"], phase=0,
                           gain=cfg["qubit_gain"], length=cfg["qubit_length"])
            self.qubit_length_us = cfg["qubit_length"]

    def body(self, cfg):
        #self.sync_all(gen_t0=self.gen_t0)
        self.delay_auto(0)

        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=self.cfg["qubit_ch"], t = 1)  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        #self.sync_all(gen_t0=self.gen_t0)
        self.delay_auto(0) # equivalen of sync_all?
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        # self.FFPulses(self.FFPulse, self.cfg["length"])
        # self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        # measure
        self.trigger(ros=self.cfg["ro_chs"], pins=[0],
                     t=self.cfg["adc_trig_offset"])
        self.pulse(self.cfg["res_ch"], name='res_pulse')
        self.delay_auto(10)

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1)
        #self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    # not needed in V2
    #def update(self):
    #    self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


# ====================================================== #


class SpecVsQblox(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum as a function of flux, specifically it uses a qblox to sweep
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through qblox
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None,
                 config_file=None, progress=None, qblox = None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, qblox = qblox)

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, plotDisp = True, plotSave = True, figNum = 1,
                smart_normalize = True):
        expt_cfg = {
            ### define the qblox parameters
            "qbloxStart": self.cfg["qbloxStart"],
            "qbloxStop": self.cfg["qbloxStop"],
            "qbloxNumPoints": self.cfg["qbloxNumPoints"],
            ### transmission parameters
            # "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            # "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            # "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
            ### spec parameters
            "step": self.cfg["step"],
            "start": self.cfg["start"],
            "expts": self.cfg["expts"],
        }
        #print(self.cfg["step"], self.cfg["start"], self.cfg["expts"])

        qbloxVec = []
        for n in range(len(expt_cfg["qbloxStart"])):
            qbloxVec.append(np.linspace(expt_cfg["qbloxStart"][n],expt_cfg["qbloxStop"][n], expt_cfg["qbloxNumPoints"]))

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        # fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
        fig, axs = plt.subplots(1,1, figsize = (8,6), num = figNum)

        # fig.suptitle(str(self.identifier), fontsize=16)
        ### create the frequency arrays for both transmission and spec
        ### also create empty array to fill with transmission and spec data
        # self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        # self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.spec_fpts = expt_cfg["start"] + np.arange(expt_cfg["expts"]) * expt_cfg["step"]
        print(self.spec_fpts)

        # X_trans = (self.trans_fpts + self.cfg["cavity_LO"]/1e6) /1e3
        # X_trans_step = X_trans[1] - X_trans[0]
        X_spec = self.spec_fpts/1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y = qbloxVec[0]
        Y_step = Y[1] - Y[0]
        # Z_trans = np.full((expt_cfg["qbloxNumPoints"], expt_cfg["TransNumPoints"]), np.nan)
        Z_spec = np.full((expt_cfg["qbloxNumPoints"], expt_cfg["expts"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        # self.trans_Imat = np.zeros((expt_cfg["qbloxNumPoints"], expt_cfg["TransNumPoints"]))
        # self.trans_Qmat = np.zeros((expt_cfg["qbloxNumPoints"], expt_cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((expt_cfg["qbloxNumPoints"], expt_cfg["expts"]))
        self.spec_Qmat = np.zeros((expt_cfg["qbloxNumPoints"], expt_cfg["expts"]))
        self.data= {
            'config': self.cfg,
            'data': {#'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'qbloxVec': qbloxVec
                     }
        }

        print(qbloxVec)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()


        QbloxClass = Qblox()
        #### loop over the qblox vector
        for i in range(expt_cfg["qbloxNumPoints"]):
            if i != 0:
                time.sleep(self.cfg['sleep_time'])
            if i % 5 == 1:
                self.save_data(self.data)
                self.soc.reset_gens()
            ### set the qblox voltage for the specific run
            # self.qblox.SetVoltage(qbloxVec[i])
            voltages_for_qblox = []
            for m in range(len(self.cfg['DACs'])):
                voltages_for_qblox.append(qbloxVec[m][i])
            print(voltages_for_qblox)
            QbloxClass.set_voltage(self.cfg['DACs'], voltages_for_qblox)
            # QbloxClass.print_voltages()
            time.sleep(1)

            if i != expt_cfg["qbloxNumPoints"]:
                time.sleep(self.cfg['sleep_time'])

            ### take the spec data
            data_I, data_Q = self._aquireSpecData()
            data_I = data_I[0]
            data_Q = data_Q[0]

            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q


            avgamp0 = np.abs(sig)
            if smart_normalize:
                avgamp0 = Normalize_Qubit_Data(data_I[0], data_Q[0])
            Z_spec[i, :] = avgamp0  #- self.cfg["minADC"]
            if i == 0:

                ax_plot_1 = axs.imshow(
                    Z_spec,
                    aspect='auto',
                    extent=[X_spec[0]-X_spec_step/2,X_spec[-1]+X_spec_step/2,Y[0]-Y_step/2,Y[-1]+Y_step/2],
                    origin='lower',
                    interpolation = 'none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_spec)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)
            # if i ==0: #### if first sweep add a colorbar
            #     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
            #     cbar1.set_label('a.u.', rotation=90)
            # else:
            #     cbar1.remove()
            #     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
            #     cbar1.set_label('a.u.', rotation=90)

            axs.set_ylabel("Qblox (V)")
            axs.set_xlabel("Spec Frequency (GHz)")
            axs.set_title(f"{self.titlename}, QDAC: {self.cfg['DACs']}, "
                             f"Cav Freq: {np.round(self.cfg['pulse_freqs'][0] + self.cfg['mixer_freq'] + self.cfg['cavity_LO'] / 1e6, 3)}")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + self.cfg["sleep_time"] * 2### time for single full row in seconds
                timeEst = (t_delta )*expt_cfg["qbloxNumPoints"]  ### estimate for full scan
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

    def _aquireTransData(self, progress=False):
        fpts = np.linspace(self.cfg["mixer_freq"] - self.cfg["TransSpan"],
                           self.cfg["mixer_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["mixer_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        print(results)
        # data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        # self.data=data
        #
        # #### find the frequency corresponding to the peak
        # sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        # avgamp0 = np.abs(sig)
        # peak_loc = np.argmin(avgamp0)
        # self.peakFreq_min = data['data']['fpts'][peak_loc]
        # peak_loc = np.argmax(avgamp0)
        # self.peakFreq_max = data['data']['fpts'][peak_loc]

        # return data
        return results[0][0][0], results['results'][0][0][1]

    # def _aquireTransData(self):
    #     ##### code to aquire just the cavity transmission data
    #     expt_cfg = {
    #         ### transmission parameters
    #         "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
    #         "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
    #         "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
    #     }
    #     ### take the transmission data
    #     self.cfg["reps"] = self.cfg["trans_reps"]
    #     fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
    #     results = []
    #     start = time.time()
    #     for f in tqdm(fpts, position=0, disable=True):
    #         self.cfg["pulse_freq"] = f
    #         prog = LoopbackProgramTrans(self.soccfg, self.cfg)
    #         results.append(prog.acquire(self.soc, load_pulses=True))
    #     results = np.transpose(results)
    #     #### pull out I and Q data
    #     data_I = results[0][0][0]
    #     data_Q = results[0][0][1]
    #
    #     #### find the frequency corresponding to the cavity peak and set as cavity transmission number
    #     sig = data_I + 1j * data_Q
    #     avgamp0 = np.abs(sig)
    #     filtered_amp = savgol_filter(avgamp0, 5, 2)
    #     peak_loc = np.argmin(filtered_amp)
    #     self.cfg["pulse_freq"] = self.trans_fpts[peak_loc]
    #     self.cfg['minADC'] = avgamp0[peak_loc]
    #
    #     return data_I, data_Q

    def _aquireSpecData(self, progress=False):

        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, soft_avgs = cfg['rounds'], threshold=None, angle=None, load_pulses=True,
                                         start_src="internal", progress=False)

        # data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # self.data = data
        #
        # x_pts = data['data']['x_pts']
        # avgi = data['data']['avgi']
        # avgq = data['data']['avgq']
        #
        # #### find the frequency corresponding to the qubit dip
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        # peak_loc = np.argmax(avgamp0)
        # self.qubitFreq = x_pts[peak_loc]

        return avgi, avgq

    # def _aquireSpecData(self):
    #     ##### code to aquire just the cavity transmission data
    #     expt_cfg = {
    #         ### spec parameters
    #         "qubit_freq_start": self.cfg["qubit_freq_start"],
    #         "qubit_freq_stop": self.cfg["qubit_freq_stop"],
    #         "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
    #     }
    #     ### take the transmission data
    #     self.cfg["reps"] = self.cfg["spec_reps"]
    #     fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
    #     results = []
    #     start = time.time()
    #     for f in tqdm(fpts, position=0, disable=True):
    #         self.cfg["qubit_freq"] = f
    #         prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
    #         results.append(prog.acquire(self.soc, load_pulses=True))
    #     results = np.transpose(results)
    #     #### pull out I and Q data
    #     data_I = results[0][0][0]
    #     data_Q = results[0][0][1]
    #
    #     return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


# def Normalize_Qubit_Data(idata, qdata):
#     idata_rotated = Amplitude_IQ_angle(idata, qdata)
#     idata_rotated -= np.median(idata_rotated) #subtract the offset
#     range_ = max(idata_rotated) - min(idata_rotated)
#     idata_rotated *= 1 / range_   #normalize data to have amplitude of 1
#     if np.abs(max(idata_rotated)) < np.abs(min(idata_rotated)):
#         idata_rotated *= -1 #ensures that the spec has a peak rather than a dip
#     return(idata_rotated)

def Normalize_Qubit_Data(idata, qdata):
    idata_rotated = Amplitude_IQ_angle(idata, qdata)
    idata_rotated -= np.median(idata_rotated) #subtract the offset
    range_ = max(idata_rotated) - min(idata_rotated)
    if np.abs(max(idata_rotated)) < np.abs(min(idata_rotated)):
        idata_rotated *= -1 #ensures that the spec has a peak rather than a dip
    idata_rotated -= min(idata_rotated)
    idata_rotated *= 1 / range_   #normalize data to have amplitude of 1

    return(idata_rotated)

def Amplitude_IQ_angle(I, Q, phase_num_points = 50):
    '''
    IQ data is inputted and it will multiply by a phase such that all of the
    information is in I
    :param I:
    :param Q:
    :param phase_num_points:
    :return: Array of data all in I quadrature
    '''
    complexarg = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complexarg * np.exp(1j * phase) for phase in phase_values]
    I_range = np.array([np.max(IQPhase.real) - np.min(IQPhase.real) for IQPhase in multiplied_phase])
    phase_index = np.argmax(I_range)
    angle = phase_values[phase_index]
    complexarg *= np.exp(1j * angle)
    return(complexarg.real)

