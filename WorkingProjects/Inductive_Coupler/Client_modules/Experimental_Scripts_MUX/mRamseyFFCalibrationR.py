import datetime

from qick import *
import time
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
import Pyro4.util

class RamseyFFCalRProg(RAveragerProgram):
    def initialize(self):
        # Qubit
        cfg = self.cfg

        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])
        self.pulse_sigma = self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(self.cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)
        self.f_ge = self.freq2reg(self.cfg["f_ge"], gen_ch=self.cfg["qubit_ch"])

        # Readout: resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))


        # Set up fast flux channels: initial gain, interaction gain, time delays, etc.
        FF.FFDefinitions(self)

        # define registers for sweep
        self.rps = []
        self.r_addrs = []
        self.res_r_modes = []
        self.r_gains = []
        for channel in self.FFChannels:
            self.rps.append(self.ch_page(gen_ch=channel))
            self.r_addrs.append(self.sreg(gen_ch=channel, name='addr'))
            self.res_r_modes.append(self.sreg(gen_ch=channel, name="mode"))  # length reg in last 16 bits of mode register
            self.r_gains.append(self.sreg(gen_ch=channel, name='gain'))
        # load waveforms
        # FF.LoadWaveform_initial(self, self.FFReadouts, self.cfg["sigma"] * 4 + 0.103)
        FF.LoadWaveforms(self)
        # FF.LoadWaveform_measure(self)

        for rp, r_addr, res_r_mode in zip(self.rps, self.r_addrs, self.res_r_modes):
            # !--- here I set a useful counter for iterating through pulses ---!
            self.regwi(rp, 1, 0)  # counting pulse number (0 to 15)
            self.regwi(rp, 2, 16)  # wraparound period
            # self.regwi(rp, 2, (self.cfg['FFlength'] // 16 + 2) * 16)  # wraparound period

            # !--- here I set the address register for res_ch 0 to play the first pulse that I've added ---!
            self.regwi(rp, r_addr, 0)  # cannot set until pulses have been defined!
            self.regwi(rp, 3, 0)  # stores value of r_addr because we play multiple pulses

            # !--- here I set the pulse length with registers to be the shortest possible ---!
            self.mathi(rp, res_r_mode, res_r_mode, '-', self.cfg["FFlength"] // 16 - 1)  # shortest len
            self.mathi(rp, 4, res_r_mode, '+', 0)  # stores value of res_r_mode because we play multiple pulses

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)

        # Set FF initial values (same as readout values)
        self.FFPulses(self.FFReadouts, self.cfg["sigma"] * 4 + 0.103)  # Should be 0 anyways

        # Qubit pi/2 pulse
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["pi2_gain"],
                                 waveform="qubit")
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.1))  # play probe pulse

        # Set FF interaction values
        for FFChannel, rp, r_addr, res_r_mode in zip(self.FFChannels, self.rps, self.r_addrs, self.res_r_modes):
            self.set_pulse_registers(ch=FFChannel, freq=0, phase=0, gain=self.soccfg['gens'][FFChannel]['maxv'],
                                     style='arb', waveform="1", outsel="input")
            self.mathi(rp, r_addr, 3, '+', 0)  # restore value of r_addr
            self.mathi(rp, res_r_mode, 4, '+', 0)  # restore value of res_r_mode
            self.pulse(ch=FFChannel)
        # self.memwi(self.rps[3], 22, 130)
        # self.memwi(self.rps[3], 23, 131)
        # self.memwi(self.rps[3], 24, 132)
        # self.memwi(self.rps[3], 25, 133)
        # self.memwi(self.rps[3], 26, 134)
        # self.memwi(self.rps[3], 27, 135)

        # Qubit X or Y pi/2 pulse
        self.sync_all(gen_t0=self.gen_t0)
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=self.deg2reg(self.cfg["SecondPulseAngle"], gen_ch=self.cfg["qubit_ch"]),
                                 gain=self.cfg["pi2_gain"], waveform="qubit")
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.05))  # play probe pulse

        # Measure: set FF readout values and measure qubit
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        # Net-zero-flux FF pulses, timing doesn't matter so much
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        for FFChannel, rp, r_g, r_addr, res_r_mode in zip(self.FFChannels, self.rps, self.r_gains, self.r_addrs,
                                                          self.res_r_modes):
            self.set_pulse_registers(ch=FFChannel, freq=0, phase=0, gain=self.soccfg['gens'][FFChannel]['maxv'],
                                     style='arb', waveform="1", outsel="input")
            self.mathi(rp, r_addr, 3, '+', 0)  # restore value of r_addr
            self.mathi(rp, res_r_mode, 4, '+', 0)  # restore value of res_r_mode
            self.mathi(rp, r_g, r_g, '*', -1)  # swap sign of gain!
            self.pulse(ch=FFChannel)
        self.FFPulses(-1 * self.FFReadouts, self.cfg["sigma"] * 4 + 0.103)  # Should be 0 anyways
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # , gen_t0=self.gen_t0)
        # print("final", self.gen_mgrs[self.FFChannels[0]].pulses)


    def update(self):
        self.memwi(self.rps[3], 1, 123)
        self.memwi(self.rps[3], 2, 124)
        self.memwi(self.rps[3], 3, 126)  # skip address 125
        self.memwi(self.rps[3], 4, 127)

        for i, rp in enumerate(set(self.rps)):  # increment once per page! some channels use the same page
            # jump counter by step and address counter by step * pulse length
            self.mathi(rp, 1, 1, '+', self.cfg['step'])  # FIXME: assumes step == 1
            self.mathi(rp, 3, 3, '+', self.cfg['step'] * (self.cfg['FFlength'] // 16 + 2))

            # if counter >= 16, reset to 0 and add one to length counter
            self.condj(rp, 1, '<', 2, 'NO_WRAP'+str(i))
            # self.condj(rp, 3, '<', 2, 'NO_WRAP'+str(i))
            self.regwi(rp, 1, 0)
            self.regwi(rp, 3, 0)  # reset pulse address to beginning
            self.mathi(rp, 4, 4, '+', 1)  # increase length by 1 clock cycle
            self.label('NO_WRAP'+str(i))

        # self.memwi(self.rps[3], 17, 128)
        # self.memwi(self.rps[3], 18, 129)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)
    def FFPulses_hires(self, list_of_gains, length_dt, t_start='auto', IQPulseArray=None, padval=0, waveform_label = 'FF'):
        FF.FFPulses_hires(self, list_of_gains, length_dt,  t_start = t_start, IQPulseArray=IQPulseArray, padval=padval,
                          waveform_label=waveform_label)
    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None, padval=0,
                       waveform_label='FF'):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains = previous_gains, t_start=t_start, IQPulseArray=IQPulseArray, padval=padval,
                          waveform_label=waveform_label)

class RamseyFFCalR(ExperimentClass):
    """
    Fast-flux calibration using Ramsey
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        prog = RamseyFFCalRProg(self.soccfg, self.cfg)
        print(datetime.datetime.now())
        try:
            t_pts, avgi, avgq = prog.acquire(self.soc, load_pulses=True)
        except:
            print("Pyro traceback:")
            print("".join(Pyro4.util.getPyroTraceback()))
        # self.soc.load_bin_program(prog.compile())
        # Start tProc.
        # self.soc.tproc.start()

        # print("pulse#: ", self.soc.tproc.single_read(addr=123))
        # print("period: ", self.soc.tproc.single_read(addr=124))
        # print("addr:   ", self.soc.tproc.single_read(addr=126))
        # print("mode:   ", self.soc.tproc.single_read(addr=127))
        # # print(self.soc.tproc.single_read(addr=128))
        # # print(self.soc.tproc.single_read(addr=129))
        # print("")
        # print("freq:  ", self.soc.tproc.single_read(addr=130))
        # print("phase: ", self.soc.tproc.single_read(addr=131))
        # print("addr:  ", self.soc.tproc.single_read(addr=132))
        # print("gain:  ", self.soc.tproc.single_read(addr=133))
        # print("mode:  ", self.soc.tproc.single_read(addr=134))
        # print("time:  ", self.soc.tproc.single_read(addr=135))

        # print(prog)
        # print(self.cfg)
        data = {'config': self.cfg, 'data': {'t_pts': t_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data
        t_pts = data['data']['t_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        signal = (avgi + 1j * avgq) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))
        avgi = signal.real
        avgq = signal.imag
        while plt.fignum_exists(num=figNum):  ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(t_pts, avgi, 'o-', label="i", color='orange')
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (clock cycles)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + 'I_Data.png')

    # if plotDisp:
        plt.show(block=False)
        plt.pause(0.1)
    # else:
        fig.clf(True)
        plt.close(fig)

        fig = plt.figure(figNum + 1)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        plt.plot(t_pts, avgq, 'o-', label="q")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (clock cycles)")
        plt.legend()
        plt.title(self.titlename)

        plt.savefig(self.iname[:-4] + 'Q_Data.png')

        # if plotDisp:
        plt.show(block=False)
        plt.pause(0.1)
    # else:
        fig.clf(True)
        plt.close(fig)

        fig = plt.figure(figNum + 2)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        plt.plot(t_pts, np.abs(avgi + 1j * avgq), 'o-', label="Amplitude")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (clock cycles)")
        plt.legend()
        plt.title(self.titlename)

        plt.savefig(self.iname[:-4] + 'Amp_Data.png')

    # if plotDisp:
        plt.show(block=False)
        plt.pause(0.1)
    # else:
        fig.clf(True)
        plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
