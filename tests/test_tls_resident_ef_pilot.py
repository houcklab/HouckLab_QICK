import importlib
import json
import hashlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ef = importlib.import_module(
    'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSResidentEFPilot')


def references(mapped=True, seed=9):
    rng = np.random.default_rng(seed)
    # f decays to e during return: identity cannot distinguish e and f.
    levels = {'identity': {'g': 0., 'e': 1., 'f': 1.},
              'ge_swap': {'g': 1., 'e': 0. if mapped else 1., 'f': 1.}}
    return {v: {s: m + rng.normal(0, .1, 800) + 1j*rng.normal(0, .1, 800)
                for s, m in states.items()} for v, states in levels.items()}


def test_ge_only_mapping_recovers_f_after_f_to_e_return():
    refs = references()
    response = ef.fit_response(refs)
    observed = {v: sum(p*np.mean(refs[v][s]) for p, s in zip((.2, .3, .5), 'gef'))
                + np.zeros(800, dtype=complex) for v in refs}
    result = ef.population(response, observed)
    assert [result[s] for s in 'gef'] == pytest.approx([.2, .3, .5], abs=.005)


def test_failed_ge_map_does_not_manufacture_f_population():
    with pytest.raises(ValueError, match='response|separation'):
        ef.fit_response(references(mapped=False))


def test_population_is_unconstrained_so_bad_data_remain_visible():
    refs = references()
    response = ef.fit_response(refs)
    observed = {v: sum(p*np.mean(refs[v][s]) for p, s in zip((-.2, .1, 1.1), 'gef'))
                + np.zeros(800, dtype=complex) for v in refs}
    assert ef.population(response, observed)['g'] < 0


def test_gain_fit_identifies_first_pi_instead_of_noisy_global_maximum():
    gains = np.arange(0, 30001, 2500)
    y = .13 + .6*np.sin(np.pi*gains/(2*11500))**2
    fit = ef.fit_gain(gains, y)
    assert fit['pi_gain'] == pytest.approx(11500, abs=100)
    with pytest.raises(ValueError, match='Rabi'):
        ef.fit_gain(gains, np.full(len(gains), .2))


def test_schedule_preserves_zero_gain_slots_and_maps_before_return():
    task = dict(state='f', view='ge_swap', dwell_us=8., late=False,
                ge_mhz=4210., ge_gain=13000, ef_mhz=4030., ef_gain=11000)
    early = ef.pulse_schedule(task, pulse_cycles=344, guard_cycles=5,
                              dwell_cycles=3441)
    late = ef.pulse_schedule(dict(task, late=True), pulse_cycles=344,
                             guard_cycles=5, dwell_cycles=3441,
                             short_cycles=108)
    assert [x['gain'] for x in early] == [13000, 11000, 0, 13000]
    assert early[-1]['start_cycles'] == late[-1]['start_cycles']
    assert late[0]['start_cycles'] == 3441-108
    assert early[2]['start_cycles']+349+3441 == early[-1]['start_cycles']


def test_no_extrapolated_frequency_can_count_as_local_alignment():
    assert ef.alignment(4030., 4210., 4026.)['aligned'] is False
    assert ef.alignment(4030., 4210., 4030.5)['aligned'] is True
    with pytest.raises(ValueError):
        ef.alignment(4030., 4210., 4200.)


def test_reference_drift_is_rejected_on_independent_data():
    refs = references()
    response = ef.fit_response(refs)
    assert ef.validate_response(response, refs)['valid']
    changed = {v: {s: x+.3 for s, x in states.items()} for v, states in refs.items()}
    assert not ef.validate_response(response, changed)['valid']


def test_science_off_the_response_plane_cannot_be_reported_as_valid():
    refs = references()
    pre = {d: refs for d in ef.DWELLS_US}
    science = {(b, s, d): {v: refs[v][s].copy() for v in ef.VIEWS}
               for b in range(2) for s in 'gef' for d in ef.DWELLS_US}
    for v in ef.VIEWS:
        science[0, 'f', 8.][v] += 10j
    summary = ef.summarize_decay(pre, pre, science, draws=20)
    assert not summary['valid']
    assert any(not row['valid'] for row in summary['science_consistency'])


def test_boundary_bootstrap_reports_uncertainty_instead_of_throwing():
    rng = np.random.default_rng(2)
    means = {'identity': {'g': 0., 'e': 1., 'f': 1.},
             'ge_swap': {'g': 1., 'e': 0., 'f': .38}}
    refs = {v: {s: m+rng.normal(0, .3, 500)+1j*rng.normal(0, .3, 500)
                for s, m in states.items()} for v, states in means.items()}
    ef.fit_response(refs)
    pre = {d: refs for d in ef.DWELLS_US}
    science = {(b, s, d): {v: refs[v][s] for v in ef.VIEWS}
               for b in range(2) for s in 'gef' for d in ef.DWELLS_US}
    summary = ef.summarize_decay(pre, pre, science, draws=100)
    assert not summary['valid']
    assert summary['bootstrap_unstable_fraction'] > .05


def test_decoder_preserves_transferred_records_for_keyboard_interrupt():
    program = ef.ResidentEFProgram.__new__(ef.ResidentEFProgram)
    program.transferred_records = []
    program.decode_dmem_records(np.zeros(6, dtype=np.uint32), expected_records=3)
    program.decode_dmem_records(np.zeros(4, dtype=np.uint32), expected_records=2)
    assert len(program.transferred_records) == 5


def test_checkpoint_handles_actual_qick_scalar_types(tmp_path):
    path = tmp_path/'manifest.json'
    ef.checkpoint(path, dict(cycles=np.int64(344), frequency=np.float64(4030.), gains=np.array([1, 2])))
    assert json.loads(path.read_text()) == dict(cycles=344, frequency=4030., gains=[1, 2])


@pytest.fixture
def hardware_workflow(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import integration
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners
    def install(tls):
        tls.FLUX_FIT_PARAMS = [-1, 2, 3, 4, 5, 6]
        tls.BaseConfig.update(dt_pulseplay=.5, dt_pulsedef=.002)
    five = SimpleNamespace(install_scan_calibration=install)
    three = SimpleNamespace()
    for name, module in [('FivePointApplesToApples', five), ('ThreePointApplesToApples', three)]:
        monkeypatch.setitem(sys.modules, 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.'+name, module)
        monkeypatch.setattr(Runners, name, module, raising=False)
    tls_name = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy'
    tls = SimpleNamespace(BaseConfig={'ff_park_gain': 0}, QUBIT='q4', SET_YOKO=False,
                          outerFolder='q4', FLUX_FIT_PARAMS=[], _load_correction=lambda *_: {})
    soc = object()
    tls.makeProxy = lambda: (soc, SimpleNamespace(get_cfg=lambda: {'version': 'mock'}))
    monkeypatch.setitem(sys.modules, tls_name, tls)
    monkeypatch.setattr(Runners, 'TLSSpectroscopy', tls, raising=False)
    monkeypatch.setattr(ef.localizer, 'checked_correction', lambda *_: tmp_path/'correction.json')
    monkeypatch.setattr(ef.localizer, 'run', lambda **_: 'mock_scout.csv')
    monkeypatch.setattr(ef.dual, 'read_scout', lambda _: [])
    monkeypatch.setattr(ef.dual, 'select_eligible_feature', lambda *_, **__: dict(center_ghz=4.03, ef_bias_ghz=4.21))
    gains_called = []
    def grid(parameters, frequencies, _tls):
        gains_called.append(float(frequencies[0]))
        assert max(frequencies) < 4.35  # Never invert the park reference.
        return np.array([-18000]), frequencies
    monkeypatch.setattr(three, '_integer_dc_grid', grid, raising=False)
    monkeypatch.setattr(ef.noise, 'preflight', lambda _: {'instructions': 450})
    monkeypatch.setattr(ef.diagonal, 'abort_and_record', lambda *_: None)
    class Program:
        def __init__(self, board, cfg, *_):
            self.cfg = cfg
            self.transferred_records = []
    monkeypatch.setattr(ef, 'ResidentEFProgram', Program)
    rng = np.random.default_rng(79)
    calls = []
    def acquire(_soc, program, *_args, total_shots, **_kwargs):
        cfg, t = program.cfg, program.cfg['ef_task']
        calls.append(cfg)
        if cfg['ef_park_reference']:
            assert cfg['ff_gain'] == -25146
            mean = 0 if t['state'] == 'g' else 1000
        elif t.get('cal_transition'):
            transition = t['cal_transition']
            frequency = cfg['ef_bias_ghz']*1000+(1.5 if transition == 'ge' else -179.5)
            pi_gain = 13500 if transition == 'ge' else 11250
            response = np.sin(np.pi*t['drive_gain']*(2 if t.get('turns') == 2 else 1)/(2*pi_gain))**2
            response *= np.exp(-((t['drive_mhz']-frequency)/1.5)**2)
            mean = 600*response
            if transition == 'ef' and t['state'] == 'g':
                mean = 1000
        else:
            means = {'identity': {'g': 0, 'e': 1000, 'f': 1000},
                     'ge_swap': {'g': 1000, 'e': 0, 'f': 1000}}
            mean = means[t['view']][t['state']]
        return [SimpleNamespace(i=int(mean+rng.normal(0, 50)), q=int(rng.normal(0, 50))) for _ in range(total_shots)]
    monkeypatch.setattr(integration, '_run_program', acquire)
    return tmp_path, tls, calls, gains_called, integration, acquire


def test_full_workflow_uses_explicit_q3_then_restores_q4_and_saves_raw(hardware_workflow):
    root, tls, calls, grids, _, _ = hardware_workflow
    folder = ef.run(data_root=root, progress=False)
    manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['status'] == 'complete', manifest.get('error')
    assert tls.QUBIT == 'q4'
    assert tls.BaseConfig == {'ff_park_gain': 0}
    assert all(c['qubit_pi_freq'] == 4367.292 and c['read_pulse_freq'] == 6933.026 for c in calls)
    assert len(calls) == 220  # 2 park + 146 calibration + 72 references/science.
    assert len(manifest['completed']) == len(list(folder.glob('*.npz'))) == len(calls)
    assert manifest['calibrations'][1]['ground_control']['valid']


def test_interrupt_retains_transferred_bank_and_partial_manifest(hardware_workflow, monkeypatch):
    root, tls, calls, grids, integration, acquire = hardware_workflow
    def interrupted(soc, program, *args, **kwargs):
        if len(calls) == 3:
            program.transferred_records = [SimpleNamespace(i=19, q=-2)]*12
            raise KeyboardInterrupt()
        return acquire(soc, program, *args, **kwargs)
    monkeypatch.setattr(integration, '_run_program', interrupted)
    with pytest.raises(KeyboardInterrupt):
        ef.run(data_root=root, progress=False)
    folder = next((root/'q3').iterdir())
    manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['status'] == 'interrupted'
    assert len(manifest['completed']) == 3
    partial = next(folder.glob('*.partial.npz'))
    with np.load(partial) as saved:
        assert len(saved['i']) == 12
    assert tls.QUBIT == 'q4'


def install_fixed_source(root, monkeypatch):
    source = root/'q3/q3_2026_10_04/q3_23_24_09_TLS_Resident_EF_Pilot_Scout_T1_5pt_vs_wall_clock_full.csv'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b'fixed calibration source\n')
    monkeypatch.setattr(ef, 'FIXED_SCOUT_SHA256', hashlib.sha256(source.read_bytes()).hexdigest())
    return source


def test_fixed_check_skips_scout_selection_recenter_and_decay(hardware_workflow, monkeypatch):
    root, tls, calls, grids, _, _ = hardware_workflow
    install_fixed_source(root, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail('fixed calibration check must not scan, select or summarize decay')
    monkeypatch.setattr(ef.localizer, 'run', forbidden)
    monkeypatch.setattr(ef.dual, 'select_eligible_feature', forbidden)
    monkeypatch.setattr(ef, 'summarize_decay', forbidden)
    folder = ef.run(data_root=root, progress=False, fixed_check=True)
    manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['status'] == 'complete_calibration_passed', manifest.get('error')
    assert manifest['target_bias_ghz'] == 4.272
    assert set(grids) == {4.272}
    assert len(manifest['calibrations']) == 2  # Exactly one local GE/EF calibration.
    assert all(not name.startswith('b') for name in manifest['completed'])
    assert manifest['summary']['readout_valid']
    assert manifest['summary']['quiet_control_valid']
    assert tls.QUBIT == 'q4'


def test_fixed_source_is_verified_before_touching_hardware(hardware_workflow, monkeypatch):
    root, tls, calls, grids, _, _ = hardware_workflow
    source = install_fixed_source(root, monkeypatch)
    source.write_bytes(b'wrong scout')
    with pytest.raises(ValueError, match='scout.*checksum'):
        ef.run(data_root=root, progress=False, fixed_check=True)
    assert not calls


def test_fixed_check_does_not_treat_strong_ge_decay_as_quiet():
    refs = references()
    pre = {d: refs for d in (.25, 8.)}
    observations = {}
    for s in 'ge':
        p = (.8, .2, 0) if s == 'e' else (1., 0., 0.)
        observations[s] = {v: sum(weight*np.mean(refs[v][state]) for weight, state in zip(p, 'gef'))
                           + np.zeros(800, dtype=complex) for v in ef.VIEWS}
    result = ef.assess_fixed_check(pre, pre, observations, draws=100)
    assert result['readout_valid']
    assert not result['quiet_control_valid']
    assert not result['valid']


def test_fixed_check_rejects_unphysical_control_outside_population_simplex():
    refs = references()
    pre = {d: refs for d in (.25, 8.)}
    observations = {s: {v: np.full(800, np.mean(refs[v][s]), dtype=complex) for v in ef.VIEWS} for s in 'ge'}
    for v in ef.VIEWS:
        observations['e'][v] = 1.4*np.mean(refs[v]['e'])-.4*np.mean(refs[v]['g'])+np.zeros(800, dtype=complex)
    result = ef.assess_fixed_check(pre, pre, observations, draws=100)
    assert not result['valid']


@pytest.mark.parametrize('dwell', ef.DWELLS_US)
def test_native_flux_tail_is_preserved_across_late_and_early_mapping(dwell, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import PulseFunctions
    monkeypatch.setattr(PulseFunctions, 'ff_maxv', lambda *_args, **_kwargs: 32766)
    class Recorder:
        def __init__(self, late, view):
            self.cfg = dict(qubit_ch=1, ff_ch=3, ff_park_gain=-25146, ff_gain=-18000, sigma=.2,
                            ef_task=dict(state='f', view=view, late=late, dwell_us=dwell,
                                         ge_mhz=4210., ef_mhz=4030., ge_gain=13000, ef_gain=11000))
            self._t1_ff_compensation = dict(segment_edges_ns=[0, 30000, 32000, 34000, 40000, 80000],
                                          multipliers=[1.03, 1.02, 1.01, 1., 1., 1.])
            self._t1_ff_settle_us = .5
            self._t1_ff_predistortion_recovery_us = 40.
            self.time = 0
            self.ends = {1: 0, 3: 0}
            self.registers, self.pulses, self.waits = {}, [], []
        def us2cycles(self, value, gen_ch=None):
            return round(value*430.08)
        def cycles2us(self, value, gen_ch=None):
            return value/430.08
        def freq2reg(self, value, gen_ch=None):
            return value
        def deg2reg(self, value, gen_ch=None):
            return value
        def set_pulse_registers(self, **registers):
            self.registers[registers['ch']] = registers
        def pulse(self, ch, t='auto'):
            row = dict(self.registers[ch])
            row['length'] = row.get('length', 4*self.us2cycles(.2))
            start = self.ends[ch] if t == 'auto' else t
            self.pulses.append(dict(row, start=self.time+start))
            self.ends[ch] = start+row['length']
        def sync_all(self, value):
            self.waits.append(value)
            self.time += max(self.ends.values())+value
            self.ends = {1: 0, 3: 0}
    played = []
    for late, view in ((False, 'identity'), (False, 'ge_swap'), (True, 'ge_swap')):
        p = Recorder(late, view)
        ef.ResidentEFProgram._resident_excursion(p)
        assert p.waits == [0, 0, 0]
        microwave = [x for x in p.pulses if x['ch'] == 1]
        assert len(microwave) == 4
        timing = p.cfg['ef_timing']
        assert timing['mapping_end_cycles'] < timing['return_start_cycles']
        assert [x['gain'] for x in microwave] == [13000, 11000, 0, 13000 if view == 'ge_swap' else 0]
        played.append(([x for x in p.pulses if x['ch'] == 3], microwave[-1]['start'], p.time))
    assert played[0] == played[1] == played[2]
