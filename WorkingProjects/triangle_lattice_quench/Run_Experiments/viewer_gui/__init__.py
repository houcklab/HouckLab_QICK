"""Standalone viewer for archived measurement files.

A historical data browser, not a run-experiments tool: it imports no hardware stack,
so it opens on any machine with PyQt5 + h5py + matplotlib and no ``qick`` installed.
The only code that reaches the experiment classes is ``replot``, imported lazily.

Launch (cwd = ...\\HouckLab_QICK\\WorkingProjects)::

    python -m triangle_lattice_quench.Run_Experiments.viewer_gui

or double-click ``triangle_lattice_quench/launch_viewer_gui.pyw``.
"""
import os

# Set before h5py is imported anywhere in this process. HDF5 1.14 takes a lock when a
# file is opened even read-only, and that makes the *writing* experiment's
# h5py.File(fname, 'a') fail with "unable to lock file" -- i.e. a browse could break a
# live save. Verified locally: reader with locking on -> writer raises; reader with
# locking off -> writer succeeds.
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
