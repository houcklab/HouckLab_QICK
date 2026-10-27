from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    readout_drive_length_us)

soc, soccfg = makeProxy()
rch, ro = BaseConfig["res_ch"], BaseConfig["ro_chs"][0]

print("config values that set the readout length")
for k in ("read_length", "adc_trig_offset", "readout_guard_us",
          "read_pulse_length", "read_pulse_style", "res_ch", "ro_chs"):
    print(f"  {k:20} = {BaseConfig.get(k, '<unset>')}")

drive = readout_drive_length_us(BaseConfig)
cycles = soccfg.us2cycles(drive, gen_ch=rch)
print(f"\ndrive length {drive:g} us -> {cycles} cycles   (16-bit field max 65535)")
print("OK" if cycles <= 65535 else "OVERFLOW by %.1fx" % (cycles / 65535))

g = soccfg['gens'][rch]
print(f"\ngenerator {rch}: {g.get('type')}")
for k in ("fs", "f_fabric", "samps_per_clk", "maxlen", "maxv", "maxv_scale"):
    if k in g:
        print(f"  {k:14} = {g[k]}")
percyc = max(soccfg.us2cycles(1.0, gen_ch=rch), 1)
print(f"\n1 us = {percyc} cycles on gen {rch}; max pulse {65535/percyc:.2f} us")
print(f"readout {ro}: 1 us = {soccfg.us2cycles(1.0, ro_ch=ro)} cycles")
