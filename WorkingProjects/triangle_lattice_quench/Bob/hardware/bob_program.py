"""BobProgram: the QICK program for one compiled Bob sequence (from ProgramBuilder).

One shot:

    1. Hold the init gains for init_hold_us so the flux settles (ProgramBuilder: 5 us).
    2. Play the stitched, compensated FF waveform on every channel.
    3. Play every drive at its scheduled time (segment start rounded up to a clock cycle).
    4. Readout: FF at the readout gains for res_length, trigger the ADCs, MUX readout pulse.
    5. DC balance: replay everything negated so each channel's net flux is zero.

Reads only ``cfg`` keys the TLQ backend writes (see compiler/tlq_backend.py); no globals,
no file access, no network.

Status: written against qick's AveragerProgramV2 API as ProgramBuilder uses it, but not
yet run on the RFSoC. The first lab run checks it on the oscilloscope (README, "Before the
first lab run").
"""
from __future__ import annotations

import numpy as np
from qick.asm_v2 import AveragerProgramV2

from . import ff_play


class BobProgram(AveragerProgramV2):
    def _initialize(self, cfg):
        bob = cfg["bob"]
        self.ff_channels = [int(c) for c in cfg["fast_flux_chs"]]
        self.ff_t0 = np.asarray(cfg.get("fast_flux_delays", [0] * len(self.ff_channels)), float)
        self.ff_maxv = float(bob.get("max_gain", 32766))

        # qubit drive + MUX readout generators
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])
        if cfg["ro_chs"]:
            self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"], mixer_freq=cfg["res_mixer_freq"],
                             mux_freqs=cfg["res_freqs"], mux_gains=cfg["res_gains"], ro_ch=cfg["ro_chs"][0])
            for i, ch in enumerate(cfg["ro_chs"]):
                self.declare_readout(ch=ch, length=cfg["readout_lengths"][i], freq=cfg["res_freqs"][i],
                                     gen_ch=cfg["res_ch"])
            self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                           length=cfg["res_length"])
        for ch in self.ff_channels:
            self.declare_gen(ch=ch)

        init, ro = bob["init_gains"], bob["readout_gains"]
        hold = bob["init_hold_us"] + bob.get("ff_lead_us", 0.0)
        ff_play.add_ff_const(self, "bob_init", init, hold)
        ff_play.add_ff_arb(self, "bob_body", bob["ff_waveforms"])
        ff_play.add_ff_const(self, "bob_ro", ro, cfg["res_length"])
        if bob.get("dc_balance", True):
            ff_play.add_ff_const(self, "bob_init_inv", init, hold, sign=-1.0)
            ff_play.add_ff_const(self, "bob_ro_inv", ro, cfg["res_length"], sign=-1.0)

        for k, d in enumerate(bob["drives"]):
            self.add_gauss(ch=cfg["qubit_ch"], name=f"bob_env_{k}", sigma=d["sigma"], length=d["length"])
            self.add_pulse(ch=cfg["qubit_ch"], name=f"bob_drive_{k}", style="arb", envelope=f"bob_env_{k}",
                           freq=d["freq"], phase=d["phase"], gain=d["gain"])

    def acquire_shots(self, soc, rounds: int = 1, progress: bool = False):
        """Run the program and return single shots ``(shots_i, shots_q)``, one array per readout
        channel (AveragerProgramFF.acquire_shots)."""
        self.acquire(soc, rounds=rounds, progress=progress)
        d_buf = self.get_raw()                 # [(*loop_dims, nreads, 2) for each readout channel]
        shots_i, shots_q = [], []
        for k, ro_ch in enumerate(self.cfg["ro_chs"]):
            n = self.us2cycles(self.cfg["readout_lengths"][k], ro_ch=ro_ch)
            # MUX readouts carry a (-0.5, -0.5) offset per sample; undo it as the lab code does
            shots_i.append(0.5 + d_buf[k][..., -1, 0] / n)
            shots_q.append(0.5 + d_buf[k][..., -1, 1] / n)
        return shots_i, shots_q

    def _body(self, cfg):
        bob = cfg["bob"]
        # (1) settle at the init gains
        ff_play.play_ff(self, "bob_init")
        self.delay_auto()
        # (2) stitched FF body, (3) drives on the drive clock (0 = start of the body)
        ff_play.play_ff(self, "bob_body")
        for k, d in enumerate(bob["drives"]):
            self.pulse(ch=cfg["qubit_ch"], name=f"bob_drive_{k}", t=d["t"])
        self.delay_auto()
        # (4) readout
        ff_play.play_ff(self, "bob_ro")
        if cfg["ro_chs"]:
            for ro_ch, adc_delay in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
                self.trigger(ros=[ro_ch], t=adc_delay)
            self.pulse(cfg["res_ch"], name="res_drive")
        self.wait_auto()
        self.delay_auto(10)
        # (5) DC balance
        if bob.get("dc_balance", True):
            ff_play.play_ff(self, "bob_ro_inv")
            ff_play.play_ff_inverted(self, "bob_body")
            ff_play.play_ff(self, "bob_init_inv")
            self.delay_auto()
