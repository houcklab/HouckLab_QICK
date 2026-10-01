"""Same-frequency energy-return screen before two-frequency swap spectroscopy.

Blind 4.020--4.080 GHz grid, 1 MHz steps. Each logical shot interleaves hot/cold
loading and 0.1/10/40-us ground probes. A first park readout heralds the qubit;
there is no feedback or extra storage wait. The established 40-us corrected
return still limits the memory accessible to this experiment. Screen peaks
require independent confirmation with off-target loading before any 2-D map.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import shutil
import subprocess
import uuid

import numpy as np

from . import TLSPumpProbeHeralded as heralded
from . import TLSPumpProbeLocalizer as localizer
from . import TLSControlledNoise as noise
from . import Q3QuasiparticlePumping as qp
from ..active_reset_OPX.programs import (
    _declare_common, _reserved_registers, allocate_named_registers,
    resident_control_names,
)

PROBES_US = (.1, 10., 40.)
SHOTS, REFERENCE_SHOTS, BLOCKS = 400, 1200, 2
RECOVERY_US = 5000.
MIN_ACCEPTED = 80
SCREEN_SE_MULTIPLIER = 3.35


def tasks(*, shots=SHOTS):
    if int(shots) != shots or shots < 2:
        raise ValueError('shots must be an integer greater than one')
    rng = np.random.default_rng(1012026)
    grid = np.arange(4020, 4081)
    # Reverse both the frequency order and all six conditions in block two.
    first = rng.permutation(grid)
    result = []
    for block, order in enumerate((first, first[::-1])):
        for mhz in order:
            frequency = float(mhz / 1000)
            arms = [dict(name=f'{state}_{t:g}', pump_state=state, probe_state='g',
                         pump_ghz=frequency, probe_ghz=frequency, pump_us=10.,
                         probe_us=t, interstage_extra_us=0.,
                         pump_prepare_after_return=False,
                         probe_prepare_after_return=False)
                    for t in PROBES_US for state in ('g', 'e')]
            if block:
                arms.reverse()
            result.append(dict(name=f'b{block}_f{mhz}', index=len(result),
                               block=block, frequency_ghz=frequency,
                               shots=int(shots), conditions=arms))
    return result


def plan():
    return dict(qubit='q3', mode='same_frequency_screen',
                frequencies_ghz=[4.02, 4.08], step_mhz=1., frequency_points=61,
                pump_us=10., probe_us=list(PROBES_US), blocks=BLOCKS,
                shots_per_condition_per_block=SHOTS, science_programs=122,
                probe_shots=122 * SHOTS * 6, readouts_per_probe=2,
                intershot_recovery_us=RECOVERY_US,
                added_interstage_wait_us=0., corrected_return_us=40.,
                preparation='offline first-readout ground herald; no active reset',
                timing_limit='40-us pump return plus park readout and guard before probe',
                no_loss_site_selection=True, automatic_two_frequency_scan=False,
                screen_se_multiplier=SCREEN_SE_MULTIPLIER,
                approximate_minutes='30--40 including references and transport',
                decision='exploratory screen only; independently confirm energy return and controls before a two-frequency grid')


class DiagonalProgram(heralded.HeraldedPumpProbeProgram):
    """Six complete, paired-readout cells; stream only at logical boundaries."""

    def __init__(self, soccfg, configs, payload, loop):
        self.configs = [dict(c) for c in configs]
        if len(configs) not in (1, 6):
            raise ValueError('use six science conditions or one reference')
        first = configs[0]
        common = ('shots', 'ff_gain', 'opx_herald_probe_gain', 'ff_park_gain',
                  'opx_herald_pump_us', 'opx_herald_interstage_extra_us')
        if any(c[k] != first[k] for c in configs for k in common):
            raise ValueError('unmatched same-frequency cell configuration')
        if len(configs) == 6:
            if first['ff_gain'] != first['opx_herald_probe_gain']:
                raise ValueError('screen must load and probe the same frequency')
            if {(c['opx_herald_pump_state'], c['opx_herald_probe_us']) for c in configs} != {
                    (s, t) for s in ('g', 'e') for t in PROBES_US}:
                raise ValueError('missing hot/cold or short-probe control')
            if any(c['opx_herald_probe_state'] != 'g' or
                   c['opx_herald_pump_prepare_after_return'] or
                   c['opx_herald_probe_prepare_after_return'] for c in configs):
                raise ValueError('science must load before visiting and probe ground')
        elif not (first['opx_herald_pump_prepare_after_return'] and
                  first['opx_herald_probe_prepare_after_return']):
            raise ValueError('reference states must be prepared at readout')
        if first['opx_herald_interstage_extra_us'] != 0.:
            raise ValueError('diagonal screen has no added storage wait')
        self.logical_shots = int(first['shots'])
        cfg = dict(first, reps=self.logical_shots * len(configs), ff_hold=40.)
        super().__init__(soccfg, cfg, payload, loop)

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg['qubit_ch'])
        self.reset_regs = allocate_named_registers(
            self, self.reset_page,
            ('i', 'q', 'z', 'ground', 'excited', 'attempts', 'pi_count', 'status', 'address'))
        reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self, 0, resident_control_names(self.cfg, ('shot_loop', 'done')), reserved=reserved)
        self.regwi(self.reset_page, self.reset_regs['address'], self.record_base)
        self.regwi(0, controls['done'], 0)
        self.memwi(0, controls['done'], self.done_addr)
        self.regwi(0, controls['shot_loop'], self.logical_shots - 1)
        count = len(self.configs)
        self._initialize_stream(controls, total_shots=self.logical_shots,
                                records_per_shot=count, total_units=self.logical_shots,
                                records_per_unit=count, prefix='AFTERGLOW_DIAGONAL')
        self._begin_park_lifecycle()
        self.label('AFTERGLOW_DIAGONAL_LOOP')
        original = self.cfg
        for cfg in self.configs:
            self.cfg = cfg
            # The inherited cell ends with 1 ms; add 4 ms before EVERY next
            # condition, not just after a group of potentially contaminating arms.
            for _ in range(4):
                self.sync_all(self.us2cycles(1000.))
            self._emit_body()
        self.cfg = original
        self.mathi(0, controls['done'], controls['done'], '+', count)
        self.memwi(0, controls['done'], self.done_addr)
        self._stream_after_shot()
        self.loopnz(0, controls['shot_loop'], 'AFTERGLOW_DIAGONAL_LOOP')
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


def words_from_records(records):
    return np.asarray([[r.herald_i, r.herald_q, r.final_i, r.final_q]
                       for r in records], dtype=np.int64).reshape(-1, 4)


def summarize_program(words, task, axes, levels):
    words = np.asarray(words)
    shots, count = int(task['shots']), len(task['conditions'])
    if words.shape != (shots * count, 4) or count != 6:
        raise ValueError('incomplete six-condition paired IQ stream')
    low, high = map(float, levels)
    if not math.isfinite(high - low) or high <= low:
        raise ValueError('final reference separation collapsed')
    data = words.reshape(shots, count, 4)
    influences, iq_influences, conditions = [], [], []
    for j, arm in enumerate(task['conditions']):
        h = heralded._projection(data[:, j, 0] + 1j * data[:, j, 1], axes['herald'])
        q = heralded._projection(data[:, j, 2] + 1j * data[:, j, 3], axes['final'])
        mask = h < axes['herald']['ground_limit']
        y = (q > axes['final']['threshold']).astype(float)
        iq = (q - low) / (high - low)
        n = int(mask.sum())
        p, v = (float(y[mask].mean()), float(iq[mask].mean())) if n else (None, None)
        influences.append(mask * (y - p) / mask.mean() if n else np.zeros(shots))
        iq_influences.append(mask * (iq - v) / mask.mean() if n else np.zeros(shots))
        conditions.append(dict(name=arm['name'], pump_state=arm['pump_state'],
                               probe_us=arm['probe_us'], shots=shots, accepted=n,
                               acceptance=n / shots, conditional_pe=p, conditional_iq=v,
                               all_shot_pe=float(y.mean()), all_shot_iq=float(iq.mean()),
                               herald_excited=float(np.mean(h > axes['herald'].get('threshold', 0.)))))
    covariance = np.cov(np.asarray(influences), ddof=1) / shots
    iq_covariance = np.cov(np.asarray(iq_influences), ddof=1) / shots
    contrasts = []
    for t in PROBES_US:
        coeff = np.asarray([(1 if a['pump_state'] == 'e' else -1)
                            if a['probe_us'] == t else 0 for a in task['conditions']], dtype=float)
        baseline = np.asarray([(1 if a['pump_state'] == 'e' else -1)
                               if a['probe_us'] == .1 else 0 for a in task['conditions']], dtype=float)
        growth_coeff = coeff - baseline
        used = np.flatnonzero((coeff != 0) | (baseline != 0))
        valid = all(conditions[j]['accepted'] >= MIN_ACCEPTED for j in used)
        p = np.asarray([c['conditional_pe'] or 0. for c in conditions])
        iq = np.asarray([c['conditional_iq'] or 0. for c in conditions])
        contrasts.append(dict(probe_us=t, valid=valid, excess=float(coeff @ p),
                              excess_error=math.sqrt(max(0., coeff @ covariance @ coeff)),
                              growth=float(growth_coeff @ p),
                              growth_error=math.sqrt(max(0., growth_coeff @ covariance @ growth_coeff)),
                              iq_excess=float(coeff @ iq), iq_growth=float(growth_coeff @ iq),
                              iq_growth_error=math.sqrt(max(0., growth_coeff @ iq_covariance @ growth_coeff))))
    return dict(block=task['block'], frequency_ghz=task['frequency_ghz'],
                conditions=conditions, contrasts=contrasts,
                covariance=covariance.tolist(), iq_covariance=iq_covariance.tolist())


def analyze(cells, *, controls_valid):
    sites, candidates = [], []
    for f in sorted({c['frequency_ghz'] for c in cells}):
        blocks = {c['block']: c for c in cells if c['frequency_ghz'] == f}
        if len(blocks) != sum(c['frequency_ghz'] == f for c in cells):
            raise ValueError('duplicate frequency/block in analysis')
        delays = []
        for t in PROBES_US:
            values = [next(v for v in c['contrasts'] if v['probe_us'] == t) for c in blocks.values()]
            valid = len(values) == BLOCKS and all(v['valid'] for v in values)
            row = dict(probe_us=t, valid=valid, blocks=len(values))
            for metric in ('excess', 'growth'):
                means = [v[metric] for v in values]
                # Descriptive SE with an order-disagreement floor; two blocks
                # are insufficient for a discovery interval across 61 sites.
                variance = sum(v[metric + '_error'] ** 2 for v in values) / len(values) ** 2
                if len(values) > 1:
                    variance = max(variance, float(np.var(means, ddof=1) / len(values)))
                row[metric] = float(np.mean(means))
                row[metric + '_error'] = math.sqrt(variance)
            # 3.35 corresponds to a one-sided normal Bonferroni screen over
            # 61 x 2 site/delay comparisons. With two orders and possible drift
            # this is candidate triage, NOT a calibrated discovery p-value.
            row['screen_hit'] = bool(controls_valid and valid and t > .1 and
                row['excess'] > SCREEN_SE_MULTIPLIER * row['excess_error'] and
                row['growth'] > SCREEN_SE_MULTIPLIER * row['growth_error'] and all(
                v['excess'] >= .03 and v['growth'] >= .03 and
                v['iq_excess'] > 0 and v['iq_growth'] > 0 for v in values))
            row['block_values'] = values
            delays.append(row)
        if any(d['screen_hit'] for d in delays):
            candidates.append(f)
        sites.append(dict(frequency_ghz=f, delays=delays))
    return dict(sites=sites, candidate_frequencies_ghz=candidates,
                controls_valid=bool(controls_valid),
                interpretation='exploratory candidates only; require independent confirmation, off-target loading and readout/carryover controls',
                automatic_two_frequency_scan=False)


def science_config(tls, compensation):
    from ..active_reset_OPX.production import ProductionResetSession
    cfg = ProductionResetSession.passive().apply(qp.base_config())
    cfg.update(dt_pulseplay=tls.BaseConfig['dt_pulseplay'], dt_pulsedef=tls.BaseConfig['dt_pulsedef'],
               apply_flux_tail_compensation=True, flux_tail_compensation=compensation,
               flux_fit_params=list(tls.FLUX_FIT_PARAMS), flux_settle_time_us=.5,
               flux_predistortion_return_prefix_us=.5, flux_predistortion_recovery_us=40.,
               flux_predistortion_overlap_payload_readout=False,
               flux_predistortion_round_trip_mode='stateful', ff_ramp_length=4., do_ff=True,
               opx_hard_flux_steps=True, opx_persistent_park=True, opx_reset_scheme='none',
               opx_resident_dmem_stream=True, opx_park_preroll_us=1000.,
               opx_inter_shot_delay_us=1000., relax_delay=1000.)
    return cfg


def build_program(soccfg, base, task, lookup, bundle):
    configs = [heralded.arm_config(base, dict(a, shots=task['shots']), lookup)
               for a in task['conditions']]
    return DiagonalProgram(soccfg, configs, bundle.payload, bundle.loop)


def reference_tasks(phase):
    return [dict(name=a['name'], shots=REFERENCE_SHOTS, conditions=[a])
            for a in heralded.reference_arms(4.05, phase=phase)]


def reference_levels(raw, axes, phase):
    levels = []
    for name in ('ref_g', 'ref_final_e'):
        records = raw[f'{name}_{phase}']
        mask = heralded.confident_ground(heralded.record_iq(records, 'herald'), axes['herald'])
        levels.append(float(np.median(heralded._projection(
            heralded.record_iq(records, 'final')[mask], axes['final']))))
    if not all(map(math.isfinite, levels)) or levels[1] <= levels[0]:
        raise ValueError('final reference separation collapsed')
    return levels


def plot_summary(folder, summary):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
    for t in PROBES_US:
        x, excess, growth, error = [], [], [], []
        for site in summary['sites']:
            value = next(d for d in site['delays'] if d['probe_us'] == t)
            if not value['valid']:
                continue
            x.append(site['frequency_ghz']); excess.append(value['excess'])
            growth.append(value['growth']); error.append(value['growth_error'])
        axes[0].plot(x, excess, '.-', label=f'{t:g} µs probe')
        if t > .1:
            axes[1].errorbar(x, growth, yerr=error, fmt='.-', label=f'{t:g} µs probe')
    axes[0].set(ylabel='Hot − cold excited fraction', title='q3 same-frequency return screen (ground-heralded)')
    axes[1].set(xlabel='Load = probe frequency (GHz)', ylabel='Excess above 0.1 µs baseline')
    for axis in axes:
        axis.axhline(0, color='k', lw=.8); axis.legend(); axis.grid(alpha=.25)
    if not summary['controls_valid']:
        fig.suptitle('Readout controls unvalidated — descriptive only', color='darkred')
    fig.savefig(Path(folder) / 'afterglow_diagonal.png', dpi=160)
    plt.close(fig)


def abort_and_record(soc, manifest):
    """Try stopping immediately, without losing data if the board is offline."""
    from ..active_reset_OPX.acquisition import _safe_abort
    if soc is not None:
        try:
            _safe_abort(soc)
        except Exception as exc:
            manifest.setdefault('abort_errors', []).append(f'{type(exc).__name__}: {exc}')


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, progress=True):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    folder = data_root / 'q3' / ('q3_afterglow_diagonal_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    path = folder / 'manifest.json'
    manifest = dict(schema='q3.afterglow-diagonal.v1', status='initializing', plan=plan(),
                    completed=[], references={}, created_at=datetime.now(timezone.utc).isoformat(),
                    correction_sha256=localizer.CORRECTION_SHA256,
                    commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).parent, text=True).strip())
    for name in ('TLSAfterglowDiagonal.py', 'TLSPumpProbeHeralded.py', 'Q3QuasiparticlePumping.py'):
        source = Path(__file__).with_name(name)
        shutil.copy2(source, folder / name)
        manifest[name + '_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    qp.save_json(path, manifest)
    import matplotlib
    matplotlib.use('Agg')
    from tqdm import tqdm
    from . import FivePointApplesToApples as five, TLSSpectroscopy as tls
    from . import TLSPumpProbeWidePassiveScan as wide
    from .ThreePointApplesToApples import _integer_dc_grid
    from ..active_reset_OPX.integration import _run_program, runtime_bundle
    soc = None
    try:
        with noise.q3_context(tls, data_root), localizer.scan_environment(correction):
            five.install_scan_calibration(tls)
            run_tasks = tasks()
            grid = sorted({s['frequency_ghz'] for s in run_tasks})
            gains, realized = _integer_dc_grid(dict(wide.parameters(), freq_step_mhz=1.), np.asarray(grid), tls)
            lookup = dict(zip(grid, map(int, gains)))
            compensation = tls._load_correction(str(correction), str(data_root))
            cfg = science_config(tls, compensation)
            bundle = runtime_bundle(cfg)  # No tProc classification; axes come from paired references.
            soc, soccfg = tls.makeProxy()
            qp.save_json(folder / 'board_configuration.json', soccfg.get_cfg())
            qp.save_json(folder / 'config.json', cfg)
            manifest['flux_grid'] = [dict(requested_ghz=f, realized_ghz=float(r), gain=g)
                                     for f, r, g in zip(grid, realized, map(int, gains))]
            def build(task):
                with (folder / 'compile.log').open('a', encoding='utf-8') as log, redirect_stdout(log):
                    return build_program(soccfg, cfg, task, lookup, bundle)
            manifest['preflight'] = []
            for task in run_tasks + sum([reference_tasks(p) for p in ('pre', 'mid', 'post')], []):
                manifest['preflight'].append(dict(name=task['name'], **noise.preflight(build(task))))
            qp.save_json(path, manifest)

            def acquire(task, callback=None):
                program = build(task)
                manifest['current'] = task
                qp.save_json(path, manifest)
                qp.save_json(folder / (task['name'] + '.json'), dict(task=task, config=program.cfg,
                                                                   preflight=noise.preflight(program)))
                try:
                    records = _run_program(soc, program, 60., cfg, total_shots=task['shots'], progress=callback)
                except BaseException as exc:
                    abort_and_record(soc, manifest)
                    partial = getattr(exc, 'partial_records', None)
                    if partial is not None:
                        np.savez_compressed(folder / (task['name'] + '.partial.npz'), words=words_from_records(partial))
                    raise
                words = words_from_records(records)
                np.savez_compressed(folder / (task['name'] + '.npz'), words=words)
                if len(records) != task['shots'] * len(task['conditions']):
                    raise RuntimeError('incomplete paired IQ acquisition')
                return records, words

            raw = {}
            def references(phase, axes=None):
                print('SS cal: paired herald and final readout', flush=True)
                for ref in reference_tasks(phase):
                    raw[ref['name']], _ = acquire(ref)
                args = [raw[f'{name}_{phase}'] for name in ('ref_g', 'ref_e', 'ref_final_e')]
                result = heralded.assess_pre_references(*args)
                if axes is not None:
                    result['frozen_axis_validation'] = heralded.validate_pair_against_axes(axes, *args)
                manifest['references'][phase] = result
                qp.save_json(path, manifest)
                print('SS cal complete.' if result['valid'] else
                      'SS cal reference checks failed; conditional results are unvalidated.', flush=True)
                return result

            pre = references('pre')
            if not pre['valid'] or pre['axes'] is None:
                manifest.update(status='complete_invalid_initial_references', current=None)
                return folder
            axes = pre['axes']
            levels = reference_levels(raw, axes, 'pre')
            cells = []
            manifest['status'] = 'acquiring'
            with tqdm(total=plan()['probe_shots'], desc='Swap return screen', unit='shot', disable=not progress,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                for task in run_tasks:
                    if task['index'] == 61:
                        references('mid', axes)
                    offset = task['index'] * SHOTS * 6
                    def update(done, total):
                        bar.update(offset + int(done) * 6 - bar.n)
                    _, words = acquire(task, update)
                    cell = summarize_program(words, task, axes, levels)
                    cells.append(cell)
                    manifest['completed'].append(dict(task=task, summary=cell, raw_file=task['name'] + '.npz'))
                    qp.save_json(path, manifest)
                    qp.save_json(folder / 'summary.json', analyze(cells, controls_valid=False))
            post = references('post', axes)
            valid = all(manifest['references'][p].get('frozen_axis_validation', {}).get('valid', False)
                        for p in ('mid', 'post'))
            summary = analyze(cells, controls_valid=valid)
            qp.save_json(folder / 'summary.json', summary)
            plot_summary(folder, summary)
            # The final fit is a sensitivity check on identical saved shots.
            if post['axes'] is not None:
                post_levels = reference_levels(raw, post['axes'], 'post')
                post_cells = []
                for entry in manifest['completed']:
                    with np.load(folder / entry['raw_file']) as saved:
                        post_cells.append(summarize_program(saved['words'], entry['task'], post['axes'], post_levels))
                qp.save_json(folder / 'post_calibration_summary.json', analyze(post_cells, controls_valid=valid and post['valid']))
            manifest.update(status='complete' if valid else 'complete_controls_uncertain', current=None)
    except BaseException as exc:
        abort_and_record(soc, manifest)
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        abort_and_record(soc, manifest)
        manifest['completed_at'] = datetime.now(timezone.utc).isoformat()
        qp.save_json(path, manifest)
    return folder


def main(argv=None):
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--data-root', default=str(localizer.DATA_ROOT))
    parser.add_argument('--correction-json')
    args = parser.parse_args(argv)
    if args.plan or not args.run:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json, progress=not args.quiet)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
