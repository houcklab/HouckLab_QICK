# QICK Active Reset and QUA-Order Acquisition

This package provides the production QICK implementation used by Gate
Calibration, Single-Qubit Coherence, and TLS Spectroscopy. It keeps the flux
output at the configured park throughout each shot, implements feedback reset
on the tProcessor, and preserves QUA-compatible shot and sweep ordering.

The runner surface exposes only the reset-mode choice. Timing, classifier, and
safety defaults are centralized here and a timing-matched calibration is
prepared automatically when active reset is selected.

## Runtime modules

- `production.py` prepares and validates a reset session for a production run.
- `integration.py` connects production experiments to the reset and acquisition
  programs.
- `programs.py` defines the tProcessor pulse and feedback programs.
- `qua_order.py` implements shot-first controller-resident sweeps and progress.
- `acquisition.py` manages streamed records, watchdogs, and fail-closed cleanup.
- `calibration.py` and `classifier.py` build the timing-matched readout
  classifier.
- `control_flow.py` emits the feedback state machine.
- `records.py` defines the streamed record layout.
- `analysis.py` contains shared analysis and serialization helpers.
- `config.py` and `benchmark_settings.py` hold centralized defaults.

The hardware-side resident readout support is in
`WorkingProjects/TLS_Spectroscopy/pynq/readout_batch.py` and is installed by
`WorkingProjects/TLS_Spectroscopy/pynq/qick_server.py` when the RFSoC Pyro
server starts.

`tests/` contains the permanent hardware-independent regression suite. One-off
q3 smoke runners, diagnostics, equivalence studies, and timing probes are not
part of the tracked production package.
