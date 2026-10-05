"""Finite q3 load--feedback/sham--probe check before another afterglow map.

Three fixed sites; hot/cold loads; short/long probes; four fixed correction
opportunities versus equal-duration zero-gain pulses. Five weak IQ pairs and
one independent strong final readout are saved for EVERY trial. This tests
memory surviving the corrected return and reset, not fast TLS memory.
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

from . import TLSRepeatedLoading as loading
from . import TLSRepeatedLoadingFeedbackCheck as check
from .TLSRepeatedLoadingProgram import RepeatedLoadingProgram
from ..active_reset_OPX.programs import OPXResetT1Program, _pulse_pi_and_align

FREQUENCIES_GHZ = (3.984, 3.862, 4.046)
SHOTS, REFERENCE_SHOTS = 600, 600
PROBES_US = (.1, 40.)
RECORD_WORDS = 12


def tasks(*, shots=SHOTS):
    if not isinstance(shots, (int, np.integer)) or shots < 2:
        raise ValueError('shots must be an integer greater than one')
    conditions = [dict(pump_state=s, feedback=f, probe_us=t)
                  for t in PROBES_US for f in (False, True) for s in ('g', 'e')]
    return [dict(name=f'b{b}_f{round(f*1000)}', block=b, frequency_ghz=f,
                 shots=int(shots), conditions=conditions if b == 0 else conditions[::-1])
            for b, order in enumerate((FREQUENCIES_GHZ, FREQUENCIES_GHZ[::-1])) for f in order]


def reference_tasks(phase):
    return [dict(name=f'ref_{s}_{phase}', block=-1, frequency_ghz=4.046,
                 shots=REFERENCE_SHOTS, conditions=[dict(pump_state='g', feedback=True,
                                                        probe_us=.1, reference_state=s)])
            for s in (('g', 'e') if phase == 'pre' else ('e', 'g'))]


def plan():
    return dict(qubit='q3', frequencies_ghz=list(FREQUENCIES_GHZ),
                load_us=10., probes_us=list(PROBES_US), blocks=2,
                shots_per_condition_per_block=SHOTS, science_records=28800,
                reference_records=2400, calibration_records=8000,
                feedback_readout_gain=1200, final_readout_gain=1880,
                feedback_rounds=4, weak_readouts_per_trial=5,
                recovery_us=5000., corrected_return_us=40., guard_us=20.,
                false_pi_training_limit=.02, false_pi_holdout_maximum=.04,
                approximate_minutes='4--8 including fresh references and transport',
                short_probe_equivalence_margin=.05, equivalence_units='normalized final-reference IQ separation',
                ground_verification_minimum=.20, automatic_long_scan=False,
                no_loss_site_selection=True,
                decision='Check preparation equivalence first; positive growth only warrants independent, detuned-loading confirmation.',
                timing_limit='40-us corrected pump return plus four feedback opportunities and verification; scheduled gap saved per condition')


class FeedbackPilotProgram(OPXResetT1Program):
    record_words = RECORD_WORDS
    _fixed_reset = RepeatedLoadingProgram._fixed_reset
    _save_iq = RepeatedLoadingProgram._save_iq
    # Existing resident loop interleaves complete cells, adding 4 ms to the
    # inherited cell's 1 ms recovery. Bank boundaries occur only between shots.
    make_program = loading.diagonal.DiagonalProgram.make_program

    def __init__(self, soccfg, configs, payload, loop):
        self.configs = [dict(c) for c in configs]
        if len(configs) not in (1, 8):
            raise ValueError('eight matched science arms or one reference required')
        first = self.configs[0]
        common = ('shots', 'ff_gain', 'ff_park_gain', 'read_pulse_gain',
                  'flux_predistortion_recovery_us', 'qubit_pi_gain', 'qubit_pi_freq')
        if any(c[k] != first[k] for c in self.configs for k in common):
            raise ValueError('unmatched load/probe configurations')
        if not first.get('do_ff') or not first.get('opx_persistent_park') or not first.get('opx_hard_flux_steps'):
            raise ValueError('persistent hard park and corrected excursions required')
        if first.get('flux_predistortion_overlap_payload_readout', True) or first['flux_predistortion_recovery_us'] != 40.:
            raise ValueError('readout must follow the full 40-us return')
        if first['read_pulse_gain'] != 1200 or first['ff_park_gain'] != -25146 or first['qubit_pi_freq'] != 4367.292:
            raise ValueError('q3 park and validated gain-1200 feedback required')
        for c in self.configs:
            if c['pilot_pump_state'] not in ('g', 'e') or c['pilot_probe_us'] not in PROBES_US:
                raise ValueError('unknown pilot arm')
            if not isinstance(c['pilot_feedback'], bool):
                raise ValueError('feedback must be explicit')
            if c['reset_pi_gain'] != (c['qubit_pi_gain'] if c['pilot_feedback'] else 0):
                raise ValueError('feedback and sham correction gains do not match')
            if c['pilot_reference_state'] not in (None, 'g', 'e'):
                raise ValueError('unknown reference state')
        if len(configs) == 8:
            if {(c['pilot_pump_state'], c['pilot_feedback'], c['pilot_probe_us']) for c in configs} != {
                    (s, f, t) for s in ('g', 'e') for f in (False, True) for t in PROBES_US}:
                raise ValueError('missing carryover or sham control')
            if any(c['pilot_reference_state'] is not None for c in configs):
                raise ValueError('reference cannot replace a science probe')
        elif first['pilot_reference_state'] is None:
            raise ValueError('single-cell program must be a reference')
        self.logical_shots = int(first['shots'])
        if self.logical_shots < 2 or self.logical_shots != first['shots']:
            raise ValueError('invalid logical shot count')
        self._sync_ticks, self.timing, self.transferred_records = 0, [], []
        super().__init__(soccfg, dict(first, reps=self.logical_shots*len(configs), ff_hold=10.), payload, loop)

    def decode_dmem_records(self, words, expected_records=None):
        records = check.decode_records(words, expected_records)
        self.transferred_records.extend(records)
        return records

    def sync_all(self, t=0):
        # Match the pinned QICK timeline's integer truncation. This is a
        # scheduled duration, not a measurement of the analog flux response.
        self._sync_ticks += max(0, int(max(self._dac_ts+self._adc_ts)+t))
        return super().sync_all(t)

    def _emit_body(self):
        cfg = self.cfg
        self.reset_regs['threshold'] = self.reset_regs['ground']
        ro_page, ro_gain = self.ch_page(cfg['res_ch']), self.sreg(cfg['res_ch'], 'gain')
        # The preceding cell used gain 1880. Every loading/reset starts weak.
        self.regwi(ro_page, ro_gain, 1200)
        self._set_payload_pulse(gain=cfg['qubit_pi_gain'] if cfg['pilot_pump_state']=='e' else 0)
        _pulse_pi_and_align(self)
        self._wait_t1_payload(10.)
        after_return = self._sync_ticks
        self._fixed_reset(cfg['pilot_label'])
        self._set_payload_pulse(gain=0)
        _pulse_pi_and_align(self)
        before_probe = self._sync_ticks
        self._wait_t1_payload(cfg['pilot_probe_us'])
        self._set_payload_pulse(gain=cfg['qubit_pi_gain'] if cfg['pilot_reference_state']=='e' else 0)
        _pulse_pi_and_align(self)
        self.regwi(ro_page, ro_gain, 1880)
        self._measure_raw()
        self._save_iq()
        self.sync_all(self.us2cycles(1000.))
        self.timing.append(dict(label=cfg['pilot_label'], pump_state=cfg['pilot_pump_state'],
                                feedback=cfg['pilot_feedback'], probe_us=cfg['pilot_probe_us'],
                                last_load_end_to_probe_excursion_us=40.+float(self.cycles2us(before_probe-after_return)),
                                note='scheduled gap to probe excursion; includes full pump return, reset and zero-pi; target has additional 0.5-us arrival'))


def build_program(soccfg, base, task, lookup, bundle):
    configs = [dict(base, ff_gain=lookup[task['frequency_ghz']], ff_hold=10., shots=task['shots'],
                    pilot_pump_state=c['pump_state'], pilot_feedback=c['feedback'],
                    pilot_probe_us=c['probe_us'], pilot_reference_state=c.get('reference_state'),
                    pilot_label=f'PILOT_{j}', reset_pi_gain=base['qubit_pi_gain'] if c['feedback'] else 0)
               for j, c in enumerate(task['conditions'])]
    return FeedbackPilotProgram(soccfg, configs, bundle.payload, bundle.loop)


def summarize_program(words, task, axis, bundle):
    n, count = task['shots'], len(task['conditions'])
    w = np.asarray(words)
    if w.shape != (n*count, RECORD_WORDS):
        raise ValueError('incomplete pilot records')
    w = w.reshape(n, count, RECORD_WORDS)
    keep = bundle.loop.project(w[:, :, 8], w[:, :, 9]) <= bundle.loop.ground_threshold
    projected = loading.heralded._projection(w[:, :, 10]+1j*w[:, :, 11], axis)
    y = projected > axis['threshold']
    iq = (projected-axis['low'])/(axis['high']-axis['low'])
    overflow = np.any(np.abs(w[:, :, :10]) > 32767, axis=(0, 2))
    conditions, influences, iq_influences = [], [], []
    for j, arm in enumerate(task['conditions']):
        k = keep[:, j]; accepted = int(k.sum())
        pe = float(y[k, j].mean()) if accepted else None
        mean_iq = float(iq[k, j].mean()) if accepted else None
        conditions.append(dict(arm, accepted=accepted, ground_fraction=float(k.mean()),
                               pe=pe, iq=mean_iq, all_pe=float(y[:, j].mean()),
                               all_iq=float(iq[:, j].mean()), overflow=bool(overflow[j]),
                               mean_corrections=float(sum(loading.feedback_decision(w[:, j, 2*r], w[:, j, 2*r+1],
                                   bundle.payload if r == 0 else bundle.loop).astype(int) for r in range(4)).mean())
                                   if arm['feedback'] else 0.))
        influences.append(k*(y[:, j]-(pe or 0.))/max(float(k.mean()), 1/n))
        iq_influences.append(k*(iq[:, j]-(mean_iq or 0.))/max(float(k.mean()), 1/n))
    covariance = lambda a: np.atleast_2d(np.cov(np.asarray(a), ddof=1))/n
    return dict(frequency_ghz=task['frequency_ghz'], block=task['block'], conditions=conditions,
                covariance=covariance(influences).tolist(), iq_covariance=covariance(iq_influences).tolist(),
                all_covariance=covariance(y.T).tolist(),
                all_iq_covariance=covariance(iq.T).tolist(),
                valid=bool(not overflow.any() and all(c['accepted'] >= 80 and c['ground_fraction'] >= .2
                                                     for c in conditions)))


def analyze(cells, *, controls_valid):
    indexed = {(c['frequency_ghz'], c['block']): c for c in cells}
    if len(indexed) != len(cells):
        raise ValueError('duplicate pilot cell')
    sites, followups = [], []
    for f in sorted({c['frequency_ghz'] for c in cells}):
        site = dict(frequency_ghz=f)
        for feedback, name in ((False, 'sham'), (True, 'feedback')):
            blocks = []
            for b in (0, 1):
                c = indexed.get((f, b))
                if c is None or not c['valid']:
                    continue
                arms = c['conditions']
                short = np.array([(1 if a['pump_state']=='e' else -1)
                                  if a['feedback']==feedback and a['probe_us']==.1 else 0 for a in arms])
                long = np.array([(1 if a['pump_state']=='e' else -1)
                                 if a['feedback']==feedback and a['probe_us']==40. else 0 for a in arms])
                row = dict(block=b)
                for metric, a, values, cov in (
                    ('short_excess', short, 'pe', 'covariance'), ('long_excess', long, 'pe', 'covariance'),
                    ('growth', long-short, 'pe', 'covariance'), ('iq_growth', long-short, 'iq', 'iq_covariance'),
                    ('all_growth', long-short, 'all_pe', 'all_covariance'),
                    ('all_iq_growth', long-short, 'all_iq', 'all_iq_covariance'),
                    ('short_iq', short, 'iq', 'iq_covariance'), ('short_all_iq', short, 'all_iq', 'all_iq_covariance')):
                    row[metric] = float(a @ [v[values] for v in arms])
                    row[metric+'_variance'] = max(0., float(a @ np.asarray(c[cov]) @ a))
                blocks.append(row)
            r = dict(valid=len(blocks)==2, blocks=blocks, preparation_comparable=False)
            if blocks:
                for metric in ('short_excess', 'long_excess', 'growth', 'iq_growth', 'all_growth',
                               'all_iq_growth', 'short_iq', 'short_all_iq'):
                    values = [v[metric] for v in blocks]
                    variance = sum(v[metric+'_variance'] for v in blocks)/len(blocks)**2
                    if len(blocks)>1:
                        variance = max(variance, float(np.var(values, ddof=1)/len(blocks)))
                    r[metric], r[metric+'_error'] = float(np.mean(values)), math.sqrt(variance)
                r['preparation_comparable'] = bool(r['valid'] and all(
                    abs(r[k])+1.96*r[k+'_error'] <= .05 for k in ('short_iq', 'short_all_iq')))
            site[name] = r
        r = site['feedback']
        hit = bool(controls_valid and r['preparation_comparable']
                   and r['growth'] > max(.03, 3.35*r['growth_error'])
                   and r['long_excess'] > 3.35*r['long_excess_error']
                   and all(v['growth'] > .02 and v['iq_growth'] > 0 and v['all_iq_growth'] > 0
                           for v in r['blocks']))
        site['needs_independent_confirmation'] = hit
        if hit:
            followups.append(f)
        sites.append(site)
    return dict(controls_valid=bool(controls_valid), sites=sites, followup_frequencies_ghz=followups,
                automatic_long_scan=False,
                interpretation='conditional classified fractions and normalized IQ, not absolute TLS population; three fixed sites, no peak reselection; even a positive needs independent off-target controls')


def plot_results(folder, summary):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for name, shift in (('sham', -.002), ('feedback', .002)):
        for ax, key in zip(axes, ('short_excess', 'growth')):
            rows = [(s['frequency_ghz'], s[name]) for s in summary['sites'] if key in s[name]]
            ax.errorbar([f+shift for f, r in rows], [r[key] for f, r in rows],
                        yerr=[r[key+'_error'] for f, r in rows], fmt='o', capsize=3, label=name)
            ax.axhline(0, color='k', lw=.8); ax.grid(alpha=.25)
            ax.set(xlabel='Load/probe frequency (GHz)'); ax.legend()
    axes[0].set(title='Short-probe hot minus cold', ylabel='Conditional classified excited fraction')
    axes[1].set(title='Additional hot minus cold growth', ylabel='(40 us excess) minus (0.1 us excess)')
    fig.suptitle('q3 feedback afterglow pilot' + ('' if summary['controls_valid'] else ': references unvalidated'))
    fig.savefig(Path(folder)/'feedback_pilot.png', dpi=160)
    plt.close(fig)


def run(*, data_root=loading.localizer.DATA_ROOT, correction_json=None, progress=True):
    from tqdm import tqdm
    from . import TLSSpectroscopy as tls, FivePointApplesToApples as five, TLSPumpProbeWidePassiveScan as wide
    from .ThreePointApplesToApples import _integer_dc_grid
    from ..active_reset_OPX.integration import _run_program
    import matplotlib
    matplotlib.use('Agg')
    root = Path(data_root)
    correction = loading.localizer.checked_correction(root, correction_json)
    folder = root/'q3'/('q3_afterglow_feedback_pilot_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    path = folder/'manifest.json'
    manifest = dict(schema='q3.afterglow-feedback-pilot.v1', status='initializing', plan=plan(),
                    completed=[], references={}, created_at=datetime.now(timezone.utc).isoformat(),
                    correction_sha256=loading.localizer.CORRECTION_SHA256,
                    commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=Path(__file__).parent, text=True).strip())
    for name in ('TLSAfterglowFeedbackPilot.py', 'TLSRepeatedLoadingProgram.py', 'TLSRepeatedLoading.py',
                 'TLSRepeatedLoadingFeedbackCheck.py', 'TLSAfterglowDiagonal.py', 'Q3QuasiparticlePumping.py'):
        source = Path(__file__).with_name(name)
        shutil.copy2(source, folder/name)
        manifest[name+'_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    loading.qp.save_json(path, manifest)
    soc, cells = None, []
    try:
        with loading.noise.q3_context(tls, root), loading.localizer.scan_environment(correction):
            five.install_scan_calibration(tls)
            grid = sorted(FREQUENCIES_GHZ)
            gains, realized = _integer_dc_grid(dict(wide.parameters(), freq_step_mhz=1.), np.array(grid), tls)
            lookup = dict(zip(grid, map(int, gains)))
            cfg = loading.diagonal.science_config(tls, tls._load_correction(str(correction), str(root)))
            cfg['read_pulse_gain'] = 1200
            soc, soccfg = tls.makeProxy()
            loading.qp.save_json(folder/'board_configuration.json', soccfg.get_cfg())
            bundle = loading.calibrate(soc, soccfg, folder, readout_gain=1200, attempts=1, false_pi_limit=.02)
            loading.qp.save_json(folder/'config.json', cfg)
            manifest['flux_grid'] = [dict(requested_ghz=f, realized_ghz=float(r), gain=g)
                                     for f, r, g in zip(grid, realized, map(int, gains))]
            def build(task):
                with (folder/'compile.log').open('a', encoding='utf-8') as log, redirect_stdout(log):
                    return build_program(soccfg, cfg, task, lookup, bundle)
            manifest['preflight'] = []
            for task in tasks()+reference_tasks('pre'):
                p = build(task)
                manifest['preflight'].append(dict(name=task['name'], timing=p.timing, **loading.noise.preflight(p)))
            loading.qp.save_json(path, manifest)
            def acquire(task, callback=None):
                p = build(task)
                manifest['current'] = task
                loading.qp.save_json(path, manifest)
                loading.qp.save_json(folder/(task['name']+'.json'), dict(task=task, config=p.cfg, timing=p.timing))
                try:
                    records = _run_program(soc, p, 90., cfg, total_shots=task['shots'], progress=callback)
                except BaseException:
                    loading.diagonal.abort_and_record(soc, manifest)
                    words = np.asarray([r.to_words() for r in p.transferred_records], dtype=np.int64).reshape(-1, RECORD_WORDS)
                    np.savez_compressed(folder/(task['name']+'.partial.npz'), words=words)
                    raise
                words = np.asarray([r.to_words() for r in records], dtype=np.int64)
                np.savez_compressed(folder/(task['name']+'.npz'), words=words)
                if words.shape != (task['shots']*len(task['conditions']), RECORD_WORDS):
                    raise RuntimeError('incomplete feedback pilot acquisition')
                manifest['completed'].append(dict(task=task, raw_file=task['name']+'.npz',
                                                 completed_at=datetime.now(timezone.utc).isoformat()))
                loading.qp.save_json(path, manifest)
                return words
            def references(phase, frozen=None):
                print('SS cal: feedback-probe final readout references', flush=True)
                raw = {t['conditions'][0]['reference_state']: acquire(t) for t in reference_tasks(phase)}
                report = loading.reference_axis(raw['g'], raw['e'], bundle.loop, frozen=frozen)
                manifest['references'][phase] = report
                loading.qp.save_json(path, manifest)
                print('SS cal complete.' if report['valid'] else 'SS cal checks failed.', flush=True)
                return report, raw
            pre, _ = references('pre')
            if not pre['valid']:
                raise RuntimeError('final-readout references failed; no science acquired')
            manifest['status'] = 'acquiring'
            offset = 0
            with tqdm(total=plan()['science_records'], desc='Afterglow pilot', unit='shot', disable=not progress,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                for task in tasks():
                    def update(done, total):
                        bar.update(offset+int(done)*8-bar.n)
                    words = acquire(task, update)
                    offset += task['shots']*8
                    bar.update(offset-bar.n)
                    cell = summarize_program(words, task, pre['axis'], bundle)
                    cells.append(cell)
                    manifest['completed'][-1]['summary'] = cell
                    loading.qp.save_json(path, manifest)
                    loading.qp.save_json(folder/'summary.json', analyze(cells, controls_valid=False))
            post, raw = references('post', pre['axis'])
            refit = loading.reference_axis(raw['g'], raw['e'], bundle.loop)
            manifest['references']['post_refit'] = refit
            valid = pre['valid'] and post['valid']
            summary = analyze(cells, controls_valid=valid)
            loading.qp.save_json(folder/'summary.json', summary)
            if refit['axis'] is not None:
                refit_cells = []
                for entry in manifest['completed']:
                    if entry['task']['block'] < 0:
                        continue
                    with np.load(folder/entry['raw_file']) as saved:
                        refit_cells.append(summarize_program(saved['words'], entry['task'], refit['axis'], bundle))
                loading.qp.save_json(folder/'post_calibration_summary.json', analyze(refit_cells, controls_valid=valid and refit['valid']))
            plot_results(folder, summary)
            manifest.update(status='complete' if valid else 'complete_controls_uncertain', current=None)
    except BaseException as exc:
        loading.diagonal.abort_and_record(soc, manifest)
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        loading.diagonal.abort_and_record(soc, manifest)
        manifest['completed_at'] = datetime.now(timezone.utc).isoformat()
        loading.qp.save_json(path, manifest)
    return folder


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--data-root', default=loading.localizer.DATA_ROOT)
    parser.add_argument('--correction-json')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(plan(), indent=2))
    else:
        folder = run(data_root=args.data_root, correction_json=args.correction_json, progress=not args.quiet)
        print(f'Afterglow pilot complete: {folder}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
