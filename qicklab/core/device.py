"""One chip in one cooldown as frozen dataclasses: the numbers every session starts from.

Fields, units and the edit/archive workflow: docs/adding_a_device.md. A device file
(`devices/<NAME>.py`) builds one `Device`; `Device.legacy_parameters()` is the old
`Qubit_Parameters` dict that `build_context` and AutoCoherence consume.

Frozen means attribute assignment raises and the dict fields (`Device.qubits`,
`Setup.board_overrides`, `Setup.ff_qubits`) are stored as read-only copies; values nested
inside those (an `ff_qubits` entry, a list in `board_overrides`) are not frozen.
"""

import copy
import dataclasses
import math
import numbers
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field

from qicklab.core.config import GAIN_MAX
from qicklab.hardware.board import base_config


class _ReadOnlyMap(Mapping):
    """Read-only copy of a dict; ==, repr, copy, deepcopy and pickle behave like the dict's."""

    __slots__ = ("_data",)

    def __init__(self, data=()):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return repr(self._data)

    def __reduce__(self):
        return (type(self), (self._data,))


def _freeze(obj, *names):
    """Store each named Mapping field of a frozen dataclass as a `_ReadOnlyMap` copy."""
    for name in names:
        value = getattr(obj, name)
        if isinstance(value, Mapping):
            object.__setattr__(obj, name, _ReadOnlyMap(value))


@dataclass(frozen=True)
class ReadoutWindow:
    """ADC integration window and tone-start-to-trigger delay [us]; tone length = sum of both."""

    length_us: float
    adc_offset_us: float


@dataclass(frozen=True)
class Readout:
    """Readout resonator of one qubit; a window left at None uses the Device default."""

    freq: float  # MHz
    gain: int  # DAC units
    window: ReadoutWindow | None = None  # regime A (measurement) window override
    ss_window: ReadoutWindow | None = None  # regime B (single-shot) window override
    kappa_mhz: float | None = None  # kappa/2pi; sets the active-reset readout delay (~6/kappa)


@dataclass(frozen=True)
class ParityParams:
    """Charge-parity calibration of a charge-sensitive qubit (docs/adding_a_device.md#parityparams)."""

    df_mhz: float  # parity branch splitting
    f_upper_mhz: float  # UPPER branch, not the doublet centre
    cd_max_mhz: float | None = (
        None  # peak charge dispersion of S(V) = cd_max |cos(2 pi (V - V0) / T)|
    )
    cd_period_mv: float | None = None  # T of that fit, mV of yoko voltage
    p_e_state0: float = 0.1  # Ramsey mapping P(e | parity state 0)
    p_e_state1: float = 0.9  # Ramsey mapping P(e | parity state 1)
    calibrated: bool = False  # True once the mapping comes from a device calibration


@dataclass(frozen=True)
class Qubit:
    """Drive parameters of one qubit plus its readout; pi2_gain None means gain // 2."""

    freq: float  # MHz
    gain: int  # pi-pulse gain, DAC units
    sigma: float  # us, Gaussian sigma (envelope 4 sigma)
    readout: Readout
    pi2_gain: int | None = None
    flattop_length: float | None = None  # us; None = plain Gaussian
    spec_gain: int | None = None  # spectroscopy drive gain; None = the spec group's
    bias_v: float | None = None  # preferred charge-line bias
    t1_us: float | None = None  # last measured T1
    parity: ParityParams | None = None
    notes: str = ""

    @property
    def effective_pi2_gain(self):
        """pi/2 gain actually played: `pi2_gain`, or `gain // 2` when it is None."""
        return self.gain // 2 if self.pi2_gain is None else self.pi2_gain


@dataclass(frozen=True)
class TwpaSetup:
    """TWPA instruments shared by the qicklab.twpa scripts."""

    yoko_addr: str  # current-mode bias yoko
    synth_port: str  # SynthHD pump serial port
    pnax_addr: str
    pump: tuple  # (freq_GHz, power_dBm, synth channel)
    bias_ua: float


@dataclass(frozen=True)
class Setup:
    """Instrument endpoints and board-cfg overrides (merged over BASE_CONFIG)."""

    rfsoc_host: str = "192.168.0.103"
    rfsoc_port: int = 8888
    rfsoc_name: str = "myqick"
    yoko_addr: str = "GPIB1::9::INSTR"  # charge-line yoko, voltage mode
    board_overrides: dict = field(default_factory=dict, hash=False)
    ff_qubits: dict | None = field(default=None, hash=False)  # None = hardware.board.FF_QUBITS
    twpa: TwpaSetup | None = None

    def __post_init__(self):
        _freeze(self, "board_overrides", "ff_qubits")

    def board_config(self):
        """Fresh BASE_CONFIG copy with (deep copies of) `board_overrides` applied."""
        return base_config() | copy.deepcopy(dict(self.board_overrides))


@dataclass(frozen=True)
class Device:
    """One chip in one cooldown. `qubits` is read-only; `with_qubit` makes trial copies."""

    name: str
    cooldown: str
    data_root: str
    qubits: dict = field(hash=False)  # {1: Qubit, ..., N: Qubit}, stored read-only
    setup: Setup
    cavity_min: bool = True  # resonator is a dip in transmission
    readout_window: ReadoutWindow = ReadoutWindow(15, 0.3)  # regime A default
    ss_window: ReadoutWindow = ReadoutWindow(15, 0.3)  # regime B default

    def __post_init__(self):
        _freeze(self, "qubits")

    def folder(self, q):
        """Data folder of qubit q, byte-identical to the legacy `QubitFolders[str(q)]`."""
        return f"{self.data_root}/Q{q}//"

    def window(self, q, *, single_shot=False):
        """Readout window of qubit q in regime A (default) or B, per-qubit override first."""
        r = self.qubits[q].readout
        if single_shot:
            return r.ss_window or self.ss_window
        return r.window or self.readout_window

    def legacy_parameters(self):
        """A fresh dict in the old `Qubit_Parameters` shape (str keys, legacy key order)."""
        return {
            str(q): {
                "Readout": {"Frequency": qb.readout.freq, "Gain": qb.readout.gain},
                "Qubit": {
                    "Frequency": qb.freq,
                    "Gain": qb.gain,
                    "pi2_Gain": qb.effective_pi2_gain,
                    "sigma": qb.sigma,
                    "flattop_length": qb.flattop_length,
                },
                "outerfoldername": self.folder(q),
            }
            for q, qb in sorted(self.qubits.items())
        }

    def with_qubit(self, q, **changes):
        """New Device with qubit q's fields replaced (dataclasses.replace); self is untouched."""
        if q not in self.qubits:
            raise KeyError(f"{self.name} has no qubit {q!r}; qubits are {sorted(self.qubits)}")
        qubits = dict(self.qubits)
        qubits[q] = dataclasses.replace(self.qubits[q], **changes)
        return dataclasses.replace(self, qubits=qubits)

    def validate(self, soccfg=None, *, image_tol_mhz=20.0, coincide_tol_mhz=2.0):
        """Raise ValueError listing every hard error; warn on soft problems; return the zone report.

        Checks: docs/adding_a_device.md#3-validate. The Nyquist-zone/image part needs `soccfg`
        (gen `fs`) and is skipped with a warning without one.
        """
        errors, warns = _check_fields(self)
        report = []
        if errors:
            raise ValueError(f"{self.name}: invalid device\n  " + "\n  ".join(errors))
        if soccfg is None:
            warns.append("Nyquist-zone and image check skipped: no soccfg given")
        else:
            zone_errors, zone_warns, report = _check_zones(
                self, soccfg, image_tol_mhz, coincide_tol_mhz
            )
            warns += zone_warns
            if zone_errors:
                raise ValueError(f"{self.name}: invalid device\n  " + "\n  ".join(zone_errors))
        for w in warns:
            warnings.warn(f"{self.name}: {w}", stacklevel=2)
        return report


def source(obj):
    """Python source of a device value: dataclasses by keyword, fields at their default left out.

    `source(device.qubits[5])` is a paste-ready `Qubit(...)` for devices/<NAME>.py; numpy
    scalars print as plain numbers.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        parts = []
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            if f.default is not dataclasses.MISSING and _same(value, f.default):
                continue
            if f.default_factory is not dataclasses.MISSING and _same(value, f.default_factory()):
                continue
            parts.append(f"{f.name}={source(value)}")
        return f"{type(obj).__name__}({', '.join(parts)})"
    if isinstance(obj, Mapping):
        return "{" + ", ".join(f"{source(k)}: {source(v)}" for k, v in obj.items()) + "}"
    if isinstance(obj, list):
        return "[" + ", ".join(source(v) for v in obj) + "]"
    if isinstance(obj, tuple):
        return "(" + ", ".join(source(v) for v in obj) + ("," if len(obj) == 1 else "") + ")"
    if hasattr(obj, "item") and callable(obj.item) and getattr(obj, "shape", None) == ():
        obj = obj.item()  # numpy scalar
    return repr(obj)


def _same(a, b):
    try:
        return bool(a == b) and type(a) is type(b)
    except Exception:
        return False


def _is_number(v):
    return isinstance(v, numbers.Real) and not isinstance(v, bool) and math.isfinite(v)


def _check_fields(dev):
    """Hard errors and warnings that need no board description."""
    errors, warns = [], []
    if not isinstance(dev.qubits, Mapping) or not dev.qubits:
        return ["qubits must be a non-empty dict {1: Qubit, ...}"], warns
    keys = list(dev.qubits)
    if any(isinstance(k, bool) or not isinstance(k, int) for k in keys) or sorted(keys) != list(
        range(1, len(keys) + 1)
    ):
        errors.append(f"qubit keys must be the ints 1..N, got {keys}")
    for win_name, win in (("readout_window", dev.readout_window), ("ss_window", dev.ss_window)):
        errors += _check_window(win_name, win)
    board = dev.setup.board_config()
    unknown = sorted(set(dev.setup.board_overrides) - set(base_config()))
    if unknown:
        errors.append(f"setup.board_overrides has keys not in BASE_CONFIG: {unknown}")
    for key in ("nqz", "qubit_nqz"):
        if board[key] not in (1, 2):
            errors.append(f"board {key} must be 1 or 2, got {board[key]!r}")

    for q, qb in dev.qubits.items():
        where = f"Q{q}"
        if not isinstance(qb, Qubit) or not isinstance(qb.readout, Readout):
            errors.append(f"{where}: must be Qubit(..., readout=Readout(...))")
            continue
        for label, v in (("freq", qb.freq), ("readout.freq", qb.readout.freq)):
            if not _is_number(v) or v <= 0:
                errors.append(f"{where}.{label} must be a positive frequency [MHz], got {v!r}")
        if not _is_number(qb.sigma) or qb.sigma <= 0:
            errors.append(f"{where}.sigma must be > 0 us, got {qb.sigma!r}")
        if qb.flattop_length is not None and (
            not _is_number(qb.flattop_length) or qb.flattop_length < 0
        ):
            errors.append(f"{where}.flattop_length must be None or >= 0 us")
        gains = [
            ("gain", qb.gain),
            ("pi2_gain", qb.effective_pi2_gain),
            ("readout.gain", qb.readout.gain),
        ]
        if qb.spec_gain is not None:
            gains.append(("spec_gain", qb.spec_gain))
        bad_gain = False
        for label, v in gains:
            if not _is_number(v) or not isinstance(v, numbers.Integral) or not 0 <= v <= GAIN_MAX:
                errors.append(
                    f"{where}.{label} must be an integer within 0..{GAIN_MAX} [DAC units], got {v!r}"
                )
                bad_gain = True
        if not bad_gain:
            pi2 = qb.effective_pi2_gain
            if pi2 > qb.gain:
                errors.append(f"{where}: pi2_gain {pi2} exceeds the pi gain {qb.gain}")
            elif qb.pi2_gain is not None and qb.flattop_length is None and qb.gain > 0:
                ratio = pi2 / qb.gain
                if abs(ratio - 0.5) > 0.1:
                    warns.append(
                        f"{where}: pi2_gain/gain = {ratio:.3f} (Gaussian pulses expect ~0.5); "
                        f"re-derive it unless it was calibrated"
                    )
        for win_name, win in (
            ("readout.window", qb.readout.window),
            ("readout.ss_window", qb.readout.ss_window),
        ):
            if win is not None:
                errors += _check_window(f"{where}.{win_name}", win)
        if qb.readout.kappa_mhz is not None and (
            not _is_number(qb.readout.kappa_mhz) or qb.readout.kappa_mhz <= 0
        ):
            errors.append(f"{where}.readout.kappa_mhz must be None or > 0")
        p = qb.parity
        if p is not None:
            if not isinstance(p, ParityParams):
                errors.append(f"{where}.parity must be ParityParams or None")
                continue
            if not _is_number(p.df_mhz) or p.df_mhz <= 0:
                errors.append(f"{where}.parity.df_mhz must be > 0, got {p.df_mhz!r}")
            if not _is_number(p.f_upper_mhz) or p.f_upper_mhz <= 0:
                errors.append(f"{where}.parity.f_upper_mhz must be > 0, got {p.f_upper_mhz!r}")
            for label, v in (("p_e_state0", p.p_e_state0), ("p_e_state1", p.p_e_state1)):
                if not _is_number(v) or not 0 <= v <= 1:
                    errors.append(f"{where}.parity.{label} must be a probability, got {v!r}")
            if _is_number(p.f_upper_mhz) and _is_number(p.df_mhz) and _is_number(qb.freq):
                tol = max(p.df_mhz, p.cd_max_mhz or 0.0) + 1.0
                if abs(p.f_upper_mhz - qb.freq) > tol:
                    warns.append(
                        f"{where}: parity.f_upper_mhz {p.f_upper_mhz} is "
                        f"{abs(p.f_upper_mhz - qb.freq):.3f} MHz from freq {qb.freq} "
                        f"(> {tol:.3f} MHz): wrong qubit or stale value?"
                    )
    return errors, warns


def _check_window(where, win):
    if not isinstance(win, ReadoutWindow):
        return [f"{where} must be a ReadoutWindow"]
    errors = []
    if not _is_number(win.length_us) or win.length_us <= 0:
        errors.append(f"{where}.length_us must be > 0, got {win.length_us!r}")
    if not _is_number(win.adc_offset_us) or win.adc_offset_us < 0:
        errors.append(f"{where}.adc_offset_us must be >= 0, got {win.adc_offset_us!r}")
    return errors


def _images(f, fs):
    """DAC images k*fs +/- (f mod fs) in (0, 2 fs), excluding f itself."""
    base = f % fs
    out = set()
    for k in range(3):
        for img in (k * fs + base, k * fs - base):
            if 0 < img < 2 * fs and abs(img - f) > 1e-6:
                out.add(round(img, 6))
    return sorted(out)


def _check_zones(dev, soccfg, image_tol_mhz, coincide_tol_mhz):
    """Nyquist zone of every tone vs its declared nqz, coincident images, image collisions."""
    board = dev.setup.board_config()
    tones = []  # (label, freq, gen ch, nqz)
    for q, qb in sorted(dev.qubits.items()):
        tones.append((f"Q{q} readout", qb.readout.freq, board["res_ch"], board["nqz"]))
        tones.append((f"Q{q} qubit", qb.freq, board["qubit_ch"], board["qubit_nqz"]))
    errors, warns, report = [], [], []
    for label, f, ch, nqz in tones:
        fs = float(soccfg["gens"][ch]["fs"])
        half = fs / 2
        zone = int(f // half) + 1
        images = _images(f, fs)
        nearest = min(images, key=lambda img: abs(img - f)) if images else None
        report.append(
            f"{label} {f} MHz: gen {ch} fs {fs} MHz, zone {zone}, nqz {nqz}, nearest image {nearest} MHz"
        )
        if f >= 2 * fs:
            errors.append(f"{label} {f} MHz is above 2 fs = {2 * fs} MHz (gen {ch})")
            continue
        edge = min(f % half, half - f % half)
        if edge < coincide_tol_mhz:
            errors.append(
                f"{label} {f} MHz lies {edge:.3f} MHz from a multiple of fs/2 = {half} MHz: "
                f"tone and image coincide"
            )
        if nqz == 1 and zone >= 2:
            warns.append(
                f"{label} {f} MHz is in Nyquist zone {zone} with nqz 1; the DAC's first-zone "
                f"image at {round(fs - f % fs if zone in (2, 4) else f % fs, 6)} MHz is stronger"
            )
        elif nqz == 2 and zone not in (2, 3):
            warns.append(f"{label} {f} MHz is in Nyquist zone {zone} with nqz 2 (mix mode: 2-3)")
        for other_label, other_f, _, _ in tones:
            if other_label == label:
                continue
            for img in images:
                if abs(img - other_f) <= image_tol_mhz:
                    warns.append(
                        f"{label} {f} MHz has an image at {img} MHz, "
                        f"{abs(img - other_f):.3f} MHz from {other_label} {other_f} MHz"
                    )
    return errors, warns, report
