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
    '''Usage: IQArray takes precedence over gains and length_samples.

    type: "const" (flat per-channel gains, built today) or "cubic" (reserved,
          not yet implemented). Only "const" is a valid build target right now.
    '''
    IQArray: list[np.ndarray] | None = None
    gains: np.ndarray | None = None
    length_samples: int | None = None
    drives: list[DriveObj] = field(default_factory=list)
    type: str = "const"

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

        # --- segment type hook ---
        # Only flat "const" segments are built today. "cubic" is reserved for a
        # future cubic-ease ramp envelope; the const build path below is unchanged.
        for seg in FF_segments:
            if getattr(seg, "type", "const") == "cubic":
                raise NotImplementedError(
                    "FFSegment.type=='cubic' is reserved and not yet implemented. "
                    "TODO: synthesize a cubic-ease IQArray between this segment's "
                    "start gains and the next segment's gains, then feed it through "
                    "the existing const concatenation path."
                )
            elif getattr(seg, "type", "const") != "const":
                raise ValueError(f"Unknown FFSegment.type {seg.type!r}; expected 'const' or 'cubic'.")

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
            self.trigger(ros=[ro_ch],  t=adc_trig_delay)
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

    def plot(self, readout_group=None, ax=None):
        '''Show all qubit dressed frequencies vs time (samples) for this program,
        overlaying the qubit drives. Delegates to the soccfg-free staticmethod
        ``plot_program`` so the same drawing works in the GUI (no hardware).

        Returns (fig, ax) if ax is None, else draws into ax and returns ax.
        '''
        cfg_like = {
            "ProgramBuilderInfo": self.cfg["ProgramBuilderInfo"],
        }
        # FFChannels is set by FF.FFDefinitions during _initialize; expose the
        # channel count so plot_program does not need a live soccfg.
        if getattr(self, "FFChannels", None) is not None:
            cfg_like["n_ff_channels"] = len(self.FFChannels)
        return ProgramBuilder.plot_program(cfg_like, readout_group=readout_group, ax=ax)

    # TODO: WIP, not working to specification yet
    @staticmethod
    def plot_program(cfg, readout_group=None, ax=None):
        '''Soccfg-free timeline plot used as the GUI entry point.

        Builds the segment timeline purely from ``cfg['ProgramBuilderInfo']``
        (a list[FFSegment]) plus an FF-channel count, runs each segment's
        per-channel gains through the device flux->dressed-frequency model,
        and draws a step plot of dressed frequency (MHz) vs time (samples),
        with vertical dashed segment boundaries and drive markers overlaid.

        Parameters
        ----------
        cfg : dict
            Must contain ``'ProgramBuilderInfo'`` (list[FFSegment]). Optional
            keys: ``'n_ff_channels'`` (defaults to len(seg0.gains) or 8),
            ``'readout_groups'`` (the qubit_parameters.json readout_groups dict,
            used to resolve the operating point when ``readout_group`` is given).
        readout_group : str | None
            Name of a readout group in ``cfg['readout_groups']``. If present,
            each entry's ``Qubit.Frequency`` seeds the rest-frequency operating
            point ``{f"Q{n}": freq}``; otherwise every qubit defaults to flux 0.
        ax : matplotlib Axes | None
            If None, a new (fig, ax) is created and returned. Else draw into ax.

        Returns
        -------
        (fig, ax) if ax was None, else ax.

        Device-calib import (qutip-backed) is lazy and wrapped: on any failure
        an explanatory message is drawn onto the axes instead of raising, so the
        GUI stays usable without hardware/qutip.
        '''
        created_fig = None
        if ax is None:
            import matplotlib.pyplot as plt
            created_fig, ax = plt.subplots(figsize=(8.0, 4.5))
        ax.clear()

        segments = cfg.get("ProgramBuilderInfo") or []
        if len(segments) == 0:
            ax.text(0.5, 0.5, "No segments to plot.", ha="center", va="center",
                    transform=ax.transAxes)
            return (created_fig, ax) if created_fig is not None else ax

        num_channels = len(cfg["fast_flux_chs"])


        # Per-segment, per-channel "level" (const gain or first IQ sample).
        def seg_level(seg, j):
            if seg.IQArray is not None:
                return float(seg.IQArray[j][0])
            return float(seg.gains[j])

        # Segment time spans in samples (cumulative len(seg)).
        seg_lengths = [int(len(seg)) for seg in segments]
        boundaries = np.concatenate([[0], np.cumsum(seg_lengths)]).astype(float)
        total_len = float(boundaries[-1]) if boundaries[-1] > 0 else 1.0

        # --- device flux model (lazy + wrapped) ---
        try:
            from pathlib import Path
            from WorkingProjects.triangle_lattice_quench.Flux_Files.New_device_calib.DeviceData import DeviceData
            from WorkingProjects.triangle_lattice_quench.Flux_Files.New_device_calib.DeviceInterface import DeviceInterface
2
            json_path = Path(__file__).parents[2] / "Flux_Files" / "New_device_calib" / "8QV1.json"
            data = DeviceData.from_json(str(json_path))
            dev = DeviceInterface(data)

            # Operating point: rest frequencies from a readout group if available,
            # else default every qubit to flux 0. Couplers omitted (VC -> flux 0).
            configuration = {}
            rg_dict = (cfg.get("readout_groups") or {})
            rg = rg_dict.get(readout_group) if readout_group else None
            if rg is not None:
                for ent_key, ent in (rg.get("entries", {}) or {}).items():
                    try:
                        n = int(ent_key)
                        freq = ent["Qubit"]["Frequency"]
                        configuration[f"Q{n}"] = float(freq)
                    except (ValueError, KeyError, TypeError):
                        continue
            if not configuration:
                configuration = {f"Q{n}": 0.0 for n in range(1, n_ch + 1)}

            vc = dev.create_voltage_configuration(configuration)

            # Dressed frequency per qubit per segment.
            qnames = [f"Q{j+1}" for j in range(n_ch)]
            seg_freqs = []  # list over segments of {Qn: MHz}
            for seg in segments:
                ff = {qnames[j]: seg_level(seg, j) for j in range(n_ch)}
                seg_freqs.append(vc.fast_flux_to_dressed_freqs(ff))
        except Exception as exc:  # qutip missing, band-edge, import error, etc.
            import traceback
            ax.set_axis_off()
            ax.text(0.5, 0.5,
                    "Frequency plot unavailable (device-calib model failed):\n"
                    f"{type(exc).__name__}: {exc}\n\n"
                    f"{traceback.format_exc()}",
                    ha="center", va="center", fontsize=7, family="monospace",
                    wrap=True, transform=ax.transAxes)
            return (created_fig, ax) if created_fig is not None else ax

        # --- draw step plot of dressed freq vs samples, one line per qubit ---
        import matplotlib.pyplot as plt
        cmap = plt.get_cmap("tab10")
        for j in range(n_ch):
            qn = f"Q{j+1}"
            ys = [seg_freqs[si].get(qn, np.nan) for si in range(len(segments))]
            # Step: hold each segment's freq flat across its time span.
            xs_step, ys_step = [], []
            for si in range(len(segments)):
                xs_step += [boundaries[si], boundaries[si + 1]]
                ys_step += [ys[si], ys[si]]
            color = cmap(j % 10)
            ax.plot(xs_step, ys_step, "-", color=color, linewidth=1.6, label=qn)
            # Label QN at both edges.
            ax.annotate(qn, xy=(boundaries[0], ys[0]), xytext=(-10, 0),
                        textcoords="offset points", ha="right", va="center",
                        fontsize=7, color=color)
            ax.annotate(qn, xy=(boundaries[-1], ys[-1]), xytext=(8, 0),
                        textcoords="offset points", ha="left", va="center",
                        fontsize=7, color=color)

        # Segment boundary dividers.
        for b in boundaries[1:-1]:
            ax.axvline(x=b, color="lightgrey", linestyle="--", linewidth=0.8, zorder=1)

        # --- overlay drives as short horizontal bars at their drive frequency ---
        # Drives are positioned at their time within the host segment. Without a
        # soccfg we approximate samples-per-us from the FF clock-cycle convention
        # (16 samples/cycle, ~430.08 MHz fabric ~ a few samples/ns); for the v1
        # preview we use a coarse fixed scale and clamp to the host segment span.
        SAMPLES_PER_US = 100.0  # coarse preview scale; refine once soccfg is wired
        for si, seg in enumerate(segments):
            seg_start = boundaries[si]
            seg_end = boundaries[si + 1]
            cursor = seg_start
            for drv in getattr(seg, "drives", []) or []:
                width = max(2.0, drv.len_us() * SAMPLES_PER_US)
                if drv.relative_t == "auto":
                    t0 = cursor
                else:
                    try:
                        t0 = seg_start + float(drv.relative_t) * SAMPLES_PER_US
                    except (TypeError, ValueError):
                        t0 = cursor
                t0 = min(max(t0, seg_start), seg_end)
                t1 = min(t0 + width, seg_end)
                cursor = max(cursor, t1)
                ax.plot([t0, t1], [drv.freq, drv.freq], "-", color="black",
                        linewidth=3.0, solid_capstyle="butt", zorder=4)
                ax.plot([0.5 * (t0 + t1)], [drv.freq], marker="v", color="black",
                        markersize=6, zorder=5)
                # Annotate which qubit this drive most likely targets (nearest
                # qubit rest frequency in this segment), if determinable.
                target = None
                best = np.inf
                for j in range(n_ch):
                    fq = seg_freqs[si].get(f"Q{j+1}", np.nan)
                    if np.isfinite(fq) and abs(fq - drv.freq) < best:
                        best, target = abs(fq - drv.freq), f"Q{j+1}"
                if target is not None:
                    ax.annotate(f"drv→{target}", xy=(0.5 * (t0 + t1), drv.freq),
                                xytext=(0, 6), textcoords="offset points",
                                ha="center", va="bottom", fontsize=6, color="black")

        ax.set_xlim(-0.04 * total_len, 1.04 * total_len)
        ax.set_xlabel("Samples")
        ax.set_ylabel("Dressed frequency (MHz)")
        ax.set_title("Program timeline: dressed qubit frequencies + drives"
                     + (f"  [readout: {readout_group}]" if readout_group else ""))
        ax.legend(fontsize=7, ncol=2, loc="best")

        if created_fig is not None:
            created_fig.tight_layout()
            return created_fig, ax
        return ax


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
            self.trigger(ros=[ro_ch], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"]) # invert readouts

        Invert combined_FF (there is a function that does this in FF_Helpers that inverts the gain to save waveform memory)
        Invert self.Init_FFs
        self.delay_auto()

'''

