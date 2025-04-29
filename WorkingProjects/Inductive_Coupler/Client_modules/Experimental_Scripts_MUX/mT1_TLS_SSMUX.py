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
from scipy.optimize import curve_fit


class T1_TLS_Program_SS(AveragerProgram):
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
            if i == 0:
                time = self.us2cycles(1)
            else:
                time = 'auto'
            # print(freq_, gain_, time)
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                 gain=gain_,
                                 waveform="qubit", t=time)
        self.FFPulses(self.FFExpts, self.cfg["delay_length"])

        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFExpts, self.cfg["delay_length"])

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

class T1_TLS_SS(ExperimentClass):
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

        self.wait_times = self.cfg["wait_times"]
        self.gain_pts = gainVec
        Z_values = np.full((len(self.wait_times), self.cfg["gainNumPoints"]), np.nan)

        if len(self.wait_times) == 1:
            X = self.gain_pts
            Y = self.wait_times
            X_step = X[1] - X[0]
            Z_fid = np.full(len(X), np.nan)
            Z_overlap = np.full(len(X), np.nan)

        elif self.cfg["gainNumPoints"] == 1:
            Y = self.gain_pts
            X = self.wait_times
            X_step = X[1] - X[0]
            Z_fid = np.full(len(X), np.nan)
            Z_overlap = np.full(len(X), np.nan)
        ####create arrays for storing the data
        else:
            X = self.gain_pts
            X_step = X[1] - X[0]
            Y = self.wait_times
            Y_step = Y[1] - Y[0]
            Z_fid = np.full((len(Y), len(X)), np.nan)
            Z_overlap = np.full((len(Y), len(X)), np.nan)


        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': Z_values, 'threshold':threshold,
                        'angle': angle, 'wait_time': self.wait_times,
                        'gainVec': gainVec,
                     }
        }

        tpts = self.wait_times

        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        start = time.time()
        for i_del in range(len(tpts)):
            # if i_del % 5 == 1:
            self.save_data(self.data)
                # self.soc.reset_gens()
            self.cfg['delay_length'] = tpts[i_del]

            start = time.time()
            for i_gain, gain_ in enumerate(gainVec):
                self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Expt'] = int(gain_)
                # print
                all_percentage = []
                for r_num in range(self.cfg['repeated_nums']):
                    prog = T1_TLS_Program_SS(self.soccfg, self.cfg)
                    shots_i0, shots_q0 = prog.acquire(self.soc,
                                                      load_pulses=True)
                    rotated_iq = rotate_data((shots_i0[0], shots_q0[0]), theta=angle)
                    excited_percentage = count_percentage(rotated_iq, threshold = threshold)
                    all_percentage.append(excited_percentage[0])

                Z_values[i_del, i_gain] = np.mean(all_percentage)
                self.data['data']['Exp_values'][i_del, i_gain] = np.mean(all_percentage)

                if i_del == 0 and i_gain == 0:
                    if len(self.wait_times) == 1:
                        ax_plot_0, = axs.plot(self.gain_pts,
                                              Z_values[0, :] * 100, 'o-', color='black'
                                              )
                        step_ = self.gain_pts[1] - self.gain_pts[0]
                        axs.set_xlim(self.gain_pts[0] - step_, self.gain_pts[-1] + step_)
                    elif self.cfg["gainNumPoints"] == 1:
                        ax_plot_0, = axs.plot(self.wait_times,
                                              Z_values[:, 0] * 100, 'o-', color='black'
                                              )
                        step_ = self.wait_times[1] - self.wait_times[0]
                        axs.set_xlim(self.wait_times[0] - step_, self.wait_times[-1] + step_)
                    else:
                        ax_plot_0 = axs.imshow(
                            Z_values * 100,
                            aspect='auto',
                            extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                    Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                            origin='lower',
                            interpolation='none',
                        )
                        cbar0 = fig.colorbar(ax_plot_0, ax=axs, extend='both')
                        cbar0.set_label('Qubit Population', rotation=90)
                else:
                    if len(self.wait_times) == 1:
                        ax_plot_0.set_data(self.gain_pts, Z_values * 100)
                        y_min, y_max = min(Z_values[0] * 100), max(Z_values[0] * 100)
                        axs.set_ylim(y_min - 5, y_max + 5)
                        # axs.relim()  # Recalculate the limits based on the new data
                        axs.autoscale_view()  # Autoscale the view to fit the new data
                        axs.grid()

                    elif self.cfg["gainNumPoints"] == 1:
                        ax_plot_0.set_data(self.wait_times, Z_values * 100)
                        y_min, y_max = min(Z_values[:, 0] * 100), max(Z_values[:, 0] * 100)
                        axs.set_ylim(0, y_max + 5)
                        # axs.relim()  # Recalculate the limits based on the new data
                        axs.autoscale_view()  # Autoscale the view to fit the new data
                        axs.grid()
                    else:
                        ax_plot_0.set_data(Z_values * 100)
                        ax_plot_0.autoscale()
                        cbar0.remove()
                        cbar0 = fig.colorbar(ax_plot_0, ax=axs, extend='both')
                        cbar0.set_label('Qubit Population', rotation=90)

                if len(self.wait_times) == 1:
                    axs.grid()
                    axs.set_ylabel('Qubit Population')
                    axs.set_xlabel("FF Gain (Dac units)")
                    axs.set_title('')
                elif self.cfg["gainNumPoints"] == 1:
                    axs.grid()
                    axs.set_ylabel("Qubit Population")
                    axs.set_xlabel("Delay time (us)")
                    axs.set_title('')
                else:
                    axs.set_ylabel("Delay time (us)")
                    axs.set_xlabel("FF Gain (Dac units)")
                    axs.set_title('')

                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)

            if i_del == 0 and i_gain == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  ### time for single full row in seconds
                timeEst = t_delta * self.cfg["gainNumPoints"] * len(self.wait_times)  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print(f'Time: {time.time() - start}')
        self.save_data(self.data)
        plt.savefig(self.iname)



        if plotDisp:
            if self.cfg['gainNumPoints'] == 1:
                def _expFit(x, a, T1, c):
                    return a * np.exp(-1 * x / T1) + c

                Z_values_only = Z_values[:, 0] * 100

                a_guess = Z_values_only[0] - Z_values_only[-1]
                b_guess = Z_values_only[-1]
                approx_t1_val = a_guess / 2.6 + b_guess
                index_t1_guess = np.argmin(np.abs(Z_values_only - approx_t1_val))
                t1_guess = self.wait_times[index_t1_guess]
                guess = [a_guess, t1_guess, b_guess]
                pOpt, pCov = curve_fit(_expFit,  self.wait_times, Z_values_only, p0=guess)
                perr = np.sqrt(np.diag(pCov))

                T1_fit = _expFit(self.wait_times, *pOpt)

                T1_est = pOpt[1]
                T1_err = perr[1]
                plt.plot(self.wait_times, T1_fit, '-', label="fit", color='red')
                plt.ylabel("Qubit Population")
                plt.xlabel("Wait time (us)")
                plt.title(f'T1: {T1_est:.2f} us $\pm$ {T1_err:.2f}')
                plt.savefig(self.iname)

            plt.show(block=True)

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['wait_times']
        percent_excited = data['data']['Exp_values']
        gainVec = data['data']['gainVec']

        X = x_pts
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

            axs.set_ylabel("FF Gain (a.u.)")
            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_title("Oscillations")
            plt.title(self.titlename + ", Read: " + str(read_index))
            plt.savefig(self.iname[:-4] + "_Read_" + str(read_index) + '.png')
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