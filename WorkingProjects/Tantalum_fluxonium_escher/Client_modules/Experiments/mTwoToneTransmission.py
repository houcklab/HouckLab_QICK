from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

class LoopbackProgramTwoToneTransmission(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ### Configure Resonator Tone
        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"],) #mixer_freq=cfg["mixer_freq"],
                         #ro_ch=cfg["ro_chs"][0])  # Declare the resonator channel
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch,
                                  ro_ch=cfg["ro_chs"][0])  # Convert to clock ticks

        if cfg["ro_mode_periodic"]:
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"]), mode='periodic')  # define the pulse
        else:
            self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"]))  # define the pulse
        ### Configure the Qubit Tone
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        qubit_ch = cfg["qubit_ch"]  # Get the qubit channel
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])  # Declare the qubit channel
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # Convert qubit length to clock ticks
        # Define the qubit pulse
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
        elif cfg["qubit_pulse_style"] == "const":
            if cfg["qubit_mode_periodic"]:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0,
                                         gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]), mode='periodic')
            else:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0,
                                         gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                         mode='periodic')
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"])
        else:
            print("define pi or flat top or const pulse")

        ### Declare ADC Readout
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                 gen_ch=cfg["res_ch"])

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.cfg[
                                   "qubit_length"]  # self.qubit_pulseLength  ####

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
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
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
                prog = LoopbackProgramTwoToneTransmission(self.soccfg, self.cfg)
                #self.soc.reset_gens()  # clear any DC or periodic values on generators
                if play_pulse:
                    results_pulse.append(prog.acquire(self.soc, load_pulses=True))
                else:
                    results_no_pulse.append(prog.acquire(self.soc, load_pulses=True))
            # results = np.transpose(results)
            #
            # prog = LoopbackProgram(self.soccfg, self.cfg)
            # self.soc.reset_gens()  # clear any DC or periodic values on generators
            # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        if play_pulse:
            data={'config': self.cfg, 'data': {'results_pulse': np.transpose(results_pulse),
                                               'results_no_pulse': np.transpose(results_no_pulse), 'fpts':fpts}}
        else:
            data={'config': self.cfg, 'data': {'results_pulse': np.transpose(results_pulse),
                                               'results_no_pulse': np.transpose(results_no_pulse), 'fpts':fpts}}
        self.data=data

            #### find the frequency corresponding to the peak
            # sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
            # x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
            # sig = sig * np.exp(1j * x_pts * 2 * np.pi * self.cfg["RFSOC_delay"]) # This is an empirically-determined "electrical delay"
            # # It is much larger than the real, physical electrical delay (which is more like 80 ns, while this one is around a us),
            # # and is caused by the fact that the RFSOC has two different clocks for the output and input. We can safely just remove this phase.
            # # Expect the effective electrical delay to change when the RFSOC is rebooted.
            # data['data']['results'][0][0][0] = np.real(sig)
            # data['data']['results'][0][0][1] = np.imag(sig)
            # avgamp0 = np.abs(sig)
            # peak_loc = np.argmin(avgamp0)
            # self.peakFreq = data['data']['fpts'][peak_loc]

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


