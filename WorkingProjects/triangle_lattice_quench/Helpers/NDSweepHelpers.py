import numpy as np

def set_nested_item(d, key_list, value):
    """Sets into nested dicts,
    e.g. set_nested_item(d, ['a', 'b', 'c'], value) executes -----> d['a']['b']['c'] = value"""
    # functools.reduce(operator.getitem, [d, *key_list[:-1]])[key_list[-1]] = value
    if not isinstance(key_list, (list, tuple)):
        d[key_list] = value

    else:
        for key in key_list[:-1]:
            d = d[key]
        d[key_list[-1]] = value

def key_savename(key_list):
    """Generates a readable single string to be the key in the returned data dictionary:
    the LAST str in the key list, followed by '[i]' for each int after it.
    e.g. key_savename('delay') ---- > 'delay'
         key_savename(('pulse_freqs', 0)) -----> 'pulse_freqs[0]'
         key_savename(('FF_Pulses', 2)) -----> 'FF_Pulses[2]'
         key_savename(('qubit_phases_matrix', 3, 1)) -----> 'qubit_phases_matrix[3][1]'"""
    if not isinstance(key_list, (list, tuple)):
        return key_list
    else:
        for i in range(len(key_list) - 1, -1, -1):
            if type(key_list[i]) == str:
                return key_list[i] + ''.join(f'[{k}]' for k in key_list[i + 1:] if isinstance(k, (int, np.integer)))