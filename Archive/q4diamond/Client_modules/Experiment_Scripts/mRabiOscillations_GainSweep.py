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


class OscillationsProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # Qubit
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                 waveform="qubit")

        # Readout: resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        FF.FFDefinitions(self)

        self.sync_all(200)

    def body(self):
        # self.sync_all(self.us2cycles(0.05), dac_t0=self.dac_t0)  # align channels and wait 50ns
        self.sync_all(dac_t0=self.dac_t0)

        # print("0", self.dac_ts, self.adc_ts)
        self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 0.51)
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.5))  # play probe pulse

        # print("Q1: prev val {}, gain {}".format(self.FFPulse[0], self.FFExpts[0]))
        # print("1", self.dac_ts, self.adc_ts)
        # this block gives good walk
        self.FFPulses_direct(self.FFExpts, self.cfg["variable_wait"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"])

        # # this block gives beating pattern
        # # # make longest pulse
        # # self.FFPulses_direct(self.FFExpts, self.cfg['start'] + self.cfg["step"] * self.cfg["expts"], self.FFPulse,
        # #                      IQPulseArray=self.cfg["IDataArray"])
        # # # trim to length, convert to units of ccs
        # # self.mathi(1, 17, 17, '-', (self.cfg['start'] + self.cfg["step"] * self.cfg["expts"]) // 16)
        # # self.mathi(1, 17, 17, '+', self.cfg['variable_wait'] // 16)
        # # print(self.gen_mgrs[self.FFChannels[0]].pulses['FF'])
        #
        # self.sync_all(dac_t0=self.dac_t0)
        # # this block gives good walk
        # # self.set_pulse_registers(ch=self.FFChannels[0], style='const', freq=0, phase=0,
        # #                          gain=self.FFExpts[0],
        # #                          length=self.cfg["variable_wait"]//16, mode='oneshot', stdysel='zero')
        #
        # # this block gives decohering walk
        # self.set_pulse_registers(ch=self.FFChannels[0], style='const', freq=0, phase=0,
        #                          gain=self.FFExpts[0],
        #                          length=self.cfg["start"]//16, mode='oneshot', stdysel='zero')
        # self.mathi(1, 17, 17, '+', (self.cfg['variable_wait'] - self.cfg["start"])//16)
        # print("2", self.dac_ts, self.adc_ts)
        #
        # print("3", self.dac_ts, self.adc_ts)
        # self.pulse(ch=self.FFChannels[0])#, t=312)
        # self.memwi(1, 13, 130)
        # self.memwi(1, 14, 131)
        # self.memwi(1, 15, 132)
        # self.memwi(1, 16, 133)
        # self.memwi(1, 17, 134)
        # self.memwi(1, 18, 135)
        #
        # self.regwi(1, 5, (self.cfg['variable_wait'] - self.cfg["start"])//16)
        # # self.regwi(1, 5, self.cfg['variable_wait']//16)
        # self.sync(1, 5)
        # # print(self.cfg['variable_wait']//16)
        # # self.synci((self.cfg['variable_wait'] - self.cfg["start"])//16)  # extra time
        # # self.dac_ts[self.FFChannels[0]] -= (self.cfg['start'] + self.cfg["step"] * self.cfg["expts"]) // 16
        # # self.dac_ts[self.FFChannels[0]] += self.cfg['variable_wait'] // 16 - 3
        # print("4", self.dac_ts, self.adc_ts)
        self.sync_all(dac_t0=self.dac_t0)

        # self.FFPulses(2 * self.FFReadouts, 0.008)
        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        # self.FFPulses_hires(-1 * self.FFExpts, self.cfg["variable_wait"], waveform_label="FF2")
        IQ_Array_Negative = np.array([-1 * array if type(array) != type(None) else None for array in self.cfg["IDataArray"]], dtype = object)
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["variable_wait"], -1 * self.FFPulse, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')
        # self.FFPulses_direct(-1 * self.FFExpts, self.cfg["variable_wait"], -1 * self.FFReadouts, IQPulseArray= self.cfg["IDataArray"],
        #                      waveform_label="FF2")
        self.FFPulses(-1 * self.FFPulse, self.cfg["sigma"] * 4 + 0.51)

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
    # def FFPulses(self, list_of_gains, length_us, t_start=None, i_data_pulse = False, waveform_label = "FFPulse"):
    #     for i, gain in enumerate(list_of_gains):
    #         length = self.us2cycles(length_us, gen_ch=self.FFChannels[i])
    #         if i_data_pulse:
    #             gencfg = self.soccfg['gens'][self.FFChannels[i]]
    #             idata = np.concatenate([np.zeros(3 * 16), np.ones(length * 16)])
    #             # idata = np.ones(length * 16)
    #
    #             idata = idata * gencfg['maxv'] * gencfg['maxv_scale']
    #             qdata = np.zeros((length + 5) * 16)
    #             self.add_pulse(ch=self.FFChannels[i], name=waveform_label,
    #                            idata=idata, qdata=qdata)
    #             self.set_pulse_registers(ch=self.FFChannels[i], freq=0, style='arb',
    #                                      phase=0, gain=int(gain),
    #                                      waveform=waveform_label, outsel="input")
    #         else:
    #             self.set_pulse_registers(ch=self.FFChannels[i], style='const', freq=0, phase=0,
    #                                  gain=gain,
    #                                  length=length)
    #     if t_start is None:
    #         self.pulse(ch=self.FF_Channel1)
    #         self.pulse(ch=self.FF_Channel2)
    #         self.pulse(ch=self.FF_Channel3)
    #         self.pulse(ch=self.FF_Channel4)
    #     else:
    #         self.pulse(ch=self.FF_Channel1, t = t_start)
    #         self.pulse(ch=self.FF_Channel2, t = t_start)
    #         self.pulse(ch=self.FF_Channel3, t = t_start)
    #         self.pulse(ch=self.FF_Channel4, t = t_start)

class Oscillations_Gain(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 I_Ground = 0, I_Excited = 1, Q_Ground = 0, Q_Excited = 1):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)
        self.I_Ground = I_Ground
        self.I_Excited = I_Excited
        self.Q_Ground = Q_Ground
        self.Q_Excited = Q_Excited

        self.I_Range = I_Excited - I_Ground
        self.Q_Range = Q_Excited - Q_Ground

    def acquire(self, threshold = None, angle = None, progress=False, debug=False, figNum = 1, plotDisp = True,
                plotSave = True):

        gainVec = np.array([int(x) for x in np.linspace(self.cfg["gainStart"],self.cfg["gainStop"], self.cfg["gainNumPoints"])])
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        self.wait_times = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        Z_values = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        self.I_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)
        self.Q_data = np.full((self.cfg["gainNumPoints"], self.cfg["expts"]), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'oscillation_I': self.I_data, 'oscillation_Q': self.Q_data, 'wait_times': self.wait_times,
                        'gainVec': gainVec, 'I_Ground': self.I_Ground,
                                           'I_Excited': self.I_Excited, 'Q_Ground': self.Q_Ground,
                                           'Q_Excited': self.Q_Excited
                     }
        }

        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])

        X = tpts
        X_step = X[1] - X[0]
        Y = gainVec
        Y_step = Y[1] - Y[0]

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

        start = time.time()
        for i in range(self.cfg["gainNumPoints"]):
            if i % 5 == 1:
                self.save_data(self.data)
            self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Expt'] = int(gainVec[i])
            if type(self.cfg["IDataArray"][0]) != type(None):
                self.cfg["IDataArray"][self.cfg["qubitIndex"] - 1] = Compensated_Pulse(int(gainVec[i]),
                                                                                   self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Pulse'],
                                                                                       self.cfg["qubitIndex"])
            results = []
            start = time.time()
            for t in tqdm(tpts, position=0, disable=True):
                self.cfg["variable_wait"] = t
                prog = OscillationsProgram(self.soccfg, self.cfg)
                results.append(prog.acquire(self.soc, load_pulses=True))

                # print(prog)
                # self.soc.load_bin_program(prog.compile())
                # # # Start tProc.
                # self.soc.tproc.start()
                # print("freq:  ", self.soc.tproc.single_read(addr=130))
                # print("phase: ", self.soc.tproc.single_read(addr=131))
                # print("addr:  ", self.soc.tproc.single_read(addr=132))
                # print("gain:  ", self.soc.tproc.single_read(addr=133))
                # print("mode:  ", self.soc.tproc.single_read(addr=134))
                # print("time:  ", self.soc.tproc.single_read(addr=135))
            print(f'Time: {time.time() - start}')
            results = np.transpose(results)

            # self.data['data']["RotatedIQ"][i, :] = np.array(rotated_iq_array)
            self.data['data']["oscillation_I"][i, :] = results[0][0][0]
            self.data['data']["oscillation_Q"][i, :] = results[0][0][1]
            if np.abs(self.I_Range) > np.abs(self.Q_Range):
                Z_values[i, :] = (results[0][0][0] - self.I_Ground) / self.I_Range
            else:
                Z_values[i, :] = (results[0][0][1] - self.Q_Ground) / self.Q_Range

            if i == 0:
                ax_plot_1 = axs.imshow(
                    Z_values,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                if np.abs(self.I_Range) > np.abs(self.Q_Range):
                    cbar1.set_label('I Data', rotation=90)
                else:
                    cbar1.set_label('Q Data', rotation=90)
            else:
                ax_plot_1.set_data(Z_values)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                if np.abs(self.I_Range) > np.abs(self.Q_Range):
                    cbar1.set_label('I Data', rotation=90)
                else:
                    cbar1.set_label('Q Data', rotation=90)
            axs.set_ylabel("FF Gain (a.u.)")
            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_title("Oscillations")


            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + 5 * 2### time for single full row in seconds
                timeEst = (t_delta )*self.cfg["gainNumPoints"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))


        if plotSave:
            plt.savefig(self.iname) #### save the figure

        print(f'Time: {time.time() - start}')


        # results = np.transpose(results)

        # data={'config': self.cfg, 'data': {'results': results, 'tpts':tpts}}
        #### pull the data from the amp rabi sweep
        # prog = OscillationsProgram_RAverager_Wrong(self.soccfg, self.cfg)
        #
        # x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
        #                                  readouts_per_experiment=1, save_experiments=None,
        #                                  start_src="internal", progress=False, debug=False)
        # data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # self.data = data

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        # x_pts = data['data']['x_pts']
        avgi = data['data']['oscillation_I']
        avgq = data['data']['oscillation_Q']

        x_pts = data['data']['wait_times']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        if np.abs(self.I_Range) > np.abs(self.Q_Range):
            plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        else:
            plt.plot(x_pts, avgq, 'o-', label="q", color = 'blue')
        plt.ylabel("Excited Population")
        plt.xlabel("Wait time (2.32/16 ns )")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname)

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
Pulse_Q1 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q1_awg_V1.p', 'rb'))
Pulse_Q2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
Pulse_Q4 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q4_awg_V1.p', 'rb'))

Pulse_Q1[0] = 1.5
Compensated_pulse_list = [Pulse_Q1, Pulse_Q2, Pulse_Q2, Pulse_Q4]
Pulse_Q1 = np.concatenate([Pulse_Q1, np.ones(16 * 1000)])
Pulse_Q2 = np.concatenate([Pulse_Q2, np.ones(16 * 1000)])
Pulse_Q4 = np.concatenate([Pulse_Q4, np.ones(16 * 1000)])
print(len(Pulse_Q1), len(Pulse_Q2), len(Pulse_Q4))
Compensated_pulse_list = [Pulse_Q1, Pulse_Q2, Pulse_Q2, Pulse_Q4]

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
