import numpy as np

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF
from WorkingProjects.triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensate

from dataclasses import dataclass, field

@dataclass
class DriveObj:
    freq:  float
    gain:  float
    phase: float
    sigma_us: float

    len_sigmas: float = 4
    relative_t: float|str = "auto"

    def len_us(self):
        return self.len_sigmas*self.sigma_us

@dataclass
class FFSegment:
    '''Usage: IQArray takes precedence over gains and length_samples'''
    IQArray: list[np.ndarray] | None = None
    gains: np.ndarray | None = None
    length_samples: int | None = None
    drives: list[DriveObj] = field(default_factory=list)

    def __len__(self):
        return self.length_samples if self.IQArray is None else len(self.IQArray[0])



INIT_FF_TIME_US = 5  # how many us to hold Init_FF at for it to asymptote
BASE_PAD_FFREADOUTS_SAMPLES = 32 # minimum samples to pad tail with FFReadout


class ProgramBuilder(FFAveragerProgramV2):
    """
    Required cfg items:
        cfg['ProgramBuilderInfo']: list[FFSegment], to build program from.
        cfg["t_offset"]: int > 0: delays in samples for each FF channel, and
        cfg["drive_offset_cycles"]: int, if > 0 how many cycles the drives should be scheduled AFTER the FF channels.
                                         if < 0, delay the FF instead. (So far, we have measured drive faster than FF, so need > 0).

    Intricacies:
    * Provide all IQArrays UNCOMPENSATED, we apply compensation on the combined thing and this makes it easier to mix arb and const waveforms.
    * However, provide everything POST-CROSSTALK, as applying the crosstalk matrix to the entire matrix is very slow.
    * Pulses can only be scheduled at a particular clock CYCLE = 16 SAMPLES. So
        PULSE START TIMES ARE ROUNDED UP TO THE NEXT CYCLE=16 SAMPLES, which may cause a pulse with relative_t=0 to start
        up to 15 samples later than the start of its FF Segment.
    * So far, there is no length checking for pulses. So make sure all your pulses fit within your FF segment.
    """



    def _samples_to_next_cycle_us(self, n_samples):
        """1/16-clock samples -> us via the program clock.
        Rounds UP to next clock cycle so that n_samples is rounded up the next 16."""
        return self.cycles2us((n_samples + 15) // 16, gen_ch=self.FFChannels[0])

    def _initialize(self, cfg):
        # --- generators / readout ---
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"], mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"], mux_gains=cfg["res_gains"], ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        FF.FFDefinitions(self)  # -> self.FFChannels, self.FFReadouts (corrected), self.gen_t0, ...

        FF_segments = cfg["ProgramBuilderInfo"]
        assert len(FF_segments) >= 1, "cfg['ProgramBuilderInfo'] must hold >= 1 FFSegment"

        # Find Init_FFs
        init_segment = FF_segments[0]
        if init_segment.IQArray is not None:
            self.Init_FFs = np.array([arr[0] for arr in init_segment.IQArray])
        else:
            self.Init_FFs = np.asarray(init_segment.gains)

        # Check t_offset
        t_offset = self.cfg['t_offset']
        assert np.min(t_offset) >= 0, "t_offset must be >= 0"

        # Calculate total length
        ff_ro_pad = BASE_PAD_FFREADOUTS_SAMPLES # default 32
        seg_lengths = [len(seg) for seg in FF_segments]
        L_body = int(sum(seg_lengths))
        self.combined_length_samples = np.max(t_offset) + L_body + ff_ro_pad

        # Create combined_IQArray
        self.combined_IQArray = []
        for j in range(len(self.FFChannels)):
            # head: t_offset of Init_FF
            combined_segments = [np.full(int(t_offset[j]), self.Init_FFs[j])]
            # body: FF_segments
            for segment, seg_len in zip(FF_segments, seg_lengths):
                if segment.IQArray is not None:
                    combined_segments.append(np.asarray(segment.IQArray[j]))
                else:
                    combined_segments.append(np.full(int(seg_len), segment.gains[j]))
            # tail: padding of FFReadouts
            combined_segments.append(np.full((np.max(t_offset) - int(t_offset[j])) + ff_ro_pad, self.FFReadouts[j]))
            compensated_arr = Compensate(np.concatenate(combined_segments), self.Init_FFs[j], j+1)
            self.combined_IQArray.append(compensated_arr)


        # --- qubit drives: one Gaussian envelope per (segment, drive)
        for si, seg in enumerate(FF_segments):
            for di, drive in enumerate(seg.drives):
                env = f"seg{si}_drive{di}"
                self.add_gauss(ch=cfg["qubit_ch"], name=env, sigma=drive.sigma_us, length=drive.len_us())
                self.add_pulse(ch=cfg["qubit_ch"], name=env, style="arb", envelope=env,
                               freq=drive.freq, phase=drive.phase, gain=drive.gain / 32766)

    def _body(self, cfg):
        FF_segments = cfg["ProgramBuilderInfo"]

        # (1) Hold Init_FFs long enough to asymptote so we can ignore ringing in jump from 0
        init_us = INIT_FF_TIME_US
        self.FFPulses(self.Init_FFs, init_us, waveform_label="Init")
        self.delay_auto()

        if cfg["drive_offset_cycles"] < 0: # if FF faster than drive, add extra delay to FF
            self.FFPulses(self.Init_FFs, self.cycles2us(-cfg["drive_offset_cycles"], gen_ch=self.FFChannels[0]), waveform_label="Init_extra")

        # (2a) Combined FF pulse
        self.FFPulses_direct(self.FFReadouts, self.combined_length_samples, self.Init_FFs,
                             IQPulseArray=self.combined_IQArray, waveform_label="combined")

        # (2b) Play all qubit drives. Drive t is measured from the start of its segment in combined_IQArray,
        # always rounded FORWARD TO THE NEXT CLOCK CYCLE
        cumulative_samples = 0 # to track previous pulses
        if cfg["drive_offset_cycles"] > 0:
            cumulative_samples += 16 * cfg["drive_offset_cycles"]

        for si, segment in enumerate(FF_segments):
            seg_start_us = self._samples_to_next_cycle_us(cumulative_samples)
            # "auto" schedules a pulse immediately after the latest-t pulse
            auto_cursor = seg_start_us
            for di, drv in enumerate(segment.drives):
                if drv.relative_t == "auto":
                    t = auto_cursor
                else:
                    t = seg_start_us + drv.relative_t
                auto_cursor = max(auto_cursor, t+drv.len_us())

                self.pulse(ch=cfg["qubit_ch"], name=f"seg{si}_drive{di}", t=t)
            cumulative_samples += len(segment)
        self.delay_auto()

        # (4) readout
        self.FFPulses(self.FFReadouts, cfg["res_length"], waveform_label="Readout")
        for ro_ch, adc_trig_delay in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name="res_drive")
        self.wait_auto()
        self.delay_auto(10)  # us

        # (5) DC balance: mirror every forward FF emission with an equal-length negated one so the
        #     net integral per channel is zero (flux/charge safety).
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"], waveform_label="ReadoutInv")
        FF.FFInvertWaveforms(self, "combined")
        if cfg["drive_offset_cycles"] < 0: # if FF faster than drive, add extra delay to FF
            self.FFPulses(-1 * self.Init_FFs, self.cycles2us(-cfg["drive_offset_cycles"], gen_ch=self.FFChannels[0]), waveform_label="Init_extraInv")
        self.FFPulses(-1 * self.Init_FFs, init_us, waveform_label="InitInv")
        self.delay_auto()

    def plot(self):
        '''Uses the FF_to_frequency mapping to show all qubit frequencies at each time, along with qubit drives.'''
        raise NotImplementedError


'''
Specification (pseudocode):
cfg['ProgramBuilderInfo'] is a list of FFSegment, in chronological order in which they happen.

class ProgramBuilder(FFAveragerProgramV2):
    def initialize():
        declare qubit gen
        declare readout gen
        add readout pulse
        declare readout adc

        FFDefinitions
        Loop through cfg['ProgramBuilderInfo']:
            if first entry, register first gains as self.Init_FFs and apply cfg['t_offset'] vector
            construct single concatenated IQArray -> self.combined_IQArray
            add_pulse for found pulses, label in a way that makes sense (maybe segment index and pulse index)

        base_pad_FFReadouts_samples = 32 
        include FFReadouts padding to end of self.combined_IQArray

    def body():
        FF_delay_time = 5
        self.FFPulses(self.Init_FFs, FF_delay_time + cfg['drive_offset']) # to make first segment asymptotic
        Loop through cfg['ProgramBuilderInfo']:
            Loop through pulses:
                t = calculate based on segment
                self.pulse(..., t=t)
        self.delay_auto()


        # treat FFReadout specially
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"]) # invert readouts

        Invert combined_FF (there is a function that does this in FF_Helpers that inverts the gain to save waveform memory)
        Invert self.Init_FFs
        self.delay_auto()

'''

