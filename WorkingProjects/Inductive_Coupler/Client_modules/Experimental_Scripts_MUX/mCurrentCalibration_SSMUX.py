from qick import *
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.rotate_SS_data import *
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
import pickle
# from WorkingProjects.Inductive_Coupler.Client_modules.Experiment_Scripts.mRabiOscillations import WalkFFProg


class CurrentCalibrationProgramSS(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # Qubit
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        # Readout: resonator DAC gen and readout ADCs
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


        FF.FFDefinitions(self)

        self.sync_all(200)

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            gain_ = self.cfg["qubit_gains"][i]
            freq_ = self.freq2reg(self.cfg["f_ges"][i], gen_ch=self.cfg["qubit_ch"])
            time = 'auto'
            if i == 0:
                time = self.us2cycles(1)

            # print(freq_, gain_, time)
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                 gain=gain_,
                                 waveform="qubit", t=time)
        self.FFPulses_direct(self.FFExpts, self.cfg["t_evolve"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"])
        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses_direct(self.cfg['Gains_BS'], self.cfg["t_BS"], self.FFExpts, IQPulseArray= self.cfg["IDataArrayBS"])
        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])

        IQ_Array_Negative_BS = np.array([-1 * array if type(array) != type(None) else None for array in
                                      self.cfg["IDataArrayBS"]])
        self.FFPulses_direct(-1 * self.cfg['Gains_BS'], self.cfg["t_BS"], -1 * self.FFExpts, IQPulseArray=IQ_Array_Negative_BS,
                             waveform_label='FFBS2')
        IQ_Array_Negative = np.array([-1 * array if type(array) != type(None) else None for array in self.cfg["IDataArray"]])
        self.FFPulses_direct(-1 * self.FFPulse, self.cfg["t_evolve"], -1 * self.FFPulse, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')

        self.FFPulses(-1 * self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_hires(self, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
        FF.FFPulses_hires(self, list_of_gains, length_us, t_start = t_start, IQPulseArray=IQPulseArray,
                          waveform_label = waveform_label )

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)
    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress)#, debug=debug)

        return self.collect_shots()

    # def collect_shots(self):
    #     shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
    #         self.cfg['readout_length'], ro_ch=0)
    #     shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
    #         self.cfg['readout_length'], ro_ch=0)
    #     return shots_i0, shots_q0

    def collect_shots(self):
        all_i = []
        all_q = []
        # print(self.di_buf)#, self.di_buf[1][:30])
        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            shots_q0=self.dq_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


class CurrentCalibration_SSMUX(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 I_Ground = 0, I_Excited = 1, Q_Ground = 0, Q_Excited = 1):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, progress=False, figNum = 1, plotDisp = True,
                plotSave = True):

        gainVec = np.array([int(x) for x in np.linspace(self.cfg["gainStart"],self.cfg["gainStop"], self.cfg["gainNumPoints"])])
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        Z_values = np.full(self.cfg["gainNumPoints"], np.nan)
        # self.I_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        # self.Q_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        self.rotatedIQ = np.full(self.cfg["gainNumPoints"], np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': [Z_values for i in range(len(self.cfg["ro_chs"]))], 'RotatedIQ': self.rotatedIQ, 'threshold':threshold,
                        'angle': angle, 'gainVec': gainVec,
                     }
        }


        # X = tpts
        # X_step = X[1] - X[0]
        # Y = gainVec
        # Y_step = Y[1] - Y[0]

        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        if np.array(self.cfg["IDataArray"]).any() != None:

            self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '1']['Gain_Pulse'], 1)
            self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '2']['Gain_Pulse'], 2)
            self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '3']['Gain_Pulse'], 3)
            self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '4']['Gain_Pulse'], 4)

        # self.cfg['Gains_BS'] = {qubit: 0 for qubit in self.cfg['FF_Qubits']}
        self.cfg['Gains_BS'] = np.zeros(len(self.cfg['FF_Qubits']))


        # print(np.round(self.cfg["IDataArray"][0][:20], 4))
        # print(np.round(self.cfg["IDataArray"][1][:20], 4))
        # print(np.round(self.cfg["IDataArray"][2][:20], 4))
        # print(np.round(self.cfg["IDataArray"][3][:20], 4))

        start = time.time()
        for i in range(self.cfg["gainNumPoints"]):
            if i % 5 == 1:
                self.save_data(self.data)
                # self.soc.reset_gens()

            for index in self.cfg["qubit_BS_indices"]:
                self.cfg['Gains_BS'][index] = self.cfg['FF_Qubits'][str(index+1)]['Gain_BS']


            if np.array(self.cfg["IDataArrayBS"]).any() != None:
                self.cfg["IDataArrayBS"][0] = Compensated_Pulse(self.cfg['Gains_BS'][0],
                                                                self.cfg['FF_Qubits']['1']['Gain_Expt'], 1)
                self.cfg["IDataArrayBS"][1] = Compensated_Pulse(self.cfg['Gains_BS'][1],
                                                                self.cfg['FF_Qubits']['2']['Gain_Expt'], 2)
                self.cfg["IDataArrayBS"][2] = Compensated_Pulse(self.cfg['Gains_BS'][2],
                                                                self.cfg['FF_Qubits']['3']['Gain_Expt'], 3)
                self.cfg["IDataArrayBS"][3] = Compensated_Pulse(self.cfg['Gains_BS'][3],
                                                                self.cfg['FF_Qubits']['4']['Gain_Expt'], 4)

            # offset one channel from the other by t_offset (units of 1/16 clock cycles
            channel_1 = self.cfg['qubit_BS_indices'][0]
            channel_2 = self.cfg['qubit_BS_indices'][1]

            # play pulse on channel 2 t_offset later than channel 1
            if self.cfg['t_offset'] > 0:
                channel = channel_2
            else:
                channel = channel_1

            previous_gain = self.cfg['FF_Qubits'][str(channel + 1)]['Gain_Expt']
            for channel_index in range(len(self.cfg["IDataArrayBS"])):
                if channel_index == channel:
                    # pad at beginning to delay this channel
                    self.cfg["IDataArrayBS"][channel_index] = np.pad(self.cfg["IDataArrayBS"][channel_index], (abs(self.cfg['t_offset']), 0),
                                                               constant_values=previous_gain)
                else:
                    # pad at end to match lengths
                    self.cfg["IDataArrayBS"][channel_index] = np.pad(self.cfg["IDataArrayBS"][channel_index],
                                                               (0, abs(self.cfg['t_offset'])),
                                                               constant_values=previous_gain)

            # if type(self.cfg["IDataArray"][0]) != type(None):
            #     self.cfg["IDataArray"][self.cfg["qubitIndex"] - 1] = Compensated_Pulse(int(gainVec[i]),
            #                                                                        self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Pulse'],
            #                                                                          self.cfg["qubitIndex"])
            # print('Printing')
            # print(np.round(self.cfg["IDataArray"][0][:20], 4))
            # print(np.round(self.cfg["IDataArray"][1][:20], 4))
            # print(np.round(self.cfg["IDataArray"][2][:20], 4))
            # print(np.round(self.cfg["IDataArray"][3][:20], 4))
            for j in range(len(self.cfg["ro_chs"])):
                start = time.time()
                prog = CurrentCalibrationProgramSS(self.soccfg, self.cfg)
                shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
                rotated_iq = rotate_data((shots_i0[j], shots_q0[j]), theta=angle[j])

                excited_percentage = count_percentage(rotated_iq, threshold = threshold[j])
                result = excited_percentage

                self.data['data']["Exp_values"][j][i] = result

                if j == 0:
                    Z_values[i] = result


            if plotDisp:
                # plot during experiment
                if i == 0:

                    ax_plot, = axs.plot(gainVec, self.data['data']["Exp_values"][j], label="Excited Population")  # Line plot
                    axs.set_xlabel("Gain")
                    axs.set_ylabel("Excited Population")
                    axs.legend()
                else:
                    ax_plot.set_ydata(self.data['data']["Exp_values"][j])  # Update y-values
                    axs.relim()  # Recalculate limits
                    axs.autoscale_view()  # Autoscale the view

                axs.set_ylabel("FF Gain (a.u.)")
                axs.set_xlabel("Wait time (2.32/16 ns )")
                axs.set_title("Oscillations")


                plt.show(block=False)
                plt.pause(0.1)
            else:
                fig.clf(True)
                plt.close(fig)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + 5 * 2### time for single full row in seconds
                timeEst = (t_delta )*self.cfg["gainNumPoints"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        # if plotSave:
        #     plt.savefig(self.iname) #### save the figure

        print(f'Time: {time.time() - start}')

        # results = np.transpose(results)

        # data={'config': self.cfg, 'data': {'results': results, 'tpts':tpts}}
        #### pull the data from the amp rabi sweep
        # prog = OscillationsProgram_RAverager_Wrong(self.soccfg, self.cfg)
        #
        # x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
        #                                  readouts_per_experiment=1, save_experiments=None,
        #                                  start_src="internal", progress=False)
        # data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # self.data = data

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        percent_excited = data['data']['Exp_values'][0]
        gainVec = data['data']['gainVec']


        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
                figNum += 1

            fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
            fig.suptitle(str(self.titlename), fontsize=16)

            ax_plot, = axs.plot(gainVec, percent_excited, label="Excited Population")  # Line plot
            axs.set_xlabel("FF Gain (a.u.)")
            axs.set_ylabel("Excited Population")
            axs.legend()

            # axs.set_ylabel("FF Gain (a.u.)")
            # axs.set_xlabel("Wait time (2.32/16 ns )")
            # axs.set_title(f"Beam Splitter Calibration, $t_offset$ = {self.cfg['t_offset']}")
            plt.title(self.titlename + ", Read: " + str(read_index))
            plt.savefig(self.iname[:-4] + "_Read_" + str(read_index) + '.png')
        # fig = plt.figure(figNum)
        # plt.plot(x_pts, percent_excited, 'o-', label="i", color = 'orange')
        # plt.ylabel("Excited Population")
        # plt.xlabel("Wait time (2.32/16 ns )")
        # plt.legend()
        # plt.title(self.titlename)
        # plt.savefig(self.iname)
        #
        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)



    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])



class CurrentCalibration_OffsetSweep_SSMUX(ExperimentClass):
    """
    Sweep offset between two FF pulses in the middle of two qubit swaps
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 I_Ground = 0, I_Excited = 1, Q_Ground = 0, Q_Excited = 1):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, progress=False, figNum = 1, plotDisp = True,
                plotSave = True):

        timeVec = np.array([int(x) for x in np.linspace(self.cfg["timeStart"],self.cfg["timeStop"], self.cfg["timeNumPoints"])])
        offsetVec = np.array([int(x) for x in np.linspace(self.cfg["offsetStart"],self.cfg["offsetStop"], self.cfg["offsetNumPoints"])])

        print(f'offsetVec: {offsetVec}')



        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        Z_values = np.full((self.cfg["offsetNumPoints"], self.cfg["timeNumPoints"]), np.nan)
        # self.I_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        # self.Q_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        self.rotatedIQ = np.full((self.cfg["offsetNumPoints"], self.cfg["timeNumPoints"]), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': [Z_values for i in range(len(self.cfg["ro_chs"]))], 'RotatedIQ': self.rotatedIQ, 'threshold':threshold,
                        'angle': angle, 'timeVec': timeVec, 'offsetVec': offsetVec,
                     }
        }



        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        if np.array(self.cfg["IDataArray"]).any() != None:

            self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '1']['Gain_Pulse'], 1)
            self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '2']['Gain_Pulse'], 2)
            self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '3']['Gain_Pulse'], 3)
            self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '4']['Gain_Pulse'], 4)
        self.cfg['Gains_BS'] = np.zeros(len(self.cfg['FF_Qubits']))
        for index in self.cfg["qubit_BS_indices"]:
            self.cfg['Gains_BS'][index] = self.cfg['FF_Qubits'][str(index + 1)]['Gain_BS']

        # print(np.round(self.cfg["IDataArray"][0][:20], 4))
        # print(np.round(self.cfg["IDataArray"][1][:20], 4))
        # print(np.round(self.cfg["IDataArray"][2][:20], 4))
        # print(np.round(self.cfg["IDataArray"][3][:20], 4))

        X = timeVec
        X_step = X[1] - X[0]
        Y = offsetVec
        Y_step = Y[1] - Y[0]

        start = time.time()

        for i in range(self.cfg["offsetNumPoints"]):
            self.cfg["t_offset"] = offsetVec[i]
            t_offset = self.cfg["t_offset"]

            if np.array(self.cfg["IDataArrayBS"]).any() != None:
                self.cfg["IDataArrayBS"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_BS'],
                                                                self.cfg['FF_Qubits'][
                                                                    '1']['Gain_Expt'], 1)
                self.cfg["IDataArrayBS"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_BS'],
                                                                self.cfg['FF_Qubits'][
                                                                    '2']['Gain_Expt'], 2)
                self.cfg["IDataArrayBS"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_BS'],
                                                                self.cfg['FF_Qubits'][
                                                                    '3']['Gain_Expt'], 3)
                self.cfg["IDataArrayBS"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_BS'],
                                                                self.cfg['FF_Qubits'][
                                                                    '4']['Gain_Expt'], 4)

            # offset one channel from the other by t_offset (units of 1/16 clock cycles
            channel_1 = self.cfg['qubit_BS_indices'][0]
            channel_2 = self.cfg['qubit_BS_indices'][1]

            # unpadded_array_1 = self.cfg["IDataArrayBS"][channel_1]
            # unpadded_array_2 = self.cfg["IDataArrayBS"][channel_2]

            if t_offset > 0:
                # play pulse on channel 2 t_offset later than channel 1
                channel = channel_2
            else:
                # play pulse on channel 1 t_offset later than channel 2
                channel = channel_1

            previous_gain = self.cfg['FF_Qubits'][str(channel + 1)]['Gain_Expt']
            for channel_index in range(len(self.cfg["IDataArrayBS"])):
                if channel_index == channel:
                    # pad at beginning to delay this channel
                    self.cfg["IDataArrayBS"][channel_index] = np.pad(self.cfg["IDataArrayBS"][channel_index],
                                                                     (abs(t_offset), 0),
                                                                     constant_values=previous_gain)
                else:
                    # pad at end to match lengths
                    self.cfg["IDataArrayBS"][channel_index] = np.pad(self.cfg["IDataArrayBS"][channel_index],
                                                                     (0, abs(t_offset)),
                                                                     mode='edge')

            # for l in range(len(self.cfg['FF_Qubits'])):
            #     plt.plot(self.cfg["IDataArrayBS"][l], label=f'channel {l + 1}')
            # plt.legend()
            # plt.title(f'IDataArrayBS for t_offset={t_offset}')
            # plt.xlim(0, 500)
            # plt.show()

            if i % 5 == 1:
                self.save_data(self.data)
                # self.soc.reset_gens()

            for j in range(self.cfg["timeNumPoints"]):

                self.cfg['t_BS'] = timeVec[j]


                for k in range(len(self.cfg["ro_chs"])):
                    prog = CurrentCalibrationProgramSS(self.soccfg, self.cfg)
                    shots_i0, shots_q0 = prog.acquire(self.soc,
                                                      load_pulses=True)
                    rotated_iq = rotate_data((shots_i0[k], shots_q0[k]), theta=angle[k])
                    excited_percentage = count_percentage(rotated_iq, threshold=threshold[k])

                    self.data['data']["Exp_values"][k][i, j] = excited_percentage

                    if k == 0:
                        Z_values[i, j] = excited_percentage

            if plotDisp:
                if i == 0:
                    ax_plot_1 = axs.imshow(
                        Z_values,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    axs.set_xlabel("Wait time (2.32/16 ns )")
                    axs.set_ylabel("Offset time (2.32/16 ns )")
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                    cbar1.set_label('Excited Population', rotation=90)
                else:
                    ax_plot_1.set_data(Z_values)
                    ax_plot_1.autoscale()
                    cbar1.remove()
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                    cbar1.set_label('Excited Population', rotation=90)

                plt.show(block=False)
                plt.pause(0.1)
            else:
                fig.clf(True)
                plt.close(fig)

            if i == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + 5 * 2  ### time for single full row in seconds
                timeEst = (t_delta) * self.cfg["timeNumPoints"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        print(f'Time: {time.time() - start}')

        return self.data



    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        timeVec = data['data']['timeVec']
        percent_excited = data['data']['Exp_values']
        offsetVec = data['data']['offsetVec']

        X = timeVec
        Y = offsetVec

        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]

        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
                figNum += 1

            fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
            fig.suptitle(str(self.titlename), fontsize=16)
            ax_plot_1 = axs.imshow(
                percent_excited[i],
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
            cbar1.set_label('Excited Population', rotation=90)

            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_ylabel("Offset time (2.32/16 ns )")
            # axs.set_title(f"Beam Splitter Calibration")
            plt.title(self.titlename + ", Read: " + str(read_index))
            plt.savefig(self.iname[:-4] + "_Read_" + str(read_index) + '.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)



    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


class CurrentCalibration_GainSweep_SSMUX(ExperimentClass):
    """
    Apply FF pulses to two qubits in the middle of swap and sweep the gain on one FF pulse to get a chevron
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 I_Ground = 0, I_Excited = 1, Q_Ground = 0, Q_Excited = 1):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, progress=False, figNum = 1, plotDisp = True,
                plotSave = True):

        gainVec = np.array([int(x) for x in np.linspace(self.cfg["gainStart"],self.cfg["gainStop"], self.cfg["gainNumPoints"])])
        timeVec = np.array([int(x) for x in np.linspace(self.cfg["timeStart"],self.cfg["timeStop"], self.cfg["timeNumPoints"])])

        t_offset = self.cfg["t_offset"]


        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        Z_values = np.full((self.cfg["gainNumPoints"], self.cfg["timeNumPoints"]), np.nan)
        # self.I_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        # self.Q_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        self.rotatedIQ = np.full((self.cfg["gainNumPoints"], self.cfg["timeNumPoints"]), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': [Z_values for i in range(len(self.cfg["ro_chs"]))], 'RotatedIQ': self.rotatedIQ, 'threshold':threshold,
                        'angle': angle, 'gainVec': gainVec, 'timeVec': timeVec,
                     }
        }



        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        if np.array(self.cfg["IDataArray"]).any() != None:
            print(f'creating IDataArray')

            print(f"channel 3: {self.cfg['FF_Qubits']['3']['Gain_Pulse']}")


            self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '1']['Gain_Pulse'], 1)
            self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '2']['Gain_Pulse'], 2)
            self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '3']['Gain_Pulse'], 3)
            self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '4']['Gain_Pulse'], 4)

        print(self.cfg["IDataArray"][2])
        # self.cfg['Gains_BS'] = {qubit: 0 for qubit in self.cfg['FF_Qubits']}
        self.cfg['Gains_BS'] = np.zeros(len(self.cfg['FF_Qubits']))

        #
        # for i in range(len(self.cfg['FF_Qubits'])):
        #     plt.plot(self.cfg["IDataArray"][i], label=f'channel {i+1}')
        # plt.legend()
        # plt.title('IDataArray')
        # plt.show()

        # print(np.round(self.cfg["IDataArray"][0][:20], 4))
        # print(np.round(self.cfg["IDataArray"][1][:20], 4))
        # print(np.round(self.cfg["IDataArray"][2][:20], 4))
        # print(np.round(self.cfg["IDataArray"][3][:20], 4))

        X = timeVec
        X_step = X[1] - X[0]
        Y = gainVec
        Y_step = Y[1] - Y[0]

        start = time.time()

        fixed_qubit_index = self.cfg["qubit_BS_indices"][0]
        swept_qubit_index = self.cfg["qubit_BS_indices"][1]
        self.cfg['Gains_BS'][fixed_qubit_index] = self.cfg["fixed_gain"]
        print(f'setting {fixed_qubit_index} to {self.cfg["fixed_gain"]}')

        for i in range(self.cfg["gainNumPoints"]):
            self.cfg['Gains_BS'][swept_qubit_index] = int(gainVec[i])
            print(f'setting {swept_qubit_index} to {int(gainVec[i])}')

            print(f'index: {i}')

            if i % 5 == 1:
                self.save_data(self.data)
                # self.soc.reset_gens()

            if np.array(self.cfg["IDataArrayBS"]).any() != None:
                print(f'creating IDataArrayBS')
                self.cfg["IDataArrayBS"][0] = Compensated_Pulse(self.cfg['Gains_BS'][0],
                                                                self.cfg['FF_Qubits']['1']['Gain_Expt'], 1)
                self.cfg["IDataArrayBS"][1] = Compensated_Pulse(self.cfg['Gains_BS'][1],
                                                                self.cfg['FF_Qubits']['2']['Gain_Expt'], 2)
                self.cfg["IDataArrayBS"][2] = Compensated_Pulse(self.cfg['Gains_BS'][2],
                                                                self.cfg['FF_Qubits']['3']['Gain_Expt'], 3)
                self.cfg["IDataArrayBS"][3] = Compensated_Pulse(self.cfg['Gains_BS'][3],
                                                                self.cfg['FF_Qubits']['4']['Gain_Expt'], 4)

            # if i % 5 == 0:
            #     for l in range(len(self.cfg['FF_Qubits'])):
            #         plt.plot(self.cfg["IDataArrayBS"][l], label=f'channel {l + 1}')
            #     plt.legend()
            #     plt.title('IDataArrayBS')
            #     plt.show()

            # offset one channel from the other by t_offset (units of 1/16 clock cycles
            channel_1 = self.cfg['qubit_BS_indices'][0]
            channel_2 = self.cfg['qubit_BS_indices'][1]

            # unpadded_array_1 = self.cfg["IDataArrayBS"][channel_1]
            # unpadded_array_2 = self.cfg["IDataArrayBS"][channel_2]

            if t_offset > 0:
                # play pulse on channel 2 t_offset later than channel 1
                channel = channel_2
            else:
                # play pulse on channel 1 t_offset later than channel 2
                channel = channel_1

            previous_gain = self.cfg['FF_Qubits'][str(channel + 1)]['Gain_Expt']
            self.cfg["IDataArrayBS"][channel] = np.pad(self.cfg["IDataArrayBS"][channel], (abs(t_offset), 0),
                                                       constant_values=previous_gain)

            for j in range(self.cfg["timeNumPoints"]):



                self.cfg["t_BS"] = timeVec[j]


                for k in range(len(self.cfg["ro_chs"])):
                    prog = CurrentCalibrationProgramSS(self.soccfg, self.cfg)
                    shots_i0, shots_q0 = prog.acquire(self.soc,
                                                      load_pulses=True)
                    rotated_iq = rotate_data((shots_i0[k], shots_q0[k]), theta=angle[k])
                    excited_percentage = count_percentage(rotated_iq, threshold=threshold[k])

                    self.data['data']["Exp_values"][k][i, j] = excited_percentage

                    if k == 0:
                        Z_values[i, j] = excited_percentage

            if plotDisp:
                if i == 0:
                    ax_plot_1 = axs.imshow(
                        Z_values,
                        aspect='auto',
                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                        origin='lower',
                        interpolation='none',
                    )
                    axs.set_xlabel("Wait time (2.32/16 ns )")
                    axs.set_ylabel("FF Gain (a.u.)")
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                    cbar1.set_label('Excited Population', rotation=90)
                else:
                    ax_plot_1.set_data(Z_values)
                    ax_plot_1.autoscale()
                    cbar1.remove()
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                    cbar1.set_label('Excited Population', rotation=90)

                plt.show(block=False)
                plt.pause(0.1)
            else:
                fig.clf(True)
                plt.close(fig)

            if i == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + 5 * 2  ### time for single full row in seconds
                timeEst = (t_delta) * self.cfg["gainNumPoints"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        print(f'Time: {time.time() - start}')

        return self.data



    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        timeVec = data['data']['timeVec']
        gainVec = data['data']['gainVec']
        percent_excited = data['data']['Exp_values']

        X = timeVec
        Y = gainVec

        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]

        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
                figNum += 1

            fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
            fig.suptitle(str(self.titlename), fontsize=16)
            ax_plot_1 = axs.imshow(
                percent_excited[i],
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
            cbar1.set_label('Excited Population', rotation=90)

            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_ylabel("FF Gain (a.u.)")
            axs.set_title(f"Beam Splitter Calibration")
            plt.title(self.titlename + ", Read: " + str(read_index))
            plt.savefig(self.iname[:-4] + "_Read_" + str(read_index) + '.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)



    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])



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

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 2):
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

Qubit2_[0] *= 1.3
Qubit2_[1] *= 1.2
Qubit2_[2] *= 1.2
Qubit2_[3] *= 1.2

Qubit4_[0] *= 1.3
Qubit4_[1] *= 1.2
Qubit4_[2] *= 1.2
Qubit4_[3] *= 1.2
# Qubit4_[0] *= 1.2



v_awg_Q1 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit4_)[1]



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
    Comp_Step_Gain[Comp_Step_Gain > 32000] = 32000
    Comp_Step_Gain[Comp_Step_Gain < -32000] = -32000

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




