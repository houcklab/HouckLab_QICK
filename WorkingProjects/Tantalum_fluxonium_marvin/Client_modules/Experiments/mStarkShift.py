# This code performs qubit spectroscopy while sweeping cavity power to see the AC Stark shift on the qubit.
# This allows calibration of photon number in the readout resonator. Make sure to use qubit powers sufficiently low
# to not populate the qubit significantly.

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_Enhance import Transmission_Enhance
from tqdm.notebook import tqdm
import time
import datetime
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

class LoopbackProgramStarkSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):

        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], ro_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0]) # conver f_res to dac register value
        self.f_res = f_res
        self.f_start = self.freq2reg(self.cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels

        #### define the qubit pulse depending on the pulse type
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
        elif self.cfg["qubit_pulse_style"] == "const":
            if self.cfg["mode_periodic"] == True:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"]), mode="periodic")
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"])
            else:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"]))
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"])

        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=0, gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = (self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
                                      + self.us2cycles(self.cfg["flat_top_length"], gen_ch=cfg["qubit_ch"]))

        # Adding the resonator pulse
        if self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["cavity_pulse_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["res_ch"]), mode="periodic")
        elif not self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["cavity_pulse_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["res_ch"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["res_ch"]) + self.us2cycles(self.cfg["pop_pulse_length"]) # switch is open while populating pulse is playing

        # self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
        #                                       gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.sync_all(self.us2cycles(1))

    def body(self):

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # Configure the cavity pulse for populating the cavity
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                 gain=self.cfg["cavity_pulse_gain"],
                                 length=self.us2cycles(self.cfg["pop_pulse_length"], gen_ch=self.cfg["res_ch"]))

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        #if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch

        if self.cfg['simultaneous']:
            self.pulse(ch=self.cfg["res_ch"])   # Play a cavity tone
            self.pulse(ch=self.cfg["qubit_ch"])  # Play a qubit tone
            self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns
        else:
            self.pulse(ch=self.cfg["res_ch"])  # Play a cavity tone
            self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns
            self.pulse(ch=self.cfg["qubit_ch"])  # Play a qubit tone

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # Configure the cavity pulse for readout
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]))

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


class StarkShift(ExperimentClass):
    """
    to write
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)


    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        expt_cfg = {
            ### define the gainuator parameters
            "trans_gain_start": self.cfg["trans_gain_start"],
            "trans_gain_stop": self.cfg["trans_gain_stop"],
            "trans_gain_num": self.cfg["trans_gain_num"],
            #spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "SpecNumPoints": self.cfg["SpecNumPoints"],
        }

        if self.cfg["units"] == "DAC":
            gainVec = np.linspace(expt_cfg["trans_gain_start"], expt_cfg["trans_gain_stop"], expt_cfg["trans_gain_num"],
                                   dtype=int) ### for current simplicity set it to an int
        else:
            gainVec = np.logspace(np.log10(expt_cfg["trans_gain_start"]), np.log10(expt_cfg["trans_gain_stop"]), num= expt_cfg["trans_gain_num"],
                                   dtype = int)

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 2, figsize = (16,10), num = figNum)

        ### create the frequency array
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])

        Y = gainVec
        print(gainVec)
        Y_step = Y[1] - Y[0]

        self.spec_Imat = np.zeros((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]))
        self.data = {
            'config': self.cfg,
            'data': {'gain_fpts': gainVec,
                     'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                     }
        }

        X_spec = self.spec_fpts / 1e3
        X_spec_step = X_spec[1] - X_spec[0]

        Z_specamp = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specphase = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specI = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_specQ = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        # Creating the extents of the plot
        if self.cfg['units'] == 'DAC':
            extents = [X_spec[0] - X_spec_step / 2, X_spec[-1] + X_spec_step / 2, Y[0] - Y_step / 2, Y[-1] + Y_step / 2]
        else:
            print(Y[-1]**2/Y[-2])
            extents = [X_spec[0] - X_spec_step / 2, X_spec[-1] + X_spec_step / 2, 10*np.log10(Y[0]**2/Y[1]), 10*np.log10(Y[-1]**2/Y[-2])]

        # Creating an entry in the dictionary for cavity pulse gain
        self.cfg["cavity_pulse_gain"] = 0

        # Looping around all the cavity pulse gains
        for i in range(expt_cfg["trans_gain_num"]):
            self.cfg["cavity_pulse_gain"] = gainVec[i]

            if self.cfg["calibrate_cav"]:
                # Get the new cavity frequency
                transm_exp = Transmission_Enhance(path="TransmisionEnhanced", cfg=self.cfg, soc=self.soc, soccfg=self.soccfg,
                                                  outerFolder=self.path_only + "\\")
                data_transm = transm_exp.acquire()
                transm_exp.save_data(data_transm)
                transm_exp.save_config()
                transm_exp.display(data_transm, plotDisp=False)
                opt_freq = transm_exp.findOptimalFrequency(data=data_transm, debug=True, window_size=0.1)
                self.cfg["read_pulse_freq"] = opt_freq
                print(opt_freq)

            data_I, data_Q = self._acquireSpecData()

            data_I = np.array(data_I)  # This broke after the qick update to 0.2.287. Returns I, Q as lists instead of np arrays
            data_Q = np.array(data_Q)

            self.data['data']['spec_Imat'][i, :] = data_I
            self.data['data']['spec_Qmat'][i, :] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q


            avgamp0 = np.abs(sig)
            avgphase = np.angle(sig, deg=True)
            avgI = data_I
            avgQ = data_Q

                ## Amplitude
            Z_specamp[i, :] = avgamp0/np.mean(avgamp0)

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_1 = axs[0,0].imshow(
                    Z_specamp,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0,0], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_specamp)
                ax_plot_1.set_clim(vmin=np.nanmin(Z_specamp))
                ax_plot_1.set_clim(vmax=np.nanmax(Z_specamp))
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0,0], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[0,0].set_ylabel("RO gain (DAC)")
            axs[0,0].set_xlabel("Spec Frequency (GHz)")
            axs[0,0].set_title("Qubit Spec : Amplitude")

            ## Phase
            Z_specphase[i, :] = avgphase

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_2 = axs[1,0].imshow(
                    Z_specphase,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1,0], extend='both')
                cbar2.set_label('Phase', rotation=90)
            else:
                ax_plot_2.set_data(Z_specphase)
                ax_plot_2.set_clim(vmin=np.nanmin(Z_specphase))
                ax_plot_2.set_clim(vmax=np.nanmax(Z_specphase))
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1,0], extend='both')
                cbar2.set_label('Phase', rotation=90)

            axs[1,0].set_ylabel("RO gain (DAC)")
            axs[1,0].set_xlabel("Spec Frequency (GHz)")
            axs[1,0].set_title("Qubit Spec : Phase")

            ## I
            Z_specI[i, :] = avgI

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_3 = axs[0,1].imshow(
                    Z_specI,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[0,1], extend='both')
                cbar3.set_label('I', rotation=90)
            else:
                ax_plot_3.set_data(Z_specI)
                ax_plot_3.set_clim(vmin=np.nanmin(Z_specI))
                ax_plot_3.set_clim(vmax=np.nanmax(Z_specI))
                cbar3.remove()
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[0,1], extend='both')
                cbar3.set_label('I', rotation=90)

            axs[0,1].set_ylabel("RO gain (DAC)")
            axs[0,1].set_xlabel("Spec Frequency (GHz)")
            axs[0,1].set_title("Qubit Spec : I")

            ## Q
            Z_specQ[i, :] = avgQ

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_4 = axs[1,1].imshow(
                    Z_specQ,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar4 = fig.colorbar(ax_plot_4, ax=axs[1,1], extend='both')
                cbar4.set_label('Q', rotation=90)
            else:
                ax_plot_4.set_data(Z_specQ)
                ax_plot_4.set_clim(vmin=np.nanmin(Z_specQ))
                ax_plot_4.set_clim(vmax=np.nanmax(Z_specQ))
                cbar4.remove()
                cbar4 = fig.colorbar(ax_plot_4, ax=axs[1,1], extend='both')
                cbar4.set_label('Q', rotation=90)

            axs[1,1].set_ylabel("RO gain (DAC)")
            axs[1,1].set_xlabel("Spec Frequency (GHz)")
            axs[1,1].set_title("Qubit Spec : Q")
            plt.suptitle(self.iname)

            plt.tight_layout()

            if plotDisp and i == 0:
                plt.show(block=False)
                # Parth's fix
                plt.pause(5)
            elif plotDisp:
                plt.draw()
                plt.pause(5)

            if i == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  ### time for single full row in seconds
                timeEst = t_delta * expt_cfg["trans_gain_num"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname)  #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)

        return self.data

    def _acquireSpecData(self):
        ##### code to aquire just the cavity transmission data

        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / expt_cfg["SpecNumPoints"]
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                       expt_cfg["SpecNumPoints"])

        prog = LoopbackProgramStarkSlice(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal",
                                         progress=False)  # qick update deprecated ? , debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice", cfg=self.cfg, soc=self.soc, soccfg=self.soccfg,
        #                                       outerFolder=r'Z:\TantalumFluxonium\Data\2024_06_29_cooldown\HouckCage_dev\dataTestSpecVsFlux', progress=True)
        # data = Instance_specSlice.acquire()
        # Instance_specSlice.display(data, plotDisp=False)
        data_I = data['data']['avgi']
        data_Q = data['data']['avgq']

        return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])




