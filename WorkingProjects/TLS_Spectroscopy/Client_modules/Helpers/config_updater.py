import ast
import datetime
import json
import os
import re
import shutil

import numpy as np


def config_path():
    """Absolute path of the live initialize.py (import is side-effect-free)."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib import initialize
    p = initialize.__file__
    if p.endswith((".pyc", ".pyo")):
        p = p[:-1]
    return os.path.abspath(p)


def _baseconfig_node(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "BaseConfig":
                    if not isinstance(node.value, ast.Dict):
                        raise RuntimeError("BaseConfig is not a dict literal")
                    return node
    raise RuntimeError("BaseConfig assignment not found")


def read_baseconfig(path=None):
    """The literal-valued entries of BaseConfig (keys whose values are expressions,
    e.g. FF_CH, are skipped)."""
    path = path or config_path()
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    node = _baseconfig_node(tree)
    out = {}
    for k, v in zip(node.value.keys, node.value.values):
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            try:
                out[k.value] = ast.literal_eval(v)
            except (ValueError, TypeError):
                pass
    return out


def _fmt(v):
    if isinstance(v, (bool, np.bool_)):
        return repr(bool(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    f = float(v)
    s = ("%.4f" % f).rstrip("0").rstrip(".")
    return s if "." in s else s + ".0"


def update_baseconfig(updates, path=None, backup=True):
    """Update literal values inside BaseConfig.  updates: {key: new_value}.
    Returns {key: (old_string, new_string)}.  Raises (and writes NOTHING) if any key is
    missing, ambiguous, or if the post-edit file does not verify."""
    path = path or config_path()
    with open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    node = _baseconfig_node(tree)
    lo, hi = node.lineno, node.end_lineno
    lines = src.splitlines(keepends=True)

    changed = {}
    for key, val in updates.items():
        pat = re.compile(r'^(\s*"' + re.escape(key) + r'"\s*:\s*)([^,#\n]+?)(\s*,)')
        hits = [i for i in range(lo - 1, hi) if pat.match(lines[i])]
        if len(hits) != 1:
            raise RuntimeError("key %r matched %d lines in BaseConfig (expected exactly 1)"
                               % (key, len(hits)))
        i = hits[0]
        m = pat.match(lines[i])
        new_val = _fmt(val)
        lines[i] = pat.sub(lambda mm: mm.group(1) + new_val + mm.group(3), lines[i], count=1)
        changed[key] = (m.group(2).strip(), new_val)

    new_src = "".join(lines)
    new_vals = {}
    new_node = _baseconfig_node(ast.parse(new_src))
    for k, v in zip(new_node.value.keys, new_node.value.values):
        if isinstance(k, ast.Constant):
            try:
                new_vals[k.value] = ast.literal_eval(v)
            except (ValueError, TypeError):
                pass
    for key, val in updates.items():
        got = new_vals.get(key)
        want = ast.literal_eval(_fmt(val))
        ok = (got == want) if isinstance(want, int) else (
            got is not None and abs(float(got) - float(want)) < 1e-12)
        if not ok:
            raise RuntimeError("verification failed for %r: wrote %r, re-read %r"
                               % (key, _fmt(val), got))
        if not isinstance(want, int) and abs(float(want) - float(val)) > 1e-3:
            raise RuntimeError("value for %r changed by more than 1e-3 in formatting "
                               "(%r -> %r) -- refusing" % (key, val, _fmt(val)))

    if backup:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, path + ".bak_" + stamp)
    tmp = path + ".tmp_write"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new_src)
    os.replace(tmp, path)
    return changed



def history_path(path=None):
    return os.path.join(os.path.dirname(path or config_path()), "pi_calibration_history.json")


def append_history(record, path=None):
    """Append one run to the calibration history, ATOMICALLY.  Writing in place would
    destroy the entire history if the process died mid-write -- the same care
    update_baseconfig already takes for initialize.py."""
    hp = history_path(path)
    records = []
    if os.path.exists(hp):
        try:
            with open(hp, encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            try:
                os.replace(hp, hp + ".corrupt_" +
                           datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            except Exception:
                pass
            records = []
    if not isinstance(records, list):
        records = [records]
    records.append(record)
    tmp = hp + ".tmp_write"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)
    os.replace(tmp, hp)
    return hp


def prune_backups(path=None, keep=10):
    """Keep only the newest `keep` initialize.py backups; they otherwise accumulate
    without bound inside the package directory."""
    path = path or config_path()
    d = os.path.dirname(path)
    base = os.path.basename(path) + ".bak_"
    baks = sorted((f for f in os.listdir(d) if f.startswith(base)), reverse=True)
    for f in baks[int(keep):]:
        try:
            os.remove(os.path.join(d, f))
        except Exception:
            pass
    return len(baks)


def last_ramsey_sign(qubit=None, path=None):
    """The hardware-measured Ramsey sign convention from the most recent run that
    recorded one (+1/-1), else None.  Filtered by QUBIT when given: a sign measured on
    one qubit must not be silently inherited by another."""
    hp = history_path(path)
    if not os.path.exists(hp):
        return None
    try:
        with open(hp, encoding="utf-8") as f:
            records = json.load(f)
    except Exception:
        return None
    for rec in reversed(records if isinstance(records, list) else [records]):
        if qubit is not None and rec.get("qubit") not in (None, qubit):
            continue
        s = rec.get("ramsey_sign")
        if s in (1, -1):
            return int(s)
    return None
