##### this experiment performs two-tone qubit spec at a single amplitude many times to see whether the transition moves with time

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime

import matplotlib.dates as mdates

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecSlice_SaraTest import \
    LoopbackProgramSpecSlice


class QubitSpecRepeat(ExperimentClass):
    """
    sweep across qubit frequencies while doing amplitude rabi to find a rabi power blob
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp = True, figNum = 1):
        ### define frequencies to sweep over
        expt_cfg = {
            ### qubit parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
            "qubit_gain": self.cfg["qubit_gain"],
            ### time paremeters

            "delay": self.cfg["delay"],
            "repetitions": self.cfg["repetitions"], #### number of times to perform measurement
        }

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.time_reps = np.arange(0, expt_cfg["repetitions"])

        self.time_stamps = []

        #### define the plotting X and Y and data holders Z
        X = self.qubit_freqs/1e3 ### put into units of GHz
        X_step = X[1] - X[0]
        Y = self.time_reps
        Y_step = 1
        Z_avgi = np.full((len(Y), len(X)), np.nan)
        Z_avgq = np.full((len(Y), len(X)), np.nan)
        Z_amp = np.full((len(Y), len(X)), np.nan)
        Z_phase = np.full((len(Y), len(X)), np.nan)
        ### create array for storing the data
        self.data= {
            'config': self.cfg,
            'data': {'avgi_mat': Z_avgi, 'avgq_mat': Z_avgq,
                     'qubit_freqs':self.qubit_freqs, 'time_reps':self.time_reps,
                     'time_stamps': self.time_stamps,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(4,1, figsize = (12,12), num = figNum)

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
            self.cfg["qubit_freq"] = self.qubit_freqs[0]
            #prog = LoopbackProgramTwoToneFreqSweep(self.soccfg, self.cfg)
            self.cfg["start"] = expt_cfg["qubit_freq_start"]
            self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / expt_cfg["SpecNumPoints"]
            self.cfg["expts"] = expt_cfg["SpecNumPoints"]
            self.cfg["use_switch"] = False
            prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)

            x_pts, avgi, avgq = prog.acquire(self.soc, angle=None, load_pulses=True, threshold=None,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False)#, debug=False)
            Z_avgi[idx, :] = avgi[0][0]
            self.data['data']['avgi_mat'][idx, :] = avgi[0][0]

            Z_avgq[idx, :] = avgq[0][0]
            self.data['data']['avgq_mat'][idx, :] = avgq[0][0]

            sig = avgi[0][0] + 1j * avgq[0][0]
            Z_amp[idx, :] = np.abs(sig)
            Z_phase[idx, :] = np.angle(sig, deg=True)

            ### save the time stamp data
            self.data['data']['time_stamps'] = self.time_stamps


            ####### plotting data
            if idx == 0:  #### if first sweep add a colorbar
                #### plotting
                ax_plot_0 = axs[0].imshow(
                    Z_avgi,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )

                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)
            else:
                ax_plot_0.set_data(Z_avgi)
                ax_plot_0.data = Z_avgi
                ax_plot_0.set_clim(vmin=np.nanmin(Z_avgi))
                ax_plot_0.set_clim(vmax=np.nanmax(Z_avgi))
                cbar0.remove()
                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)

            axs[0].set_ylabel("repetition number")
            axs[0].set_xlabel("qubit frequency (GHz)")
            axs[0].set_title("Two-tone spec sweep: avgi")

            #### plot the q
            if idx == 0:  #### if first sweep add a colorbar
                #### plot the q
                ax_plot_1 = axs[1].imshow(
                    Z_avgq,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_avgq)
                ax_plot_1.set_clim(vmin=np.nanmin(Z_avgq))
                ax_plot_1.set_clim(vmax=np.nanmax(Z_avgq))
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[1].set_ylabel("repetition number")
            axs[1].set_xlabel("qubit frequency (GHz)")
            axs[1].set_title("Two-tone spec swee: avgq")

            #### plot the amp

            if idx == 0:  #### if first sweep add a colorbar
                ax_plot_2 = axs[2].imshow(
                    Z_amp,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
                cbar2.set_label('a.u.', rotation=90)
            else:
                ax_plot_2.set_data(Z_amp)
                ax_plot_2.set_clim(vmin=np.nanmin(Z_amp))
                ax_plot_2.set_clim(vmax=np.nanmax(Z_amp))
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
                cbar2.set_label('a.u.', rotation=90)

            axs[2].set_ylabel("repetition number")
            axs[2].set_xlabel("qubit frequency (GHz)")
            axs[2].set_title("Two-tone spec swee: amp")

            #### plot the phase
            if idx == 0:  #### if first sweep add a colorbar
                ax_plot_3 = axs[3].imshow(
                    Z_phase,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[3], extend='both')
                cbar3.set_label('a.u.', rotation=90)
            else:
                ax_plot_3.set_data(Z_phase)
                ax_plot_3.set_clim(vmin=np.nanmin(Z_phase))
                ax_plot_3.set_clim(vmax=np.nanmax(Z_phase))
                cbar3.remove()
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[3], extend='both')
                cbar3.set_label('a.u.', rotation=90)

            axs[3].set_ylabel("repetition number")
            axs[3].set_xlabel("qubit frequency (GHz)")
            axs[3].set_title("Two-tone spec sweep: phase")

            if plotDisp:
                plt.show(block=False)
                plt.pause(5)

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
        freqs = self.qubit_freqs/1e3
        dates = self.time_stamps

        #### convert date data from string to datetime object
        date_arr = []
        for idx in range(len(dates)):
            date_arr.append(datetime.datetime.fromtimestamp(dates[idx]))

        fig1, axs1 = plt.subplots(1,1, figsize = (12,12))

        x_lims = [freqs[0], freqs[-1]]
        y_lims = [mdates.date2num(date_arr[0]), mdates.date2num(date_arr[-1])]

        axs1.imshow(
            Z_amp,
            extent = [x_lims[0], x_lims[1],  y_lims[0], y_lims[1] ],
            aspect = 'auto',
            origin='lower',
            interpolation='none',
        )
        #### set up the date formating for the y axis
        axs1.yaxis_date()
        date_format = mdates.DateFormatter('%y/%m/%d %H:%M')
        axs1.yaxis.set_major_formatter(date_format)
        plt.tight_layout()

        axs1.set_xlabel('Frequency (GHz)')
        axs1.set_ylabel('Date time')

        plt.tight_layout()

        ### save the figure and return the data
        data = self.data
        plt.savefig(self.iname, dpi = 600)  #### save the figure

        return data

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


class LoopbackProgramTwoToneFreqSweep(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters
        self.cfg["start"] = self.freq2reg(self.cfg["qubit_freq_start"], gen_ch=self.cfg["qubit_ch"])
        # We are also given freq_stop and SpecNumPoints, use these to compute freq_step
        self.cfg["step"] = self.freq2reg(
            (self.cfg["qubit_freq_stop"] - self.cfg["qubit_freq_start"]) / (self.cfg["SpecNumPoints"] - 1),
            gen_ch=self.cfg["qubit_ch"])
        self.cfg["expts"] = self.cfg["SpecNumPoints"]
        # self.cfg["reps"] = self.cfg["averages"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.q_freq = self.sreg(cfg["qubit_ch"], "freq")  # get freq register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=cfg["start"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))

        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=cfg["start"], phase=0,
                                     gain=cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                     mode="periodic")
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"], mode = 'periodic',
                                     length=self.us2cycles(self.cfg["read_length"]))

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

