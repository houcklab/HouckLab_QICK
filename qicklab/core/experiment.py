import datetime
import json
import os
import threading
import time
import traceback

import h5py
import numpy as np

from qicklab.core.config import validate_gains


def h5_array(key, data):
    """Convert one save_data payload to the array H5File.add writes; raise before any write.

    Numeric and bool data become float64 (the on-disk type of every existing record),
    complex data complex128, str data a str array (written as an h5py UTF-8 string
    dataset). None, object, bytes, datetime and other arrays raise TypeError naming `key`.
    See docs/architecture.md#h5-and-json-writing.
    """
    try:
        arr = np.asarray(data)
    except ValueError as exc:  # ragged nested lists
        raise TypeError(f"save_data: key {key!r} is not a rectangular array ({exc})") from exc
    kind = arr.dtype.kind
    if kind in "biuf":
        return arr.astype(np.float64)
    if kind == "c":
        return arr.astype(np.complex128)
    if kind == "U":
        return arr
    raise TypeError(
        f"save_data: key {key!r} has unsupported dtype {arr.dtype} "
        f"(value {data!r:.80}); store numbers, bools, complex numbers or strings"
    )


_REPLACE_RETRIES = 5  # os.replace attempts before the in-place fallback
_REPLACE_BACKOFF_S = 0.05  # seconds; the wait grows linearly with the attempt


def _write_text_replacing(path, text):
    """Write `text` to `path` through `<path>.tmp` + os.replace; never leave the .tmp behind.

    On Windows os.replace raises PermissionError while another process holds `path` open
    (a reader script, a viewer, an antivirus/indexer/sync client), although an in-place
    open(path, "w") still works. The replace is retried a few times; if it still fails,
    `text` (already fully serialised, so it cannot fail half-way) is written in place, as
    before F77. The .tmp is removed on every path, including when the write itself raises, unless another process holds it (that cleanup error is swallowed so a finished save never fails over it).
    See docs/architecture.md#h5-and-json-writing.
    """
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as fid:
            fid.write(text)
        for attempt in range(_REPLACE_RETRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt + 1 < _REPLACE_RETRIES:
                    time.sleep(_REPLACE_BACKOFF_S * (attempt + 1))
        with open(path, "w") as fid:  # target locked against replace: in-place write
            fid.write(text)
    finally:
        try:
            os.remove(tmp)
        except OSError:  # already replaced away; or held by a scanner: never fail the save
            pass


class H5File(h5py.File):
    """h5py.File that flushes on open and adds datasets with `add`."""

    def __init__(self, *args, **kwargs):
        h5py.File.__init__(self, *args, **kwargs)
        self.flush()

    def add(self, key, data):
        """Write `data` as a resizable dataset named `key`, replacing any existing one.

        Types follow h5_array (numeric/bool -> float64, complex -> complex128, str -> UTF-8
        string); an unsupported value raises TypeError before anything is written.
        """
        data = h5_array(key, data)
        if data.dtype.kind == "U":
            dtype, values = h5py.string_dtype(), data.astype(object)
        else:
            dtype, values = data.dtype, data
        if key in self:
            del self[key]
        self.create_dataset(
            key,
            shape=data.shape,
            maxshape=tuple([None] * len(data.shape)),
            dtype=dtype,
        )
        self[key][...] = values


MakeFile = H5File


class NumpyJSONEncoder(json.JSONEncoder):
    """json encoder for numpy values: arrays -> lists, np.bool_ -> bool, complex -> [re, im]."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, (complex, np.complexfloating)):
            return [float(obj.real), float(obj.imag)]
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyJSONEncoder, self).default(obj)


NpEncoder = NumpyJSONEncoder


def data_paths(outerFolder, path, prefix, now):
    """Return (fname, iname, cname, titlename) for a run started at datetime `now`.

    See docs/architecture.md#file-naming-must-stay-byte-identical.
    """
    datetimestring = now.strftime("%Y_%m_%d_%H_%M_%S")
    datestring = now.strftime("%Y_%m_%d")
    fname = os.path.join(
        outerFolder + path,
        path + "_" + datestring,
        path + "_" + datetimestring + "_" + prefix + ".h5",
    )
    iname = os.path.join(
        outerFolder + path,
        path + "_" + datestring,
        path + "_" + datetimestring + "_" + prefix + ".png",
    )
    titlename = path + "_" + datetimestring
    cname = os.path.join(
        outerFolder + path,
        path + "_" + datestring,
        path + "_" + datetimestring + "_" + prefix + ".json",
    )
    return fname, iname, cname, titlename


# Every (fname, iname, cname) handed out in this process, so two experiments built in the
# same second get distinct files even before either has written anything.
_CLAIMED_PATHS = set()
_CLAIMED_LOCK = threading.Lock()


def unique_data_paths(fname, iname, cname):
    """Return (fname, iname, cname) unchanged unless one is on disk or already claimed here.

    On a collision (same path, prefix and second) "_1", "_2", ... is appended to the stem of
    all three. See docs/architecture.md#file-naming-must-stay-byte-identical.
    """
    names = (fname, iname, cname)
    exts = (".h5", ".png", ".json")
    with _CLAIMED_LOCK:
        n = 0
        cand = names
        while any(
            os.path.normcase(os.path.abspath(p)) in _CLAIMED_PATHS or os.path.exists(p)
            for p in cand
        ):
            n += 1
            cand = tuple(p[: -len(e)] + f"_{n}" + e for p, e in zip(names, exts))
        _CLAIMED_PATHS.update(os.path.normcase(os.path.abspath(p)) for p in cand)
    return cand


class ExperimentClass:
    """Base class for all experiments"""

    # (start, step, expts) cfg keys when the program's register sweep is over the drive gain
    gain_sweep_keys = None

    def __init__(
        self,
        path="",
        outerFolder="",
        prefix="data",
        soc=None,
        soccfg=None,
        cfg=None,
        config_file=None,
        liveplot_enabled=False,
        **kwargs,
    ):
        """Store cfg/soc/soccfg, create the dated data folder, set fname/iname/cname/titlename.

        `path` is both the sub-folder name and the file stem; kwargs go into __dict__ first.
        Raises ValueError, before any folder is made, if a drive gain in `cfg` is out of range
        (docs/concepts/timing_and_units.md#gains).
        """
        validate_gains(cfg, self.gain_sweep_keys, where=f"{type(self).__name__} cfg")

        self.__dict__.update(kwargs)
        self.path = path
        self.outerFolder = outerFolder
        datetimenow = datetime.datetime.now()
        self.prefix = prefix
        self.cfg = cfg
        self.soc = soc
        self.soccfg = soccfg
        if config_file is not None:
            self.config_file = os.path.join(path, config_file)
        else:
            self.config_file = None

        datestring = datetimenow.strftime("%Y_%m_%d")
        os.makedirs(
            os.path.join(self.outerFolder + self.path, self.path + "_" + datestring), exist_ok=True
        )

        fname, iname, cname, titlename = data_paths(
            self.outerFolder, self.path, self.prefix, datetimenow
        )
        fname, iname, cname = unique_data_paths(fname, iname, cname)
        self.fname = fname
        self.iname = iname
        self.titlename = titlename
        self.cname = cname

    def save_config(self):
        """Write self.cfg to the .json (cname) and to the h5 attribute `config` (fname).

        The cfg is serialised first, so an unencodable value raises before any file is
        touched, and the .json is written to a temp file that replaces cname in one step.
        """
        text = json.dumps(self.cfg, cls=NumpyJSONEncoder)
        _write_text_replacing(self.cname, text)
        self.datafile().attrs["config"] = text

    def datafile(self, group=None, remote=False, data_file=None, swmr=False):
        """Open self.fname (or `data_file`) as an H5File in append mode."""
        if data_file == None:
            data_file = self.fname

        f = H5File(data_file, "a")
        return f

    def acquire(self, progress=False, debug=False):
        pass

    def analyze(self, data=None, **kwargs):
        pass

    def display(self, data=None, **kwargs):
        pass

    def save_data(self, data=None):
        """Write each item of `data` (default self.data) as a dataset in fname (see h5_array).

        Every value is converted before the file is opened, so one bad key raises TypeError
        and nothing is written; re-saving a key replaces it.
        """
        if data is None:
            data = self.data

        arrays = {k: h5_array(k, d) for k, d in data.items()}
        with self.datafile() as f:
            for k, d in arrays.items():
                f.add(k, d)


def finish(cls, inst, data, *, reraise=False, **display_kw):
    """Display, then always save: ``cls.display(inst, data, **display_kw)``, ``save_data``, ``save_config``.

    A display that raises (a fit on noise-only data) or is interrupted (Ctrl-C on a blocking
    plot window) no longer loses the record: the traceback is printed, ``repr(exc)`` is stored
    on ``inst.display_error`` and the h5 + json are still written. Display stays first because
    some displays write fit fields into ``data``; save_config stays last because some save_data
    overrides rename ``inst.fname``. ``reraise=True`` re-raises the display error after saving
    (single runs); the default lets repetition loops continue. ``cls`` is explicit so a call
    site naming a parent class keeps calling that class's methods. Returns the display
    exception, or None. See docs/architecture.md#display-never-loses-the-record.
    """
    error = None
    try:
        cls.display(inst, data, **display_kw)
    except Exception as exc:
        traceback.print_exc()
        inst.display_error = repr(exc)
        error = exc
    finally:
        cls.save_data(inst, data)
        cls.save_config(inst)
    if reraise and error is not None:
        raise error
    return error
