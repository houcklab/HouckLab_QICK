"""Repeated blind q3 same-frequency afterglow maps versus wall-clock time.

Reuse the measured paired-readout sequence: hot/cold 10-us loading, a complete
40-us corrected return, ground herald, then a 0.1/10/40-us probe. This is an
offline-heralded energy-return screen, not the paper's feed-forward protocol.
No loss-site selection, feedback reset, or lifetime fitting is performed.
Default: one 4.000--4.050-GHz pass; --continuous explicitly repeats until stopped.
"""
import argparse
from contextlib import redirect_stdout
import csv
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import numpy as np

from . import TLSAfterglowDiagonal as diagonal
from . import TLSControlledNoise as noise
from . import TLSPumpProbeLocalizer as localizer
from . import Q3QuasiparticlePumping as qp


class TimeMapProgram(diagonal.DiagonalProgram):
    """Same hardware program; retain decoded banks on the host for interruption."""

    def __init__(self, *args, **kwargs):
        self.received_records = []
        super().__init__(*args, **kwargs)

    def decode_dmem_records(self, words, expected_records=None):
        records = diagonal.heralded.decode_paired_iq(words, expected_records)
        self.received_records.extend(records)
        return records


def now():
    return datetime.now(timezone.utc).isoformat()


def plan(*, freq_start=4., freq_stop=4.05, step_mhz=2., shots=400, passes=1):
    values = tuple(map(float, (freq_start, freq_stop, step_mhz, shots, passes)))
    if not all(map(math.isfinite, values)):
        raise ValueError('request values must be finite')
    start, stop, step, count, repeats = values
    if not 3.8 <= start <= stop <= 4.3:
        raise ValueError('frequency range must lie within 3.8--4.3 GHz')
    if step < .5 or step > 500:
        raise ValueError('step must be between 0.5 and 500 MHz')
    intervals = (stop-start)*1000/step
    if not math.isclose(intervals, round(intervals), abs_tol=1e-7):
        raise ValueError('frequency endpoints must lie on the requested grid')
    if count != int(count) or not 100 <= count <= 4000:
        raise ValueError('shots must be an integer from 100 to 4000')
    if repeats != int(repeats) or repeats < 0:
        raise ValueError('passes must be a nonnegative integer; zero means continuous')
    grid = np.round(start + np.arange(round(intervals)+1)*step/1000, 9).tolist()
    records = len(grid)*int(count)*6
    if records*diagonal.RECOVERY_US/60e6 > 30.:
        raise ValueError('workload exceeds 30 minutes of sequence time between reference boundaries; reduce band or shots')
    return dict(qubit='q3', frequencies_ghz=grid, frequency_points=len(grid),
                step_mhz=step, shots=int(count), passes=int(repeats),
                probe_us=list(diagonal.PROBES_US), pump_us=10.,
                probe_records_per_pass=records, readouts_per_record=2,
                active_reset=False, preparation='offline ground herald after loading',
                corrected_return_us=40., intercondition_recovery_us=diagonal.RECOVERY_US,
                science_sequence_minimum_minutes=records*diagonal.RECOVERY_US/60e6,
                reference_records_at_each_boundary=3*diagonal.REFERENCE_SHOTS,
                reference_policy='frozen initial axes; independent references at every pass boundary',
                timing_limit='40-us return plus herald readout, guard, zero-gain pulse and probe arrival',
                no_loss_site_selection=True,
                interpretation='hot-minus-cold conditional return and growth, not an individual TLS identification')


def tasks(request, *, pass_index):
    if int(pass_index) != pass_index or pass_index < 0:
        raise ValueError('pass index must be a nonnegative integer')
    grid = request['frequencies_ghz']
    # Chronological sweeps reverse to expose sweep-order artifacts.
    order = grid if pass_index % 2 == 0 else grid[::-1]
    result = []
    for frequency in order:
        arms = [dict(name=f'{state}_{delay:g}', pump_state=state, probe_state='g',
                     pump_ghz=frequency, probe_ghz=frequency, pump_us=10.,
                     probe_us=delay, interstage_extra_us=0.,
                     pump_prepare_after_return=False, probe_prepare_after_return=False)
                for delay in diagonal.PROBES_US for state in ('g', 'e')]
        if pass_index % 2:
            arms.reverse()
        result.append(dict(name=f'p{pass_index:05d}_f{round(frequency*1e6):07d}',
                           index=len(result), block=int(pass_index),
                           frequency_ghz=frequency, shots=request['shots'], conditions=arms))
    return result


def map_rows(cells, passes):
    boundaries = {p['pass_index']: p for p in passes}
    rows, seen = [], set()
    for cell in cells:
        task, summary = cell['task'], cell['summary']
        key = (task['block'], task['frequency_ghz'])
        if key in seen:
            raise ValueError('duplicate pass/frequency cell')
        seen.add(key)
        started, ended = (datetime.fromisoformat(cell[k]) for k in ('started_at', 'completed_at'))
        if started.tzinfo is None or ended.tzinfo is None or ended < started:
            raise ValueError('cell times must be timezone-aware and ordered')
        boundary = boundaries[task['block']]
        by_arm = {(c['pump_state'], c['probe_us']): c for c in summary['conditions']}
        for contrast in summary['contrasts']:
            delay = contrast['probe_us']
            hot, cold = (by_arm[(state, delay)] for state in ('e', 'g'))
            rows.append(dict(pass_index=task['block'], frequency_ghz=task['frequency_ghz'],
                realized_frequency_ghz=cell['realized_ghz'], probe_us=delay,
                cell_started_at=cell['started_at'], cell_completed_at=cell['completed_at'],
                pass_started_at=boundary['started_at'], pass_completed_at=boundary['completed_at'],
                controls=boundary['controls'],
                valid=bool(boundary['controls']=='valid' and contrast['valid']),
                enough_accepted=bool(contrast['valid']), shots=task['shots'],
                hot_accepted=hot['accepted'], cold_accepted=cold['accepted'],
                hot_acceptance=hot['acceptance'], cold_acceptance=cold['acceptance'],
                hot_pe=hot['conditional_pe'], cold_pe=cold['conditional_pe'],
                hot_all_shot_pe=hot['all_shot_pe'], cold_all_shot_pe=cold['all_shot_pe'],
                excess=contrast['excess'], excess_error=contrast['excess_error'],
                growth=contrast['growth'], growth_error=contrast['growth_error'],
                iq_excess=contrast['iq_excess'], iq_growth=contrast['iq_growth'],
                iq_growth_error=contrast['iq_growth_error']))
    return rows


def write_csv(path, rows):
    """Retry only publication if Windows holds the old CSV open."""
    if not rows:
        return
    path = Path(path)
    pending = path.with_suffix('.csv.pending')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for delay in (.05, .1, .2, .4, .8, 1., 1., None):
        try:
            os.replace(pending, path)
            return
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)


def map_arrays(request, rows, passes, *, metric):
    grid = {f: i for i, f in enumerate(request['frequencies_ghz'])}
    indices = {p['pass_index']: i for i, p in enumerate(passes)}
    delays = diagonal.PROBES_US if metric=='excess' else diagonal.PROBES_US[1:]
    arrays = {t: np.full((len(passes), len(grid)), np.nan) for t in delays}
    for row in rows:
        # Pending rows are explicitly provisional; failed references stay blank.
        if row['probe_us'] in arrays and row['enough_accepted'] and row['controls'] in ('valid', 'pending'):
            arrays[row['probe_us']][indices[row['pass_index']], grid[row['frequency_ghz']]] = row[metric]
    return arrays


def plot_results(folder, request, rows, passes):
    if not rows:
        return
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as dates
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import Normalize
    folder = Path(folder)
    grid = np.asarray(request['frequencies_ghz'])
    dx = request['step_mhz']/2000
    norm = Normalize(-.15, .15)  # Fixed signed scale across passes and sessions.
    def draw(metric, filename):
        arrays = map_arrays(request, rows, passes, metric=metric)
        fig, axes = plt.subplots(1, len(arrays), figsize=(5*len(arrays), 5),
                                 sharey=True, squeeze=False, constrained_layout=True)
        for axis, (delay, data) in zip(axes[0], arrays.items()):
            vertices, colors = [], []
            for i, boundary in enumerate(passes):
                start = dates.date2num(datetime.fromisoformat(boundary['started_at']))
                end_iso = boundary['completed_at'] or max(
                    (r['cell_completed_at'] for r in rows if r['pass_index']==boundary['pass_index']),
                    default=boundary['started_at'])
                end = dates.date2num(datetime.fromisoformat(end_iso))
                end = max(end, start+1/86400)
                for f, value in zip(grid, data[i]):
                    if not math.isfinite(value):
                        continue
                    vertices.append([(f-dx,start),(f+dx,start),(f+dx,end),(f-dx,end)])
                    colors.append(value)
            collection = PolyCollection(vertices, cmap='RdBu_r', norm=norm, edgecolors='none')
            collection.set_array(np.asarray(colors))
            axis.add_collection(collection)
            axis.set_xlim(grid[0]-dx, grid[-1]+dx)
            start = dates.date2num(datetime.fromisoformat(passes[0]['started_at']))
            end = dates.date2num(datetime.fromisoformat(passes[-1]['completed_at'] or rows[-1]['cell_completed_at']))
            axis.set_ylim(start, max(end, start+1/86400))
            locator = dates.AutoDateLocator()
            axis.yaxis.set_major_locator(locator)
            axis.yaxis.set_major_formatter(dates.ConciseDateFormatter(locator,tz=timezone.utc))
            axis.set(xlabel='Frequency (GHz)', title=f'{delay:g} µs probe')
            fig.colorbar(collection, ax=axis, extend='both', label=('Hot − cold excited fraction' if metric=='excess'
                else 'Hot − cold growth above 0.1 µs'))
        axes[0,0].set_ylabel('Wall-clock time (UTC)')
        pending = any(p['controls']=='pending' for p in passes)
        fig.suptitle('q3 afterglow: '+('excess re-excitation' if metric=='excess' else 'growth control')+
                     (' — provisional references' if pending else '')+
                     '\nEach strip is one sequential pass; point timestamps are saved in CSV', fontsize=12)
        fig.savefig(folder/filename, dpi=160)
        plt.close(fig)
    draw('excess', 'afterglow_vs_wall_clock.png')
    draw('growth', 'afterglow_growth_vs_wall_clock.png')
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, constrained_layout=True)
    latest = passes[-1]['pass_index']
    for delay in diagonal.PROBES_US:
        points = sorted((r for r in rows if r['pass_index']==latest and r['probe_us']==delay
                         and r['enough_accepted'] and r['controls']!='invalid'), key=lambda r:r['frequency_ghz'])
        for axis, metric in zip(axes, ('excess', 'growth')):
            if metric=='growth' and delay==.1:
                continue
            axis.errorbar([r['frequency_ghz'] for r in points], [r[metric] for r in points],
                          yerr=[r[metric+'_error'] for r in points], fmt='.', label=f'{delay:g} µs')
    for axis in axes:
        axis.axhline(0., color='black', linewidth=.8)
        axis.grid(alpha=.25)
        axis.legend()
    axes[0].set(ylabel='Hot − cold excited fraction', title=f'q3 afterglow pass {latest+1} ({passes[-1]["controls"]} references)')
    axes[1].set(xlabel='Frequency (GHz)', ylabel='Growth above 0.1 µs')
    fig.savefig(folder/'afterglow_latest_spectrum.png', dpi=160)
    plt.close(fig)


def finalize(folder, manifest, cells, boundaries, request, soc, save, original_error):
    """Stop hardware first; preserve acquisition errors if derived output fails."""
    diagonal.abort_and_record(soc, manifest)
    manifest['completed_at'] = now()
    try:
        save(folder/'manifest.json', manifest)
        if cells:
            rows = map_rows(cells, boundaries)
            write_csv(folder/'afterglow_vs_wall_clock.csv', rows)
            save(folder/'summary.json', dict(rows=rows, passes=boundaries,
                status=manifest['status'], interpretation=request['interpretation'],
                lifetime_fitting=False))
            plot_results(folder, request, rows, boundaries)
    except BaseException as exc:
        manifest['finalization_error'] = f'{type(exc).__name__}: {exc}'
        try:
            save(folder/'manifest.json', manifest)
        except BaseException:
            pass
        if original_error is None:
            raise
        if hasattr(original_error, 'add_note'):
            original_error.add_note('Output finalization also failed: '+manifest['finalization_error'])


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, progress=True, **parameters):
    request = plan(**parameters)  # Validate before proxy creation or hardware access.
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    folder = data_root/'q3'/('q3_afterglow_time_map_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    path = folder/'manifest.json'
    manifest = dict(schema='q3.afterglow-time-map.v1', status='initializing', plan=request,
                    created_at=now(), completed=[], passes=[], references={},
                    correction_sha256=localizer.CORRECTION_SHA256,
                    commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=Path(__file__).parent, text=True).strip())
    for name in ('TLSAfterglowTimeMap.py','TLSAfterglowDiagonal.py','TLSPumpProbeHeralded.py','Q3QuasiparticlePumping.py'):
        source = Path(__file__).with_name(name)
        shutil.copy2(source, folder/name)
        manifest[name+'_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    def save(destination, value):
        # Existing checkpoint access-conflict messages go to the session log.
        with (folder/'checkpoint.log').open('a', encoding='utf-8') as log, redirect_stdout(log):
            qp.save_json(destination, value)
    save(path, manifest)
    from tqdm import tqdm
    from . import FivePointApplesToApples as five, TLSSpectroscopy as tls
    from . import TLSPumpProbeWidePassiveScan as wide
    from .ThreePointApplesToApples import _integer_dc_grid
    from ..active_reset_OPX.integration import _run_program, runtime_bundle
    soc, cells, boundaries = None, [], manifest['passes']
    try:
        with noise.q3_context(tls, data_root), localizer.scan_environment(correction):
            five.install_scan_calibration(tls)
            grid = request['frequencies_ghz']
            gains, realized = _integer_dc_grid(dict(wide.parameters(), freq_step_mhz=request['step_mhz']), np.asarray(grid), tls)
            lookup, realized_lookup = dict(zip(grid,map(int,gains))), dict(zip(grid,map(float,realized)))
            compensation = tls._load_correction(str(correction), str(data_root))
            cfg = diagonal.science_config(tls, compensation)
            bundle = runtime_bundle(cfg)
            soc, soccfg = tls.makeProxy()
            save(folder/'board_configuration.json', soccfg.get_cfg())
            save(folder/'config.json', cfg)
            manifest['flux_grid'] = [dict(requested_ghz=f, realized_ghz=realized_lookup[f], gain=lookup[f]) for f in grid]
            def build(task):
                with (folder/'compile.log').open('a', encoding='utf-8') as log, redirect_stdout(log):
                    configs = [diagonal.heralded.arm_config(cfg,dict(a,shots=task['shots']),lookup)
                               for a in task['conditions']]
                    return TimeMapProgram(soccfg,configs,bundle.payload,bundle.loop)
            def references(phase, axes=None):
                print('SS cal: paired herald and final readout', flush=True)
                raw = []
                for arm in diagonal.heralded.reference_arms(grid[len(grid)//2], phase=phase):
                    task = dict(name=arm['name'], shots=diagonal.REFERENCE_SHOTS, conditions=[arm])
                    records, _ = acquire(task)
                    raw.append(records)
                report = diagonal.heralded.assess_pre_references(*raw)
                if axes is not None:
                    report['frozen_axis_validation'] = diagonal.heralded.validate_pair_against_axes(axes, *raw)
                manifest['references'][phase] = report
                save(path, manifest)
                valid = report['valid'] if axes is None else report['frozen_axis_validation']['valid']
                print('SS cal complete.' if valid else 'SS cal reference checks failed.', flush=True)
                return report, raw
            def acquire(task, callback=None):
                program = build(task)
                started = now()
                manifest['current'] = dict(task=task, started_at=started)
                save(path, manifest)
                save(folder/(task['name']+'.json'), dict(task=task, preflight=noise.preflight(program)))
                try:
                    records = _run_program(soc, program, 60., cfg, total_shots=task['shots'], progress=callback)
                except BaseException as exc:
                    diagonal.abort_and_record(soc, manifest)
                    partial = getattr(exc, 'partial_records', program.received_records)
                    count = len(task['conditions'])
                    partial = partial[:len(partial)//count*count]
                    try:
                        np.savez_compressed(folder/(task['name']+'.partial.npz'), words=diagonal.words_from_records(partial))
                    except Exception as write_error:
                        manifest['partial_write_error'] = f'{type(write_error).__name__}: {write_error}'
                    raise
                ended = now()
                words = diagonal.words_from_records(records)
                np.savez_compressed(folder/(task['name']+'.npz'), words=words)
                if len(records)!=task['shots']*len(task['conditions']):
                    raise RuntimeError('incomplete paired IQ acquisition')
                manifest['current'].update(completed_at=ended, raw_file=task['name']+'.npz')
                save(folder/(task['name']+'.json'), dict(task=task,preflight=noise.preflight(program),
                    started_at=started,completed_at=ended,raw_file=task['name']+'.npz'))
                save(path, manifest)
                return records, dict(started_at=started, completed_at=ended, words=words)
            # Preflight both orders across the entire requested fixed grid.
            manifest['preflight'] = []
            for index in (0,1):
                for task in tasks(request, pass_index=index):
                    manifest['preflight'].append(dict(name=task['name'], **noise.preflight(build(task))))
            save(path, manifest)
            initial, raw = references('boundary_00000')
            if not initial['valid'] or initial['axes'] is None:
                manifest.update(status='complete_invalid_initial_references', current=None)
                return folder
            axes = initial['axes']
            ref_raw = dict(zip(('ref_g_boundary_00000','ref_e_boundary_00000','ref_final_e_boundary_00000'),raw))
            levels = diagonal.reference_levels(ref_raw, axes, 'boundary_00000')
            index = 0
            while request['passes']==0 or index<request['passes']:
                boundary = dict(pass_index=index, started_at=now(), completed_at=None, controls='pending')
                boundaries.append(boundary)
                manifest['status'] = 'acquiring'
                pass_tasks = tasks(request, pass_index=index)
                with tqdm(total=request['probe_records_per_pass'], desc=f'Afterglow pass {index+1}',
                          unit='shot', disable=not progress,
                          bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                    for task in pass_tasks:
                        offset = task['index']*request['shots']*6
                        def update(done, total):
                            bar.update(max(0, offset+int(done)*6-bar.n))
                        _, acquired = acquire(task, update)
                        cell = dict(task=task, summary=diagonal.summarize_program(acquired['words'],task,axes,levels),
                                    started_at=acquired['started_at'], completed_at=acquired['completed_at'],
                                    realized_ghz=realized_lookup[task['frequency_ghz']], raw_file=task['name']+'.npz')
                        cells.append(cell)
                        manifest['completed'].append(cell)
                        save(path, manifest)
                        write_csv(folder/'afterglow_vs_wall_clock.csv', map_rows(cells,boundaries))
                boundary['completed_at'] = now()  # Science interval; excludes subsequent references.
                post, _ = references(f'boundary_{index+1:05d}', axes)
                boundary['controls'] = 'valid' if post['frozen_axis_validation']['valid'] else 'invalid'
                rows = map_rows(cells, boundaries)
                write_csv(folder/'afterglow_vs_wall_clock.csv', rows)
                save(folder/'summary.json', dict(rows=rows, passes=boundaries,
                    interpretation=request['interpretation'], lifetime_fitting=False))
                plot_results(folder, request, rows, boundaries)
                manifest['current'] = None
                save(path, manifest)
                if boundary['controls']=='invalid':
                    manifest['status'] = 'complete_controls_uncertain'
                    break
                index += 1
            else:
                manifest['status'] = 'complete'
    except BaseException as exc:
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        finalize(folder,manifest,cells,boundaries,request,soc,save,sys.exc_info()[1])
    return folder


def main(argv=None):
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--data-root', default=str(localizer.DATA_ROOT))
    parser.add_argument('--correction-json')
    parser.add_argument('--freq-start', type=float, default=4.)
    parser.add_argument('--freq-stop', type=float, default=4.05)
    parser.add_argument('--step-mhz', type=float, default=2.)
    parser.add_argument('--shots', type=int, default=400)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--passes', type=int, default=1)
    group.add_argument('--continuous', action='store_true')
    args = parser.parse_args(argv)
    parameters = dict(freq_start=args.freq_start,freq_stop=args.freq_stop,step_mhz=args.step_mhz,
                      shots=args.shots,passes=0 if args.continuous else args.passes)
    if args.plan or not args.run:
        print(json.dumps(plan(**parameters),indent=2))
    else:
        folder = run(data_root=args.data_root,correction_json=args.correction_json,
                     progress=not args.quiet,**parameters)
        status = json.loads((folder/'manifest.json').read_text())['status']
        print(f'Afterglow scan {status}: {folder}',flush=True)
        if status!='complete':
            return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
