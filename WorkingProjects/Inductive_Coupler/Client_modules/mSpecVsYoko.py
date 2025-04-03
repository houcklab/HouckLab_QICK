from qick import *
import matplotlib.pyplot as plt
import numpy as np
from Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime
from PythonDrivers.YOKOGS200 import *
from scipy.signal import savgol_filter
import time


class LoopbackProgramTrans(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])


        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=self.us2cycles(cfg["readout_length"]), gen_ch=cfg["res_ch"])

        style = self.cfg["pulse_style"]
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
            0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))

        if style in ["flat_top", "arb"]:
            sigma = cfg["sigma"]
            nsigma = 5
            samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
            idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
                                  si=sigma * samples_per_clock,
                                  length=sigma * samples_per_clock * nsigma,
                                  maxv=np.iinfo(np.int16).max - 1)
            self.add_pulse(ch=res_ch, name="measure", idata=idata)

        if style == "const":
            # print(ffChannel, style, ff_freq, cfg["ff_gain"], cfg["ff_length"])
            # print(res_ch, style, freq, cfg["pulse_gain"], cfg["length"])

            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     length=self.us2cycles(cfg["length"]),
                                     )  # mode="periodic")
            # print('ffChannel', 'style', 'ff_freq', 'cfg["ff_gain"]', 'cfg["ff_length"]')
            #
            # print(ffChannel, style, ff_freq, cfg["ff_gain"], cfg["ff_length"])

        elif style == "flat_top":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure", length=self.us2cycles(cfg["length"]))
        elif style == "arb":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
        # control should wait until the readout is over
        self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"] + self.cfg["readout_length"]))
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels

# ====================================================== #

class LoopbackProgramSpecSlice(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=self.us2cycles(cfg["readout_length"]), gen_ch=cfg["res_ch"])
        style = self.cfg["pulse_style"]
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
            0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        if style in ["flat_top", "arb"]:
            sigma = self.us2cycles(cfg["sigma"])
            nsigma = 5
            samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
            idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
                                  si=sigma * samples_per_clock,
                                  length=sigma * samples_per_clock * nsigma,
                                  maxv=np.iinfo(np.int16).max - 1)
            self.add_pulse(ch=res_ch, name="measure", idata=idata)
        if style == "const":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     length=self.us2cycles(cfg["length"]),
                                     )  # mode="periodic")
            #             self.set_pulse_registers(ch=qubit_ch, style=style, freq=qubit_freq, phase=0, gain=cfg["qubit_gain"],
            #                                      length=cfg["qubit_length"],mode="periodic")
            self.set_pulse_registers(ch=qubit_ch, style=style, freq=qubit_freq, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"]))

        elif style == "flat_top":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure", length=self.us2cycles(cfg["length"]))
        elif style == "arb":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        # Play qubit pulse
        self.pulse(ch=self.cfg["qubit_ch"])  # play readout pulse
        self.synci(1000)  # wait for qubit to be excited

        # self.sync_all()
        # Play measurement pulse and trigger readout
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
        # control should wait until the readout is over
        self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"] + self.cfg["readout_length"]))
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels


# ====================================================== #


class SpecVsYoko(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum as a function of flux, specifically it uses a yoko to sweep
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through yoko
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None,
                 config_file=None, progress=None, yoko = None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, yoko = yoko)

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        expt_cfg = {
            ### define the yoko parameters
            "yokoStart": self.cfg["yokoStart"],
            "yokoStop": self.cfg["yokoStop"],
            "yokoNumPoints": self.cfg["yokoNumPoints"],
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }


        yokoVec = np.linspace(expt_cfg["yokoStart"],expt_cfg["yokoStop"], expt_cfg["yokoNumPoints"])

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
        fig.suptitle(str(self.identifier), fontsize=16)
        ### create the frequency arrays for both transmission and spec
        ### also create empty array to fill with transmission and spec data
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        X_trans = (self.trans_fpts + self.cfg["cavity_LO"]/1e6) /1e3
        X_trans_step = X_trans[1] - X_trans[0]
        X_spec = self.spec_fpts/1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y = yokoVec
        Y_step = Y[1] - Y[0]
        Z_trans = np.full((expt_cfg["yokoNumPoints"], expt_cfg["TransNumPoints"]), np.nan)
        Z_spec = np.full((expt_cfg["yokoNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_Imat = np.zeros((expt_cfg["yokoNumPoints"], expt_cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((expt_cfg["yokoNumPoints"], expt_cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((expt_cfg["yokoNumPoints"], expt_cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((expt_cfg["yokoNumPoints"], expt_cfg["SpecNumPoints"]))
        self.data= {
            'config': self.cfg,
            'data': {'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'yokoVec': yokoVec
                     }
        }

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()
        self.yoko.SetVoltage(yokoVec[0])
        step_size = np.abs(yokoVec[1] - yokoVec[0])
        if np.round(step_size, 8) == 0:
            step_size = 0.00001
        step_size = min([step_size / 2, 0.001])
        self.yoko.rampstep = step_size
        #### loop over the yoko vector
        for i in range(expt_cfg["yokoNumPoints"]):
            if i != 0:
                time.sleep(self.cfg['sleep_time'])
            ### set the yoko voltage for the specific run
            self.yoko.SetVoltage(yokoVec[i])

            time.sleep(5)
            ### take the transmission data
            data_I, data_Q = self._aquireTransData()
            self.data['data']['trans_Imat'][i,:] = data_I
            self.data['data']['trans_Qmat'][i,:] = data_Q

            #### plot out the transmission data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig)
            Z_trans[i, :] = avgamp0
            # axs[0].plot(x_pts, avgamp0, label="Amplitude; ADC 0")
            ax_plot_0 = axs[0].imshow(
                Z_trans,
                aspect='auto',
                extent=[np.min(X_trans)-X_trans_step/2,np.max(X_trans)+X_trans_step/2,np.min(Y)-Y_step/2,np.max(Y)+Y_step/2],
                origin= 'lower',
                interpolation= 'none',
            )
            if i ==0: #### if first sweep add a colorbar
                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)
            else:
                cbar0.remove()
                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)

            axs[0].set_ylabel("Yoko Voltage (V)")
            axs[0].set_xlabel("Cavity Frequency (GHz)")
            axs[0].set_title("Cavity Transmission")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
            if i != expt_cfg["yokoNumPoints"]:
                time.sleep(self.cfg['sleep_time'])

            ### take the spec data
            data_I, data_Q = self._aquireSpecData()
            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig)
            Z_spec[i, :] = avgamp0  #- self.cfg["minADC"]
            ax_plot_1 = axs[1].imshow(
                Z_spec,
                aspect='auto',
                extent=[np.min(X_spec)-X_spec_step/2,np.max(X_spec)+X_spec_step/2,np.min(Y)-Y_step/2,np.max(Y)+Y_step/2],
                origin='lower',
                interpolation = 'none',
            )
            if i ==0: #### if first sweep add a colorbar
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[1].set_ylabel("Yoko Voltage (V)")
            axs[1].set_xlabel("Spec Frequency (GHz)")
            axs[1].set_title("Qubit Spec")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + self.cfg["sleep_time"] * 2### time for single full row in seconds
                timeEst = (t_delta )*expt_cfg["yokoNumPoints"]  ### estimate for full scan
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

    def _aquireTransData(self):
        ##### code to aquire just the cavity transmission data
        expt_cfg = {
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
        }
        ### take the transmission data
        self.cfg["reps"] = self.cfg["trans_reps"]
        fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)
        #### pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]

        #### find the frequency corresponding to the cavity peak and set as cavity transmission number
        sig = data_I + 1j * data_Q
        avgamp0 = np.abs(sig)
        filtered_amp = savgol_filter(avgamp0, 5, 2)
        peak_loc = np.argmin(filtered_amp)
        self.cfg["pulse_freq"] = self.trans_fpts[peak_loc]
        self.cfg['minADC'] = avgamp0[peak_loc]

        return data_I, data_Q

    def _aquireSpecData(self):
        ##### code to aquire just the cavity transmission data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        ### take the transmission data
        self.cfg["reps"] = self.cfg["spec_reps"]
        fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["qubit_freq"] = f
            prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)
        #### pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]

        return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


