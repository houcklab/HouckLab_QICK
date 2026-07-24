from qick import QickSoc


def _adc_tile_block(self, ro_ch=0):
    adc = str(self.readouts[ro_ch].adc)
    return int(adc[0]), int(adc[1])


def _get_readout_cal_freeze(self, ro_ch=0):
    t, b = _adc_tile_block(self, ro_ch)
    return {"tile": t, "block": b,
            "status": dict(self.rf.adc_tiles[t].blocks[b].GetCalFreeze())}


def _set_readout_cal_freeze(self, ro_ch=0, freeze=True):
    t, b = _adc_tile_block(self, ro_ch)
    self.rf.adc_tiles[t].blocks[b].SetCalFreeze(
        {"CalFrozen": 0, "DisableFreezePin": 1, "FreezeCalibration": 1 if freeze else 0})
    return _get_readout_cal_freeze(self, ro_ch)


def _set_all_adc_cal_freeze(self, freeze=True):
    done = []
    for ti, tile in enumerate(self.rf.adc_tiles):
        for bi, blk in enumerate(tile.blocks):
            try:
                blk.SetCalFreeze({"CalFrozen": 0, "DisableFreezePin": 1,
                                  "FreezeCalibration": 1 if freeze else 0})
                done.append([ti, bi])
            except Exception:
                pass
    return done


def add_cal_methods():
    QickSoc.get_readout_cal_freeze = _get_readout_cal_freeze
    QickSoc.set_readout_cal_freeze = _set_readout_cal_freeze
    QickSoc.set_all_adc_cal_freeze = _set_all_adc_cal_freeze
    return QickSoc
