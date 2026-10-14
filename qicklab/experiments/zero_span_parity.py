"""Zero-span two-tone parity-switching acquisition: strobe (per-rep IQ) and decimated
(raw ADC trace) paths, with fail-fast cfg validation.

cfg contract and the validation rules: docs/experiments/zero_span_parity.md.
"""

import numpy as np
from qick import AveragerProgram

from qicklab.core.experiment import (
    ExperimentClass,
)

_STROBE_REQUIRED = (
    "sample_period_us",
    "reps_per_chunk",
)
_DECIMATED_REQUIRED = (
    "capture_length_us",
    "soft_avgs",
)
_SHARED_REQUIRED = (
    "mode",
    "start_src",
    "res_ch",
    "qubit_ch",
    "ro_chs",
    "nqz",
    "qubit_nqz",
    "mixer_freq",
    "read_pulse_freq",
    "parity_drive_freq",
    "qubit_gain",
    "pulse_gain",
    "res_phase",
    "adc_trig_offset",
    "read_length",
)


def _validate_cfg(cfg, soccfg):
    """Raise RuntimeError on the first violated rule (1-5, 8, 9 of
    docs/experiments/zero_span_parity.md#the-nine-validation-rules)."""
    missing = [k for k in _SHARED_REQUIRED if k not in cfg]
    if missing:
        raise RuntimeError(f"[ZeroSpanParity cfg] missing required keys: {missing}")
    mode = cfg["mode"]
    if mode not in ("strobe", "decimated"):
        raise RuntimeError(
            f"[ZeroSpanParity cfg] cfg['mode']={mode!r} must be 'strobe' or 'decimated'"
        )
    extra = _STROBE_REQUIRED if mode == "strobe" else _DECIMATED_REQUIRED
    missing_extra = [k for k in extra if k not in cfg]
    if missing_extra:
        raise RuntimeError(f"[ZeroSpanParity cfg] missing keys for mode={mode!r}: {missing_extra}")

    if mode == "strobe":
        sp = float(cfg["sample_period_us"])
        floor = float(cfg["adc_trig_offset"]) + float(cfg["read_length"]) + 1.0
        if sp < floor:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 1] sample_period_us={sp} us is below "
                f"floor (adc_trig_offset + read_length + 1.0 = {floor:.3f} us). "
                f"Increase sample_period_us or shorten read_length."
            )

    def _check_cycle_cap(length_key, rule_no):
        for label in ("qubit_ch", "res_ch"):
            cyc = soccfg.us2cycles(cfg[length_key], gen_ch=cfg[label])
            if cyc > 65535:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule {rule_no}] {length_key} yields "
                    f"{cyc} cycles on {label} > 65535 cap. Reduce {length_key}."
                )

    if mode == "strobe":
        _check_cycle_cap("sample_period_us", 2)
    else:
        _check_cycle_cap("capture_length_us", 3)

    ro_ch = cfg["ro_chs"][0]
    try:
        ro_info = soccfg["readouts"][ro_ch]
    except (KeyError, IndexError, TypeError) as ex:
        raise RuntimeError(f"[ZeroSpanParity cfg] cannot read soccfg['readouts'][{ro_ch}]: {ex!r}")
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
        # Buffer sized by the declared read_length, not capture_length_us; nominal estimate.
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
        cap_us = float(cfg["capture_length_us"])
        floor = float(cfg["adc_trig_offset"]) + float(cfg["read_length"])
        if cap_us < floor:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 9] capture_length_us={cap_us} us "
                f"< adc_trig_offset + read_length = {floor:.3f} us. "
                f"Pulse ends before readout window closes. Increase "
                f"capture_length_us or shorten read_length."
            )

    # try/except: QickConfig has __getitem__ but no __contains__.
    qch = cfg["qubit_ch"]
    try:
        gen_info = soccfg["gens"][qch]
    except (KeyError, IndexError, TypeError):
        gen_info = None
    if gen_info is not None:
        try:
            f_dds = float(gen_info["f_dds"])
        except (KeyError, TypeError):
            f_dds = None
        if f_dds is not None:
            half = f_dds / 2.0
            f_drive = float(cfg["parity_drive_freq"])
            if not (-half <= f_drive <= half):
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 8] parity_drive_freq={f_drive} MHz "
                    f"outside qubit channel {qch} DDS range [-{half}, {half}] MHz."
                )


class _ZeroSpanParityProgBase(AveragerProgram):
    """Const readout tone + const parity-drive tone, then measure; subclasses set the
    const-pulse length via _const_length_us()."""

    def _const_length_us(self):
        """Return the const-pulse duration (us) for this acquisition path."""
        raise NotImplementedError

    def _setup_two_tones(self):
        cfg = self.cfg
        self.declare_gen(
            ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0]
        )
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"]),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        f_qub = self.freq2reg(cfg["parity_drive_freq"], gen_ch=cfg["qubit_ch"])
        return f_res, f_qub

    def initialize(self):
        cfg = self.cfg
        f_res, f_qub = self._setup_two_tones()
        length_us = self._const_length_us()
        length_cyc_q = self.us2cycles(length_us, gen_ch=cfg["qubit_ch"])
        length_cyc_r = self.us2cycles(length_us, gen_ch=cfg["res_ch"])

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="const",
            freq=f_qub,
            phase=0,
            gain=cfg["qubit_gain"],
            length=length_cyc_q,
        )
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=length_cyc_r,
        )
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


class ZeroSpanParityProgStrobe(_ZeroSpanParityProgBase):
    """Strobe path: tones held one sample_period per rep, reps back to back (near-CW
    drive); one integrated IQ point per rep."""

    def _const_length_us(self):
        return self.cfg["sample_period_us"]


class ZeroSpanParityProgDecimated(_ZeroSpanParityProgBase):
    """Decimated path: tones held for capture_length_us; the trace length is set by the
    declared readout window, not by capture_length_us."""

    def _const_length_us(self):
        return self.cfg["capture_length_us"]


class ZeroSpanParity(ExperimentClass):
    """Zero-span parity record; cfg["mode"] picks strobe or decimated. Own h5 schema
    (I, Q, t_us, gap_indices + scalar attrs), see docs/experiments/zero_span_parity.md."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )
        _validate_cfg(self.cfg, self.soccfg)
        mode = self.cfg["mode"]
        # AveragerProgram reads cfg["reps"] at construction, so set it first.
        if mode == "strobe":
            self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
            self.prog = ZeroSpanParityProgStrobe(self.soccfg, self.cfg)
        elif mode == "decimated":
            self.cfg["reps"] = 1
            self.prog = ZeroSpanParityProgDecimated(self.soccfg, self.cfg)
        else:
            raise ValueError(f"Unknown mode: {mode!r}")

    def set_qubit_gain(self, gain):
        """Set the drive gain and rebuild the strobe program (modulated_strobe_acquire)."""
        if self.cfg.get("mode", "strobe") != "strobe":
            raise RuntimeError("set_qubit_gain is strobe-mode only")
        self.cfg["qubit_gain"] = gain
        # A caller may have bumped reps_per_chunk since construction.
        if "reps_per_chunk" in self.cfg:
            self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
        self.prog = ZeroSpanParityProgStrobe(self.soccfg, self.cfg)

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
        prog = self.prog
        prog.acquire(
            self.soc,
            load_pulses=True,
            start_src=cfg["start_src"],
            progress=progress,
            readouts_per_experiment=1,
            save_experiments=None,
        )
        ro_ch = cfg["ro_chs"][0]
        # ro_ch=0 (not ro_chs[0]) to match the single-shot separator's units
        # (docs/architecture.md#readout-buffers).
        ro_cycles = float(self.soccfg.us2cycles(cfg["read_length"], ro_ch=0))
        if ro_cycles <= 0:
            ro_cycles = 1.0
        # di_buf is indexed by declaration order, not absolute channel.
        I = np.asarray(prog.di_buf[0], dtype=float).ravel() / ro_cycles
        Q = np.asarray(prog.dq_buf[0], dtype=float).ravel() / ro_cycles
        sp = float(cfg["sample_period_us"])
        t_us = np.arange(I.size, dtype=float) * sp
        data = {
            "I": I,
            "Q": Q,
            "t_us": t_us,
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
        # Nominal rate: on some firmware f_output is not the true decimated rate, so
        # t_us is reconstructable from the saved metadata (docs/experiments/zero_span_parity.md).
        decimated_fs_MHz = float(self.soccfg["readouts"][ro_ch]["f_output"])
        sp = 1.0 / decimated_fs_MHz

        n_captures = int(cfg.get("n_captures", 1))
        if n_captures < 1:
            raise RuntimeError(f"[ZeroSpanParity] n_captures={n_captures} must be >= 1")
        soft_avgs = int(cfg.get("soft_avgs", 1))
        if soft_avgs > 1:
            if not cfg.get("allow_soft_avgs", False):
                raise RuntimeError(
                    f"[ZeroSpanParity] soft_avgs={soft_avgs} > 1 averages "
                    f"across independent captures and destroys parity "
                    f"trajectories. Set cfg['allow_soft_avgs']=True if you "
                    f"really want a non-time-resolved averaged trace."
                )

        I_parts, Q_parts, t_parts = [], [], []
        capture_sizes = []
        chunk_wall_clocks = []
        gap_indices = []
        cum_offset_us = 0.0
        cum_idx = 0
        for ci in range(n_captures):
            chunk_wall_clocks.append(datetime.datetime.now().isoformat())
            # No soft_avgs kwarg: AveragerProgram injects it (keyword collision).
            dec = prog.acquire_decimated(
                self.soc,
                load_pulses=(ci == 0),
                start_src=cfg["start_src"],
                progress=progress,
            )
            # (2, length) for reps=1, (reps, 2, length) for reps>1, (length, 2) on some paths.
            arr = np.asarray(dec[0])
            if arr.ndim == 2 and arr.shape[0] == 2:
                I_c = arr[0]
                Q_c = arr[1]
            elif arr.ndim == 2 and arr.shape[1] == 2:
                I_c = arr[:, 0]
                Q_c = arr[:, 1]
            elif arr.ndim == 3:
                I_c = arr[:, 0, :].ravel()
                Q_c = arr[:, 1, :].ravel()
            else:
                raise RuntimeError(f"unexpected acquire_decimated shape: {arr.shape}")
            t_c = np.arange(I_c.size, dtype=float) * sp
            if ci > 0:
                cum_offset_us = float(t_parts[-1][-1]) + sp
                gap_indices.append(cum_idx)
            t_shifted = t_c + cum_offset_us
            I_parts.append(I_c)
            Q_parts.append(Q_c)
            t_parts.append(t_shifted)
            capture_sizes.append(int(I_c.size))
            cum_idx += I_c.size

        I = np.concatenate(I_parts)
        Q = np.concatenate(Q_parts)
        t_us = np.concatenate(t_parts)
        data = {
            "I": I,
            "Q": Q,
            "t_us": t_us,
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
            # The first capture's real length, not total / n_captures.
            "samples_per_capture": int(capture_sizes[0]) if capture_sizes else 0,
            "capture_sizes": np.asarray(capture_sizes, dtype=int),
            "soft_avgs": soft_avgs,
            "mode": "decimated",
        }
        self.data = {"data": data}
        return data

    def save_data(self, data=None):
        """Write IQ trace + metadata to self.fname (.h5)."""
        import h5py

        if data is None:
            data = (
                self.data["data"]
                if isinstance(self.data, dict) and "data" in self.data
                else self.data
            )
        # "a" keeps the save_config attr; delete-then-create makes re-saving idempotent.
        with h5py.File(self.fname, "a") as f:

            def _put(name, arr):
                if name in f:
                    del f[name]
                f.create_dataset(name, data=arr)

            _put("I", np.asarray(data["I"]))
            _put("Q", np.asarray(data["Q"]))
            _put("t_us", np.asarray(data["t_us"]))
            _put("gap_indices", np.asarray(data.get("gap_indices", []), dtype=int))
            if "capture_sizes" in data:
                _put("capture_sizes", np.asarray(data["capture_sizes"], dtype=int))
            if "chunk_wall_clock_starts" in data:
                wcs = [str(s) if s is not None else "" for s in data["chunk_wall_clock_starts"]]
                _put("chunk_wall_clock_starts", np.asarray(wcs, dtype=h5py.string_dtype("utf-8")))
            # Keep in sync with the acquire-path dicts; missing keys are skipped.
            scalar_keys = (
                "wall_clock_start",
                "sample_period_us",
                "mode",
                "decimated_fs_MHz",
                "decimated_fs_source",
                "read_length_us",
                "capture_length_us",
                "adc_trig_offset_us",
                "ro_norm_cycles",
                "samples_per_capture",
                "n_chunks",
                "n_captures",
                "soft_avgs",
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
