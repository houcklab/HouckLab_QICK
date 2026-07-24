from qick import QickSoc


def _adc_tile_block(self, ro_ch=0):
    adc = str(self.readouts[ro_ch].adc)
    return int(adc[0]), int(adc[1])


def _adc_block(self, ro_ch=0):
    t, b = _adc_tile_block(self, ro_ch)
    return t, b, self.rf.adc_tiles[t].blocks[b]


def _adc_cal_api(self, ro_ch=0):
    _, _, blk = _adc_block(self, ro_ch)
    return sorted(a for a in dir(blk) if not a.startswith("_"))


def _get_readout_cal_freeze(self, ro_ch=0):
    t, b, blk = _adc_block(self, ro_ch)
    for getter in (lambda: blk.CalFreeze, lambda: blk.GetCalFreeze()):
        try:
            return {"tile": t, "block": b, "status": dict(getter())}
        except Exception:
            pass
    return {"tile": t, "block": b, "status": None, "api": _adc_cal_api(self, ro_ch)}


def _set_readout_cal_freeze(self, ro_ch=0, freeze=True):
    t, b, blk = _adc_block(self, ro_ch)
    fc = 1 if freeze else 0
    errs = []
    for setter in (lambda: setattr(blk, "CalFreeze", {"FreezeCalibration": fc, "DisableFreezePin": 1}),
                   lambda: blk.SetCalFreeze({"CalFrozen": 0, "DisableFreezePin": 1, "FreezeCalibration": fc})):
        try:
            setter()
            return _get_readout_cal_freeze(self, ro_ch)
        except Exception as e:
            errs.append(repr(e))
    return {"tile": t, "block": b, "status": None, "errors": errs, "api": _adc_cal_api(self, ro_ch)}


def _set_all_adc_cal_freeze(self, freeze=True):
    done = []
    fc = 1 if freeze else 0
    for ti, tile in enumerate(self.rf.adc_tiles):
        for bi, blk in enumerate(tile.blocks):
            for setter in (lambda blk=blk: setattr(blk, "CalFreeze", {"FreezeCalibration": fc, "DisableFreezePin": 1}),
                           lambda blk=blk: blk.SetCalFreeze({"CalFrozen": 0, "DisableFreezePin": 1, "FreezeCalibration": fc})):
                try:
                    setter()
                    done.append([ti, bi])
                    break
                except Exception:
                    pass
    return done


def add_cal_methods():
    QickSoc.adc_cal_api = _adc_cal_api
    QickSoc.get_readout_cal_freeze = _get_readout_cal_freeze
    QickSoc.set_readout_cal_freeze = _set_readout_cal_freeze
    QickSoc.set_all_adc_cal_freeze = _set_all_adc_cal_freeze
    return QickSoc
