"""
Base experiment class for the TLS_Spectroscopy project.

Self-contained (no GUI/Quarky coupling).  Mirrors the lab's ExperimentClass on
both the QICK side (dated HDF5 + JSON + PNG folders, MakeFile/NpEncoder) and the
QUA side (a .pkl of the whole ``self.data`` dict via ``pickle_data``), so ported
QUA experiments that expect ``self.pname`` / ``pickle_data()`` work unchanged.

Directory / file naming (per experiment instance):
    <outerFolder>/<path>/<path>_<YYYY_MM_DD>/<path>_<HH_MM_SS>_<suffix>.{h5,json,png,pkl}
"""

import os
import json
import pickle
import datetime
from pathlib import Path

import numpy as np
import h5py


class MakeFile(h5py.File):
    """h5py.File whose ``add`` creates resizable float datasets (overwriting)."""

    def __init__(self, *args, **kwargs):
        h5py.File.__init__(self, *args, **kwargs)
        self.flush()

    def add(self, key, data):
        data = np.array(data)
        try:
            self.create_dataset(key, shape=data.shape,
                                maxshape=tuple([None] * len(data.shape)),
                                dtype=str(data.astype(np.float64).dtype))
        except (RuntimeError, ValueError):
            if key in self:
                del self[key]
            self.create_dataset(key, shape=data.shape,
                                maxshape=tuple([None] * len(data.shape)),
                                dtype=str(data.astype(np.float64).dtype))
        self[key][...] = data


class NpEncoder(json.JSONEncoder):
    """Let json.dump handle numpy scalars/arrays (used for config + meta_dict)."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return super(NpEncoder, self).default(obj)


class ExperimentClass:
    """Base class for all TLS_Spectroscopy experiments.

    Parameters
    ----------
    path : str
        sub-directory name under ``outerFolder`` (also used in file names).
    outerFolder : str
        absolute root directory for saved data.
    prefix / suffix : str
        file-name suffix (both accepted; ``suffix`` wins if given).
    cfg : dict
        the merged experiment config (BaseConfig | UpdateConfig).
    soc, soccfg :
        the Pyro4 proxy and local QickConfig from ``socProxy.makeProxy``.
    meta_dict : dict, optional
        extra run metadata saved alongside the data (parity with the QUA repo).
    short_directory_names : bool
        if True, use ``<date>/`` sub-folders instead of ``<path>_<date>/``.
    """

    def __init__(self, path='', outerFolder='', prefix='data', suffix=None,
                 soc=None, soccfg=None, cfg=None, config=None, meta_dict=None,
                 short_directory_names=False, **kwargs):
        self.__dict__.update(kwargs)
        self.path = path
        self.outerFolder = outerFolder
        # accept both cfg (QICK) and config (QUA) spellings
        self.cfg = cfg if cfg is not None else config
        self.soc = soc
        self.soccfg = soccfg
        self.meta_dict = meta_dict
        self.suffix = str(suffix if suffix is not None else prefix)

        now = datetime.datetime.now()
        time_string = now.strftime('%H_%M_%S')
        date_string = now.strftime('%Y_%m_%d')
        self.date_string = date_string
        self.time_string = time_string

        base = Path(self.outerFolder) / self.path
        subdir = date_string if short_directory_names else (self.path + "_" + date_string)
        data_dir = base / subdir
        data_dir.mkdir(parents=True, exist_ok=True)

        stem = (time_string if short_directory_names else self.path + "_" + time_string)
        stem = stem + "_" + self.suffix
        self.dname = str(data_dir / stem)
        self.fname = self.dname + '.h5'
        self.iname = self.dname + '.png'
        self.cname = self.dname + '.json'
        self.pname = self.dname + '.pkl'

    # ---- lifecycle hooks (overridden by subclasses) ----
    def go(self, save=False, analyze=False, display=False, progress=False):
        data = self.acquire(progress)
        if analyze:
            data = self.analyze(data)
        if save:
            self.save_data(data)
        if display:
            self.display(data)
        return data

    def acquire(self, progress=False, debug=False):
        pass

    def analyze(self, data=None, **kwargs):
        pass

    def display(self, data=None, **kwargs):
        pass

    # ---- IO ----
    def datafile(self, data_file=None):
        return MakeFile(self.fname if data_file is None else data_file, 'a')

    def save_config(self):
        """Write the config dict as JSON and mirror it into the h5 attrs."""
        if not self.cname.endswith('.h5'):
            with open(self.cname, 'w') as fid:
                json.dump(self.cfg, fid, cls=NpEncoder)
            with self.datafile() as f:
                f.attrs['config'] = json.dumps(self.cfg, cls=NpEncoder)
                if self.meta_dict is not None:
                    f.attrs['meta_dict'] = json.dumps(self.meta_dict, cls=NpEncoder)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        with self.datafile() as f:
            for k, d in data.items():
                try:
                    f.add(k, np.array(d))
                except (TypeError, ValueError):
                    # non-array entries (e.g. nested dicts) are stored as JSON attrs
                    f.attrs[k] = json.dumps(d, cls=NpEncoder)

    def load_data(self, f):
        data = {}
        for k in f.keys():
            data[k] = np.array(f[k])
        return data

    def pickle_data(self, data=None):
        with open(self.pname, 'wb') as f:
            pickle.dump(self.data if data is None else data, f)
