from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

class LoopbackProgramTrans(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], ro_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])


        if self.cfg["ro_mode_periodic"]:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=freq, phase=0,
                                     gain=cfg["read_pulse_gain"], mode='periodic',
                                     length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        else:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=freq, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

# ====================================================== #

class Transmission(ExperimentClass):
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
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            #self.soc.reset_gens()  # clear any DC or periodic values on generators
            results.append(prog.acquire(self.soc, load_pulses=True, progress = progress))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        #
        # prog = LoopbackProgram(self.soccfg, self.cfg)
        # self.soc.reset_gens()  # clear any DC or periodic values on generators
        # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        #### find the frequency corresponding to the peak
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        sig = sig * np.exp(1j * x_pts * 2 * np.pi * self.cfg["RFSOC_delay"]) # This is an empirically-determined "electrical delay"
        # It is much larger than the real, physical electrical delay (which is more like 80 ns, while this one is around a us),
        # and is caused by the fact that the RFSOC has two different clocks for the output and input. We can safely just remove this phase.
        # Expect the effective electrical delay to change when the RFSOC is rebooted.
        data['data']['results'][0][0][0] = np.real(sig)
        data['data']['results'][0][0][1] = np.imag(sig)
        avgamp0 = np.abs(sig)
        peak_loc = np.argmax(avgamp0)
        self.peakFreq = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num = figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)
        plt.title("Averages = " + str(self.cfg["reps"]))
        plt.subplot(2, 2, 1)
        plt.title("I, Q")
        plt.plot(x_pts, np.real(sig),label="I")
        plt.plot(x_pts, np.imag(sig),label="Q")
        plt.legend()
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.subplot(2, 2, 2)
        plt.plot(x_pts, avgamp0, label="Magnitude")
        plt.title("Magnitude")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.subplot(2, 2, 3)
        plt.plot(x_pts, np.unwrap(np.angle(sig)), label="Phase")
        plt.title("Phase")
        plt.ylabel("radians")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.subplot(2, 2, 4, adjustable='box', aspect=1)
        plt.plot(np.real(sig), np.imag(sig))
        plt.xlabel('I')
        plt.ylabel('Q')
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


