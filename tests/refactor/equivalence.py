"""Phase-3a equivalence checker: the legacy tree at 0f0a51f versus the qicklab package.

Four checks, driven by ``tests/refactor/symbol_map.py`` (see README.md in this folder):

(a) the legacy tree is checked out into a temporary ``git worktree`` and imported from
    there (its own sys.path entry, its own sys.modules session);
(b) AST equality per moved symbol: imports and docstrings removed, every global name
    that refers to a project symbol spelled as that symbol's NEW name on both sides;
(c) binding check: every free global name of a moved symbol (methods and nested
    functions included) must resolve to the same origin in old and new -- same symbol
    (location + normalised AST hash) for project code, same object for everything else;
(d) ledger: every top-level statement of every legacy module has exactly one entry.

CLI::

    python -m tests.refactor.equivalence                 # check whatever exists under qicklab/
    python -m tests.refactor.equivalence --phase 3a-i    # require every 3a-i entry to be in place
    python -m tests.refactor.equivalence --ledger-only   # (d) only, legacy tree only
    python -m tests.refactor.equivalence --self-test     # identity must pass, perturbations must fail
"""

from __future__ import annotations

import argparse
import ast
import builtins
import contextlib
import copy
import difflib
import hashlib
import importlib
import io
import json
import shutil
import subprocess
import symtable
import sys
import tempfile
import types
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEGACY_COMMIT = "0f0a51f"
LEGACY_PREFIX = "WorkingProjects.QM_Team.qubit_measurements.Client_modules"
LEGACY_DIR = LEGACY_PREFIX.replace(".", "/")
NEW_TOPS = ("qicklab", "runners", "tests", "devices")
# Never imported: the legacy runner (at LEGACY_COMMIT; its runners/ copy is deleted since 5b)
# executes a measurement session at import time; runners/ and tests/ in the new tree are
# scripts, checked statically.
NEVER_IMPORT = (f"{LEGACY_PREFIX}.Runners.CSTQ03_BFC", "runners", "tests")
MODULE_DUNDERS = frozenset(
    "__file__ __name__ __doc__ __spec__ __package__ __path__ __loader__ __cached__".split()
)
MAIN_GUARD = "<main>"
MODULE_KEY = "<module>"
AST_KINDS = ("moved", "renamed", "merged", "deleted")


# ----------------------------------------------------------------------------- keys


def _is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    t = node.test
    sides = [t.left, *t.comparators]
    names = {s.id for s in sides if isinstance(s, ast.Name)}
    consts = {s.value for s in sides if isinstance(s, ast.Constant)}
    return names == {"__name__"} and consts == {"__main__"}


def _target_names(target: ast.AST) -> list[str] | None:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out = []
        for elt in target.elts:
            sub = _target_names(elt)
            if sub is None:
                return None
            out += sub
        return out
    return None


def _raw_key(node: ast.stmt) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign):
        names = [_target_names(t) for t in node.targets]
        if all(n is not None for n in names):
            return ",".join(n for group in names for n in group)
        return f"<assign:{ast.unparse(node.targets[0])}>"
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, ast.AugAssign):
        return f"<augassign:{ast.unparse(node.target)}>"
    if _is_main_guard(node):
        return MAIN_GUARD
    if isinstance(node, ast.If):
        return f"<if:{ast.unparse(node.test)}>"
    if isinstance(node, ast.Expr):
        return f"<expr:{ast.unparse(node.value)}>"
    return f"<{type(node).__name__.lower()}:{ast.unparse(node).splitlines()[0]}>"


def statement_keys(tree: ast.Module) -> list[tuple[str, ast.stmt]]:
    """Ledger keys of a module's top-level statements (imports and the docstring excluded)."""
    seen: Counter[str] = Counter()
    out = []
    for i, node in enumerate(tree.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)) or (i == 0 and _is_docstring(node)):
            continue
        key = _raw_key(node)
        seen[key] += 1
        out.append((key if seen[key] == 1 else f"{key}#{seen[key]}", node))
    return out


def _assign_key_names(tree: ast.Module) -> dict[str, str]:
    """name -> ledger key of the top-level statement that (last) binds it."""
    out = {}
    for key, node in statement_keys(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = key
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for name in _target_names(t) or []:
                    out[name] = key
    return out


# ----------------------------------------------------------------------------- trees


@dataclass
class Tree:
    """A source tree on disk; module names are resolved relative to ``root``."""

    label: str
    root: Path
    _src: dict = field(default_factory=dict)
    _ast: dict = field(default_factory=dict)
    _sym: dict = field(default_factory=dict)

    def path(self, module: str) -> Path | None:
        base = self.root / module.replace(".", "/")
        for p in (base.with_suffix(".py"), base / "__init__.py"):
            if p.is_file():
                return p
        return None

    def exists(self, module: str) -> bool:
        return self.path(module) is not None

    def is_package(self, module: str) -> bool:
        p = self.path(module)
        return p is not None and p.name == "__init__.py"

    def source(self, module: str) -> str:
        if module not in self._src:
            self._src[module] = self.path(module).read_text(encoding="utf-8")
        return self._src[module]

    def parse(self, module: str) -> ast.Module:
        if module not in self._ast:
            self._ast[module] = ast.parse(self.source(module), filename=str(self.path(module)))
        return self._ast[module]

    def symtable(self, module: str) -> symtable.SymbolTable:
        if module not in self._sym:
            self._sym[module] = symtable.symtable(
                self.source(module), str(self.path(module)), "exec"
            )
        return self._sym[module]

    def statements(self, module: str) -> dict[str, ast.stmt]:
        return dict(statement_keys(self.parse(module)))

    def legacy_modules(self) -> list[str]:
        base = self.root / LEGACY_DIR
        out = []
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(self.root).with_suffix("")
            parts = list(rel.parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            out.append(".".join(parts))
        return out


def is_project(module: str) -> bool:
    return module.startswith(LEGACY_PREFIX) or module.split(".")[0] in NEW_TOPS


# ----------------------------------------------------------------------------- static resolver


class Resolver:
    """Static model of a module's final global namespace (what a function sees at call time).

    Bindings: ("def", module, key) project statement; ("module", name);
    ("ext", module, attr) a name taken from a non-project module; ("missing", module, attr).
    """

    def __init__(self, tree: Tree):
        self.tree = tree
        self._ns: dict[str, dict] = {}

    def _external_names(self, module: str) -> list[str]:
        try:
            mod = importlib.import_module(module)
        except Exception:
            return []
        names = getattr(mod, "__all__", None)
        return list(names) if names is not None else [n for n in dir(mod) if not n.startswith("_")]

    def _abs(self, module: str, node: ast.ImportFrom) -> str:
        if not node.level:
            return node.module
        parts = module.split(".")
        if not self.tree.is_package(module):
            parts = parts[:-1]
        parts = parts[: len(parts) - (node.level - 1)]
        return ".".join(parts + ([node.module] if node.module else []))

    def binding_of(self, module: str, name: str):
        if is_project(module) and self.tree.exists(module):
            ns = self.namespace(module)
            if name in ns:
                return ns[name]
            if self.tree.exists(f"{module}.{name}"):
                return ("module", f"{module}.{name}")
            return ("missing", module, name)
        return ("ext", module, name)

    def star_names(self, module: str) -> list[str]:
        if is_project(module) and self.tree.exists(module):
            for node in self.tree.parse(module).body:
                if (
                    isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ):
                    return [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
            return [n for n in self.namespace(module) if not n.startswith("_")]
        return self._external_names(module)

    def namespace(self, module: str) -> dict:
        if module in self._ns:
            return self._ns[module]
        ns: dict = {}
        self._ns[module] = ns  # partial namespace visible to import cycles, like CPython
        keys = _assign_key_names(self.tree.parse(module))
        self._walk(module, self.tree.parse(module).body, ns, keys)
        return ns

    def _walk(self, module, body, ns, keys):
        for node in body:
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        ns[a.asname] = ("module", a.name)
                    else:
                        ns[a.name.split(".")[0]] = ("module", a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                src = self._abs(module, node)
                for a in node.names:
                    if a.name == "*":
                        for n in self.star_names(src):
                            ns[n] = self.binding_of(src, n)
                    else:
                        ns[a.asname or a.name] = self.binding_of(src, a.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                ns[node.name] = ("def", module, keys.get(node.name, node.name))
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                for t in targets:
                    names = _target_names(t) or []
                    alias = (
                        isinstance(node, ast.Assign)
                        and len(names) == 1
                        and isinstance(t, ast.Name)
                        and isinstance(value, ast.Name)
                        and value.id in ns
                    )
                    for n in names:
                        ns[n] = ns[value.id] if alias else ("def", module, keys.get(n, n))
            elif isinstance(node, ast.If) and not _is_main_guard(node):
                self._walk(module, node.body, ns, keys)
                self._walk(module, node.orelse, ns, keys)
            elif isinstance(node, ast.Try):
                for part in (node.body, *[h.body for h in node.handlers], node.orelse):
                    self._walk(module, part, ns, keys)


# ----------------------------------------------------------------------------- normalisation


class _ScopeWalker(ast.NodeTransformer):
    """Visits a symbol with the matching symtable scope, so only true globals are touched."""

    def __init__(self, table: symtable.SymbolTable, on_global):
        self.stack = [table]
        self.on_global = on_global  # callback(name_node) for global Name nodes

    def _is_global(self, name: str) -> bool:
        t = self.stack[-1]
        if t.get_type() == "module":  # str on <=3.12, StrEnum on 3.13
            return True
        try:
            return t.lookup(name).is_global()
        except KeyError:
            return False

    def _child(self, node, name):
        parent = self.stack[-1]
        for ch in parent.get_children():
            if ch.get_lineno() == node.lineno and ch.get_name() == name:
                return ch
        return parent

    def _visit_list(self, nodes):
        return [self.visit(n) for n in nodes if n is not None]

    def _visit_args(self, args: ast.arguments):
        args.defaults = self._visit_list(args.defaults)
        args.kw_defaults = [self.visit(d) if d is not None else None for d in args.kw_defaults]
        for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if a is not None and a.annotation is not None:
                a.annotation = self.visit(a.annotation)

    def visit_FunctionDef(self, node):
        node.decorator_list = self._visit_list(node.decorator_list)
        self._visit_args(node.args)
        if node.returns is not None:
            node.returns = self.visit(node.returns)
        self.stack.append(self._child(node, node.name))
        node.body = self._visit_list(node.body)
        self.stack.pop()
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        node.decorator_list = self._visit_list(node.decorator_list)
        node.bases = self._visit_list(node.bases)
        node.keywords = self._visit_list(node.keywords)
        self.stack.append(self._child(node, node.name))
        node.body = self._visit_list(node.body)
        self.stack.pop()
        return node

    def visit_Lambda(self, node):
        self._visit_args(node.args)
        self.stack.append(self._child(node, "lambda"))
        node.body = self.visit(node.body)
        self.stack.pop()
        return node

    def _visit_comprehension(self, node, scope_name):
        # The first iterable is evaluated in the enclosing scope. Comprehensions inlined by
        # PEP 709 (3.12+) have no table of their own: _child then falls back to the parent.
        first, *rest = node.generators
        first.iter = self.visit(first.iter)
        self.stack.append(self._child(node, scope_name))
        first.target = self.visit(first.target)
        first.ifs = self._visit_list(first.ifs)
        for g in rest:
            self.generic_visit(g)
        for fld in ("elt", "key", "value"):
            if hasattr(node, fld):
                setattr(node, fld, self.visit(getattr(node, fld)))
        self.stack.pop()
        return node

    def visit_GeneratorExp(self, node):
        return self._visit_comprehension(node, "genexpr")

    def visit_ListComp(self, node):
        return self._visit_comprehension(node, "listcomp")

    def visit_SetComp(self, node):
        return self._visit_comprehension(node, "setcomp")

    def visit_DictComp(self, node):
        return self._visit_comprehension(node, "dictcomp")

    def visit_Name(self, node):
        if self._is_global(node.id):
            self.on_global(node)
        return node


_SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_STMT_LISTS = ("body", "orelse", "finalbody")


class _Strip(ast.NodeTransformer):
    """Remove imports (anywhere) and docstrings (module/class/def); keep blocks non-empty."""

    def visit_Import(self, node):
        return None

    visit_ImportFrom = visit_Import

    def generic_visit(self, node):
        if isinstance(node, _SCOPES) and node.body and _is_docstring(node.body[0]):
            node.body = node.body[1:]
        had = {f: isinstance(getattr(node, f, None), list) for f in _STMT_LISTS}
        had = {f: v and bool(getattr(node, f)) for f, v in had.items()}
        super().generic_visit(node)
        for f, was in had.items():
            if (was or (f == "body" and isinstance(node, _SCOPES))) and not getattr(node, f):
                setattr(node, f, [ast.Pass()])
        return node


# ----------------------------------------------------------------------------- the checker


@dataclass
class Finding:
    check: str  # ledger | ast | binding | structure | import
    status: str  # FAIL | WARN | OK | SKIP
    where: str
    detail: str = ""


class Side:
    """One tree plus its static resolver, runtime modules and per-module name maps."""

    def __init__(self, tree: Tree, checker: Checker):
        self.tree = tree
        self.checker = checker
        self.resolver = Resolver(tree)
        self.modules: dict[str, types.ModuleType] = {}
        self.import_errors: dict[str, str] = {}
        self._maps: dict[str, dict[str, str]] = {}
        self._hash: dict[tuple[str, str], str | None] = {}

    # canonical spelling of each global name of a module (project symbols -> their new name)
    def name_map(self, module: str) -> dict[str, str]:
        if module not in self._maps:
            m = {}
            for name, b in self.resolver.namespace(module).items():
                if b[0] == "def":
                    spelled = self.checker.canonical_name(b[1], b[2], name)
                    if spelled != name:
                        m[name] = spelled
            self._maps[module] = m
        return self._maps[module]

    def normalized(self, module: str, key: str, rename_to: str | None = None) -> ast.AST | None:
        node = self.tree.statements(module).get(key)
        if node is None:
            return None
        node = copy.deepcopy(node)
        mapping = self.name_map(module)

        def rewrite(name_node):
            if name_node.id in mapping:
                name_node.id = mapping[name_node.id]

        _ScopeWalker(self.tree.symtable(module), rewrite).visit(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            node.name = rename_to or self.checker.canonical_name(module, key, node.name)
        node = _Strip().visit(node)
        return node

    def ast_hash(self, module: str, key: str) -> str | None:
        if (module, key) not in self._hash:
            if not self.tree.exists(module):
                self._hash[(module, key)] = None
            else:
                node = self.normalized(module, key)
                self._hash[(module, key)] = (
                    None if node is None else hashlib.sha1(ast.dump(node).encode()).hexdigest()[:12]
                )
        return self._hash[(module, key)]

    def global_loads(self, module: str, key: str) -> list[str]:
        node = self.tree.statements(module).get(key)
        names: list[str] = []

        def grab(name_node):
            if isinstance(name_node.ctx, ast.Load) and name_node.id not in names:
                names.append(name_node.id)

        _ScopeWalker(self.tree.symtable(module), grab).visit(copy.deepcopy(node))
        return names

    # origin descriptor of a global name, runtime first, static fallback
    def describe(self, module: str, name: str):
        if name in MODULE_DUNDERS:
            return ("dunder", name)  # per-module by definition; compared by role
        static = self.resolver.namespace(module).get(name)
        mod = self.modules.get(module)
        if mod is not None:
            if name in mod.__dict__:
                obj = mod.__dict__[name]
            elif hasattr(builtins, name):
                return ("obj", getattr(builtins, name))
            else:
                return ("missing",)
            if isinstance(obj, types.ModuleType):
                return self._describe_module(obj.__name__, obj)
            owner = getattr(obj, "__module__", None)
            if (
                isinstance(obj, (types.FunctionType, type))
                and isinstance(owner, str)
                and is_project(owner)
            ):
                top = obj.__qualname__.split(".")[0]
                key = _assign_key_names(self.tree.parse(owner)).get(top, top)
                return self._describe_def(owner, key)
            if static is not None and static[0] == "def":
                return self._describe_def(static[1], static[2])
            return ("obj", obj)
        # static fallback
        if static is None:
            return ("obj", getattr(builtins, name)) if hasattr(builtins, name) else ("missing",)
        if static[0] == "def":
            return self._describe_def(static[1], static[2])
        if static[0] == "module":
            return self._describe_module(static[1], None)
        if static[0] == "missing":
            return ("missing",)
        try:
            return ("obj", getattr(importlib.import_module(static[1]), static[2]))
        except Exception:
            return ("ext-unresolved", static[1], static[2])

    def _describe_module(self, name: str, obj):
        if is_project(name):
            return ("projmod", self.checker.canonical_module(name))
        if obj is None:
            try:
                obj = importlib.import_module(name)
            except Exception:
                return ("ext-unresolved", name)
        return ("obj", obj)

    def _describe_def(self, module: str, key: str):
        loc = self.checker.canonical_location(module, key)
        return ("proj", loc, self.ast_hash(module, key))


def _same_origin(a, b) -> bool:
    if a[0] != b[0]:
        return False
    if a[0] != "obj":
        return a == b
    x, y = a[1], b[1]
    if x is y:
        return True
    qx = (getattr(x, "__module__", None), getattr(x, "__qualname__", None))
    qy = (getattr(y, "__module__", None), getattr(y, "__qualname__", None))
    if None not in qx and qx == qy:
        return True
    if isinstance(x, (int, float, str, bytes, bool, type(None), tuple, frozenset)):
        return type(x) is type(y) and x == y
    return False


def _fmt(desc) -> str:
    if desc[0] == "obj":
        o = desc[1]
        if isinstance(o, types.ModuleType):
            return f"module {o.__name__}"
        q = getattr(o, "__qualname__", None)
        if q is not None:
            return f"{type(o).__name__} {getattr(o, '__module__', '?')}.{q}"
        return f"{type(o).__name__} {o!r:.60}"
    if desc[0] == "proj":
        return f"project {desc[1][0]}:{desc[1][1]} [ast {desc[2]}]"
    return " ".join(str(x) for x in desc)


class Checker:
    def __init__(self, entries, old_tree: Tree, new_tree: Tree, file_phase: dict[str, str]):
        self.entries = list(entries)
        self.file_phase = file_phase
        self.by_old = {(e.old_module, e.old_qualname): e for e in self.entries}
        self.module_dest = {
            e.old_module: e.new_module for e in self.entries if e.old_qualname == MODULE_KEY
        }
        self.old = Side(old_tree, self)
        self.new = Side(new_tree, self)
        self.findings: list[Finding] = []

    # ---- name canonicalisation (shared by both sides)
    def canonical_location(self, module: str, key: str) -> tuple[str, str]:
        if module.startswith(LEGACY_PREFIX):
            e = self.by_old.get((module, key))
            if e is not None:
                return (e.new_module, e.new_name)
        return (module, key)

    def canonical_name(self, module: str, key: str, name: str) -> str:
        """How the new code spells the symbol bound to ``name`` (key = its ledger key).

        Aliases (``from x import a as b``, ``b = a``) spell the target's new name, so old
        and new code compare equal however each side chose to import it.
        """
        if "," in key or key.startswith("<"):
            return name  # one name of a tuple assignment / a synthetic key: never renamed
        return self.canonical_location(module, key)[1]

    def canonical_module(self, module: str) -> str:
        return self.module_dest.get(module, module)

    # ---- (a) runtime loading
    def load(self, side: Side, modules: list[str]):
        root = side.tree.root
        tops = {"WorkingProjects", "qicklab", "devices", "runners"}
        saved_path = list(sys.path)
        saved_mods = {k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] in tops}
        sys.path.insert(0, str(root))
        importlib.invalidate_caches()
        sink = io.StringIO()
        try:
            for m in modules:
                if m.startswith(NEVER_IMPORT) or not side.tree.exists(m):
                    continue
                try:
                    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                        mod = importlib.import_module(m)
                except BaseException as exc:  # noqa: BLE001 - SystemExit from scripts too
                    side.import_errors[m] = f"{type(exc).__name__}: {exc}"[:200]
                    continue
                f = Path(getattr(mod, "__file__", "") or "").resolve()
                if root.resolve() not in f.parents:
                    raise RuntimeError(f"{m} imported from {f}, expected under {root}")
                side.modules[m] = mod
        finally:
            for k in list(sys.modules):
                if k.split(".")[0] in tops:
                    sys.modules.pop(k)
            sys.modules.update(saved_mods)
            sys.path[:] = saved_path
            importlib.invalidate_caches()

    # ---- (d) ledger
    def check_ledger(self):
        counts = Counter((e.old_module, e.old_qualname) for e in self.entries)
        for k, n in counts.items():
            if n > 1:
                self.findings.append(Finding("ledger", "FAIL", f"{k[0]}:{k[1]}", f"{n} entries"))
        legacy = self.old.tree.legacy_modules()
        mapped = {e.old_module for e in self.entries}
        for m in legacy:
            keys = [MODULE_KEY] + [k for k, _ in statement_keys(self.old.tree.parse(m))]
            if m not in mapped:
                self.findings.append(Finding("ledger", "FAIL", m, "legacy file has no entries"))
            for k in keys:
                if (m, k) not in counts:
                    self.findings.append(Finding("ledger", "FAIL", f"{m}:{k}", "no entry"))
            for e in self.entries:
                if e.old_module == m and e.old_qualname not in keys:
                    self.findings.append(
                        Finding("ledger", "FAIL", f"{m}:{e.old_qualname}", "stale entry")
                    )
        for m in mapped - set(legacy):
            self.findings.append(Finding("ledger", "FAIL", m, "entries for a non-existent file"))
        n = sum(1 + len(statement_keys(self.old.tree.parse(m))) for m in legacy)
        self.findings.append(Finding("ledger", "OK", "legacy", f"{len(legacy)} files, {n} keys"))

    # ---- (b) + (c)
    def selected(self, phase: str | None):
        out = []
        for e in self.entries:
            if e.old_qualname == MODULE_KEY or e.kind not in AST_KINDS:
                continue
            fp = self.file_phase.get(e.old_module, "3a-i")
            if phase == "3a-i" and fp != "3a-i":
                continue
            out.append(e)
        return out

    def check_duplicates(self, modules):
        """A name bound twice at top level: the earlier binding is dead at runtime."""
        for m in sorted(modules):
            if not self.new.tree.exists(m):
                continue
            for key, _ in statement_keys(self.new.tree.parse(m)):
                base, _, n = key.partition("#")
                if n and not base.startswith("<"):
                    self.findings.append(
                        Finding("structure", "FAIL", f"{m}:{base}", f"bound {n}x at top level")
                    )

    def check_symbols(self, phase: str | None):
        entries = self.selected(phase)
        self.check_duplicates({e.new_module for e in entries})
        for e in entries:
            # In 3b a symbol may already sit at its final home (final_module/final_name).
            at_final = (
                phase == "3b"
                and e.final_module is not None
                and self.new.tree.exists(e.final_module)
                and self.new.tree.statements(e.final_module).get(e.final_name or e.new_name)
                is not None
            )
            if at_final and e.kind != "deleted":
                continue
            where = f"{_short(e.old_module)}:{e.old_qualname} -> {e.new_module}:{e.new_name}"
            if not self.new.tree.exists(e.new_module):
                status = "FAIL" if phase in ("3a-i", "3a-ii") else "SKIP"
                self.findings.append(Finding("structure", status, where, "new module missing"))
                continue
            new_stmt = self.new.tree.statements(e.new_module).get(e.new_name)
            if new_stmt is None:
                if e.kind in ("deleted", "merged") and e.phase == "3b":
                    status = "OK" if phase == "3b" else "WARN"
                    self.findings.append(Finding("structure", status, where, "absent (3b work)"))
                else:
                    self.findings.append(Finding("structure", "FAIL", where, "symbol missing"))
                continue
            if phase == "3b":
                if e.kind == "deleted":
                    self.findings.append(Finding("structure", "FAIL", where, "should be deleted"))
                continue
            self._compare_ast(e, where)
            self._compare_bindings(e, where)

    def _compare_ast(self, e, where):
        old = self.old.normalized(e.old_module, e.old_qualname, rename_to=e.new_name)
        new = self.new.normalized(e.new_module, e.new_name, rename_to=e.new_name)
        if ast.dump(old) == ast.dump(new):
            self.findings.append(Finding("ast", "OK", where))
            return
        a, b = ast.unparse(old).splitlines(), ast.unparse(new).splitlines()
        diff = list(difflib.unified_diff(a, b, "old", "new", lineterm="", n=1))
        self.findings.append(Finding("ast", "FAIL", where, "\n".join(diff[:40])))

    def _compare_bindings(self, e, where):
        old_names = self.old.global_loads(e.old_module, e.old_qualname)
        new_names = self.new.global_loads(e.new_module, e.new_name)
        omap, nmap = self.old.name_map(e.old_module), self.new.name_map(e.new_module)
        new_by_spelling = {nmap.get(n, n): n for n in new_names}
        bad = []
        for o in old_names:
            spelled = omap.get(o, o)
            n = new_by_spelling.get(spelled)
            if n is None:
                continue  # name no longer used: already an AST mismatch
            d_old = self.old.describe(e.old_module, o)
            d_new = self.new.describe(e.new_module, n)
            if not _same_origin(d_old, d_new):
                bad.append(f"  {o!r}: old -> {_fmt(d_old)}\n  {n!r}: new -> {_fmt(d_new)}")
        mode = "runtime" if e.old_module in self.old.modules else "static"
        mode += "/" + ("runtime" if e.new_module in self.new.modules else "static")
        if "__file__" in old_names and Path(self.old.tree.path(e.old_module)).parent.relative_to(
            self.old.tree.root
        ) != Path(self.new.tree.path(e.new_module)).parent.relative_to(self.new.tree.root):
            self.findings.append(
                Finding(
                    "binding", "WARN", where, "uses __file__ and the file moved: check path math"
                )
            )
        if bad:
            self.findings.append(Finding("binding", "FAIL", where, f"[{mode}]\n" + "\n".join(bad)))
        else:
            self.findings.append(Finding("binding", "OK", where, mode))

    def run(self, phase: str | None = None, ledger_only: bool = False, runtime: bool = True):
        self.check_ledger()
        if ledger_only:
            return self.findings
        entries = self.selected(phase)
        if runtime:
            self.load(self.old, sorted({e.old_module for e in entries}))
            new_mods = sorted({e.new_module for e in entries if self.new.tree.exists(e.new_module)})
            self.load(self.new, new_mods)
            for side in (self.old, self.new):
                for m, err in side.import_errors.items():
                    self.findings.append(
                        Finding("import", "WARN", f"{side.tree.label}:{m}", f"static only: {err}")
                    )
        self.check_symbols(phase)
        return self.findings


def _short(module: str) -> str:
    return module[len(LEGACY_PREFIX) + 1 :] if module.startswith(LEGACY_PREFIX) else module


# ----------------------------------------------------------------------------- worktree


@contextlib.contextmanager
def legacy_worktree(commit: str = LEGACY_COMMIT):
    """Check ``commit`` out into a temporary git worktree; always removed afterwards."""
    tmp = Path(tempfile.mkdtemp(prefix="qicklab_legacy_"))
    wt = tmp / "legacy"
    git = ["git", "-C", str(REPO)]
    subprocess.run(
        [*git, "worktree", "add", "--detach", str(wt), commit], check=True, capture_output=True
    )
    try:
        yield wt
    finally:
        subprocess.run([*git, "worktree", "remove", "--force", str(wt)], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
        subprocess.run([*git, "worktree", "prune"], capture_output=True)


# ----------------------------------------------------------------------------- reporting


def report(findings: list[Finding], verbose: bool = False, out=sys.stdout) -> int:
    tally: dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        tally[f.check][f.status] += 1
    fails = [f for f in findings if f.status == "FAIL"]
    for f in findings:
        if f.status == "FAIL" or (verbose and f.status in ("WARN", "SKIP")):
            print(f"{f.status} [{f.check}] {f.where}", file=out)
            if f.detail:
                print("    " + f.detail.replace("\n", "\n    "), file=out)
    print("summary:", file=out)
    for check in ("ledger", "structure", "import", "ast", "binding"):
        if check in tally:
            parts = ", ".join(f"{k}={v}" for k, v in sorted(tally[check].items()))
            print(f"  {check:9s} {parts}", file=out)
    print("RESULT:", "FAIL" if fails else "PASS", f"({len(fails)} failures)", file=out)
    return 1 if fails else 0


def _entries_and_phases():
    from tests.refactor import symbol_map

    return symbol_map.SYMBOLS, symbol_map.FILE_PHASE


# ----------------------------------------------------------------------------- self-test


def identity_entries(tree: Tree):
    """Every legacy statement mapped onto itself (used to validate the checker)."""
    from tests.refactor.symbol_map import Entry

    out = []
    for m in tree.legacy_modules():
        out.append(Entry(m, MODULE_KEY, m, MODULE_KEY, "moved", "3a-i", ""))
        for k, _ in statement_keys(tree.parse(m)):
            out.append(Entry(m, k, m, k, "moved", "3a-i", ""))
    return out


PERTURBATIONS = {
    # a changed constant: AST failure on ramp_to + binding failures in every caller
    "constant": (
        "Experiments/utils.py",
        "def ramp_to(yoko, target, step=0.001, delay=0.01):",
        "def ramp_to(yoko, target, step=0.002, delay=0.01):",
    ),
    # an import-only change re-binding a shadowed name (the star-import hazard):
    # invisible to the AST check, caught by the binding check
    "shadow": (
        "Experiments/mAmplitudeRabiFF.py",
        None,
        f"\nfrom {LEGACY_PREFIX}.Experiments.utils import fit_rabi_cosine  # noqa\n",
    ),
}


def _perturbed_copy(src_root: Path, dst_root: Path, rel: str, old: str | None, new: str):
    shutil.copytree(
        src_root / LEGACY_DIR, dst_root / LEGACY_DIR, ignore=shutil.ignore_patterns("__pycache__")
    )
    p = dst_root / LEGACY_DIR / rel
    text = p.read_text(encoding="utf-8")
    if old is None:
        text += new
    else:
        assert text.count(old) == 1, f"perturbation anchor not unique in {rel}"
        text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")


def self_test(legacy_root: Path, verbose: bool = False) -> int:
    ok = True
    old_tree = Tree("legacy@" + LEGACY_COMMIT, legacy_root)
    entries = identity_entries(old_tree)

    def run(label, new_root):
        chk = Checker(
            entries, Tree("legacy@" + LEGACY_COMMIT, legacy_root), Tree(label, new_root), {}
        )
        findings = chk.run()
        buf = io.StringIO()
        report(findings, verbose, out=buf)
        return findings, buf.getvalue()

    # The legacy files leave the working tree during 3a, so the identity case and the
    # perturbations start from a copy of the legacy worktree, not from the repo.
    tmp = Path(tempfile.mkdtemp(prefix="qicklab_identity_"))
    try:
        shutil.copytree(
            legacy_root / LEGACY_DIR, tmp / LEGACY_DIR, ignore=shutil.ignore_patterns("__pycache__")
        )
        findings, text = run("copy", tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    fails = [f for f in findings if f.status == "FAIL"]
    n_ast = sum(f.check == "ast" and f.status == "OK" for f in findings)
    n_bind = sum(f.check == "binding" and f.status == "OK" for f in findings)
    print(
        f"[identity] legacy@{LEGACY_COMMIT} vs a copy of itself: {len(fails)} failures, {n_ast} AST ok, {n_bind} bindings ok"
    )
    if fails:
        print(text)
        ok = False

    expectations = {
        "constant": lambda fs: (
            any(f.check == "ast" and "utils:ramp_to" in f.where for f in fs)
            and any(f.check == "binding" and "ramp_to" in f.detail for f in fs)
        ),
        "shadow": lambda fs: (
            not any(f.check == "ast" for f in fs)
            and {f.where.split(" ->")[0] for f in fs if f.check == "binding"}
            == {"Experiments.mAmplitudeRabiFF:AmplitudeRabiFF"}
        ),
    }
    for name, (rel, old, new) in PERTURBATIONS.items():
        tmp = Path(tempfile.mkdtemp(prefix=f"qicklab_perturb_{name}_"))
        try:
            _perturbed_copy(legacy_root, tmp, rel, old, new)
            findings, text = run(f"perturbed-{name}", tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        fails = [f for f in findings if f.status == "FAIL"]
        caught = bool(fails) and expectations[name](fails)
        kinds = Counter(f.check for f in fails)
        print(
            f"[perturbed:{name}] {rel}: {len(fails)} failures {dict(kinds)} -> {'caught as expected' if caught else 'NOT CAUGHT CORRECTLY'}"
        )
        if verbose or not caught:
            print(text)
        ok &= caught
    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ----------------------------------------------------------------------------- CLI


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tests.refactor.equivalence", description=__doc__.splitlines()[0]
    )
    ap.add_argument("--phase", choices=("3a-i", "3a-ii", "3b"))
    ap.add_argument(
        "--legacy-root", type=Path, help="existing checkout of the legacy tree (skip the worktree)"
    )
    ap.add_argument(
        "--new-root", type=Path, default=REPO, help="root containing qicklab/ (default: repo)"
    )
    ap.add_argument("--ledger-only", action="store_true")
    ap.add_argument(
        "--static", action="store_true", help="no imports: static binding resolution only"
    )
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", type=Path, help="also write findings as JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    sys.setrecursionlimit(10000)

    with contextlib.ExitStack() as stack:
        legacy = args.legacy_root or stack.enter_context(legacy_worktree())
        if args.self_test:
            return self_test(legacy, args.verbose)
        entries, file_phase = _entries_and_phases()
        chk = Checker(
            entries, Tree("legacy@" + LEGACY_COMMIT, legacy), Tree("new", args.new_root), file_phase
        )
        findings = chk.run(args.phase, args.ledger_only, runtime=not args.static)
        if args.json:
            args.json.write_text(
                json.dumps([f.__dict__ for f in findings], indent=1), encoding="utf-8"
            )
        return report(findings, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
