import sys
from pathlib import Path

# The code under test imports itself (qicklab.*, tests.*) from the repo root.
REPO = str(Path(__file__).resolve().parents[1])
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def _twpa_state_sandbox_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("twpa_state_sandbox")


@pytest.fixture(autouse=True)
def _twpa_state_log_sandbox(monkeypatch, _twpa_state_sandbox_dir):
    """No test may append to the real TWPA state log (qicklab.twpa.common.TWPA_STATE_DIR).

    Any test that runs a qicklab.twpa main() (set_bias, flux_sweep, ...) would otherwise write a
    made-up line to the lab's provenance record whenever the data drive is mapped. Tests that read
    the log redirect it again to their own tmp_path."""
    monkeypatch.setattr("qicklab.twpa.common.TWPA_STATE_DIR", str(_twpa_state_sandbox_dir))
