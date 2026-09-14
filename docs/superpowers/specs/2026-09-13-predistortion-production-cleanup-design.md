# Predistortion Production Cleanup Design

## Objective

Move the September 12–13 q3 and q5 measurement artifacts out of the temporary top-level `FluxTeam/Data/q3` and `FluxTeam/Data/q5` trees, preserve their campaign grouping in the standard device hierarchy, and turn the reusable predistortion and five-point T1 work into production code on both controllers. Qubit-specific experiment runners and diagnostic tests are temporary and will not remain in either production branch.

## Data relocation

The relocation targets are:

- q3: `FTT02_AlOxJJ_2026_08_28/RFSOC/q3/q3_2026_09_12` and `q3_2026_09_13`
- q5: `FTT02_SiOxJJ_2026_08_28/OPX/q5/q5_2026_09_12` and `q5_2026_09_13`

Predistortion campaigns retain their meaningful grouping below each date as `predistortion_validation/<campaign>/...`. Redundant temporary path components such as `q3/q3_2026_09_13` and `q5/q5_2026_09_13` are removed. q5 sweet-spot measurement outputs are placed directly in the corresponding standard date directory. Historical file contents and embedded provenance paths are not rewritten.

Before moving anything, the migration builds a manifest containing each source, destination, size, and SHA-256 checksum. It aborts on an unknown layout or an existing destination. After relocation, every destination is rehashed and compared with the manifest. Only then are explicitly identified temporary Python files, Python caches, pytest caches, and empty temporary directories removed. The manifest remains in `FluxTeam/Data/migration_manifests` as an audit record.

The dry-run inventory contains 287 measurement artifacts and 19 temporary/cache files, with no destination collisions.

## Production code boundaries

Production retains only controller-independent or controller-appropriate mechanisms:

- image-based ridge tracking with a continuous paired-ridge/shoulder choice;
- phase corroboration and causal residual fitting;
- safe composition of a residual correction with an existing correction;
- provenance, waveform-timing, and correction-safety validation;
- controller-specific waveform execution behind the existing common configuration surface;
- reusable multi-amplitude consensus fitting;
- matched five-point T1 acquisition with active reset and bidirectional frequency ordering.

The q3- and q5-named calibration, validation, refit, and transfer runners are removed. Their reusable logic moves into generic helpers or the regular TLS spectroscopy pipeline. Qubit-specific values remain configuration, not implementation.

## Predistortion workflow

The regular step-response workflow becomes the only production entry point.

Step 3a measures the response using the shared image tracker and emits a correction JSON with complete pulse-condition metadata. Step 3b can apply the selected correction, measure the residual, fit a damped residual correction, compose it with the applied correction, and emit the composed candidate. Both repositories expose the same composition controls.

Correction discovery scans all supported `*_dc_compensation.json` candidates recursively rather than depending on one historical filename. A candidate must still pass method, controller, baseline, target, pulse-condition, and explicit match-mode checks. Discovery does not weaken validation.

The multi-amplitude consensus algorithm is extracted from the q5 runner into a generic helper. It combines normalized residual traces, aligns measurement-resolved segment edges, fits bounded multiplier adjustments, and reports before/after residual metrics. It contains no q5 paths, frequencies, or voltage constants.

## Five-point T1 protocol

Both production controllers use the same statistical work per frequency:

- delays: 10, 50, and 200 microseconds;
- 180 shots for P0, P1, and each of the three delayed survival measurements;
- five conditions × 180 shots = 900 Bernoulli trials per frequency, matching the prior three-condition × 300-shot budget;
- active reset between shots;
- frequency-major acquisition with the conditions executed together at each frequency;
- alternating forward/reverse frequency order between passes to reduce time-direction bias;
- identical output semantics and uncertainty propagation.

The implementation stays in generic experiment/helper modules and standard runners; no q3- or q5-specific five-point implementation is introduced.

## Repository and workstation cleanup

The QICK `tls-spectroscopy` branch and QUA `marty-branch` receive the production changes. Tracked `Q3Predistortion*.py`, `Q5Predistortion*.py`, and their qubit-specific tests are deleted after reusable behavior is covered by generic tests. Untracked q5 diagnostic scripts are removed locally. Unrelated files such as `.vscode`, `.worktrees`, and current device configuration edits are preserved.

After unit tests, targeted compilation checks, and code review pass, both branches are pushed. Measurement-PC instructions first preserve unrelated worktree state, then fast-forward the appropriate branch; upstream tracked deletions remove the obsolete runners automatically.

## Verification and failure handling

The work is complete only when:

1. all 287 manifest entries exist at their intended standard destinations with identical hashes;
2. the temporary top-level q3 and q5 data roots no longer exist;
3. generic predistortion and five-point tests pass in both repositories;
4. no production source or test refers to a removed qubit-specific runner or temporary data root;
5. both remote production branches point at the reviewed commits.

Any collision, checksum mismatch, unknown data layout, test failure, or review finding stops the corresponding operation before cleanup or push.
