import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from .core import Command
from .validation import build_shot, load_candidate
from . import qua, qick


def legacy_round_trip(document, *, hold_ns, recovery_ns):
    edges = np.asarray(document['segment_edges_ns'], float)
    levels = np.asarray(document['multipliers'], float)
    if edges.shape != levels.shape or edges.ndim != 1 or not len(edges):
        raise ValueError('invalid legacy step table')
    step = Command(np.r_[edges, max(edges[-1], hold_ns+recovery_ns)+4000], levels)
    if not np.isfinite(hold_ns) or not np.isfinite(recovery_ns) or hold_ns <= 0 or recovery_ns <= 0:
        raise ValueError('positive finite hold and recovery required')
    if recovery_ns < edges[-1]:
        raise ValueError('legacy recovery must cover the full step-table horizon')
    end = hold_ns+recovery_ns
    bounds = np.unique(np.r_[0, edges[edges < end], hold_ns, (edges+hold_ns)[edges+hold_ns < end], end])
    t = (bounds[:-1]+bounds[1:])/2
    def value_at(time):
        index = np.maximum(np.searchsorted(step.edges_ns, time, side='right')-1, 0)
        return np.where(time >= 0, step.values[index], 0)
    value = value_at(t)-value_at(t-hold_ns)
    if abs(value[-1]) > 1e-12:
        bounds = np.r_[bounds, end+4000]
        value = np.r_[value, 0]
    return Command(bounds, value)


def compile_bank(commands, *, backend, park, scale, max_instructions, clock_ns=None):
    if backend not in {'qick', 'qua'}:
        raise ValueError('backend must be qick or qua')
    plans = []
    for command in commands:
        if backend == 'qick':
            if clock_ns is None:
                raise ValueError('actual QICK fabric clock_ns is required; never infer it from the model')
            plan = qick.compile_command(command, park_gain=park, scale_gain=scale, clock_ns=clock_ns,
                                        max_instructions=max_instructions)
        else:
            plan = qua.compile_command(command, park_v=park, scale_v=scale, max_instructions=max_instructions)
        plans.append(plan)
    total = sum(plan.instruction_estimate for plan in plans)
    if total > max_instructions:
        raise ValueError(f'bank instruction allowance {total} exceeds {max_instructions}; prepare separate conditions')
    return plans


def prepare(*, mode, backend, park, scale, holds_ns, recovery_ns, diagnostic=False,
            model_path=None, legacy_path=None, amplitude=1, max_instructions=16384, clock_ns=None):
    if mode not in {'neutral', 'legacy-piecewise', 'uncorrected'}:
        raise ValueError('select neutral, legacy-piecewise or uncorrected explicitly')
    if backend not in {'qua', 'qick'}:
        raise ValueError('invalid backend')
    if not holds_ns or not np.isfinite(amplitude) or not 0 < amplitude <= 1:
        raise ValueError('nonempty holds and normalized amplitude in (0,1] required')
    if not np.isfinite(recovery_ns) or recovery_ns <= 0 or any(not np.isfinite(h) or h <= 0 for h in holds_ns):
        raise ValueError('positive finite hold/recovery required')
    candidate = None
    if mode == 'neutral':
        unit = 'V' if backend == 'qua' else 'DAC_gain'
        model, candidate = load_candidate(model_path, park=park, scale=scale, unit=unit,
                                           require_scientific_gate=not diagnostic)
    elif not diagnostic:
        raise ValueError('fallback plans require diagnostic mode; no acquisition path is provided')
    if mode == 'legacy-piecewise':
        legacy = json.loads(Path(legacy_path).read_text())
        if legacy.get('success') is not True or legacy.get('multiplier_clipped', False):
            raise ValueError('legacy candidate must be successful and unclipped')
    commands, shots = [], []
    for hold in holds_ns:
        if mode == 'neutral':
            shot = build_shot(model, amplitude=amplitude, hold_ns=hold, recovery_ns=recovery_ns,
                               sample_ns=candidate['evidence'].get('emission_sample_ns', model.resolution_ns))
            command = shot['command']
            details = {'omitted_inverse_command_tail_bound': shot['terminal_tail_bound'],
                       'physical_plant_settling_verified': False}
        elif mode == 'legacy-piecewise':
            unit_command = legacy_round_trip(legacy, hold_ns=hold, recovery_ns=recovery_ns)
            command = Command(unit_command.edges_ns, amplitude*unit_command.values)
            details = {'legacy_note': 'existing table, causal two-edge playback; original legacy experiment behavior unchanged'}
        else:
            command = Command([0, hold, hold+recovery_ns], [amplitude, 0])
            details = {}
        commands.append(command)
        shots.append({'hold_ns': hold, 'normalized_command': command.to_dict(), **details})
    plans = compile_bank(commands, backend=backend, park=park, scale=scale,
                         max_instructions=max_instructions, clock_ns=clock_ns)
    for shot, plan in zip(shots, plans):
        shot['backend_plan'] = asdict(plan)
    return {'schema_version': 1, 'mode': mode, 'backend': backend, 'diagnostic': diagnostic,
            'hardware_ready': False, 'acquisition_performed': False,
            'instruction_allowance_sum': sum(p.instruction_estimate for p in plans),
            'requires': ['verified calibration coordinate and physical park after active reset',
                         'full controller compilation and memory/dispatch/timing checks',
                         'queue drive/probe on parallel timeline before final align'],
            'shots': shots}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['neutral', 'legacy-piecewise', 'uncorrected'], required=True)
    parser.add_argument('--backend', choices=['qick', 'qua'], required=True)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--legacy', type=Path)
    parser.add_argument('--park', type=float, required=True)
    parser.add_argument('--scale', type=float, required=True)
    parser.add_argument('--amplitude', type=float, default=1)
    parser.add_argument('--holds-ns', type=float, nargs='+', required=True)
    parser.add_argument('--recovery-ns', type=float, default=1600000)
    parser.add_argument('--clock-ns', type=float)
    parser.add_argument('--max-instructions', type=int, default=16384)
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if str(args.out.resolve()).startswith('/Volumes/'):
        raise ValueError('write plans in the local workspace, never the data volume')
    result = prepare(mode=args.mode, backend=args.backend, park=args.park, scale=args.scale,
        holds_ns=args.holds_ns, recovery_ns=args.recovery_ns, model_path=args.model, legacy_path=args.legacy,
        amplitude=args.amplitude, max_instructions=args.max_instructions, clock_ns=args.clock_ns, diagnostic=args.diagnostic)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def formatted(value, depth=0):
        if isinstance(value, dict):
            return '{\n'+',\n'.join('  '*(depth+1)+json.dumps(k)+': '+formatted(v, depth+1) for k, v in value.items())+'\n'+'  '*depth+'}'
        if isinstance(value, (list, tuple)) and any(isinstance(v, (dict, list, tuple)) for v in value):
            return '[\n'+',\n'.join('  '*(depth+1)+formatted(v, depth+1) for v in value)+'\n'+'  '*depth+']'
        return json.dumps(value, allow_nan=False)
    args.out.write_text(formatted(result)+'\n')
    print(f"Wrote {len(result['shots'])} diagnostic shot plans to {args.out}; hardware_ready=false")


if __name__ == '__main__':
    main()
