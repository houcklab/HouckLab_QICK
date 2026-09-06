import ast
from copy import deepcopy
from pathlib import Path
from pprint import pformat
from shutil import copyfile


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


def apply_local_overrides(namespace, source_file, allowed_names):
    path = local_override_path(source_file)
    if not path.exists():
        return None
    allowed = tuple(allowed_names)
    values = _read_assignments(path)
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ValueError(f"unknown local setting names in {path}: {', '.join(unknown)}")
    for name, value in values.items():
        namespace[name] = _merge(namespace[name], value)
    return path


def snapshot_local_overrides(namespace, source_file, allowed_names):
    path = local_override_path(source_file)
    if path.exists():
        return path
    blocks = []
    for name in allowed_names:
        blocks.append(f"{name} = {pformat(namespace[name], sort_dicts=False)}")
    path.write_text("\n\n".join(blocks) + "\n")
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


def source_local_values(source_file):
    path = Path(source_file)
    tree = ast.parse(path.read_text(), filename=str(path))
    allowed = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "LOCAL_OVERRIDE_KEYS":
            allowed = tuple(ast.literal_eval(node.value))
            break
    if allowed is None:
        raise ValueError(f"{path} has no LOCAL_OVERRIDE_KEYS")
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
        raise ValueError(f"missing local settings in {path}: {', '.join(missing)}")
    return allowed, {name: values[name] for name in allowed}


def snapshot_source_local_overrides(source_file):
    allowed, values = source_local_values(source_file)
    return snapshot_local_overrides(values, source_file, allowed)


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
