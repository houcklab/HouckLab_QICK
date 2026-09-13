# Controller-neutral flux inverse

Scope: new offline/dedicated paths only, QICK da387a3 and QUA 422b6c9. Preserve main checkout dirty work, measured files, and all legacy paths. No hardware execution or shared-branch pushes.

## Model and fairness

Use a parallel stable high-pass state-space inverse, not a free multiplier table:

`g_j(r)=r*c_j(r); dz_j/dt=(g_j(r)-z_j)/tau_j; u=r+sum_j(g_j(r)-z_j)`.

For LTI, c is constant. For the amplitude-conditioned extension, c is piecewise linear in desired normalized amplitude, with endpoint-constant interpolation toward zero, no extrapolation beyond calibrated nonzero range, and g(0)=0. Histories superpose as differences of the same potential g on every transition; coefficients are never selected independently on return edges. Stable fixed poles have tau >= twice the measurement spacing. Coefficient L1 bounds limit transient amplification. DC gain is exactly one. Use exact state updates and interval-mean commands on a 2-us emission grid (refined from the initial 4-us choice solely to reduce numerical hold approximation), with additional edges only for explicitly requested target transitions. Fine hardware timing is an emission approximation, not evidence of sub-resolution plant dynamics.

Identify a forward plant in the same fixed stable basis from known input commands and voltage-domain measured responses. Account for the probe's truncated/frozen command. Fit an additive DC nuisance per trace; report that this deliberately studies flatness rather than absolute frequency accuracy. Fit inverse coefficients by regularized linear least squares against the identified plant's response. Compare shared LTI against amplitude-conditioned models, leave one amplitude out, blocked time validation, and the later three-amplitude piecewise validation set. Report train errors, held-out errors, pole/coefficient bounds, extraction sensitivity, and missing history evidence separately.

## Evidence limits

Saved smooth traces already use 17-point Savitzky–Golay filtering; the multi-amplitude builder applies another 7-point filter. Raw centroids, grid ridges, support masks, and repeat differences must be audited. No independent shot noise estimates are available in averaged maps. Spectral linewidth is not a frequency confidence interval. A 4-us sampling grid cannot resolve alternating 2-us correction segments or validate a sub-us pole. Amplitude dependence, static calibration error, ridge bias, and incomplete park recovery are confounded in these scans; disagreement rejects the particular shared model, not all possible LTI models.

## Emission and lifecycle

A versioned JSON model and byte-identical Python core generate normalized commands in both repositories. Backend modules only convert time/amplitude and emit native instructions. Quantize cumulative boundaries, reject clipping and undersized durations, bound program size, and compare reconstructed commands on their union of edges (RMS/max/integrated timing error). No OPX output filters.

Each dedicated shot starts after active reset at park. A finite recovery interval is chosen from an explicit state-tail bound; a shot cannot silently drop history. Precompute variable-hold schedules, keep drive/readout timing independent of the queued flux horizon, and require real compiler/timing verification on the measurement PC before acquisition. Raw/legacy piecewise remain explicitly selectable fallback modes. The new model is an experimental candidate until all scientific and emission gates pass.

## Acceptance

Deterministic tests before implementation; exact synthetic plant/inverse, causality, round-trip, chunk continuity, interpolation, schema rejection, clipping, timing, instruction limits, active reset, and variable holds. Offline acceptance requires supported smooth RMS <0.25 MHz and absolute early(<=21us)-late(>=300us) <0.5 MHz at each q5 amplitude, with repeat/estimator noise reported. Evidence and metadata gate real use; lack of hardware verification cannot be labeled a pass. q3 has only one amplitude and cannot establish cross-amplitude transfer. Prepare software runners and commands only after offline software checks pass; scientific failures must block measurement-ready status.
