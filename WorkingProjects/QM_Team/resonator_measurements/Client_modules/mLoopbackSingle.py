from qick import *
from socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Experiment import ExperimentClass
import datetime


class LoopbackProgramSingle(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=1, mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])

        style = self.cfg["pulse_style"]
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
            0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))

        if style in ["flat_top", "arb"]:
            sigma = cfg["sigma"]
            nsigma = 5
            samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
            idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
                                  si=sigma * samples_per_clock,
                                  length=sigma * samples_per_clock * nsigma,
                                  maxv=np.iinfo(np.int16).max - 1)
            self.add_pulse(ch=res_ch, name="measure", idata=idata)

        if style == "const":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     length=cfg["length"])
        elif style == "flat_top":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure", length=cfg["length"])
        elif style == "arb":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
        # control should wait until the readout is over
        self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
        self.sync_all(self.cfg["relax_delay"])  # sync all channels


# ====================================================== #

class LoopbackSingle(ExperimentClass):
    """
    Loopback Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = LoopbackProgramSingle(self.soccfg, self.cfg)
        self.soc.reset_gens()  # clear any DC or periodic values on generators
        iq_list = prog.acquire(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'iq_list': iq_list}}
        self.data=data
        return data

    def acquire_decimated(self, progress=False, debug=False):
        prog = LoopbackProgramSingle(self.soccfg, self.cfg)
        self.soc.reset_gens()  # clear any DC or periodic values on generators
        iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'iq_list': iq_list}}
        self.data=data
        return data

    def display_decimated(self, data=None, fit=True, **kwargs):
        if data is None:
            data = self.data

        hfig, hax = plt.subplots(4, 1, figsize = (10, 10), dpi = 150)
        plt.subplots_adjust(hspace = 0.4, wspace=0.4)
        for ii, iq in enumerate(data['data']['iq_list']):
            hax[ii].plot(iq[0], label="I value, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].plot(iq[1], label="Q value, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].plot(np.abs(iq[0] + 1j * iq[1]), label="mag, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].set_ylabel("a.u.")
            hax[ii].set_xlabel("Clock ticks")
            hax[ii].legend(loc='best', bbox_to_anchor = (1,1))
        hax[0].set_title("Averages = " + str(data['config']["soft_avgs"]))
        plt.savefig(self.iname, bbox_inches='tight')

    def display(self, data=None, fit=True, **kwargs):
        data = data['data']
        amps = abs(data['iq_list'][0] + 1j * data['iq_list'][1])
        amps_dB = 20*np.log10(amps)
        print("Linear amplitudes are {0} ADC units".format(amps))
        print("20*Log amplitudes are {0} ADC units".format(amps_dB))

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


