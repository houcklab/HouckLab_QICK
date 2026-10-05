# q3 local e–f loss pilot

User authorized revisiting a loss feature through the e–f transition while
keeping g–e in a relatively quiet region. This is a finite feasibility and
decay pilot, not an automatic long scan or a saturation experiment.

## What changes from September 29

`TLSDualTransitionLoss` already attempted this idea. Its e–f frequency at the
target was inferred from the park anharmonicity. Prompt park mapping occurred
during the flux transient and did not reliably permute f; waiting the full
40-us return instead removed much of the useful state contrast. The apparent
loss peaks did not survive the readout controls. Repeating that sequence with
more shots is not justified.

`TLSResidentEFPilot` instead calibrates **both microwave transitions locally**,
prepares the state at the target, and applies the readout mapping **at the
target before returning**. Shared production code and `initialize.py` are
unchanged. The runner supplies temporary explicit q3 settings even if local
measurement-PC overrides currently select q4.

## Pulse and readout sequence

1. Passive park preparation: 1-ms washout between shots; no active-reset
   classifier or herald acceptance gate.
2. Corrected step to the target, with 30.5 us before local pulses.
3. Three identical-duration Gaussian slots: local g–e preparation; local e–f
   preparation; a zero-gain slot. The third slot supplies the identical timing
   needed for separate two-pulse 2π audits. Zero-gain pulses are kept in every
   control, including g preparation.
4. Additional dwell of 0.25, 2 or 8 us.
5. A fourth slot, at the target: either a zero-gain g–e pulse (identity view),
   or the calibrated local g–e π (g/e swap view).
6. Full native, stateful 40-us flux return, followed by ordinary park readout.

The additional dwell is not the full f lifetime interval. At sigma=0.2 us,
the empty slot and guards add about 0.82 us between f preparation and mapping.
Every arm saves actual quantized pulse times, the f-pulse-end-to-map-start gap,
and the return boundary. No microwave pulses interrupt or freeze the native
flux-correction segments; pulse and correction events run concurrently.

Why two views help: in an ideal limiting case where f becomes e during the
return, identity gives `(g,e,f) -> (g,e,e)`, while a g–e swap before return gives
`(g,e,f) -> (e,g,e)`. The pair still distinguishes the three initial states.
The experiment does **not** assume that ideal response: it estimates a
four-real-coordinate response from separate g/e/f preparation references.
Sequential transmon higher-level preparation and decay are established, for
example in [Peterer et al., arXiv:1409.6031](https://arxiv.org/abs/1409.6031).

## Bounded acquisition

One usual 3.8–4.3-GHz five-point scout selects a bidirectional loss line with
a quiet g–e window around the predicted shifted bias. The frozen −180-MHz
anharmonicity is only a starting prior. No park e–f calibration is reused.

At that one target:

- Opposed g–e spectroscopy: ±12 MHz at 2-MHz spacing, then ±2 MHz at
  0.5-MHz spacing; a 0–30000-DAC Rabi sweep fits the **first** π gain.
- Opposed e–f spectroscopy: ±24 MHz, then the same refinement and gain
  sweep. Both transitions have independent zero/π/two-π checks with 500 shots.
- An e–f ground-prepared negative control checks for direct excitation of g.
- If the measured local e–f transition misses the scout feature by >2 MHz,
  one bias correction and recalibration is allowed, limited to ±6 MHz inside
  the scout's qualified quiet window. A second mismatch ends the finite pilot
  as unresolved, retaining the calibration data.

Once aligned, late-prepared g/e/f references supply the response **at each
total visit duration**, with identical pulse slots, mapping time and full
flux waveform to science. Prep shifts to the end of the visit, leaving the
same 0.25-us additional delay before mapping. Training/held-out checks reject
an unresolved or ill-conditioned response before science.

Science: g/e/f × three dwells × two readout views × two reversed-order passes,
500 shots per arm. Independent late references follow science. Views are
separate acquisitions, not simultaneous observations of one qubit; inference
assumes stationarity over these short arms and is checked against the final
references and each science vector's consistency with the response plane.

There are 220 programs with no recenter: two park references, 146 pulse
calibration/control arms and 72 response/science arms. Most spectroscopy
points use 160 shots. Expected runtime is **8–15 minutes**, potentially up to
20 minutes with one recenter and NAS/transport overhead. Progress has an ETA;
only usual scout/calibration output, generic progress and a final manifest
path are printed. No new `[pump]`/`[floquet]` message stream.

## Interpretation and saved evidence

All raw IQ and per-arm configuration, requested/realized flux coordinates,
board configuration, native correction and its hash, source copies/hashes,
local spectra, Rabi fits, pulse audits and partial transferred records survive
a rejection or interruption. The manifest states the reason. Final response
drift or off-response-plane science cannot become a valid decay result.

The response inversion is unconstrained: negative or >1 estimates remain
visible and can invalidate the model. A bootstrap resamples science shots and
shared reference means, keeping the two passes separately visible. Near-boundary
reference instability produces an explicit invalid summary rather than a
random bootstrap exception. PNG and SVG population plots are saved only for
validated summaries.

These are **preparation-relative populations**, not absolute f purity or an
independently measured defect temperature. A resolved f loss with a quiet e
control would justify a locally calibrated line-versus-flank profile next.
One bias cannot prove a TLS-specific e–f loss peak: ordinary higher-level
relaxation, drifting references and preparation imperfections remain possible.
There is no automatic expansion to that profile.

## Verification and command

- Maintained test suite: **1418 passed** (1402 existing + 16 new).
- New tests include an ideal f→e return, failed mapping, off-plane science,
  reference drift, unstable bootstrap, full simulated runner workflow with
  q4 configuration restoration, interrupt/partial-data preservation, and
  actual native flux-helper playback equivalence between early and late prep.
- Offline QICK **0.2.133**, latest saved RFSoC configuration: 44 compiled and
  emulated configurations (all g/e/f, both views, all dwells, early/late prep,
  pulse audits and explicit park references), maximum **475/8192** instructions.
  Exact microwave gains, frequency words, scheduled start offsets and record
  boundaries reproduce. No late pulse under conservative four-cycle opcode
  timing. The emulator is a digital timing check, not an analog pulse calibration.
  NumPy-2 assembler scalar compatibility was applied only in the offline audit,
  not to the measurement runner. Physical local calibrations remain required.

On the measurement PC:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSResidentEFPilot --run
```

Output: `Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3/q3_resident_ef_pilot_<UTC>_<id>/`.

## First hardware attempt: selection stopped the experiment

Session `q3_resident_ef_pilot_20261005T032401Z_b4a205d9`, commit `5315fdbc`,
finished as `unresolved` at 03:26:34 UTC after 2m32.5s. Error:
`no bidirectional loss line with a quiet shifted e-f bias`.
**Zero local calibration or science arms completed.** The folder contains
only the manifest and three source snapshots. Their text matches the pushed
sources exactly after accounting for Windows CRLF endings. This was not a
negative e–f result: the measurement was never attempted.

Scout source:
`q3/q3_2026_10_04/q3_23_24_09_TLS_Resident_EF_Pilot_Scout_T1_5pt_vs_wall_clock_full.csv`.
All251 frequency rows and 250shots per condition completed in144.54s;
median P1−P0 contrast0.444. Loss sites are still present.

The selection rule required every point in the predicted shifted bias's
±8MHz window to have normalized10-us survival≥0.65 AND25-us survival≥0.60.
Several loss candidates passed the bidirectional depth criterion but failed
that window condition. For example:

| Loss candidate | Predicted shifted g–e bias | Minimum10-us survival in window | Minimum25-us survival in window |
| --- | --- | --- | --- |
|4.022GHz|4.202GHz|0.562|0.227|
|4.092GHz|4.272GHz|0.752|0.547|
|3.886GHz|4.066GHz|0.730|0.510|
|3.984GHz|4.164GHz|0.685|0.571|

The4.092GHz line's pooled/up/down depths were0.302/0.283/0.204. Its exact
predicted shifted center4.272GHz had25-us survival0.876; neighboring4.270
and4.274GHz had0.839 and0.664. The rejecting25-us point was4.276GHz,
4MHz away, with0.547; both scan directions were low there (0.532/0.564).
The25-us window median was0.725. These are noisy normalized scout estimates,
not a validated local pulse calibration or proof of a quiet e control.

Assessment: demanding a quiet **entire±8MHz window at25us** before a
**one-bias8-us maximum pilot** was unnecessarily restrictive. The nearby
loss must still be respected if local calibration requires moving the bias.
Simply disabling the quiet-site gate would select4.022GHz and knowingly
introduce a g–e-loss confound, so it is not an appropriate workaround.

Decision: do not rerun this unchanged, take another broad scout, or expand
to a long e–f profile. There is no new experimental evidence for the e–f
route. If it is pursued, the only justified next step is a bounded local
preparation/readout check at a fixed potentially quiet bias using this scout,
with an independently tested e control before any loss profile. Stop the
route if usable local f preparation/readout cannot be demonstrated. No
measurement-code change or new run command is issued in this results review.
