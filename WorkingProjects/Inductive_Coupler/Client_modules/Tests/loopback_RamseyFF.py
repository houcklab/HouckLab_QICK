from qick import *
from q4diamond.Client_modules.socProxy import soc, soccfg
import matplotlib.pyplot as plt
import numpy as np


class LoopbackProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # define registers for sweep
        self.rps = []
        self.r_gains = []
        self.r_addr = self.sreg(gen_ch=cfg["res_chs"][0], name='addr')

        for i, (res_ch, ch) in enumerate(zip(cfg["res_chs"], cfg["ro_chs"])):
            # configure the readout lengths and downconversion frequencies (ensuring it is an available DAC frequency)
            self.declare_readout(ch=ch, length=self.cfg["readout_length"],
                                 freq=self.cfg["pulse_freq"], gen_ch=res_ch)
            # set the nyquist zone
            self.declare_gen(ch=res_ch, nqz=1)

            self.rps.append(self.ch_page(gen_ch=res_ch))
            self.r_gains.append(self.sreg(gen_ch=res_ch, name='gain'))

            # convert frequency to DAC frequency (ensuring it is an available ADC frequency)
            freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=ch)
            phase = self.deg2reg(cfg["res_phase"], gen_ch=res_ch)
            gain = cfg["pulse_gain"]
            self.default_pulse_registers(ch=res_ch, freq=freq, phase=phase, gain=gain)

            if i == 0:  # load all of the pulses onto the channel register
                buf = 10
                for j in range(16):
                    IQPulse = np.concatenate([16000 * np.ones(buf*16 - j), 32000 * np.ones(16*cfg["length"] + j)])
                    self.add_pulse(ch=res_ch, name="arblen"+str(j), idata=IQPulse, qdata=np.zeros_like(IQPulse))
                self.set_pulse_registers(ch=res_ch, style='arb', waveform="arblen0", outsel="input")
            else:
                IQPulse = np.concatenate([16000 * np.ones(buf*16), 32000 * np.ones(16*cfg["length"])])
                self.add_pulse(ch=res_ch, name="arblen", idata=IQPulse, qdata=np.zeros_like(IQPulse))
                self.set_pulse_registers(ch=res_ch, style='arb', waveform="arblen", outsel="input")


        # !--- here I set the address register for res_ch 0 to play the first pulse that I've added ---!
        self.safe_regwi(self.rps[0], self.r_addr, 0)  # cannot set until pulses have been defined!

        # !--- here I set the pulse length with registers to be the shortest possible ---!
        self.res_r_mode = self.sreg(cfg["res_chs"][0], "mode")  # length reg in last 16 bits of mode register
        self.mathi(self.rps[0], self.res_r_mode, self.res_r_mode, '-', cfg["length"] + buf - 3)  # shortest length

        # !--- set a register to determine pulse address and length ---!
        self.safe_regwi(self.rps[0], 1, self.cfg['number'] // 16)  # integer division, determines pulse length
        self.safe_regwi(self.rps[0], 2, self.cfg['number'] % 16)  # remainder, determines pulse address
        self.memwi(self.rps[0], 1, 123)  # save value to memory for readout/debugging
        self.memwi(self.rps[0], 2, 124)  # save value to memory for readout/debugging
        self.mathi(self.rps[0], 2, 2, '*', cfg["length"] + buf)  # convert to an actual address


        # # !--- here I set a useful counter for iterating through pulses ---!
        # self.safe_regwi(self.rps[0], 1, 0)  # counting pulse number
        # self.safe_regwi(self.rps[0], 2, 16)  # wraparound period
        #
        # # !--- here I set the address register for res_ch 0 to play the first pulse that I've added ---!
        # self.safe_regwi(self.rps[0], self.r_addr, 0)  # cannot set until pulses have been defined!
        #
        # # !--- here I set the pulse length with registers to be the shortest possible ---!
        # self.res_r_mode = self.sreg(cfg["res_chs"][0], "mode")  # length reg in last 16 bits of mode register
        # self.mathi(self.rps[0], self.res_r_mode, self.res_r_mode, '-', cfg["length"] + buf - 3)  # shortest length
        #
        #
        # # jump counter by step and address counter by step * pulse length
        # self.mathi(self.rps[0], 1, 1, '+', self.cfg['step'])
        # self.mathi(self.rps[0], self.r_addr, self.r_addr, '+', self.cfg['step'] * (self.cfg['length'] + buf))
        #
        # # if counter >= 16, reset to 0 and add one to length counter
        # self.condj(self.rps[0], 1, '<', 2, 'NO_WRAP')
        # self.safe_regwi(self.rps[0], 1, 0)
        # self.safe_regwi(self.rps[0], self.r_addr, 0)  # reset pulse address to beginning
        # self.mathi(self.rps[0], self.res_r_mode, self.res_r_mode, '+', 1)  # increase length by 1 clock cycle
        # self.label('NO_WRAP')
        # self.memwi(self.rps[0], 1, 123)  # save value to memory for readout/debugging
        # self.memwi(self.rps[0], self.res_r_mode, 124)  # save value to memory for readout/debugging


        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        # set the pulse
        self.math(self.rps[0], self.res_r_mode, self.res_r_mode, '+', 1)  # set pulse length
        self.math(self.rps[0], self.r_addr, self.r_addr, '+', 2)  # jump to pulse address

        # fire the pulse
        self.sync_all(dac_t0=self.cfg["delays"])
        # trigger all declared ADCs
        self.trigger(adcs=self.ro_chs,
                     pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])

        # pulse DACs for a scope trigger
        for res_ch in self.cfg["res_chs"]:
            self.pulse(ch=res_ch)

        # # !--- in this block I change the gain register to add a pulse of opposite sign ---!
        # for rp, r_g, res_ch in zip(self.rps, self.r_gains, self.cfg['res_chs']):
        #     self.mathi(rp, r_g, r_g, '*', -1)
        #     self.pulse(res_ch)

        # pause the tProc until readout is done
        self.wait_all()
        # increment the time counter to give some time before the next measurement
        # (the syncdelay also lets the tProc get back ahead of the clock)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


class LoopbackProgramR(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # define registers for sweep
        self.rps = []
        self.r_gains = []
        self.r_addr = self.sreg(gen_ch=cfg["res_chs"][0], name='addr')

        for i, (res_ch, ch) in enumerate(zip(cfg["res_chs"], cfg["ro_chs"])):
            # configure the readout lengths and downconversion frequencies (ensuring it is an available DAC frequency)
            self.declare_readout(ch=ch, length=self.cfg["readout_length"],
                                 freq=self.cfg["pulse_freq"], gen_ch=res_ch)
            # set the nyquist zone
            self.declare_gen(ch=res_ch, nqz=1)

            self.rps.append(self.ch_page(gen_ch=res_ch))
            self.r_gains.append(self.sreg(gen_ch=res_ch, name='gain'))

            # convert frequency to DAC frequency (ensuring it is an available ADC frequency)
            freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=ch)
            phase = self.deg2reg(cfg["res_phase"], gen_ch=res_ch)
            gain = cfg["pulse_gain"]
            self.default_pulse_registers(ch=res_ch, freq=freq, phase=phase, gain=gain)

            if i == 0:  # load all of the pulses onto the channel register
                self.buf = 3
                for j in range(16):
                    IQPulse = np.concatenate([0 * np.ones(16 * self.buf - j),
                                              32000 * np.ones(16 * cfg["length"] + j)])
                    self.add_pulse(ch=res_ch, name="arblen"+str(j), idata=IQPulse, qdata=np.zeros_like(IQPulse))
                self.set_pulse_registers(ch=res_ch, style='arb', waveform="arblen0", outsel="input")
            else:
                IQPulse = np.concatenate([0 * np.ones(16 * self.buf),
                                          32000 * np.ones(16 * cfg["length"])])
                self.add_pulse(ch=res_ch, name="arblen", idata=IQPulse, qdata=np.zeros_like(IQPulse))
                self.set_pulse_registers(ch=res_ch, style='arb', waveform="arblen", outsel="input")

        # !--- here I set a useful counter for iterating through pulses ---!
        self.safe_regwi(self.rps[0], 1, 0)  # counting pulse number
        self.safe_regwi(self.rps[0], 2, 16)  # wraparound period

        # !--- here I set the address register for res_ch 0 to play the first pulse that I've added ---!
        self.safe_regwi(self.rps[0], self.r_addr, 0)  # cannot set until pulses have been defined!

        # !--- here I set the pulse length with registers to be the shortest possible ---!
        self.res_r_mode = self.sreg(cfg["res_chs"][0], "mode")  # length reg in last 16 bits of mode register
        self.mathi(self.rps[0], self.res_r_mode, self.res_r_mode, '-', cfg["length"] + self.buf - 3)  # shortest length

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        # fire the pulse
        self.sync_all(dac_t0=self.cfg["delays"])
        # trigger all declared ADCs
        self.trigger(adcs=self.ro_chs,
                     pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])

        # pulse DACs for a scope trigger
        for res_ch in self.cfg["res_chs"]:
            self.pulse(ch=res_ch)

        # # !--- in this block I change the gain register to add a pulse of opposite sign ---!
        # for rp, r_g, res_ch in zip(self.rps, self.r_gains, self.cfg['res_chs']):
        #     self.mathi(rp, r_g, r_g, '*', -1)
        #     self.pulse(res_ch)

        # pause the tProc until readout is done
        self.wait_all()
        # increment the time counter to give some time before the next measurement
        # (the syncdelay also lets the tProc get back ahead of the clock)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        # jump counter by step and address counter by step * pulse length
        self.mathi(self.rps[0], 1, 1, '+', self.cfg['step'])
        self.mathi(self.rps[0], self.r_addr, self.r_addr, '+', self.cfg['step'] * (self.cfg['length'] + self.buf))

        # if counter >= 16, reset to 0 and add one to length counter
        self.condj(self.rps[0], 1, '<', 2, 'NO_WRAP')
        self.safe_regwi(self.rps[0], 1, 0)
        self.safe_regwi(self.rps[0], self.r_addr, 0)  # reset pulse address to beginning
        self.mathi(self.rps[0], self.res_r_mode, self.res_r_mode, '+', 1)  # increase length by 1 clock cycle
        self.label('NO_WRAP')

        self.memwi(self.rps[0], 1, 123)
        self.memwi(self.rps[0], self.res_r_mode, 124)


config = {"res_chs": [4, 1],  # --Fixed
          "ro_chs": [0, 1],  # --Fixed
          "reps": 100,  # --Fixed
          "rounds": 10,  # --Fixed
          "relax_delay": 2.0,  # --us
          "res_phase": 0,  # --degrees
          "length": 10,  # [Clock ticks]

          "readout_length": 50,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks

          "pulse_gain": 500,  # [DAC units]
          # Try varying pulse_gain from 500 to 30000 DAC units

          "pulse_freq": 0,  # [MHz]
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "adc_trig_offset": 185,  # [Clock ticks]
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "delays": [6] * 4 + [0] * 3,
          "soft_avgs": 10000,

          "start": 0,  # cycles, pulse width
          "step": 1,
          'expts': 50,
          }


###################
# Try it yourself !
###################
# Standard program to see entire waveform
# plt.figure(1)
# config['reps'] = 1
# config['number'] = 0
#
# for n in [1, 15, 100]:
#     config['number'] = n
#     prog = LoopbackProgram(soccfg, config)
#     iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
#     soc.load_bin_program(prog.compile())
#     # Start tProc.
#     soc.tproc.start()
#     print(soc.tproc.single_read(addr=123))#, n // 16)
#     print(soc.tproc.single_read(addr=124))#, n % 16)
#     for ii, iq in enumerate(iq_list):
#         plt.plot(iq[0],
#                  label="I, ref" if ii == 1 else "I, len %d (pulse# %d)" % (3 + n // 16, n % 16),
#                  c='k' if ii == 1 else None)
#         # plt.plot(iq[1], label="Q value, ADC %d (DAC %d)"%(config['ro_chs'][ii], config['res_chs'][ii]))
#         # plt.plot(np.abs(iq[0]+1j*iq[1]), label="mag, ADC %d (DAC %d)"%(config['ro_chs'][ii], config['res_chs'][ii]),
#         #          c='k' if ii==1 else None)
# plt.ylabel("a.u.")
# plt.xlabel("Clock ticks")
# plt.title("Averages = " + str(config["soft_avgs"]))
# plt.legend()



# Using RAveragerProgram while iterating through waveforms
config['reps'] = 100
config['step'] = 1
for n in [1, 8, 15, 100, config['length'] * 16]:
    config['expts'] = n
    prog = LoopbackProgramR(soccfg, config)
    x_pts, avgi, avgq = prog.acquire(soc, load_pulses=True, progress=False, debug=False)
    soc.load_bin_program(prog.compile())
    # Start tProc.
    soc.tproc.start()
    print(soc.tproc.single_read(addr=123))
    print(soc.tproc.single_read(addr=124))

# Plot results.
plt.figure(2)
for ii, (iai, iaq) in enumerate(zip(avgi, avgq)):
    plt.plot(x_pts, iai[0], label="ADC %d, DAC %d" % (config['ro_chs'][ii], config['res_chs'][ii]))
    # plt.plot(iq[1], label="Q value, ADC %d, DAC %d" % (config['ro_chs'][ii], config['res_chs'][ii]))
    # plt.plot(x_pts, np.abs(iai[0] + 1j * iaq[0]), label="mag, ADC %d, DAC %d" % (config['ro_chs'][ii], config['res_chs'][ii]))
plt.ylabel("a.u.")
plt.xlabel("Waveform number")
plt.title("Reps = " + str(config["reps"]) + " Rounds = " + str(config["rounds"]))
plt.legend()





plt.show()
