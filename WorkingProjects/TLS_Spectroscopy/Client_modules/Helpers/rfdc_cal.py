import time


def _adc_tile_block(soc, ro_ch=0):
    adc = str(soc.readouts[ro_ch].adc)
    return int(adc[0]), int(adc[1])


def readout_adc_block(soc, ro_ch=0):
    tile, block = _adc_tile_block(soc, ro_ch)
    return tile, block, soc.rf.adc_tiles[tile].blocks[block]


def cal_freeze_status(soc, ro_ch=0):
    tile, block, blk = readout_adc_block(soc, ro_ch)
    st = blk.GetCalFreeze()
    print(f"[rfdc] ro_ch={ro_ch} -> ADC tile {tile} block {block} | CalFreeze={st}")
    return st


def freeze_readout_cal(soc, ro_ch=0, freeze=True):
    tile, block, blk = readout_adc_block(soc, ro_ch)
    blk.SetCalFreeze({"CalFrozen": 0, "DisableFreezePin": 1,
                      "FreezeCalibration": 1 if freeze else 0})
    st = blk.GetCalFreeze()
    print(f"[rfdc] ADC tile {tile} block {block} -> "
          f"{'FROZEN' if freeze else 'THAWED'} (CalFrozen={st.get('CalFrozen')})")
    return st


def freeze_all_adc_cal(soc, freeze=True):
    done = []
    for t, tile in enumerate(soc.rf.adc_tiles):
        for b, blk in enumerate(tile.blocks):
            try:
                blk.SetCalFreeze({"CalFrozen": 0, "DisableFreezePin": 1,
                                  "FreezeCalibration": 1 if freeze else 0})
                done.append(f"{t}{b}")
            except Exception:
                pass
    print(f"[rfdc] cal {'FROZEN' if freeze else 'THAWED'} on ADC blocks {done}")
    return done


def recal_then_freeze(soc, ro_ch=0, settle_s=3.0):
    tile, block, blk = readout_adc_block(soc, ro_ch)
    blk.SetCalFreeze({"CalFrozen": 0, "DisableFreezePin": 1, "FreezeCalibration": 0})
    time.sleep(float(settle_s))
    return freeze_readout_cal(soc, ro_ch, freeze=True)
