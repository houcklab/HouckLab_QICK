"""Shared fixtures.

Run everything:            python -m pytest Bob/tests
Skip the GUI tests:        python -m pytest Bob/tests -m "not gui"

GUI tests need pytest-qt and run without a screen (offscreen Qt). They write Bob's
settings to a temporary folder, never to your real ones.
"""
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))          # the folder that contains Bob/
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Bob.blocks.registry import make_block  # noqa: E402
from Bob.config.calibration import CalibrationStore  # noqa: E402
from Bob.config.station import Station  # noqa: E402
from Bob.core.params import Value  # noqa: E402
from Bob.core.sequence import Sequence  # noqa: E402

FIXTURE_CALIB = HERE / "fixtures" / "qubit_parameters.json"


def pytest_configure(config):
    config.addinivalue_line("markers", "gui: needs PyQt5 + pytest-qt (runs offscreen)")


@pytest.fixture(scope="session")
def station():
    return Station.load("8QV1")


@pytest.fixture(scope="session")
def calib():
    return CalibrationStore.load(FIXTURE_CALIB)


@pytest.fixture
def fresh_station():
    """A station copy a test may modify."""
    st = Station.load("8QV1")
    st.data = dict(st.data)
    return st


@pytest.fixture
def basic_seq():
    """FF hold (0.4 us) with a pi pulse on Q3, then Measure."""
    s = Sequence()
    h = make_block("FFHold")
    h.set_field("duration_us", Value(0.4))
    s.insert_segment(h)
    p = make_block("PiPulse")
    p.set_field("qubit", Value(3))
    s.add_pulse(p, h.id)
    s.set_measure(make_block("Measure"))
    return s


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Send Bob's GUI settings to a temp .ini file and preload the fixture calibration."""
    from Bob.Bob_GUI.app_settings import ENV_VAR, app_settings
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "bob_settings.ini"))
    s = app_settings()
    s.setValue("calibration_path", str(FIXTURE_CALIB))
    s.sync()
    return s
