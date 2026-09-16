# Controller-neutral flux predistortion: schemas and semantics

Every module under `fluxpred/` is byte-identical between `HouckLab_QICK` and
`Houck-Lab-Qua`. Verify with:

```bash
shasum -a 256 fluxpred/*.py tools/*.py
```

Only `fluxpred/qick.py` and `fluxpred/qua.py` know about a controller, and neither
imports a controller SDK. Device-specific code lives outside the package.

## 1. Model document — `houcklab.fluxpred.model.v1`

```json
{
  "schema": "houcklab.fluxpred.model.v1",
  "device": "q5",
  "controller": "QUA",
  "coordinate": {"unit": "V", "park": 0.156232010522, "scale": 0.231509604478},
  "model": {
    "type": "parallel_highpass_inverse",
    "taus_us": [8.0, 24.0, 64.0, 192.0],
    "coefficients": [-0.056, 0.036, -0.028, 0.020],
    "dc_gain": 1.0
  },
  "calibration": {
    "method": "ramsey_cryoscope_xy",
    "source_files": ["..."],
    "source_sha256": ["..."],
    "static_flux_model": {},
    "fit_settings": {},
    "cross_validation": {}
  },
  "acceptance": {"software": false, "scientific": false, "hardware": false}
}
```

`coefficients` is one-dimensional for an LTI model. An amplitude-conditioned model
uses a two-dimensional `coefficients` plus a matching `amplitudes` list; the
interpolation rule is in `core.Filter.potential` and has `g(0) = 0` exactly.

`schema.load_model` fails closed on:

- a schema string that is not exactly `houcklab.fluxpred.model.v1`;
- a device/controller pair that does not match (`q3`→QICK/`DAC_gain`, `q5`→QUA/`V`);
- a coordinate unit, park or scale that differs from the caller's calibration;
- `dc_gain` other than exactly `1.0`;
- non-positive or non-increasing `taus_us`;
- a coefficient L1 norm above `max_l1` (default `0.25`);
- any NaN/Infinity JSON literal, anywhere in the document;
- a `calibration.method` other than `ramsey_cryoscope_xy` — spectroscopy-ridge
  models are rejected by construction;
- empty provenance, a source-file/hash length mismatch, or a malformed digest;
- a requested normalized amplitude outside the calibrated range;
- `acceptance.scientific = false`, unless the caller passes an explicit
  diagnostic override.

`verify_source_hashes` re-hashes the referenced raw files and refuses a model whose
measurement changed underneath it.

## 2. Measurement document — `houcklab.fluxpred.measurement.v1`

Written by both device runners, read by `tools/fit_ramsey_flux_response.py`. The
fitter never imports a hardware experiment. Required sections:

- `sequence` — park/target coordinate, normalized amplitude, the delay grid, the
  probe-window ladder, shots, rounds, recovery, and `emitted_plan_sha256`.
- `observable` — `["x", "y"]`, per-delay contrast, the contrast threshold, and the
  supported fraction.
- `analysis` — the static flux model, the unwrap record (ladder windows, ambiguous
  count, branch tolerance), the differentiator settings, and the per-delay detuning
  uncertainty (`null` where contrast is zero).
- `provenance` — timestamp, controller commit, code commit, operator note.
- `files` — path, SHA-256 and size for `raw_csv` and `command_json`.

`command_json` holds the exact emitted normalized command. `command_from_summary`
re-hashes it against `sequence.emitted_plan_sha256` and refuses a mismatch, so a
model can never be fitted against a waveform other than the one that was played.

## 3. Equivalence report — `houcklab.fluxpred.equivalence.v1`

`report.cross_backend_report` lowers the same normalized condition bank through both
backends, reconstructs the normalized command from each backend plan, and compares
them on the union of boundaries.

Per condition it records the requested/QUA/QICK command hashes, segment and
instruction counts, QUA timing and voltage quantization error, each backend's
normalized LSB, the terminal park quantization residual, and the normalized
difference (`max_abs`, `rms`, `integrated_abs_ns`, `signed_area_ns`).

Edge matching is quantization-aware. Transitions smaller than
`max(2 × coarser LSB, significant_jump_fraction × full amplitude)` are not treated
as edges, because the two DACs have different LSBs (q5: 2⁻¹⁶ V ≈ 6.6e-5 normalized;
q3: 1 gain count ≈ 9.6e-5 normalized) and cannot agree on sub-LSB tail steps. Real
edges are matched one-for-one and their displacement is reported, so a one-clock
displaced full-amplitude edge is caught even when the RMS is small.

A large `max_abs` with a small `rms` is the expected signature of a sub-clock edge
sliver, not a systematic offset; check `max_edge_time_error_ns` to tell them apart.

## 4. Command semantics

The inverse is

```
g_j(r) = r · c_j(r)
dz_j/dt = (g_j(r) − z_j) / τ_j
u = r + Σ_j (g_j(r) − z_j)
```

with fixed real negative poles, so it is BIBO stable and has unity DC gain by
construction.

State is carried through every edge. `render` and `render_on_schedule` both return
the final state; `build_shot` renders park → target → hold → return → recovery as
one causal timeline and refuses to emit if the truncated tail exceeds
`tail_tolerance`. The return command depends on the state accumulated during the
hold, so each production condition gets its own command — `report.condition_bank`
builds one per hold and their hashes differ.

`report.repeated_shot_state` propagates state across repeated shots and reports
whether the tail bound converges; a recovery that is too short does not settle and
the test suite pins that behaviour.

## 5. Emission schedule

Uniform sampling does not fit q3. A 1.8 ms timeline at 4 µs uniform emission needs
about 450 segments, and at 32 tProc instructions per segment that is roughly 14,400
instructions — far beyond tProc-v1 memory.

`core.geometric_schedule` emits dense-early, sparse-late segments. For the same
1.8 ms timeline with `first_ns=2000`, `growth=1.35`, `max_ns=100000`,
`quantum_ns=1000` it produces 29 segments (about 928 instructions), with 2 µs
resolution where the 8 µs pole matters. `validation.shot_schedule` builds the hold
and recovery schedules and concatenates them, so an emission boundary always lands
exactly on the return edge.

## 6. Probe placement

Each probe is placed at the start of an emission segment, offset by
`inset_ns` (default 8 ns). Because the emission quantum (≥ 1 µs) is far longer than
two π/2 pulses plus the widest window (≈ 0.6 µs), the commanded flux is exactly
constant across the phase-accumulation window on both controllers. The frozen-probe
model in `fit.highpass_features` is therefore exact rather than an approximation,
and the two backends measure the same observable.

`core.probe_fits_constant_segment` enforces this, and both experiments refuse to run
if any requested delay would straddle a flux update.

The inset matters: the engine treats a probe starting exactly on an edge as seeing
the level *before* that edge. Insetting keeps the probe unambiguously inside the
following segment.
