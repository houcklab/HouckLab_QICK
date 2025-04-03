# This code performs qubit spectroscopy while sweeping cavity power to see the AC Stark shift on the qubit.
# This allows calibration of photon number in the readout resonator. Make sure to use qubit powers sufficiently low
# to not populate the qubit significantly.

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_Enhance import \
    Transmission_Enhance
from tqdm.notebook import tqdm
import time
import datetime
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time


class CavityTransm_MIST(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):

        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout

        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], ro_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])


        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        self.f_res = f_res

        # Adding the resonator pulse
        if self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]), mode="periodic")
        elif not self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))

        self.sync_all(self.us2cycles(10))

    def body(self):

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        if self.cfg["populate_cavity"]:
            # Configure the cavity pulse for populating the cavity
            self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                     gain=self.cfg["cavity_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]))

            self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns


            self.pulse(ch=self.cfg["res_ch"])  # Play a cavity tone
            self.sync_all(self.us2cycles(15))  # align channels and wait 10ns

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


class CavityInducedHeating(ExperimentClass):
    """
    to write
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp=True, plotSave=True, figNum=1):
        expt_cfg = {
            "param_name": self.cfg["param_name"],
            "param_start": self.cfg["param_start"],
            "param_stop": self.cfg["param_stop"],
            "param_num": self.cfg["param_num"],
            # trans parameters
            "trans_freq_start": self.cfg["read_pulse_freq"] - self.cfg["TransSpan"]/2,  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["read_pulse_freq"] + self.cfg["TransSpan"]/2,  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_num_points": self.cfg["TransNumPoints"],
        }

        paramVec = np.linspace(expt_cfg["param_start"], expt_cfg["param_stop"], expt_cfg["param_num"], dtype=int)

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 2, figsize=(16, 10), num=figNum)

        ### create the frequency array
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"],
                                     expt_cfg["trans_num_points"])

        Y = paramVec
        Y_step = Y[1] - Y[0]

        self.trans_Imat = np.zeros((expt_cfg["param_num"], expt_cfg["trans_num_points"]))
        self.trans_Qmat = np.zeros((expt_cfg["param_num"], expt_cfg["trans_num_points"]))
        self.data = {
            'config': self.cfg,
            'data': {'param_fpts': paramVec,
                     'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts': self.trans_fpts,
                     }
        }

        X_spec = self.trans_fpts / 1e3
        X_spec_step = X_spec[1] - X_spec[0]

        Z_specamp = np.full(self.trans_Qmat.shape, np.nan)
        Z_specphase = np.full(self.trans_Qmat.shape, np.nan)
        Z_specI = np.full(self.trans_Qmat.shape, np.nan)
        Z_specQ = np.full(self.trans_Qmat.shape, np.nan)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        # Creating the extents of the plot
        extents = [X_spec[0] - X_spec_step / 2, X_spec[-1] + X_spec_step / 2, Y[0] - Y_step / 2, Y[-1] + Y_step / 2]

        # Creating an entry in the dictionary for cavity pulse gain

        # Looping around all the cavity pulse gains
        for i in range(expt_cfg["param_num"]):
            self.cfg[self.cfg["param_name"]] = paramVec[i]

            if 'param_name_2' in self.cfg:
                self.cfg[self.cfg['param_name_2']] = paramVec[i]

            data_I, data_Q = self.acquireTransData()

            data_I = np.array(
                data_I)  # This broke after the qick update to 0.2.287. Returns I, Q as lists instead of np arrays
            data_Q = np.array(data_Q)

            self.data['data']['trans_Imat'][i, :] = data_I
            self.data['data']['trans_Qmat'][i, :] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q

            avgamp0 = np.abs(sig)
            avgphase = np.angle(sig, deg=True)
            avgI = data_I
            avgQ = data_Q

            ## Amplitude
            Z_specamp[i, :] = avgamp0 / np.mean(avgamp0)

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_1 = axs[0, 0].imshow(
                    Z_specamp,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0, 0], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_specamp)
                ax_plot_1.set_clim(vmin=np.nanmin(Z_specamp))
                ax_plot_1.set_clim(vmax=np.nanmax(Z_specamp))
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0, 0], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[0, 0].set_ylabel(self.cfg['param_name'])
            axs[0, 0].set_xlabel("Trans Frequency (GHz)")
            axs[0, 0].set_title("Trans Spec : Amplitude")

            ## Phase
            Z_specphase[i, :] = avgphase

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_2 = axs[1, 0].imshow(
                    Z_specphase,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1, 0], extend='both')
                cbar2.set_label('Phase', rotation=90)
            else:
                ax_plot_2.set_data(Z_specphase)
                ax_plot_2.set_clim(vmin=np.nanmin(Z_specphase))
                ax_plot_2.set_clim(vmax=np.nanmax(Z_specphase))
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1, 0], extend='both')
                cbar2.set_label('Phase', rotation=90)

            axs[1, 0].set_ylabel(self.cfg['param_name'])
            axs[1, 0].set_xlabel("Trans Frequency (GHz)")
            axs[1, 0].set_title("Trans Spec : Phase")

            ## I
            Z_specI[i, :] = avgI

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_3 = axs[0, 1].imshow(
                    Z_specI,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[0, 1], extend='both')
                cbar3.set_label('I', rotation=90)
            else:
                ax_plot_3.set_data(Z_specI)
                ax_plot_3.set_clim(vmin=np.nanmin(Z_specI))
                ax_plot_3.set_clim(vmax=np.nanmax(Z_specI))
                cbar3.remove()
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[0, 1], extend='both')
                cbar3.set_label('I', rotation=90)

            axs[0, 1].set_ylabel(self.cfg['param_name'])
            axs[0, 1].set_xlabel("Trans Frequency (GHz)")
            axs[0, 1].set_title("Trans Spec : I")

            ## Q
            Z_specQ[i, :] = avgQ

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_4 = axs[1, 1].imshow(
                    Z_specQ,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar4 = fig.colorbar(ax_plot_4, ax=axs[1, 1], extend='both')
                cbar4.set_label('Q', rotation=90)
            else:
                ax_plot_4.set_data(Z_specQ)
                ax_plot_4.set_clim(vmin=np.nanmin(Z_specQ))
                ax_plot_4.set_clim(vmax=np.nanmax(Z_specQ))
                cbar4.remove()
                cbar4 = fig.colorbar(ax_plot_4, ax=axs[1, 1], extend='both')
                cbar4.set_label('Q', rotation=90)

            axs[1, 1].set_ylabel(self.cfg['param_name'])
            axs[1, 1].set_xlabel("Trans Frequency (GHz)")
            axs[1, 1].set_title("Trans Spec : Q")
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
                timeEst = t_delta * expt_cfg["param_num"]  ### estimate for full scan
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

    def acquireTransData(self):
        ##### code to aquire just the cavity transmission data

        expt_cfg = {
            "center": self.cfg["read_pulse_freq"],
            "span": self.cfg["TransSpan"],
            "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / (expt_cfg["expts"] - 1)
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = CavityTransm_MIST(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)
        data = {'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}

        data_I = data['data']['results'][0][0][0]
        data_Q = data['data']['results'][0][0][1]

        self.cfg['read_pulse_freq'] = expt_cfg['center']
        return data_I, data_Q

    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
