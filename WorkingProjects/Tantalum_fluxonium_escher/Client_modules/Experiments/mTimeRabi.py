from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass # used to come from WTF, might cause problems
from tqdm.notebook import tqdm
import time
# class LoopbackProgramTimeRabi(AveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
#         for ch in cfg["ro_chs"]:
#             self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
#                                  freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])
#
#         read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
#                                   ro_ch=cfg["ro_chs"][0])  # convert f_res to dac register value
#         qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg[
#             "qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#
#         # Define qubit pulse
#         if cfg["qubit_pulse_style"] == "flat_top":
#             self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
#                            sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
#                            length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
#             self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
#                                      phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
#                                      # cfg["start"],
#                                      waveform="qubit", length=self.us2cycles(cfg["qb_length"]))
#             self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(cfg["qb_length"])
#         elif cfg["qubit_pulse_style"] == "const":
#             self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0,
#                                      gain=cfg["qubit_gain"],
#                                      length=self.us2cycles(cfg["qb_length"], gen_ch=cfg["qubit_ch"]),
#                                      )
#             # mode="periodic")
#             self.qubit_pulseLength = self.us2cycles(cfg["qb_length"], gen_ch=cfg["qubit_ch"])
#
#         else:
#             print("define pi or flat top pulse")
#
#         self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
#                                  gain=cfg["read_pulse_gain"],
#                                  length=self.us2cycles(self.cfg["read_length"]))
#
#         # Calculate length of trigger pulse
#         self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
#                                               gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####
#
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
#
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
# def body(self):
#     cfg = self.cfg
#     self.pulse(ch=cfg["qubit_ch"])  # play probe pulse
#     self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
#
#     self.measure(pulse_ch=cfg["res_ch"],adcs=[0,1],wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))
#

#-----------------------------------------------------------#
class LoopbackProgramTimeRabi(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters
        self.cfg["start"] = self.cfg["qubit_len_start"]
        self.cfg["step"] = 1
        self.cfg["expts"] = 1 #self.cfg["qubit_len_expts"]
        self.cfg["reps"] = self.cfg["TimeRabi_reps"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        #self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        #self.r_length = self.sreg(cfg["qubit_ch"], "t") ### Ignore

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # convert f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        # Define qubit pulse
        if cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=self.cfg["qubit_gain"], #cfg["start"],
                                     waveform="qubit",  length=self.us2cycles(cfg["qb_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(cfg["qb_length"])
        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0,
                                     gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qb_length"], gen_ch=cfg["qubit_ch"]),
                                     )
                                     #mode="periodic")
            self.qubit_pulseLength = self.us2cycles(cfg["qb_length"], gen_ch=cfg["qubit_ch"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def body(self):
        # Switch control
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc
        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        # self.sync_all(self.us2cycles(0.05)) # align channels and wait 50ns
        # If we're calibrating a pi/2 pulse:
        if self.cfg["two_pulses"]:
            self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    # def update(self):
    #     self.mathi(self.q_rp, self.r_length, self.r_length, '+',
    #                self.cfg["step"])  # update gain of the Gaussian pi pulse
# ====================================================== #

class TimeRabi(ExperimentClass):
    """
    Basic TimeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None,
                 config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self):
        #### pull the data from the amp rabi sweep
        avgi_list = []
        avgq_list = []
        len_list = np.linspace(self.cfg["qubit_len_start"], self.cfg["qubit_len_start"]+self.cfg["qubit_len_step"]*self.cfg["qubit_len_expts"], self.cfg["qubit_len_expts"])
        for length in len_list:
            self.cfg["qb_length"] = length
            prog = LoopbackProgramTimeRabi(self.soccfg, self.cfg)
            start = time.time()
            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                                 readouts_per_experiment=1, save_experiments=None,
                                                 start_src="internal", progress=False, debug=False)
            print(f'Time: {time.time() - start}')
            avgi_list.append(avgi[0][0][0])
            avgq_list.append(avgq[0][0][0])


        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data
        return x_pts, np.array(avgi_list), np.array(avgq_list)


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.remainder(np.angle(sig,deg=True)+360,360)
        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="Phase")
        axs[0].set_ylabel("Degrees")
        axs[0].set_xlabel("Qubit length (DAC units)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="Magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Qubit length (DAC units)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Qubit length (DAC units)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Qubit length (DAC units)")
        axs[3].legend()

        fig.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(2)
            plt.close()
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

