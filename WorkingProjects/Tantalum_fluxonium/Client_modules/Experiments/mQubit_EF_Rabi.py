from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time


class LoopbackProgramQubit_ef_rabi(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters

        # Amplitude variation for a E-F Rabi
        self.cfg["start"] = self.cfg["qubit_ef_gain_start"]
        self.cfg["step"] = self.cfg["qubit_ef_gain_step"]
        # How many amplitude steps to do
        self.cfg["expts"] = self.cfg["RabiNumPoints"]

        # Number of averages at each step
        # self.cfg["reps"] = self.cfg["AmpRabi_reps"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.qreg_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.qreg_freq = self.sreg(self.cfg["qubit_ch"], "freq") # frequency register on qubit channel
        # To see list of all registers: self.pulse_registers
        # We need an additional register to use for the e-g frequency.
        # I don't know how to check the list of registers properly, so I will just use an arbitrary number that doesn't
        # match any of the ones listed above for channel 0 or 1, which are readout and qubit, resp.
        self.qreg_gain_ef = 4 # Taken from https://github.com/conniemiao/slab_rfsoc_expts/blob/d62c098f55bc4745bfb8e9ffa41d5bb49085b11e/experiments/single_qubit/pulse_probe_ef_spectroscopy.py#L99

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_ge_freq = self.freq2reg(cfg["qubit_ge_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.safe_regwi(self.q_rp, self.qreg_gain_ef, self.cfg["start"]) # Set the ef frequency register to start at the correct value

        # Define qubit pulse: gaussian
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit")
        # Define qubit pulse: flat top
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))

        # Don't know what kind of pulse we want
        else:
            print("define gaussian or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):
        ge_freq = self.freq2reg(self.cfg["qubit_ge_freq"], gen_ch=self.cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        ef_freq = self.freq2reg(self.cfg["qubit_ef_freq"], gen_ch=self.cfg["qubit_ch"])
        # Set up g-e pi pulse
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
                                 waveform="qubit")
        self.pulse(ch=self.cfg["qubit_ch"])  # play ge pi pulse

        # Set up e-f pulse
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ef_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=0,
                                 waveform="qubit")
        self.mathi(self.q_rp, self.qreg_gain, self.qreg_gain_ef, '+', 0) # Hack to set the qreg_gain register page to qreg_gain_ef (+0)
        self.pulse(ch = self.cfg['qubit_ch']) # play ef probe pulse

        self.sync_all(self.us2cycles(0.05)) # align channels and wait /

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.qreg_gain_ef, self.qreg_gain_ef, '+', self.cfg["step"]) # update frequency of the ef spectroscopy probe




# ====================================================== #

class Qubit_ef_rabi(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramQubit_ef_rabi(self.soccfg, self.cfg)
        start = time.time()
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


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
        axs[0].set_xlabel("Amplitude (in dac units)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="Magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Amplitude (in dac units)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Amplitude (in dac units)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Amplitude (in dac units)")
        axs[3].legend()

        fig.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(2)
            plt.close()
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


