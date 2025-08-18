from qick.asm_v2 import AsmV2
from scipy.optimize import curve_fit

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepWaveformAveragerProgram import \
    SweepWaveformAveragerProgram
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *

from math import ceil, floor


class FFvsDriveTimingProgram(FFAveragerProgramV2):
    def __init__(self, *args, **kwargs):
        cfg = kwargs['cfg']
        assert cfg["start"] >= 0, "Can't have a negative start time."
        assert cfg["step"] > 0, "Can't have a negative step"

        # The "reps" loop is outermost, so this will reset the cycle and sample counter on each of these loops
        # 1 cycle = 16 samples
        # cycle_counter: always 2+length of waveform in cycles
        # sample_counter: total samples Mod 16, output (0...15) instead
        before_reps = kwargs.get("before_reps", AsmV2())
        reset_loop = AsmV2()
        reset_loop.write_reg(dst='delay_cycles', src= floor(cfg["start"] / 16) - cfg["step"] // 16)
        reset_loop.write_reg(dst='delay_samples', src= cfg["start"] % 16  - cfg["step"]  % 16)
        before_reps.extend_macros(reset_loop)
        kwargs["before_reps"] = before_reps

        super().__init__(*args, **kwargs)

    '''Load 16 waveforms, one for each starting sample within the first clock cycle. Use for sweeping
    the length of arbitrary pulses.'''
    def FFLoad16Waveforms(self, list_of_gains, previous_gains, IDataArray, waveform_label="FF_swept", truncation_length=None):
        if truncation_length is None:
            truncation_length = self.cfg["start"] + self.cfg["expts"] * self.cfg["step"]
        truncation_length = ceil(truncation_length / 16) * 16

        for channel, gain, prev_gain, IQPulse in zip(self.FFChannels, list_of_gains, previous_gains, IDataArray):
            if IQPulse is None:  # if not specified, assume constant of max value
                IQPulse = gain * np.ones(truncation_length)
            # add buffer to beginning of IQPulse
            IQPulse = np.concatenate([prev_gain * np.ones(48), IQPulse[:truncation_length]])
            for i in range(1, 17):
                # create shifted pulse. All pulses are len(IQPulse) + 2 clock cycles!
                idata = IQPulse[i:len(IQPulse) - 16 + i]
                wname = f"{waveform_label}_{i}_{channel}"
                self.add_envelope(ch=channel, name=wname,
                                      idata=idata, qdata=np.zeros_like(idata))
                self.add_pulse(ch=channel, name=wname,
                                   style="arb", envelope=wname,
                                   freq=0, phase=0, gain=1.0, outsel="input")


    def FFPulses_arb_predelay(self, t_start, waveform_label="FF_swept"):
        '''Play a waveform based on the value in delay_samples.'''

        # The waveform itself contains (32 + samples_in_front) samples of delay.
        # choose the correct waveform depending on the amount of samples mod 16
        for i in range(1, 17):
            samples_in_front = 16 - i
            self.cond_jump(f"delay_is_{samples_in_front}", "delay_samples", 'Z', '-', samples_in_front)
        for i in range(1, 17):
            samples_in_front = 16 - i
            self.label(f"delay_is_{samples_in_front}")
            FF.FFPlayWaveforms(self, waveform_label=f"{waveform_label}_{i}", t_start=t_start)
            self.jump("arb_delay_finish")
        self.label("arb_delay_finish")

    def FFInvert_arb_predelay(self, t_start, waveform_label="FF_swept"):
        '''Same as above, but invert the waveform.'''
        for i in range(1, 17):
            samples_in_front = 16 - i
            self.cond_jump(f"inv_delay_is_{samples_in_front}", "delay_samples", 'Z', '-', samples_in_front)
        for i in range(1, 17):
            samples_in_front = 16 - i
            self.label(f"inv_delay_is_{samples_in_front}")
            FF.FFInvertWaveforms(self, waveform_label=f"{waveform_label}_{i}", t_start=t_start)
            self.jump("inv_arb_delay_finish")
        self.label("inv_arb_delay_finish")

    def _initialize(self, cfg):
        # Readout (MUX): resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        FF.FFDefinitions(self)
        for FFreadout in self.FFReadouts:
            assert FFreadout == 0, "Use 0 for FFReadouts for this experiment."
        # longest_length = self.cfg["start"] + self.cfg["expts"] * self.cfg["step"]
        # FFLoad16Waveforms(self, self.FFPulse, "FFExpt", longest_length)

        # Qubit (Test one qubit at a time)
        self.qubit_length_us = 4 * cfg["sigma"]
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])  # Qubit
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=self.qubit_length_us)

        self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive', style="arb", envelope="qubit",
                           freq=cfg["qubit_freqs"][0], phase=90, gain=cfg["qubit_gains"][0])

        # Make the step FF pulse
        self.IQArray = [None] *  len(self.FFChannels)
        idx = cfg['qubit_index'] - 1
        FF_impulse = np.full(16*self.us2cycles(self.qubit_length_us), self.FFPulse[idx])
        self.IQArray[idx] = np.concatenate([FF_impulse, np.full(16, self.FFReadouts[idx])])
        # 1 cycle = 16 samples
        # cycle_counter: always 2+length of waveform in cycles
        # sample_counter: total samples Mod 16, but output (1...16) instead
        # Set in before_reps of the "reps" loop (see self.__init__ above)
        self.add_reg(name='delay_cycles')
        self.add_reg(name='delay_samples')


        # Increment the cycle and sample counter. Carry the one if sample_counter > 16.
        IncrementLength = AsmV2()
        IncrementLength.inc_reg(dst='delay_cycles',  src=cfg["step"] // 16)
        IncrementLength.inc_reg(dst='delay_samples', src=cfg["step"]  % 16)
        ############# If sample_counter > 15:
        IncrementLength.cond_jump("no_carry", "delay_samples", "S", "-", 16)
        IncrementLength.inc_reg(dst='delay_cycles', src= +1)
        IncrementLength.inc_reg(dst='delay_samples',src= -16)
        IncrementLength.label("no_carry")
        IncrementLength.nop()
        ##############
        # # Write into data memory for debugging
        # self.add_reg(name='data_counter')
        # self.write_reg(dst='data_counter', src=0)
        # IncrementLength.inc_reg(dst='data_counter', src=+1)
        # IncrementLength.write_dmem("data_counter", "cycle_counter")
        # IncrementLength.inc_reg(dst='data_counter', src=+1)
        # IncrementLength.write_dmem("data_counter", "sample_counter")
        #############
        self.add_loop("expt_samples", int(self.cfg["expts"]), exec_before=IncrementLength)

        self.delay_auto(200)


    def delay_reg(self, reg):
        # Delay by cycle_counter cycles
        self.asm_inst(inst={'CMD': 'TIME', 'C_OP': 'inc_ref', 'R1': self._get_reg(reg)}, addr_inc=1)

    def _body(self, cfg):
        # 1: FFPulses
        # self.delay_auto()
        # 2: FFExpt

        self.FFLoad16Waveforms(self.FFReadouts, self.FFReadouts, self.IQArray)

        self.FFPulses(self.FFReadouts, 10, t_start=0)
        self.delay(10)
        self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive', t=self.cycles2us(cfg['qubit_delay_cycles']+2))
        self.delay_reg("delay_cycles")
        self.FFPulses_arb_predelay(t_start=0) # 2 cycle delay included here

        # can't use delay auto since qick doesn't know about jumps (?)
        self.delay(self.cycles2us(3 + self.us2cycles(self.qubit_length_us)))

        # 3: FFReadouts
        self.FFPulses(self.FFReadouts, self.cfg["res_length"], t_start=0)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive', t=0)
        self.wait(self.cfg["res_length"] + 1)
        self.delay(self.cfg["res_length"] + 10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.delay(self.cfg["res_length"])
        self.FFInvert_arb_predelay(t_start=0)
        self.delay(self.cycles2us(3 + self.us2cycles(self.qubit_length_us)))
        self.FFPulses(-1 * self.FFReadouts, 10, t_start=0)
        self.delay(10)

    def loop_pts(self):
        return (self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts']) - 16*self.cfg['qubit_delay_cycles'] ,)



class CalibrateFFvsDriveTiming(SweepExperiment1D_lines):
    def init_sweep_vars(self):
        self.Program = FFvsDriveTimingProgram


        self.x_name = "expt_samples"

        self.z_value = 'population'  # contrast or population
        self.xlabel = 'FF pulse delay relative to qubit (samples)'  # for plotting

        self.cfg.pop('confusion_matrix')


    def _display_plot(self, data=None, fig_axs=None):
        fig, ax = super()._display_plot(data=data, fig_axs=fig_axs)
        NS_PER_SAMPLE = self.soccfg.cycles2us(1) * 1000 / 16
        print(NS_PER_SAMPLE)

        ax.secondary_xaxis('top', (lambda t: t * NS_PER_SAMPLE, lambda t: t / NS_PER_SAMPLE))
        ax.set_title(f'Qubit {self.cfg['qubit_index']} FF pulse delay relative to qubit (ns)')

        # def lorentzian_fit(x, x0, a, b, c):
        #     return a / (1 + (x - x0) ** 2 / b ** 2) + c

        def gaussian_fit(x, x0, a, b, c):
            return a * np.exp(-(x - x0) ** 2 / b ** 2 / 2) + c

        pop_vec = data['data'][self.z_value][0]
        x_vec = data['data'][self.x_name]

        width_guess = self.cfg['sigma']/NS_PER_SAMPLE * 16
        p0 = [x_vec[np.argmax(pop_vec)], np.max(pop_vec), width_guess, 0]
        try:
            params, _ = curve_fit(gaussian_fit, x_vec, pop_vec, p0)
            print(params)
            ax.plot(x_vec, gaussian_fit(x_vec, *params), color='black')
            ax.axvline(params[0], color='black', linestyle='--', label=f"x0 = {params[0]:.2f} samples = {params[0]*NS_PER_SAMPLE:.2f} ns")
            ax.legend(prop={'size': 14})
        except:
            print("No fit found.")
