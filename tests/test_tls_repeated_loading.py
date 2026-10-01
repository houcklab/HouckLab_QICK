"""Dose, reset-history and carryover checks for the accumulation experiment."""
import importlib
import numpy as np
import pytest


@pytest.fixture
def m():
    name = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSRepeatedLoading'
    assert importlib.util.find_spec(name), 'repeated loading is not implemented'
    return importlib.import_module(name)


def test_dose_has_equal_visits_and_last_write_time(m):
    for n in (0, 1, 8, 32):
        states = m.write_schedule(n)
        assert len(states) == 32 and sum(states) == n
        if n:
            assert states[-1] == 1
            assert states[:32-n] == [0] * (32-n)
    for bad in (-1, 33, 2.5, float('nan')):
        with pytest.raises(ValueError):
            m.write_schedule(bad)


def test_screen_interleaves_short_long_and_has_detuned_zero_dose(m):
    specs = m.tasks(shots=200)
    assert len(specs) == 128
    assert m.plan()['probe_shots'] == 153600
    for f in {t['frequency_ghz'] for t in specs}:
        for b in (0, 1):
            selected = [t for t in specs if t['frequency_ghz'] == f and t['block'] == b]
            assert {(t['writes'], t['location']) for t in selected} == {
                (n, s) for n in (0, 1, 8, 32) for s in ('on', 'off')}
            assert all(set(t['probes_us']) == {.1, 40.} for t in selected)
    assert m.plan()['automatic_erase'] is False


def test_record_signed_decode_and_incomplete_detection(m):
    words = np.zeros((2, m.RECORD_WORDS), dtype=np.int64)
    words[0, 0] = -123
    words[-1, -1] = -456
    result = m.decode_records(words.astype(np.uint32), 2)
    assert result[0].words[0] == -123 and result[1].words[-1] == -456
    with pytest.raises(ValueError):
        m.decode_records(words.ravel()[:-1])
    with pytest.raises(ValueError):
        m.decode_records(words, 3)


def test_reset_feedback_threshold_handles_both_projection_orientations(m):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    for sign in (1, -1):
        c = ClassifierCalibration(1, 'loop', 0., 0, sign, 0, -5, 5, 100, {})
        assert m.feedback_decision(6 * sign, 0, c)
        assert not m.feedback_decision(5 * sign, 0, c)
        assert not m.feedback_decision(-10 * sign, 0, c)


def synthetic_cell(m, task, *, rise, offset=0., seed=1, poor_reset=False):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    rng = np.random.default_rng(seed)
    n = task['shots']
    w = np.zeros((n, 2, m.RECORD_WORDS), dtype=np.int64)
    # Every fixed reset has four correction readouts plus an independent final one.
    w[:, :, :-2:2] = -100
    if poor_reset:
        w[:, :, -4] = 100
    for j, t in enumerate(task['probes_us']):
        prob = .1 + offset + (rise if t == 40. else 0.)
        w[:, j, -2] = np.where(rng.random(n) < prob, 100, -100)
    cal = ClassifierCalibration(1, 'loop', 0., 0, 1, 0, -20, 0, 100, {})
    axis = dict(theta_rad=0., threshold=0., low=-100., high=100.)
    return m.summarize_program(w.reshape(-1, m.RECORD_WORDS), task, cal, axis)


def test_analysis_removes_starting_population_and_requires_local_accumulation(m):
    def report(kind):
        cells = []
        for i, task in enumerate(t for t in m.tasks(shots=4000) if t['frequency_ghz'] == 4.037):
            n = task['writes']
            rise = (.16 * n/32 if kind == 'return' and task['location'] == 'on' else
                    .16 * n/32 if kind == 'broad' else 0.)
            cells.append(synthetic_cell(m, task, rise=rise, offset=.1*n/32, seed=i))
        return m.analyze(cells, controls_valid=True)
    assert not report('carryover')['candidate_frequencies_ghz']
    assert not report('broad')['candidate_frequencies_ghz']
    assert report('return')['candidate_frequencies_ghz'] == [4.037]


def test_final_reset_failure_is_never_silently_called_ground(m):
    task = m.tasks(shots=200)[0]
    cell = synthetic_cell(m, task, rise=.3, poor_reset=True)
    assert not cell['valid']
    assert all(c['accepted'] == 0 for c in cell['conditions'])
    assert all(c['all_shot_pe'] is not None for c in cell['conditions'])
    assert not m.analyze([cell], controls_valid=True)['candidate_frequencies_ghz']


def test_short_long_covariance_and_count_validation(m):
    task = m.tasks(shots=200)[0]
    cell = synthetic_cell(m, task, rise=.2)
    assert np.shape(cell['covariance']) == (2, 2)
    assert cell['growth'] > .10 and cell['growth_error'] > 0
    with pytest.raises(ValueError, match='incomplete'):
        m.summarize_program(np.zeros((1, m.RECORD_WORDS)), task, None, None)


def test_reset_confidence_gate_uses_calibrated_ground_acceptance(m):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    task = next(t for t in m.tasks(shots=200) if t['writes'] == 32)
    w = np.zeros((200, 2, m.RECORD_WORDS), dtype=np.int64)
    r = w[:, :, :-2].reshape(200, 2, 33, 5, 2)
    r[:, :, :, :, 0] = -10  # ambiguous ground-reference outcomes
    r[:90, :, :, -1, 0] = -100  # 45% confident, as expected for this classifier
    r[:, :, -1, -1, 0] = -100
    w[:, :, -2] = -100
    loop = ClassifierCalibration(1,'loop',0.,0,1,0,-20,0,100,
                                 {'ground_accept':.45,'false_ground_accept':.02})
    axis = dict(theta_rad=0.,threshold=0.,low=-100.,high=100.)
    result = m.summarize_program(w.reshape(-1,m.RECORD_WORDS),task,loop,axis)
    assert result['valid']
    assert result['conditions'][0]['verified_write_fraction'] == pytest.approx(.45)


def test_calibration_keeps_q3_and_uses_fixed_reset_recovery(m):
    cfg = m.calibration_config()
    assert cfg['opx_feedback_syncdelay_us'] == 20.
    assert cfg['opx_loop_recovery_us'] == 20.
    assert cfg['opx_inter_shot_delay_us'] == 1000.
    assert cfg['ff_park_gain'] == -25146 and cfg['qubit_pi_freq'] == 4367.292


def test_reference_validation_respects_conservative_ground_zone(m):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    loop = ClassifierCalibration(1,'loop',0.,0,1,0,-20,0,100,
                                 {'ground_accept':.30,'false_ground_accept':.02})
    g=np.zeros((600,m.RECORD_WORDS),dtype=np.int64)
    g[:,-4]=-10
    g[:180,-4]=-100
    g[:,-2]=-100
    e=g.copy();e[:,-2]=100
    assert m.reference_axis(g,e,loop)['valid']


def test_feedback_arithmetic_overflow_invalidates_cell(m):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    task=m.tasks(shots=200)[0]
    w=np.zeros((400,m.RECORD_WORDS),dtype=np.int64)
    w[:,:-2:2]=-100
    w[:,-2]=-100
    w[0,0]=40000
    loop=ClassifierCalibration(1,'loop',0.,0,1,0,-20,0,100,{})
    axis=dict(theta_rad=0.,threshold=0.,low=-100.,high=100.)
    result=m.summarize_program(w,task,loop,axis)
    assert not result['valid']
    assert result['conditions'][0]['feedback_iq_out_of_range'] == 1


def test_empty_ground_reference_is_reported_without_losing_completed_science(m):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    loop=ClassifierCalibration(1,'loop',0.,0,1,0,-20,0,100,{})
    w=np.zeros((600,m.RECORD_WORDS),dtype=np.int64)
    w[:,-4]=100
    result=m.reference_axis(w,w,loop)
    assert result['valid'] is False and result['axis'] is None
    assert result['ground_acceptance'] == 0


def test_final_reset_acceptance_gate_scales_with_reference(m):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    task = next(t for t in m.tasks(shots=600) if t['writes'] == 32)
    w = np.zeros((600,2,m.RECORD_WORDS),dtype=np.int64)
    r = w[:,:,:-2].reshape(600,2,33,5,2)
    r[:,:,:,:,0] = -10
    r[:120,:,:,-1,0] = -100
    w[:,:,-2] = -100
    loop = ClassifierCalibration(1,'loop',0.,0,1,0,-20,0,100,
                                 {'ground_accept':.20,'false_ground_accept':.01})
    axis = dict(theta_rad=0.,threshold=0.,low=-100.,high=100.)
    cell = m.summarize_program(w.reshape(-1,m.RECORD_WORDS),task,loop,axis)
    assert cell['valid'] and cell['conditions'][0]['accepted'] == 120


def test_pilot_preserves_controls_and_precision_but_reduces_programs(m, capsys):
    assert m.main(['--plan', '--pilot']) == 0
    import json
    p=json.loads(capsys.readouterr().out)
    assert p['mode'] == 'pilot'
    assert p['doses'] == [0,32]
    assert p['science_programs'] == 24 and p['probe_shots'] == 28800
    specs=m.tasks(pilot=True)
    assert {t['frequency_ghz'] for t in specs} == {4.026,4.037,4.046}
    for f in (4.026,4.037,4.046):
        for b in (0,1):
            selected=[t for t in specs if t['frequency_ghz']==f and t['block']==b]
            assert {(t['writes'],t['location']) for t in selected} == {
                (n,s) for n in (0,32) for s in ('on','off')}
            assert all(t['shots']==600 and set(t['probes_us'])=={.1,40.} for t in selected)
    assert m.plan()['science_programs'] == 128


def test_pilot_flags_return_for_followup_without_claiming_dose_dependence(m):
    cells=[]
    for i,task in enumerate(t for t in m.tasks(shots=4000,pilot=True) if t['frequency_ghz']==4.037):
        rise=.25 if task['writes']==32 and task['location']=='on' else 0.
        cells.append(synthetic_cell(m,task,rise=rise,seed=i))
    report=m.analyze(cells,controls_valid=True,pilot=True)
    assert report['pilot_followup_frequencies_ghz'] == [4.037]
    assert report['candidate_frequencies_ghz'] == []
    assert not report['dose_dependence_tested']
    assert report['automatic_full_run'] is False
    assert not m.analyze(cells[:4],controls_valid=True,pilot=True)['pilot_followup_frequencies_ghz']
    assert not m.analyze(cells,controls_valid=False,pilot=True)['pilot_followup_frequencies_ghz']
