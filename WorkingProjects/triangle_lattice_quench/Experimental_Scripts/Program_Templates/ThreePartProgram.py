from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF
from WorkingProjects.triangle_lattice_quench.Helpers.rotate_SS_data import *


class ThreePartProgramOneFF(FFAveragerProgramV2):
    def _initialize(self, cfg):
        # Qubit (one Gaussian envelope per pulse, indexed by qubit_pulse position)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])  # Qubit

        # Readout (MUX): resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        FF.FFDefinitions(self)

        for i in range(len(self.cfg["qubit_gains"])):
            self.add_gauss(ch=cfg["qubit_ch"], name=f"qubit{i}", sigma=cfg["sigma"][i], length=4 * cfg["sigma"][i])
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=90, gain=cfg["qubit_gains"][i])
        self.qubit_total_length_us = 4 * sum(cfg["sigma"])

    def _body(self, cfg):
        # 1: FFPulses
        FF_Delay_time = 9
        self.FFPulses(self.FFPulse, 1.01 + self.qubit_total_length_us + FF_Delay_time)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 + FF_Delay_time if i==0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        self.delay_auto()
        # 2: FFExpt
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"],
                             waveform_label='FFExpts')
        self.delay_auto()

        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3) # Overshoot to freeze dynamics
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        # FF.FFPulses_compensated(self, self.FFReadouts, self.FFExpts, self.cfg["res_length"])
        # self.delay(0.1)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])

        # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3)

        ###     If waveform memory becomes a problem, change this code to use the same waveform
        ###         but invert the gain on the generator channel.
        IQ_Array_Negative = [None if array is None else -1 * np.array(array) for array in self.cfg["IDataArray"]]
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_samples"], -1 * self.FFReadouts, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + FF_Delay_time + 1.1)
        self.delay_auto()

class ThreePartProgramTwoFF(ThreePartProgramOneFF):
    def _body(self, cfg):
        # 1: FFPulses
        FF_Delay_time = 9
        self.delay_auto()
        self.FFPulses(self.FFPulse, self.qubit_total_length_us + 1.01 + FF_Delay_time)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1.0 + FF_Delay_time if i==0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_ )
        # 2: FFExpt
        assert 'expt_samples' not in self.cfg, "Use expt_samples1 and expt_samples2 instead."
        assert 'IDataArray'  not in self.cfg, "Use IDataArray1 and IDataArray2 instead."

        # print(self.cfg["IDataArray1"], self.cfg["IDataArray2"])
        concat_IQarray = [np.concatenate([arr1[:self.cfg["expt_samples1"]], arr2])
                                    for arr1, arr2, in zip(self.cfg["IDataArray1"], self.cfg["IDataArray2"])]
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples1"]+self.cfg["expt_samples2"],
                             self.FFPulse, IQPulseArray=concat_IQarray, waveform_label='FFExpts')
        self.delay_auto()


        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3) # Overshoot to freeze dynamics
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        # self.delay(1)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3)

        ###     If waveform memory becomes a problem, change this code to use the same waveform
        ###         but invert the gain on the generator channel.
        IQ_Array_Negative = [None if array is None else -1 * np.array(array) for array in concat_IQarray]
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_samples1"]+self.cfg["expt_samples2"], -1 * self.FFReadouts, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + 1.01 + FF_Delay_time)
        self.delay_auto()

# class ThreePartProgramTwoFF(ThreePartProgramOneFF):
#     def body(self):
#         # 1: FFPulses
#         self.sync_all(gen_t0=self.gen_t0)
#         self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
#         for i in range(len(self.cfg["qubit_gains"])):
#             gain_ = self.cfg["qubit_gains"][i]
#             freq_ = self.freq2reg(self.cfg["qubit_freqs"][i], gen_ch=self.cfg["qubit_ch"])
#             time_ = self.us2cycles(1) if i == 0 else 'auto'
#
#             self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
#                                  gain=gain_,
#                                  waveform="qubit", t=time_)
#         # 2: FFExpt
#         assert 'expt_samples' not in self.cfg, "Use expt_samples1 and expt_samples2 instead."
#         assert 'IDataArray'  not in self.cfg, "Use IDataArray1 and IDataArray2 instead."
#
#         concat_IQarray = [np.concatenate([arr1[:self.cfg["expt_samples1"]], arr2])
#                             for arr1, arr2, in zip(self.cfg["IDataArray1"], self.cfg["IDataArray2"])]
#         # fig, ax = plt.subplots()
#         # for i, arr in enumerate(concat_IQarray):
#         #     ax.plot(arr,marker='o', label=i)
#         # ax.legend()
#         # plt.show(block=True)
#         self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples1"]+self.cfg["expt_samples2"],
#                              self.FFPulse, IQPulseArray=concat_IQarray)
#         self.sync_all(gen_t0=self.gen_t0)
#
#
#         if 'ReadoutIQ' in self.cfg:
#             print("Using loaded FFReadouts envelope")
#             self.FFPulses_direct(self.FFReadouts, int(3.0 / 0.145e-3 // 16 * 16 + 16),
#                                  [g[-1] for g in concat_IQarray], IQPulseArray=self.cfg['ReadoutIQ'], waveform_label='FFRO')
#             # Not enough waveform memory for the entire 20 us res_length so compensate the first 3 us
#         self.FFPulses(self.FFReadouts, self.cfg["res_length"]-3.0)
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=self.cfg["ro_chs"], pins=[0],
#                      adc_trig_delay=self.us2cycles(self.cfg["adc_trig_delay"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(10))
#
#         # End: invert FF pulses to ensure pulses integrate to 0
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
#         # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3)
#
#         ###     If waveform memory becomes a problem, change this code to use the same waveform
#         ###         but invert the gain on the generator channel.
#         IQ_Array_Negative = [None if array is None else -1 * np.array(array) for array in concat_IQarray]
#         self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_samples1"]+self.cfg["expt_samples2"], - 1 * self.FFReadouts,
#                              IQPulseArray=IQ_Array_Negative,
#                              waveform_label='FF2')
#         self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
#
#

