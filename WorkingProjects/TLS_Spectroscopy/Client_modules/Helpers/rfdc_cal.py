import time

_SERVER_MSG = ("The board's Pyro server does not expose %s(...). The RF-ADC lives on the RFSoC, "
               "so the freeze must run server-side: start the board with "
               "WorkingProjects/TLS_Spectroscopy/pynq/qick_server.py (QickSocCal), or add that "
               "QickSocCal subclass to your server.py and restart it, then reconnect (makeProxy).")


def _method(soc, name):
    fn = getattr(soc, name, None)
    if fn is None:
        raise RuntimeError(_SERVER_MSG % name)
    return fn


def cal_freeze_status(soc, ro_ch=0):
    st = _method(soc, "get_readout_cal_freeze")(ro_ch)
    print(f"[rfdc] ro_ch={ro_ch} -> ADC tile {st['tile']} block {st['block']} | CalFreeze={st['status']}")
    return st


def freeze_readout_cal(soc, ro_ch=0, freeze=True):
    st = _method(soc, "set_readout_cal_freeze")(ro_ch, bool(freeze))
    print(f"[rfdc] ADC tile {st['tile']} block {st['block']} -> "
          f"{'FROZEN' if freeze else 'THAWED'} (CalFrozen={st['status'].get('CalFrozen')})")
    return st


def freeze_all_adc_cal(soc, freeze=True):
    done = _method(soc, "set_all_adc_cal_freeze")(bool(freeze))
    print(f"[rfdc] cal {'FROZEN' if freeze else 'THAWED'} on ADC blocks {done}")
    return done


def recal_then_freeze(soc, ro_ch=0, settle_s=3.0):
    _method(soc, "set_readout_cal_freeze")(ro_ch, False)
    time.sleep(float(settle_s))
    return freeze_readout_cal(soc, ro_ch, True)
