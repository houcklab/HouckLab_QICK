"""The documentation website (mkdocs.yml) builds cleanly, and its hooks do what they promise.

The build runs in strict mode with MkDocs' validation on: a page under docs/ missing from the nav,
a link to a missing page or a missing heading anchor fails. Skipped when the website requirements
(requirements-docs.txt) are not installed.
"""

import importlib.util
import re
from pathlib import Path

import pytest

pytest.importorskip("material", reason="pip install -r requirements-docs.txt")

from mkdocs.commands.build import build  # noqa: E402
from mkdocs.config import load_config  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    config = load_config(str(REPO / "mkdocs.yml"), strict=True, site_dir=str(out))
    build(config)
    return out


def _hooks():
    spec = importlib.util.spec_from_file_location("site_hooks", REPO / "site_src" / "hooks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_site_builds_strict(site):
    assert (site / "index.html").is_file()
    assert (site / "getting_started.html").is_file()


def test_reading_path_is_published(site):
    """docs/README.md would be dropped as a second index; the hook publishes it."""
    page = (site / "reading-path.html").read_text(encoding="utf-8")
    assert "Reading path" in page


def test_readmes_listed_later_in_a_section_stay_in_the_sidebar(site):
    """Only a section's first entry is its overview page; a README listed later keeps its own
    sidebar entry (the reading path, the refactor review findings)."""
    page = (site / "getting_started.html").read_text(encoding="utf-8")
    assert re.search(r'<a href="reading-path\.html" class="md-nav__link[^"]*">\s*<span', page)
    handoff = (site / "dev" / "refactor-2026-10" / "HANDOFF.html").read_text(encoding="utf-8")
    assert re.search(r'<a href="review/index\.html" class="md-nav__link[^"]*">\s*<span', handoff)
    experiments = (site / "experiments" / "t1.html").read_text(encoding="utf-8")
    assert "Experiments" in experiments  # the section overview is still experiments/README.md


def test_links_out_of_docs_point_at_github(site):
    page = (site / "running_a_session.html").read_text(encoding="utf-8")
    assert (
        "https://github.com/houcklab/HouckLab_QICK/blob/bfc_code/tests/regression/README.md" in page
    )


def test_github_angle_escapes_render_as_on_github(site):
    page = (site / "experiments" / "t1.html").read_text(encoding="utf-8")
    assert "repetitions &lt;= 1" in page and "\\&lt;" not in page and "\\<" not in page


def test_code_names_link_to_source(site):
    page = (site / "running_a_session.html").read_text(encoding="utf-8")
    source_link = r'<a class="qk-src" href="([^"]+)"[^>]*><code>([^<]+)</code>'
    by_name = {name: url for url, name in re.findall(source_link, page)}
    assert by_name["qicklab/core/session.py"].endswith("/blob/bfc_code/qicklab/core/session.py")
    assert re.search(r"/qicklab/core/io\.py#L\d+$", by_name["qicklab.core.io.record_calibration"])


def test_dotted_names_resolve_without_imports():
    hooks = _hooks()
    assert hooks._resolve_dotted("qicklab.core.session") == ("qicklab/core/session.py", None, False)
    path, line, _ = hooks._resolve_dotted("qicklab.core.io.record_calibration")
    assert path == "qicklab/core/io.py" and line > 0
    assert hooks._resolve_dotted("qicklab.core.io.no_such_name") is None
    assert hooks._resolve_dotted("qicklab.analysis")[2] is True  # a package: a folder link


def test_every_abbreviation_is_used():
    """A hover definition nobody sees is dead weight; one per line, `*[TERM]: meaning`."""
    terms = re.findall(
        r"^\*\[([^\]]+)\]: \S", (REPO / "site_src" / "abbreviations.md").read_text("utf-8"), re.M
    )
    text = "\n".join(p.read_text(encoding="utf-8") for p in (REPO / "docs").rglob("*.md"))
    assert terms
    unused = [t for t in terms if not re.search(rf"(?<![\w`]){re.escape(t)}(?![\w`])", text)]
    assert not unused, unused
