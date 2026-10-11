import os
import json
import datetime

import h5py
import numpy as np


class ExperimentClass:
    """Base class for all experiments.

    One run writes three files sharing a timestamped stem: <stem>.h5 (/data group,
    config and searchable metadata as root attrs), <stem>.json (config) and <stem>.png.
    Experiments build self.data = {'config': cfg, 'data': {...}}; save_data mirrors it.
    """

    def __init__(self, path=None, outerFolder=None, suffix='data', soc=None, soccfg=None, cfg=None):
        # Default path: "{outerFolder}\\{path}\\{path}_{YYYY_MM_DD}\\{path}_{YYYY_MM_DD}_{HH_MM_SS}_{suffix}.{h5|png|json}"

        self.outerFolder = outerFolder or cfg['outerFolder']  # i.e. "Z:\\QSimMeasurements\\Measurements\\8QV1_Q0V\\"
        self.path = path or type(self).__name__               # i.e. "SpecSliceFF"
        self.suffix = suffix                                  # i.e. "data"

        now = datetime.datetime.now()
        self.start_time = now.isoformat(timespec='seconds')
        self.day = f"{now:%Y_%m_%d}"
        self.day_folder = f"{self.path}_{self.day}"
        absolute_folder = os.path.join(self.outerFolder + self.path, self.day_folder)
        file_stem = f"{self.path}_{now:%Y_%m_%d_%H_%M_%S}_{self.suffix}"
        self.titlename = file_stem
        absolute_stem = os.path.join(absolute_folder, file_stem)

        os.makedirs(absolute_folder, exist_ok=True)
        self.fname, self.iname, self.cname = absolute_stem + '.h5', absolute_stem + '.png', absolute_stem + '.json'

        self.soc = soc
        self.soccfg = soccfg
        if isinstance(cfg, str):
            self.cfg = json.load(open(cfg))
        elif isinstance(cfg, dict):
            self.cfg = cfg
        else:
            raise TypeError("cfg must be a Python dict or str (json file name)")

    # Hooks for subclasses
    def acquire(self, progress=False, debug=False):
        pass

    def analyze(self, data=None, **kwargs):
        pass

    def display(self, data=None, **kwargs):
        pass

    # Saving
    def datafile(self):
        return h5py.File(self.fname, 'a')

    def save_config(self):
        with open(self.cname, 'w') as fid:
            json.dump(self.cfg, fid, cls=NpEncoder)
        with self.datafile() as f:
            f.attrs['config'] = json.dumps(self.cfg, cls=NpEncoder)

    def save_data(self, data=None):
        """'config' -> root attr, 'data' -> /data group; other keys go at the root."""
        data = self.data if data is None else data
        with self.datafile() as f:
            for key, value in data.items():
                if key == 'config':
                    f.attrs['config'] = json.dumps(value, cls=NpEncoder)
                elif isinstance(value, dict):
                    _write_group(f.require_group(key), value)
                else:
                    _write_group(f, {key: value})
        print(f'Saved {self.fname}.')
        self.save_metadata(data)

    def save_metadata(self, data=None):
        """Searchable root attrs; overrides come from cfg['meta']."""
        cfg = self.cfg or {}
        data = data or {}
        inner = data.get('data', data)
        meta_cfg = cfg.get('meta') or {}
        readout = next((inner[k] for k in ('Qubit_Readout_List', 'Qubit_Readout') if k in inner), None)
        if readout is None:
            readout = cfg.get('Qubit_Readout_List', [])
            print(f"[save_metadata] {type(self).__name__} did not save 'Qubit_Readout_List' in its "
                  f"data dict; using cfg value {readout}")
        meta = {
            'Experiment': type(self).__name__,
            'Qubit_Readout': readout,
            'qubits': meta_cfg.get('qubits', readout),
            'start_time': self.start_time,
            'finish_time': datetime.datetime.now().isoformat(timespec='seconds'),
            'group_name': meta_cfg.get('group_name', self.day),
            'name': meta_cfg.get('name', ''),
        }
        with self.datafile() as f:
            for key, value in meta.items():
                try:
                    if isinstance(value, (list, tuple, np.ndarray)):
                        value = np.asarray(value)
                    if isinstance(value, np.ndarray) and value.dtype.kind in 'US':
                        f.attrs.create(key, value.astype(object), dtype=h5py.string_dtype())
                    else:
                        f.attrs[key] = value
                except Exception as e:
                    print(f"[save_metadata] failed key {key!r}: {e}")

    # Loading
    @staticmethod
    def load_metadata(path):
        """Root attrs except the config blob; cheap enough to scan a directory."""
        with open_for_reading(path) as f:
            return {k: f.attrs[k] for k in f.attrs if k != 'config'}

    @staticmethod
    def load_data(path, keys=None):
        """Read a run as {'config', 'data', 'metadata'}; old files keep datasets at the root."""
        with open_for_reading(path) as f:
            group = f['data'] if isinstance(f.get('data'), h5py.Group) else f
            names = [k for k in group if isinstance(group[k], h5py.Dataset) and (keys is None or k in keys)]
            config = f.attrs.get('config')
            return {'config': json.loads(config) if config is not None else {},
                    'data': {k: group[k][()] for k in names},
                    'metadata': {k: f.attrs[k] for k in f.attrs if k != 'config'}}

    # Run-and-save combinations
    def acquire_save(self, **kwargs):
        data = self.acquire(**kwargs)
        self.save_data(data)
        return data

    def acquire_save_display(self, **kwargs):
        data = self.acquire()
        self.save_data(data)
        self.save_config()
        self.display(data, **kwargs)
        return data

    def acquire_display_save(self, **kwargs):
        data = self.acquire()
        self.display(data, **kwargs)
        self.save_data(data)
        self.save_config()
        return data

    def acquire_display(self, **kwargs):
        """Use if acquire() already calls save_data()."""
        data = self.acquire()
        self.display(data, **kwargs)
        self.save_config()
        return data


def _write_group(group, mapping):
    """Write mapping into group, recursing into dicts; a key that fails is skipped with a message."""
    for key, value in mapping.items():
        try:
            if isinstance(value, dict):
                _write_group(group.require_group(key), value)
            else:
                _write_dataset(group, key, value)
        except Exception as e:
            print(f"[save_data] failed key {key!r}: {e}")


def _write_dataset(group, key, value):
    """Write value to group[key] (replacing it), keeping numeric dtypes and storing strings as vlen."""
    value = np.asarray(value)
    if value.dtype.kind in 'iufcb':
        dtype = value.dtype
    elif value.dtype.kind in 'USO':
        dtype = h5py.string_dtype()
        value = value.astype(object)
    else:
        raise TypeError(f"{key!r}: unsupported dtype {value.dtype}")
    if key in group:
        del group[key]
    group.create_dataset(key, data=value, dtype=dtype)

class NpEncoder(json.JSONEncoder):
    """Let json.dump handle numpy scalars and arrays."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


'''USED BY THE VIEWER GUI'''

class FileBeingSaved(OSError):
    """The h5 is locked by another process, i.e. an experiment is saving it right now."""


def open_for_reading(path):
    """Open an h5 read-only without ever blocking a concurrent save (use as a context manager).

    No HDF5 lock is taken; if the OS refuses the open because a save is in progress,
    FileBeingSaved is raised so callers can retry instead of reading a half-written file."""
    try:
        return h5py.File(path, 'r', locking=False)
    except OSError as e:
        try:
            with open(path, 'rb') as fh:
                fh.read(8)
        except PermissionError:
            raise FileBeingSaved(f"{path} is locked (being saved?) -- try again shortly") from e
        raise


