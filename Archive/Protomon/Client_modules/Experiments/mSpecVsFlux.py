from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from Protomon.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime
from Protomon.Client_modules.PythonDrivers.YOKOGS200 import *

from Protomon.Client_modules.Experiments.mTransmission import LoopbackProgramTrans
#from Protomon.Client_modules.Experiments.mTransmissionFF import LoopbackProgramTransFF
from Protomon.Client_modules.Experiments.mSpecSlice_ShashwatTest import PulseProbeSpectroscopyProgram
import pyvisa


# class LoopbackProgramTrans(AveragerProgram):
#     def __init__(self, soccfg, cfg):
#         super().__init__(soccfg, cfg)
#
#     def initialize(self):
#         cfg = self.cfg
#         res_ch = cfg["res_ch"]
#         #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
#         self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
#
#         # configure the readout lengths and downconversion frequencies
#         for ro_ch in cfg["ro_chs"]:
#             self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])
#
#         style = self.cfg["read_pulse_style"]
#         freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
#             0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#         # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
#
#         if style in ["flat_top", "arb"]:
#             sigma = cfg["sigma"]
#             nsigma = 5
#             samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
#             idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
#                                   si=sigma * samples_per_clock,
#                                   length=sigma * samples_per_clock * nsigma,
#                                   maxv=np.iinfo(np.int16).max - 1)
#             self.add_pulse(ch=res_ch, name="measure", idata=idata)
#
#         if style == "const":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
#                                      length=cfg["length"],
#                                      )  # mode="periodic")
#         elif style == "flat_top":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
#                                      waveform="measure", length=cfg["length"])
#         elif style == "arb":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
#                                      waveform="measure")
#
#         self.synci(200)  # give processor some time to configure pulses
#
#     def body(self):
#         self.synci(200)  # give processor time to get ahead of the pulses
#         self.trigger(adcs=self.ro_chs, pins=[0],
#                      adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
#         self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
#         # control should wait until the readout is over
#         self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels
#
# # ====================================================== #
#
# class LoopbackProgramSpecSlice(AveragerProgram):
#     def __init__(self, soccfg, cfg):
#         super().__init__(soccfg, cfg)
#
#     def initialize(self):
#         cfg = self.cfg
#         res_ch = cfg["res_ch"]
#         #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
#         self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
#
#         # Qubit configuration
#         qubit_ch = cfg["qubit_ch"]
#         self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
#
#         # configure the readout lengths and downconversion frequencies
#         for ro_ch in cfg["ro_chs"]:
#             self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])
#         style = self.cfg["read_pulse_style"]
#         freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
#             0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#
#         qubit_freq = self.freq2reg(cfg["qubit_freq"],
#                                    gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#
#         # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
#         if style in ["flat_top", "arb"]:
#             sigma = cfg["sigma"]
#             nsigma = 5
#             samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
#             idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
#                                   si=sigma * samples_per_clock,
#                                   length=sigma * samples_per_clock * nsigma,
#                                   maxv=np.iinfo(np.int16).max - 1)
#             self.add_pulse(ch=res_ch, name="measure", idata=idata)
#         if style == "const":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
#                                      length=cfg["length"],
#                                      )  # mode="periodic")
#             #             self.set_pulse_registers(ch=qubit_ch, style=style, freq=qubit_freq, phase=0, gain=cfg["qubit_gain"],
#             #                                      length=cfg["qubit_length"],mode="periodic")
#             self.set_pulse_registers(ch=qubit_ch, style=style, freq=qubit_freq, phase=0, gain=cfg["qubit_gain"],
#                                      length=cfg["qubit_length"])
#
#         elif style == "flat_top":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
#                                      waveform="measure", length=cfg["length"])
#         elif style == "arb":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
#                                      waveform="measure")
#
#         self.synci(200)  # give processor some time to configure pulses
#
#     def body(self):
#         self.synci(200)  # give processor time to get ahead of the pulses
#
#         # Play qubit pulse
#         self.pulse(ch=self.cfg["qubit_ch"])  # play readout pulse
#         self.sync_all()
#         # Play measurement pulse and trigger readout
#         self.trigger(adcs=self.ro_chs, pins=[0],
#                      adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
#         self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
#         # control should wait until the readout is over
#         self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels


# ====================================================== #


class SpecVsFlux(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum as a function of flux, specifically it uses a yoko to sweep
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through yoko
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        expt_cfg = {
            ### define the yoko parameters
            "yoko1VoltageStart": self.cfg["yoko1VoltageStart"],
            "yoko1VoltageStop": self.cfg["yoko1VoltageStop"],
            "yoko2VoltageStart": self.cfg["yoko2VoltageStart"],
            "yoko2VoltageStop": self.cfg["yoko2VoltageStop"],
            "yokoVoltageNumPoints": self.cfg["yokoVoltageNumPoints"],
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }

        ### define the yoko vector for the voltages, note this assumes that yoko1 already exists

        yoko1 = YOKOGS200(VISAaddress='USB0::0x0B21::0x0039::91T515414::0::INSTR', rm=pyvisa.ResourceManager())

        yoko2 = YOKOGS200(VISAaddress='USB0::0x0B21::0x0039::91S929901::0::INSTR', rm=pyvisa.ResourceManager())

        voltVecC = np.linspace(expt_cfg["yoko1VoltageStart"],expt_cfg["yoko1VoltageStop"], expt_cfg["yokoVoltageNumPoints"])
        yoko1.SetVoltage(expt_cfg["yoko1VoltageStart"])

        voltVecD = np.linspace(expt_cfg["yoko2VoltageStart"], expt_cfg["yoko2VoltageStop"],
                               expt_cfg["yokoVoltageNumPoints"])#*np.tan(self.cfg["theta"])
        yoko2.SetVoltage(expt_cfg["yoko2VoltageStart"])

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(3,1, figsize = (8,12), num = figNum)

        ### create the frequency arrays for both transmission and spec
        ### also create empty array to fill with transmission and spec data
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        X_trans = (self.trans_fpts + self.cfg["cavity_LO"]/1e6) /1e3
        X_trans_step = X_trans[1] - X_trans[0]
        X_spec = self.spec_fpts/1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y = voltVecC
        Y_step = Y[1] - Y[0]
        Z_trans = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["TransNumPoints"]), np.nan)
        Z_spec = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_Imat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]))
        self.data= {
            'config': self.cfg,
            'data': {'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'voltVecC': voltVecC, 'voltVecD' : voltVecD
                     }
        }

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        #### loop over the yoko vector
        for i in range(expt_cfg["yokoVoltageNumPoints"]):
            ### set the yoko voltage for the specific run
            yoko1.SetVoltage(voltVecC[i])
            yoko2.SetVoltage(voltVecD[i])

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

            axs[0].set_ylabel("yoko voltage (V)")
            axs[0].set_xlabel("Cavity Frequency (GHz)")
            axs[0].set_title("Cavity Transmission")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if plotSave:
                plt.savefig(self.iname)  #### save the figure

            ### take the spec data
            data_I, data_Q = self._aquireSpecData()
            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            avgphase = np.arctan2(data_Q, data_I) - np.mean(np.arctan2(data_Q, data_I))
            Z_spec[i, :] = avgphase
            ax_plot_1 = axs[1].imshow(
                Z_spec,
                aspect='auto',
                extent=[np.min(X_spec)-X_spec_step/2,np.max(X_spec)+X_spec_step/2,np.min(Y)-Y_step/2,np.max(Y)+Y_step/2],
                origin='lower',
                interpolation = 'none',
            )

            #### plot out the spec data background subtracted
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig) -np.mean(np.abs(sig))
            Z_spec[i, :] = avgamp0
            ax_plot_2 = axs[2].imshow(
                Z_spec,
                aspect='auto',
                extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                        np.max(Y) + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            if i ==0: #### if first sweep add a colorbar
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
                cbar2.set_label('a.u.', rotation=90)
            else:
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
                cbar2.set_label('a.u.', rotation=90)

            axs[1].set_ylabel("yoko voltage (V)")
            axs[1].set_xlabel("Spec Frequency (GHz)")
            axs[1].set_title("Qubit Spec Phase Bkgnd Sub")
            axs[2].set_ylabel("yoko voltage (V)")
            axs[2].set_xlabel("Spec Frequency (GHz)")
            axs[2].set_title("Qubit Spec Mag Bkgnd Sub")

            plt.tight_layout()

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if plotSave:
                plt.savefig(self.iname)  #### save the figure

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start ### time for single full row in seconds
                timeEst = t_delta*expt_cfg["yokoVoltageNumPoints"] ### estimate for full scan
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
        self.cfg["reps"] = self.cfg["trans_reps"]
        self.cfg["rounds"] = self.cfg["trans_rounds"]
        ### take the transmission data
        fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        results = []
        print("beginning acquire transmission")
        print(self.cfg)
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            # prog = LoopbackProgramTransFF(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        #### pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]

        #### find the frequency corresponding to the cavity peak and set as cavity transmission number
        sig = data_I + 1j * data_Q
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.cfg["read_pulse_freq"] = self.trans_fpts[peak_loc]
        print("read pulse freq = ", self.cfg["read_pulse_freq"] )

        return data_I, data_Q

    def _aquireSpecData(self):
        ##### code to aquire just the qubit spec data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        ### take the transmission data
        fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.cfg["step"] = np.float(
            (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / expt_cfg["SpecNumPoints"])
        self.cfg["start"] = self.cfg["qubit_freq_start"]
        self.cfg["expts"] = self.cfg["SpecNumPoints"]
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["rounds"] = self.cfg["spec_rounds"]
        self.cfg["qubit_pulse_style"] = "const"
        print("beginning acquire spec")
        print(self.cfg)
        start = time.time()
        prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        #### pull out I and Q data
        data_I = data['data']['avgi'][0][0]
        data_Q = data['data']['avgq'][0][0]

        return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


