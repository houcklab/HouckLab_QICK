# q3 dual-transition loss test

**Goal:** Test whether a freshly observed q3 loss line appears at the same transition frequency in both g–e and e–f relaxation.

**Scope:** Add one experimental runner and focused tests. Leave the production TLS scan and active-reset code untouched.

1. Calibrate the park e–f pulse with opposed frequency scans, a gain scan, and a 0/π/2π return check. Save raw IQ and stop if the pulse is not resolved.
2. Run one ordinary passive five-point scout, selecting a bidirectional loss line whose e–f matching bias is reachable.
3. Use corrected excursions and read out at the target bias before the 40 µs recovery. At each bias acquire local ground/excited references; require a resolved f reference at the e–f bias before science. Record all IQ, reference checks, frequency mapping, and progress in a NAS manifest.
4. Interleave g–e and e–f offsets, short and long dwells, then reverse the order. Compare excess loss in transition-frequency coordinates. Treat anharmonicity as a park-calibrated prior, and report its uncertainty as a limitation rather than an exact e–f frequency measurement at each target bias.
5. Keep the new runner silent during `--run`, leaving normal SS-cal and five-point output visible. Add pure-function and hardware-mock tests; run the relevant suite, then push the experimental branch and provide the measurement-PC command.
