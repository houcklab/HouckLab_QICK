from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.initialize_propagation_q3 import (
    diagnose_layers,
    extract_literal_config,
)


def test_extract_literal_config_reads_values_without_importing_module(tmp_path):
    path = Path(tmp_path) / "initialize.py"
    path.write_text(
        "FF_CH = 3\n"
        "BaseConfig = {\n"
        "    'ff_ch': FF_CH,\n"
        "    'qubit_gain': 15500,\n"
        "    'qubit_pi_gain': 15500,\n"
        "    'sigma': 0.2,\n"
        "}\n"
    )

    values = extract_literal_config(
        path,
        ("qubit_gain", "qubit_pi_gain", "sigma"),
    )

    assert values == {
        "qubit_gain": 15500,
        "qubit_pi_gain": 15500,
        "sigma": 0.2,
    }


def test_diagnose_layers_detects_source_import_mismatch():
    source = {"qubit_gain": 15500, "qubit_pi_gain": 15500}
    imported = {"qubit_gain": 11100, "qubit_pi_gain": 11100}
    runner = {"qubit_gain": 11100, "qubit_pi_gain": 11100}

    assert diagnose_layers(source, imported, runner) == "source_import_mismatch"


def test_diagnose_layers_detects_runner_override():
    source = {"qubit_gain": 15500, "qubit_pi_gain": 15500}
    imported = dict(source)
    runner = {"qubit_gain": 11100, "qubit_pi_gain": 15500}

    assert diagnose_layers(source, imported, runner) == "runner_override_mismatch"


def test_diagnose_layers_explains_pi_gain_precedence():
    source = {"qubit_gain": 15500, "qubit_pi_gain": 11100}
    imported = dict(source)
    runner = {"qubit_gain": 11100, "qubit_pi_gain": 11100}

    assert diagnose_layers(source, imported, runner) == "qubit_pi_gain_controls_sscal"


def test_diagnose_layers_reports_complete_propagation():
    values = {"qubit_gain": 15500, "qubit_pi_gain": 15500}

    assert diagnose_layers(values, values, values) == "propagation_ok"
