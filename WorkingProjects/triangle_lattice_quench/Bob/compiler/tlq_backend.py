"""Triangle-lattice backend: resolved sequence -> one stitched FF waveform per channel,
cycle-aligned drives, and the cfg dict BobProgram reads.

Stitching follows ProgramBuilder (per channel):

    head    channel_delays[j] samples at the init gains        (ProgramBuilder's t_offset)
    body    every segment's samples, in order
    tail    (max delay - delay[j]) + readout_pad samples at the readout gains

Deliberate differences from ProgramBuilder:

* Compensation is applied to ``waveform - init`` with ``init`` as the offset, as MottQuench
  and BSClean do. ProgramBuilder passes the absolute waveform with the init as offset,
  which adds the init level twice.
* The waveform is padded to a whole number of clock cycles at the END (at the readout
  gains). FFPlay_Arb pads the beginning, which shifts the flux by up to 15 samples
  relative to the drives.
* Gains outside the DAC range are reported as problems and clipped, instead of printed.
"""
from __future__ import annotations

import numpy as np

from ..config.problems import Problem
from ..config.resolver import ResolvedSequence, Resolver
from ..config.station import Station
from ..config.validate import validate
from ..core.sequence import Sequence
from ..hardware.compensation import Compensator
from .backend import Backend, CompiledDrive, CompiledProgram, CompileError
from .timing import SAMPLES_PER_CYCLE, ceil_to_cycle, schedule_drives


class TLQBackend(Backend):
    name = "triangle_lattice_quench"

    def __init__(self, station: Station, compensator: Compensator | None = None, compensate: bool = True):
        self.station = station
        self.compensator = compensator if compensator is not None else Compensator.from_station(station)
        self.compensate = compensate

    def compile(self, seq: Sequence, res: ResolvedSequence) -> CompiledProgram:
        if not res.ok:
            raise CompileError("the sequence has errors; fix them before compiling",
                               [p for p in res.problems if p.level == "error"])
        if not res.segments:
            raise CompileError("the sequence has no flux segments")
        st = self.station
        n = st.n_channels
        spu = st.samples_per_us
        maxv = float(st.data.get("max_gain", 32766))
        notes: list = []

        waves = [s.wave for s in res.segments]
        init = np.asarray(waves[0].start_gains, float)
        if res.measure is not None and res.measure.ok:
            ro = np.asarray(res.measure.params["ff_readout_gains"], float)
        else:
            ro = np.asarray(waves[-1].end_gains, float)

        delays = np.asarray(st.data.get("ff_channel_delays_samples", [0] * n), int)
        if delays.shape != (n,):
            raise CompileError(f"station ff_channel_delays_samples must have {n} entries")
        delays = delays - delays.min()
        pad = int(st.data.get("readout_pad_samples", 32))

        # ---- flux: head (per-channel delay at init) + body + tail (at readout), padded to whole cycles
        body = np.concatenate([w.samples for w in waves], axis=1) if waves else np.zeros((n, 0))
        rows = []
        for j in range(n):
            tail = int(delays.max() - delays[j]) + pad
            rows.append(np.concatenate([np.full(int(delays[j]), init[j]), body[j], np.full(tail, ro[j])]))
        raw = np.vstack(rows)
        total = ceil_to_cycle(raw.shape[1])
        if total > raw.shape[1]:
            raw = np.hstack([raw, np.repeat(ro[:, None], total - raw.shape[1], axis=1)])

        compensated = False
        ff = raw.copy()
        if self.compensate and self.compensator.available():
            # filter the step relative to the init level, then add the init back (see module docstring)
            ff = np.vstack([self.compensator.apply(raw[j] - init[j], init[j], j + 1) for j in range(n)])
            compensated = True
        elif self.compensate:
            notes.append("IIR compensation files not found; the waveform is uncompensated. Copy them into "
                         f"library/stations/{st.name}/iir/ to enable it.")

        over = np.abs(ff) > maxv
        if over.any():
            chans = sorted({int(j) + 1 for j in np.where(over.any(axis=1))[0]})
            notes.append(f"FF waveform exceeds ±{maxv:.0f} on Q{', Q'.join(map(str, chans))} after "
                         f"{'compensation' if compensated else 'stitching'}; clipped.")
            res.problems.append(Problem("warning", notes[-1]))
            ff = np.clip(ff, -maxv, maxv)

        # ---- drives
        lengths = [w.length for w in waves]
        bounds = list(np.concatenate([[0], np.cumsum(lengths)]).astype(int))
        drives_by_seg = [[] for _ in waves]
        for pi, rp in enumerate(res.pulses):
            if rp.drive is not None and rp.segment_index >= 0:
                drives_by_seg[rp.segment_index].append((pi, rp.drive))
        offset_cycles = int(st.data.get("drive_offset_cycles", 0))
        sched = schedule_drives(lengths, drives_by_seg, spu, offset_cycles)
        drives = []
        for sd in sched:
            rp = res.pulses[sd.pulse_index]
            d = rp.drive
            drives.append(CompiledDrive(d.qubit, d.freq_mhz, d.gain, d.phase_deg, d.sigma_us, d.length_us(),
                                        sd.t_us, sd.segment_index, rp.block.id, rp.block.name))

        qick_cfg = self._qick_cfg(seq, res, ff, init, ro, drives, offset_cycles)
        return CompiledProgram(
            samples_per_us=spu, ff_raw=raw, ff=ff, init_gains=init, readout_gains=ro,
            segment_bounds=bounds, segment_names=[s.block.name for s in res.segments],
            segment_acts=[s.block.act for s in res.segments], segment_ids=[s.block.id for s in res.segments],
            channel_delays=delays, drives=drives, qick_cfg=qick_cfg, compensated=compensated, notes=notes)

    # ------------------------------------------------------------------ qick cfg
    def _qick_cfg(self, seq, res, ff, init, ro, drives, drive_offset_cycles) -> dict:
        st = self.station.data
        cfg = {k: st[k] for k in ("res_ch", "qubit_ch", "res_nqz", "qubit_nqz", "res_mixer_freq",
                                  "qubit_mixer_freq", "res_phase", "fast_flux_chs")}
        cfg["fast_flux_delays"] = list(st.get("fast_flux_delays_us", [0] * len(st["fast_flux_chs"])))
        cfg["relax_delay"] = seq.settings.relax_delay_us if seq.settings.relax_delay_us is not None \
            else st.get("relax_delay", 200)
        cfg["reps"] = int(seq.settings.reps)
        cfg["rounds"] = int(seq.settings.rounds)
        if res.measure is not None and res.measure.ok:
            cfg.update(res.measure.readout)
            cfg["res_length"] = float(res.measure.params["res_length_us"])
            cfg["bob_measure_mode"] = res.measure.params["mode"]
        else:
            cfg.update({"res_freqs": [], "res_gains": [], "ro_chs": [], "readout_lengths": [],
                        "adc_trig_delays": [], "res_length": float(st.get("res_length", 10))})
        qubit_lo = float(st.get("qubit_LO", 0))
        cfg["bob"] = {
            "ff_waveforms": ff,
            "init_gains": init,
            "readout_gains": ro,
            "init_hold_us": float(st.get("init_hold_us", 5.0)),
            # a negative drive offset starts the flux that much earlier instead of delaying the drives
            "ff_lead_us": max(0, -int(drive_offset_cycles)) * SAMPLES_PER_CYCLE / self.station.samples_per_us,
            "dc_balance": bool(st.get("dc_balance", True)),
            "max_gain": float(st.get("max_gain", 32766)),
            "drives": [{"freq": d.freq_mhz - qubit_lo, "gain": d.gain / float(st.get("max_gain", 32766)),
                        "phase": d.phase_deg, "sigma": d.sigma_us, "length": d.length_us, "t": d.t_us,
                        "qubit": d.qubit} for d in drives],
        }
        return cfg


def compile_sequence(seq, station, calib, point=None, compensate=True):
    """Resolve, validate and compile in one call. Returns (compiled or None, resolved, problems)."""
    res = Resolver(station, calib).resolve(seq, point)
    problems = list(res.problems) + validate(seq, res, station)
    res.problems = problems
    compiled = None
    if seq.segments and not any(p.level == "error" for p in problems):
        try:
            compiled = TLQBackend(station, compensate=compensate).compile(seq, res)
        except CompileError as exc:
            problems.append(Problem("error", str(exc)))
    return compiled, res, problems
