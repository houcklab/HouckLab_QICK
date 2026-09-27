# QICK 3A/3B measured-trace extractor (opt-in)

`QubitFluxStepResponse(trace_tracking_mode="consensus_v1")` uses the same
vendored `step-trace-v1` package as QUA. The package hash is recorded in
`WorkingProjects/TLS_Spectroscopy/Client_modules/Helpers/step_response/SOURCE_SHA256`.
It saves measured support, source, branch, ambiguity, and quality diagnostics.
An unsuccessful or uncertain trace cannot emit a correction JSON; the raw map
and fit-rejection reason remain available. A 3B residual must be composed with
the exact correction used for acquisition, verified against native DAC-step
and flux-channel metadata.
The expected frequency window, configured polarity, and maximum inter-column
jump are honored. `auto` shoulder mode follows the dominant single ridge;
an explicit lower/upper shoulder request is rejected if no persistent pair
is resolved.

The current `ridge`/`image_template_causal` caller defaults are deliberately
unchanged. The Sept. 18 q3 3B holdout has only 63.4% supported coverage, a
16 µs unsupported gap, and substantial branch ambiguity under this extractor;
it does not meet the candidate gate. The measured-trace candidate method is
recognized by the QICK loader only when the existing production provenance
requirements are satisfied. No pulse sequence, active correction, or timing
was changed.

The offline CLI, notebook, and read-only regression report are in the local
`TLS Counting/Shared Tools/Step Response` folder, outside Git.
