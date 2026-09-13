"""Reproduce the offline audit/fit from a frozen, hashed numerical snapshot.

Usage: python -m fluxpred.run_offline --out reports/neutral_flux
This module has no acquisition entry point. It writes local diagnostic artifacts.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .core import Command, Filter, compare_commands, render
from .fit import Trace, fit_plant, fit_inverse, interpolate_plant, plant_response
from .offline import blocked_plant_score, forecast, common_horizon
from .validation import flatness, acceptance, build_shot
from . import qick, qua

TRAIN_IDS = ('12_57_45', '12_18_02', '13_21_04')
VALIDATION_IDS = ('14_22_26', '14_30_44', '14_39_01')
EMISSION_NS = 2000
INVERSE_REGULARIZATION = 1e-5
TAU_BANKS = ([8000, 32000, 128000], [8000, 24000, 64000, 192000])


def _one(entries, tag):
    found = [entry for entry in entries if tag in entry['id']]
    if len(found) != 1:
        raise ValueError(f"expected exactly one frozen trace matching {tag}")
    return found[0]


def _trace(entry, *, include_first=False, smooth=False):
    t = np.array(entry['time_ns'], float)
    y = np.array(entry['response_smooth' if smooth else 'response_raw'], float)
    support = np.array(entry['support'], bool) & np.isfinite(y)
    if not include_first:
        support &= t >= 5000
    return Trace(t, y, Command(**entry['applied_command']), support, entry['probe_ns'])


def _frequency(entry, normalized_response):
    p = entry['flux_fit_params']
    voltage = entry['park']+(entry['target']-entry['park'])*np.asarray(normalized_response)
    phase = np.pi*(voltage-p['phase_offset_volts'])/p['period_volts']
    ej = p['EJmax']*np.sqrt(np.cos(phase)**2+p['d']**2*np.sin(phase)**2)
    return 1000*(np.sqrt(8*ej*p['Ec'])-p['Ec']+p.get('tilt_slope', 0)*voltage)


def _metrics(entry, y, support=None):
    tr = _trace(entry)
    return flatness(tr.time_ns, _frequency(entry, y), tr.support if support is None else support)


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _select(traces):
    selection = []
    for tau in TAU_BANKS:
        for reg in (1e-5, 1e-4, 1e-3):
            try:
                score = blocked_plant_score(traces, tau, regularization=reg)
                selection.append(dict(taus_ns=tau, regularization=reg, blocked_raw_rms=score))
            except ValueError as exc:
                selection.append(dict(taus_ns=tau, regularization=reg, rejected=str(exc)))
    successful = [item for item in selection if 'blocked_raw_rms' in item]
    if not successful:
        raise ValueError('no identifiable stable plant in the prespecified model family')
    return min(successful, key=lambda row: row['blocked_raw_rms']), selection


def run(evidence_path, output):
    evidence_path, output = Path(evidence_path), Path(output)
    if str(output.resolve()).startswith('/Volumes/'):
        raise ValueError("write diagnostics in a local workspace, never the measured-data volume")
    document = json.loads(evidence_path.read_text())
    if document['schema_version'] != 1:
        raise ValueError('unsupported evidence schema')
    entries = document['traces']
    train_entries = [_one(entries, tag) for tag in TRAIN_IDS]
    test_entries = [_one(entries, tag) for tag in VALIDATION_IDS]
    traces = [_trace(entry) for entry in train_entries]
    scale = max(entry['target']-entry['park'] for entry in train_entries)
    amplitudes = np.array([(entry['target']-entry['park'])/scale for entry in train_entries])

    # Prespecified small bank/regularization grid. No use of the later dataset.
    chosen, selection = _select(traces)
    tau, reg = chosen['taus_ns'], chosen['regularization']
    common = fit_plant(traces, tau, regularization=reg)
    local = [fit_plant([trace], tau, regularization=reg) for trace in traces]
    lti = fit_inverse([common['coefficients']], tau, sample_ns=EMISSION_NS, regularization=INVERSE_REGULARIZATION)['model']
    local_inverses = [fit_inverse([fit['coefficients']], tau, sample_ns=EMISSION_NS, regularization=INVERSE_REGULARIZATION)['model'] for fit in local]
    conditioned = Filter(tau, amplitudes, [m.coefficients[0] for m in local_inverses])

    # LOAO predictions never estimate a plant from the held-out amplitude.
    loao = []
    for index, (entry, trace, amplitude) in enumerate(zip(train_entries, traces, amplitudes)):
        keep = [j for j in range(3) if j != index]
        fold_choice, _ = _select([traces[j] for j in keep])
        fold_tau, fold_reg = fold_choice['taus_ns'], fold_choice['regularization']
        pooled = fit_plant([traces[j] for j in keep], fold_tau, regularization=fold_reg)['coefficients']
        inverse = fit_inverse([pooled], fold_tau, sample_ns=EMISSION_NS, regularization=INVERSE_REGULARIZATION)['model']
        fold_plants = [fit_plant([traces[j]], fold_tau, regularization=fold_reg)['coefficients'] for j in keep]
        fold_inverses = [fit_inverse([plant], fold_tau, sample_ns=EMISSION_NS, regularization=INVERSE_REGULARIZATION)['model'] for plant in fold_plants]
        c, outside = interpolate_plant(amplitudes[keep], [m.coefficients[0] for m in fold_inverses], amplitude)
        a, _ = interpolate_plant(amplitudes[keep], fold_plants, amplitude)
        conditioned_heldout = Filter(fold_tau, [1], [c])
        loao.append({'id': entry['id'], 'amplitude': amplitude, 'outside_training_hull': outside,
                     'boundary_rule': 'constant endpoint diagnostic; not validated extrapolation',
                     'nested_train_only_selection': fold_choice,
                     'lti_forecast': _metrics(entry, forecast(inverse, amplitude, pooled, trace, sample_ns=EMISSION_NS)),
                     'conditioned_forecast': _metrics(entry, forecast(conditioned_heldout, amplitude, a, trace, sample_ns=EMISSION_NS))})

    comparison, forecasts = [], {}
    for index, entry in enumerate(test_entries):
        trace, amplitude = _trace(entry), amplitudes[index]
        lti_y = forecast(lti, amplitude, common['coefficients'], trace, sample_ns=EMISSION_NS)
        conditioned_y = forecast(conditioned, amplitude, local[index]['coefficients'], trace, sample_ns=EMISSION_NS)
        old_model = plant_response(trace.command, trace.time_ns, tau, common['coefficients'], probe_ns=trace.probe_ns)
        raw_frequency = np.array(entry['raw_frequency_mhz'], float)
        saved = np.array(entry['smooth_frequency_mhz'], float)
        all_support = np.array(entry['support'], bool)
        comparison.append({'id': entry['id'], 'target_native': entry['target'], 'amplitude': amplitude,
            'piecewise_saved_all_supported': flatness(trace.time_ns, saved, all_support, smooth_window=1),
            'piecewise_raw_smoothed_same_support': flatness(trace.time_ns, raw_frequency, trace.support),
            'shared_lti_forecast': _metrics(entry, lti_y),
            'conditioned_forecast': _metrics(entry, conditioned_y),
            'plant_discrepancy_raw_rms_normalized': float(np.std((trace.response-old_model)[trace.support]))})
        forecasts[entry['id']] = {'time_ns': trace.time_ns, 'support': trace.support,
            'piecewise_frequency_mhz': raw_frequency,
            'lti_forecast_frequency_mhz': _frequency(entry, lti_y),
            'conditioned_forecast_frequency_mhz': _frequency(entry, conditioned_y)}

    # Synthetic model-only cancellation is reported separately from transported
    # measured discrepancy; it cannot be an experimental acceptance gate.
    model_only = []
    for index, amp in enumerate(amplitudes):
        for name, model in [('lti', lti), ('conditioned', conditioned)]:
            cmd, _ = render(model, [(amp, 600000)], sample_ns=EMISSION_NS)
            response = plant_response(Command(cmd.edges_ns, cmd.values/amp), traces[index].time_ns, tau, local[index]['coefficients'], probe_ns=500, freeze_probe=False)
            model_only.append(dict(amplitude=amp, inverse=name, metrics=_metrics(train_entries[index], response)))

    # Same normalized artifact on both controllers. Profile clocks are examples,
    # not inferred q3 firmware: the measurement snapshots do not save soccfg.
    emitter = []
    for clock in (4.0, 2.5):
        for hold in (1000, 13004, 100000, 497000):
            shot = build_shot(conditioned, amplitude=1, hold_ns=hold, recovery_ns=1600000, sample_ns=EMISSION_NS)
            cmd = shot['command']
            qplan = qick.compile_command(cmd, park_gain=-25146, scale_gain=10396, clock_ns=clock, max_instructions=16384)
            uplan = qua.compile_command(cmd, park_v=train_entries[0]['park'], scale_v=scale)
            qc, uc = qick.reconstruct_command(qplan), qua.reconstruct_command(uplan)
            qa, ua = common_horizon(qc, uc, terminal_tolerance=1e-4)
            emitter.append({'profile_note': 'illustrative fabric clock; actual q3 soccfg absent', 'qick_clock_ns': clock,
                'hold_ns': hold, 'mismatch': compare_commands(qa, ua),
                'horizon_difference_ns': float(qc.edges_ns[-1]-uc.edges_ns[-1]),
                'qick_instruction_allowance': qplan.instruction_estimate, 'qua_source_operations': uplan.instruction_estimate,
                'terminal_filter_tail_bound': shot['terminal_tail_bound'], 'hardware_compiled': False})

    # Same-command repeated center scans bound reproducibility, not pure noise.
    repeats = []
    pairs = [('11_47_02', '12_18_02'), ('14_30_44', '14_54_13')]
    for first, second in pairs:
        if not any(second in item['id'] for item in entries):
            continue
        a, b = _one(entries, first), _one(entries, second)
        if a['applied_command'] != b['applied_command']:
            continue
        t = np.array(a['time_ns']); raw_a = np.array(a['raw_frequency_mhz'], float); raw_b = np.array(b['raw_frequency_mhz'], float)
        valid = np.isfinite(raw_a) & np.isfinite(raw_b) & np.array(a['support']) & np.array(b['support'])
        late = valid & (t >= 300000)
        difference = raw_a-np.mean(raw_a[late])-(raw_b-np.mean(raw_b[late]))
        repeats.append({'first': a['id'], 'second': b['id'],
                        'raw_difference_rms_mhz': float(np.sqrt(np.mean(difference[valid]**2))),
                        'difference_metrics': flatness(t, difference, valid),
                        'note': 'noise, ridge bias and real drift confounded; not a noise confidence interval'})

    first_sample_sensitivity = []
    for entry, local_fit in zip(train_entries, local):
        including = fit_plant([_trace(entry, include_first=True)], tau, regularization=reg)
        first_sample_sensitivity.append({'id': entry['id'], 'coefficients_from_5us': local_fit['coefficients'],
                                        'coefficients_including_1us': including['coefficients']})
    audit = []
    for entry in entries:
        tr = _trace(entry, include_first=True)
        audit.append({'id': entry['id'], 'qubit': entry['qubit'], 'source_sha256': entry['source_sha256'],
                      'metrics': flatness(tr.time_ns, np.array(entry['smooth_frequency_mhz'], float), entry['support'], smooth_window=1),
                      'sensitivity': entry['sensitivity']})
    q3_entries = [entry for entry in entries if entry['qubit'] == 'q3']
    q3_train = _one(q3_entries, '00_53_50')
    q3_choice, q3_selection = _select([_trace(q3_train)])
    q3_plant = fit_plant([_trace(q3_train)], q3_choice['taus_ns'], regularization=q3_choice['regularization'])
    q3_model = fit_inverse([q3_plant['coefficients']], q3_choice['taus_ns'], sample_ns=EMISSION_NS, regularization=INVERSE_REGULARIZATION)['model']
    q3_comparison = [{'id': entry['id'], 'used_in_fit': entry['id'] == q3_train['id'],
        'forecast': _metrics(entry, forecast(q3_model, 1, q3_plant['coefficients'], _trace(entry), sample_ns=EMISSION_NS))}
        for entry in q3_entries]
    gates = acceptance([row['conditioned_forecast'] for row in comparison], held_out_supported=False)
    gates['emission_sample_ns'] = EMISSION_NS
    gates['snapshot_sha256'] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    gates['training_ids'] = TRAIN_IDS
    gates['validation_ids'] = VALIDATION_IDS
    gates['reasons'] = ['conditional residual-transport forecast is not a measured correction',
                        'unresolved onset below 5 us and unknown analog initial history',
                        'no uncorrected band-edge amplitude scans or shot-resolved noise estimates',
                        'actual controller clock, compiler memory and dispatch timing not validated']
    report = {'schema_version': 1, 'snapshot_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        'emission_sample_ns': EMISSION_NS, 'inverse_regularization': INVERSE_REGULARIZATION,
        'training_ids': TRAIN_IDS, 'validation_ids': VALIDATION_IDS,
        'metric_definition': 'raw estimates smoothed ONCE17 samples; RMS about late mean>=300us; early<=21us; forecasts only>=5us',
        'selection': selection, 'selected': chosen, 'shared_plant': common,
        'amplitude_plants': local, 'amplitudes': amplitudes, 'loao': loao,
        'later_comparison': comparison, 'model_only': model_only, 'emitter_comparison': emitter,
        'repeat_comparison': repeats, 'first_sample_sensitivity': first_sample_sensitivity,
        'trace_audit': audit, 'gates': gates,
        'q3_single_amplitude': {'selection': q3_selection, 'selected': q3_choice, 'plant': q3_plant, 'model': q3_model.to_dict(), 'comparisons': q3_comparison},
        'q3_scope': 'one measured amplitude only; no LOAO or cross-band validation; q5 artifact emission on QICK is a normalized-command witness, not a q3 calibration'}
    output.mkdir(parents=True, exist_ok=True)
    for name, model in [('shared_lti_candidate', lti), ('conditioned_candidate', conditioned)]:
        candidate = {'schema_version': 1, 'model': model.to_dict(),
            'coordinate': {'park': train_entries[0]['park'], 'scale': scale, 'unit': 'V'}, 'evidence': gates}
        (output/f'{name}.json').write_text(json.dumps(_jsonable(candidate), indent=2, allow_nan=False)+'\n')
    q3_candidate = {'schema_version': 1, 'model': q3_model.to_dict(),
        'coordinate': {'park': q3_train['park'], 'scale': q3_train['target']-q3_train['park'], 'unit': 'DAC_gain'},
        'evidence': {**gates, 'training_ids': [q3_train['id']], 'validation_ids': [e['id'] for e in q3_entries if e['id'] != q3_train['id']],
                    'reasons': ['single q3 amplitude; changed-command forecasts fail; nominal emitted history only',
                                       'no actual controller compilation or physical settling verification']}}
    (output/'q3_single_amplitude_candidate.json').write_text(json.dumps(_jsonable(q3_candidate), indent=2, allow_nan=False)+'\n')
    # Nulls explicitly represent unsupported samples in forecast arrays.
    for row in forecasts.values():
        for key, value in list(row.items()):
            if isinstance(value, np.ndarray) and value.dtype != bool:
                row[key] = [float(x) if np.isfinite(x) else None for x in value]
    (output/'comparison.json').write_text(json.dumps(_jsonable(report), indent=2, allow_nan=False)+'\n')
    (output/'forecast_traces.json').write_text(json.dumps(_jsonable(forecasts), indent=2, allow_nan=False)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', default='reports/neutral_flux/input_traces.json')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = run(args.evidence, args.out)
    print(json.dumps(_jsonable({key: result[key] for key in ['selected', 'later_comparison', 'gates']}), indent=2))


if __name__ == '__main__':
    main()
