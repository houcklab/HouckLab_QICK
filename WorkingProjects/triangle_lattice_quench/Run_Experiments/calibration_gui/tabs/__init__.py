"""Per-tab modules for the calibration GUI.

Each module owns one MainWindow tab (plus that tab's private dialogs / workers).
They depend on the package foundation (``state``, ``helpers``, ``widgets``) and,
where there is a real dependency, on sibling tab modules. ``main_window`` imports
the tab classes from here.
"""
