from qick import RAveragerProgram
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
import time


class Qubit_ef_spectroscopy(RAveragerProgram):
    """
    This class represents a RAveragerProgram for doing e-f spectroscopy on the qubit.
    First, we perform a g-e pi pulse, followed by a gaussian pulse scanning for the e-f frequency.
    """
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Data labels
        self.cfg["x_pts_label"] = "qubit freq (MHz)"
        self.cfg["y_pts_label"] = "ADC amplitude"

        # set the start, step, and other parameters
        self.cfg["start"] = self.cfg["qubit_ef_freq_start"]
        self.cfg["step"] = self.cfg["qubit_ef_freq_step"]
        self.cfg["expts"] = self.cfg["qubit_ef_freq_num"]

        # Register pages
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])              # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")      # get gain register for qubit_ch
        self.r_freq = self.sreg(self.cfg["qubit_ch"], "freq") # frequency register on qubit channel

        ###
        # To see list of all registers: self.pulse_registers
        # We need an additional register to use for the e-g frequency.
        # I don't know how to check the list of registers properly, so I will just use an arbitrary number that doesn't
        # match any of the ones listed above for channel 0 or 1, which are readout and qubit, resp.
        ###

        # Taken from https://github.com/conniemiao/slab_rfsoc_expts/blob/d62c098f55bc4745bfb8e9ffa41d5bb49085b11e/experiments/single_qubit/pulse_probe_ef_spectroscopy.py#L99
        self.r_freq_ef = 4

        # Declare channels
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        # Define frequency in dac register values
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_ge_freq = self.freq2reg(cfg["qubit_ge_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.safe_regwi(self.q_rp, self.r_freq_ef, self.freq2reg(self.cfg["start"], gen_ch = self.cfg["qubit_ch"])) # Set the ef frequency register to start at the correct value

        # Define qubit pulse: gaussian
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit")
        # Define qubit pulse: flat top
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_ge_freq, phase=0,
                                     gain=cfg["qubit_ge_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                     mode="periodic")
        # Qubit pulse style is not one of the known ones
        else:
            print("define gaussian or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):
        # Define ge frequency
        ge_freq = self.freq2reg(self.cfg["qubit_ge_freq"], gen_ch=self.cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        # Set up and play g-e pi pulse
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
                                 waveform="qubit")
        self.pulse(ch=self.cfg["qubit_ch"])

        # Change the qubit-frequency-register named "r_freq" value to e-f frequency
        self.mathi(self.q_rp, self.r_freq, self.r_freq_ef, '+', 0)

        # play ef probe pulse
        self.pulse(ch = self.cfg['qubit_ch'])

        self.sync_all(self.us2cycles(0.05)) # align channels and wait /

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq_ef, self.r_freq_ef, '+', self.freq2reg(self.cfg["step"], gen_ch = self.cfg["qubit_ch"])) # update frequency of the ef spectroscopy probe

    ### Defining the template config
    config_template = {
        # Voltage of the YOKO
        "yokoVoltage": 0,

        # Cavity Parameters
        "read_pulse_style": "const",
        "read_length": 10,  # [us]
        "read_pulse_gain": 4000,  # [DAC units]
        "read_pulse_freq": 5753.5,  # [MHZ]

        # Qubit g-e transition parameters
        "qubit_ge_freq": 4655,  # [MHz]
        "qubit_ge_gain": 6500,  # Gain for pi pulse [DAC units]

        # Qubit e-f transition parameters
        "qubit_ef_freq_start": 4655 - 195,  # [MHz}
        "qubit_ef_freq_step": 0.4, # [MHz]
        "qubit_ef_freq_num": 101,  # number of points

        # Pulse-style parameters
        "qubit_pulse_style": "arb", # Gaussian
        "qubit_length": None,  # [us], necessary for "const" style
        "sigma": 0.2,  # [us]
        "flat_top_length": None, # [us], necessary for flat-top style pulses

        # Averaging parameters
        "relax_delay": 500,  # [us]
        "reps": 100,  # number of averages of every experiment
        "sets": 10,   # Number of times to perform the experiment
    }





# ====================================================== #
# For backwards compatibility with non-GUI usage

class Qubit_ef_spectroscopy_experiment(ExperimentClass):
    """
    The following class is a wrapper aroung the Qubit_ef_spectroscopy class.
    This class is called to control and talk with the Qubit_ef_spectroscopy class
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = Qubit_ef_spectroscopy(self.soccfg, self.cfg)
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
        max_indx = np.argmax(avgsig)
        print(x_pts[max_indx])
        avgphase = np.remainder(np.angle(sig,deg=True)+360,360)
        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="Phase")
        axs[0].set_ylabel("Degrees")
        axs[0].set_xlabel("e-f spec frequency (MHz)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="Magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("e-f spec frequency (MHz)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("e-f spec frequency (MHz)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("e-f spec frequency (MHz)")
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


