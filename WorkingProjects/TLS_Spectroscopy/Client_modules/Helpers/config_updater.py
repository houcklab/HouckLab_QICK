import ast
import datetime
import hashlib
import json
import os
import re
import shutil

import numpy as np


OVERRIDE_BASENAME = "local_overrides.py"
OVERRIDE_DICT = "OVERRIDES"
_SKELETON = "OVERRIDES = {\n}\n\nouterFolder = None\n"


def _initialize_dir():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib import initialize
    p = initialize.__file__
    if p.endswith((".pyc", ".pyo")):
        p = p[:-1]
    return os.path.dirname(os.path.abspath(p))


def config_path():
    return os.path.join(_initialize_dir(), OVERRIDE_BASENAME)


def _ensure_override_file(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(_SKELETON)


def _dict_node(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    if not isinstance(node.value, ast.Dict):
                        raise RuntimeError("%s is not a dict literal" % name)
                    return node
    raise RuntimeError("%s assignment not found" % name)


def _entry_indent(lines, lo, hi):
    for i in range(lo - 1, hi):
        m = re.match(r'^(\s*)"', lines[i])
        if m:
            return m.group(1)
    return "    "


def read_baseconfig(path=None, name=OVERRIDE_DICT):
    path = path or config_path()
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    node = _dict_node(tree, name)
    out = {}
    for k, v in zip(node.value.keys, node.value.values):
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            try:
                out[k.value] = ast.literal_eval(v)
            except (ValueError, TypeError):
                pass
    return out


def baseconfig_source_hash(path=None):
    path = path or config_path()
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def _fmt(v):
    if isinstance(v, (bool, np.bool_)):
        return repr(bool(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    f = float(v)
    s = ("%.4f" % f).rstrip("0").rstrip(".")
    return s if "." in s else s + ".0"


def _same_literal_value(current, expected):
    if isinstance(current, bool) or isinstance(expected, bool):
        return type(current) is type(expected) and current == expected
    try:
        return abs(float(current) - float(expected)) < 1e-12
    except (TypeError, ValueError, OverflowError):
        return current == expected


def update_baseconfig(updates, path=None, backup=True, expected=None,
                      expected_source_hash=None):
    path = path or config_path()
    _ensure_override_file(path)
    with open(path, "rb") as f:
        raw_src = f.read()
    src = raw_src.decode("utf-8")
    if expected_source_hash is not None:
        live_hash = hashlib.sha256(raw_src).hexdigest()
        if live_hash != str(expected_source_hash):
            raise RuntimeError(
                "compare-and-swap failed: the override source changed during "
                "calibration; refusing to write values onto an unmeasured "
                "physical configuration")
    tree = ast.parse(src)
    node = _dict_node(tree, OVERRIDE_DICT)
    lo, hi = node.lineno, node.end_lineno
    lines = src.splitlines(keepends=True)

    current_vals = {}
    for key_node, value_node in zip(node.value.keys, node.value.values):
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            try:
                current_vals[key_node.value] = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                pass
    for key, wanted in (expected or {}).items():
        if key not in current_vals:
            raise RuntimeError(
                "compare-and-swap failed: %r is not a literal in the live override "
                "table" % key)
        if not _same_literal_value(current_vals[key], wanted):
            raise RuntimeError(
                "compare-and-swap failed: override %r changed during calibration "
                "(%r at start, %r now); refusing to write a hybrid tuple"
                % (key, wanted, current_vals[key]))

    changed = {}
    inserts = {}
    for key, val in updates.items():
        pat = re.compile(r'^(\s*"' + re.escape(key) + r'"\s*:\s*)([^,#\n]+?)(\s*,)')
        hits = [i for i in range(lo - 1, hi) if pat.match(lines[i])]
        if len(hits) > 1:
            raise RuntimeError("key %r matched %d lines in overrides (expected <= 1)"
                               % (key, len(hits)))
        if len(hits) == 1:
            i = hits[0]
            m = pat.match(lines[i])
            new_val = _fmt(val)
            lines[i] = pat.sub(lambda mm: mm.group(1) + new_val + mm.group(3),
                               lines[i], count=1)
            changed[key] = (m.group(2).strip(), new_val)
        else:
            inserts[key] = val
    if inserts:
        indent = _entry_indent(lines, lo, hi)
        close_idx = hi - 1
        block = []
        for key, val in inserts.items():
            new_val = _fmt(val)
            block.append('%s"%s": %s,\n' % (indent, key, new_val))
            changed[key] = (None, new_val)
        lines[close_idx:close_idx] = block

    new_src = "".join(lines)
    new_vals = {}
    new_node = _dict_node(ast.parse(new_src), OVERRIDE_DICT)
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

    tmp = path + ".tmp_write"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(new_src)
    with open(path, "rb") as f:
        live_src = f.read().decode("utf-8")
    if live_src != src:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError(
            "BaseConfig file changed while the update was being prepared; refusing "
            "to overwrite the concurrent edit")
    if backup:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, path + ".bak_" + stamp)
    os.replace(tmp, path)
    return changed



def history_path(path=None):
    return os.path.join(os.path.dirname(path or config_path()), "pi_calibration_history.json")


def append_history(record, path=None):
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


def _lit(v):
    if isinstance(v, bool):
        return repr(v)
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return repr(float(v))
    return repr(v)


def _read_module_str(path, name):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    try:
                        val = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        return None
                    return val if isinstance(val, str) else None
    return None


def _write_overrides(dest, values, outer_folder=None):
    lines = ["OVERRIDES = {\n"]
    for k in sorted(values):
        lines.append('    "%s": %s,\n' % (k, _lit(values[k])))
    lines.append("}\n\n")
    folder = repr(outer_folder) if isinstance(outer_folder, str) and outer_folder else "None"
    lines.append("outerFolder = %s\n" % folder)
    tmp = dest + ".tmp_write"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)
    os.replace(tmp, dest)
    return dest


def bootstrap_local_overrides(source_path=None, dest_path=None, keys=None):
    dest = dest_path or config_path()
    src = source_path or os.path.join(_initialize_dir(), "initialize.py")
    values = read_baseconfig(path=src, name="BaseConfig")
    if keys is not None:
        values = {k: values[k] for k in keys if k in values}
    folder = _read_module_str(src, "outerFolder")
    return _write_overrides(dest, values, folder)


def last_ramsey_sign(qubit=None, path=None):
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
