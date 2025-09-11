from qick.asm_v2 import AsmV2

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *

from math import ceil

class SweepWaveformAveragerProgram(FFAveragerProgramV2):
    '''A base class containing all the subroutines used for sweeping the length of an arbitrary waveform
    to inherit from.

    For the user: you need to supply the config with "start", "step", (units of samples) and "expts".
        An _initialize function for most use cases is provided,
        you will write _body in which you only need to call

        FFLoad16Waveforms(self, list_of_gains, previous_gains, IDataArray) once

        FFPulses_arb_length_and_delay(self, t_start) in place of FFPulses_direct and
        FFInvert_arb_length_and_delay(self, t_start) to invert the pulse at the end.

        Both functions include a delay() by the correct number of cycles.

    - Joshua 8/12/25
    '''

    def __init__(self, *args, **kwargs):
        cfg = kwargs['cfg']
        assert cfg["start"] >= 0, "Can't have a negative start time."
        assert cfg["step"] >= 0, "Can't have a negative step"

        # The "reps" loop is outermost, so this will reset the cycle and sample counter on each of these loops
        # 1 cycle = 16 samples
        # cycle_counter: always 2+length of waveform in cycles
        # sample_counter: total samples Mod 16, but output (1...16) instead
        before_reps = kwargs.get("before_reps", AsmV2())
        reset_loop = AsmV2()
        reset_loop.write_reg(dst='cycle_counter', src=2 + ceil(cfg["start"] / 16) - cfg["step"] // 16)
        reset_loop.write_reg(dst='sample_counter', src=(cfg["start"] - 1) % 16 + 1 - cfg["step"]  % 16)
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
            IQPulse[IQPulse > 32766] = 32766
            IQPulse[IQPulse < - 32766] = - 32766
            IQPulse = np.concatenate([prev_gain * np.ones(3*16), IQPulse[:truncation_length]])
            for i in range(1, 17):
                # create shifted pulse. All pulses are len(IQPulse) + 2 clock cycles!
                idata = IQPulse[i:len(IQPulse) - 16 + i]
                wname = f"{waveform_label}_{i}_{channel}"
                self.add_envelope(ch=channel, name=wname,
                                      idata=idata, qdata=np.zeros_like(idata))
                self.add_pulse(ch=channel, name=wname,
                                   style="arb", envelope=wname,
                                   freq=0, phase=0, gain=1.0, outsel="input")

    def FFPlayChangeLength(self, waveform_label, length_src, t_start):
        for channel in self.FFChannels:
            pulse_name = f"{waveform_label}_{channel}"
            for wname in self.list_pulse_waveforms(pulse_name):
                self.read_wmem(name=wname)
                self.write_reg(dst='w_length', src=length_src)
                self.write_wmem(name=wname)

                if t_start != 'auto':
                    t_start = t_start + 0  # instance.gen_t0[channel]
                self.pulse(ch=channel, name=pulse_name, t=t_start)

    def FFPulses_arb_length_and_delay(self, t_start, waveform_label="FF_swept"):
        '''Play a waveform based on the values in cycle_counter and sample_counter.'''
        # Special case: 0 samples (cycle_counter < 3), skip directly to readout (no FFExpt)
        self.cond_jump("skip_waveform", "cycle_counter", 'S', '-', 3)
        # Else, choose the correct waveform depending on the amount of samples mod 16
        for i in range(1, 17):
            self.cond_jump(f"length_is_{i}", "sample_counter", 'Z', '-', i)
        for i in range(1, 17):
            self.label(f"length_is_{i}")
            self.FFPlayChangeLength(f"{waveform_label}_{i}", "cycle_counter", t_start=t_start)
            self.jump("arb_length_finish")
        self.label("arb_length_finish")
        # Delay by cycle_counter cycles
        self.asm_inst(inst={'CMD': 'TIME', 'C_OP': 'inc_ref', 'R1': self._get_reg("cycle_counter")}, addr_inc=1)

        self.label("skip_waveform")
        self.nop()

    def FFInvert_arb_length_and_delay(self, t_start, waveform_label="FF_swept"):
        '''Same as above, but invert the waveform.'''
        self.cond_jump("finish_inv", "cycle_counter", 'S', '-', 3)
        for i in range(1, 17):
            self.cond_jump(f"inv_length_is_{i}", "sample_counter", 'Z', '-', i)
        for i in range(1, 17):
            self.label(f"inv_length_is_{i}")
            FF.FFInvertWaveforms(self, f"{waveform_label}_{i}", t_start=t_start)
            self.jump("finish_inv")
        self.label("finish_inv")
        self.asm_inst(inst={'CMD': 'TIME', 'C_OP': 'inc_ref', 'R1': self._get_reg("cycle_counter")}, addr_inc=1)

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
        # longest_length = self.cfg["start"] + self.cfg["expts"] * self.cfg["step"]
        # FFLoad16Waveforms(self, self.FFPulse, "FFExpt", longest_length)

        # Qubit (Equal sigma for all)
        self.qubit_length_us = 4 * cfg["sigma"]
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])  # Qubit
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=self.qubit_length_us)
        for i in range(len(self.cfg["qubit_gains"])):
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}', style="arb", envelope="qubit",
                           freq=cfg["qubit_freqs"][i], phase=90, gain=cfg["qubit_gains"][i])

        # 1 cycle = 16 samples
        # cycle_counter: always 2+length of waveform in cycles
        # sample_counter: total samples Mod 16, but output (1...16) instead
        # Set in before_reps of the "reps" loop (see self.__init__ above)
        self.add_reg(name='cycle_counter')
        self.add_reg(name='sample_counter')


        # Increment the cycle and sample counter. Carry the one if sample_counter > 16.
        IncrementLength = AsmV2()
        IncrementLength.inc_reg(dst='cycle_counter',  src=cfg["step"] // 16)
        IncrementLength.inc_reg(dst='sample_counter', src=cfg["step"]  % 16)
        ############# If sample_counter > 16:
        IncrementLength.cond_jump("no_carry", "sample_counter", "S", "-", 17)
        IncrementLength.inc_reg(dst='cycle_counter', src= +1)
        IncrementLength.inc_reg(dst='sample_counter',src= -16)
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

    def loop_pts(self):
        return (self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts']) ,)
