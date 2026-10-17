# Refactor handoff — read this first

Branch: `qicklab_refactor` (from `bfc_code` @ 0f0a51f). Last updated 2026-10-14 (END of session 2 on macOS: 18 research-review findings landed; eight more are
parked, unlanded, on branch `qicklab_refactor_wip`; see TRANSFER STATE below).
Claude Code session that produced this: https://claude.ai/code/session_01LV3mPq1wVnxztiZabqm3RY

## Goal (user's words, condensed)
Complete refactor of the QM_Team code base: dense and hard to follow; runner only works for one qubit
parameter set (new device = new parameter file, same experiment code); far too many comments; bookkeeping
scattered. Be terse, keep only what is needed, add a parameters/reference docs page with pedagogy in mind,
preserve existing functionality, atomic commits, old code recoverable from `bfc_code`, follow best practices.
Orchestrate with dynamic workflows dispatching Opus 5.5 agents; the orchestrator checks itself.

## Decisions already taken with the user (do not re-ask)
- Flatten to a top-level package `qicklab/` (hardware/core/experiments/analysis/runs/twpa) + `devices/` + `runners/` + `tests/` + `docs/`.
- Device files are Python dataclasses (`devices/CSTQ03.py`), not TOML.
- Lab-note comments move to `docs/` (device files may keep short dated inline history).
- ruff + pytest installed; `pyproject.toml` committed. Push target: `origin` (houcklab/HouckLab_QICK).

## Where things are
| What | Path |
|---|---|
| Design spec v3 (layout, migration map, Device/Session/PLAN API, invariants, verification ladder, commit plan) | `docs/dev/refactor-2026-10/design.md` |
| Phase-3a execution brief (the next step) | `docs/dev/refactor-2026-10/brief_3a.md` |
| Per-subsystem audits (symbols, cfg keys, dead code, lab notes, bugs) | `docs/dev/refactor-2026-10/audit/` |
| Design critiques that shaped v3 | `docs/dev/refactor-2026-10/critique_{user,eng}.md` |
| Open lab questions raised by the docs writers (for the user) | `docs/dev/refactor-2026-10/docs_open_questions.json` and `docs/devices/CSTQ03.md` "Open items" |
| Environment lock of the machine the golden was generated on | `docs/dev/refactor-2026-10/requirements-lock.txt` |
| Regression harness (acceptance test for every commit) | `tests/regression/` (README explains) |
| Symbol map + AST/binding equivalence checker for phase 3a | `tests/refactor/` (README explains) |
| Docs tree (written ahead of the code, describes the target API) | `docs/` |

## Commit log so far (all on `qicklab_refactor`)
1. `077e9c2` test(regression): harness v1 + golden
2. `e42007d` chore: pyproject
3. `e67c24d` docs: documentation tree (42 pages)
4. test(regression): harness v2 — display runs for real, save_data/save_config digests, synthetic boards A and B, per-(cls,path) budget, variant + multi-flag labels, frozen legacy runner fixture, qick version pin, recording cfg; golden regenerated ON THE LEGACY CODE
5. test(refactor): symbol map (593 entries, 52 files) + equivalence checker (AST modulo renames + free-name binding check + ledger)
6. docs(dev): this handoff + planning artifacts + CLAUDE.md pointer
7. `650b0250` docs(dev): macOS test environment — exact pins install on Homebrew Python 3.13.2 arm64
   (`requirements-macos.txt`); the only mismatch was `python3` = miniforge 3.9
8. `9b8540ba` test(regression): golden regenerated on macOS on the untouched legacy tree (platform note
   applied: 804 fit-output diffs in 15 labels, incl. the `pulse_freq` carry-over in the two transmission
   multi-flag labels; three captures byte-identical; 106 passed). Session 2:
   https://claude.ai/code/session_01Si1tqwikwVWbWUzWwbxDCY

9. `5dc9e120` refactor: 3a-i — every whole-file row git-mv'd into `qicklab/`, explicit imports, renames +
   aliases, `driver_qicklab` is the DRIVER, `tests/test_imports.py`; equivalence `--phase 3a-i` PASS
   (341 AST / 341 bindings), pytest 147 passed, golden byte-identical. Harness fixes in the same commit:
   the golden fixture undoes the capture patches at module teardown (they leaked `savefig` no-ops into
   later test modules), `CURRENT_PHASE` in `tests/refactor/test_equivalence.py`, checker self-test runs on
   a copy of the legacy worktree, transitional ruff per-file ignores in `pyproject.toml` (3b removes them).

10. `b87f4dd0` refactor: 3a-ii — the twelve remaining files split into 32 destination modules per the map,
    `WorkingProjects/` deleted, consumers retargeted, driver clock loop removed, `CURRENT_PHASE = "3a-ii"`;
    equivalence strict + phase-less PASS (505 AST / 505 bindings), pytest 170 passed, golden byte-identical.
11. `bd2d85ec` style: 3a-iii — `ruff format` + isort only (listed in `.git-blame-ignore-revs`); equivalence
    PASS, pytest 170 passed, golden byte-identical.

12. `a3924c28` refactor(hardware) — area 1 (+ the equivalence gate enters 3b: structural only, pending deletions allowed)
13. `62e3a660` refactor(core) — area 2 (pure `data_paths()`, dead go/load_data, comments)
14. `3b405ba4` test(refactor): 3b gate follows `final_module`; synthhd import allowlist
15. `98f70b8c` refactor(analysis) — area 3 (min_q_range_phase, fit_exp_decay, fit_rabi_cosine, spec Lorentzians,
    hist_process(normalize=...) merge, classify_thermal_tail, dead code, verified identical-result improvements)
16. `791d395c` refactor(twpa) — area 7 (hardware/pnax.py, hardware/synthhd.py, yoko ramp_current, twpa/common.py;
    all five scripts kept)
17. `07f9900d` refactor(experiments) — area 4, basic experiments (rotate_iq deleted, `if True:` flattened, comments,
    verified identical-result improvements)
18. `742d357e` refactor(experiments) — area 5, advanced (single_shot ~550 dead lines + readout_optimize *_Higher*
    classes deleted; ModifiedRamsey's readout window / active reset / schedule ledger are core/readout.py,
    core/active_reset.py (ActiveResetMixin), core/schedule.py; ARV/SingleShot/Undriven keep their own copies)
19. `818a782a` refactor(runs) — area 6 (analysis.iq.kmeans_split, analysis/plotting.py, core/io.py,
    auto_coherence merges into yoko.ramp_to / spectroscopy.find_two_tone_peaks)
20. 3b-done: `CURRENT_PHASE = "3b-done"` — the structural gate is strict again (every 3b deletion/merge done)
Each 3b area commit: full pytest 170 passed on an isolated snapshot worktree, golden byte-identical,
adversarial old-vs-new review (reject → fix → approve where needed). Workflow script per area:
`~/.claude/projects/.../workflows/scripts/qicklab-3b-area-*.js` (cleanup agent, reviewer, fix loop, args =
area brief). User decisions 2026-10-13: functionality-preserving improvements are applied inside 3b
commits with a proof of identical results (reviewer re-verifies); behaviour-changing improvements and the
known bugs become a separate phase of individual commits after 3b (user: "make these improvements as you
see fit"), preceded by a research-effectiveness review workflow (one Opus agent per measurement domain).

21. `0cf3b82c` docs(dev): research-effectiveness review (85 verified findings; `docs/dev/refactor-2026-10/review/`)
22. `2a21c17f` fix(active_reset_verify): F09 — ARV runs the shared reset block (golden: 16 hw leaves, ARV reset-ON)
23. `578518d2` fix(active_reset): F00 — stall for the read latency before the reset read (golden: 32 hw + 50
    cfg_access leaves, reset-ON MR/ARV programs; needs the documented hardware validation)
24. `70aebbec` fix(runs): F08 — finish() helper saves the record even when display() raises (golden: 0 leaves)
25. `5ba679cb` fix(ramsey): F01 (+F12, T2R guard, F67) — principal-axis projection, sampling bounds, guarded
    display (golden: 660 leaves, all T2R display `sets` in 4 labels; the 5 per-board raised displays now fit)

26. `aefb2214` fix(hmm): F06 — i.i.d.-null likelihood-ratio gate and resolved-rate gate (golden: 0 leaves)

27. `8436b708` fix(runs): F11 — T1-SS calibration in its own cfg (golden: 56 RunT1SS leaves, dead keys gone)
28. `c65810e8` fix(active_reset): F22 — res_phase wrapped mod 2^b_phase (golden: 0 leaves)
29. `36344a3c` fix(fitting): F13 — one FFT-seeded Nyquist-bounded Rabi fit (golden: 0 leaves)

30. `c46424ce` fix(runs): F28 — yoko_fixed charge sweeps record the held bias + repeat axis (golden: new label
    RunChargeSweep[yoko_fixed], 0 leaves elsewhere)
31. `8164e138` fix(t2_echo): F23 — even/zero num_pi_pulses rejected (golden: 0 leaves)

32. `0d9f4437` fix(runs): F15 — MR validation controls acquired regardless of the analysis flag (golden: 394
    leaves, the new control experiments in RunModifiedRamsey[*])
33. `94f6a24e` fix(acquisition): F18 — strobe blocks compile reps_per_block (golden: 4 hw leaves, ZSP[validate])
34. `736c8fac` fix(zero_span): F17 — event-based baseline rate, iterated burst exclusion (golden: 0 leaves)

35. `2859f222` fix(readout): F10 — thermal-mode population by a two-cloud EM fit (golden: 0 leaves)
36. `8fdde7ca` fix(runs): F03 — transmission_fit carries the display fit's minimum (golden: 24 leaves, the
    two transmission carry-over labels' downstream pulse_freq/program/config digests)

37. `4ecf0ba1` fix(rabi): F26 — rotation from the analysed read, fixed sign, contrast diagnostic (golden: 88
    data_digest leaves in the four Rabi labels)

Session 3 (Windows PC, 2026-10-14; https://claude.ai/code/session_013hKCT9KZpyGQ3BqMAGCkXk):
38. `2b699295` test(regression): golden regenerated on Windows (i7-11700F, scipy-openblas 0.3.30, numpy 2.4.1):
    1064 leaves, sets 716 + data_digest 348 in 16 labels per board, nothing else; two further captures
    byte-identical (sha1 ea536087…)
39. `ba997e58` fix(yoko): F21+F53 — open_charge_yoko / enable_current_output_safely / two-sided ramp_to guard
    with readback (golden: 838 leaves, all yoko_writes, every label on both boards)
40. `5f9342b2` fix(spectroscopy): F04 — doublet selection (min_sep in every branch, window clip, seed/edge/
    duplicate/quarter-step gates, min_sep hand-off + provenance keys in ZSP cfg) (golden: 304 leaves = lorentz_*
    data_digest in 6 labels + 2 ZSP cfg keys and cfg_digest in RunZeroSpanParity[*]); four Opus review rounds here
    (one reject: the first sub-grid gate at 0.5 step dropped real lines; now 0.25). DEFERRED: partner significance
    gate (F04 (c) second half): below SNR ~15 on the ZSP grid a single line is often paired with a noise maximum
    (source one_lorentzian_center_plus_peak) and the run parks between the parity lines without error; needs a
    partner-height-over-noise threshold (design decision + golden change).
41. `4e6418b8` fix(coherence): F02+F34 — bounded, guarded fit_exp_decay (dict result, ok criteria incl.
    |a| >= 3 a_err) saved as t1_fit_* / t2e_fit_* in the h5 (golden: 684 leaves = new display `sets` + new fit
    datasets in the 7 T1/T2E labels; nothing else). Not done: T2R fit saving, T1/T2E in the AutoCoherence summary.
42. `5eb2063b` fix(zero_span): F19 — stage-8 controls: gain restore, rebuilds (base rebuild in a finally),
    stitched 200 ms records, batch-means se + Welch/Student-t thresholds, both_branches_respond / branch_ratio /
    complementarity / midpoint null, variants table in EVIDENCE.md (golden: 24 hw/count leaves, ZSP[validate] only);
    three Opus rounds. FOLLOW-UPS: stages 1-2 set_qubit_gain(base) sits after the _preserve_cfg block, not in a
    finally; se_batch_us (10 ms) is not tied to the measured dwell (se ~2x too small at a 30 ms dwell);
    min_record_us / se_batch_us / k_sigma are not exposed in Control_params; control C has no decision statistic.
43. `988b1acb` fix(transmission): F25 — hanger_fit_kappa_tot_mhz / _ext_mhz = |f0|/Q in MHz replace the 1e6-too-small
    external-only key; four stale docs pages fixed (golden: 24 data_digest leaves, the 4 RunTransmissionSweep* labels).
    Follow-ups: docs/adding_a_device.md:100 "6/kappa" should name the angular kappa; the Q lower bound 1e2 caps
    kappa at |f0|/100 on a small IF axis (pre-existing).
44. `e513085f` fix(modified_ramsey): F16 — model-free lag-covariance statistic (interior-trimmed, baseline-band
    corrected, block bootstrap) drives echo_null / flip_final_pi2 / drive_off verdicts; drive_off decisive with a
    symmetric 0.1 rule (golden byte-identical: no label runs the analysis). Four Opus rounds here, three rejects
    (NaN-error flip rule, drift-filter edge bias, interior bias at CSTQ03 contrast). TIER C left: add drive_off to
    the default validation_controls and confirm the 0.1 budget on the fridge; the per-record lag sum is not in
    _analysis.json; K is per record (a control with a slightly different rep period can lose the comparison).
45. `e4d960c4` fix(single_shot): F48 — T1_SS and the Undriven charge sweep save the completed points on abort
    (sweep_completed / points_completed + cfg aborted) and retry the shot-counter race (golden byte-identical).
46. `9721f8f1` fix(readout_optimize): F33 — qubit-pulse map brackets each gain row with shared |g> blocks (463
    programs instead of 882), g_ref_index / g_block_time / g_drift_* saved, gated drift warning (golden: 48 leaves,
    SingleShot_QubitOptimize hw counts + fid/overlap digests + the four new keys).
47. `72147fe5` fix(spectroscopy): F05 part 1 — partner significance gate (MIN_PARTNER_SNR 5, edge baseline,
    parity_partner_snr provenance, min_partner_snr overrides), estimate_noise_floor dedupe; three gate-off harness
    labels keep the ZSP pipeline and the two-tone quasi-CW record under the golden (43 labels per board) (golden:
    114 leaves in the plain ZSP / two-tone labels, which now raise / step to budget on the noise-only harness
    spectra). Not done: F05 part 2 (joint 1-vs-2 line fit, tier B) and AutoCoherence |I+iQ|^2 -> project_iq_signal.
48. `5f72d402` fix(zero_span): F07 — apriori_gmm (two-Gaussian ML threshold on the record's own scores, bits withheld
    when not bimodal, classifier_* fit fields in the summary) is the default ZSP classifier; 'apriori' aliases it,
    'apriori_midpoint' keeps the old behaviour (golden byte-identical). TIER C left: automatic resolved-jump warning /
    HMM classifier; noise-crossing rate inflation is documented (bin, or SNR >= ~5), not fixable per sample.
49. `0384a482` fix(experiments): F14+F20+F24+F27 — every regime-A program uses cover_readout_window (window 4608
    samples, tone 6581, measure waiti 6580; generator-clock tone/drive lengths; T1_SS normalises by the declared
    window; ZSP read_length on the readout clock 1536 + compiled-period check) (golden: 6254 leaves, hw/data_digest/
    sets in 33 labels; no cfg_access/outcome/yoko change). Averaged regime-A IQ amplitudes are NOT comparable with
    records before 2026-10-15. Left: the hard-coded [0, 1] readout loops (switching to ro_chs drops ADC 1 from the
    payload: separate change); sample_period_us_compiled not added.
50. `0397f869` fix(runs): tier-B batch B1 — F51 DAC gain guard (0..32767, constructor + build_context + run-level +
    ZSP set_qubit_gain), F52 resonator carry-over quality gate (assess_resonator_fit: depth, half-power width, edge;
    pulse_freq left unchanged on failure), F84 honoured run parameters (transmission_sweep reps/rounds, two_tone_spec
    peak kwargs, trans_qubit_spec gain 800 / relax 2500, flattop_relax_delay) (golden: 96 leaves = RunTrans_QubitSpec
    gain/relax/program + the two transmission combo labels' pulse_freq no longer carried from noise). Follow-ups:
    ZSP stage-7 power knob unguarded; charge_sweep / charge-dispersion keep spec gain only when Gauss; transmission
    JSON pulse_freq is display's fit minimum even when the gate rejects it.
51. `192e09a3` fix(coherence): tier-B batch B2 — F83 (tProc cycle from soccfg, quantised_t2e_step), F78 (realised wait
    axes), F29 (virtual Ramsey detuning f_virt_mhz, detuning_mhz; SIGN of the f_ge correction unverified on hardware:
    one-time check with freq_shift = +0.05), F65 (warn-only AutoCoherence timing checks, T1_expected_us pre-flight),
    F68+F79 (principal-axis rotation for T1/T2E), F66 (T1_SS two-pass model-weighted fit, readout-corrected population,
    pi_gain played), F82 (AutoCoherence Qubit_Pulse != Qubit_Readout guard) (golden: 4956 leaves in the 9 coherence
    labels: cfg step / phase_step / f_virt_mhz, T2R program hashes, fits and axes, T1_SS keys). 27 + 3 Opus agents.
52. `e81a68fc` fix(auto_coherence): tier-B batch B3 — F35 (sweet-spot walk: SNR gate on every spectrum, start-voltage
    gain raise, one pass with a visited set, re-acquire at the best, failure flag; MRC marks the cycle not verified;
    calibration sweet_spot_found / sweet_spot_sep_mhz), F64 (pi gain from a cosine fit with argmax fallbacks; Stage 2.5
    shortest-window-within-SE rule; extended mode per N) (golden: 570 leaves in RunModifiedRamsey_Control(+verified)
    only). Known: extended mode still returns the best step across all N; ss_target_fidelity compares the measured
    scan contrast, not the fitted maximum.
53. `5b5f8c3f` fix(readout): tier-B batch B4 — F63 (single-shot family on cover_readout_window), F62 (hist_process exact-CDF
    contrast and threshold, self-consistent (fid, threshold)), F61 (single-shot figures of merit saved per read),
    F60 (map uncertainties + smoothed recommendation), F59 (labelled two-Gaussian overlap + snr_mat; MixedShots deleted,
    symbol map row) (golden: 2668 leaves in 12 labels, all downstream of the SS threshold plus the new keys).
54. `8d92d564` fix(spectroscopy): tier-B batch B5 — F36 (hanger fit in (f0, Qint, Qext): the Qtot/Qext twin is unreachable,
    sandwich covariance, propagated hanger_fit_*_err keys), F37 (ChiShift joint two-trace fit: chi_fit / chi_err with a
    'resolved' flag, chi_argmin kept), F69 (constant_tone / constant_two_tone are true periodic CW tones, one program,
    reset_gens in a finally; the harness makes input() raise EOFError), F70 (lorentz_*_err, Rabi fit perr, AmplitudeRabiFF_N
    fit keys, hanger pcov), F71 (gain-length sweep summary: peak SNR, saturation fit, T2* bound, recommendation) (golden:
    474 leaves in 19 labels: hanger values on the pure-noise fixture incl. the pulse_freq carry-over, new keys, the two CW
    labels down to one program). Known: a magnitude-only hanger fit does not resolve under/over-coupling; the chi fit's
    b-delta trade-off below ~kappa/4; a doublet never resolved in a gain group is fitted as one line.
55. `9410e436` fix(zero_span): tier-B batch B6 — F75 (vectorised sliding-window rates, covered_us normalisation, partial-window
    burst threshold), F76 (one bin-rate estimator, (n_bins - 1) denominator), F73 (censored sampled-telegraph dwell MLE with
    the joint two-state inversion; tau_mle_* / tau_err_*), F32 (readout eps, spurious-rate estimate, ACF / PSD / HMM rates and
    an agreement line in ZSP; ts_hmm_* in Undriven), F45 (batch-means SE contrast SNR with a look-elsewhere significance
    check), F43 (rule 4 = 2e7 memory cap + streaming-headroom warning; chunk_wall_clock_ends; defaults NOT changed), F44 (ZSP
    validation stages 1-3 before the main record on a fresh instance; probe / drive-line adoption gates; stage-3 recipe gate;
    kmeans + stage 3/8/7 fail-fast), F74 (slim UndrivenSingleShot h5 layout: float32 raw, SoftLink aliases, uint8 labels)
    (golden: 434 leaves in 4 labels: undriven bin rates + ts_hmm_* keys, ZSP wall-clock ends, [validate,gate_off] experiment
    order). Known / follow-ups: F43 defaults decision (n_chunks 1 / reps_per_chunk 600000 would move the ZSP program hashes;
    n_chunks == 1 path saves no chunk_wall_clock_*; measured rep period from prog.stats not recorded); F44 order 1-2-3 not
    1-2-1-3, stage 1 drives at the unrefined line, line-swap hazard above half the splitting, ZSP_ParityFreqs_Cached not
    updated; F32 PSD not gap-aware, HMM cut to the first 1e5 samples; F73 stage-7 mean_dwell still the arithmetic mean,
    threshold_stability default percentiles sit inside a cloud; F75 covered_us not saved; F74 Repeat 10000 still the runner
    value (documented cost).
56. `7d6e7c5e` fix(modified_ramsey): tier-B batch B7 — F31 (predict_parity_mapping two-level propagator; echo_null marked
    'not a null' above a 0.2 predicted residual ratio and excluded from the decisive checks), F39 (drive_detuned judged as
    an inverted mapping with a reset-pi transfer gate; tau_offset defaults to the predicted null: even harmonic, or the
    solved zero in the symmetric scheme; runner control_tau_offset_frac 0.25 -> None), F30 (mapping probabilities fitted
    with the rate, gate at the fitted mapping, mixture i.i.d. null, predicted-mapping seed), F38 (clean readout clouds
    from a labelled two-Gaussian mixture; MR emissions use them under a fitted/calibrated mapping), F42 (f_ge-vs-qubit
    guard, warn by default, require_f_ge_near_qubit opt-in), F41 (MRC runs the MR sequence via build_modified_ramsey_cfg
    with a SingleShot at V_sweet; true-state-separation normalised lag-covariance ratio with a predicted prep
    correction), F40 (charge_sweep_voltages, joint doublet refit, smoothed quarter-max censor bound, splitting fit in the
    npz), F72 (quasi-CW parity analysis with self-calibrated readout and the program's rep period) (golden: 898 leaves in
    3 labels: F31 keys on the MR control records; MRC[verified] re-sequenced by the SingleShot_MRCalib records). Known /
    follow-ups: F31 1-2-1-3 order and mapping seeding beyond the HMM seed; F39 tau_offset / drive_detuned not in the
    runner's validation_controls; F30 i.i.d.-LR / resolved-rate gates (tier C); F38 reset threshold and apriori separator
    stay on the raw e centre; F41 SS pi still at ctx.qubit_frequency_center, num_cycles 1000 documented; F40 S vs T
    period open, 5 mV grid reports undersampled; F72 relax_delay / active reset in the QCW program (tier C). Two
    orchestrator test edits (doublet-selection FakeQcw.prog; latency test's MRC case now compiles) are in the commit.
57. `698f31d1` fix(infra): tier-B batch B8 — F77 (h5_array convert-first saves, H5File.add replaces, NumpyJSONEncoder
    bool/complex, save_config tmp + os.replace with Windows retries and in-place fallback, unique_data_paths _1/_2
    suffix), F80 (make_proxy timeout 300 s; build_context rfsoc_host/port/name/timeout_s kwargs), F81 (attenuator
    set_attenuation with dll_dir, full device search, device range check, error codes; import-time DLL registration
    gone; symbol-map row 'deleted' 3b) (golden identical). Known: same-second two-process collision when the first
    crashes before save_config; save_config's datafile() handle not closed (pre-existing); timeout not derived from
    avg_maxlen.
58. `d5efdf29` fix(twpa): tier-B batch B9 — F55 (pump_sweep ranked on band-mean gain against a per-row pump-OFF trace;
    gain_min / ripple; atomic per-row saves, honest 'NOT saved'), F54 (TWPA state log twpa_state.jsonl on every exit with a
    bias readback and a confirmed/unknown pump state; gain_compare LEAVE_PUMP_ON, set_pump --on; bring-up order
    flux_sweep -> set_bias -> pump_sweep -> gain_compare -> set_pump --on; conftest sandboxes TWPA_STATE_DIR) (golden
    identical). Known: phase-5 session stamping / connect() warning wait for Setup.twpa; leaving the pump on relies on
    interpreter exit not closing the SynthHD; PNA-X / yoko opened before the try; not verified against pywindfreak.
59. `1c95731c` fix(io): tier-B batch B10 — F46 provenance (h5 attrs['provenance'] + <stem>_provenance.json beside every
    save; session record from build_context incl. device; last yoko landed level from ramp_to / ramp_current; program
    hash; save_record takes the acquiring experiment; TWPA / heatmap / ARV / analysis sidecars) (golden identical).
    Known: no yoko read-back at save time; save_cycle_summary, auto_coherence summary, zero_span_validation sidecars
    and spectroscopy.py npz carry no provenance yet; save_config's open datafile() handle and dead cname guard are
    still separate commits.
TIER B IS COMPLETE (items 50-59). Skipped by decision: F47 (= F21+F53). Phase-5a inputs, not commits: F49, F50, F56,
F57, F58.
60. `837e0d45` refactor(cfg): dead cfg keys dropped — pulse_style (BASE_CONFIG + trans_config) and the runner's ts gain keys
    (start_ts_gain / end_ts_gain / ts_step; build_context still accepts ts and ignores it); allowlist in
    tests/regression/README.md 'Allowed cfg diffs'; symbol-map row for the runner's ts -> deleted 3b (golden: 2668 leaves,
    all the four keys in cfg / config digests / cfg_digest; hw, sets, cfg_access, yoko_writes, outcome identical).
TIER A IS COMPLETE. Next: tier B in batches (plan: scratchpad tierB_plan.md of session 3 -> copied below), then the
dead-cfg-key commit, 5a, 5b, 6, docs rewrite, merge back.
Tier-B batches (one workflow, one regeneration, one commit each): B1 F51 F52 F84 | B2 F29 F65 F78 F83 F68+F79 F66 F82 |
B3 F35 F64 | B4 F59 F60 F61 F62 F63 | B5 F36 F37 F69 F70 F71 | B6 F32 F43 F44 F45 F73 F74 F75 F76 |
B7 F30 F31 F38 F39 F40 F41 F42 F72 | B8 F77 F80 F81 | B9 F54 F55 | B10 F46 alone. Skip F47 (= F21+F53).
Landed: B1-B10 (items 50-59) and the dead-cfg-key commit (60). Next: 5a (brief + workflow in the session scratchpad:
brief_5a.md, workflow_phase5a.js), 5b, 6, docs rewrite, merge back.
Phase-5a inputs, not commits now: F49, F50 (Device.validate), F56, F57, F58.
ALL EIGHT PARKED ITEMS ARE LANDED (39-46). `qicklab_refactor_wip` is deleted; the per-item table in TRANSFER STATE is
historical. Pushed to origin after 46.

## TRANSFER STATE (2026-10-14, end of macOS session 2) — READ THIS BEFORE ANYTHING ELSE
The macOS machine is being left; the next machine is a Windows PC that is NOT the final lab PC (the lab PC
is where the code runs in the end; see "End state"). Everything needed is in git, nothing on the Mac.

**Branches (both pushed to `origin`):**
- `qicklab_refactor` — 44 verified commits since `eecd7f98` (every one passed the full ladder; golden
  byte-identical except the per-commit allowlists written in each commit message). Head = this HANDOFF commit.
- `qicklab_refactor_wip` = `qicklab_refactor` + two UNVERIFIED commits holding the working tree of the
  eight in-flight findings when the session was cut:
  1. "wip: reviewed, unlanded fixes F04 F21+F53 F16 F02+F34 F19 F25" — agent-complete edits (plus their new
     tests and docs). Quick ladder on this tree passed (compileall, `ruff --select F`, `ruff format --check`,
     and all tests except the golden suite); the GOLDEN SUITE WAS NOT RUN on it and the golden is unchanged, so
     `pytest tests/test_golden.py` is expected to fail there until each item is landed with its golden regen.
  2. "wip: interrupted implementers F33 F48 (partial, unreviewed)" — the implementer agents were stopped
     mid-work. Treat as a starting point only: either finish+review them or `git revert` that commit and
     relaunch the two items from `review/findings_with_refuter_notes.json`.
  Never merge `qicklab_refactor_wip` as-is. Land items one at a time onto `qicklab_refactor` (procedure
  below), then delete the wip branch.

**Per-item status** (agent reports and the last reviewer verdict for each are in
`review/inflight/<ID>.json`: `status`, `last_report`, `last_review.findings`):
| ID | Files (from `git diff qicklab_refactor qicklab_refactor_wip`) | State at cut | Expected golden impact |
|---|---|---|---|
| F04 doublet selection | analysis/spectroscopy.py, experiments/qubit_spec.py, runs/zero_span.py (one `min_sep_mhz=` line), tests/test_doublet_selection.py, docs two_tone_spec.md | refix done, re-review round 2 interrupted; 2 open should-fix (tests for the two_highest_peaks min_sep rule and for the zero_span `min_sep_mhz` plumbing) | only RunSpecGainLengthSweep (`experiments[1]` lorentz_* 0→1 length); ZSP labels unchanged |
| F21+F53 yoko safety | hardware/yoko.py, twpa/set_bias.py, twpa/flux_sweep.py, core/context.py, tests/regression/capture.py (FakeYoko), tests/test_yoko_safety.py, docs hardware.md/twpa.md/architecture.md/troubleshooting.md/charge_sweep.md/undriven_single_shot.md/charge_transmission_sweep.md, tests/regression/README.md, comment line in experiments/undriven_single_shot.py | three review rounds, all approve; 2 should-fix left (report hygiene; "all 40 labels change in yoko_writes" which IS the intended impact) | `yoko_writes` on every label (new state queries, LEV 0 before OUTP ON, LEV? readback per ramp_to); nothing in cfg/hw/data. `TWPA_YOKO_ADDRESS` moved into hardware.yoko: add a `final_module` row in tests/refactor/symbol_map.py or a re-export, or test_equivalence fails |
| F16 parity-control verdicts | analysis/modified_ramsey.py (compare_parity_controls), tests/test_modified_ramsey_offline.py, docs modified_ramsey.md (+ new docs/experiments/modified_ramsey_control.md if present) | fix round 1 done, unreviewed; 3 should-fix from review 1 (echo_null resolved-rate gate precedence, Hessian-only errors in the flip-rate agreement test, drive_off threshold vs CSTQ03 numbers) | none expected (offline analysis) — verify with diff_labels on RunModifiedRamsey[*] |
| F02+F34 T1/T2E fit guard | analysis/fitting.py (fit_exp_decay), experiments/t1.py, t2_echo.py, tests/test_exp_decay_fit.py, docs t1.md/t2_echo.md/auto_coherence.md/coherence_combos.md/interleaved_coherence.md/running_a_session.md | implementer done, review 1 interrupted → run the rereview workflow | T1/T2E labels: fit outputs (`sets`/data_digest) and possibly new saved keys; see last_report |
| F19 ZSP validation stage 8 + B2-B4 | runs/zero_span_validation.py, analysis/zero_span_checks.py, tests/test_zero_span_validation.py, docs zero_span_parity.md (validation sections only) | implementer done, review 1 interrupted → rereview | ZSP[validate] label only, per last_report |
| F25 kappa units | experiments/transmission.py, runs/resonator.py print, tests/test_transmission_kappa.py, docs transmission_fit.md/transmission_sweep.md | review 1 rejected (1 must-fix: four docs pages incl. docs/devices/CSTQ03.md still say the kappa printout is 1e6 too small); fix round interrupted → finish the docs fix, then rereview | none in data; print text only (methods/cfg unaffected) — verify |
| F33 g-reference bracketing | experiments/readout_optimize.py (+ docs qubit_optimize.md) | implementer interrupted (partial) | SingleShot_QubitOptimize only: n_programs 882→483, hw digest, fid_mat/overlap_mat |
| F48 partial save on abort | experiments/undriven_single_shot.py, t1_single_shot.py, tests/test_partial_save.py, docs averaging.md/t1_single_shot.md/undriven_single_shot.md | implementer interrupted (partial; the test file exists) | none on the success path |

Shared files touched by more than one item: experiments/undriven_single_shot.py (F21 one comment line +
F48), docs/experiments/undriven_single_shot.md (F21 + F48), docs/architecture.md, docs/troubleshooting.md
(F21 + others). Use `tools/hunk_filter.py [--invert] <regex> <files>` to split them at landing time.

**Landing procedure on the next machine (per item, one commit each):**
1. Environment: Python 3.13 (`py -3.13 -m venv .venv`, `.venv\Scripts\activate`), `pip install -r
   docs/dev/refactor-2026-10/requirements-test.txt` (exact pins; on macOS the same pins installed cleanly with
   Python 3.13.2 — see requirements-macos.txt). Then on a CLEAN `qicklab_refactor` checkout run
   `python -m pytest tests` (~11 min on the Mac). The golden (`tests/regression/golden_cstq03.json`) was
   regenerated on macOS (commit 9b8540ba): a Windows BLAS can flip float roundings, so if the first run fails
   ONLY in `data_digest`/`sets` leaves, regenerate ONCE at the branch head (`REGRESSION_UPDATE=1 python -m
   pytest tests`, confirm two further captures byte-identical, classify with `tools/classify_golden.py`,
   commit as "test(regression): regenerate golden on Windows (<CPU/BLAS>, numpy x.y)" listing the leaf
   classes). Any diff in `cfg`/`hw`/`methods`/`yoko_writes` on the clean head = wrong environment (check
   `qick==0.2.334`, numpy/scipy pins): fix the environment, never the golden. Do not land anything until the
   suite is green and stable.
2. Bring one item's files over: `git checkout qicklab_refactor_wip -- <its files>` (or `git diff
   qicklab_refactor qicklab_refactor_wip -- <files> | git apply`; hunk-filter the shared files). New files:
   same command. Check `git diff --stat` shows only that item.
3. If its `review/inflight/<ID>.json` status is not "approved, no open findings": run the rereview workflow
   (`tools/workflow_rereview.js`, args `{id, item (the finding JSON from review/findings_with_refuter_notes.json),
   files, context}`) or the apply-findings fix loop, then address what it returns. Claude Code's Workflow tool
   accepts `scriptPath` for files inside the repo; the scripts' RULES text still names the Mac repo path and
   `source .venv/bin/activate` — edit those two strings for Windows before use.
4. Fast ladder: `python -m compileall -q qicklab devices runners tests`; `ruff check --select F qicklab
   runners tests devices`; `ruff format --check qicklab devices runners tests`; the item's tests;
   `python docs/dev/refactor-2026-10/tools/diff_labels.py <labels> --variants A` (every differing leaf must be
   explained by the item).
5. Full suite with golden regen: `REGRESSION_UPDATE=1 python -m pytest tests -p no:cacheprovider`
   (`tools/land_fix.sh <tag> [paths]` does 2+4+5 in a scratch worktree under Git Bash; set `QICKLAB_SCRATCH`;
   on plain PowerShell run the steps by hand). CHECK THE EXIT CODE before committing. Classify:
   `python tools/classify_golden.py <(git show HEAD:tests/regression/golden_cstq03.json)
   tests/regression/golden_cstq03.json` and write every leaf class per label into the commit message.
6. Prune `[tool.ruff.lint.per-file-ignores]` with `tools/prune_ignores.py` if the item removed a trigger.
   Commit (`fix(<area>): <ID> ...`, with the Claude-Session trailer of the session doing the work), then append
   the commit to the log below and refresh "NEXT STEP".

**After the eight parked items:** remaining tier A: F05 (unify peak finding), F07 (ZSP apriori classifier;
needs F04 landed), F14+F20+F24+F27 (regime-A readout window → `cover_readout_window` in all programs); then
tier B (F29–F84, group tiny ones thematically; F46 provenance touches many files — do it when nothing else is
in flight); the dead-cfg-key commit (`pulse_style`, `ts`, ConstantTwoTone debug prints; allowlist + golden
regen); then phases 5a (Device/Session/recipes/PLAN + devices/CSTQ03.py + runners/CSTQ03_session.py; inputs:
design.md phase-5 section and findings F57/F58/F46/F49/F50/F51/F56), 5b (delete runners/CSTQ03_BFC.py and
driver_legacy), 6 (parameter registry + generated docs/parameters.md, reconcile docs with the real API), the
CLAUDE.md/AGENTS.md/README rewrite, then "End state" below. Tier C (needs the fridge) stays documented only
(`review/tier_c_and_gaps.json`).

**Tools now live in the repo** (`docs/dev/refactor-2026-10/tools/`): `diff_labels.py`, `classify_golden.py`,
`hunk_filter.py`, `prune_ignores.py`, `land_fix.sh`, and the three workflow scripts
(`workflow_apply_findings.js`: implementer → adversarial reviewer → fix, args `{"items":[finding,...]}` with an
optional `extra_instructions` string per finding; `workflow_rereview.js`; `workflow_3b_area.js`, historical).
`review/findings_with_refuter_notes.json` is `findings.json` plus each item's refuter notes/reasoning — use it
as the Workflow args source. The regression README lists the 40 labels.

The repo IS the qicklab package: `qicklab/`, `devices/` (empty init), `runners/CSTQ03_BFC.py` (legacy runner,
star-imports `qicklab.runs`, deleted in 5b), `tests/`, `docs/`. The lab code runs on the original Windows PC
in the end (user, 2026-10-13): keep Windows-only lines (DLL directory, `.env`, `Z:\` roots) and the TWPA
modules (`qicklab/twpa/*`, needed; `pywindfreak` is an optional extra, not a reason to drop them).

## NEXT STEP: remaining tier-A findings, then tier B, dead-cfg-key commit, 5a, 5b, 6, docs rewrite, merge back
The eight parked items are landed (session 3, this Windows PC). Procedure per item is unchanged (apply-findings or
rereview workflow with Opus agents, fast ladder, ONE full-suite golden regeneration at a time, classify, commit with
every leaf class in the message, handoff line). Order: F05 (what is left of its part (1): the partner significance
gate deferred from F04, estimate_noise_floor dedupe in auto_coherence/_spec_peak_snr and zero_span_checks; the
tier-B joint two-Lorentzian fit is a later item), F07 (GMM-threshold ZSP classifier as the new default; F04 landed),
F14+F20+F24+F27 (cover_readout_window in every regime-A program + ro_ch in ZSP; large golden change: hw digests of
every regime-A label and ZSP; do it when nothing else is in flight), then tier B (F29-F84, group tiny ones; F46
provenance touches many files), the dead-cfg-key commit, 5a, 5b, 6, docs rewrite, merge back (End state).
Open follow-ups recorded in items 40, 42, 43, 44 above (F04 significance gate = F05; F19 stages 1-2 finally /
se_batch_us; F25 adding_a_device.md; F16 tier C).

## Phase 3b plan as executed (one commit per area, adversarial old-vs-new review each)
Areas in order (shared helpers first): 1 hardware, 2 core, 3 analysis helpers (+ switch callers), 4 experiments
basic, 5 experiments advanced (single_shot / readout_optimize deletions, MR dedupe into core/readout,
core/active_reset, core/schedule only where the audit proved identical math), 6 runs (dedupe KMeans/plot/save
into analysis.iq / analysis.plotting / core.io), 7 twpa (common.py, hardware/pnax.py, hardware/synthhd.py;
all five TWPA scripts stay). Sources: design.md migration-map "phase-3b cleanup notes" + comment policy,
the 3b rows of the symbol map (deleted with audit citation / merged with proof), the audits' "Lab notes to
migrate" tables (the docs tree already holds most notes: verify on the named page, add if missing, delete
the comment). Decision 2026-10-13: dead cfg keys (`pulse_style`, `ts`) are NOT dropped in 3b — that is a
later dedicated commit with an allowlist + golden regeneration — so every 3b commit keeps the golden
byte-identical. Ladder per area: compileall, ruff --select F (shrink the transitional per-file ignores in
`pyproject.toml` as the legacy bodies go), equivalence `--phase 3b` (structural: deleted symbols gone,
merge targets present), full pytest with the golden unchanged.
Then 3a-iii is done; 3a-iii (format), 3b (per-area cleanup with adversarial review), 5a/5b (Device/Session/
recipes/PLAN, delete legacy runner), 6 (parameter registry → generated parameters.md; reconcile docs), rewrite
CLAUDE.md/AGENTS.md/README, then the approved bug-fix commits. Full list and order: design.md "Commit plan".

Known gotchas for 3a (from the symbol-map agent): `runs/singleshot` needs `from datetime import datetime`
(the class) and `import os`; `runs/coherence` needs `import time`; `mSpecSliceFF` needs `curve_fit`;
`verify_ModifiedRamsey_timing._REPO_ROOT` uses `Path(__file__).parents[N]` and breaks after moving to
`tests/hardware/`. Three symbol placements deliberately differ from design.md (recorded in
`tests/refactor/README.md`): `transition_matrix_2state` → `analysis.rates`; `_stage_sweet_spot_search` and
`_choose_next_voltage` stay in `runs.auto_coherence`; `analysis/telegraph` is split into `hmm/rates/dwell/undriven`.

## Rules (non-negotiable)
- The golden (`tests/regression/golden_cstq03.json`) is regenerated ONLY with a written, per-label justification;
  refactor commits never change it (allowed: the documented dead-key allowlist in tests/regression/README.md).
- Bug fixes are separate commits, one per bug, after the user approves the list in design.md "Known bugs".
- Experiment class names, cfg key names, data paths (`outerFolder + path`, timestamp formats) are unchanged.
- No hardware access at import time; never regenerate the golden on a machine with a different qick version
  (the golden stores `qick.get_version()`; pin is `qick==0.2.334`).

## Setting up on a new machine (macOS / Linux / Windows)
```
git clone https://github.com/houcklab/HouckLab_QICK.git && cd HouckLab_QICK
git checkout qicklab_refactor
python3 -m venv .venv
source .venv/bin/activate                 # macOS/Linux        (Windows: .venv\Scripts\activate)
pip install -r docs/dev/refactor-2026-10/requirements-test.txt   # pinned, cross-platform, ~15 packages
python -m pytest tests                    # ~11-15 min; expect: all pass (platform note below)
```
Python 3.13.5 was used; 3.11+ is required. Windows PC (session 3): the `py` launcher only had 3.8/3.9, so
`winget install --id Python.Python.3.13 --scope user` was used (3.13.15); the pins installed cleanly. That PC has
16 GB RAM: run ONE golden capture at a time (three concurrent captures were all killed for low memory); a full
`pytest tests` takes ~14 min there, `pytest tests/regression` ~10 min. Set `PYTHONUTF8=1` (cp1252 console). `requirements-lock.txt` is the full Windows `pip freeze`, kept for
reference only — do not install it on macOS. The `.venv` is not in git. The committed `.env` holds a Windows
PYTHONPATH; pytest does not need it (`pyproject.toml` sets `pythonpath = ["."]`), and `python -m <module>`
from the repo root works everywhere. PyCharm users: mark the repo root as sources root.
The lab's RFSoC/yoko are never needed for the tests.

**Platform note on the golden.** The golden was captured on Windows originally and regenerated on macOS in
9b8540ba (the original Windows capture is `git show ed66820e:tests/regression/golden_cstq03.json`). The tProc program hashes, cfg dicts and
yoko sequences are platform-independent, but the `data_digest` / `sets` fields hash floats rounded to 9
significant digits, so a different BLAS (Apple Accelerate vs MKL/OpenBLAS) can in rare cases flip a rounding
boundary. If the very first `pytest tests` on the new machine fails ONLY in `data_digest`/`sets` entries
(nothing in `cfg`, `hw`, `methods`, `yoko_writes`), that is a platform artifact, not a code change: BEFORE
moving any code, run `REGRESSION_UPDATE=1 python -m pytest tests/regression` on the untouched legacy tree,
commit the regenerated golden with the message "test(regression): regenerate golden on macOS (BLAS rounding)",
and run the suite twice more to confirm it is stable on that machine. Any diff in `cfg`, `hw` or `methods`
on an untouched tree means the environment is wrong (check `qick==0.2.334`, numpy/scipy versions).

## Environment mismatch policy (added 2026-10-13, session 2 start on macOS)
If the exact pins in `requirements-test.txt` cannot be installed (no wheel for the Mac's Python/arch), do NOT
fight it: install the nearest available versions, but keep `qick==0.2.334` if at all possible (it is pure
Python; install from PyPI or `pip install qick==0.2.334 --no-deps` then the deps separately). Record the
actual versions in `docs/dev/refactor-2026-10/requirements-macos.txt`. Then run the suite on the UNTOUCHED
legacy tree: diffs only in `data_digest`/`sets` → regenerate the golden on the legacy tree (platform note
above) and commit it; diffs in `cfg`/`hw`/`methods` with a different qick version → the harness `__meta__`
check will fail by design; if qick 0.2.334 truly cannot be installed, regenerate the golden on the legacy
tree with the new qick version, commit it with the version in the message, and note that program hashes are
now relative to that version. Either way the golden must be stable (two identical captures) BEFORE phase 3a-i.

## End state: merge back into `bfc_code` (user decision 2026-10-13)
When the whole plan is done and the verification ladder is green, unify the code base: `bfc_code` has not
moved since 0f0a51f, so `git checkout bfc_code && git merge --ff-only qicklab_refactor` keeps history linear
with every atomic commit individually revertable (`git revert <sha>`), then `git push origin bfc_code`. If
`bfc_code` HAS moved in the meantime, rebase `qicklab_refactor` onto it first (resolve conflicts, rerun the
full ladder), then fast-forward. Show the user the commit list and the final test summary before merging. On the final (lab) Windows PC, before
regenerating anything, run the suite once against the ORIGINAL Windows golden (`git show ed66820e:...`) and
classify the diff: everything outside the per-commit allowlists must be explainable, or it is a platform/env
problem to fix first.

## Resuming with Claude Code
Open the repo on the new machine, start Claude Code, and say: "Continue the qicklab refactor — read
docs/dev/refactor-2026-10/HANDOFF.md (TRANSFER STATE first), then design.md; get the suite green on the
clean qicklab_refactor head, then land the parked items from qicklab_refactor_wip one commit at a time per the
landing procedure, using dynamic workflows with Opus agents. Do not re-ask decisions recorded there." The CLAUDE.md banner also points here. Memory from the previous machine is not required;
everything needed is in this directory.
