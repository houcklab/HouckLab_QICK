"""Every module under qicklab imports, and no import touches hardware.

The walk runs in a fresh interpreter (``python -c``), so modules that earlier
tests already imported are executed again here instead of being served from
``sys.modules``. Before anything from qicklab is imported, ``Pyro4.locateNS``,
``Pyro4.Proxy``, ``pyvisa.ResourceManager`` (and Pyro5's ``locate_ns`` /
``Proxy``, used by hardware.sc5510a) are replaced by functions that raise, so an
import that opens a connection fails the test.
"""

import importlib
import importlib.util
import json
import os
import pkgutil
import subprocess
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# module -> the only missing dependency it may fail on (ModuleNotFoundError.name)
ALLOWED_FAILURES = {
    "qicklab.twpa.set_pump": "pywindfreak",  # optional extra [twpa], not installed
    "qicklab.twpa.pump_sweep": "pywindfreak",
    "qicklab.twpa.gain_compare": "pywindfreak",
    "qicklab.hardware.attenuator": "distutils",  # gone on Python 3.12+; phase 3b fixes it
}


class HardwareAccessAtImport(RuntimeError):
    pass


def _forbidden(what):
    def call(*args, **kwargs):
        raise HardwareAccessAtImport(f"{what} called during import")

    return call


def _block_hardware():
    import Pyro4
    import pyvisa

    Pyro4.locateNS = _forbidden("Pyro4.locateNS")
    Pyro4.Proxy = _forbidden("Pyro4.Proxy")
    pyvisa.ResourceManager = _forbidden("pyvisa.ResourceManager")
    try:
        import Pyro5.api
    except ImportError:
        return
    Pyro5.api.locate_ns = _forbidden("Pyro5.api.locate_ns")
    Pyro5.api.Proxy = _forbidden("Pyro5.api.Proxy")


def _import_all():
    """Child-process entry point: import every qicklab module, print a JSON report."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    _block_hardware()
    import qicklab

    report = {}

    def record(name, exc):
        report[name] = {
            "type": type(exc).__name__,
            "missing": getattr(exc, "name", None) if isinstance(exc, ImportError) else None,
            "traceback": "".join(traceback.format_exception(exc)),
        }

    def onerror(name):  # a package whose __init__ fails while walking
        record(name, sys.exc_info()[1])

    names = [m.name for m in pkgutil.walk_packages(qicklab.__path__, "qicklab.", onerror)]
    for name in names:
        try:
            importlib.import_module(name)
        except BaseException as exc:  # noqa: BLE001 - SystemExit at import is a failure too
            record(name, exc)
        else:
            report.setdefault(name, None)
    print(json.dumps(report))


def test_every_qicklab_module_imports_without_hardware():
    proc = subprocess.run(
        [sys.executable, "-c", "from tests.test_imports import _import_all; _import_all()"],
        cwd=REPO,
        env={**os.environ, "MPLBACKEND": "Agg"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report, "pkgutil.walk_packages found no qicklab modules"

    unexpected = {}
    for name, failure in report.items():
        if failure is None:
            continue
        allowed = ALLOWED_FAILURES.get(name)
        if failure["type"] == "ModuleNotFoundError" and failure["missing"] == allowed:
            continue
        unexpected[name] = failure["traceback"]
    assert not unexpected, "\n\n".join(f"{n}:\n{tb}" for n, tb in unexpected.items())


def test_qicklab_init_binds_nothing():
    spec = importlib.util.find_spec("qicklab")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert [n for n in vars(module) if not n.startswith("__")] == []
