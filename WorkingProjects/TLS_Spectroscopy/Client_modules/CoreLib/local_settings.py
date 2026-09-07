import ast
from copy import deepcopy
from pathlib import Path
from pprint import pformat
from shutil import copyfile
import subprocess


_UNCHANGED = object()
_DELETE = object()
_SOURCE_BASELINE = "_SOURCE_BASELINE"


def local_override_path(source_file):
    return Path(source_file).with_suffix(".local.py")


def _read_assignments(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            raise ValueError(f"{path} may contain only literal assignments")
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            raise ValueError(f"{path} may contain only literal assignments")
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path} may contain only literal assignments") from exc
    return values


def _merge(current, override):
    if not isinstance(current, dict) or not isinstance(override, dict):
        return deepcopy(override)
    merged = deepcopy(current)
    for key, value in override.items():
        if key in merged:
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _changed_patch(committed, current):
    if not isinstance(committed, dict) or not isinstance(current, dict):
        return _UNCHANGED if committed == current else deepcopy(current)
    changed = {
        key: _DELETE
        for key in committed
        if key not in current
    }
    for key, value in current.items():
        if key not in committed:
            changed[key] = deepcopy(value)
            continue
        patch = _changed_patch(committed[key], value)
        if patch is not _UNCHANGED:
            changed[key] = patch
    return changed if changed else _UNCHANGED


def _apply_patch(current, patch):
    if patch is _DELETE:
        return _DELETE
    if not isinstance(patch, dict):
        return deepcopy(patch)
    merged = deepcopy(current) if isinstance(current, dict) else {}
    for key, value in patch.items():
        updated = _apply_patch(merged.get(key), value)
        if updated is _DELETE:
            merged.pop(key, None)
        else:
            merged[key] = updated
    return merged


def _write_assignments(path, values, names=None, source_baseline=_UNCHANGED):
    order = tuple(values) if names is None else tuple(names)
    blocks = [
        f"{name} = {pformat(values[name], sort_dicts=False)}"
        for name in order
        if name in values
    ]
    if source_baseline is not _UNCHANGED:
        blocks.append(
            f"{_SOURCE_BASELINE} = "
            f"{pformat(source_baseline, sort_dicts=False)}"
        )
    path.write_text("\n\n".join(blocks) + "\n")


def _head_source_text(source_file):
    source = Path(source_file).resolve()
    try:
        root_result = subprocess.run(
            ["git", "-C", str(source.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if root_result.returncode != 0:
        return None
    root = Path(root_result.stdout.strip()).resolve()
    try:
        relative = source.relative_to(root).as_posix()
    except ValueError:
        return None
    try:
        show_result = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{relative}"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return show_result.stdout if show_result.returncode == 0 else None


def _direct_source_changes(source_file, allowed_names, source_baseline=None):
    if source_baseline is None:
        head_text = _head_source_text(source_file)
        if head_text is None:
            return None, {}
        _, committed = _source_local_values(head_text, str(source_file))
    else:
        committed = source_baseline
    _, current = source_local_values(source_file)
    changed = {}
    for name in allowed_names:
        if name not in current or name not in committed:
            continue
        patch = _changed_patch(committed[name], current[name])
        if patch is not _UNCHANGED:
            changed[name] = patch
    return current, changed


def apply_local_overrides(namespace, source_file, allowed_names):
    path = local_override_path(source_file)
    if not path.exists():
        return None
    allowed = tuple(allowed_names)
    values = _read_assignments(path)
    source_baseline = values.pop(_SOURCE_BASELINE, None)
    removed_names = set()
    if isinstance(source_baseline, dict):
        removed_names = (
            set(values) - set(allowed)
        ) & set(source_baseline)
        for name in removed_names:
            values.pop(name)
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ValueError(f"unknown local setting names in {path}: {', '.join(unknown)}")
    current, direct_changes = _direct_source_changes(
        source_file,
        allowed,
        source_baseline if isinstance(source_baseline, dict) else None,
    )
    if direct_changes:
        values = _apply_patch(values, direct_changes)
    if current is not None and (
        source_baseline != current or direct_changes or removed_names
    ):
        _write_assignments(path, values, allowed, current)
    for name, value in values.items():
        namespace[name] = _merge(namespace[name], value)
    return path


def snapshot_local_overrides(
    namespace,
    source_file,
    allowed_names,
    source_baseline=_UNCHANGED,
):
    path = local_override_path(source_file)
    if path.exists():
        return path
    _write_assignments(
        path,
        namespace,
        allowed_names,
        source_baseline,
    )
    return path


def _source_value(node, values):
    if isinstance(node, ast.Constant):
        return deepcopy(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise ValueError(f"unknown setting reference {node.id}")
        return deepcopy(values[node.id])
    if isinstance(node, ast.List):
        return [_source_value(item, values) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_source_value(item, values) for item in node.elts)
    if isinstance(node, ast.Set):
        return {_source_value(item, values) for item in node.elts}
    if isinstance(node, ast.Dict):
        return {
            _source_value(key, values): _source_value(value, values)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _source_value(node.operand, values)
        return value if isinstance(node.op, ast.UAdd) else -value
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
        and not node.keywords
    ):
        return str(_source_value(node.args[0], values))
    raise ValueError("setting is not a supported literal expression")


def _source_local_values(source, filename):
    tree = ast.parse(source, filename=filename)
    allowed = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "LOCAL_OVERRIDE_KEYS":
            allowed = tuple(ast.literal_eval(node.value))
            break
    if allowed is None:
        raise ValueError(f"{filename} has no LOCAL_OVERRIDE_KEYS")
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = _source_value(node.value, values)
        except ValueError:
            if target.id in allowed:
                raise
    missing = [name for name in allowed if name not in values]
    if missing:
        raise ValueError(f"missing local settings in {filename}: {', '.join(missing)}")
    return allowed, {name: values[name] for name in allowed}


def source_local_values(source_file):
    path = Path(source_file)
    return _source_local_values(path.read_text(), str(path))


def snapshot_source_local_overrides(source_file):
    allowed, values = source_local_values(source_file)
    return snapshot_local_overrides(
        values,
        source_file,
        allowed,
        values,
    )


def copy_local_scratch(source_file, target_file=None):
    source = Path(source_file)
    target = (
        local_override_path(source)
        if target_file is None
        else Path(target_file)
    )
    if not target.exists():
        copyfile(source, target)
    return target
