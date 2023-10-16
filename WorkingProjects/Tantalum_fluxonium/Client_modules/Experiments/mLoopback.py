from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from qick import helpers

class LoopbackProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]

        # set the nyquist zone
        self.declare_gen(ch=cfg["res_ch"], nqz=1)

        # configure the readout lengths and downconversion frequencies (ensuring it is an available DAC frequency)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.cfg["readout_length"],
                                 freq=self.cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        # convert frequency to DAC frequency (ensuring it is an available ADC frequency)
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        phase = self.deg2reg(cfg["res_phase"], gen_ch=res_ch)
        gain = cfg["pulse_gain"]
        self.default_pulse_registers(ch=res_ch, freq=freq, phase=phase, gain=gain)

        style = self.cfg["pulse_style"]

        if style in ["flat_top", "arb"]:
            sigma = cfg["sigma"]
            self.add_gauss(ch=res_ch, name="measure", sigma=sigma, length=sigma * 5)

        if style == "const":
            self.set_pulse_registers(ch=res_ch, style=style, length=cfg["length"])
        elif style == "flat_top":
            # The first half of the waveform ramps up the pulse, the second half ramps down the pulse
            self.set_pulse_registers(ch=res_ch, style=style, waveform="measure", length=cfg["length"])
        elif style == "arb":
            self.set_pulse_registers(ch=res_ch, style=style, waveform="measure")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        # fire the pulse
        # trigger all declared ADCs
        # pulse PMOD0_0 for a scope trigger
        # pause the tProc until readout is done
        # increment the time counter to give some time before the next measurement
        # (the syncdelay also lets the tProc get back ahead of the clock)
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"],
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

        # equivalent to the following:


#         self.trigger(adcs=self.ro_chs,
#                      pins=[0],
#                      adc_trig_offset=self.cfg["adc_trig_offset"])
#         self.pulse(ch=self.cfg["res_ch"])
#         self.wait_all()
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

# ====================================================== #
class Loopback(ExperimentClass):
    """
    Loopback Experiment basic
    """

    # def __init__(self, soc=None, soccfg=None, path='', prefix='data', cfg=None, config_file=None, progress=None):
    #     super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = LoopbackProgram(self.soccfg, self.cfg)
        self.soc.reset_gens()  # clear any DC or periodic values on generators
        iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'iq_list': iq_list}}
        self.data=data
        return data

    def display(self, data=None, fit=True, **kwargs):
        if data is None:
            data = self.data
        plt.figure(1)
        for ii, iq in enumerate(data['data']['iq_list']):
            plt.plot(iq[0], label="I value, ADC %d" % (data['config']['ro_chs'][ii]))
            plt.plot(iq[1], label="Q value, ADC %d" % (data['config']['ro_chs'][ii]))
            plt.plot(np.abs(iq[0] + 1j * iq[1]), label="mag, ADC %d" % (data['config']['ro_chs'][ii]))
        plt.ylabel("a.u.")
        plt.xlabel("Clock ticks")
        plt.title("Averages = " + str(data['config']["soft_avgs"]))
        plt.legend()
        plt.savefig(self.iname)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


