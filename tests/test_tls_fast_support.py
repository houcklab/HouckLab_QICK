"""Offline safety contracts retained from the retired diagnostic runners."""
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import tls_fast_support as support

ROOT = Path(__file__).resolve().parents[1]
RUNNERS = ROOT / 'WorkingProjects/TLS_Spectroscopy/Client_modules/Runners'


def test_q3_configuration_is_explicit_and_each_call_is_independent():
    cfg = support.base_config()
    assert (cfg['ff_park_gain'], cfg['qubit_pi_freq'], cfg['read_pulse_freq']) == (
        -25146, 4367.292, 6933.026)
    assert (cfg['sigma'], cfg['qubit_pi_gain'], cfg['reps']) == (.2, 13500, 250)
    assert cfg['opx_feedback_read_timing'] == 'official_wait_all'
    assert cfg['opx_feedback_pre_measure_sync'] is True
    assert cfg['opx_feedback_flush_mode'] == 'off'
    cfg['FF_Qubits']['1']['channel'] = 99
    assert support.base_config()['FF_Qubits']['1']['channel'] == 3


def test_q3_context_restores_original_and_missing_attributes_after_failure():
    previous = {'ff_park_gain': 0, 'qubit_pi_gain': 32000, 'sigma': 2.}
    tls = SimpleNamespace(BaseConfig=previous, QUBIT='q4', SET_YOKO=True,
                          outerFolder='old', FLUX_FIT_PARAMS=[0])
    before = vars(tls).copy()
    with pytest.raises(RuntimeError, match='acquisition failed'):
        with support.q3_context(tls, 'new'):
            assert tls.BaseConfig['ff_park_gain'] == -25146
            assert tls.QUBIT == 'q3' and tls.SET_YOKO is False
            tls.BASELINE_DC_OFFSET = 123
            tls.FLUX_FIT_PARAMS = [1]
            raise RuntimeError('acquisition failed')
    assert vars(tls) == before and tls.BaseConfig is previous


def test_scan_environment_is_restored_even_on_acquisition_failure(monkeypatch):
    original = {
        'Q3_5PT_EXECUTION_TEST': 'passive', 'Q3_5PT_PREDISTORTION': 'off',
        'Q3_5PT_FREQ_MIN_GHZ': '4.13', 'Q3_PROTOCOL_CROSSOVER_PHASE': 'legacy_off',
        'Q3_FLUXPRED_MODE': 'neutral', 'Q3_FLUXPRED_MODEL_JSON': 'old.json',
        'Q3_FLUX_TAIL_GAIN': '0.5', 'UNRELATED_CLEANUP_TEST_VALUE': 'preserved',
    }
    for key, value in original.items():
        monkeypatch.setenv(key, value)
    before = dict(os.environ)
    with pytest.raises(RuntimeError, match='acquisition failed'):
        with support.scan_environment(Path('chosen.json')):
            for key in ('Q3_5PT_EXECUTION_TEST', 'Q3_5PT_PREDISTORTION',
                        'Q3_5PT_FREQ_MIN_GHZ', 'Q3_PROTOCOL_CROSSOVER_PHASE',
                        'Q3_FLUXPRED_MODEL_JSON'):
                assert key not in os.environ
            assert os.environ['Q3_FLUXPRED_MODE'] == 'off'
            assert os.environ['Q3_FLUX_TAIL_GAIN'] == '1.0'
            assert os.environ['Q3_5PT_CORRECTION_JSON'] == 'chosen.json'
            assert os.environ['UNRELATED_CLEANUP_TEST_VALUE'] == 'preserved'
            raise RuntimeError('acquisition failed')
    assert dict(os.environ) == before


def test_pinned_correction_rejects_missing_and_wrong_artifacts(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError, match='correction'):
        support.checked_correction(tmp_path)
    correction = tmp_path / 'correction.json'
    correction.write_bytes(b'abc')
    with pytest.raises(RuntimeError, match='checksum'):
        support.checked_correction(tmp_path, correction)
    monkeypatch.setattr(support, 'CORRECTION_SHA256', hashlib.sha256(b'abc').hexdigest())
    assert support.checked_correction(tmp_path, correction) == correction
    with pytest.raises(FileNotFoundError, match='NAS'):
        support.checked_correction(tmp_path / 'missing', correction)


def test_preflight_rejects_instruction_and_addressed_waveform_memory_overruns():
    program = SimpleNamespace(compile=lambda: [0] * 20,
        soccfg={'tprocs': [{'pmem_size': 32}], 'gens': [{'maxlen': 64}]},
        pulses=[{'w': {'addr': 60, 'data': np.zeros((8, 2))}}], record_words=2)
    with pytest.raises(ValueError, match='waveform'):
        support.preflight(program)
    program.pulses[0]['w']['addr'] = 40
    assert support.preflight(program)['waveform_memory'][0]['used_samples'] == 48
    program.compile = lambda: [0] * 33
    with pytest.raises(ValueError, match='instruction'):
        support.preflight(program)


def test_checkpoint_preserves_qick_scalar_types_and_retries_nas_rename(tmp_path, monkeypatch):
    path = tmp_path / 'manifest.json'
    replace = support.os.replace
    calls = []
    sleeps = []
    def transient_lock(source, target):
        calls.append((source, target))
        if len(calls) < 3:
            raise PermissionError('NAS lock')
        replace(source, target)
    monkeypatch.setattr(support.os, 'replace', transient_lock)
    monkeypatch.setattr(support.time, 'sleep', sleeps.append)
    support.checkpoint(path, dict(cycles=np.int64(344), frequency=np.float64(4030.),
                                 gains=np.array([1, 2]), artifact=path))
    assert json.loads(path.read_text()) == dict(cycles=344, frequency=4030.,
                                              gains=[1, 2], artifact=str(path))
    assert sleeps == [.05, .1] and len(calls) == 3
    assert not path.with_suffix('.pending').exists()


def test_checkpoint_surfaces_persistent_lock_and_leaves_pending_metadata(tmp_path, monkeypatch):
    def locked(*args):
        raise PermissionError('persistent NAS lock')
    sleeps = []
    monkeypatch.setattr(support.os, 'replace', locked)
    monkeypatch.setattr(support.time, 'sleep', sleeps.append)
    path = tmp_path / 'manifest.json'
    with pytest.raises(PermissionError, match='persistent'):
        support.checkpoint(path, {'status': 'interrupted'})
    assert sleeps == [.05, .1, .2, .4, .8, 1., 1.]
    assert json.loads(path.with_suffix('.pending').read_text()) == {'status': 'interrupted'}


class AcquisitionAST(ast.NodeTransformer):
    """Ignore relocated imports and the old delegating checkpoint wrapper."""
    def visit_Import(self, node):
        return None
    def visit_ImportFrom(self, node):
        return None
    def visit_FunctionDef(self, node):
        return None if node.name == 'checkpoint' else self.generic_visit(node)


@pytest.mark.parametrize('name', ['TLSFastLossMap.py', 'TLSFastSinglePointMap.py'])
def test_cleanup_preserves_fast_acquisition_ast_and_default_plan(name):
    manifest = json.loads((ROOT / 'docs/cleanup_2026_10_06.json').read_text())
    tree = AcquisitionAST().visit(ast.parse((RUNNERS / name).read_text()))
    fingerprint = hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
    assert fingerprint == manifest['fast_runner_acquisition_ast_sha256'][name]
    module = importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.' + name[:-3])
    plan = hashlib.sha256(json.dumps(module.plan(), sort_keys=True).encode()).hexdigest()
    assert plan == manifest['fast_runner_default_plan_sha256'][name]


def test_retained_python_has_no_imports_of_retired_experiment_modules():
    manifest = json.loads((ROOT / 'docs/cleanup_2026_10_06.json').read_text())
    retired = {Path(p).stem for p in manifest['deleted_paths']
               if '/Runners/' in p or '/Experiments/' in p}
    # Ignored historical test archives remain user-owned and may reference
    # retired workflows. Check retained tracked files and the new support files.
    tracked = subprocess.check_output(['git', 'ls-files', '-z',
        'WorkingProjects/TLS_Spectroscopy/Client_modules', 'tests'],
        cwd=ROOT, text=True).split('\0')
    paths = {ROOT / name for name in tracked if name.endswith('.py')}
    paths.update((Path(support.__file__), Path(__file__)))
    for path in paths:
        if not path.exists():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert not {a.name.split('.')[-1] for a in node.names} & retired, path
            elif isinstance(node, ast.ImportFrom):
                assert not {a.name for a in node.names} & retired, path
                assert not set((node.module or '').split('.')) & retired, path


@pytest.mark.parametrize('name', ['ThreePointApplesToApples.py', 'FivePointApplesToApples.py'])
def test_protocol_retirement_preserves_non_crossover_runner_ast(name):
    manifest = json.loads((ROOT / 'docs/cleanup_2026_10_06.json').read_text())
    baseline = manifest['followups'][-1]['runner_ast_without_crossover_sha256'][name]
    tree = ast.parse((RUNNERS / name).read_text())
    assert not any(isinstance(node, ast.Name) and 'crossover' in node.id
                   for node in ast.walk(tree))
    tree.body = [node for node in tree.body
                 if not isinstance(node, ast.FunctionDef) or node.name != 'runtime_parameters']
    fingerprint = hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
    assert fingerprint == baseline


@pytest.mark.parametrize('name', ['ThreePointApplesToApples.py', 'FivePointApplesToApples.py'])
@pytest.mark.parametrize('case_index', [0, 1])
def test_protocol_retirement_preserves_normal_runtime_settings_and_overrides(name, case_index):
    manifest = json.loads((ROOT / 'docs/cleanup_2026_10_06.json').read_text())
    followup = manifest['followups'][-1]
    environ = followup['normal_runtime_cases'][case_index]
    baseline = followup['normal_runtime_parameters_sha256'][name][case_index]
    # Execute only pure parameter definitions; do not import hardware clients.
    tree = ast.parse((RUNNERS / name).read_text())
    params_name = ('P6_3PT_APPLES_TO_APPLES' if name.startswith('Three')
                   else 'P6_5PT_APPLES_TO_APPLES')
    nodes = [node for node in tree.body
             if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and
                                                     t.id == params_name for t in node.targets))
             or (isinstance(node, ast.FunctionDef) and
                 node.name in ('apply_series_overrides', 'runtime_parameters'))]
    namespace = {'np': np, 'os': os}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<normal runtime settings>', 'exec'), namespace)
    runtime = namespace['runtime_parameters']
    def fingerprint(params):
        return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    assert fingerprint(runtime(environ)) == baseline
    for obsolete_phase in ('legacy_off', 'current_on', 'invalid'):
        assert fingerprint(runtime(dict(environ, Q3_PROTOCOL_CROSSOVER_PHASE=obsolete_phase))) == baseline
