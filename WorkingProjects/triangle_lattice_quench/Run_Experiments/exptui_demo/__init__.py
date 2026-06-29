"""ExptUI_demo — first-pass experiment-config UI.

Three files:
  * spec.py    : ``ExperimentSpec`` frozen dataclass + validation helpers.
  * codegen.py : ``generate_script(spec) -> str`` + ``validate_against_json``.
  * tab.py     : Qt widget ``ExptUITab`` (imported only when Qt is available).

The split keeps ``spec`` and ``codegen`` Qt-free so they're testable with pure
pytest.

The deliverable that lands on disk is a runnable Python script in the style of
``Run_Experiments/beamsplitter_clean_timing.py`` (BSClean_Correlations branch).
"""

from .spec import ExperimentSpec  # re-export for convenience
from .codegen import generate_script, validate_against_json

__all__ = ["ExperimentSpec", "generate_script", "validate_against_json"]
