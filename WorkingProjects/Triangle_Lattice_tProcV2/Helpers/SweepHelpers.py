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
    """Generates a readable single string to be the key in the returned data dictionary.
    e.g. key_savename('delay') ---- > 'delay'
         key_savename(('pulse_freqs', 0)) -----> 'pulse_freqs'
         key_savename(['FF_Qubits', '1', 'Gain_Pulse']) -----> 'Gain_Pulse'"""
    if not isinstance(key_list, (list, tuple)):
        return key_list
    else:
        for key in reversed(key_list):
            if type(key) == str:
                return key