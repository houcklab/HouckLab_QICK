"""
Zero-span two-tone parity-switching acquisition (QICK / RFSoC).

Canonical reference:
    docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md

This module contains the device-agnostic acquisition code:
    ZeroSpanParityProgStrobe       (Path A, v1) per-rep IQ via di_buf/dq_buf
    ZeroSpanParityProgDecimated    (Path B, v2) raw decimated ADC waveform
    ZeroSpanParity                 ExperimentClass dispatching on cfg["mode"]
    _validate_cfg                  fail-fast configuration validation (spec §5.3)

cfg keys consumed by ZeroSpanParity (see spec §5.2 for the full contract):

  === required (all modes) ===
  mode               "strobe" | "decimated"
  start_src          "internal" | "external"
  res_ch, qubit_ch, ro_chs, nqz, qubit_nqz, mixer_freq
  read_pulse_freq    MHz, parking freq for readout tone
  parity_drive_freq  MHz, parking freq for qubit tone (one parity peak)
  qubit_gain, pulse_gain, res_phase
  adc_trig_offset    us
  read_length        us

  === required if mode=="strobe" ===
  sample_period_us   us, sample cadence
  reps_per_chunk     int, samples per acquire() call (chunking via chunked_acquire)

  === required if mode=="decimated" ===
  capture_length_us  us, duration of const tone pulse (must cover the readout window)
  soft_avgs          int, software-averaged rounds (must be 1 unless
                     allow_soft_avgs=True; >1 destroys parity trajectories)
  === optional in mode=="decimated" ===
  n_captures         int, number of outer captures to stitch (default 1).
                     gap_indices marks the boundaries.
  allow_soft_avgs    bool, opt-in to soft_avgs > 1 (non-time-resolved).

Validation errors include the spec rule number, the offending value, and the
violated bound.

NOTE: For decimated mode the time axis t_us is computed from
soccfg['readouts'][ro_ch]['f_output']. On some firmware revisions this is
empirically not the true decimated sample rate (see
_loopback_check_ZeroSpanParity.py). Metadata fields read_length_us,
capture_length_us, samples_per_capture, and decimated_fs_source are persisted
so the time axis can be reconstructed post-hoc once the true rate is known.
"""

import numpy as np
from qick import AveragerProgram

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import (
    ExperimentClass,
)


_STROBE_REQUIRED = (
    "sample_period_us", "reps_per_chunk",
)
_DECIMATED_REQUIRED = (
    "capture_length_us", "soft_avgs",
)
# n_captures is optional; defaults to 1. When >1, _acquire_decimated runs the
# acquire_decimated() call back-to-back and stitches results with gap_indices,
# mirroring chunked_acquire semantics for strobe mode.
_SHARED_REQUIRED = (
    "mode", "start_src", "res_ch", "qubit_ch", "ro_chs", "nqz", "qubit_nqz",
    "mixer_freq", "read_pulse_freq", "parity_drive_freq",
    "qubit_gain", "pulse_gain", "res_phase",
    "adc_trig_offset", "read_length",
)


def _validate_cfg(cfg, soccfg):
    """
    Fail-fast validation of a ZeroSpanParity cfg dict (spec §5.3 rules 1-8).

    Raises RuntimeError on the first violation found. Each error message names
    the rule number, the offending value, and the violated bound.
    """
    # Presence checks first — easier to debug than indexing errors below.
    missing = [k for k in _SHARED_REQUIRED if k not in cfg]
    if missing:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] missing required keys: {missing}"
        )
    mode = cfg["mode"]
    if mode not in ("strobe", "decimated"):
        raise RuntimeError(
            f"[ZeroSpanParity cfg] cfg['mode']={mode!r} must be 'strobe' or 'decimated'"
        )
    extra = _STROBE_REQUIRED if mode == "strobe" else _DECIMATED_REQUIRED
    missing_extra = [k for k in extra if k not in cfg]
    if missing_extra:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] missing keys for mode={mode!r}: {missing_extra}"
        )

    # Rule 1: sample_period floor
    if mode == "strobe":
        sp = float(cfg["sample_period_us"])
        floor = float(cfg["adc_trig_offset"]) + float(cfg["read_length"]) + 1.0
        if sp < floor:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 1] sample_period_us={sp} us is below "
                f"floor (adc_trig_offset + read_length + 1.0 = {floor:.3f} us). "
                f"Increase sample_period_us or shorten read_length."
            )

    # Rules 2 & 3: const-pulse 16-bit cycle cap
    # us2cycles depends on the channel; soccfg exposes us2cycles via soccfg.us2cycles
    if mode == "strobe":
        cyc_q = soccfg.us2cycles(cfg["sample_period_us"], gen_ch=cfg["qubit_ch"])
        cyc_r = soccfg.us2cycles(cfg["sample_period_us"], gen_ch=cfg["res_ch"])
        for label, cyc in [("qubit_ch", cyc_q), ("res_ch", cyc_r)]:
            if cyc > 65535:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 2] sample_period_us yields "
                    f"{cyc} cycles on {label} > 65535 cap. "
                    f"Reduce sample_period_us."
                )
    else:
        cyc_q = soccfg.us2cycles(cfg["capture_length_us"], gen_ch=cfg["qubit_ch"])
        cyc_r = soccfg.us2cycles(cfg["capture_length_us"], gen_ch=cfg["res_ch"])
        for label, cyc in [("qubit_ch", cyc_q), ("res_ch", cyc_r)]:
            if cyc > 65535:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 3] capture_length_us yields "
                    f"{cyc} cycles on {label} > 65535 cap. "
                    f"Reduce capture_length_us."
                )

    # Rules 4 & 5: avg_maxlen / buf_maxlen
    ro_ch = cfg["ro_chs"][0]
    try:
        ro_info = soccfg["readouts"][ro_ch]
    except (KeyError, IndexError, TypeError) as ex:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] cannot read soccfg['readouts'][{ro_ch}]: {ex!r}"
        )
    if mode == "strobe":
        avg_maxlen = int(ro_info["avg_maxlen"])
        reps = int(cfg["reps_per_chunk"])
        if reps > avg_maxlen:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 4] reps_per_chunk={reps} > "
                f"avg_maxlen={avg_maxlen} for readout ch {ro_ch}. "
                f"Reduce reps_per_chunk (and increase n_chunks if longer record "
                f"is needed)."
            )
    else:
        # The decimated buffer is sized by the declared readout length
        # (declare_readout(length=us2cycles(read_length))), NOT by the const
        # pulse length (capture_length_us). Check read_length against the
        # buffer cap.
        #
        # CAVEAT: this estimate uses the nominal decimated rate from
        # soccfg["readouts"][ro_ch]["f_output"]. The actual buffer length
        # depends on how declare_readout converts `us2cycles(read_length)`
        # (without ro_ch) into readout-clock cycles, then decimates. On
        # firmware where tProc and readout clocks differ, the exact returned
        # sample count may disagree with this estimate by O(1) sample.
        # The check remains a useful pre-flight bound (sufficient, not
        # exact); hardware loopback should confirm the exact count.
        buf_maxlen = int(ro_info["buf_maxlen"])
        decimated_fs_MHz = float(ro_info["f_output"])
        n_samples = int(round(float(cfg["read_length"]) * decimated_fs_MHz))
        if n_samples > buf_maxlen:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 5] read_length={cfg['read_length']} "
                f"us => {n_samples} decimated samples > buf_maxlen={buf_maxlen} "
                f"for readout ch {ro_ch} at {decimated_fs_MHz} MHz. "
                f"Reduce read_length."
            )
        # Sanity check: pulse must cover the readout window. The readout fires
        # at adc_trig_offset and lasts read_length, so capture_length_us must
        # be >= adc_trig_offset + read_length.
        cap_us = float(cfg["capture_length_us"])
        floor = float(cfg["adc_trig_offset"]) + float(cfg["read_length"])
        if cap_us < floor:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 5b] capture_length_us={cap_us} us "
                f"< adc_trig_offset + read_length = {floor:.3f} us. "
                f"Pulse ends before readout window closes. Increase "
                f"capture_length_us or shorten read_length."
            )

    # Rule 8: parity_drive_freq within DAC range. Use try/except instead of
    # `in soccfg` because QickConfig.__getitem__ exists but __contains__ does
    # not, which makes `"gens" in soccfg` crash on KeyError.
    qch = cfg["qubit_ch"]
    try:
        gen_info = soccfg["gens"][qch]
    except (KeyError, IndexError, TypeError):
        gen_info = None
    if gen_info is not None:
        try:
            f_max = float(gen_info["f_dds"])
        except (KeyError, TypeError):
            f_max = None
        if f_max is not None:
            f_drive = float(cfg["parity_drive_freq"])
            if not (0.0 <= f_drive <= f_max):
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 8] parity_drive_freq={f_drive} MHz "
                    f"outside qubit channel {qch} DDS range [0, {f_max}] MHz."
                )

    # Rules 6 & 7 are caller-level constraints (Recalibrate flags vs cached values).
    # The orchestrator enforces them before constructing cfg, so they are not
    # re-checked here.


class ZeroSpanParityProgStrobe(AveragerProgram):
    """
    Path A: stroboscopic per-rep IQ acquisition for zero-span parity measurement.

    Both tones are held on for the full duration of each rep; reps run back-to-
    back with syncdelay=0 so the qubit drive is effectively CW from the qubit's
    perspective (apart from a small inter-rep tProc-overhead gap).

    Each rep contributes one integrated IQ point to prog.di_buf[ro_ch] /
    prog.dq_buf[ro_ch]. The ExperimentClass wrapper reshapes those into a time-
    resolved 1-D IQ trace with sample period = cfg["sample_period_us"].

    Required cfg keys: see module docstring.
    """

    def _setup_two_tones(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                          mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"]),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])
        f_qub = self.freq2reg(cfg["parity_drive_freq"], gen_ch=cfg["qubit_ch"])
        return f_res, f_qub

    def initialize(self):
        cfg = self.cfg
        f_res, f_qub = self._setup_two_tones()
        period_cyc_q = self.us2cycles(cfg["sample_period_us"], gen_ch=cfg["qubit_ch"])
        period_cyc_r = self.us2cycles(cfg["sample_period_us"], gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=f_qub,
                                  phase=0, gain=cfg["qubit_gain"],
                                  length=period_cyc_q)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res,
                                  phase=cfg["res_phase"], gain=cfg["pulse_gain"],
                                  length=period_cyc_r)
        self.synci(200)

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=0,
        )


class ZeroSpanParityProgDecimated(AveragerProgram):
    """
    Path B: decimated raw-ADC waveform acquisition for zero-span parity.

    Both tones held on for the full capture window; ADC streams decimated samples
    for the entire window. ExperimentClass wrapper calls prog.acquire_decimated()
    instead of prog.acquire() to extract the (length, 2) IQ array.

    Sample period = 1 / soccfg['readouts'][ro_ch]['f_output'] (us).
    Total length = capture_length_us * f_output_MHz samples, capped by buf_maxlen.
    """

    def _setup_two_tones(self):
        # Identical to strobe — could be hoisted to a mixin, but the spec calls
        # for both classes to be self-contained for clarity. Duplication is
        # bounded (~12 lines) and changes to one usually require revisiting both.
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                          mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"]),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])
        f_qub = self.freq2reg(cfg["parity_drive_freq"], gen_ch=cfg["qubit_ch"])
        return f_res, f_qub

    def initialize(self):
        cfg = self.cfg
        f_res, f_qub = self._setup_two_tones()
        capture_cyc_q = self.us2cycles(cfg["capture_length_us"], gen_ch=cfg["qubit_ch"])
        capture_cyc_r = self.us2cycles(cfg["capture_length_us"], gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=f_qub,
                                  phase=0, gain=cfg["qubit_gain"],
                                  length=capture_cyc_q)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res,
                                  phase=cfg["res_phase"], gain=cfg["pulse_gain"],
                                  length=capture_cyc_r)
        self.synci(200)

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=0,
        )


class ZeroSpanParity(ExperimentClass):
    """
    Dispatcher ExperimentClass for the zero-span parity measurement.

    cfg["mode"] selects between strobe (Path A) and decimated (Path B). See
    module docstring + spec §5 for the full configuration contract.

    Saves data via the standard ExperimentClass HDF5 + JSON pattern:
      .h5  : datasets I, Q, t_us, gap_indices; attrs sample_period_us, mode, etc.
      .json: cfg dict (via save_config)
      .png : optional, written by display() if called
    """

    def __init__(self, soc=None, soccfg=None, path="", outerFolder="",
                 prefix="data", cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, cfg=cfg, config_file=config_file,
                         progress=progress)
        _validate_cfg(self.cfg, self.soccfg)
        mode = self.cfg["mode"]
        # AveragerProgram.__init__ reads cfg["reps"] during make_program() —
        # we must set it BEFORE constructing the program. For strobe mode,
        # reps_per_chunk drives the loop; for decimated mode, reps=1 and the
        # whole capture is one shot (averaged in software via soft_avgs).
        if mode == "strobe":
            self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
            self.prog = ZeroSpanParityProgStrobe(self.soccfg, self.cfg)
        elif mode == "decimated":
            self.cfg["reps"] = 1
            self.prog = ZeroSpanParityProgDecimated(self.soccfg, self.cfg)
        else:
            # _validate_cfg already raised, but keep defensive check.
            raise ValueError(f"Unknown mode: {mode!r}")

    def acquire(self, progress=False, **kwargs):
        mode = self.cfg["mode"]
        if mode == "strobe":
            return self._acquire_strobe(progress=progress)
        if mode == "decimated":
            return self._acquire_decimated(progress=progress)
        raise ValueError(f"Unknown mode: {mode!r}")

    def _acquire_strobe(self, progress=False):
        import datetime
        cfg = self.cfg
        wall_clock_start = datetime.datetime.now().isoformat()
        # cfg["reps"] was already set to reps_per_chunk in __init__ before
        # AveragerProgram.make_program() ran. No further mutation needed here.
        prog = self.prog
        # AveragerProgram.acquire returns (avg_di, avg_dq) along with filling
        # prog.di_buf/prog.dq_buf with the raw per-rep stream.
        prog.acquire(
            self.soc,
            load_pulses=True,
            start_src=cfg["start_src"],
            progress=progress,
            readouts_per_experiment=1,
            save_experiments=None,
        )
        ro_ch = cfg["ro_chs"][0]
        # Normalize accumulated di_buf/dq_buf by the number of readout-window
        # cycles so I/Q are in the same units as g/e centroids computed by
        # mSingleShotProgramFFMUX.collect_shots (which divides by
        # us2cycles(readout_length, ro_ch=0)). Without this the apriori
        # separator from get_apriori_separator_from_singleshot is on a
        # different scale than the strobe trace and classification is wrong.
        ro_cycles = float(self.soccfg.us2cycles(cfg["read_length"], ro_ch=ro_ch))
        if ro_cycles <= 0:
            ro_cycles = 1.0
        I = np.asarray(prog.di_buf[ro_ch], dtype=float).ravel() / ro_cycles
        Q = np.asarray(prog.dq_buf[ro_ch], dtype=float).ravel() / ro_cycles
        sp = float(cfg["sample_period_us"])
        t_us = np.arange(I.size, dtype=float) * sp
        data = {
            "I": I, "Q": Q, "t_us": t_us,
            "gap_indices": np.array([], dtype=int),
            "wall_clock_start": wall_clock_start,
            "sample_period_us": sp,
            "read_length_us": float(cfg["read_length"]),
            "adc_trig_offset_us": float(cfg["adc_trig_offset"]),
            "ro_norm_cycles": ro_cycles,
            "mode": "strobe",
        }
        self.data = {"data": data}
        return data

    def _acquire_decimated(self, progress=False):
        import datetime
        cfg = self.cfg
        wall_clock_start = datetime.datetime.now().isoformat()
        prog = self.prog
        ro_ch = cfg["ro_chs"][0]
        # TODO(hardware): the loopback smoke test on this firmware empirically
        # observed that soccfg['readouts'][ro_ch]['f_output'] is NOT the true
        # rate of samples returned by acquire_decimated. Until that mismatch is
        # resolved, sample_period_us below is the *nominal* rate from soccfg
        # and t_us cannot be trusted as an absolute physical time axis. We
        # persist read_length_us and the raw returned-sample count so the time
        # axis can be reconstructed once the true rate is known.
        decimated_fs_MHz = float(self.soccfg["readouts"][ro_ch]["f_output"])

        n_captures = int(cfg.get("n_captures", 1))
        if n_captures < 1:
            raise RuntimeError(
                f"[ZeroSpanParity] n_captures={n_captures} must be >= 1"
            )
        soft_avgs = int(cfg.get("soft_avgs", 1))
        if soft_avgs > 1:
            # soft_avgs > 1 averages independent captures together — it
            # destroys per-shot parity trajectories. Allowed only when the
            # caller has explicitly opted in via an averaged-mode flag.
            if not cfg.get("allow_soft_avgs", False):
                raise RuntimeError(
                    f"[ZeroSpanParity] soft_avgs={soft_avgs} > 1 averages "
                    f"across independent captures and destroys parity "
                    f"trajectories. Set cfg['allow_soft_avgs']=True if you "
                    f"really want a non-time-resolved averaged trace."
                )

        I_parts, Q_parts, t_parts = [], [], []
        chunk_wall_clocks = []
        gap_indices = []
        cum_offset_us = 0.0
        cum_idx = 0
        for ci in range(n_captures):
            chunk_wall_clocks.append(datetime.datetime.now().isoformat())
            # soft_avgs is handled by AveragerProgram.__init__ from cfg["soft_avgs"];
            # passing it again here would collide with the kwarg that
            # AveragerProgram.acquire_decimated injects internally.
            dec = prog.acquire_decimated(
                self.soc,
                load_pulses=(ci == 0),
                start_src=cfg["start_src"],
                progress=progress,
            )
            # acquire_decimated returns a list with one IQ array per ro_ch.
            # Shape conventions vary by firmware:
            #   (length, 2)         — I,Q is the trailing axis
            #   (2, length)         — I,Q is the leading axis (observed on tprocv2 firmware)
            #   (n_reps, length, 2) — multi-rep, flatten across reps
            arr = np.asarray(dec[0])
            if arr.ndim == 2 and arr.shape[1] == 2:
                I_c = arr[:, 0]; Q_c = arr[:, 1]
            elif arr.ndim == 2 and arr.shape[0] == 2:
                I_c = arr[0]; Q_c = arr[1]
            elif arr.ndim == 3:
                I_c = arr.reshape(-1, 2)[:, 0]
                Q_c = arr.reshape(-1, 2)[:, 1]
            else:
                raise RuntimeError(f"unexpected acquire_decimated shape: {arr.shape}")
            sp = 1.0 / decimated_fs_MHz  # us per decimated sample (nominal)
            t_c = np.arange(I_c.size, dtype=float) * sp
            if ci > 0:
                cum_offset_us = float(t_parts[-1][-1]) + sp
                gap_indices.append(cum_idx)
            t_shifted = t_c + cum_offset_us
            I_parts.append(I_c); Q_parts.append(Q_c); t_parts.append(t_shifted)
            cum_idx += I_c.size

        I = np.concatenate(I_parts)
        Q = np.concatenate(Q_parts)
        t_us = np.concatenate(t_parts)
        sp = 1.0 / decimated_fs_MHz
        data = {
            "I": I, "Q": Q, "t_us": t_us,
            "gap_indices": np.asarray(gap_indices, dtype=int),
            "wall_clock_start": wall_clock_start,
            "chunk_wall_clock_starts": chunk_wall_clocks,
            "n_captures": int(n_captures),
            "sample_period_us": sp,
            "decimated_fs_MHz": decimated_fs_MHz,
            "decimated_fs_source": "soccfg.f_output_unverified",
            "read_length_us": float(cfg["read_length"]),
            "capture_length_us": float(cfg["capture_length_us"]),
            "adc_trig_offset_us": float(cfg["adc_trig_offset"]),
            "samples_per_capture": int(I.size // max(n_captures, 1)),
            "soft_avgs": soft_avgs,
            "mode": "decimated",
        }
        self.data = {"data": data}
        return data

    def save_data(self, data=None):
        """Write IQ trace + metadata to self.fname (.h5)."""
        import h5py
        if data is None:
            data = self.data["data"] if isinstance(self.data, dict) and "data" in self.data else self.data
        with h5py.File(self.fname, "w") as f:
            f.create_dataset("I", data=np.asarray(data["I"]))
            f.create_dataset("Q", data=np.asarray(data["Q"]))
            f.create_dataset("t_us", data=np.asarray(data["t_us"]))
            f.create_dataset("gap_indices",
                             data=np.asarray(data.get("gap_indices", []), dtype=int))
            # Per-chunk wall-clock starts (when chunked_acquire was used, or
            # when n_captures > 1 in decimated mode) — needed to reconstruct
            # actual inter-chunk gaps post-hoc.
            if "chunk_wall_clock_starts" in data:
                wcs = [str(s) if s is not None else "" for s in
                       data["chunk_wall_clock_starts"]]
                f.create_dataset(
                    "chunk_wall_clock_starts",
                    data=np.asarray(wcs, dtype=h5py.string_dtype("utf-8")),
                )
            # Scalar metadata. Keep this list in sync with whatever the
            # acquire-path dicts return; missing keys are silently skipped.
            scalar_keys = (
                "wall_clock_start", "sample_period_us", "mode",
                "decimated_fs_MHz", "decimated_fs_source",
                "read_length_us", "capture_length_us", "adc_trig_offset_us",
                "ro_norm_cycles", "samples_per_capture",
                "n_chunks", "n_captures", "soft_avgs",
            )
            for k in scalar_keys:
                if k in data:
                    try:
                        f.attrs[k] = data[k]
                    except TypeError:
                        f.attrs[k] = str(data[k])

    def display(self, data=None, plotDisp=False, **kwargs):
        """No-op for live display; analysis module generates plots from the .h5."""
        return None


if __name__ == "__main__":
    # Synthetic soccfg-like object for unit testing _validate_cfg without QICK hardware.
    class _FakeSocCfg:
        def __init__(self):
            self._d = {
                "readouts": {0: {"avg_maxlen": 16384, "buf_maxlen": 8192,
                                 "f_output": 100.0}},
                "gens": {0: {"f_dds": 6144.0}, 1: {"f_dds": 6144.0}},
            }
        def us2cycles(self, us, gen_ch=None, ro_ch=None):
            # Pretend 384 MHz clock on every channel.
            return int(round(us * 384.0))
        def __getitem__(self, k): return self._d[k]
        def __contains__(self, k): return k in self._d

    sc = _FakeSocCfg()
    base = {
        "mode": "strobe", "start_src": "internal",
        "res_ch": 0, "qubit_ch": 1, "ro_chs": [0],
        "nqz": 2, "qubit_nqz": 2, "mixer_freq": 0.0,
        "read_pulse_freq": 7000.0, "parity_drive_freq": 3050.0,
        "qubit_gain": 5000, "pulse_gain": 1000, "res_phase": 0,
        "adc_trig_offset": 0.5, "read_length": 5.0,
        "sample_period_us": 20.0, "reps_per_chunk": 1000,
    }

    # Valid cfg passes.
    _validate_cfg(base, sc)
    print("_validate_cfg valid strobe: OK")

    # Rule 1: sample_period too small
    bad = dict(base); bad["sample_period_us"] = 1.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 1" in str(ex), ex
    else: raise AssertionError("expected rule 1 to fire")

    # Rule 2: sample_period too long => cycles > 65535
    bad = dict(base); bad["sample_period_us"] = 500.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 2" in str(ex), ex
    else: raise AssertionError("expected rule 2 to fire")

    # Rule 4: reps_per_chunk too large
    bad = dict(base); bad["reps_per_chunk"] = 10**6
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 4" in str(ex), ex
    else: raise AssertionError("expected rule 4 to fire")

    # Rule 5: read_length too long (decimated mode) — buffer cap is sized
    # by the declared readout window, not by the const-pulse length.
    dec_base = dict(base)
    dec_base.update({"mode": "decimated", "capture_length_us": 50.0,
                     "soft_avgs": 1})
    del dec_base["sample_period_us"]
    del dec_base["reps_per_chunk"]
    _validate_cfg(dec_base, sc)  # read_length=5 us * 100 MHz = 500 samples < 8192
    bad = dict(dec_base); bad["read_length"] = 90.0  # 9000 samples > 8192
    bad["capture_length_us"] = 100.0                  # keep capture >= read+offset
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 5" in str(ex) and "rule 5b" not in str(ex), ex
    else: raise AssertionError("expected rule 5 to fire")

    # Rule 5b: pulse shorter than readout window — pulse ends before readout closes.
    bad = dict(dec_base); bad["capture_length_us"] = 3.0  # < adc_trig_offset + read_length = 5.5
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 5b" in str(ex), ex
    else: raise AssertionError("expected rule 5b to fire")

    # Rule 8: parity_drive_freq out of range
    bad = dict(base); bad["parity_drive_freq"] = 9000.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 8" in str(ex), ex
    else: raise AssertionError("expected rule 8 to fire")

    # Missing key
    bad = dict(base); del bad["qubit_gain"]
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "missing required keys" in str(ex)
    else: raise AssertionError("expected missing-key error")

    print("_validate_cfg all rules: OK")

    # --- soft_avgs > 1 opt-in gate (decimated mode) --------------------------
    # Per Codex review: soft_avgs > 1 averages across independent parity
    # captures and destroys the time-resolved trajectory. _acquire_decimated
    # must reject it unless the user explicitly opts in.
    class _StubExp:
        """Minimal ZeroSpanParity stand-in to exercise _acquire_decimated's
        soft_avgs gate without instantiating QICK programs."""
        _acquire_decimated = ZeroSpanParity._acquire_decimated
        def __init__(self, cfg, soccfg):
            self.cfg = cfg
            self.soccfg = soccfg
            self.soc = None
            self.prog = None
    cfg_soft = dict(base)
    cfg_soft.update({"mode": "decimated", "capture_length_us": 50.0,
                     "soft_avgs": 4, "read_length": 5.0,
                     "adc_trig_offset": 0.5})
    del cfg_soft["sample_period_us"]; del cfg_soft["reps_per_chunk"]
    try:
        _StubExp(cfg_soft, sc)._acquire_decimated(progress=False)
    except RuntimeError as ex:
        assert "soft_avgs" in str(ex), ex
    else:
        raise AssertionError("expected soft_avgs gate to raise without opt-in")
    print("_acquire_decimated soft_avgs gate fires without opt-in: OK")

    # --- strobe I/Q normalization matches single-shot units ------------------
    # Per Codex review: strobe raw di_buf values are integrated over the
    # readout window (~us2cycles(read_length, ro_ch) summands), but the
    # apriori separator from mSingleShotProgramFFMUX.collect_shots is in
    # per-cycle units (di_buf / us2cycles(readout_length, ro_ch=0)). The fix
    # in _acquire_strobe divides I/Q by the same divisor. Regression guard:
    # synthesize a di_buf that mimics 100-cycle integration of a unit signal,
    # call the normalization path, and confirm the resulting per-sample I is
    # ~1.0 (per-cycle) rather than ~100.
    class _FakeProg:
        def __init__(self, di_val, dq_val, n):
            self.di_buf = {0: np.full(n, di_val, dtype=float)}
            self.dq_buf = {0: np.full(n, dq_val, dtype=float)}
        def acquire(self, *_a, **_k):
            return None
    class _StrobeStub:
        _acquire_strobe = ZeroSpanParity._acquire_strobe
        def __init__(self, cfg, soccfg, prog):
            self.cfg = cfg
            self.soccfg = soccfg
            self.soc = None
            self.prog = prog
    # 100-cycle readout (5 us * 100 MHz / 5 us * 384 MHz tProc - whichever the
    # fake uses): with our _FakeSocCfg, us2cycles(5, ro_ch=0) returns
    # 5 * 384 = 1920 (the fake hardcodes 384 MHz regardless of channel). The
    # important check is that I_normalized = di_val / 1920, not I = di_val.
    cfg_strobe = dict(base)
    n_reps = 1000
    cfg_strobe["reps_per_chunk"] = n_reps
    fake = _FakeProg(di_val=192000.0, dq_val=0.0, n=n_reps)
    stub = _StrobeStub(cfg_strobe, sc, fake)
    out = stub._acquire_strobe(progress=False)
    # Expected I per sample = 192000 / us2cycles(5, ro_ch=0) = 192000/1920 = 100.0
    assert abs(float(out["I"][0]) - 100.0) < 1e-6, (
        f"strobe normalization wrong: got {out['I'][0]}, expected 100.0"
    )
    assert out["ro_norm_cycles"] == 1920.0, out["ro_norm_cycles"]
    assert out["read_length_us"] == 5.0
    assert out["mode"] == "strobe"
    print("_acquire_strobe normalizes I/Q by us2cycles(read_length, ro_ch=0): OK")
