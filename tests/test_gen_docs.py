"""scripts/gen_docs.py: the committed docs/parameters.md and step-page tables are its output.

Run `python scripts/gen_docs.py` after changing qicklab/core/params.py, a recipe, a group or
the device model; these tests fail until the generated files are committed again.
"""

import importlib.util
import re
import warnings
from pathlib import Path

import pytest

from qicklab.core import params as P
from qicklab.runs import STEPS

REPO = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO / "docs" / "experiments"


def _load():
    spec = importlib.util.spec_from_file_location("gen_docs", REPO / "scripts" / "gen_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load()
OUTPUTS = gen.outputs()


@pytest.mark.parametrize(
    "path",
    sorted(OUTPUTS, key=lambda p: p.as_posix()),
    ids=lambda p: p.relative_to(REPO).as_posix(),
)
def test_committed_output_is_current(path):
    current, generated = OUTPUTS[path]
    assert current == generated, (
        f"{path.relative_to(REPO).as_posix()} is out of date: run python scripts/gen_docs.py"
    )


def test_generator_is_deterministic_and_idempotent():
    assert gen.render_parameters() == gen.render_parameters()
    for page, steps in gen.pages().items():
        once = gen.render_page((EXPERIMENTS / f"{page}.md").read_text(encoding="utf-8"), steps)
        assert gen.render_page(once, steps) == once, page


def test_every_step_is_on_exactly_one_page():
    placed = [step for steps in gen.pages().values() for step in steps]
    assert sorted(placed) == sorted(STEPS)
    assert set(gen.PAGE_OF) <= set(STEPS)


def test_markers_are_on_the_step_pages_only():
    step_pages = set(gen.pages())
    for path in sorted(EXPERIMENTS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if path.stem in step_pages:
            assert text.count(gen.BEGIN) == text.count(gen.END) == 1, path.name
            assert text.index(gen.BEGIN) < text.index(gen.END), path.name
        else:
            assert gen.BEGIN not in text and gen.END not in text, path.name


def test_each_page_block_has_every_recipe_keyword_of_its_steps():
    for page, steps in gen.pages().items():
        text = (EXPERIMENTS / f"{page}.md").read_text(encoding="utf-8")
        block = text.split(gen.BEGIN)[1].split(gen.END)[0]
        for step in steps:
            assert f"`R.{step}(...)`" in block, (page, step)
            for p in P.entries("recipe", f"recipe:{step}"):
                assert f"| `{p.key}` |" in block, (page, step, p.key)


def test_parameters_md_covers_the_registry():
    text = gen.render_parameters()
    for p in P.PARAMS.values():
        shown = p.key.split(".", 1)[1] if p.scope == "device" else p.key
        assert f"| `{shown}` |" in text, (p.key, p.scope)
    for step in STEPS:
        assert f"\n### R.{step}\n" in text, step


def test_knobs_table_is_about_twenty_registered_rows():
    assert 15 <= len(gen.KNOBS) <= 25
    for _label, scope, key in gen.KNOBS:
        assert (key, scope) in P.PARAMS, (key, scope)


def test_page_links_point_at_existing_anchors():
    text = gen.render_parameters()
    slugs = gen.parameters_anchors()
    for step in STEPS:
        assert f"r{step}" in slugs, step
    for anchor in re.findall(r"\]\(#([\w-]+)\)", text):
        assert anchor in slugs, anchor


_SUMMARY = re.compile(r"^Recipe: `R\.(\w+)\(\.\.\.\)`.*?, session groups (.+?) \(\[shared groups\]")


def _blocks_by_step(text):
    """{step: (groups on its summary line, the text of its table)} of a rendered block."""
    out, step = {}, None
    for line in text.split("\n"):
        m = _SUMMARY.match(line)
        if m:
            step = m.group(1)
            listed = [] if m.group(2) == "none" else re.findall(r"`(\w+)`", m.group(2))
            out[step] = (listed, [])
        elif step and line.startswith("| "):
            out[step][1].append(line)
        elif line.startswith("### ") or line == gen.END:
            step = None
    return {s: (groups, "\n".join(rows)) for s, (groups, rows) in out.items()}


def test_summary_groups_cover_every_group_a_step_reads():
    """The 'session groups' list names every group the step's rows, run function or regime use."""
    from qicklab.core.session import GROUPS

    blocks = _blocks_by_step(gen.render_parameters())
    for page, steps in gen.pages().items():
        text = (EXPERIMENTS / f"{page}.md").read_text(encoding="utf-8")
        page_blocks = _blocks_by_step(text.split(gen.BEGIN)[1])
        for step in steps:
            assert page_blocks[step][0] == blocks[step][0], (page, step)
    assert set(blocks) == set(STEPS)
    for step, (listed, rows) in blocks.items():
        assert set(listed) <= set(GROUPS), (step, listed)
        # every "(<group> group" default cell and every "the <group> group's" note
        named = set(re.findall(r"\((\w+) group", rows)) | set(
            re.findall(r"the (\w+) group's", rows)
        )
        assert named <= set(listed), (step, sorted(named - set(listed)))
        s = STEPS[step]()
        assert {g for g in s.needs if g in GROUPS} <= set(listed), step
        for group in GROUPS:
            readers = {r for p in P.entries("session", f"session:{group}") for r in p.read_by}
            if s.fn.__name__ in readers:
                assert group in listed, (step, group)
        if s.regime == "B":
            assert "single_shot" in listed, step


def test_summary_groups_pinned_cases():
    """Steps that read groups through the config rather than a Step slot (review finding)."""
    blocks = _blocks_by_step(gen.render_parameters())
    assert blocks["charge_transmission_sweep"][0] == ["transmission", "charge"]
    assert blocks["constant_two_tone"][0] == ["tones"]
    assert blocks["charge_sweep"][0] == ["spec", "charge"]
    assert blocks["undriven_single_shot"][0] == ["single_shot"]
    assert blocks["amplitude_rabi"][0] == []


# lint of the hand-written pages (python scripts/gen_docs.py --lint) -------------------------

LINT_ERRORS, LINT_WARNINGS = gen.lint_docs()


def test_hand_written_pages_use_registered_parameter_names():
    """Every keyword of an R./G./Session/device-class call the pages show, and every name in the
    first column of a parameter table, is registered (on a step page, or a legacy key mapped to a
    keyword); every name in a keyword column is a keyword (a legacy key only as an alias)."""
    assert not LINT_ERRORS, "\n".join(LINT_ERRORS)


def test_cfg_names_on_the_pages_lint():
    """Report (warn, never fail) backticked cfg keys the code uses but the registry lacks."""
    if LINT_WARNINGS:
        warnings.warn("\n".join(["docs lint:", *LINT_WARNINGS]), stacklevel=1)


def test_hand_written_links_into_parameters_md_are_linted():
    """The lint resolves the pages' parameters.md#<anchor> links (a heading rename in
    render_parameters() fails test_hand_written_pages_use_registered_parameter_names); this pins
    that the links it guards are really there."""
    linked = {
        (p.relative_to(REPO / "docs").as_posix(), a)
        for p in gen.lint_pages()
        for a in gen._PARAMS_LINK.findall(gen.hand_written(p.read_text(encoding="utf-8")))
    }
    assert {
        ("experiments/README.md", "knobs-you-change-every-session"),
        ("running_a_session.md", "session"),
        ("running_a_session.md", "step-recipes"),
        ("glossary.md", "step-recipes"),
        ("troubleshooting.md", "step-recipes"),
        ("experiments/twpa.md", "twpasetup"),
    } <= linked
    assert {a for _, a in linked} <= gen.parameters_anchors()


def test_lint_pages_are_the_hand_written_ones():
    rel = {p.relative_to(REPO / "docs").as_posix() for p in gen.lint_pages()}
    assert "parameters.md" not in rel
    assert {"README.md", "glossary.md", "experiments/t1.md", "concepts/config_regimes.md"} <= rel
    assert "devices/CSTQ03.md" in rel


# Refactor-plan language (design-time phases, "target API", "not present yet") belongs in
# docs/dev/, not on the user pages. Physics phases ("phase 0", "phase 90 deg", "phase 3.0008 pi")
# and the timing-verify "phase 1/2" in architecture.md / modified_ramsey.md are not refactor
# phases: only phases 5-9 (the refactor's later phases), the 5a/5b/6a/6b slice names and the
# explicit refactor wording match.
_PLAN_LANGUAGE = re.compile(
    r"refactor phase|\bphase[ -][5-9][ab]?\b(?![.\d]*\s*(?:deg|°|π|pi\b))|\b[56][ab]\b"
    r"|\bdesign v\d\b|\btarget (?:API|layout)\b|not present yet",
    re.IGNORECASE,
)


def test_user_pages_have_no_refactor_plan_language():
    hits = [
        f"{p.relative_to(REPO / 'docs').as_posix()}:{i}: {m.group()!r}"
        for p in gen.lint_pages()
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        for m in _PLAN_LANGUAGE.finditer(line)
    ]
    assert not hits, "refactor-plan language on a user page (move it to docs/dev/):\n" + "\n".join(
        hits
    )


@pytest.mark.parametrize(
    "line, flagged",
    [
        ("Parameter tables (refactor phase 6; not present yet).", True),
        ("The recipes arrive in phase 6.", True),
        ("added in 5a, removed in 5b", True),
        ("this is the target API of design v3", True),
        ("closing phase 90 deg; pi pulse at phase 0", False),
        ("realised phase 3.0008 pi; phase 5.2 pi", False),
        ("timing verify phase 1 passed (42/42); phase 2 was not run", False),
    ],
)
def test_plan_language_pattern(line, flagged):
    assert bool(_PLAN_LANGUAGE.search(line)) is flagged


def test_doc_only_names_are_unregistered_and_used():
    registered = {p.key for p in P.PARAMS.values()}
    text = "\n".join(p.read_text(encoding="utf-8") for p in gen.lint_pages())
    for name, why in gen.DOC_ONLY.items():
        assert name not in registered, name
        assert f"`{name}`" in text, name
        assert why, name


_PLANTED = """\
R.t1(relax_dely=5000) and `R.t1(...)`
`R.no_such_step()`, `G.resolve(spec)`
`Session(DEVICE, coherence=G.coherence(t1_stepp=5), qubit_pulse=2)`
`Qubit(freqq=1.0)`

| Key | Default | Units | Meaning |
|---|---|---|---|
| `bogus_key` / `t1_step` | 1 | us | x |
| `T1_step` (legacy `nonsense_in_parens`) | 5 | us | x |
| `parity.f_upper_mhz` | 1 | MHz | x |

| Key | Content |
|---|---|
| `some_output` | x |

```python
R.t2_echo(
    t2_max_us=20,   # wait = 5 T2 (comment)
)
```
`thermal_tail_md2_threshold` and `x_cfg_only`
[a](../parameters.md#no-such-heading), [b](parameters.md#step-recipes)
"""


def test_lint_flags_planted_mistakes():
    errors, warns = gen.lint_text(_PLANTED, cfg_keys={"x_cfg_only": ["qicklab/x.py"]})
    assert errors == [
        (1, "R.t1(relax_dely=...): not a registered keyword"),
        (2, "R.no_such_step(...): no such recipe or group builder"),
        (3, "G.coherence(t1_stepp=...): not a registered keyword"),
        (4, "Qubit(freqq=...): not a registered keyword"),
        (8, "parameter table names `bogus_key`: not in the registry"),
        (22, "parameters.md#no-such-heading: no such heading in parameters.md"),
    ]
    assert warns == [(21, "`x_cfg_only`: a cfg key (qicklab/x.py) the registry lacks")]


def test_lint_skips_the_generated_block():
    page = "\n".join(["# x", gen.BEGIN, "R.t1(not_a_keyword=1)", gen.END, "R.t1(relax_dely=1)"])
    assert gen.hand_written(page).count("\n") == page.count("\n")
    errors, _ = gen.lint_text(page, cfg_keys={})
    assert errors == [(5, "R.t1(relax_dely=...): not a registered keyword")]


_KEYWORD_TABLES = """\
| Keyword | Default | Units |
|---|---|---|
| `Shots` | 1 | shots |
| `SpecSpan` | 10 | MHz |
| `shots` (`Shots` in the legacy `SS_params`) | 1 | shots |
| `repeat`, legacy `Repeat` | 1 | 1 |
| `parity_spec.SpecSpan` | 1.0 | MHz |
| `parity_spec.Shots` | 1 | shots |

| knob | `spec` group key | CSTQ03 value |
|---|---|---|
| span | `SpecSpan` | 10 |
| span | `spec_span` (cfg `SpecSpan`) | 10 |
| drive | `Qubit.gain`, `gauss` | x |

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `T1_step` | 5 | us | a legacy table |
"""


def test_lint_keyword_columns_take_keywords_only():
    """A column headed Keyword or "<x> group key" holds what a Session / recipe user types: a
    legacy or cfg key there counts only in parentheses or after the word "legacy"."""
    errors, _ = gen.lint_text(_KEYWORD_TABLES, cfg_keys={})
    miss = "not a keyword (a legacy or cfg key only as an alias)"
    assert errors == [
        (3, f"parameter table names `Shots`: {miss}"),
        (4, f"parameter table names `SpecSpan`: {miss}"),
        (8, f"parameter table names `parity_spec.Shots`: {miss}"),
        (
            12,
            "parameter table names `SpecSpan`: not a keyword of session:spec ("
            "a legacy or cfg key only as an alias)",
        ),
    ]


_SCOPED_TABLES = """| knob | `spec` group key | CSTQ03 value |
|---|---|---|
| span | `t1_step` | 10 |
| span | the legacy `SpecSpan` | 10 |
| drive | `gain`, `Qubit.freq` | 800 |

| step | group | CSTQ03 session values | notes |
|---|---|---|---|
| `t1` | `coherence` | `t1_step` 5 us, `T1_step` | `anything_goes` |
| `t2_echo` | `echo` | `t2_max_us` 20, `t1_step` 1 | |
| `t2_ramsey` | `coherence` | `f_virt_mhz` None, `freq_shift` 0 | |

| Step | Keywords | Value |
|---|---|---|
| `auto_coherence` | `ss_voltage_min`; `voltage_min` | 0 |

<!-- lint-keywords: recipe:auto_coherence -->
`auto_coherence` settings: `t2e_max_us` 500, `T2E_max_us` (legacy `T2E_max_us`),
`t2_max_us` 20.

`t2_max_us` outside the marked paragraph is not checked.
<!-- lint-keywords: recipe:no_such_step -->
"""


def test_lint_keyword_columns_are_scoped():
    """A "`<group>` group key" column takes that group's keywords; a keyword column of a table
    with a step / group column takes the keywords of the recipe / group of its row; a cell that
    names only an alias fails; a "lint-keywords" marker scopes the next paragraph."""
    errors, _ = gen.lint_text(_SCOPED_TABLES, cfg_keys={})
    alias = "(a legacy or cfg key only as an alias)"
    assert errors == [
        (3, f"parameter table names `t1_step`: not a keyword of session:spec {alias}"),
        (4, "keyword cell names only an alias, no keyword"),
        (
            9,
            f"parameter table names `T1_step`: not a keyword of recipe:t1 / session:coherence "
            f"{alias}",
        ),
        (
            10,
            f"parameter table names `t1_step`: not a keyword of recipe:t2_echo / session:echo "
            f"{alias}",
        ),
        (
            15,
            f"parameter table names `voltage_min`: not a keyword of recipe:auto_coherence {alias}",
        ),
        (18, "`T2E_max_us`: not a keyword of recipe:auto_coherence"),
        (19, "`t2_max_us`: not a keyword of recipe:auto_coherence"),
        (22, "lint-keywords: no such registry scope recipe:no_such_step"),
    ]


def test_lint_user_pages_take_legacy_keys_only_as_aliases():
    """Outside docs/experiments/ (legacy=False) a bare legacy key in a parameter table's first
    column fails too; the step pages' legacy Parameters tables keep it."""
    errors, _ = gen.lint_text(_KEYWORD_TABLES, cfg_keys={}, legacy=False)
    assert (
        18,
        "parameter table names `T1_step`: not in the registry (a legacy key only as an alias)",
    ) in errors
    assert all(n != 18 for n, _ in gen.lint_text(_KEYWORD_TABLES, cfg_keys={})[0])


@pytest.mark.parametrize(
    "page, now, legacy_form",
    [
        ("bringup_workflow.md", "| span | `spec_span` (cfg `SpecSpan`) |", "| span | `SpecSpan` |"),
        (
            "concepts/averaging.md",
            "| `repeat` (`Repeat` in the legacy `US_params`) |",
            "| `Repeat` |",
        ),
        (
            "concepts/averaging.md",
            "| `shots` (`Shots` in the legacy `SS_params`) |",
            "| `Shots` (in recipes) |",
        ),
        ("bringup_workflow.md", "| span | `spec_span` (cfg `SpecSpan`) |", "| span | `t1_step` |"),
        ("bringup_workflow.md", "| `t1_step` 5 us x 100 points", "| `T1_step` 5 us x 100 points"),
        ("bringup_workflow.md", "`t2e_max_us` 500", "`T2E_max_us` 500"),
        ("bringup_workflow.md", "`repetitions` in the `coherence`", "`Repeat` in the `coherence`"),
        (
            "running_a_session.md",
            "| `ss_voltage_min`, `ss_voltage_max`; `spec_gain` |",
            "| `voltage_min`, `ss_voltage_max`; `spec_gain` |",
        ),
    ],
)
def test_lint_guards_the_real_tables(page, now, legacy_form):
    """The tables and paragraphs of the review findings (bring-up spec and coherence tables and
    auto_coherence / repetitions paragraphs, averaging counts table, library-value table) are
    linted as keyword / user-page text: a legacy key, or a keyword of another scope, fails."""
    path = REPO / "docs" / page
    text = path.read_text(encoding="utf-8")
    assert now in text
    legacy = path.parent == EXPERIMENTS
    assert not gen.lint_text(text, cfg_keys={}, legacy=legacy)[0]
    assert gen.lint_text(text.replace(now, legacy_form), cfg_keys={}, legacy=legacy)[0]
