# Active Reset on q4 — Failure Log & Handoff

> **SUPERSEDED.** This log records the *legacy single-quadrature* reset failing its
> gate on q4 in July 2026. The rotated reset (`Helpers/active_reset_rot.py`) replaced
> it and passes; it is now the default everywhere. Keep this as the record of why the
> legacy path was abandoned, not as a statement about reset today.


Status as of 2026-07-27. Branch `tls-spectroscopy`. This documents everything we found
debugging why active (feedback) reset never passes its gate on q4, what has been fixed,
and the still-open bug. Written for a fresh agent to pick up.

---

## TL;DR

- Active (feedback) reset **still fails** its end-to-end gate even with **good readout
  (single-shot F = 0.907, P(e|g)=0.04, P(g|e)=0.145)**. It should work at F>0.8. So the
  remaining problem is a **code bug in the reset's per-shot decision path, NOT the readout
  chain / chip fidelity.** (I spent too long blaming the readout — the data below refutes that.)
- **Three real bugs were found and fixed** (register clobbers ×2, photon-detuned reset π).
  Each was necessary but none is sufficient.
- **The open bug:** the conditional reset grounds a prepared |e> by only ~16% (1.0 → 0.84),
  while *forcing* the π on every shot grounds ~70%. So the in-loop `condj` is **skipping ~80%
  of excited shots it should flip** — an in-loop read/threshold bug — AND the reset π itself
  only rotates ~70% even on a cleared cavity, while the identical prep π is a full π.
- **QUA active reset works on this exact device** (same qubit, same chip), so this is
  definitively a QICK-port bug, not physics.

---

## System

- QICK RFSoC, `qick 0.2.133`, tProc **v1**. Qubit q4, chip FTTv02_SiOxJJ, all fast-flux, PARK.
- **Channel/register map (verified against the real qick 0.2.133 source):**
  - `res_ch`=gen0 → tproc_ch **1**; `qubit_ch`=gen1 → tproc_ch **2** (EVEN). Both share **page 1**.
  - `pulse_registers = [freq, phase, addr, gain, mode, t, addr2, gain2, mode2, mode3]`.
  - `_sreg_tproc(ch,name) = 11 + 10*((ch+1)%2) + index(name)`.
  - On any page: **regs 11–30 are the two channels' pulse registers**; regs **1–10 and 31 are
    free scratch**; the RAverager/Averager loop counters live on **page 0** only.
  - Qubit (tproc_ch 2, even) → regs **21–30**: freq=21, phase=22, addr=23, gain=24, **mode=25**,
    **t=26**, addr2=27, gain2=28, mode2=29, mode3=30.
- Readout: `read_pulse_gain=7000`, `read_length=10 us`, `read_pulse_freq≈7248.95 MHz`,
  κ/2π≈0.363 MHz (1/κ≈0.44 us, cavity clears in ~4 us), 2|χ|/κ≈0.35.
- Qubit π: arb Gaussian, `sigma=0.25 us` (4σ=1 us, bandwidth ~0.6 MHz), DRAG β=0,
  `qubit_pi_freq=2600.7 MHz`, `qubit_pi_gain=5790`, anharmonicity −200 MHz.

## Key files

- `Helpers/active_reset.py` — `active_reset_block(...)`, the reset primitive.
- `Experiments/mActiveResetProbe.py` — `ActiveResetProbe`: `calibrate_res_phase`,
  `_residual_at` (the gate's end-to-end check), `ReadProbeProgram` (raw |g>/|e> read),
  `ResetCheckProgram` (prep → reset → measure).
- `Experiments/mT1VsFlux.py` — `FFT1Program` (T1 with feedback reset).
- `Experiments/mCoherence.py` — `T1` driver; `Runners/SingleQubitCoherence.py` — runs the
  probe/gate then T1.
- `Experiments/mRabiChevronIQ.py` (`_rabi_feedback_reset`), `Experiments/mSingleShot1Q.py`
  (`SingleShotProgram` feedback reset, `discriminate_shots`).

## How the reset works (active_reset.py `active_reset_block`)

```
regwi(page, reg_thr, threshold_raw)              # reg_thr = threshold (raw accumulator units)
for i in range(max_iters=3):
    measure(res_ch, adcs=[ro_ch], wait=True, syncdelay=meas_syncdelay_us)
    read(tproc_ch, page, oper, reg_val)          # reg_val = raw lower-quadrature accumulator
    condj(page, reg_val, ground_op, reg_thr, skip)  # skip the flip if on the GROUND side
    pulse(ch=qubit_ch)                           # conditional X180
    label(skip)
    sync_all(settle_us)
sync_all(thermalization_us=25)
```
- `ground_below=False` ⇒ `ground_op=">"`. `condj` jumps to `skip` (no flip) if
  `reg_val > threshold`. Ground reads high (less negative), excited reads low (more negative),
  threshold sits between. So excited (`reg_val < threshold`) should NOT skip ⇒ flip.
- Default scratch registers (after fixes): `reg_val=1`, `reg_thr=2`.
- Default `reset_meas_syncdelay_us=4.0` (after fix), `reset_settle_us=0.05`,
  `reset_thermalization_us=25.0`, `reset_max_iters=3`.

## The gate

`mActiveResetProbe._residual_at` preps |g> and |e>, runs the reset, projects the averaged I/Q
onto the g→e axis, and requires prepared-|e> residual `< 0.2` (and |g> `< 0.2`). If not, the
runner prints "ACTIVE RESET NOT confirmed" and **falls back to passive relax (1500 us)**.
Every run this session has fallen back to passive.

---

## Confirmed bugs found AND FIXED (each necessary, none sufficient)

1. **Register clobber — default 20/21 → 1/2** (commit `1984198`).
   `active_reset_block` defaulted `reg_val=20, reg_thr=21`. On this board reg 21 = the qubit's
   **freq** register. `regwi(21, threshold)` overwrote the qubit DDS frequency with the raw
   threshold (which changes run to run), detuning the drive. Symptom: T1 came out a **flat line**
   at P(e)≈0.1 (curve_fit then returned random "scattered" T1 values — the whole "T1 scatter"
   saga was this artifact), and Rabi Chevron SS looked wrong while passive Rabi Chevron IQ looked
   fine. Fixed by moving the reset scratch to regs 1/2.

2. **Register clobber at explicit call sites — 25/26 → 1/2, gain-stash 27/28 → 3/4**
   (commit `1e53a6b`). `_rabi_feedback_reset` (mRabiChevronIQ.py) and `SingleShotProgram`
   (mSingleShot1Q.py) passed `reg_val=25, reg_thr=26` **explicitly** (= qubit `mode`/`t`
   registers), which the default fix didn't reach; they also stashed swept gains into 27/28
   (`addr2`/`gain2`). Fixed to 1/2 and 3/4. **STILL UNFIXED (off-limits parallel-agent file):**
   `mBasicAutoTuner.py:~1374` uses `reg_val=25, reg_thr=26` — same bug, flagged, not edited.

3. **Photon-detuned reset π — `reset_meas_syncdelay_us` 0.2 → 4.0 us** (commit `dae1f62`).
   The conditional X180 fired only ~0.2 us after a 10 us / gain-7000 readout, i.e. inside the
   cavity ring-down (~4 us), so it was AC-Stark detuned off resonance and barely rotated. Proven
   with a forced-flip + msync sweep: at msync=0.2 us the forced π does nothing; by msync≥2 us it
   is a real π. Fixed by delaying the conditional π until the cavity clears.

---

## THE OPEN BUG (unsolved)

Even after all three fixes, with a **good readout**, the gate fails. Representative run
(2026-07-27, res_phase=45°, purity 0.97):

```
SS cal:           F = 0.907   confusion [[0.959, 0.145],[0.041, 0.855]]  (P(e|g)=0.04, P(g|e)=0.145)
probe raw reads:  ground lower = -2694,  excited lower = -39374,  threshold_raw = -18675
held-out assign:  F = 0.885   P(e|g)=0.032  P(g|e)=0.197
end-to-end reset: prepared |g> -> +0.156   prepared |e> -> +0.838   (baseline 1.0)  => NOT confirmed
```

Interpretation:
- prepared |e> only drops 1.0 → 0.838 ⇒ the reset grounds **~16%** of excited shots.
- With F≈0.9 / P(g|e)≈0.15, a working reset should identify ~85% of excited per iteration and,
  over 3 iterations, drive |e> to ≈0. It does not.

### Decisive evidence that it's the DECISION path, not readout or physics

A forced-flip diagnostic (removed after use — reconstruct it; see below) compared:
- **CONDITIONAL** (calibrated threshold): |e> → ~0.82 (grounds ~16%).
- **ALWAYS-FLIP** (threshold set to ±1e6 so `condj` can never skip; π fires every shot, one
  iteration): at msync≥2 us, |g> → ~0.8 (ground driven to excited) and |e> → ~0.30–0.37
  (grounds ~70%).
- **NEVER-FLIP** (threshold ∓1e6; π never fires): |e> ≈ baseline. Sanity.

Two independent problems fall out of this:
- **(A) The in-loop `condj` skips excited shots it should flip.** ALWAYS-FLIP (forced) grounds
  ~70% but CONDITIONAL grounds only ~16% — the conditional path is worse than a single forced
  flip, which is impossible if `condj` were firing correctly on excited. So the reset's in-loop
  read/threshold is **classifying most excited shots as ground** (skipping the flip), even though
  the *held-out* probe reads excited cleanly far below threshold (−39374 vs −18675). This is not
  the readout fidelity (0.907) — it's the in-loop read value or the read/condj call itself.
- **(B) Even the forced π only grounds ~70%, not ~95%, on a cleared cavity** (msync=8 us gives
  |e>→0.30). Yet the *prep* π — the identical `pulse(ch=qubit_ch)` with the same
  `qubit_pi_gain` — excites ground to baseline ~1.0 (a full π). So the reset π is weaker than the
  prep π even after the cavity is cleared. Something about the reset context still degrades it.

Also note prepared-|g> residual rose from ~0 (when the π was dead, pre-fix #3) to ~0.15–0.19
(post-fix): now that the π fires, it *false-flips* some ground shots to excited too. Both |g>
and |e> drift toward a mixed state → gate fails.

---

## Leads for the next agent (in priority order)

1. **Capture the reset's actual in-loop read values.** This is the single most important
   experiment and was not yet done. Instrument `active_reset_block` (guard behind a cfg flag so
   production is unaffected) to `memwi` each `reg_val` after the `read`, for prepared |g> and |e>,
   and read them back. Compare to `ReadProbeProgram`'s raw values (ground −2694 / excited −39374).
   - If the in-loop read for excited is NOT ≈ −39374 (i.e. it reads on the ground side), the
     in-loop `read`/measurement differs from the probe's — find why (accumulator not fresh, wrong
     channel, `oper`, scale, res_phase applied differently in the loop, etc.).
   - If the in-loop read IS ≈ −39374 yet `condj` still skips, the bug is in the `read`/`condj`
     wiring (wrong destination register, sign, or arg order).

2. **Verify the `read()` call against the real qick API.** `active_reset.py:58` calls
   `prog.read(tproc_ch, page, oper, reg_val)`. I could NOT find `def read(` in
   `qick_lib/qick/qick_asm.py` of the 0.2.133 sdist (only `def readout`); the `read` opcode exists
   (`'read'` in the instruction table) but the wrapper method's name/signature/arg-order was never
   confirmed. **Confirm the exact signature and that `(tproc_ch, page, oper, reg_val)` maps to it
   correctly** — a wrong arg order here (e.g. page vs channel, or which operand is the destination
   register) would make `condj` compare a stale/uninitialized reg_val and skip every real decision,
   which fits symptom (A) exactly. (qick sources were extracted to a scratchpad during debugging;
   re-download with `pip download qick==0.2.133 --no-deps --no-binary :all:`.)

3. **Fix the partial reset π (symptom B).** Once (A) is solved, chase why the reset π rotates
   ~70% vs the prep π's ~full π on a cleared cavity. Candidates: residual cavity photons / slow
   mode beyond 8 us, measurement-induced dephasing persisting into the π, or a timing/phase issue
   specific to firing the π right after a `measure(wait=True)` + `sync_all`.

4. **Consider porting QUA's reset structure faithfully.** QUA (see below) loops
   *measure → (flip if excited) → measure* **until a measurement confirms ground**, with a
   dead-band (flip only if `> ss_thresh`, exit only if `< ground_confidence_threshold`), and
   always ends on a verified-ground read. The QICK port is a fixed 3× measure-then-flip ending on
   an *unverified* flip, single threshold, no dead-band. A dead-band (flip only when *confidently*
   excited) would also cut the |g> false-flips. Note tProc-v1 buffer constraint: a data-dependent
   number of `measure`s breaks the fixed `readouts_per_experiment`/reshape, so a faithful
   while-loop needs either fixed-count-with-early-exit-on-flipping-only, or reset reads kept out of
   the data buffer.

## QUA reference (WORKS on this exact device)

`/Users/.../Houck-Lab-Qua/LabCode/Experiments/Coherence/m_T1.py` — the T1's active reset:
```python
with while_(I_reset > ground_confidence_threshold):     # loop until CONFIRMED ground
    with if_(I_reset > ss_thresh):                       # flip only if confidently excited (dead-band)
        play('X180', qubit)
        align(qubit, resonator)
    I, _ = measure_1q(...)                               # re-measure every iteration
    assign(I_reset, I)
wait(thermalization_time*u.ns, qubit)
```
`ground_confidence_threshold` (= QICK `calib_params["ground_threshold"]`, e.g. −0.108) is the
"first threshold where fidelity > 0.6" point; `ss_thresh` is the optimal threshold. QUA's active
reset produces a **clean T1 on this device**, which is why we know the QICK failure is a port bug.

## How to reproduce / test

- Full path: `python Runners/SingleQubitCoherence.py` — runs `calibrate_res_phase` → probe →
  `_residual_at` gate. Watch the "reset prepared |e> (want ~0)" line; it prints ~0.6–0.85 and
  "ACTIVE RESET NOT confirmed → falling back to passive".
- Isolate the π vs the decision: recreate a small runner that calls
  `ActiveResetProbe.calibrate_res_phase()` then `probe._residual_at(res_phase, threshold_raw,
  ground_below, shots)` with `probe.cfg["reset_max_iters"]=1` and (a) the calibrated threshold,
  (b) threshold `+1e6, ground_below=False` (ALWAYS-FLIP), (c) threshold `-1e6` (NEVER-FLIP),
  sweeping `probe.cfg["reset_meas_syncdelay_us"]`. ALWAYS-FLIP isolates the π; CONDITIONAL vs
  ALWAYS-FLIP isolates the `condj`/read bug.
- Register-safety check on hardware: print
  `{n: prog.sreg(cfg['qubit_ch'], n) for n in ('freq','phase','addr','gain','mode','t','addr2','gain2','mode2','mode3')}`
  and `prog.ch_page(cfg['qubit_ch'])`; confirm the reset's scratch regs (1,2,3,4) are disjoint.

## Constraints for whoever edits this

- Only edit files under `WorkingProjects/TLS_Spectroscopy/Client_modules/`.
- Do NOT edit the parallel autotuner files: `mBasicAutoTuner.py`, `BasicAutoTune.py`,
  `BasicDiscovery.py`, `BasicGainSearch.py`, `basic_joint_optimizer.py`,
  `test_basic_auto_tuner.py` (reference only).
- The user keeps tuned parameter VALUES local on the measurement PC; change CODE, not their values.
