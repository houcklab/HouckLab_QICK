"""One-bias q3 e-f pilot with LOCAL preparation and mapping before flux return.

Two IQ views (identity and a local g-e pi) distinguish preparation-relative
g/e/f populations even when f relaxes during the 40-us park return. Neither
absolute f purity nor TLS identity is inferred from this pilot alone.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid

import numpy as np

from . import TLSDualTransitionLoss as dual
from . import TLSPumpProbeResidentDrive as resident
from . import TLSPumpProbeLocalizer as localizer
from . import TLSPumpProbeWidePassiveScan as wide
from . import TLSControlledNoise as noise
from . import TLSAfterglowDiagonal as diagonal
from .TLSEchoRefocusProgram import _flux_events
from ..Helpers import ff_pulse
from ..active_reset_OPX.programs import OPXResetT1Program, _pulse_pi_and_align

VIEWS = ('identity', 'ge_swap')
DWELLS_US = (.25, 2., 8.)
CAL_SHOTS, SHOTS = 160, 500
FIXED_SCOUT_RELATIVE = 'q3/q3_2026_10_04/q3_23_24_09_TLS_Resident_EF_Pilot_Scout_T1_5pt_vs_wall_clock_full.csv'
FIXED_SCOUT_SHA256 = '0c0ed0c6b3ec6a8d559bd503e2a2a1243951fe2d31e95bc51abd4f762b96cf13'
FIXED_BIAS_GHZ = 4.272
FIXED_FEATURE_GHZ = 4.092


def checkpoint(path, payload):
    def encode(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(f'unsupported metadata type {type(value).__name__}')
    dual.checkpoint(path, json.loads(json.dumps(payload, default=encode)))


def plan(*, fixed_check=False):
    if fixed_check:
        return dict(qubit='q3', scout='reuse checksum-verified October4 scout; no new scout or site selection',
                    fixed_bias_ghz=FIXED_BIAS_GHZ, old_feature_ghz=FIXED_FEATURE_GHZ,
                    calibration='one local g-e and e-f spectroscopy/Rabi calibration with independent pulse and readout audits',
                    maximum_alignment_attempts=1, automatic_recenter=False,
                    views=list(VIEWS), reference_dwells_us=[.25, 8.],
                    check='independent g/e/f response references and ground/excited 8-us controls only',
                    science_decay=False, automatic_long_scan=False, shots_per_check=SHOTS,
                    reset='1000 us passive park washout', programs=176,
                    approximate_minutes='5--10 including transport and NAS overhead',
                    interpretation='Local preparation/readout feasibility. The old scout does not establish that the TLS is still at its previous frequency.')
    return dict(qubit='q3', scout='one 3.8--4.3 GHz passive five-point scan',
                selection='loss line with a quiet shifted g-e window',
                calibration='local g-e and e-f opposed spectroscopy, Rabi gains, independent 0/pi/2pi checks',
                maximum_alignment_attempts=2, views=list(VIEWS), dwells_us=list(DWELLS_US),
                shots_per_science_arm=SHOTS, science_passes=2,
                mapping='g-e pi AT TARGET before full corrected 40-us return',
                references='late-prepared g/e/f at each dwell, before and after science',
                reset='1000 us passive park washout', approximate_minutes='8--15; up to 20 if one recenter is needed',
                interpretation='preparation-relative f survival at one bias; a resolved line-versus-flank profile is still needed for TLS attribution',
                automatic_long_scan=False)


def _vector(blocks):
    means = [complex(np.mean(blocks[v])) for v in VIEWS]
    return np.array([z for m in means for z in (m.real, m.imag)])


def _covariance(blocks):
    covariance = np.zeros((4, 4))
    for k, v in enumerate(VIEWS):
        x = np.asarray(blocks[v], dtype=complex).ravel()
        if len(x) < 50 or not np.all(np.isfinite(x)):
            raise ValueError('response needs at least 50 finite IQ shots per view')
        covariance[2*k:2*k+2, 2*k:2*k+2] = np.cov([x.real, x.imag])/len(x)
    return covariance


def fit_response(references, *, validate=True):
    columns = [_vector({v: references[v][s] for v in VIEWS}) for s in 'gef']
    covariances = [_covariance({v: references[v][s] for v in VIEWS}) for s in 'gef']
    matrix = np.column_stack([columns[1]-columns[0], columns[2]-columns[0]])
    condition = float(np.linalg.cond(matrix))
    if not math.isfinite(condition) or (validate and condition > 8):
        raise ValueError('two-view response is ill-conditioned')
    snr = [float(np.linalg.norm(columns[b]-columns[a]) /
                 max(np.sqrt(np.trace(covariances[a]+covariances[b])), 1e-12))
           for a, b in ((0, 1), (0, 2), (1, 2))]
    if validate and min(snr) < 6:
        raise ValueError('two-view state separation is unresolved')
    return dict(ground=columns[0].tolist(), matrix=matrix.tolist(), condition=condition,
                pair_snr=snr, units='relative to freshly prepared g/e/f ensembles, not absolute populations')


def population(response, observed):
    matrix = np.asarray(response['matrix'])
    target = _vector(observed)-np.asarray(response['ground'])
    e, f = np.linalg.lstsq(matrix, target, rcond=None)[0]
    residual = np.linalg.norm(target-matrix @ [e, f])
    return dict(g=float(1-e-f), e=float(e), f=float(f), residual_iq=float(residual))


def validate_response(response, references):
    matrix = np.asarray(response['matrix'])
    inverse = np.linalg.pinv(matrix)
    scale = min(np.linalg.norm(matrix[:, 0]), np.linalg.norm(matrix[:, 1]))
    rows = []
    for s in 'gef':
        observed = {v: references[v][s] for v in VIEWS}
        result = population(response, observed)
        cov = _covariance(observed)
        error = np.sqrt(np.maximum(np.diag(inverse @ cov @ inverse.T), 0))
        target = np.array([s == 'e', s == 'f'], dtype=float)
        valid = (np.all(abs(np.array([result['e'], result['f']])-target) <= .15+3*error)
                 and result['residual_iq'] <= .10*scale+4*np.sqrt(np.trace(cov)))
        rows.append(dict(state=s, **result, valid=bool(valid)))
    return dict(valid=all(r['valid'] for r in rows), states=rows)


def fit_gain(gains, scores):
    """Fit the first pi of a positive sin-squared Rabi response, not its max."""
    from scipy.optimize import minimize_scalar
    gains, y = np.asarray(gains, dtype=float), np.asarray(scores, dtype=float)
    if len(gains) < 8 or not np.all(np.isfinite(y)) or np.ptp(y) < .12:
        raise ValueError('Rabi contrast is unresolved')
    def solve(pi_gain):
        shape = np.sin(np.pi*gains/(2*pi_gain))**2
        design = np.column_stack([np.ones(len(gains)), shape])
        coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
        error = float(np.mean((design @ coefficients-y)**2))
        return error if coefficients[1] > 0 else 1e6, coefficients
    grid = np.arange(4000., 28001., 100.)
    best = float(grid[np.argmin([solve(g)[0] for g in grid])])
    optimum = minimize_scalar(lambda g: solve(g)[0], bounds=(max(4000., best-150), min(28000., best+150)), method='bounded')
    error, coefficients = solve(optimum.x)
    if coefficients[1] < .12 or np.sqrt(error) > .12*coefficients[1]+.04 or optimum.x < 4100 or optimum.x > 27900:
        raise ValueError('Rabi oscillation is not resolved inside the gain range')
    return dict(pi_gain=int(round(optimum.x)), offset=float(coefficients[0]),
                amplitude=float(coefficients[1]), rms=float(np.sqrt(error)))


def alignment(feature_mhz, ge_mhz, ef_mhz):
    if not all(math.isfinite(float(x)) for x in (feature_mhz, ge_mhz, ef_mhz)) or not -250 < ef_mhz-ge_mhz < -100:
        raise ValueError('local e-f calibration has implausible anharmonicity')
    return dict(feature_mhz=float(feature_mhz), measured_ge_mhz=float(ge_mhz),
                measured_ef_mhz=float(ef_mhz), anharmonicity_mhz=float(ef_mhz-ge_mhz),
                mismatch_mhz=float(ef_mhz-feature_mhz), aligned=bool(abs(ef_mhz-feature_mhz) <= 2.))


def pulse_schedule(task, *, pulse_cycles, guard_cycles, dwell_cycles, short_cycles=None):
    """Matched four slots; late references shift prep, keeping mapping fixed."""
    if task['state'] not in 'gef' or task['view'] not in VIEWS:
        raise ValueError('unknown state or readout view')
    if pulse_cycles < 3 or guard_cycles < 1 or dwell_cycles < 1:
        raise ValueError('invalid pulse timing')
    short_cycles = dwell_cycles if short_cycles is None else short_cycles
    if short_cycles < 1 or short_cycles > dwell_cycles:
        raise ValueError('invalid late-reference delay')
    slot = pulse_cycles+guard_cycles
    delay = dwell_cycles-short_cycles if task.get('late') else 0
    frequencies = [task['ge_mhz'], task['ef_mhz'], task['ef_mhz'], task['ge_mhz']]
    gains = [task['ge_gain'] if task['state'] != 'g' else 0,
             task['ef_gain'] if task['state'] == 'f' else 0, 0,
             task['ge_gain'] if task['view'] == 'ge_swap' else 0]
    transition = task.get('cal_transition')
    if transition == 'ge':
        frequencies[:3] = [task['drive_mhz']]*3
        gains[:3] = [task['drive_gain'], task['drive_gain'] if task.get('turns') == 2 else 0, 0]
    elif transition == 'ef':
        frequencies[1:3] = [task['drive_mhz']]*2
        gains[1:3] = [task['drive_gain'], task['drive_gain'] if task.get('turns') == 2 else 0]
    starts = [delay+i*slot for i in range(3)]+[3*slot+dwell_cycles]
    return [dict(start_cycles=int(t), length_cycles=int(pulse_cycles), freq_mhz=float(f), gain=int(g))
            for t, f, g in zip(starts, frequencies, gains)]


class ResidentEFProgram(OPXResetT1Program):
    record_words = 2

    def decode_dmem_records(self, words, expected_records=None):
        records = resident.decode_single_iq(words, expected_records)
        self.transferred_records.extend(records)
        return records

    def __init__(self, soccfg, cfg, payload, loop):
        if cfg.get('opx_reset_scheme') != 'none' or not cfg.get('opx_hard_flux_steps') or not cfg.get('opx_persistent_park'):
            raise ValueError('resident e-f pilot requires passive persistent hard park')
        if cfg.get('flux_predistortion_overlap_payload_readout', True):
            raise ValueError('readout must follow the full return')
        if int(cfg['shots']) < 50 or int(cfg['shots']) != cfg['shots']:
            raise ValueError('invalid shot count')
        task = cfg['ef_task']
        if not .25 <= float(task['dwell_us']) <= 8.:
            raise ValueError('invalid pilot dwell')
        for key in ('ge_gain', 'ef_gain', 'drive_gain'):
            if key in task and (int(task[key]) != task[key] or not 0 <= task[key] <= 30000):
                raise ValueError('invalid pulse gain')
        if cfg.get('use_switch'):
            raise ValueError('explicit resident timing requires the switch disabled')
        self.transferred_records = []
        super().__init__(soccfg, cfg, payload, loop)

    def _resident_excursion(self):
        cfg, task = self.cfg, self.cfg['ef_task']
        if self._t1_ff_compensation is None:
            raise ValueError('resident sequence requires pinned compensation')
        qch, fch = cfg['qubit_ch'], cfg['ff_ch']
        periods = [float(self.cycles2us(1)), float(self.cycles2us(1, gen_ch=qch)), float(self.cycles2us(1, gen_ch=fch))]
        if max(periods)-min(periods) > 1e-12:
            raise ValueError('resident pulse and flux scheduling requires equal clocks')
        pulse = 4*int(self.us2cycles(float(cfg['sigma']), gen_ch=qch))
        guard = max(1, int(self.us2cycles(.01)))
        dwell = int(self.us2cycles(float(task['dwell_us'])))
        slots = pulse_schedule(task, pulse_cycles=pulse, guard_cycles=guard,
                               dwell_cycles=dwell, short_cycles=self.us2cycles(.25))
        # Lead allows the tProc to enqueue the first two channels without a
        # late time-zero microwave pulse. The science slots remain identical.
        lead = int(self.us2cycles(.5))
        for slot in slots:
            slot['start_cycles'] += lead
        end = slots[-1]['start_cycles']+pulse+guard
        window = float(self.cycles2us(end))
        pre, post = 30.+self._t1_ff_settle_us, .1
        park, target = int(cfg['ff_park_gain']), int(cfg['ff_gain'])
        segments, recovery = ff_pulse.compensation_round_trip_segments(
            self._t1_ff_compensation, pre+window+post,
            recovery_us=self._t1_ff_predistortion_recovery_us)
        before, tail = ff_pulse.split_compensation_segments(segments, pre)
        events, tail_cycles = _flux_events(self, park, target, tail)
        if tail_cycles <= end:
            raise ValueError('flux return would overlap target mapping')
        ff_pulse.play_relative_compensation_segments(self, park, target, before)
        self.sync_all(0)
        # Queue in chronological order. No all-channel sync between pulses:
        # it would wait for future compensation segments.
        merged = [(e['start_cycles'], 0, e) for e in events]+[(e['start_cycles'], 1, e) for e in slots]
        for start, kind, event in sorted(merged, key=lambda e: (e[0], e[1])):
            if kind == 0:
                self.set_pulse_registers(ch=fch, style='const', freq=0, phase=0,
                                        stdysel='last', gain=event['gain_dac'], length=event['length_cycles'])
                self.pulse(ch=fch, t=start)
            else:
                self.set_pulse_registers(ch=qch, style='arb', waveform='qubit',
                                        freq=self.freq2reg(event['freq_mhz'], gen_ch=qch),
                                        phase=self.deg2reg(0, gen_ch=qch), gain=event['gain'])
                self.pulse(ch=qch, t=start)
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)
        cfg['ef_timing'] = dict(pulse_slots=slots, flux_events=events,
                               mapping_end_cycles=slots[-1]['start_cycles']+pulse,
                               return_start_cycles=tail_cycles, clock_period_us=float(self.cycles2us(1)),
                               pre_us=pre, window_us=window, post_us=post,
                               f_prep_end_to_map_start_us=float(self.cycles2us(slots[-1]['start_cycles']-slots[1]['start_cycles']-pulse)),
                               local_mapping_before_return=True)

    def _emit_body(self):
        park_up, park_down = self._shot_park_callbacks()
        park_up()
        if self.cfg.get('ef_park_reference'):
            if self.cfg['ff_gain'] != self.cfg['ff_park_gain'] or self.cfg['ef_task']['state'] not in ('g', 'e'):
                raise ValueError('park reference must use the explicit park gain and g/e state')
            self._set_payload_pulse(gain=0 if self.cfg['ef_task']['state'] == 'g' else None)
            _pulse_pi_and_align(self)
            self.cfg['ef_timing'] = dict(park_reference=True, local_mapping_before_return=False)
        else:
            self._resident_excursion()
        self._measure_raw()
        for name in ('i', 'q'):
            self.memw(self.reset_page, self.reset_regs[name], self.reset_regs['address'])
            self.mathi(self.reset_page, self.reset_regs['address'], self.reset_regs['address'], '+', 1)
        park_down()
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))


def summarize_decay(pre, post, science, *, draws=400):
    """Bootstrap IQ shots AND shared reference means, retaining each pass."""
    responses = {d: fit_response(pre[d]) for d in DWELLS_US}
    audits = {d: validate_response(responses[d], post[d]) for d in DWELLS_US}
    if not all(a['valid'] for a in audits.values()):
        return dict(valid=False, post_reference_validation=audits,
                    reason='independent final response changed; raw science retained')
    rng = np.random.default_rng(41026)
    def resample(block):
        x = np.asarray(block)
        return x[rng.integers(len(x), size=len(x))]
    estimates = {(b, s, d): population(responses[d], science[b, s, d])
                 for b in range(2) for s in 'gef' for d in DWELLS_US}
    consistency = []
    for (b, s, d), result in estimates.items():
        matrix = np.asarray(responses[d]['matrix'])
        inverse = np.linalg.pinv(matrix)
        covariance = _covariance(science[b, s, d])
        for state in 'gef':
            covariance += result[state]**2*_covariance({v: pre[d][v][state] for v in VIEWS})
        residual = _vector(science[b, s, d])-np.asarray(responses[d]['ground'])-matrix @ [result['e'], result['f']]
        projection = np.eye(4)-matrix @ inverse
        chi2 = float(residual @ np.linalg.pinv(projection @ covariance @ projection.T, rcond=1e-8) @ residual)
        se = np.sqrt(np.maximum(np.diag(inverse @ covariance @ inverse.T), 0))
        valid = (chi2 < 18.5 and all(-.05-4*err <= result[level] <= 1.05+4*err for level, err in zip('ef', se))
                 and -.05-4*np.sum(se) <= result['g'] <= 1.05+4*np.sum(se))
        consistency.append(dict(block=b, preparation=s, dwell_us=d, residual_chi2=chi2, valid=bool(valid)))
    if not all(row['valid'] for row in consistency):
        return dict(valid=False, post_reference_validation=audits, science_consistency=consistency,
                    reason='science IQ is incompatible with the calibrated two-view response; raw data retained')
    values = {k: [] for k in estimates}
    unstable_draws = 0
    for _ in range(draws):
        rs = {d: fit_response({v: {s: resample(pre[d][v][s]) for s in 'gef'} for v in VIEWS}, validate=False)
              for d in DWELLS_US}
        unstable_draws += any(r['condition'] > 8 or min(r['pair_snr']) < 6 for r in rs.values())
        for k in estimates:
            values[k].append(population(rs[k[2]], {v: resample(science[k][v]) for v in VIEWS}))
    if unstable_draws > .05*draws:
        return dict(valid=False, post_reference_validation=audits, science_consistency=consistency,
                    bootstrap_unstable_fraction=unstable_draws/draws,
                    reason='reference response is too close to the resolution boundary for stable inference')
    rows = []
    for s in 'gef':
        for d in DWELLS_US:
            pooled = {level: float(np.mean([estimates[b, s, d][level] for b in range(2)])) for level in 'gef'}
            samples = {level: np.mean([[x[level] for x in values[b, s, d]] for b in range(2)], axis=0) for level in 'gef'}
            rows.append(dict(preparation=s, dwell_us=d, relative_population=pooled,
                             ci95={level: np.quantile(samples[level], [.025, .975]).tolist() for level in 'gef'},
                             pass_populations=[estimates[b, s, d] for b in range(2)]))
    delta = np.mean([[values[b, 'f', .25][i]['f']-values[b, 'f', 8.][i]['f'] for i in range(draws)] for b in range(2)], axis=0)
    return dict(valid=True, post_reference_validation=audits, science_consistency=consistency, populations=rows,
                f_loss_short_minus_long=float(np.mean(delta)), f_loss_ci95=np.quantile(delta, [.025, .975]).tolist(),
                interpretation='One bias, preparation-relative population transfer; no claim of a TLS peak or absolute f purity.')


def plot_summary(folder, summary):
    if not summary['valid']:
        return
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for axis, preparation, levels in [(axes[0], 'f', 'gef'), (axes[1], 'e', 'f'), (axes[1], 'g', 'f')]:
        rows = [r for r in summary['populations'] if r['preparation'] == preparation]
        for level in levels:
            x = [r['dwell_us'] for r in rows]
            y = np.array([r['relative_population'][level] for r in rows])
            bounds = np.array([r['ci95'][level] for r in rows]).T
            axis.errorbar(x, y, yerr=np.maximum(np.array([y-bounds[0], bounds[1]-y]), 0),
                          fmt='o-', capsize=3, label=f'{preparation} preparation: {level}')
    axes[0].set_title('Locally prepared f: population transfer')
    axes[1].set_title('Ground and excited preparation controls')
    for axis in axes:
        axis.set(xlabel='Additional dwell (µs)', ylabel='Preparation-relative population')
        axis.axhline(0, color='k', lw=.7)
        axis.grid(alpha=.25)
        axis.legend(fontsize=9)
    fig.suptitle('q3 local e–f pilot — target mapping before park return')
    for suffix in ('png', 'svg'):
        fig.savefig(Path(folder)/('resident_ef_decay.'+suffix), dpi=180)
    plt.close(fig)


def assess_fixed_check(pre, post, observations, *, draws=400):
    """Prove stable preparation-relative readout, then check local g-e loss."""
    responses = {d: fit_response(pre[d]) for d in (.25, 8.)}
    reports = {d: validate_response(responses[d], post[d]) for d in (.25, 8.)}
    result = dict(valid=False, readout_valid=False, quiet_control_valid=False,
                  final_response_validation=reports,
                  interpretation='Preparation-relative state control only; no absolute f purity or TLS loss result.')
    if not all(r['valid'] for r in reports.values()):
        result['reason'] = 'independent final readout references changed'
        return result
    matrix = np.asarray(responses[8.]['matrix'])
    inverse = np.linalg.pinv(matrix)
    estimates = {s: population(responses[8.], observations[s]) for s in 'ge'}
    residual_checks = {}
    for s, estimate in estimates.items():
        covariance = _covariance(observations[s])
        for state in 'gef':
            covariance += estimate[state]**2*_covariance({v: pre[8.][v][state] for v in VIEWS})
        residual = _vector(observations[s])-np.asarray(responses[8.]['ground'])-matrix @ [estimate['e'], estimate['f']]
        projection = np.eye(4)-matrix @ inverse
        chi2 = float(residual @ np.linalg.pinv(projection @ covariance @ projection.T, rcond=1e-8) @ residual)
        errors = np.sqrt(np.maximum(np.diag(inverse @ covariance @ inverse.T), 0))
        physical = (all(-.05-4*err <= estimate[level] <= 1.05+4*err for level, err in zip('ef', errors))
                    and -.05-4*sum(errors) <= estimate['g'] <= 1.05+4*sum(errors))
        residual_checks[s] = dict(residual_chi2=chi2, valid=bool(chi2 < 18.5 and physical))
    result['control_response_consistency'] = residual_checks
    if not all(r['valid'] for r in residual_checks.values()):
        result['reason'] = '8-us controls are inconsistent with the calibrated response'
        return result
    rng = np.random.default_rng(51026)
    samples = {s: [] for s in 'ge'}
    unstable = 0
    def resample(x):
        x = np.asarray(x)
        return x[rng.integers(len(x), size=len(x))]
    for _ in range(draws):
        response = fit_response({v: {s: resample(pre[8.][v][s]) for s in 'gef'} for v in VIEWS}, validate=False)
        unstable += response['condition'] > 8 or min(response['pair_snr']) < 6
        for s in 'ge':
            samples[s].append(population(response, {v: resample(observations[s][v]) for v in VIEWS}))
    result['bootstrap_unstable_fraction'] = float(unstable/draws)
    if unstable > .05*draws:
        result['reason'] = 'response uncertainty is unstable'
        return result
    result['readout_valid'] = True
    bounds = {s: {level: np.quantile([x[level] for x in samples[s]], [.025, .975]).tolist()
                  for level in 'gef'} for s in 'ge'}
    heating = np.quantile([x['e']+x['f'] for x in samples['g']], [.025, .975]).tolist()
    quiet = bounds['e']['e'][0] >= .65 and bounds['e']['f'][1] <= .15 and heating[1] <= .15
    result.update(valid=bool(quiet), quiet_control_valid=bool(quiet),
                  controls_8us={s: dict(relative_population=estimates[s], ci95=bounds[s]) for s in 'ge'},
                  ground_control_added_excitation_ci95=heating,
                  thresholds=dict(excited_control_retention_lower95_min=.65, added_excitation_upper95_max=.15),
                  reason='local preparation/readout and quiet controls passed' if quiet else
                         'local readout passed, but 8-us g-e/ground controls did not establish a quiet site')
    return result


def plot_calibration(folder, calibrations):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(9, 6), constrained_layout=True)
    for column, calibration in enumerate(calibrations):
        for spectrum in calibration['spectroscopy']:
            if spectrum['stage'] == 'fine':
                points = sorted(spectrum['points'], key=lambda p: p['frequency_mhz'])
                axes[0, column].plot([p['frequency_mhz'] for p in points], [p['score'] for p in points],
                                     'o-', ms=4, label=f"order {spectrum['order']+1}")
        fit = calibration['rabi_fit']
        gains = calibration['gain_grid']
        dense = np.linspace(min(gains), max(gains), 300)
        axes[1, column].plot(gains, calibration['gain_scores'], 'ko', ms=4, label='acquired')
        axes[1, column].plot(dense, fit['offset']+fit['amplitude']*np.sin(np.pi*dense/(2*fit['pi_gain']))**2,
                             label='Rabi fit')
        axes[1, column].axvline(fit['pi_gain'], color='tab:red', ls='--', label='first π')
        axes[0, column].set(title='Local '+calibration['transition'], xlabel='Drive frequency (MHz)')
        axes[1, column].set(xlabel='Pulse gain (DAC)')
    for axis in axes.flat:
        axis.set_ylabel('IQ / park reference separation')
        axis.grid(alpha=.25)
        axis.legend(fontsize=8)
    fig.suptitle('q3 fixed-bias pulse calibration — no TLS loss measurement')
    for suffix in ('png', 'svg'):
        fig.savefig(Path(folder)/('local_pulse_calibration.'+suffix), dpi=180)
    plt.close(fig)


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, progress=True, fixed_check=False):
    from tqdm import tqdm
    from . import FivePointApplesToApples as five, TLSSpectroscopy as tls
    from .ThreePointApplesToApples import _integer_dc_grid
    from ..active_reset_OPX.integration import _run_program, runtime_bundle

    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    fixed_source = None
    if fixed_check:
        fixed_source = data_root/FIXED_SCOUT_RELATIVE
        if hashlib.sha256(fixed_source.read_bytes()).hexdigest() != FIXED_SCOUT_SHA256:
            raise ValueError('fixed scout checksum does not match the reviewed source')
    folder = data_root/'q3'/('q3_resident_ef_pilot_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    path = folder/'manifest.json'
    manifest = dict(schema='q3.resident-ef-fixed-check.v1' if fixed_check else 'q3.resident-ef-pilot.v1',
                    status='initializing', plan=plan(fixed_check=fixed_check), completed=[],
                    created_at=datetime.now(timezone.utc).isoformat(), correction_sha256=localizer.CORRECTION_SHA256,
                    commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).parent, text=True).strip())
    for name in ('TLSResidentEFPilot.py', 'TLSEchoRefocusProgram.py', 'TLSDualTransitionLoss.py'):
        source = Path(__file__).with_name(name)
        shutil.copy2(source, folder/name)
        manifest[name+'_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    checkpoint(path, manifest)
    soc = None
    try:
        with noise.q3_context(tls, data_root), localizer.scan_environment(correction):
            five.install_scan_calibration(tls)
            if fixed_check:
                selected = dict(center_ghz=FIXED_FEATURE_GHZ, ef_bias_ghz=FIXED_BIAS_GHZ,
                                source='previously reviewed scout; feasibility check only')
                manifest.update(scout=str(fixed_source), scout_sha256=FIXED_SCOUT_SHA256)
                shutil.copy2(fixed_source, folder/'source_scout.csv')
            else:
                parameters = dict(wide.parameters(), output_suffix='TLS_Resident_EF_Pilot_Scout')
                scout = localizer.run(data_root=data_root, correction_json=correction, parameter_overrides=parameters, announce=False)
                manifest['scout'] = str(scout)
                selected = dual.select_eligible_feature(dual.read_scout(scout), anharmonicity_mhz=-180., pooled_readout=True)
            manifest['selection'] = selected
            checkpoint(path, manifest)
            compensation = tls._load_correction(str(correction), str(data_root))
            base = diagonal.science_config(tls, compensation)
            bundle = runtime_bundle(base)
            soc, soccfg = tls.makeProxy()
            checkpoint(folder/'board_configuration.json', soccfg.get_cfg())
            checkpoint(folder/'config.json', base)
            feature = selected['center_ghz']*1000
            initial_bias = selected['ef_bias_ghz']
            bar = tqdm(total=1, desc='Pulse calibration', unit='arm', disable=not progress,
                       bar_format='{desc}: {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]')
            raw = {}
            def acquire(name, task, *, bias, shots=CAL_SHOTS, park_reference=False):
                grid = np.array([float(bias)])
                with (folder/'compile.log').open('a', encoding='utf-8') as log, redirect_stdout(log):
                    if park_reference:
                        gain, realized = int(base['ff_park_gain']), None
                    else:
                        gains, realized_grid = _integer_dc_grid(dict(wide.parameters(), dc_min=-25146, freq_step_mhz=.5), grid, tls)
                        gain, realized = int(gains[0]), float(realized_grid[0])
                    cfg = dict(base, ef_task=task, ef_bias_ghz=bias, ff_gain=gain, shots=shots, reps=shots,
                               ff_hold=8., ef_park_reference=park_reference)
                    program = ResidentEFProgram(soccfg, cfg, bundle.payload, bundle.loop)
                    check = noise.preflight(program)
                manifest['current'] = dict(name=name, task=task, bias_ghz=bias, realized_ge_bias_ghz=realized)
                checkpoint(path, manifest)
                checkpoint(folder/(name+'.json'), dict(config=program.cfg, preflight=check))
                try:
                    records = _run_program(soc, program, 60., cfg, total_shots=shots)
                except BaseException as exc:
                    partial = getattr(exc, 'partial_records', program.transferred_records)
                    np.savez_compressed(folder/(name+'.partial.npz'), i=[r.i for r in partial], q=[r.q for r in partial])
                    raise
                np.savez_compressed(folder/(name+'.npz'), i=[r.i for r in records], q=[r.q for r in records])
                if len(records) != shots:
                    raise RuntimeError('incomplete resident e-f IQ acquisition')
                raw[name] = resident.record_iq(records)
                manifest['completed'].append(name)
                checkpoint(path, manifest)
                bar.update(1)
                return raw[name]

            default = dict(state='g', view='identity', dwell_us=.25, late=False,
                           ge_mhz=4367.292, ge_gain=13500, ef_mhz=4187.292, ef_gain=11250)
            bar.total = 2
            park_g = acquire('park_g', default, bias=4.367292, shots=500, park_reference=True)
            park_e = acquire('park_e', dict(default, state='e'), bias=4.367292, shots=500, park_reference=True)
            axis = np.mean(park_e)-np.mean(park_g)
            dual.validate_ef_audit(park_g, park_e, park_g)
            def score(x):
                return float(np.real((np.mean(x)-np.mean(park_g))/axis))
            calibration = []
            def calibrate(transition, task, bias, attempt):
                # Opposed frequency orders bracket drift; fine scans locate
                # the actual local transition rather than its park extrapolation.
                prefix = f'a{attempt}_{transition}'
                center = task[transition+'_mhz']
                radius = 12 if transition == 'ge' else 24
                gain = 13500 if transition == 'ge' else 9000
                spec = []
                for stage, offsets in [('coarse', np.arange(-radius, radius+.01, 2)), ('fine', np.arange(-2, 2.01, .5))]:
                    peaks = []
                    for order in range(2):
                        frequencies = center+offsets if order == 0 else (center+offsets)[::-1]
                        measurements = []
                        for k, frequency in enumerate(frequencies):
                            t = dict(task, state='g' if transition == 'ge' else 'e',
                                     view='identity' if transition == 'ge' else 'ge_swap',
                                     cal_transition=transition, drive_mhz=float(frequency), drive_gain=gain, turns=1)
                            y = score(acquire(f'{prefix}_{stage}_{order}_{k}', t, bias=bias))
                            measurements.append(dict(frequency_mhz=float(frequency), score=y))
                        best = max(measurements, key=lambda x: x['score'])
                        if best['frequency_mhz'] in (float(min(frequencies)), float(max(frequencies))):
                            raise ValueError('local spectroscopy peak lies at scan boundary')
                        peaks.append(best['frequency_mhz'])
                        spec.append(dict(stage=stage, order=order, points=measurements))
                        manifest['calibration_in_progress'] = dict(transition=transition, bias_ghz=bias, spectroscopy=spec)
                        checkpoint(path, manifest)
                    if abs(peaks[0]-peaks[1]) > (4 if stage == 'coarse' else 1.):
                        raise ValueError('opposed local frequency scans disagree')
                    center = float(np.mean(peaks))
                gain_grid = np.arange(0, 30001, 2500)
                scores = []
                for k, g in enumerate(gain_grid):
                    t = dict(task, state='g' if transition == 'ge' else 'e',
                             view='identity' if transition == 'ge' else 'ge_swap',
                             cal_transition=transition, drive_mhz=center, drive_gain=int(g), turns=1)
                    scores.append(score(acquire(f'{prefix}_gain_{k}', t, bias=bias)))
                fit = fit_gain(gain_grid, scores)
                audit = []
                for turns in (0, 1, 2):
                    t = dict(task, state='g' if transition == 'ge' else 'e',
                             view='identity' if transition == 'ge' else 'ge_swap',
                             cal_transition=transition, drive_mhz=center,
                             drive_gain=fit['pi_gain'] if turns else 0, turns=turns)
                    audit.append(acquire(f'{prefix}_audit_{turns}', t, bias=bias, shots=500))
                report = dual.validate_ef_audit(*audit)
                ground_control = None
                if transition == 'ef':
                    ground = []
                    for drive_gain in (0, fit['pi_gain']):
                        t = dict(task, state='g', view='ge_swap', cal_transition='ef',
                                 drive_mhz=center, drive_gain=drive_gain, turns=1)
                        ground.append(acquire(f'{prefix}_ground_{drive_gain}', t, bias=bias, shots=500))
                    effect = abs(np.mean(ground[1])-np.mean(ground[0]))
                    allowance = .15*report['contrast']+3*math.hypot(dual._standard_error(ground[0]), dual._standard_error(ground[1]))
                    ground_control = dict(effect=float(effect), allowance=float(allowance), valid=bool(effect <= allowance))
                    if not ground_control['valid']:
                        raise ValueError('e-f pulse excites the ground-prepared control')
                calibration.append(dict(attempt=attempt, transition=transition, bias_ghz=bias,
                                        measured_frequency_mhz=center, spectroscopy=spec,
                                        gain_grid=gain_grid.tolist(), gain_scores=scores, rabi_fit=fit, independent_audit=report,
                                        ground_control=ground_control))
                manifest['calibrations'] = calibration
                checkpoint(path, manifest)
                return center, fit['pi_gain']

            bias = initial_bias
            for attempt in range(1 if fixed_check else 2):
                bar.total = bar.n+146  # 60 g-e + 86 e-f calibration arms.
                task = dict(default, ge_mhz=bias*1000, ef_mhz=bias*1000-180.)
                task['ge_mhz'], task['ge_gain'] = calibrate('ge', task, bias, attempt)
                task['ef_mhz'] = task['ge_mhz']-180.
                task['ef_mhz'], task['ef_gain'] = calibrate('ef', task, bias, attempt)
                matched = alignment(feature, task['ge_mhz'], task['ef_mhz'])
                manifest['alignment'] = matched
                checkpoint(path, manifest)
                if fixed_check or matched['aligned']:
                    break
                corrected_bias = bias+(feature-task['ef_mhz'])/1000
                if attempt == 1 or abs(corrected_bias-initial_bias) > .006:
                    manifest.update(status='complete_unresolved_alignment', current=None)
                    checkpoint(path, manifest)
                    bar.close()
                    return folder
                bias = corrected_bias
            manifest['target_bias_ghz'] = bias
            manifest['local_pulses'] = task
            pre, post, science = {}, {}, {}
            bar.set_description('Qutrit readout check' if fixed_check else 'Qutrit readout and decay')
            bar.total = bar.n+(28 if fixed_check else 72)
            reference_dwells = (.25, 8.) if fixed_check else DWELLS_US
            def references(phase, output):
                print('SS cal: local two-view g/e/f references', flush=True)
                for d in reference_dwells:
                    output[d] = {v: {} for v in VIEWS}
                    pairs = [(v, s) for v in VIEWS for s in 'gef']
                    for v, s in (pairs if phase == 'pre' else pairs[::-1]):
                        output[d][v][s] = acquire(f'{phase}_d{d}_{v}_{s}', dict(task, state=s, view=v, dwell_us=d, late=True), bias=bias, shots=SHOTS)
                manifest[phase+'_response'] = {}
                for d in reference_dwells:
                    if phase == 'pre':
                        train = {v: {s: output[d][v][s][:SHOTS//2] for s in 'gef'} for v in VIEWS}
                        held = {v: {s: output[d][v][s][SHOTS//2:] for s in 'gef'} for v in VIEWS}
                        response = fit_response(train)
                        report = validate_response(response, held)
                        if not report['valid']:
                            raise ValueError('held-out two-view response failed')
                        manifest[phase+'_response'][str(d)] = dict(response=fit_response(output[d]), holdout=report)
                    else:
                        response = manifest['pre_response'][str(d)]['response']
                        manifest[phase+'_response'][str(d)] = validate_response(response, output[d])
                valid = phase == 'pre' or all(r['valid'] for r in manifest['post_response'].values())
                print('SS cal complete: local two-view references.' if valid else
                      'SS cal: local two-view final references unresolved.', flush=True)
                checkpoint(path, manifest)
            references('pre', pre)
            if fixed_check:
                observations = {s: {} for s in 'ge'}
                manifest['status'] = 'checking_local_controls'
                for s in 'ge':
                    for v in VIEWS:
                        observations[s][v] = acquire(f'check_d8_{s}_{v}', dict(task, state=s, view=v, dwell_us=8., late=False), bias=bias, shots=SHOTS)
                references('post', post)
                manifest['summary'] = assess_fixed_check(pre, post, observations)
                plot_calibration(folder, calibration)
                manifest.update(status='complete_calibration_passed' if manifest['summary']['valid'] else
                                'complete_calibration_check_failed', current=None)
            else:
                manifest['status'] = 'measuring'
                for block in range(2):
                    cells = [(s, d, v) for d in DWELLS_US for s in 'gef' for v in VIEWS]
                    for s, d, v in (cells if block == 0 else cells[::-1]):
                        key = (block, s, d)
                        science.setdefault(key, {})[v] = acquire(f'b{block}_d{d}_{s}_{v}', dict(task, state=s, view=v, dwell_us=d, late=False), bias=bias, shots=SHOTS)
                references('post', post)
                manifest['summary'] = summarize_decay(pre, post, science)
                plot_summary(folder, manifest['summary'])
                manifest.update(status='complete' if manifest['summary']['valid'] else 'complete_invalid_final_response', current=None)
            checkpoint(folder/'summary.json', manifest['summary'])
            bar.total = bar.n
            bar.refresh()
            bar.close()
            checkpoint(path, manifest)
    except (ValueError, RuntimeError) as exc:
        diagonal.abort_and_record(soc, manifest)
        manifest.update(status='unresolved', error=f'{type(exc).__name__}: {exc}')
        checkpoint(path, manifest)
    except BaseException as exc:
        diagonal.abort_and_record(soc, manifest)
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', error=f'{type(exc).__name__}: {exc}')
        checkpoint(path, manifest)
        raise
    finally:
        diagonal.abort_and_record(soc, manifest)
        if 'bar' in locals():
            bar.close()
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
        checkpoint(path, manifest)
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--fixed-check', action='store_true', help='local preparation/readout check at 4.272 GHz using the reviewed scout; no new scan or recenter')
    parser.add_argument('--data-root', default=localizer.DATA_ROOT)
    parser.add_argument('--correction-json')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps(plan(fixed_check=args.fixed_check), indent=2))
        return 0
    folder = run(data_root=args.data_root, correction_json=args.correction_json, progress=not args.quiet, fixed_check=args.fixed_check)
    status = json.loads((folder/'manifest.json').read_text())['status']
    print(f'Local e-f pilot {status}: {folder / "manifest.json"}', flush=True)
    return 0 if status in ('complete', 'complete_calibration_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
