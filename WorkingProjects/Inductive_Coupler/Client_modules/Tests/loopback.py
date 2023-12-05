from qick import *
from q4diamond.Client_modules.socProxy import soc, soccfg
import matplotlib.pyplot as plt
import numpy as np


class LoopbackProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # define registers for sweep
        self.rp = self.ch_page(gen_ch=cfg["res_chs"][0])
        self.r_addr = self.sreg(gen_ch=cfg["res_chs"][0], name='addr')

        for res_ch, ch in zip(cfg["res_chs"], cfg["ro_chs"]):
            # configure the readout lengths and downconversion frequencies (ensuring it is an available DAC frequency)
            self.declare_readout(ch=ch, length=self.cfg["readout_length"],
                                 freq=self.cfg["pulse_freq"], gen_ch=res_ch)

            # set the nyquist zone
            self.declare_gen(ch=res_ch, nqz=1)

            # convert frequency to DAC frequency (ensuring it is an available ADC frequency)
            freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=ch)
            phase = self.deg2reg(cfg["res_phase"], gen_ch=res_ch)
            gain = cfg["pulse_gain"]
            self.default_pulse_registers(ch=res_ch, freq=freq, phase=phase, gain=gain)

            buf = 10
            IQPulse = np.concatenate([16000 * np.ones(buf*16 - 1), 32000 * np.ones(16*cfg["length"] + 1)])
            self.add_pulse(ch=res_ch, name="arblen", idata=IQPulse, qdata=np.zeros_like(IQPulse))
            IQPulse = np.concatenate([16000 * np.ones(buf*16 - 8), 32000 * np.ones(16*cfg["length"] + 8)])
            self.add_pulse(ch=res_ch, name="arblen0", idata=IQPulse, qdata=np.zeros_like(IQPulse))
            self.set_pulse_registers(ch=res_ch, style='arb', waveform="arblen", outsel="input")

        # self.set_pulse_registers(ch=res_ch, style="const", length=cfg["length"])

        # !--- here I change the address register for res_ch 0 to play the second pulse that I've added ---!
        # self.safe_regwi(self.rp, self.r_addr, 0)  # cannot set until pulses have been defined!
        self.safe_regwi(self.rp, self.r_addr, cfg["length"] + buf)  # cannot set until pulses have been defined!

        # !--- here I attempt to change the pulse length with registers ---!
        self.res_r_mode=self.sreg(cfg["res_chs"][0], "mode")  # length register is packed in the last 16 bits of mode register
        # self.res_r_length = 1 # declare a register for keeping track of the flat top length, (used in sync() after the pulse)
        # self.safe_regwi(self.rp, self.res_r_length, 100)
        self.mathi(self.rp, self.res_r_mode, self.res_r_mode, '-', 6)

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        # fire the pulse
        self.greg = self.sreg(gen_ch=self.cfg['res_chs'][0], name='gain')
        self.greg1 = self.sreg(gen_ch=self.cfg['res_chs'][1], name='gain')

        self.sync_all(dac_t0=self.cfg["delays"])
        # trigger all declared ADCs
        self.trigger(adcs=self.ro_chs,
                     pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])

        # pulse DACs for a scope trigger
        for res_ch in self.cfg["res_chs"]:
            self.pulse(ch=res_ch)
        # for res_ch in self.cfg["res_chs"]:
        #     self.pulse(ch=res_ch, t='auto')

        # !--- in this block I change the gain register to add a pulse of opposite sign ---!
        self.mathi(self.ch_page(gen_ch=self.cfg['res_chs'][0]), self.greg, self.greg, '*', -1)
        self.mathi(self.ch_page(gen_ch=self.cfg['res_chs'][1]), self.greg1, self.greg1, '*', -1)
        self.mathi(self.rp, self.res_r_mode, self.res_r_mode, '+', 6)
        self.pulse(ch=self.cfg["res_chs"][0])
        self.pulse(ch=self.cfg["res_chs"][1])


        # pause the tProc until readout is done
        self.wait_all()
        # increment the time counter to give some time before the next measurement
        # (the syncdelay also lets the tProc get back ahead of the clock)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


class LoopbackProgramR(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        # define registers for sweep
        self.rp = self.ch_page(gen_ch=cfg["res_chs"][0])
        self.r_addr = self.sreg(gen_ch=cfg["res_chs"][0], name='addr')

        for res_ch, ch in zip(cfg["res_chs"], cfg["ro_chs"]):
            # configure the readout lengths and downconversion frequencies (ensuring it is an available DAC frequency)
            self.declare_readout(ch=ch, length=self.cfg["readout_length"],
                                 freq=self.cfg["pulse_freq"], gen_ch=res_ch)

            # set the nyquist zone
            self.declare_gen(ch=res_ch, nqz=1)

            # convert frequency to DAC frequency (ensuring it is an available ADC frequency)
            freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
            phase = self.deg2reg(cfg["res_phase"], gen_ch=res_ch)
            gain = cfg["pulse_gain"]
            self.default_pulse_registers(ch=res_ch, freq=freq, phase=phase, gain=gain)

            IQPulse = 32000 * np.ones(16*cfg["length"])
            self.add_pulse(ch=res_ch, name="arblen", idata=IQPulse, qdata=np.zeros_like(IQPulse))
            self.set_pulse_registers(ch=res_ch, style='arb', waveform="arblen", outsel="input")

            for i in range(cfg['expts']):
                IQPulse[:i * 16] = 0
                self.add_pulse(ch=res_ch, name="arblen{}".format(i), idata=IQPulse, qdata=np.zeros_like(IQPulse))

        self.safe_regwi(self.rp, self.r_addr, 0)  # cannot set until pulses have been defined!
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

        # pause the tProc until readout is done
        self.wait_all()
        # increment the time counter to give some time before the next measurement
        # (the syncdelay also lets the tProc get back ahead of the clock)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        # jump by self.cfg['step'] entire pulses
        self.mathi(self.rp, self.r_addr, self.r_addr, '+', self.cfg['step'] * self.cfg['length'])


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
          'expts': 5,
          }


###################
# Try it yourself !
###################
# Standard program to see entire waveform
config['reps'] = 1
prog = LoopbackProgram(soccfg, config)
iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=False, debug=False)

# Plot results.
plt.figure(1)
for ii, iq in enumerate(iq_list):
    plt.plot(iq[0], label="I value, ADC %d (DAC %d)"%(config['ro_chs'][ii], config['res_chs'][ii]))
    # plt.plot(iq[1], label="Q value, ADC %d (DAC %d)"%(config['ro_chs'][ii], config['res_chs'][ii]))
    plt.plot(np.abs(iq[0]+1j*iq[1]), label="mag, ADC %d (DAC %d)"%(config['ro_chs'][ii], config['res_chs'][ii]))
plt.ylabel("a.u.")
plt.xlabel("Clock ticks")
plt.title("Averages = " + str(config["soft_avgs"]))
plt.legend()


# Not sure what this program is, can you use acquire_decimated with RAveragerProgram in a useful way?
# prog = LoopbackProgramR(soccfg, config)
# iq_lists = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
# print(iq_lists[0].transpose())
#
# # Plot results.
# plt.figure(2)
# for jj, iq_list in enumerate(iq_lists):
#     plt.plot(iq_list.transpose()[0], label="I value, ADC %d"%(config['ro_chs'][jj]))
#     plt.plot(iq_list.transpose()[1], label="Q value, ADC %d"%(config['ro_chs'][jj]))
#     plt.plot(np.abs(iq_list.transpose()[0]+1j*iq_list.transpose()[1]), label="mag, ADC %d"%(config['ro_chs'][jj]))
# plt.ylabel("a.u.")
# plt.xlabel("Clock ticks")
# plt.title("Reps = " + str(config["reps"]) + " Rounds = " + str(config["rounds"]))
# plt.legend()



# Using RAveragerProgram while iterating through waveforms
# prog = LoopbackProgramR(soccfg, config)
# x_pts, avgi, avgq = prog.acquire(soc, load_pulses=True, progress=True, debug=False)
# print(x_pts)
#
# # Plot results.
# plt.figure(2)
# for ii, (iai, iaq) in enumerate(zip(avgi, avgq)):
#     # plt.plot(x_pts, iai[0], label="ADC %d, DAC %d" % (config['ro_chs'][ii], config['res_chs'][ii]))
#     # plt.plot(iq[1], label="Q value, ADC %d, DAC %d" % (config['ro_chs'][ii], config['res_chs'][ii]))
#     plt.plot(x_pts, np.abs(iai[0] + 1j * iaq[0]), label="mag, ADC %d, DAC %d" % (config['ro_chs'][ii], config['res_chs'][ii]))
# plt.ylabel("a.u.")
# plt.xlabel("Waveform number")
# plt.title("Reps = " + str(config["reps"]) + " Rounds = " + str(config["rounds"]))
# plt.legend()





# # Varying frequency, looking at IQ response. Use 'const' pulse
# fs1 = np.linspace(0, 0.02, 201)
# iq_lists = [[], []]
# config['reps'] = 100
# config['readout_length'] = 10000
# for f in fs1:
#     config['pulse_freq'] = f + 500
#     prog = LoopbackProgram(soccfg, config)
#     iq_list = prog.acquire(soc, load_pulses=True, progress=False, debug=False)
#     iq_lists[0].append([iq_list[0][0][0], iq_list[1][0][0]])
# fs2 = np.linspace(0, 1, 51)
# for f in fs2:
#     config['pulse_freq'] = f + 500
#     prog = LoopbackProgram(soccfg, config)
#     iq_list = prog.acquire(soc, load_pulses=True, progress=False, debug=False)
#     iq_lists[1].append([iq_list[0][1][0], iq_list[1][1][0]])
#
# # Plot results.
# fig, axes = plt.subplots(1, 2, sharey=True)
# axes[0].plot(fs1, np.array(iq_lists[0]).transpose()[0], label="I value, ADC %d (DAC %d)"%(config['ro_chs'][0], config['res_chs'][0]))
# axes[0].plot(fs1, np.array(iq_lists[0]).transpose()[1], label="Q value, ADC %d (DAC %d)"%(config['ro_chs'][0], config['res_chs'][0]))
# axes[0].set_xlabel("Frequency (MHz), +500 MHz")
# axes[0].legend()
# axes[1].plot(fs2, np.array(iq_lists[1]).transpose()[0], label="I value, ADC %d (DAC %d)"%(config['ro_chs'][1], config['res_chs'][1]))
# axes[1].plot(fs2, np.array(iq_lists[1]).transpose()[1], label="Q value, ADC %d (DAC %d)"%(config['ro_chs'][1], config['res_chs'][1]))
# axes[1].set_xlabel("Frequency (MHz), +500 MHz")
# axes[1].legend()
# plt.ylabel("a.u.")
# plt.suptitle("Averages = " + str(config["soft_avgs"]) + " Reps = " + str(config['reps']))



plt.show()
