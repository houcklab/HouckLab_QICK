---
title: Home
hide:
  - navigation
  - toc
---

<div class="qk-hero" markdown>

# qicklab

<p class="qk-tagline">Measure superconducting qubits with the Houck Lab RFSoC.</p>

qicklab is the Houck Lab QM-team code for characterising superconducting qubits. You write a short
Python file that says which qubit to measure, at which bias, and which measurements to run, in
order. qicklab turns that into pulse programs for a Xilinx RFSoC running QICK, runs them, then
fits, plots and saves every result together with the exact settings that produced it.

[Get started](getting_started.md){ .md-button .md-button--primary }
[Run a session](running_a_session.md){ .md-button }
[Look up a parameter](parameters.md){ .md-button }

</div>

## Where do you want to start?

Pick the card that matches what you are trying to do. Every page also has search in the top bar
(press ++slash++), and the arrows at the bottom of each page walk you through the docs in reading
order.

<div class="grid cards" markdown>

-   :material-school-outline:{ .lg .middle } **I'm new here**

    ---

    Install the code, run a measurement on a simulated board in about ten minutes, and learn what
    each part of a session file does before you go near the fridge.

    [:octicons-arrow-right-24: Your first session](getting_started.md)

-   :material-play-circle-outline:{ .lg .middle } **I'm taking data today**

    ---

    Edit the session file, choose and order the steps, override a setting for one step, dry-run
    the plan, then run it on the board.

    [:octicons-arrow-right-24: Running a session](running_a_session.md)

-   :material-chip:{ .lg .middle } **I have a new chip or a new cooldown**

    ---

    Go from "find the resonator" to the T1 / T2 / T2E benchmark, and write the device file that
    holds the chip's measured numbers.

    [:octicons-arrow-right-24: Bringing up a new chip](bringup_workflow.md) &middot;
    [Adding a device](adding_a_device.md)

-   :material-flask-outline:{ .lg .middle } **What does this measurement do?**

    ---

    One page per measurement: its pulse sequence, every setting with units and default, what it
    saves, and its known issues.

    [:octicons-arrow-right-24: Experiments](experiments/README.md)

-   :material-tune-variant:{ .lg .middle } **I need a setting's units or default**

    ---

    Every knob of every step, device field and session group, generated from the code so it never
    drifts. It opens with the twenty or so values most sessions change.

    [:octicons-arrow-right-24: Parameters](parameters.md)

-   :material-lifebuoy:{ .lg .middle } **Something went wrong**

    ---

    Error messages and symptoms, what causes them and how to fix them. Search the page for the
    exact text of your error.

    [:octicons-arrow-right-24: Troubleshooting](troubleshooting.md)

-   :material-book-open-variant:{ .lg .middle } **I want to understand the details**

    ---

    The ideas the rest of the docs lean on: the two config regimes, the readout window,
    averaging, timing and units, IQ conventions.

    [:octicons-arrow-right-24: Concepts](concepts/config_regimes.md) &middot;
    [Glossary](glossary.md)

-   :material-code-braces:{ .lg .middle } **I'm changing the code**

    ---

    Package layout and layering rules, the parameter registry, the regression harness that guards
    every pulse program, and the history of the 2026-10 refactor.

    [:octicons-arrow-right-24: Architecture](architecture.md)

</div>

## How the pieces fit together

A measurement passes through five things. You edit the first three; the last two are the
hardware and what it leaves behind.

<div class="qk-flow" markdown>
<div markdown>

**Device file**

`devices/<name>.py`

What the chip *is*: its measured qubit and resonator frequencies, pulse gains, readout windows,
and where its data is saved. One file per sample and cooldown.

</div>
<div markdown>

**Session**

`SESSION = Session(...)`

Today's choices: which qubit to read and drive, the charge-bias voltage, and settings shared by
several measurements.

</div>
<div markdown>

**Plan**

`PLAN = [R.t1(), ...]`

The measurements to run, in order. Each entry is a *step*; any setting can be changed for one
step, as in `R.t1(relax_delay=5000)`.

</div>
<div markdown>

**RFSoC**

`run(SESSION, PLAN)`

qicklab compiles each step into a pulse program, plays it on the board and reads back the
signal. With `dry_run=True` a simulated board stands in, so you can check a plan anywhere.

</div>
<div markdown>

**Data**

`.h5` `.png` `.json`

Every step saves its data, a plot, and the exact settings it ran with, plus a provenance record
of the code version and hardware.

</div>
</div>

The session and the plan live together in one short file per sample,
`runners/<name>_session.py`. That file is the one you edit day to day. You should not need to
change the device file or the `qicklab` package to take data.

## The current cooldown

!!! info "2026-10-29 BFC cooldown (as of 2026-11-04)"

    Two CSTQ03 samples are cold: `CSTQ03_nucell_fab2026_10` (neutrino cell) and
    `CSTQ03_qcage_fab2026_09` (Qcage). Each has its own device file under `devices/` and its own
    session file under `runners/`. The cooldown starts with
    [TWPA calibration](experiments/twpa.md), then the
    [bring-up sequence](bringup_workflow.md). The active research topic is
    [zero-span charge-parity switching](experiments/zero_span_parity.md). Chip notes:
    [CSTQ03](devices/CSTQ03.md).

## Using this site

- **Search** with ++slash++ or ++s++. It matches parameter names exactly (`relax_delay`) and
  finds class names from a fragment (`SingleShot`).
- **Hover a dotted-underlined term** such as TWPA, tProc or FF to see what it means. The full
  list is in the [glossary](glossary.md).
- **Code names with a small arrow** (`qicklab.core.session`) link to that source on GitHub, at
  the right line for a function or class.
- **Copy** any code block with the button in its top-right corner.
- **Move between pages** with ++p++ (previous) and ++n++ (next), or the arrows at the bottom of
  each page.
- **Theme**: the sun/moon icon in the top bar switches light, dark, or your system's setting.

When the code and a page disagree, the code is right and the page needs fixing. The parameter
tables are generated from the code, so those always match it.
