# Neutral flux implementation plan

**Goal:** implement and validate one owned causal inverse algorithm and matched controller emitters.
**Architecture:** byte-identical fluxpred core and fitting code vendored into isolated QICK/QUA branches; separate backend adapters and dedicated integration helpers.
**Tech stack:** Python, NumPy, SciPy, pytest; optional matplotlib for report figures.
**Spec:** ../specs/2026-09-13-neutral-flux-design.md

## Constraints

No measured data writes, no hardware access, no built-in OPX filtering, no legacy behavior changes, no pushes. Preserve both main checkouts. Data-dependent acceptance is separate from deterministic software validation.

- [x] Audit both branches, measured extraction, commands, return history, and baseline tests.
- [x] Tests first: core state-space causality, exact exponential average, conditioning potential, round-trip and streaming state, strict serialization.
- [x] Implement fluxpred/core.py; run tests; expose Command and Filter to emitters.
- [x] Independently implement QICK/QUA emitters with cumulative edge quantization, clipping and instruction bounds; test fake hardware APIs.
- [x] Tests first: known-command forward identification, inversion of synthetic plants, held-out amplitude fitting, rank/regularization guards; implement fluxpred/fit.py.
- [x] Implement read-only offline audit runner; frozen snapshots with source hashes, supported raw and smoothed estimates, metric definitions, train/LOAO/later-set evidence, extraction sensitivity, q3 limitations, no unsupported hardware-ready claim.
- [x] Dedicated shot plan/regressions: active reset at park; explicit full return recovery; variable holds; normalized reconstruction comparison and program-bank limits. Keep piecewise as explicit fallback.
- [x] Self-review/review tests, run full focused suites in both repositories, compare identical core hashes, write evidence report and committed commands. Commit local codex/* branches only.
