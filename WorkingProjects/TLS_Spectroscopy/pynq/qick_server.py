#!/usr/bin/env python3
import sys
import getopt

ns_host = None
ns_port = None
proxy_name = "myqick"

options, remainder = getopt.gnu_getopt(sys.argv[1:], "n:p:h")
for opt, arg in options:
    if opt == "-n":
        ns_host = arg
    elif opt == "-p":
        ns_port = int(arg)
    elif opt == "-h":
        print("Usage: sudo python3 qick_server.py [-n nshost] [-p nsport] [name]")
        sys.exit(0)
if remainder:
    proxy_name = remainder[0]

import Pyro4
from qick import QickSoc


class QickSocCal(QickSoc):
    def _adc_tile_block(self, ro_ch=0):
        adc = str(self.readouts[ro_ch].adc)
        return int(adc[0]), int(adc[1])

    def readout_adc_tile_block(self, ro_ch=0):
        return self._adc_tile_block(ro_ch)

    def get_readout_cal_freeze(self, ro_ch=0):
        t, b = self._adc_tile_block(ro_ch)
        return {"tile": t, "block": b,
                "status": dict(self.rf.adc_tiles[t].blocks[b].GetCalFreeze())}

    def set_readout_cal_freeze(self, ro_ch=0, freeze=True):
        t, b = self._adc_tile_block(ro_ch)
        self.rf.adc_tiles[t].blocks[b].SetCalFreeze(
            {"CalFrozen": 0, "DisableFreezePin": 1, "FreezeCalibration": 1 if freeze else 0})
        return self.get_readout_cal_freeze(ro_ch)

    def set_all_adc_cal_freeze(self, freeze=True):
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


Pyro4.config.REQUIRE_EXPOSE = False
Pyro4.config.SERIALIZER = "pickle"
Pyro4.config.SERIALIZERS_ACCEPTED = set(["pickle"])
Pyro4.config.PICKLE_PROTOCOL_VERSION = 4

ns = Pyro4.locateNS(host=ns_host, port=ns_port)
host = Pyro4.socketutil.getInterfaceAddress(ns._pyroUri.host)
daemon = Pyro4.Daemon(host=host)

soc = QickSocCal()
print("initialized QICK (with ADC cal-freeze methods)")

ns.register(proxy_name, daemon.register(soc))
for obj in soc.autoproxy:
    daemon.register(obj)
print("registered QICK as", proxy_name)

daemon.requestLoop()
