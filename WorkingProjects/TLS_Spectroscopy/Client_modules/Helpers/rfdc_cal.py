import time

_SERVER_MSG = ("The board's Pyro server does not expose %s(...). The RF-ADC lives on the RFSoC, "
               "so the freeze must run server-side: add the QickSoc cal-freeze methods "
               "(WorkingProjects/TLS_Spectroscopy/pynq/add_cal_methods.py) before start_server on "
               "the board and restart it, then reconnect (makeProxy).")


def _method(soc, name):
    fn = getattr(soc, name, None)
    if fn is None:
        raise RuntimeError(_SERVER_MSG % name)
    return fn


def cal_freeze_status(soc, ro_ch=0):
    st = _method(soc, "get_readout_cal_freeze")(ro_ch)
    print(f"[rfdc] readout cal-freeze status: {st}")
    return st


def freeze_readout_cal(soc, ro_ch=0, freeze=True):
    st = _method(soc, "set_readout_cal_freeze")(ro_ch, bool(freeze))
    if st.get("status") is None:
        raise RuntimeError(f"Could not {'freeze' if freeze else 'thaw'} the ADC cal on this board. "
                           f"Server returned {st}. Send the 'api' list so the right call can be used.")
    print(f"[rfdc] ADC tile {st['tile']} block {st['block']} -> "
          f"{'FROZEN' if freeze else 'THAWED'} | status {st['status']}")
    return st


def freeze_all_adc_cal(soc, freeze=True):
    done = _method(soc, "set_all_adc_cal_freeze")(bool(freeze))
    print(f"[rfdc] cal {'FROZEN' if freeze else 'THAWED'} on ADC blocks {done}")
    return done


def recal_then_freeze(soc, ro_ch=0, settle_s=3.0):
    _method(soc, "set_readout_cal_freeze")(ro_ch, False)
    time.sleep(float(settle_s))
    return freeze_readout_cal(soc, ro_ch, True)
