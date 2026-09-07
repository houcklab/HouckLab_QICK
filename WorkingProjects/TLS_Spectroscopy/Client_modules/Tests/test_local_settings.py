import importlib
from pathlib import Path
import subprocess

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


def test_direct_runner_setting_edit_updates_local_override(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    committed = (
        "P_SCAN = {'run': False, 'shots': 100}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )
    source.write_text(committed)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "add", "Runner.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "Runner.local.py").write_text(
        "P_SCAN = {'run': False, 'shots': 500}\n"
    )
    source.write_text(
        "P_SCAN = {'run': True, 'shots': 100}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )

    loaded = {"P_SCAN": {"run": True, "shots": 100}}
    module.apply_local_overrides(loaded, source, ("P_SCAN",))

    assert loaded == {"P_SCAN": {"run": True, "shots": 500}}
    source.write_text(committed)
    loaded_after_source_is_clean = {"P_SCAN": {"run": False, "shots": 100}}
    module.apply_local_overrides(
        loaded_after_source_is_clean,
        source,
        ("P_SCAN",),
    )
    assert loaded_after_source_is_clean == {
        "P_SCAN": {"run": False, "shots": 500}
    }


def test_committed_runner_setting_edit_updates_existing_local_override(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text(
        "P_SCAN = {'run': False, 'shots': 100}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "add", "Runner.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    local = tmp_path / "Runner.local.py"
    module.snapshot_source_local_overrides(source)
    local.write_text(
        local.read_text().replace("'shots': 100", "'shots': 500", 1)
    )
    source.write_text(
        "P_SCAN = {'run': True, 'shots': 100}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )
    subprocess.run(["git", "add", "Runner.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "enable scan"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    loaded = {"P_SCAN": {"run": True, "shots": 100}}
    module.apply_local_overrides(loaded, source, ("P_SCAN",))

    assert loaded == {"P_SCAN": {"run": True, "shots": 500}}


def test_reverted_runner_setting_does_not_resurface_from_local_override(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text(
        "P_SCAN = {'run': False, 'shots': 100}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )
    module.snapshot_source_local_overrides(source)
    source.write_text(
        "P_SCAN = {'run': True, 'shots': 100}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )
    enabled = {"P_SCAN": {"run": True, "shots": 100}}
    module.apply_local_overrides(enabled, source, ("P_SCAN",))
    assert enabled == {"P_SCAN": {"run": True, "shots": 100}}
    source.write_text(
        "P_SCAN = {'run': False, 'shots': 100}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )

    reverted = {"P_SCAN": {"run": False, "shots": 100}}
    module.apply_local_overrides(reverted, source, ("P_SCAN",))

    assert reverted == {"P_SCAN": {"run": False, "shots": 100}}


def test_removed_runner_setting_is_removed_from_local_override(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text(
        "P_SCAN = {'run': False, 'legacy': 1}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )
    module.snapshot_source_local_overrides(source)
    source.write_text(
        "P_SCAN = {'run': False}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )

    loaded = {"P_SCAN": {"run": False}}
    module.apply_local_overrides(loaded, source, ("P_SCAN",))

    assert loaded == {"P_SCAN": {"run": False}}
    assert "legacy" not in module._read_assignments(
        tmp_path / "Runner.local.py"
    )["P_SCAN"]


def test_removed_top_level_setting_is_pruned_from_local_override(tmp_path):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text(
        "P_SCAN = {'run': False}\n"
        "P_OLD = {'run': True}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN', 'P_OLD')\n"
    )
    module.snapshot_source_local_overrides(source)
    source.write_text(
        "P_SCAN = {'run': False}\n"
        "LOCAL_OVERRIDE_KEYS = ('P_SCAN',)\n"
    )

    loaded = {"P_SCAN": {"run": False}}
    module.apply_local_overrides(loaded, source, ("P_SCAN",))

    assignments = module._read_assignments(tmp_path / "Runner.local.py")
    assert loaded == {"P_SCAN": {"run": False}}
    assert "P_OLD" not in assignments
    assert "P_OLD" not in assignments["_SOURCE_BASELINE"]


def test_local_override_still_loads_when_git_is_unavailable(tmp_path, monkeypatch):
    module = local_settings_module()
    source = tmp_path / "Runner.py"
    source.write_text("")
    (tmp_path / "Runner.local.py").write_text("P_SCAN = {'run': True}\n")
    loaded = {"P_SCAN": {"run": False, "shots": 100}}

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(module.subprocess, "run", unavailable)

    module.apply_local_overrides(loaded, source, ("P_SCAN",))

    assert loaded == {"P_SCAN": {"run": True, "shots": 100}}


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


def test_bootstrap_snapshots_all_runner_surfaces(monkeypatch):
    bootstrap = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.bootstrap_local_settings"
    )
    snapshots = []
    monkeypatch.setattr(
        bootstrap,
        "snapshot_source_local_overrides",
        lambda source: snapshots.append(Path(source)),
    )
    bootstrap.main()

    assert len(snapshots) == 4
    assert snapshots == list(bootstrap.SOURCE_PATHS)
    assert not hasattr(bootstrap, "SCRATCH_SOURCE")
    assert not hasattr(bootstrap, "SCRATCH_TARGET")


def test_local_settings_has_no_temporary_scratch_bootstrap():
    module = local_settings_module()
    assert not hasattr(module, "copy_local_scratch")
