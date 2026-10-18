"""The agent guides and the top-level README point at things that exist.

CLAUDE.md (Claude Code) and AGENTS.md (Codex) are one text: only their first line differs. Every
repo path quoted in backticks in them or in README.md must exist, as must every relative link
target in README.md and docs/README.md, and docs/README.md must link every top-level docs page.
Quoted paths may carry placeholders (`devices/<NAME>.py`) or globs; they must match a file.
Inside fenced code blocks (the copy-paste commands and the layout tree) every token that starts
with a top-level directory (`qicklab/...`, `tests/...`) is checked too, and the README's Python
quick-start snippet is executed as a dry run.
"""

import ast
import re
from pathlib import Path

import pytest
import pyvisa

from qicklab.core import context as context_module

REPO = Path(__file__).resolve().parents[1]
GUIDES = ("CLAUDE.md", "AGENTS.md", "README.md")
SUFFIXES = (".py", ".md", ".json", ".toml", ".txt")
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
TOP_DIRS = ("qicklab", "devices", "runners", "scripts", "tests", "docs")


def _text(name):
    return (REPO / name).read_text(encoding="utf-8")


def _outside_fences(text):
    """The text with fenced code blocks removed (their contents are commands and trees)."""
    return re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.S | re.M)


def _fences(text):
    """The fenced code blocks, as (info string, body) pairs."""
    return re.findall(r"^```([^\n]*)\n(.*?)^```[^\n]*$", text, flags=re.S | re.M)


def _quoted(text):
    return re.findall(r"`([^`\n]+)`", _outside_fences(text))


def _fenced_paths(text):
    """Repo-relative path tokens inside code fences (`tests/test_x.py`, `scripts/gen_docs.py`)."""
    top = "|".join(TOP_DIRS)
    pattern = rf"(?<![\w./\\-])((?:{top})/[\w./<>*-]*)"
    return [m.rstrip(".") for _, body in _fences(text) for m in re.findall(pattern, body)]


def _is_path(token):
    if not re.fullmatch(r"[\w./<>*-]+", token) or token.startswith(".") or "//" in token:
        return False
    return "/" in token or token.endswith(SUFFIXES)


def _repo_files():
    out = []
    for path in REPO.rglob("*"):
        rel = path.relative_to(REPO)
        if not SKIP_DIRS.intersection(rel.parts):
            out.append(rel)
    return out


def _exists(token):
    pattern = re.sub(r"<[^>]+>", "*", token.rstrip("/"))
    if "/" not in token:  # a bare file name: it must exist somewhere in the repo
        return any(rel.match(pattern) for rel in _repo_files())
    if "*" in pattern:
        return any(REPO.glob(pattern))
    return (REPO / pattern).exists()


def test_claude_and_agents_identical_below_first_line():
    claude, agents = _text("CLAUDE.md").splitlines(), _text("AGENTS.md").splitlines()
    assert "Claude" in claude[0] and "Codex" in agents[0]
    assert claude[1:] == agents[1:], "edit CLAUDE.md and AGENTS.md together (only line 1 differs)"


@pytest.mark.parametrize("name", GUIDES)
def test_quoted_paths_exist(name):
    paths = [t for t in _quoted(_text(name)) if _is_path(t)]
    assert paths, f"{name}: no quoted paths found (has the quoting style changed?)"
    missing = sorted({t for t in paths if not _exists(t)})
    assert not missing, f"{name} quotes paths that do not exist: {missing}"


@pytest.mark.parametrize("name", GUIDES)
def test_fenced_paths_exist(name):
    paths = _fenced_paths(_text(name))
    assert paths, f"{name}: no paths found in its code blocks (has the layout changed?)"
    missing = sorted({t for t in paths if not _exists(t)})
    assert not missing, f"{name} code blocks name paths that do not exist: {missing}"


@pytest.mark.parametrize("name", GUIDES)
def test_quoted_qicklab_modules_exist(name):
    """`qicklab.core.io.record_calibration`: the longest module prefix of the dotted name is a
    module file, and the next part (if any) is a top-level name defined in that module."""
    dotted = [t for t in _quoted(_text(name)) if re.fullmatch(r"qicklab(\.\w+)+", t)]
    missing = [token for token in dotted if not _resolves(token)]
    assert not missing, f"{name} names modules or attributes that do not exist: {missing}"


def test_dotted_name_check_rejects_misspellings():
    assert _resolves("qicklab.core.io.record_calibration")
    assert not _resolves("qicklab.core.readuot.cover_readout_window")
    assert not _resolves("qicklab.core.io.record_calibratoin")


def _module_file(dotted):
    base = REPO.joinpath(*dotted.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return path
    return None


def _resolves(token):
    parts = token.split(".")
    for n in range(len(parts), 0, -1):
        path = _module_file(".".join(parts[:n]))
        if path is not None:
            break
    else:
        return False
    if n == len(parts):
        return True
    return parts[n] in _top_level_names(path)


def _top_level_names(path):
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def test_readme_quick_start_dry_run(monkeypatch, tmp_path):
    """The README's Python snippet runs as pasted: a dry run that touches no hardware."""
    (snippet,) = [body for info, body in _fences(_text("README.md")) if info.strip() == "python"]
    tree = ast.parse(snippet)
    last = tree.body[-1]
    assert isinstance(last, ast.Expr), "the snippet should end with the run(...) call"
    tree.body[-1] = ast.Assign(targets=[ast.Name("report", ast.Store())], value=last.value)
    ast.fix_missing_locations(tree)

    def refuse(*args, **kwargs):
        raise AssertionError("the README dry run touched the real hardware factory")

    monkeypatch.setattr(context_module, "makeProxy", refuse)
    monkeypatch.setattr(pyvisa, "ResourceManager", refuse)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    scope = {}
    exec(compile(tree, "README.md", "exec"), scope)
    report = scope["report"]
    assert report and all(e["status"] == "ok" and e["programs"] > 0 for e in report), report


@pytest.mark.parametrize("name", ["README.md", "docs/README.md"])
def test_relative_links_resolve(name):
    page = REPO / name
    targets = re.findall(r"\]\(([^)\s]+)\)", _outside_fences(page.read_text(encoding="utf-8")))
    local = [t.split("#")[0] for t in targets if not re.match(r"[a-z]+:", t)]
    missing = sorted({t for t in local if t and not (page.parent / t).exists()})
    assert not missing, f"{name} links to missing files: {missing}"


def test_docs_index_lists_every_top_level_page():
    index = _text("docs/README.md")
    pages = sorted(p.relative_to(REPO / "docs").as_posix() for p in (REPO / "docs").glob("*.md"))
    pages += sorted(
        p.relative_to(REPO / "docs").as_posix() for p in (REPO / "docs" / "concepts").glob("*.md")
    )
    pages.append("experiments/README.md")
    unlisted = [p for p in pages if p != "README.md" and f"]({p}" not in index]
    assert not unlisted, f"docs/README.md does not link: {unlisted}"
