##### this experiment performs two-tone qubit spec at a single amplitude many times to see whether the transition moves with time

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from STFU.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime

import matplotlib.dates as mdates



class TwoQubitFluxDrift(ExperimentClass):
    """
    sweep across qubit frequencies while doing amplitude rabi to find a rabi power blob
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp = True, figNum = 1):
        ### define frequencies to sweep over
        expt_cfg = {
            ### qubit 1 parameters
            "qubit1_freq_start": self.cfg["qubit1_freq_start"],
            "qubit1_freq_stop": self.cfg["qubit1_freq_stop"],
            "SpecNumPoints1": self.cfg["SpecNumPoints1"],  ### number of points
            "qubit1_gain": self.cfg["qubit1_gain"],
            ### qubit 2 parameters
            "qubit2_freq_start": self.cfg["qubit2_freq_start"],
            "qubit2_freq_stop": self.cfg["qubit2_freq_stop"],
            "SpecNumPoints2": self.cfg["SpecNumPoints2"],  ### number of points
            "qubit2_gain": self.cfg["qubit2_gain"],
            ### time paremeters
            "delay": self.cfg["delay"],
            "repetitions": self.cfg["repetitions"], #### number of times to perform measurement
        }

        ### define qubit frequency array
        self.qubit1_freqs = np.linspace(expt_cfg["qubit1_freq_start"], expt_cfg["qubit1_freq_stop"],
                                        expt_cfg["SpecNumPoints1"])

        self.qubit2_freqs = np.linspace(expt_cfg["qubit2_freq_start"], expt_cfg["qubit2_freq_stop"],
                                        expt_cfg["SpecNumPoints2"])

        self.time_reps = np.arange(0, expt_cfg["repetitions"])

        self.time_stamps = []

        #### define the plotting X and Y and data holders Z
        X1 = self.qubit1_freqs/1e3 ### put into units of GHz
        X1_step = X1[1] - X1[0]
        Y = self.time_reps
        Y_step = 1
        Z1_avgi = np.full((len(Y), len(X1)), np.nan)
        Z1_avgq = np.full((len(Y), len(X1)), np.nan)
        Z1_amp = np.full((len(Y), len(X1)), np.nan)
        Z1_phase = np.full((len(Y), len(X1)), np.nan)

        X2= self.qubit2_freqs/1e3 ### put into units of GHz
        X2_step = X2[1] - X2[0]
        Z2_avgi = np.full((len(Y), len(X2)), np.nan)
        Z2_avgq = np.full((len(Y), len(X2)), np.nan)
        Z2_amp = np.full((len(Y), len(X2)), np.nan)
        Z2_phase = np.full((len(Y), len(X2)), np.nan)

        ### create array for storing the data
        self.data= {
            'config': self.cfg,
            'data': {
                    'avgi_mat1': Z1_avgi, 'avgq_mat1': Z1_avgq, 'qubit1_freqs':self.qubit1_freqs,
                    'avgi_mat2': Z2_avgi, 'avgq_mat2': Z2_avgq, 'qubit2_freqs': self.qubit2_freqs,
                    'time_reps':self.time_reps, 'time_stamps': self.time_stamps,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(4,2, figsize = (12,12), num = figNum)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over repetitions
        for idx in range(len(Y)):
            ### store the time of the measurement
            self.time_stamps.append(time.time())
            #### set new qubit frequency and aquire data
            self.cfg["qubit1_freq"] = self.qubit1_freqs[0]
            prog = LoopbackQubit1Spec(self.soccfg, self.cfg)

            x_pts, avgi1, avgq1 = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False, debug=False)

            self.cfg["qubit2_freq"] = self.qubit2_freqs[0]
            prog = LoopbackQubit2Spec(self.soccfg, self.cfg)

            x_pts, avgi2, avgq2 = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                               readouts_per_experiment=1, save_experiments=None,
                                               start_src="internal", progress=False, debug=False)

            ###### qubit 1 values
            Z1_avgi[idx, :] = avgi1[0][0]
            self.data['data']['avgi_mat1'][idx, :] = avgi1[0][0]

            Z1_avgq[idx, :] = avgq1[0][0]
            self.data['data']['avgq_mat1'][idx, :] = avgq1[0][0]

            sig1 = avgi1[0][0] + 1j * avgq1[0][0]
            Z1_amp[idx, :] = np.abs(sig1)
            Z1_phase[idx, :] = np.angle(sig1, deg=True)

            ##### qubit 2 values
            Z2_avgi[idx, :] = avgi2[0][0]
            self.data['data']['avgi_mat2'][idx, :] = avgi2[0][0]

            Z2_avgq[idx, :] = avgq2[0][0]
            self.data['data']['avgq_mat2'][idx, :] = avgq2[0][0]

            sig2 = avgi2[0][0] + 1j * avgq2[0][0]
            Z2_amp[idx, :] = np.abs(sig2)
            Z2_phase[idx, :] = np.angle(sig2, deg=True)

            ### save the time stamp data
            self.data['data']['time_stamps'] = self.time_stamps


            ####### plotting data

            ###### plot the I for both qubits
            if idx == 0:  #### if first sweep add a colorbar
                #### plotting
                ax_plot_00 = axs[0, 0].imshow(
                    Z1_avgi,
                    aspect='auto',
                    extent=[X1[0] - X1_step / 2, X1[-1] + X1_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )

                cbar00 = fig.colorbar(ax_plot_00, ax=axs[0, 0], extend='both')
                cbar00.set_label('a.u.', rotation=90)
            else:
                ax_plot_00.set_data(Z1_avgi)
                ax_plot_00.data = Z1_avgi
                ax_plot_00.set_clim(vmin=np.nanmin(Z1_avgi))
                ax_plot_00.set_clim(vmax=np.nanmax(Z1_avgi))
                cbar00.remove()
                cbar00 = fig.colorbar(ax_plot_00, ax=axs[0, 0], extend='both')
                cbar00.set_label('a.u.', rotation=90)

            axs[0, 0].set_ylabel("repetition number")
            axs[0, 0].set_xlabel("qubit 1 frequency (GHz)")
            axs[0, 0].set_title("spec sweep: avgi")

            ####### qubit 2 I
            if idx == 0:  #### if first sweep add a colorbar
                #### plotting
                ax_plot_01 = axs[0, 1].imshow(
                    Z2_avgi,
                    aspect='auto',
                    extent=[X2[0] - X2_step / 2, X2[-1] + X2_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )

                cbar01 = fig.colorbar(ax_plot_01, ax=axs[0, 1], extend='both')
                cbar01.set_label('a.u.', rotation=90)
            else:
                ax_plot_01.set_data(Z2_avgi)
                ax_plot_01.data = Z2_avgi
                ax_plot_01.set_clim(vmin=np.nanmin(Z2_avgi))
                ax_plot_01.set_clim(vmax=np.nanmax(Z2_avgi))
                cbar01.remove()
                cbar01 = fig.colorbar(ax_plot_01, ax=axs[0, 1], extend='both')
                cbar01.set_label('a.u.', rotation=90)

            axs[0, 1].set_ylabel("repetition number")
            axs[0, 1].set_xlabel("qubit 2 frequency (GHz)")
            axs[0, 1].set_title("spec sweep: avgi")

            #### plot the q for qubit 1
            if idx == 0:  #### if first sweep add a colorbar
                #### plot the q
                ax_plot_10 = axs[1, 0].imshow(
                    Z1_avgq,
                    aspect='auto',
                    extent=[X1[0] - X1_step / 2, X1[-1] + X1_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar10 = fig.colorbar(ax_plot_10, ax=axs[1, 0], extend='both')
                cbar10.set_label('a.u.', rotation=90)
            else:
                ax_plot_10.set_data(Z1_avgq)
                ax_plot_10.set_clim(vmin=np.nanmin(Z1_avgq))
                ax_plot_10.set_clim(vmax=np.nanmax(Z1_avgq))
                cbar10.remove()
                cbar10 = fig.colorbar(ax_plot_10, ax=axs[1, 0], extend='both')
                cbar10.set_label('a.u.', rotation=90)

            axs[1, 0].set_ylabel("repetition number")
            axs[1, 0].set_xlabel("qubit 1 frequency (GHz)")
            axs[1, 0].set_title("spec sweep: avgq")

            #### plot the q for qubit 2
            if idx == 0:  #### if first sweep add a colorbar
                #### plot the q
                ax_plot_11 = axs[1, 1].imshow(
                    Z2_avgq,
                    aspect='auto',
                    extent=[X2[0] - X2_step / 2, X2[-1] + X2_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar11 = fig.colorbar(ax_plot_11, ax=axs[1, 1], extend='both')
                cbar11.set_label('a.u.', rotation=90)
            else:
                ax_plot_11.set_data(Z2_avgq)
                ax_plot_11.set_clim(vmin=np.nanmin(Z2_avgq))
                ax_plot_11.set_clim(vmax=np.nanmax(Z2_avgq))
                cbar11.remove()
                cbar11 = fig.colorbar(ax_plot_11, ax=axs[1, 1], extend='both')
                cbar11.set_label('a.u.', rotation=90)

            axs[1, 1].set_ylabel("repetition number")
            axs[1, 1].set_xlabel("qubit 2 frequency (GHz)")
            axs[1, 1].set_title("spec sweep: avgq")

            #### plot the amp for qubit 1
            if idx == 0:  #### if first sweep add a colorbar
                ax_plot_20 = axs[2, 0].imshow(
                    Z1_amp,
                    aspect='auto',
                    extent=[X1[0] - X1_step / 2, X1[-1] + X1_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar20 = fig.colorbar(ax_plot_20, ax=axs[2, 0], extend='both')
                cbar20.set_label('a.u.', rotation=90)
            else:
                ax_plot_20.set_data(Z1_amp)
                ax_plot_20.set_clim(vmin=np.nanmin(Z1_amp))
                ax_plot_20.set_clim(vmax=np.nanmax(Z1_amp))
                cbar20.remove()
                cbar20 = fig.colorbar(ax_plot_20, ax=axs[2, 0], extend='both')
                cbar20.set_label('a.u.', rotation=90)

            axs[2, 0].set_ylabel("repetition number")
            axs[2, 0].set_xlabel("qubit 1 frequency (GHz)")
            axs[2, 0].set_title("spec sweep: amp")

            #### plot the amp for qubit 2
            if idx == 0:  #### if first sweep add a colorbar
                ax_plot_21 = axs[2, 1].imshow(
                    Z2_amp,
                    aspect='auto',
                    extent=[X2[0] - X2_step / 2, X2[-1] + X2_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar21 = fig.colorbar(ax_plot_21, ax=axs[2, 1], extend='both')
                cbar21.set_label('a.u.', rotation=90)
            else:
                ax_plot_21.set_data(Z2_amp)
                ax_plot_21.set_clim(vmin=np.nanmin(Z2_amp))
                ax_plot_21.set_clim(vmax=np.nanmax(Z2_amp))
                cbar21.remove()
                cbar21 = fig.colorbar(ax_plot_21, ax=axs[2, 1], extend='both')
                cbar21.set_label('a.u.', rotation=90)

            axs[2, 1].set_ylabel("repetition number")
            axs[2, 1].set_xlabel("qubit 2 frequency (GHz)")
            axs[2, 1].set_title("spec sweep: amp")

            #### plot the phase for qubit 1
            if idx == 0:  #### if first sweep add a colorbar
                ax_plot_30 = axs[3, 0].imshow(
                    Z1_phase,
                    aspect='auto',
                    extent=[X1[0] - X1_step / 2, X1[-1] + X1_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar30 = fig.colorbar(ax_plot_30, ax=axs[3, 0], extend='both')
                cbar30.set_label('a.u.', rotation=90)
            else:
                ax_plot_30.set_data(Z1_phase)
                ax_plot_30.set_clim(vmin=np.nanmin(Z1_phase))
                ax_plot_30.set_clim(vmax=np.nanmax(Z1_phase))
                cbar30.remove()
                cbar30 = fig.colorbar(ax_plot_30, ax=axs[3, 0], extend='both')
                cbar30.set_label('a.u.', rotation=90)

            axs[3, 0].set_ylabel("repetition number")
            axs[3, 0].set_xlabel("qubit 1 frequency (GHz)")
            axs[3, 0].set_title("spec sweep: phase")

            #### plot the phase for qubit 2
            if idx == 0:  #### if first sweep add a colorbar
                ax_plot_31 = axs[3, 1].imshow(
                    Z2_phase,
                    aspect='auto',
                    extent=[X2[0] - X2_step / 2, X2[-1] + X2_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar31 = fig.colorbar(ax_plot_31, ax=axs[3, 1], extend='both')
                cbar31.set_label('a.u.', rotation=90)
            else:
                ax_plot_31.set_data(Z2_phase)
                ax_plot_31.set_clim(vmin=np.nanmin(Z2_phase))
                ax_plot_31.set_clim(vmax=np.nanmax(Z2_phase))
                cbar31.remove()
                cbar31 = fig.colorbar(ax_plot_31, ax=axs[3, 1], extend='both')
                cbar31.set_label('a.u.', rotation=90)

            axs[3, 1].set_ylabel("repetition number")
            axs[3, 1].set_xlabel("qubit 2 frequency (GHz)")
            axs[3, 1].set_title("spec sweep: phase")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if idx == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  ### time for single full row in seconds
                timeEst = (t_delta + self.cfg["delay"]) * len(Y)
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round( (t_delta + self.cfg["delay"] )/ 60 , 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

            plt.tight_layout()

            #self.save_data(self.data)
            time.sleep(self.cfg["delay"])
        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        ##### plot the data with date time stamps

        #### plot the full data set
        #### freqs are in MHz, convert to GHz
        freqs1 = self.qubit1_freqs/1e3
        freqs2 = self.qubit2_freqs / 1e3
        dates = self.time_stamps

        #### convert date data from string to datetime object
        date_arr = []
        for idx in range(len(dates)):
            date_arr.append(datetime.datetime.fromtimestamp(dates[idx]))

        fig1, axs1 = plt.subplots(1,2, figsize = (12,12))

        x1_lims = [freqs1[0], freqs1[-1]]
        x2_lims = [freqs2[0], freqs2[-1]]
        y_lims = [mdates.date2num(date_arr[0]), mdates.date2num(date_arr[-1])]

        #### plotting for qubit 1
        axs1[0].imshow(
            Z1_avgi,
            extent = [x1_lims[0], x1_lims[1],  y_lims[0], y_lims[1] ],
            aspect = 'auto',
            origin='lower',
            interpolation='none',
        )
        #### set up the date formating for the y axis
        axs1[0].yaxis_date()
        date_format = mdates.DateFormatter('%y/%m/%d %H:%M')
        axs1[0].yaxis.set_major_formatter(date_format)
        plt.tight_layout()

        axs1[0].set_xlabel('Frequency (GHz)')
        axs1[0].set_ylabel('Date time')

        ##### plotting the amplitude for qubit 2
        axs1[1].imshow(
            Z2_avgi,
            extent=[x2_lims[0], x2_lims[1], y_lims[0], y_lims[1]],
            aspect='auto',
            origin='lower',
            interpolation='none',
        )
        #### set up the date formating for the y axis
        axs1[1].yaxis_date()
        date_format = mdates.DateFormatter('%y/%m/%d %H:%M')
        axs1[1].yaxis.set_major_formatter(date_format)
        plt.tight_layout()

        axs1[1].set_xlabel('Frequency (GHz)')
        axs1[1].set_ylabel('Date time')

        plt.tight_layout()

        ### save the figure and return the data
        data = self.data
        plt.savefig(self.iname, dpi = 600)  #### save the figure

        return data

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


class LoopbackQubit1Spec(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters
        self.cfg["start"] = self.freq2reg(self.cfg["qubit1_freq_start"], gen_ch=self.cfg["qubit_ch"])
        # We are also given freq_stop and SpecNumPoints, use these to compute freq_step
        self.cfg["step"] = self.freq2reg(
            (self.cfg["qubit1_freq_stop"] - self.cfg["qubit1_freq_start"]) / (self.cfg["SpecNumPoints1"] - 1),
            gen_ch=self.cfg["qubit_ch"])
        self.cfg["expts"] = self.cfg["SpecNumPoints1"]
        # self.cfg["reps"] = self.cfg["averages"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.q_freq = self.sreg(cfg["qubit_ch"], "freq")  # get freq register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read1_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read1_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read1_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit1_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read1_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read1_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read1_length"]))

        if cfg["qubit1_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma1"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma1"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit1_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit1_gain"],
                                     waveform="qubit")

        elif cfg["qubit1_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma1"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma1"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit1_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length1"]))

        elif cfg["qubit1_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=cfg["start"], phase=0,
                                     gain=cfg["qubit1_gain"],
                                     length=self.us2cycles(self.cfg["qubit1_length"], gen_ch=cfg["qubit_ch"]),
                                     mode="periodic")
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read1_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read1_pulse_gain"], mode = 'periodic',
                                     length=self.us2cycles(self.cfg["read1_length"]))

        else:
            print("define pi or flat top pulse")

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):

        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        self.sync_all(self.us2cycles(0.05)) # align channels and wait 50ns

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.q_freq, self.q_freq, '+', self.cfg["step"]) # update freq of the Gaussian pi pulse



class LoopbackQubit2Spec(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters
        self.cfg["start"] = self.freq2reg(self.cfg["qubit2_freq_start"], gen_ch=self.cfg["qubit_ch"])
        # We are also given freq_stop and SpecNumPoints, use these to compute freq_step
        self.cfg["step"] = self.freq2reg(
            (self.cfg["qubit2_freq_stop"] - self.cfg["qubit2_freq_start"]) / (self.cfg["SpecNumPoints2"] - 1),
            gen_ch=self.cfg["qubit_ch"])
        self.cfg["expts"] = self.cfg["SpecNumPoints2"]
        # self.cfg["reps"] = self.cfg["averages"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.q_freq = self.sreg(cfg["qubit_ch"], "freq")  # get freq register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read2_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read2_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read2_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit2_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read2_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read2_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read2_length"]))

        if cfg["qubit2_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma2"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma2"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit2_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit2_gain"],
                                     waveform="qubit")

        elif cfg["qubit2_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma1"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma1"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit1_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length1"]))

        elif cfg["qubit2_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=cfg["start"], phase=0,
                                     gain=cfg["qubit2_gain"],
                                     length=self.us2cycles(self.cfg["qubit2_length"], gen_ch=cfg["qubit_ch"]),
                                     mode="periodic")
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read1_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read2_pulse_gain"], mode = 'periodic',
                                     length=self.us2cycles(self.cfg["read2_length"]))

        else:
            print("define pi or flat top pulse")

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):

        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        self.sync_all(self.us2cycles(0.05)) # align channels and wait 50ns

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.q_freq, self.q_freq, '+', self.cfg["step"]) # update freq of the Gaussian pi pulse

