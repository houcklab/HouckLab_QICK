"""Resolver from qubit_parameters.json to a flat experiment cfg dict.

Pipeline:
    qubit_parameters.json  ->  build_config(**kwargs)  ->  cfg dict

The JSON replaces the legacy per-stage *_params.py / Qubit_Parameters dict structure
entirely. There is no intermediate Qubit_Parameters object exposed.

Caller specifies which named entries to use from each pipeline-stage namespace:
    build_config(
        Qubit_Readout  = [3, 4, 5, 6, 7, 8],     # required: list of readout-entry labels
        Readout_Point  = 'readout_3800',         # REQUIRED: key in readout_groups (no default)
        Qubit_Pulse    = ['3_3800+', '6_3800+'], # optional: list of drive-entry labels
        Ramp_State     = '6Q_right_half_mid_k',  # optional: key in ramp_groups
        Dynamics_Point = '34',                   # optional: key in dynamics_groups
    )
"""
import json
import warnings
from pathlib import Path

from WorkingProjects.triangle_lattice_quench.MUXInitialize import BaseConfig

JSON_PATH = Path(__file__).parent / 'Run_Experiments' / 'Qubit_Parameters' / 'qubit_parameters.json'


def _deref_base(value, base_params):
    """If `value` names an entry in base_params, return that array. Else value unchanged."""
    if isinstance(value, str) and value in base_params:
        return list(base_params[value])
    return value


def _apply_recipe(base_arr, method, recipe_arg, recipe_kwargs):
    """Apply an FF_gains-like recipe (subsys / set / add) to base_arr. Returns a plain list."""
    base = list(base_arr)
    if method == 'subsys':
        det = recipe_kwargs.get('det', 0)
        out = [b + det for b in base]
        for q in recipe_arg:
            out[q - 1] = base[q - 1]
        return out
    if method == 'set':
        out = list(base)
        for q_name, val in recipe_arg.items():
            out[int(q_name[1:]) - 1] = val
        return out
    if method == 'add':
        out = list(base)
        for q_name, val in recipe_arg.items():
            out[int(q_name[1:]) - 1] += val
        return out
    raise ValueError(f"Unknown _recipe method: {method!r}")


# ---------------------------------------------------------------------------
# Per-stage resolvers. Each returns a FLAT dict (Readout / Qubit sub-dicts are
# spread to top level for convenient indexing in the build_config comprehensions).
# ---------------------------------------------------------------------------

def _resolve_readout(jd, name, group_name):
    """Returns flat: {Frequency, Gain, Readout_Time, ADC_Offset, Readout_FF, Pulse_FF}.

    Looks up `name` inside the readout group `group_name`.
    """
    base = jd.get('base_params', {})
    group = jd['readout_groups'][group_name]
    if name in group.get('entries', {}):
        entry = group['entries'][name]
        return {
            **entry.get('Readout', {}),
            'Readout_FF': list(_deref_base(group.get('Readout_FF'), base)),
            'Pulse_FF':   list(_deref_base(group.get('Pulse_FF'),   base)),
        }
    raise KeyError(f"readout entry {name!r} not found in readout group {group_name!r}")


def _resolve_drive(jd, name):
    """Returns flat: {Frequency, Gain, sigma, Pulse_FF}.

    Searches drive_groups first, then readout_groups (so a readout's associated
    drive is reachable through Qubit_Pulse even when defined alongside its readout).
    """
    base = jd.get('base_params', {})
    for ns in ('drive_groups', 'readout_groups'):
        for group in jd.get(ns, {}).values():
            if name in group.get('entries', {}):
                entry = group['entries'][name]
                if 'Pulse_FF_abs' in entry:
                    Pulse_FF = list(entry['Pulse_FF_abs'])
                elif '_recipe' in group and '_recipe_arg' in entry:
                    rec    = group['_recipe']
                    kwargs = {k: v for k, v in rec.items() if k not in ('base', 'method')}
                    Pulse_FF = _apply_recipe(_deref_base(rec['base'], base),
                                             rec['method'], entry['_recipe_arg'], kwargs)
                else:
                    Pulse_FF = list(_deref_base(group.get('Pulse_FF'), base))
                return {**entry.get('Qubit', {}), 'Pulse_FF': Pulse_FF}
    raise KeyError(f"drive entry {name!r} not found in drive_groups or readout_groups")


def _resolve_ramp(jd, ramp_state):
    """Returns {'Init_FF': [...] or None, 'Expt_FF': [...]}.

    Init_FF=None means "no init segment; caller falls back to Gain_Pulse".
    """
    base = jd.get('base_params', {})
    for group in jd['ramp_groups'].values():
        if ramp_state in group.get('entries', {}):
            entry = group['entries'][ramp_state]
            Expt_base = _deref_base(group.get('Expt_FF'), base)
            if 'Expt_FF_abs' in entry:
                Expt_FF = list(entry['Expt_FF_abs'])
            elif 'Expt_FF_delta' in entry and entry['Expt_FF_delta'] is not None:
                Expt_FF = [b + d for b, d in zip(Expt_base, entry['Expt_FF_delta'])]
            else:
                Expt_FF = list(Expt_base)
            if 'Init_FF_abs' in entry:
                Init_FF = list(entry['Init_FF_abs'])
            elif 'Init_FF_delta' in entry:
                d = entry['Init_FF_delta']
                Init_FF = None if d is None else [b + di for b, di in zip(Expt_base, d)]
            else:
                Init_FF = list(Expt_FF)
            return {'Init_FF': Init_FF, 'Expt_FF': Expt_FF}
    raise KeyError(f"ramp entry {ramp_state!r} not found in any ramp_groups")


def _resolve_dynamics(jd, dynamics_point):
    """Returns the resolved dynamics entry. May contain 'Dynamics_FF', 'BS_FF',
    't_offset', 'exact_t_bs', 'ij_samples', etc. *_FF_abs keys have their suffix
    stripped; string values naming a base_params array are dereferenced."""
    base = jd.get('base_params', {})
    for group in jd['dynamics_groups'].values():
        if dynamics_point in group.get('entries', {}):
            entry = group['entries'][dynamics_point]
            out = {}
            for k, v in entry.items():
                if k.endswith('_FF_abs'):
                    out[k[:-len('_abs')]] = list(_deref_base(v, base))
                elif k.endswith('_abs'):
                    out[k[:-len('_abs')]] = v
                else:
                    out[k] = v
            return out
    raise KeyError(f"dynamics entry {dynamics_point!r} not found in any dynamics_groups")


# ---------------------------------------------------------------------------
# Public entry point — mirrors the Template's build_config signature/output.
# ---------------------------------------------------------------------------

def build_config(**kwargs):
    valid = {'Qubit_Readout', 'Qubit_Pulse', 'Ramp_State', 'Dynamics_Point', 'Readout_Point', 'jd'}
    for k in kwargs:
        assert k in valid, f"Unrecognized key in build_config: {k}"

    Qubit_Readout  = kwargs['Qubit_Readout']
    Qubit_Pulse    = kwargs.get('Qubit_Pulse', [])
    Ramp_State     = kwargs.get('Ramp_State')
    Dynamics_Point = kwargs.get('Dynamics_Point')

    jd = kwargs.get('jd')
    if jd is None:
        with open(JSON_PATH) as fh:
            jd = json.load(fh)
    Readout_Point = kwargs.get('Readout_Point')
    if not Readout_Point:
        raise ValueError(
            "build_config requires an explicit Readout_Point (one of "
            f"{list(jd['readout_groups'])}) -- defaulting is disabled so the active "
            "readout is never ambiguous when multiple readout_groups exist."
        )

    
    readouts = [_resolve_readout(jd, str(Q), Readout_Point) for Q in Qubit_Readout]
    drives   = [_resolve_drive(jd,   str(P)) for P in Qubit_Pulse]

    # Sanity check: MUX readout / drive sets should share their FF point. Warn if not.
    if len({tuple(r['Readout_FF']) for r in readouts}) > 1:
        warnings.warn(
            "Qubit_Readout entries do not share the same Readout_FF: "
            + str({str(Q): r['Readout_FF'] for Q, r in zip(Qubit_Readout, readouts)}),
            stacklevel=2,
        )
    if drives and len({tuple(d['Pulse_FF']) for d in drives}) > 1:
        warnings.warn(
            "Qubit_Pulse entries do not share the same Pulse_FF: "
            + str({str(P): d['Pulse_FF'] for P, d in zip(Qubit_Pulse, drives)}),
            stacklevel=2,
        )

    N = len(Qubit_Readout)
    res_config = {
        'res_gains':       [r['Gain'] / 32766. * N                  for r in readouts],
        'res_freqs':       [r['Frequency'] - BaseConfig['res_LO']   for r in readouts],
        'readout_lengths': [r['Readout_Time']                        for r in readouts],
        'adc_trig_delays': [r['ADC_Offset']                          for r in readouts],
    }
    qubit_config = {
        'qubit_freqs': [d['Frequency'] - BaseConfig['qubit_LO'] for d in drives],
        'qubit_gains': [d['Gain'] / 32766.                       for d in drives],
        'sigma':       [d['sigma']                               for d in drives],
    }
    config = BaseConfig | res_config | qubit_config

    Qubit_Names  = [str(Q) for Q in range(1, len(config['fast_flux_chs']) + 1)]
    Gain_Readout = readouts[0]['Readout_FF']
    Gain_Pulse   = drives[0]['Pulse_FF'] if drives else Gain_Readout

    if Ramp_State:
        ramp = _resolve_ramp(jd, Ramp_State)
        Gain_RampInit = ramp['Init_FF'] if ramp['Init_FF'] is not None else Gain_Pulse
        Gain_Expt     = ramp['Expt_FF']
    else:
        Gain_RampInit = list(Gain_Pulse)
        Gain_Expt     = list(Gain_Pulse)

    if Dynamics_Point:
        dyn = _resolve_dynamics(jd, Dynamics_Point)
        Gain_Dynamics = dyn.get('Dynamics_FF') or dyn.get('BS_FF') or list(Gain_Pulse)
        for k in ('t_offset', 'ij_samples', 'exact_t_bs', 'ij_gains', 'pad_bs',
                  'meas_pi2_freq', 'meas_pi2_gain', 'pi2_init_gain'):
            if k in dyn:
                config[k] = dyn[k]
    else:
        Gain_Dynamics = list(Gain_Pulse)

    config['FF_Qubits'] = {}
    for i, Qubit in enumerate(Qubit_Names):
        # Gain_BS and Gain_Dynamics are same, have both for backward compatibility
        config['FF_Qubits'][Qubit] = {
            'channel':       config['fast_flux_chs'][i],
            'Additional_Delay_Time': config['fast_flux_delays'][i],
            'Gain_Readout':  Gain_Readout[i],
            'Gain_Pulse':    Gain_Pulse[i],
            'Gain_RampInit': Gain_RampInit[i],
            'Gain_Expt':     Gain_Expt[i],
            'Gain_BS':       Gain_Dynamics[i],
            'Gain_Dynamics': Gain_Dynamics[i],
        }

    config['Qubit_Readout_List'] = Qubit_Readout
    config['Qubit_Pulse']        = list(Qubit_Pulse)  # chip labels, indexable by 0-based position
    config['ro_chs']             = list(range(len(Qubit_Readout)))
    return config
