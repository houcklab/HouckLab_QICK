import datetime
import json
import os
import traceback

import h5py
import numpy as np

from qicklab.core.config import validate_gains


class H5File(h5py.File):
    """h5py.File that flushes on open and adds float64 datasets with `add`."""

    def __init__(self, *args, **kwargs):
        h5py.File.__init__(self, *args, **kwargs)
        self.flush()

    def add(self, key, data):
        """Write `data` as a resizable float64 dataset named `key`."""
        data = np.array(data)
        try:
            self.create_dataset(
                key,
                shape=data.shape,
                maxshape=tuple([None] * len(data.shape)),
                dtype=str(data.astype(np.float64).dtype),
            )
        except RuntimeError:
            del self[key]
            self.create_dataset(
                key,
                shape=data.shape,
                maxshape=tuple([None] * len(data.shape)),
                dtype=str(data.astype(np.float64).dtype),
            )
        self[key][...] = data


MakeFile = H5File


class NumpyJSONEncoder(json.JSONEncoder):
    """Ensure json dump can handle np arrays"""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
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
        self.fname = fname
        self.iname = iname
        self.titlename = titlename
        self.cname = cname

    def save_config(self):
        """Write self.cfg to the .json (cname) and to the h5 attribute `config` (fname)."""
        if self.cname[:-3] != ".h5":
            with open(self.cname, "w") as fid:
                (json.dump(self.cfg, fid, cls=NumpyJSONEncoder),)
            self.datafile().attrs["config"] = json.dumps(self.cfg, cls=NumpyJSONEncoder)

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
        """Write each item of `data` (default self.data) as a float64 dataset in fname."""
        if data is None:
            data = self.data

        with self.datafile() as f:
            for k, d in data.items():
                f.add(k, np.array(d))


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
