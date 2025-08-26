from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

class LoopbackProgramTrans_wQubitTone(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        # Declaring readout tone and adc
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))

        # Declaring qubit tone
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
        self.qubit_freq = self.freq2reg(self.cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

        # define the qubit pulse depending on the pulse type
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
        elif self.cfg["qubit_pulse_style"] == "const":
            if self.cfg["mode_periodic"] == True:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.qubit_freq, phase=0,
                                         gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                         mode="periodic")
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])
            else:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.qubit_freq, phase=0,
                                         gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])

        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=self.qubit_freq,
                                     phase=0, gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = (self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
                                      + self.us2cycles(self.cfg["flat_top_length"], gen_ch=cfg["qubit_ch"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses

    def body(self):

        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

# ====================================================== #

class Transmission_wQubitTone(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        expt_cfg = {
                "center": self.cfg["read_pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / (expt_cfg["expts"]-1)
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        gain = [0, self.cfg["qubit_gain"]]
        print("The gain array is ", gain)
        avg_i = []
        avg_q = []
        start = time.time()
        for i in range(2):
            self.cfg["qubit_gain"] = gain[i]
            avg_i.append([])
            avg_q.append([])
            for f in fpts:
                self.cfg["read_pulse_freq"] = f
                prog = LoopbackProgramTrans_wQubitTone(self.soccfg, self.cfg)
                results = prog.acquire(self.soc, load_pulses=True)
                avg_i[i].append(results[0][0][0])
                avg_q[i].append(results[1][0][0])
            if debug:
                print(f'Time: {time.time() - start}')

        avg_i = np.array(avg_i)
        avg_q = np.array(avg_q)
        data={'config': self.cfg, 'data': {'avgi': avg_i, 'avgq':avg_q, 'fpts':fpts}}
        self.data=data

        # find the frequency corresponding to the peak
        sig = avg_i[1] + 1j * avg_q[1]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num = figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        sig_0 = data['data']['avgi'][0] + 1j * data['data']['avgq'][0]
        sig_1 = data['data']['avgi'][1] + 1j * data['data']['avgq'][1]
        avgamp_0 = np.abs(sig_0)
        avgamp_1 = np.abs(sig_1)
        plt.plot(x_pts, avgamp_0, label="Magnitude for 0 qubit_gain")
        plt.plot(x_pts, avgamp_1, label="Magnitude for "+str(self.cfg["qubit_gain"])+ " qubit_gain")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title("Averages = " + str(self.cfg["reps"]))
        plt.legend()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show()

        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        # print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


