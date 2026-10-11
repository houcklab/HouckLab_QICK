"""Retrieval helpers over qubit_parameters.json (data only). Every FF array key starts with FF_.

JSON top level: `drive_groups` (readout + drive groups; entries carry Readout/Qubit/SingleShot blocks) and
`ff_groups` (free-form FF data, e.g. ramp_groups/<group>/<entry>/FF_Expt).
FF placement rule in drive_groups: FF_Readouts / FF_Pulses live on the group. An entry's "Readout" / "Qubit" object (the dict
holding Frequency, Gain, ...) may carry FF_override: a list replaces the whole group array, a single number replaces only the
index int(entry_name[0]) - 1 (entry names start with their qubit number, e.g. "3", "5A", "3_3800+"). FF_Readouts / FF_Pulses
inside those objects, or on the entry itself, are an error. Retrievers return deep copies; the QubitParams data is never mutated.

    qp = QubitParams(jd)                                                   # jd: loaded dict or path to the JSON
    qp.get_ff('ramp_groups', 'ramp_3800', '34', 'FF_Expt')                 # any value under ff_groups (deep copy)
    qp.drive_ff('FF_Pulses', 'ramsey_3800+', '1_3800+')                    # FF array under drive_groups (placement rule)
    qp.res_config('readout_3800', ['3', '4'])                              # res_*, readout_lengths, adc_trig_delays, ro_chs, Qubit_Readout_List, FF_Readouts (+ angle, threshold, confusion_matrix if SingleShot exists)
    qp.qubit_config('ramsey_3800+', ['3_3800+'])                           # qubit_freqs, qubit_gains, sigma, Qubit_Pulse, FF_Pulses
    qp.res_qubit_config('readout_3800', ['3', '4'], ['3'])                 # pulses looked up in the readout group
"""
import copy
import json
import warnings

from triangle_lattice_quench.MUXInitialize import BaseConfig

def _walk(root, keys, label):
    """Walks the json using keys, does a  deepcopy of root[k0][k1]..."""
    node = root
    for i, k in enumerate(keys):
        if not isinstance(node, dict) or k not in node:
            avail = list(node) if isinstance(node, dict) else type(node).__name__
            raise KeyError(f"{label}/{'/'.join(map(str, keys))}: {k!r} not found at "
                           f"{'/'.join([label, *map(str, keys[:i])])}; available: {avail}")
        node = node[k]
    return copy.deepcopy(node)


class QubitParams:
    """Read-only lookups into a qubit_parameters.json dict (or a path to one)."""

    def __init__(self, jd):
        if not isinstance(jd, dict):
            with open(jd) as fh:
                jd = json.load(fh)
        self.jd = jd

    def get_ff(self, *keys):
        """Getter for jd['ff_groups'][k0][k1]..."""
        return _walk(self.jd.get('ff_groups', {}), keys, 'ff_groups')

    def drive_ff(self, name, group, qubit_entry=None):
        """FF array ("FF_Readouts" or "FF_Pulses") of drive_groups[group],
        If needed, apply qubit_entry's FF_override:
            a list replaces the array, a number replaces a single value."""

        g = _walk(self.jd, ('drive_groups', group), 'jd')
        if qubit_entry is None:
            return _walk(g, (name,), f'drive_groups/{group}')
        else:
            # entry given, check for FF_override (a list needs no group-level array, so look that up after)
            e = _walk(g, ('entries', qubit_entry), f'drive_groups/{group}')
            FF_override = e.get({'FF_Readouts': 'Readout', 'FF_Pulses': 'Qubit'}[name], {}).get('FF_override')
            if isinstance(FF_override, list):
                return FF_override

            FF_array = _walk(g, (name,), f'drive_groups/{group}')
            if FF_override is not None:
                qubit_index = int(qubit_entry[0]) - 1
                assert 0 <= qubit_index < len(FF_array), f"{qubit_entry}: FF_override index {qubit_index} outside {len(FF_array)} FF channels"
                FF_array[qubit_index] = FF_override
            return FF_array

    def res_config(self, group, entries):
        """ResConfig from drive_groups[group] entries: res_freqs (MHz, rel. res_LO), res_gains (DAC/32766 x N_mux), readout_lengths (us), adc_trig_delays (us), ro_chs, Qubit_Readout_List, FF_Readouts, plus angle, threshold, confusion_matrix when every entry has a SingleShot object."""
        ros = [_walk(self.jd.get('drive_groups', {}), (group, 'entries', str(Q), 'Readout'), 'drive_groups') for Q in entries]
        sss = [_walk(self.jd.get('drive_groups', {}), (group, 'entries', str(Q)), 'drive_groups').get('SingleShot') for Q in entries]
        N = len(entries)
        cfg = {
            'res_gains':       [r['Gain'] / 32766. * N                for r in ros],
            'res_freqs':       [r['Frequency'] - BaseConfig['res_LO'] for r in ros],
            'readout_lengths': [r['Readout_Time']                      for r in ros],
            'adc_trig_delays': [r['ADC_Offset']                        for r in ros],
            'ro_chs': list(range(len(entries))),
            'Qubit_Readout_List' : entries,
            'FF_Readouts' : self.drive_ff("FF_Readouts", group, qubit_entry=str(entries[0]) if len(entries)==1 else None)
        }
        if all(sss):
            cfg['angle'] = [ss['angle'] for ss in sss]
            cfg['threshold'] = [ss['threshold'] for ss in sss]
            cfg['confusion_matrix'] = [[[1 - ss['ng_contrast'], ss['ne_contrast']], [ss['ng_contrast'], 1 - ss['ne_contrast']]] for ss in sss]
        return cfg

    def qubit_config(self, group, entries):
        """QubitConfig from drive_groups[group] entries: qubit_freqs (MHz, rel. qubit_LO), qubit_gains (DAC/32766), sigma (us),
        Qubit_Pulse (the entry labels), FF_Pulses (first entry's by the placement rule; the group-level array if entries is empty)."""
        drs = [_walk(self.jd.get('drive_groups', {}), (group, 'entries', str(e), 'Qubit'), 'drive_groups') for e in entries]
        ffs = [self.drive_ff('FF_Pulses', group, str(e)) for e in entries]
        if len({tuple(f) for f in ffs}) > 1:  # Multiple pulses should share one FF point
            warnings.warn(f"drive_groups/{group} entries do not share the same FF_Pulses: "
                          + str({str(e): f for e, f in zip(entries, ffs)}), stacklevel=2)
        return {
            'qubit_freqs': [d['Frequency'] - BaseConfig['qubit_LO'] for d in drs],
            'qubit_gains': [d['Gain'] / 32766.                       for d in drs],
            'sigma':       [d['sigma']                               for d in drs],
            'Qubit_Pulse': list(entries),
            'FF_Pulses': ffs[0] if ffs else self.drive_ff('FF_Pulses', group),
        }

    def res_qubit_config(self, readout_group, readout_entries, pulse_entries):
        """res_config(readout_group, readout_entries) | qubit_config(readout_group, pulse_entries)."""
        return self.res_config(readout_group, readout_entries) | self.qubit_config(readout_group, pulse_entries)

