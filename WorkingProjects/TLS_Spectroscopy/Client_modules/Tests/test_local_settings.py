import importlib
from pathlib import Path

import pytest


MODULE_NAME = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.local_settings"
)


def local_settings_module():
    return importlib.import_module(MODULE_NAME)


def test_local_overrides_merge_dicts_and_replace_scalars(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text("")
    (tmp_path / "Runner.local.py").write_text(
        "RESET_MODE = 'active'\n"
        "P_SCAN = {'run': True, 'nested': {'points': 41}}\n"
    )
    namespace = {
        "RESET_MODE": "passive",
        "P_SCAN": {"run": False, "shots": 100, "nested": {"span": 2}},
    }

    observed = module.apply_local_overrides(
        namespace,
        source,
        ("RESET_MODE", "P_SCAN"),
    )

    assert observed == tmp_path / "Runner.local.py"
    assert namespace == {
        "RESET_MODE": "active",
        "P_SCAN": {
            "run": True,
            "shots": 100,
            "nested": {"span": 2, "points": 41},
        },
    }


def test_local_overrides_reject_unknown_or_executable_statements(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text("")
    local = tmp_path / "Runner.local.py"
    local.write_text("P_SCNA = {'run': True}\n")
    with pytest.raises(ValueError, match="P_SCNA"):
        module.apply_local_overrides({}, source, ("P_SCAN",))

    local.write_text("import os\nP_SCAN = {'run': True}\n")
    with pytest.raises(ValueError, match="literal assignments"):
        module.apply_local_overrides(
            {"P_SCAN": {"run": False}},
            source,
            ("P_SCAN",),
        )


def test_snapshot_creates_local_file_without_overwriting_it(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text("")
    namespace = {
        "RESET_MODE": "active",
        "P_SCAN": {"run": True, "shots": 100},
    }

    target = module.snapshot_local_overrides(
        namespace,
        source,
        ("RESET_MODE", "P_SCAN"),
    )
    first = target.read_text()
    namespace["RESET_MODE"] = "passive"
    module.snapshot_local_overrides(
        namespace,
        source,
        ("RESET_MODE", "P_SCAN"),
    )

    assert target == tmp_path / "Runner.local.py"
    assert target.read_text() == first
    loaded = {"RESET_MODE": "passive", "P_SCAN": {"run": False}}
    module.apply_local_overrides(
        loaded,
        source,
        ("RESET_MODE", "P_SCAN"),
    )
    assert loaded == namespace | {"RESET_MODE": "active"}


def test_copy_local_scratch_preserves_existing_local_file(tmp_path):
    module = local_settings_module()
    source = tmp_path / "test.py"
    source.write_text("first\n")

    target = module.copy_local_scratch(source)
    source.write_text("second\n")
    module.copy_local_scratch(source)

    assert target == tmp_path / "test.local.py"
    assert target.read_text() == "first\n"


def test_copy_local_scratch_accepts_an_explicit_target(tmp_path):
    module = local_settings_module()
    source = tmp_path / "named_script.py"
    target = tmp_path / "test.local.py"
    source.write_text("payload\n")

    observed = module.copy_local_scratch(source, target)

    assert observed == target
    assert target.read_text() == "payload\n"


def test_snapshot_source_extracts_allowed_settings_without_importing_module(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text(
        "CHANNEL = 3\n"
        "P_SCAN = {'channel': CHANNEL, 'run': True}\n"
        "LOCAL_OVERRIDE_KEYS = ('CHANNEL', 'P_SCAN')\n"
        "raise RuntimeError('must not execute')\n"
    )

    target = module.snapshot_source_local_overrides(source)

    namespace = {"CHANNEL": 0, "P_SCAN": {"run": False}}
    module.apply_local_overrides(
        namespace,
        source,
        ("CHANNEL", "P_SCAN"),
    )
    assert target == tmp_path / "Runner.local.py"
    assert namespace == {"CHANNEL": 3, "P_SCAN": {"run": True, "channel": 3}}


def test_local_python_files_are_ignored_by_git():
    root = Path(__file__).parents[4]
    patterns = (root / ".gitignore").read_text().splitlines()
    assert "WorkingProjects/TLS_Spectroscopy/Client_modules/**/*.local.py" in patterns


def test_bootstrap_snapshots_all_surfaces_and_copies_scratch(monkeypatch, tmp_path):
    bootstrap = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.bootstrap_local_settings"
    )
    snapshots = []
    scratches = []
    monkeypatch.setattr(
        bootstrap,
        "snapshot_source_local_overrides",
        lambda source: snapshots.append(Path(source)),
    )
    monkeypatch.setattr(
        bootstrap,
        "copy_local_scratch",
        lambda source, target: scratches.append((Path(source), Path(target))),
    )

    bootstrap.main()

    assert len(snapshots) == 4
    assert snapshots == list(bootstrap.SOURCE_PATHS)
    assert bootstrap.SCRATCH_SOURCE.name == "transmission_timing_q3.py"
    assert bootstrap.SCRATCH_TARGET.name == "test.local.py"
    assert scratches == [(bootstrap.SCRATCH_SOURCE, bootstrap.SCRATCH_TARGET)]


def test_tracked_test_script_launches_ignored_local_scratch():
    client_root = Path(__file__).parents[1]
    source = (client_root / "active_reset_OPX" / "test.py").read_text()
    assert "test.local.py" in source
    assert "runpy.run_path" in source
