r"""MkDocs hooks of the documentation website (mkdocs.yml `hooks:`). Build-time only.

1. `on_files`: publish docs/README.md (the reading path, which GitHub shows for the docs/ folder)
   as reading-path.html. MkDocs would otherwise drop it as a second index next to docs/index.md.
2. `on_page_markdown`: a link that leaves docs/ (`../README.md`, `../tests/regression/README.md`)
   has no page on the site; point it at the file on GitHub instead. Also render GitHub's `\<`
   escape as `<`.
3. `on_page_content`: an inline code span that names a repo file (`qicklab/core/session.py`) or a
   qicklab module or attribute (`qicklab.core.io.record_calibration`) becomes a link to that
   source on GitHub, at the definition's line for an attribute. Nothing is imported: names are
   resolved from the files with `ast`, so the build needs neither qick nor numpy.
"""

from __future__ import annotations

import ast
import functools
import posixpath
import re
from pathlib import Path

from mkdocs.structure.files import File, InclusionLevel
from mkdocs.utils import get_relative_url

REPO = Path(__file__).resolve().parents[1]
READING_PATH = "README.md"
TOP_DIRS = ("qicklab", "devices", "runners", "scripts", "tests", "docs", "archive")

_FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1[^\n]*$", re.S | re.M)
_MD_LINK = re.compile(r"(\]\()([^)\s]+)(\))")
_INLINE_CODE = re.compile(r"(`+[^`\n]*?`+)")
# skip what must not get a nested link: existing links, code blocks, headings (and their TOC)
_CODE = re.compile(
    r"(<a\b.*?</a>|<pre\b.*?</pre>|<h[1-6]\b.*?</h[1-6]>)|<code>([^<&]+)</code>", re.S
)
_PATH = re.compile(rf"(?:{'|'.join(TOP_DIRS)})(?:/[\w.-]+)+/?")
_DOTTED = re.compile(r"qicklab(?:\.\w+)+")


def _source_url(config, rel, line=None, tree=False):
    ref = config["extra"].get("source_ref", "main")
    url = f"{config['repo_url'].rstrip('/')}/{'tree' if tree else 'blob'}/{ref}/{rel}"
    return f"{url}#L{line}" if line else url


# 1. the reading path -------------------------------------------------------------------------


def on_files(files, config):
    if (
        files.get_file_from_path(READING_PATH) is None
        and (Path(config["docs_dir"]) / READING_PATH).is_file()
    ):
        dest = "reading-path/index.html" if config["use_directory_urls"] else "reading-path.html"
        files.append(
            File(
                READING_PATH,
                config["docs_dir"],
                config["site_dir"],
                config["use_directory_urls"],
                dest_uri=dest,
                inclusion=InclusionLevel.INCLUDED,
            )
        )
    return files


def on_nav(nav, config, files):
    """A README.md is a section's overview page only when it is the section's first entry
    (experiments/README.md). Material otherwise takes any README of a section as its overview
    and drops it from the list, as it would the reading path and the refactor review page."""

    def walk(items):
        for i, item in enumerate(items):
            if item.is_section:
                walk(item.children)
            elif item.is_page and i > 0 and item.is_index:
                item.file.name = posixpath.splitext(posixpath.basename(item.file.src_uri))[0]

    walk(nav.items)
    return nav


# 2. links that leave docs/ -------------------------------------------------------------------


def _outside_fences(markdown, fn):
    out, pos = [], 0
    for m in _FENCE.finditer(markdown):
        out += [fn(markdown[pos : m.start()]), m.group(0)]
        pos = m.end()
    return "".join([*out, fn(markdown[pos:])])


def on_page_markdown(markdown, page, config, files):
    docs = Path(config["docs_dir"]).resolve()
    here = (docs / page.file.src_uri).parent

    def fix(m):
        target = m.group(2)
        if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
            return m.group(0)
        path, _, anchor = target.partition("#")
        full = (here / path).resolve()
        if not full.exists() or (full.is_file() and full.is_relative_to(docs)):
            return m.group(0)  # a page of the site, or broken: MkDocs reports it
        if full.is_dir() and full.is_relative_to(docs):
            return m.group(0)
        if not full.is_relative_to(REPO):
            return m.group(0)
        rel = full.relative_to(REPO).as_posix()
        url = _source_url(config, rel, tree=full.is_dir())
        return m.group(1) + url + (f"#{anchor}" if anchor else "") + m.group(3)

    def prose(text):
        # GitHub reads `\<` as an escaped `<` (the generated tables write `\<= 1`); Python-Markdown
        # does not and would print the backslash. Outside inline code only, as on GitHub.
        parts = _INLINE_CODE.split(text)
        for i in range(0, len(parts), 2):
            parts[i] = _MD_LINK.sub(fix, parts[i]).replace("\\<", "&lt;").replace("\\>", "&gt;")
        return "".join(parts)

    return _outside_fences(markdown, prose)


# 3. code spans that name source --------------------------------------------------------------


@functools.cache
def _definitions(path):
    """{name: line} of a module's top-level definitions, plus {Class.method: line}."""
    names = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names[node.name] = node.lineno
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names[f"{node.name}.{item.name}"] = item.lineno
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for n in ast.walk(target):
                    if isinstance(n, ast.Name):
                        names.setdefault(n.id, node.lineno)
    return names


@functools.cache
def _resolve_dotted(dotted):
    """(repo-relative path, line or None, is_dir) for `qicklab.a.b[.attr[.method]]`, else None."""
    parts = dotted.split(".")
    for n in range(len(parts), 0, -1):
        base = REPO.joinpath(*parts[:n])
        module = base.with_suffix(".py")
        package = base / "__init__.py"
        rest = parts[n:]
        if module.is_file() or package.is_file():
            path = module if module.is_file() else package
            if not rest:
                if module.is_file():
                    return module.relative_to(REPO).as_posix(), None, False
                return base.relative_to(REPO).as_posix(), None, True
            if len(rest) > 2:
                return None
            line = _definitions(path).get(".".join(rest))
            return (path.relative_to(REPO).as_posix(), line, False) if line else None
    return None


def _resolve_path(token, page, files):
    """(url relative to the page, or a repo path for GitHub, is_dir) for a repo path token."""
    rel = token.rstrip("/")
    full = REPO / rel
    if not full.exists():
        return None
    if rel.startswith("docs/") and full.suffix == ".md":
        doc = files.get_file_from_path(rel[len("docs/") :])
        if doc is not None:
            return get_relative_url(doc.url, page.url), True
    return rel, False


def on_page_content(html, page, config, files):
    def link(m):
        if m.group(1) is not None:
            return m.group(0)
        token = m.group(2)
        if _PATH.fullmatch(token):
            found = _resolve_path(token, page, files)
            if found is None:
                return m.group(0)
            target, on_site = found
            if on_site:
                return f'<a href="{target}"><code>{token}</code></a>'
            url = _source_url(config, target, tree=(REPO / target).is_dir())
        elif _DOTTED.fullmatch(token):
            found = _resolve_dotted(token)
            if found is None:
                return m.group(0)
            rel, line, is_dir = found
            url = _source_url(config, rel, line, tree=is_dir)
        else:
            return m.group(0)
        title = f"Source on GitHub ({config['extra'].get('source_ref', 'main')})"
        return f'<a class="qk-src" href="{url}" title="{title}"><code>{token}</code></a>'

    return _CODE.sub(link, html)
