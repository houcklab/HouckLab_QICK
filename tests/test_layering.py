"""Package layering (docs/dev/refactor-2026-10/design.md "Package layering"), checked on the source.

hardware < core < analysis < experiments < runs < twpa: a module imports only from its own layer
or a lower one. analysis never imports qick. No project import inside a function or class body.
qicklab/__init__.py is empty. Device files import only qicklab.core.device.
"""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAYERS = ("hardware", "core", "analysis", "experiments", "runs", "twpa")
RANK = {name: i for i, name in enumerate(LAYERS)}

# (importing module, imported module) -> why it is allowed. Every entry must still be needed.
LOCAL_IMPORT_EXEMPTIONS = {
    ("qicklab.analysis.zero_span", "qicklab.analysis.zero_span_checks"): (
        "import cycle: zero_span_checks imports classify_parity_trace/_bin_iq_time from zero_span. "
        "Fix: move projected_histogram_snr into analysis.zero_span (re-exported by "
        "zero_span_checks) with its symbol-map row, then delete this entry."
    ),
}


def _modules(top):
    for path in sorted((REPO / top).rglob("*.py")):
        rel = path.relative_to(REPO).with_suffix("")
        parts = rel.parts[:-1] if rel.parts[-1] == "__init__" else rel.parts
        yield ".".join(parts), path


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _module_scope(tree):
    """ids of the nodes that run at import time: the module body and everything nested under a
    module-level if/try/with/for, but not the bodies of functions, classes or lambdas."""
    ids, stack = set(), list(tree.body)
    while stack:
        node = stack.pop()
        ids.add(id(node))
        if not isinstance(node, _SCOPES):
            stack.extend(ast.iter_child_nodes(node))
    return ids


def _imports(path):
    """(imported module, lineno, is_top_level) for every import statement in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    top_level = _module_scope(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, node.lineno, id(node) in top_level) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path}:{node.lineno}: relative import"
            if node.module == "qicklab":
                out += [
                    (f"qicklab.{a.name}", node.lineno, id(node) in top_level) for a in node.names
                ]
            else:
                out.append((node.module, node.lineno, id(node) in top_level))
    return out


def _layer(module):
    parts = module.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "qicklab" else None


def test_layer_order():
    bad = []
    for mod, path in _modules("qicklab"):
        own = _layer(mod)
        if own is None:
            continue
        for target, line, _ in _imports(path):
            tl = _layer(target)
            if tl in RANK and RANK[tl] > RANK[own]:
                bad.append(f"{mod}:{line} ({own}) imports {target} ({tl})")
    assert not bad, "upward imports:\n" + "\n".join(bad)


def test_analysis_never_imports_qick():
    bad = [
        f"{mod}:{line} imports {target}"
        for mod, path in _modules("qicklab")
        if _layer(mod) == "analysis"
        for target, line, _ in _imports(path)
        if target.split(".")[0] == "qick"
    ]
    assert not bad, "\n".join(bad)


def test_no_function_local_project_imports():
    bad, used = [], set()
    for top in ("qicklab", "devices"):
        for mod, path in _modules(top):
            for target, line, top_level in _imports(path):
                if top_level or target.split(".")[0] not in ("qicklab", "devices"):
                    continue
                key = (mod, target)
                if key in LOCAL_IMPORT_EXEMPTIONS:
                    used.add(key)
                else:
                    bad.append(f"{mod}:{line} imports {target} inside a function or class")
    assert not bad, "\n".join(bad)
    stale = set(LOCAL_IMPORT_EXEMPTIONS) - used
    assert not stale, f"exemptions no longer needed, delete them: {sorted(stale)}"


def test_scope_scan_sees_functions_under_module_level_blocks(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import qicklab.core.a\n"
        "if True:\n"
        "    import qicklab.core.b\n"
        "    def g():\n"
        "        import qicklab.core.c\n"
        "try:\n"
        "    from qicklab.core import d\n"
        "except ImportError:\n"
        "    class K:\n"
        "        import qicklab.core.e\n"
        "    f = lambda: __import__('x')\n"
        "def h():\n"
        "    if True:\n"
        "        import qicklab.core.g\n",
        encoding="utf-8",
    )
    got = {target: top for target, _, top in _imports(probe)}
    assert got == {
        "qicklab.core.a": True,
        "qicklab.core.b": True,
        "qicklab.core.c": False,
        "qicklab.core": True,
        "qicklab.core.e": False,
        "qicklab.core.g": False,
    }


def test_qicklab_init_is_empty():
    assert (REPO / "qicklab" / "__init__.py").read_text(encoding="utf-8").strip() == ""


def test_device_files_import_only_core_device():
    bad = []
    for mod, path in _modules("devices"):
        for target, line, _ in _imports(path):
            if target.split(".")[0] in ("qicklab", "devices") and target != "qicklab.core.device":
                bad.append(f"{mod}:{line} imports {target}")
    assert not bad, "\n".join(bad)
