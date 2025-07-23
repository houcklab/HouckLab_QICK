from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions


class TwoToneTransmissionProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Declare generators
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Declare the qubit channel

        # Declare readout ADC channel
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Readout pulse
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        if cfg["ro_mode_periodic"]:
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"]), mode='periodic')  # define the pulse
        else:
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"]))  # define the pulse

        # Configure the qubit pulse
        self.qubit_pulse_length = PulseFunctions.create_qubit_pulse(self, self.cfg["qubit_freq"])

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"] +
                                              self.qubit_pulse_length, gen_ch=cfg["qubit_ch"])

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        ### initial pulse
        self.sync_all(self.us2cycles(0.01))  # align channels and wait

        if self.cfg["play_qubit_pulse"]:
            self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
            self.sync_all(self.us2cycles(0.01))  # align channels and wait

        ### Final measure
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

# ====================================================== #

class TwoToneTransmission(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        print(self.cfg)
        expt_cfg = {
                "center": self.cfg["read_pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        start = time.time()
        results_no_pulse = []
        results_pulse = []
        # For loop to first do just transmission, then play a qubit tone and do transmission again
        qubit_tone_loop = [False, True]
        for play_pulse in qubit_tone_loop:

            self.cfg['play_qubit_pulse'] = qubit_tone_loop[play_pulse]

            for f in tqdm(fpts, position=0, disable=True):
                self.cfg["read_pulse_freq"] = f
                prog = TwoToneTransmissionProgram(self.soccfg, self.cfg)
                self.soc.reset_gens()  # clear any DC or periodic values on generators
                if play_pulse:
                    results_pulse.append(prog.acquire(self.soc, load_pulses=True))
                else:
                    results_no_pulse.append(prog.acquire(self.soc, load_pulses=True))

        data={'config': self.cfg, 'data': {'results_pulse': np.transpose(results_pulse),
                                           'results_no_pulse': np.transpose(results_no_pulse), 'fpts': fpts}}
        self.data=data

        print(f'Time: {time.time() - start}')
        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num = figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        sig_no_pulse = data['data']['results_no_pulse'][0][0][0] + 1j * data['data']['results_no_pulse'][0][0][1]
        sig_pulse = data['data']['results_pulse'][0][0][0] + 1j * data['data']['results_pulse'][0][0][1]

        # Make the plot
        plt.title("Averages = " + str(self.cfg["reps"]))
        plt.subplot(2, 2, 1)
        plt.title("I, Q")
        plt.plot(x_pts, np.real(sig_no_pulse),label="I, no pulse")
        plt.plot(x_pts, np.imag(sig_no_pulse),label="Q, no pulse")
        plt.plot(x_pts, np.real(sig_pulse),label="I, pulse")
        plt.plot(x_pts, np.imag(sig_pulse),label="Q, pulse")
        plt.legend()
        plt.ylabel("ADC units")
        plt.xlabel("Cavity Frequency (GHz)")

        plt.subplot(2, 2, 2)
        plt.plot(x_pts, np.abs(sig_no_pulse), label="No pulse")
        plt.plot(x_pts, np.abs(sig_pulse), label="Pulse")
        plt.title("Magnitude")
        plt.ylabel("ADC units")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.legend()

        plt.subplot(2, 2, 3)
        plt.plot(x_pts, np.unwrap(np.angle(sig_no_pulse)), label="No pulse")
        plt.plot(x_pts, np.unwrap(np.angle(sig_pulse)), label="Pulse")
        plt.title("Phase")
        plt.ylabel("radians")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.legend()

        plt.subplot(2, 2, 4, adjustable='box', aspect=1)
        plt.plot(np.real(sig_no_pulse), np.imag(sig_no_pulse), label = "No pulse")
        plt.plot(np.real(sig_pulse), np.imag(sig_pulse), label="Pulse")
        plt.xlabel('I')
        plt.ylabel('Q')
        plt.legend()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


