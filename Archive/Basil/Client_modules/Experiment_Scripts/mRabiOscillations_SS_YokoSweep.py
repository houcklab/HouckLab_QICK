from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q3diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
from q3diamond.Client_modules.Helpers.rotate_SS_data import *
import time

class OscillationsProgramSS(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_read_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)


        # self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        # self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        # for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
        #     self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"]),
        #                          freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        #
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        # f_ge = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

        ### Start fast flux
        # self.declare_gen(ch=cfg["ff_ch"], nqz=cfg["ff_nqz"])
        for FF_info in cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]

        self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
        self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]

        ### Finish FF

        # add qubit and readout pulses to respective channels

        self.qubit_pulseLength = self.us2cycles(cfg["sigma"] * 4)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.us2cycles(cfg["sigma"]), length=self.qubit_pulseLength)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"] ,
                                 waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=read_freq, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        # self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.cfg["ff_gain"],
        #                          length=self.cfg["sigma"] * 4 + self.us2cycles(0.1) )
        # self.pulse(ch=self.cfg['ff_ch'])
        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq,
                                 phase=0, gain=self.FF_Gain1_readout,
                                 length=self.qubit_pulseLength + self.us2cycles(0.01))
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq,
                                 phase=0, gain=self.FF_Gain2_readout,
                                 length=self.qubit_pulseLength + self.us2cycles(0.01))
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.01))  # play probe pulse

        self.sync_all()
        if self.cfg["variable_wait"] > 0.01:
            self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=self.FF_Gain1_exp,
                                     length=self.us2cycles(self.cfg["variable_wait"]))
            self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=self.FF_Gain2_exp,
                                     length=self.us2cycles(self.cfg["variable_wait"]))

            # self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain= -1 * self.cfg["ff_gain"],
            #                           length=self.us2cycles(self.cfg["variable_wait"])) #self.us2cycles(1))

            self.pulse(ch=self.FF_Channel1)
            self.pulse(ch=self.FF_Channel2)

            self.sync_all()

        # self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain= self.cfg["ff_gain"],
        #                          length= self.cfg["length"])
        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
                                 gain=self.FF_Gain1_readout,
                                 length=self.us2cycles(self.cfg["length"]))
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
                                 gain=self.FF_Gain2_readout,
                                 length=self.us2cycles(self.cfg["length"]))
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=None)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

        # time_to_balance = self.us2cycles(self.cfg["length"]) - self.us2cycles(self.cfg["variable_wait"]) +  \
        #                          self.us2cycles(self.cfg["sigma"] * 4) + self.us2cycles(0.1)
        # if time_to_balance > 5:
        #     self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain=-1 * self.FF_Gain1,
        #                              length=time_to_balance)
        #     self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain=-1 * self.FF_Gain2,
        #                              length=time_to_balance)
        #     self.pulse(ch=self.FF_Channel1)
        #     self.pulse(ch=self.FF_Channel2)
        #     self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
        #
        # elif time_to_balance < -5:
        #     self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain= self.FF_Gain1,
        #                              length= -1 * time_to_balance)
        #     self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain= self.FF_Gain2,
        #                              length=-1 * time_to_balance)
        #     self.pulse(ch=self.FF_Channel1)
        #     self.pulse(ch=self.FF_Channel2)
        #     self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
        #
        # else:

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['read_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['read_length'], ro_ch=0)

        return shots_i0, shots_q0


class Oscillations_SS_Yoko(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 yoko = None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, yoko = yoko)

    def acquire(self, threshold = None, angle = None, progress=False, debug=False, figNum = 1, plotDisp = True,
                plotSave = True):

        expt_cfg = {
            ### define the yoko parameters
            "yokoStart": self.cfg["yokoStart"],
            "yokoStop": self.cfg["yokoStop"],
            "yokoNumPoints": self.cfg["yokoNumPoints"],
            ### define the wait_time parameters:
            "wait_start": self.cfg["start"],
            "wait_step": self.cfg["step"],
            "wait_expts": self.cfg["expts"]
        }


        yokoVec = np.linspace(expt_cfg["yokoStart"],expt_cfg["yokoStop"], expt_cfg["yokoNumPoints"])
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (10,8), num = figNum)
        fig.suptitle(str(self.titlename), fontsize=16)

        self.wait_times = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        Z_values = np.full((expt_cfg["yokoNumPoints"], expt_cfg["wait_expts"]), np.nan)
        self.rotatedIQ = np.full((expt_cfg["yokoNumPoints"], expt_cfg["wait_expts"]), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': Z_values, 'RotatedIQ': self.rotatedIQ, 'threshold':threshold,
                        'wait_times': self.wait_times, 'yokoVec': yokoVec
                     }
        }

        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.cfg["reps"] = self.cfg["shots"]

        self.yoko.SetVoltage(yokoVec[0])
        step_size = np.abs(yokoVec[1] - yokoVec[0])
        if np.round(step_size, 8) == 0:
            step_size = 0.00001
        step_size = min([step_size / 2, 0.001])
        self.yoko.rampstep = step_size

        X = tpts
        X_step = X[1] - X[0]
        Y = yokoVec
        Y_step = Y[1] - Y[0]

        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        start = time.time()
        for i in range(expt_cfg["yokoNumPoints"]):
            print('yoko index: ', i)
            # if i != 0:
            #     time.sleep(self.cfg['sleep_time'])
            ### set the yoko voltage for the specific run
            self.yoko.SetVoltage(yokoVec[i])

            time.sleep(5)
            results = []
            rotated_iq_array = []

            for t in tqdm(tpts, position=0, disable=True):
                # print(t)
                self.cfg["variable_wait"] = t
                prog = OscillationsProgramSS(self.soccfg, self.cfg)
                shots_i0, shots_q0 = prog.acquire(self.soc,
                                                  load_pulses=True)
                rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
                rotated_iq_array.append(rotated_iq)
                excited_percentage = count_percentage(rotated_iq, threshold = threshold)
                results.append(excited_percentage)

            # self.data['data']["RotatedIQ"][i, :] = np.array(rotated_iq_array)
            self.data['data']["Exp_values"][i, :] = np.array(results)

            Z_values[i, :] = np.array(results)

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
                cbar1.set_label('Excited Population', rotation=90)
            else:
                ax_plot_1.set_data(Z_values)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('Excited Population', rotation=90)

            axs.set_ylabel("Yoko Voltage (V)")
            axs.set_xlabel("Wait time (us)")
            axs.set_title("Oscillations")


            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + 5 * 2### time for single full row in seconds
                timeEst = (t_delta )*expt_cfg["yokoNumPoints"]  ### estimate for full scan
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
        # avgi = data['data']['avgi'][0][0]
        # avgq = data['data']['avgq'][0][0]

        x_pts = data['data']['tpts']
        percent_excited = data['data']['results']
        # avgi = data['data']['results'][0][0][0]
        # avgq = data['data']['results'][0][0][1]


        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, percent_excited, 'o-', label="i", color = 'orange')
        plt.ylabel("Excited Population")
        plt.xlabel("Wait time (us)")
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

