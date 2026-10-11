import numpy as np

from triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import triangle_lattice_quench.Helpers.FF_utils as FF
from triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensate

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
# FF samples per us when no soccfg is at hand (GUI preview): 16 samples per fabric clock at a
# 215.04 MHz clock (the 4.65 ns cycle the T1/T2 programs assume). plot() passes the exact value.
DEFAULT_FF_SAMPLES_PER_US = 16 * 215.04


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
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"], mixer_freq=cfg["res_mixer_freq"],
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
        self.FFPlay_Const(self.Init_FFs, init_us, waveform_label="Init")
        self.delay_auto()

        if cfg["drive_offset_cycles"] < 0: # if FF faster than drive, add extra delay to FF
            self.FFPlay_Const(self.Init_FFs, self.cycles2us(-cfg["drive_offset_cycles"], gen_ch=self.FFChannels[0]), waveform_label="Init_extra")

        # (2a) Combined FF pulse (INCLUDES ALL SEGMENTS EXCEPT FFREADOUT)
        self.FFPlay_Arb(self.FFReadouts, self.combined_length_samples, self.Init_FFs,
                             IQPulseArray=self.combined_IQArray, waveform_label="combined")

        # (2b) Play all qubit drives. Drive t is measured from the start of its segment in combined_IQArray,
        # always rounded FORWARD TO THE NEXT CLOCK CYCLE
        cumulative_samples = 0 # to track previous pulses
        if cfg["drive_offset_cycles"] > 0:
            cumulative_samples += 16 * cfg["drive_offset_cycles"]

        # Loop through all segments, correctly time all qubit drives
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

        # (4) readout,
        self.FFPlay_Const(self.FFReadouts, cfg["res_length"], waveform_label="Readout")
        for ro_ch, adc_trig_delay in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch],  t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name="res_drive")
        self.wait_auto()
        self.delay_auto(10)  # us

        # (5) DC balance: mirror every forward FF emission with an equal-length negated one so the
        #     net integral per channel is zero (flux/charge safety).
        self.FFPlay_Const(-1 * self.FFReadouts, cfg["res_length"], waveform_label="ReadoutInv")
        FF.FFInvertWaveforms(self, "combined")
        if cfg["drive_offset_cycles"] < 0: # if FF faster than drive, add extra delay to FF
            self.FFPlay_Const(-1 * self.Init_FFs, self.cycles2us(-cfg["drive_offset_cycles"], gen_ch=self.FFChannels[0]), waveform_label="Init_extraInv")
        self.FFPlay_Const(-1 * self.Init_FFs, init_us, waveform_label="InitInv")
        self.delay_auto()

    def plot(self, readout_group=None, ax=None):
        '''Show all qubit dressed frequencies vs time (samples) for this program,
        overlaying the qubit drives. Delegates to the soccfg-free staticmethod
        ``plot_program`` so the same drawing works in the GUI (no hardware).

        Returns (fig, ax) if ax is None, else draws into ax and returns ax.
        '''
        cfg_like = {
            "ProgramBuilderInfo": self.cfg["ProgramBuilderInfo"],
            "t_offset": self.cfg.get("t_offset"),
            "drive_offset_cycles": self.cfg.get("drive_offset_cycles", 0),
        }
        # FFChannels is set by FF.FFDefinitions during _initialize; expose the
        # channel count and exact clock rate so plot_program does not need a live soccfg.
        if getattr(self, "FFChannels", None) is not None:
            cfg_like["n_ff_channels"] = len(self.FFChannels)
            cfg_like["samples_per_us"] = 16.0 / self.cycles2us(1, gen_ch=self.FFChannels[0])
        return ProgramBuilder.plot_program(cfg_like, readout_group=readout_group, ax=ax)

    @staticmethod
    def drive_schedule(segments, cycle_us, drive_offset_cycles=0):
        '''Start time (us) of every drive, replicating ``_body`` (keep the two in step).

        Each segment's drives are measured from the segment start rounded UP to the next
        clock cycle; ``relative_t="auto"`` places a drive right after the latest-ending one.
        A positive ``drive_offset_cycles`` shifts every drive later by that many cycles.
        Returns [(segment_index, drive_index, t_start_us)].
        '''
        out, cumulative = [], 16 * max(0, int(drive_offset_cycles))
        for si, seg in enumerate(segments):
            seg_start_us = cycle_us * ((cumulative + 15) // 16)
            cursor = seg_start_us
            for di, drv in enumerate(seg.drives):
                t = cursor if drv.relative_t == "auto" else seg_start_us + drv.relative_t
                cursor = max(cursor, t + drv.len_us())
                out.append((si, di, t))
            cumulative += len(seg)
        return out

    @staticmethod
    def drive_envelope(drive, cycle_us, samples_per_clk=16):
        '''The Gaussian ``add_gauss`` builds for this drive, as (sample_index, amplitude in 0..1).

        QICK v2 (GAUSS_BUG off): the length is rounded to a whole number of fabric clocks,
        sigma is the true standard deviation (NOT rounded), the peak sits at the centre,
        exp(-(x - mu)^2 / (2 sigma^2)) with mu = length/2 - 0.5 samples.
        '''
        n_samp = samples_per_clk * max(1, int(round(drive.len_us() / cycle_us)))
        sigma = max(drive.sigma_us / cycle_us * samples_per_clk, 1e-9)
        x = np.arange(n_samp)
        return x, np.exp(-(x - (n_samp / 2 - 0.5)) ** 2 / (2 * sigma ** 2))

    @staticmethod
    def plot_program(cfg, readout_group=None, ax=None):
        '''Soccfg-free timeline plot used as the GUI entry point.

        Draws, against time in samples (1 sample = 1/16 clock; a second axis shows us):
          * one line per qubit: its DRESSED frequency (MHz) as the FF segments move it
            (flat for constant segments, following the waveform for IQArray segments);
          * every qubit drive at the frequency it is played at: a baseline at the drive
            frequency over the pulse length, and the Gaussian envelope (correct length and
            sigma, as QICK builds it) rising from that baseline, scaled by gain relative to
            the largest drive; labelled with frequency, sigma, length and gain;
          * dashed lines at the segment boundaries.

        Parameters
        ----------
        cfg : dict
            ``'ProgramBuilderInfo'`` (list[FFSegment]) is required. Optional:
            ``'n_ff_channels'`` (else len(seg0.gains)), ``'readout_groups'`` (the
            qubit_parameters.json dict, used with ``readout_group``), ``'t_offset'`` (per-channel
            FF delay in samples), ``'drive_offset_cycles'``, ``'samples_per_us'`` (exact value from
            soccfg; default ``DEFAULT_FF_SAMPLES_PER_US``) and ``'device_json'`` (path override).
        readout_group : str | None
            If given, each entry's ``Qubit.Frequency`` is taken to be that qubit's dressed
            frequency when the FF gains equal the group's ``Pulse_FF`` (where it was measured),
            which fixes the DC operating point. Otherwise every qubit is at flux 0 for zero FF.
        ax : matplotlib Axes | None
            If None, a new (fig, ax) is created and returned. Else draw into ax.

        Returns (fig, ax) if ax was None, else ax.

        Assumptions: segment gains are POST-crosstalk (as the builder requires), so the flux a
        qubit sees comes from the forward FF crosstalk matrix times the applied gains. Couplers are
        taken at flux 0. If the device model cannot be loaded the drives and segment timeline are
        still drawn, with a note, instead of failing.
        '''
        created_fig = None
        if ax is None:
            import matplotlib.pyplot as plt
            created_fig, ax = plt.subplots(figsize=(8.0, 4.5))
        ax.clear()
        done = lambda: (created_fig, ax) if created_fig is not None else ax

        segments = cfg.get("ProgramBuilderInfo") or []
        if len(segments) == 0:
            ax.text(0.5, 0.5, "No segments to plot.", ha="center", va="center", transform=ax.transAxes)
            return done()

        # ---- timing ----
        spu = float(cfg.get("samples_per_us") or DEFAULT_FF_SAMPLES_PER_US)
        cycle_us = 16.0 / spu
        drive_off = int(cfg.get("drive_offset_cycles") or 0)
        ff_x0 = 16 * max(0, -drive_off)       # x=0 is the drives' reference; FF starts later if drives lead
        first = segments[0]
        n_ch = int(cfg.get("n_ff_channels") or len(cfg.get("fast_flux_chs") or [])
                   or (len(first.IQArray) if first.IQArray is not None else len(first.gains)))
        t_off = np.broadcast_to(np.asarray(cfg.get("t_offset") if cfg.get("t_offset") is not None else 0),
                                (n_ch,)).astype(int)
        seg_lengths = [int(len(seg)) for seg in segments]
        bounds = ff_x0 + np.concatenate([[0], np.cumsum(seg_lengths)]).astype(float)

        # ---- device model: dressed frequency of every qubit at a given PHYSICAL FF gain ----
        qn = [f"Q{j + 1}" for j in range(n_ch)]
        model_error = None
        unanchored = []                      # qubits whose Qubit.Frequency the device model cannot reach
        unanchored_names = set()
        freq_cache = {}
        try:
            from pathlib import Path
            from triangle_lattice_quench.Device_Calibration.Device_calib.DeviceData import DeviceData
            from triangle_lattice_quench.Device_Calibration.Device_calib.DeviceInterface import DeviceInterface
            from triangle_lattice_quench.Device_Calibration.Device_calib.VoltageConfiguration import VoltageConfiguration
            json_path = cfg.get("device_json") or (Path(__file__).parents[2] / "Device_Calibration" / "Device_calib"
                                                  / "Device_jsons" / "8QV1_Triangle_Lattice.json")
            dev = DeviceInterface(DeviceData.from_json(str(json_path)))

            # forward FF crosstalk: physical gain seen by each qubit's flux = CT @ applied gains
            ct = np.eye(n_ch)
            try:
                from triangle_lattice_quench.Helpers import FF_Crosstalk_Helper
                m = getattr(FF_Crosstalk_Helper, "FF_CROSSTALK", None)
                if m is not None and np.shape(m) == (n_ch, n_ch):
                    ct = np.asarray(m, float)
            except Exception:
                pass

            # DC operating point: fluxes at which FF gain = 0
            rg = (cfg.get("readout_groups") or {}).get(readout_group) if readout_group else None
            rest = {}
            for key, ent in ((rg or {}).get("entries") or {}).items():
                try:
                    rest[f"Q{int(key)}"] = float(ent["Qubit"]["Frequency"])
                except (ValueError, KeyError, TypeError):
                    continue
            base_flux = {name: 0.0 for name in qn}
            zero_all = {name: 0.0 for name in dev.transmons}            # couplers explicit: no "defaulting" print
            if rest:
                at_zero = VoltageConfiguration(dev, zero_all)
                pulse_ff = (rg or {}).get("FF_Pulses")
                for j, name in enumerate(qn):
                    if name not in rest:
                        continue
                    try:    # flux at which this qubit sits at Qubit.Frequency, then back off by its Pulse_FF
                        flux = dev.transmons[name].flux(at_zero.dressed_to_bare_freq(name, rest[name]))
                    except Exception:
                        unanchored.append(f"{name} ({rest[name]:.0f} MHz, model range "
                                          f"{dev.transmons[name].w_min:.0f}-{dev.transmons[name].w_max:.0f})")
                        unanchored_names.add(name)
                        continue
                    g0 = float(pulse_ff[j]) if pulse_ff is not None and j < len(pulse_ff) else 0.0
                    base_flux[name] = flux - g0 / dev.transmons[name].ffgain_quantum
            vc = VoltageConfiguration(dev, {**zero_all, **base_flux})

            def dressed(j, phys_gain):
                key = (j, float(phys_gain))
                if key not in freq_cache:
                    freq_cache[key] = vc.fast_flux_to_dressed_freqs({qn[j]: float(phys_gain)})[qn[j]]
                return freq_cache[key]
        except Exception as exc:  # qutip missing, bad json path, band edge, ...
            model_error = f"{type(exc).__name__}: {exc}"
            dressed = None

        # ---- qubit frequency traces ----
        import matplotlib.pyplot as plt
        cmap = plt.get_cmap("tab10")
        y_all = []
        traces = {}                                    # qubit -> (x samples, dressed MHz), used to find each drive's target
        if dressed is not None:
            for j in range(n_ch):
                xs, ys = [0.0], []
                init = None
                for si, seg in enumerate(segments):
                    a, b = bounds[si] + t_off[j], bounds[si + 1] + t_off[j]
                    if seg.IQArray is not None:
                        arr = np.asarray(seg.IQArray, float)                     # (n_ch, L) applied gains
                        phys = (ct @ arr)[j]
                        lo, hi = float(phys.min()), float(phys.max())
                        grid = np.linspace(lo, hi, 33) if hi > lo else np.array([lo])
                        curve = np.interp(phys, grid, [dressed(j, g) for g in grid]) if hi > lo \
                            else np.full(phys.shape, dressed(j, lo))
                        pick = np.unique(np.linspace(0, len(phys) - 1, min(len(phys), 300)).astype(int))
                        x_seg, y_seg = a + pick, curve[pick]
                    else:
                        gains = np.asarray(seg.gains, float)
                        f = dressed(j, float((ct @ gains)[j]))
                        x_seg, y_seg = np.array([a, b]), np.array([f, f])
                    if init is None:
                        init = y_seg[0]
                        xs, ys = [0.0], [init]                                  # Init level until the first segment
                    xs += list(x_seg)
                    ys += list(y_seg)
                color = cmap(j % 10)
                mark = "*" if qn[j] in unanchored_names else ""          # dashed + starred: frequency not placed
                traces[qn[j]] = (np.asarray(xs, float), np.asarray(ys, float))
                ax.plot(xs, ys, "--" if mark else "-", color=color, linewidth=1.6, label=qn[j] + mark,
                        zorder=2, gid=f"qubit_{qn[j]}")
                ax.annotate(qn[j] + mark, xy=(xs[0], ys[0]), xytext=(-8, 0), textcoords="offset points",
                            ha="right", va="center", fontsize=7, color=color)
                ax.annotate(qn[j] + mark, xy=(xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                            ha="left", va="center", fontsize=7, color=color)
                y_all += ys

        # ---- segment boundaries ----
        for b in bounds[1:-1]:
            ax.axvline(x=b, color="lightgrey", linestyle="--", linewidth=0.8, zorder=1)

        # ---- drives: baseline at the drive frequency + the Gaussian envelope above it ----
        sched = ProgramBuilder.drive_schedule(segments, cycle_us, drive_off)
        drive_f = [segments[si].drives[di].freq for si, di, _ in sched]
        y_all += drive_f
        y_lo, y_hi = (min(y_all), max(y_all)) if y_all else (0.0, 1.0)
        span = (y_hi - y_lo) or 100.0
        bump = 0.12 * span
        max_gain = max([abs(segments[si].drives[di].gain) for si, di, _ in sched] + [1e-12])
        x_end = bounds[-1] + (int(t_off.max()) if len(t_off) else 0)
        for k, (si, di, t_us) in enumerate(sched):
            drv = segments[si].drives[di]
            x_env, env = ProgramBuilder.drive_envelope(drv, cycle_us)
            xs = t_us * spu + x_env
            x_end = max(x_end, xs[-1])
            h = bump * abs(drv.gain) / max_gain
            target, best = None, np.inf                  # the qubit nearest in frequency AT the pulse centre
            for name, (tx, ty) in traces.items():
                f = float(np.interp(0.5 * (xs[0] + xs[-1]), tx, ty))
                if abs(f - drv.freq) < best:
                    best, target = abs(f - drv.freq), name
            color = cmap(qn.index(target) % 10) if target in qn else "black"
            ax.axhline(drv.freq, color=color, linestyle=":", linewidth=0.7, alpha=0.35, zorder=1)
            ax.fill_between(xs, drv.freq, drv.freq + h * env, color=color, alpha=0.30, linewidth=0, zorder=3)
            ax.plot(xs, drv.freq + h * env, "-", color=color, linewidth=1.2, zorder=4, gid=f"drive_env_{si}_{di}")
            ax.plot([xs[0], xs[-1]], [drv.freq, drv.freq], "-", color=color, linewidth=2.2,
                    solid_capstyle="butt", zorder=4, gid=f"drive_base_{si}_{di}")
            label = (f"{drv.freq:.1f} MHz" + (f" → {target}" if target else "")
                     + f"\nσ={drv.sigma_us * 1e3:.0f} ns, {drv.len_us() * 1e3:.0f} ns, g={drv.gain:.0f}")
            ax.annotate(label, xy=(0.5 * (xs[0] + xs[-1]), drv.freq + h), xytext=(0, 4),
                        textcoords="offset points", ha="center", va="bottom", fontsize=6, color=color)

        notes = []
        if model_error is not None:
            notes.append("Dressed-frequency model unavailable (drives and timeline only):\n" + model_error)
        if unanchored:
            notes.append("Not placed at Qubit.Frequency (outside the device model's range; assumed flux 0 at zero FF):\n"
                         + ", ".join(unanchored))
        if notes:
            ax.text(0.01, 0.99, "\n".join(notes), transform=ax.transAxes, ha="left", va="top",
                    fontsize=6, color="firebrick", family="monospace", zorder=10)

        ax.set_xlim(-0.05 * x_end, 1.05 * x_end)
        ax.set_ylim(y_lo - 0.08 * span, y_hi + 0.08 * span + (bump + 0.1 * span if sched else 0))
        ax.set_xlabel("Samples (1/16 clock)")
        ax.set_ylabel("Dressed frequency (MHz)")
        old = getattr(ax, "_program_builder_us_axis", None)
        if old is not None:                                  # redraws into the same ax must not stack axes
            try:
                old.remove()
            except Exception:
                pass
        ax._program_builder_us_axis = ax.secondary_xaxis("top", functions=(lambda s: s / spu, lambda t: t * spu))
        ax._program_builder_us_axis.set_xlabel("Time (µs)", fontsize=8)
        ax.set_title("Program timeline: dressed qubit frequencies + drives"
                     + (f"  [readout: {readout_group}]" if readout_group else ""), pad=28)
        if dressed is not None:
            ax.legend(fontsize=7, ncol=2, loc="best")

        if created_fig is not None:
            created_fig.tight_layout()
        return done()


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
        self.FFPlay_Const(self.Init_FFs, FF_delay_time + cfg['drive_offset']) # to make first segment asymptotic
        Loop through cfg['ProgramBuilderInfo']:
            Loop through pulses:
                t = calculate based on segment
                self.pulse(..., t=t)
        self.delay_auto()


        # treat FFReadout specially
        self.FFPlay_Const(self.FFReadouts, self.cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPlay_Const(-1 * self.FFReadouts, self.cfg["res_length"]) # invert readouts

        Invert combined_FF (there is a function that does this in FF_Helpers that inverts the gain to save waveform memory)
        Invert self.Init_FFs
        self.delay_auto()

'''

