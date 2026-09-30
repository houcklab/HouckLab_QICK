# Initialization record before q4 repeated T1

`initialize.py` is the exact local TLS Spectroscopy initialization source at
commit `34f2815c`, saved before preparing the September 30 q4 overnight run.
Its SHA256 is recorded in `snapshot.json`. The source file is unchanged.
No `initialize.local.py` existed in this local checkout.

`q4_requested_BaseConfig.json` records the user-supplied q4 settings; `FF_CH`
resolves to channel 3 from the current initialization. The dedicated runner
uses these settings without importing or editing initialization. On the
measurement PC it also archives both initialization files if present, before
connecting to the board.

To restore the source if it is edited later, copy this `initialize.py` to
`WorkingProjects/TLS_Spectroscopy/Client_modules/Calib/initialize.py`. A PC-local
override must be restored from that PC's run snapshot as well if it was changed.
