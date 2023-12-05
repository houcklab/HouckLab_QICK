from qick import *
from q4diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q4diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
from q4diamond.Client_modules.Helpers.rotate_SS_data import *
import time
import q4diamond.Client_modules.Helpers.FF_utils as FF
import pickle
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations import WalkFFProg


# class OscillationsProgram(AveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#
#         # Qubit
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
#         self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
#         self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
#         self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)
#
#         self.freq_01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=self.cfg["qubit_ch"])
#         self.freq_12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=self.cfg["qubit_ch"])
#
#         # Readout: resonator DAC gen and readout ADCs
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                  gain=cfg["pulse_gain"],
#                                  length=self.us2cycles(cfg["length"]))
#         for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
#                                  freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
#
#         FF.FFDefinitions(self)
#
#         self.sync_all(200)
#
#     def body(self):
#         self.sync_all(dac_t0=self.dac_t0)
#         self.FFPulses(self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
#         self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_01, phase=0,
#                              gain=self.cfg["qubit_gain01"],
#                              waveform="qubit", t=self.us2cycles(1))
#         self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_12, phase=0,
#                              gain=self.cfg["qubit_gain12"],
#                              waveform="qubit")
#         self.FFPulses_direct(self.FFExpts, self.cfg["variable_wait"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
#         self.sync_all(dac_t0=self.dac_t0)
#
#         self.FFPulses(self.FFReadouts, self.cfg["length"])
#
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0, 1],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(10))
#
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
#         IQ_Array_Negative = np.array([-1 * array if type(array) != type(None) else None for array in self.cfg["IDataArray"]], dtype = object)
#         self.FFPulses_direct(-1 * self.FFPulse, self.cfg["variable_wait"], -1 * self.FFPulse, IQPulseArray = IQ_Array_Negative,
#                             waveform_label='FF2')
#         self.FFPulses(-1 * self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
#
#     def FFPulses(self, list_of_gains, length_us, t_start='auto'):
#         FF.FFPulses(self, list_of_gains, length_us, t_start)
#
#     def FFPulses_hires(self, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
#         FF.FFPulses_hires(self, list_of_gains, length_us, t_start = t_start, IQPulseArray=IQPulseArray,
#                           waveform_label = waveform_label )
#
#     def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
#                         waveform_label = "FF"):
#         FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
#                            IQPulseArray=IQPulseArray, waveform_label = waveform_label)

class QubitSpecSliceFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        FF.FFDefinitions(self)
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])


        # add qubit and readout pulses to respective channels
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
        # print(cfg["qubit_length"], self.f_start, cfg['start'], cfg["qubit_gain"])

        # print(self.FFPulse)

    def body(self):
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), dac_t0=self.dac_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


class SpecGainSweep(ExperimentClass):
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
        # expt_cfg = {
        #     # spec parameters
        #     "qubit_freq_start": self.cfg["qubit_freq_start"],
        #     "qubit_freq_stop": self.cfg["qubit_freq_stop"],
        #     "SpecNumPoints": self.cfg["SpecNumPoints"],  # number of points
        # }
        gainVec = np.array([int(x) for x in np.linspace(self.cfg["gainStart"],self.cfg["gainStop"], self.cfg["gainNumPoints"])])
        # create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 1, figsize=(8, 10), num=figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        # create the frequency arrays for both transmission and spec

        # self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
        #                              expt_cfg["SpecNumPoints"])

        self.spec_fpts = self.cfg['start'] + np.arange(self.cfg['expts']) * self.cfg['step']


        Y = gainVec
        X_spec = self.spec_fpts / 1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y_step = Y[1] - Y[0]
        Z_spec = np.full((self.cfg["gainNumPoints"], self.cfg["SpecNumPoints"]), np.nan)

        # create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.spec_Imat = np.zeros((self.cfg["gainNumPoints"], self.cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((self.cfg["gainNumPoints"], self.cfg["SpecNumPoints"]))
        self.data = {
            'config': self.cfg,
            'data': {'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                     'gainVec': gainVec,
                     }
        }
        # start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('\nstarting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        # loop over the DelayPoints vector
        for i in range(self.cfg["gainNumPoints"]):
            if i % 5 == 1:
                self.save_data(self.data)
                self.soc.reset_gens()

            self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Pulse'] = int(gainVec[i])

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

            Z_spec[i, :] = sig_all_i.real  # - self.cfg["minADC"]

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

            axs.set_ylabel("Gain (a.u.)")
            axs.set_xlabel("Spec Frequency (GHz)")
            axs.set_title("Spec vs FF gain")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i == 0:  # during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  # time for single full row in seconds
                timeEst = (t_delta) * self.cfg["gainNumPoints"]  # estimate for full scan
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

    def _acquireSpecData(self):
        """
        code to acquire just the cavity transmission data
        """
        # take the transmission data
        # self.cfg["reps"] = self.cfg["spec_reps"]
        # self.cfg["rounds"] = self.cfg["spec_rounds"]

        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
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



# class QubitSpecGainSweep(ExperimentClass):
#     """
#     Basic T1
#     """
#
#     def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
#                  I_Ground = 0, I_Excited = 1, Q_Ground = 0, Q_Excited = 1):
#         super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
#                          config_file=config_file, progress=progress)
#
#     def acquire(self, threshold = None, angle = None, progress=False, debug=False, figNum = 1, plotDisp = True,
#                 plotSave = True):
#
#         gainVec = np.array([int(x) for x in np.linspace(self.cfg["gainStart"],self.cfg["gainStop"], self.cfg["gainNumPoints"])])
#         while plt.fignum_exists(num = figNum):
#             figNum += 1
#         fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
#         fig.suptitle(str(self.titlename), fontsize=16)
#
#         self.wait_times = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
#         Z_values = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
#
#         self.rotatedIQ = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
#
#         self.data= {
#             'config': self.cfg,
#             'data': {'Exp_values': [Z_values for i in range(len(self.cfg["ro_chs"]))],
#
#                         'gainVec': gainVec,
#                      }
#         }
#
#         tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
#
#         X = tpts
#         X_step = X[1] - X[0]
#         Y = gainVec
#         Y_step = Y[1] - Y[0]
#
#         startTime = datetime.datetime.now()
#         print('') ### print empty row for spacing
#         print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
#         if np.array(self.cfg["IDataArray"]).any() != None:
#
#             self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
#                                                                                    '1']['Gain_Pulse'], 1)
#             self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
#                                                                                    '2']['Gain_Pulse'], 2)
#             self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
#                                                                                    '3']['Gain_Pulse'], 3)
#             self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
#                                                                                '4']['Gain_Pulse'], 4)
#
#         print(np.round(self.cfg["IDataArray"][0][:20], 4))
#         print(np.round(self.cfg["IDataArray"][1][:20], 4))
#         print(np.round(self.cfg["IDataArray"][2][:20], 4))
#         print(np.round(self.cfg["IDataArray"][3][:20], 4))
#
#         start = time.time()
#         for i in range(self.cfg["gainNumPoints"]):
#             if i % 5 == 1:
#                 self.save_data(self.data)
#                 # self.soc.reset_gens()
#             self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Expt'] = int(gainVec[i])
#             if type(self.cfg["IDataArray"][0]) != type(None):
#                 self.cfg["IDataArray"][self.cfg["qubitIndex"] - 1] = Compensated_Pulse(int(gainVec[i]),
#                                                                                    self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Pulse'],
#                                                                                      self.cfg["qubitIndex"])
#             print('Printing')
#             print(np.round(self.cfg["IDataArray"][0][:20], 4))
#             print(np.round(self.cfg["IDataArray"][1][:20], 4))
#             print(np.round(self.cfg["IDataArray"][2][:20], 4))
#             print(np.round(self.cfg["IDataArray"][3][:20], 4))
#             for j in range(len(self.cfg["ro_chs"])):
#                 results = []
#                 rotated_iq_array = []
#                 start = time.time()
#                 for t in tqdm(tpts, position=0, disable=True):
#                     self.cfg["variable_wait"] = t
#                     # print('wait time: ', t)
#                     prog = OscillationsProgramSS(self.soccfg, self.cfg)
#                     shots_i0, shots_q0 = prog.acquire(self.soc,
#                                                       load_pulses=True)
#                     rotated_iq = rotate_data((shots_i0[j], shots_q0[j]), theta=angle[j])
#                     rotated_iq_array.append(rotated_iq)
#                     excited_percentage = count_percentage(rotated_iq, threshold = threshold[j])
#                     results.append(excited_percentage)
#                 print(f'Time: {time.time() - start}')
#
#                 self.data['data']["Exp_values"][j][i, :] = np.array(results)
#
#                 # results = np.transpose(results)
#                 # self.data['data']["RotatedIQ"][i, :] = np.array(rotated_iq_array)
#                 if j == 0:
#                     Z_values[i, :] = np.array(results)
#
#             if i == 0:
#                 ax_plot_1 = axs.imshow(
#                     Z_values,
#                     aspect='auto',
#                     extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
#                             Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
#                     origin='lower',
#                     interpolation='none',
#                 )
#                 cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
#                 cbar1.set_label('Excited Population', rotation=90)
#             else:
#                 ax_plot_1.set_data(Z_values)
#                 ax_plot_1.autoscale()
#                 cbar1.remove()
#                 cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
#                 cbar1.set_label('Excited Population', rotation=90)
#
#             axs.set_ylabel("FF Gain (a.u.)")
#             axs.set_xlabel("Wait time (2.32/16 ns )")
#             axs.set_title("Oscillations")
#
#
#             if plotDisp:
#                 plt.show(block=False)
#                 plt.pause(0.1)
#
#             if i ==0: ### during the first run create a time estimate for the data aqcuisition
#                 t_delta = time.time() - start + 5 * 2### time for single full row in seconds
#                 timeEst = (t_delta )*self.cfg["gainNumPoints"]  ### estimate for full scan
#                 StopTime = startTime + datetime.timedelta(seconds=timeEst)
#                 print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
#                 print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
#                 print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))
#
#
#         if plotSave:
#             plt.savefig(self.iname) #### save the figure
#
#         print(f'Time: {time.time() - start}')
#
#
#         # results = np.transpose(results)
#
#         # data={'config': self.cfg, 'data': {'results': results, 'tpts':tpts}}
#         #### pull the data from the amp rabi sweep
#         # prog = OscillationsProgram_RAverager_Wrong(self.soccfg, self.cfg)
#         #
#         # x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
#         #                                  readouts_per_experiment=1, save_experiments=None,
#         #                                  start_src="internal", progress=False, debug=False)
#         # data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
#         # self.data = data
#
#         return self.data
#
#
#     def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
#         if data is None:
#             data = self.data
#
#         x_pts = data['data']['wait_times']
#         percent_excited = data['data']['Exp_values']
#         gainVec = data['data']['gainVec']
#
#         X = x_pts
#         Y = gainVec
#
#         X_step = X[1] - X[0]
#         Y_step = Y[1] - Y[0]
#
#         for i, read_index in enumerate(self.cfg['Read_Indeces']):
#             while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
#                 figNum += 1
#
#             fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
#             fig.suptitle(str(self.titlename), fontsize=16)
#             ax_plot_1 = axs.imshow(
#                 percent_excited[i],
#                 aspect='auto',
#                 extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
#                         Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
#                 origin='lower',
#                 interpolation='none',
#             )
#             cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
#             cbar1.set_label('Excited Population', rotation=90)
#
#             axs.set_ylabel("FF Gain (a.u.)")
#             axs.set_xlabel("Wait time (2.32/16 ns )")
#             axs.set_title("Oscillations")
#             plt.title(self.titlename + ", Read: " + str(read_index))
#             plt.savefig(self.iname[:-4] + "_Read_" + str(read_index) + '.png')
#         # fig = plt.figure(figNum)
#         # plt.plot(x_pts, percent_excited, 'o-', label="i", color = 'orange')
#         # plt.ylabel("Excited Population")
#         # plt.xlabel("Wait time (2.32/16 ns )")
#         # plt.legend()
#         # plt.title(self.titlename)
#         # plt.savefig(self.iname)
#         #
#         # if plotDisp:
#         #     plt.show(block=True)
#         #     plt.pause(0.1)
#         # else:
#         #     fig.clf(True)
#         #     plt.close(fig)
#
#
#
#     def save_data(self, data=None):
#         print(f'Saving {self.fname}')
#         super().save_data(data=data['data'])


import pickle
def QuadExponentialFit(t, A1, T1, A2, T2, A3, T3, A4, T4):
    return(A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2) + A3 * np.exp(-t / T3) + A4 * np.exp(-t / T4))

def Compensated_AWG(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = QuadExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3], Fit_Parameters[4], Fit_Parameters[5],
                                   Fit_Parameters[6], Fit_Parameters[7])
    analytic_n[analytic_n < -0.8] = -0.8
    v_awg = ideal_AWG / (1 + analytic_n)
    v_awg[v_awg > maximum] = maximum
    return(time, v_awg)

def DoubleExponentialFit(t, A1, T1, A2, T2):
    return (A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2))

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = DoubleExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3])
    print('analytic_n Before correction', analytic_n[:30])
    analytic_n[analytic_n < -0.7] = -0.7
    print('analytic_n After correction', analytic_n[:30])

    v_awg = ideal_AWG / (1 + analytic_n)
    print('v_awg Before correction', v_awg[:30])

    v_awg[v_awg > maximum] = maximum
    print('v_awg After correction', v_awg[:30])

    return(time, v_awg)
# Pulse_Q1 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q1_awg_V1.p', 'rb'))
# Pulse_Q2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
# Pulse_Q4 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q4_awg_V1.p', 'rb'))
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected.p', 'rb'))
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_corrected_V3.p', 'rb'))
# Qubit2_parameters_long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected_LongTime_3.p', 'rb'))

Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_PreFinal.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_PreFinal.p', 'rb'))
# Qubit1_[0] *= 1.
# Qubit1_[2] *= 1.
# Qubit1_[4] *= 1.2
#
# # print(Qubit4_)
# Qubit4_[0] *= 1.6
# Qubit4_[2] *= 1.6
# Qubit4_[4] *= 1.7

# print(Qubit4_)

Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_PreFinal.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
Qubit2_[0] *= 0.75
Qubit2_[2] *= 0.75
Qubit2_[4] *= 1

v_awg_Q1 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit4_)[1]

print(v_awg_Q1[:20])

# v_awg_Q2 = Compensated_AWG_LongTimes(150 * 2 * 16 * 3, Qubit2_parameters_long)[1]

# print(v_awg_Q2)

Compensated_pulse_list = [v_awg_Q1, v_awg_Q2, v_awg_Q2, v_awg_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)

# Compensated_Step_Pulse = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/v_awg_V2.p', 'rb'))
# Compensated_Step_Pulse = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V1.p', 'rb'))
# Compensated_Step_Pulse = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
#
#
# def Compensated_Pulse(final_gain, initial_gain, compensated = True):
#     # Compensated_Step_Pulse
#     if not compensated:
#         return(np.ones(16 * 800) * final_gain)
#     # Compensated_Step_Pulse[700:] = 1
#     # Compensated_Step_Pulse[0] = 2
#     # Compensated_Step_Pulse[3000:] = 1
#     # Compensated_Step_Pulse[:6] = 1.5
#     Compensated_Step_Pulse[3000:] = 1
#     Compensated_Step_Pulse[:4] = 2
#     Comp_Step = np.concatenate([Compensated_Step_Pulse, np.ones(len(Compensated_Step_Pulse) % 16 + 16 * 800)])
#
#     Comp_Difference = Comp_Step - 1
#     Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
#     return(Comp_Step_Gain)
def Amplitude_IQ(I, Q, phase_num_points = 200):
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
    return(phase_values[phase_index])
    # final_complex = complex * np.exp(1j * phase_values[phase_index])
    # plt.plot(complex.real, label = 'I Before')
    # plt.plot(complex.imag, label = 'Q Before')
    #
    # plt.plot(final_complex.real, label = 'I After')
    # plt.plot(final_complex.imag, label = 'Q After')
    # plt.legend()
    # plt.show()

    print(max(I) - min(I),
          max(Q) - min(Q),
          max(final_complex.real) - min(final_complex.real),
          max(final_complex.imag) - min(final_complex.imag))
    return(final_complex.real)

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