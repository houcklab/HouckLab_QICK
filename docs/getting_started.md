# Your first session

This page takes you from nothing installed to a measurement running on the fridge, one step at a
time. You do not need to know QICK or the RFSoC already. Each step says what it does, why, and
what you should see when it works.

Steps 1 to 5 work on any computer and touch no hardware; allow about half an hour. Step 6 needs
the lab network and the fridge.

!!! info "What you need"

    - **Python 3.11 or newer**, and **git**. The lab PCs have both.
    - **For steps 1 to 5:** any Windows, macOS or Linux computer. Everything runs against a
      simulated board.
    - **For step 6:** a lab PC on the lab network, which reaches the RFSoC at `192.168.0.103` and
      the data drive `V:`, and the go-ahead from whoever is running the fridge.

## 1. The big picture

A superconducting qubit is controlled and read out with microwave pulses. In this lab those
pulses are generated, and the signal coming back from the chip is digitised, by a Xilinx
**RFSoC** board. The board runs **QICK**, open-source firmware with a Python library. QICK
programs run on the board's timed processor, the **tProc**, which plays each pulse at an exact
clock cycle.

qicklab is the layer on top of QICK. You describe *what* to measure; qicklab writes the tProc
programs, runs them, fits the results, draws the plots and saves everything. You work with four
things, listed from the one you change least to the one you change most:

| Thing | Where it lives | What it holds | When you edit it |
|---|---|---|---|
| **Device** | `devices/<name>.py` | One physical sample's measured numbers: qubit and resonator frequencies, pulse gains and lengths, readout windows, and where its data is saved | When a calibration changes |
| **Session** | the top of `runners/<name>_session.py` | Today's choices: which qubit to read and which to drive, the charge-bias voltage, and settings shared by several measurements | At the start of a sitting |
| **Step** | a recipe call such as `R.t1()` | One measurement and its settings. Any setting can be overridden for that one step: `R.t1(relax_delay=5000)` | Often |
| **Plan** | `PLAN = [...]` in the same runner file | The ordered list of steps that `run()` executes | Often |

Each step saves three files: an `.h5` file with the data and the exact settings, a `.png` plot,
and a `.json` copy of the settings that you can read in any text editor.

!!! tip "Names you will see"

    Each step has a short snake_case name (`t1`, `single_shot`, `amplitude_rabi`), which is
    also the name of its recipe (`R.t1()`). Underneath, each step uses one or more *experiment
    classes* with older names such as `T1FF` or `SingleShotProgramFFMUX`. The `FF` and `MUX` in
    those names are historical and do not mean the experiment uses fast flux or multiplexing.
    Hover over a dotted-underlined term on this site for its meaning, or see the
    [glossary](glossary.md).

## 2. Set up your computer

You will download the code, create a private Python environment for it, and install the exact
library versions it needs. Choose your system:

=== "Windows (PowerShell)"

    ```powershell
    git clone -b bfc_code https://github.com/houcklab/HouckLab_QICK.git
    cd HouckLab_QICK
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r docs/dev/refactor-2026-10/requirements-test.txt
    ```

=== "macOS / Linux"

    ```bash
    git clone -b bfc_code https://github.com/houcklab/HouckLab_QICK.git
    cd HouckLab_QICK
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r docs/dev/refactor-2026-10/requirements-test.txt
    ```

What each line does:

1. **`git clone -b bfc_code ...`** downloads the repository and checks out `bfc_code`, the branch
   where lab work happens. The `main` branch holds the lab's older code; nothing in these docs
   applies to it.
2. **`cd HouckLab_QICK`** moves into it. Run everything from this folder, the *repo root*: the
   code imports `devices` and `runners` as top-level packages, so they must be on the path.
3. **`python -m venv .venv`** creates a private Python environment in the `.venv` folder, so
   this project's library versions cannot clash with anything else on the computer.
4. **Activating** the environment makes `python` and `pip` in this window use it. Your prompt now
   starts with `(.venv)`. Activate it again in every new terminal window.
5. **`pip install -r ...`** installs pinned versions of everything the code needs. The important
   one is `qick==0.2.334`: the QICK library on your computer must match the firmware on the
   board, so never upgrade it on its own.

Already have the repository, for example on a lab PC? Then go to it, update it and activate the
existing environment instead:

```powershell
cd HouckLab_QICK
git switch bfc_code
git pull
.venv\Scripts\Activate.ps1
```

!!! tip "PowerShell says running scripts is disabled on this system"

    Windows blocks the activation script by default. Allow scripts you run yourself, once:
    `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again. Or use the
    Command Prompt (cmd) instead, where the line is `.venv\Scripts\activate.bat`.

!!! tip "A `UnicodeEncodeError`, or garbled symbols, in a Windows console"

    Some messages contain characters such as μ or →. Tell Python to use UTF-8 in that window
    before running anything: `$env:PYTHONUTF8 = "1"` in PowerShell, `set PYTHONUTF8=1` in cmd.

!!! tip "Using PyCharm"

    Open the repo root as the project, choose `.venv` as the interpreter (Settings → Python
    Interpreter → Add → Existing), and mark the repo root as a *Sources Root* (right-click the
    folder → Mark Directory as). Ctrl+Q on any recipe, for example on `R.t1`, then shows every
    setting with its default and units.

## 3. Check the installation

The test suite proves that your copy behaves exactly like the lab's. Two quick test files are
enough to show that everything imports:

```
python -m pytest tests/test_imports.py tests/test_layering.py
```

After a few seconds you should see:

```text
........                                                                 [100%]
8 passed in 8.34s
```

If instead you get `ModuleNotFoundError: No module named 'qick'`, the environment is not active
(no `(.venv)` at the start of the prompt): activate it and try again. If you get
`No module named 'devices'`, you are not in the repo root.

The full suite (`python -m pytest tests`) takes about 14 minutes and replays every pulse program
the lab's code produces. You do not need it to take data; it matters when you change the code.

## 4. Your first dry run

A **dry run** executes a plan against a simulated board. Every pulse program is compiled exactly
as it would be for the real board, but nothing plays and nothing is kept. It catches typos,
missing settings, timing mistakes (two pulses that overlap, a wait shorter than its pulses) and
memory limits before you are at the fridge. It says nothing about physics: the simulated board
returns synthetic data.

Start Python from the repo root (type `python`), and paste:

```python
from runners.CSTQ03_nucell_fab2026_10_session import SESSION  # (1)!
from qicklab.core.session import run  # (2)!
from qicklab.runs import recipes as R  # (3)!
run(SESSION, [R.amplitude_rabi(), R.single_shot()], dry_run=True)  # (4)!
```

1.  The session of one of the two samples in the fridge, the CSTQ03 chip in the neutrino cell. It
    names the device file, the qubit (Q1) and the bias (0 V). Importing it is safe: nothing
    connects to any hardware until `run()` is called.
2.  `run()` executes a plan: it connects, checks the device file against the board, then runs the
    steps in order and prints what each one does.
3.  `R` is the catalogue of recipes, one per measurement: `R.t1`, `R.t2_echo`,
    `R.single_shot`, ... [Experiments](experiments/README.md) has a page for each.
4.  A two-step plan. *Amplitude Rabi* sweeps the drive strength to find the gain of a π pulse,
    the pulse that takes the qubit from ground to excited. *Single shot* then reads the qubit many
    times, with and without that pulse, to see how well the two states can be told apart.
    `dry_run=True` swaps in the simulated board.

After a few seconds you should see something like this (shortened):

```text
[session] DRY RUN (fake board, nothing is kept): CSTQ03_nucell_fab2026_10 (2026-10-29), readout Q1, pulse Q1, bias 0.0 V, 2 step(s): amplitude_rabi, single_shot
[charge yoko] GPIB1::9::INSTR: function VOLT, output OFF, setpoint 0.0
[readout window] integration 15.0 us, adc_trig_offset 0.3 us, resonator tone 15.3 us

[session] dry run 1/2: amplitude_rabi (regime A)
    Amplitude_Rabi_params = {'qubit_freq': 2993,
                             'max_gain': 10000,
                             'number_of_steps': 101,
                             ...}
Saving C:/.../qicklab_dryrun_.../Q1//AmplitudeRabi\AmplitudeRabi_2026_11_04\AmplitudeRabi_2026_11_04_20_23_30_data.h5
[session] regime A -> B: single-shot config rebuilt from BaseConfig (carry-overs pulse_freq / res_phase dropped) with the session single_shot group

[session] dry run 2/2: single_shot (regime B)
    ...
[session] dry run report:
     1. amplitude_rabi                         1 experiment(s)    1 program(s)  ok
        built: AmplitudeRabiFF/AmplitudeRabi x1
     2. single_shot                            1 experiment(s)    2 program(s)  ok
        built: SingleShotProgramFFMUX/SingleShot x1
```

How to read it:

- **The first lines** say what is about to run: which sample, which qubits, which bias, which
  steps. On the real board, the yoko line is the charge-bias source being set.
- **Before each step** come its *effective* parameters: every setting after the library default,
  the session and your overrides have been combined. This is exactly what will run. On the fridge,
  copy it into your lab notebook.
- **`regime A -> B`** means qicklab switched from the measurement configuration to the
  single-shot configuration, because single shot needs different readout settings. It happens
  automatically. Why there are two, and what is not carried across, is explained in
  [config regimes](concepts/config_regimes.md); you can leave that for later.
- **The report** at the end lists each step. `ok` means every pulse program compiled. `INCOMPLETE`
  means the dry run stopped a long step early on purpose (see below); that is not a failure. A
  step that fails prints its error, and the run ends with a `RuntimeError` naming it.

!!! note "Warnings you can ignore in a dry run"

    Because the data is synthetic, physics warnings such as `analog SNR 0.04 < 1` or
    `readout contrast 0.031 < 0.3` mean nothing here. You will also see `UserWarning: ... is in
    Nyquist zone 2 with nqz 1` for Q2 and Q4. That one is a real check of the device file against
    the board (`Device.validate`), but it concerns other qubits than the one this session uses.
    Soft problems like this warn; real errors stop the run.

The files it "saved" went to a temporary folder that is deleted afterwards.

## 5. Read the session file

Now open the file you just imported, `runners/CSTQ03_nucell_fab2026_10_session.py`. It is the
file you edit to take data. It has three blocks.

**1. `SESSION`: today's choices.**

```python
SESSION = Session(
    DEVICE,
    qubit_readout=1,  # whose resonator is read out; also picks the data folder Q1
    qubit_pulse=1,  # whose drive settings are used
    bias_v=0.000,  # [V] charge-bias voltage, set once when the session connects
    yoko_fixed=False,
    # shared settings: every coherence step (t1, t2_ramsey, ...) reads this one group
    coherence=G.coherence(repetitions=1000),
    echo=G.echo(repetitions=3000),
)
```

`qubit_readout` and `qubit_pulse` are usually the same qubit. The *groups* (`coherence`, `echo`,
`spec`, `single_shot`, ...) hold settings that several steps share, so that changing one value
changes all of them together.

**2. `STEP`: every measurement, configured for this cooldown.** A dictionary with one entry per
measurement, holding the lab's current settings: `STEP["t1"]`, `STEP["two_tone_spec"]`, and so
on. Read it to see how each measurement is set up, but you rarely need to edit it.

**3. `PLAN`: what actually runs.** An ordered list of steps. To run something, list it here, by
uncommenting a line or adding one:

```python
PLAN = [
    STEP["transmission_fit"],  # a step as configured in STEP
    STEP["t1"],
    R.t1(relax_delay=5000),  # the same measurement, one setting changed
]
```

Steps run in the order written, and the same step can appear more than once.

Each setting is decided in this order, and the last one given wins:

```
library recipe default  <  session group  <  keyword on the step
```

So `coherence=G.coherence(relax_delay=3000)` on the session changes the relax delay of every
coherence step, while `R.t1(relax_delay=5000)` changes it for that one step only.

!!! tip "Finding a setting"

    Every keyword of a step is listed, with its units, default and meaning, in the table at the
    top of that step's page (for example [t1](experiments/t1.md)), and all of them are in
    [Parameters](parameters.md). In Python, `help(R.t1)` prints the same. A misspelled keyword
    is an error straight away (`TypeError: t1() got an unexpected keyword argument`), so a typo
    can never be silently ignored.

Dry-run the runner file itself before every real run:

```
python -m runners.CSTQ03_nucell_fab2026_10_session --dry-run
```

!!! warning "Long steps stop early in a dry run"

    A step that repeats many times, such as `t1` with 1000 repetitions, stops at the dry-run guard
    after about 40 repeats and is reported `INCOMPLETE`: the programs it did compile were fine, the rest
    were not checked. Some steps are slow even in a dry run; the committed `STEP["undriven_single_shot"]`
    (a million shots per pass) can take many minutes. To check a plan quickly, dry-run a short
    version, for example `R.undriven_single_shot(shots=10_000, repeat=2)`. Details:
    [Dry run](running_a_session.md#dry-run).

## 6. Run on the fridge

!!! warning "Before you run on hardware"

    - **Agree it with whoever is running the fridge.** A run drives real hardware: the RFSoC plays
      microwave pulses into the fridge, and the charge-bias yoko is ramped to `bias_v` as soon as
      the session connects.
    - **Check the order of work for this cooldown.** The 2026-10-29 cooldown starts with
      [TWPA calibration](experiments/twpa.md), which uses its own scripts rather than a session.
    - **Check the device file.** At the start of a cooldown its numbers are carried over from the
      previous one until they are measured again. The [bring-up workflow](bringup_workflow.md) is
      the order in which to re-measure them.
    - **Dry-run the exact plan you are about to run** (step 5).

On a lab PC, from the repo root with the environment active:

```
python -m runners.CSTQ03_nucell_fab2026_10_session
```

For the other sample, use `python -m runners.CSTQ03_qcage_fab2026_09_session`.

What happens: qicklab connects to the RFSoC over the network (with Pyro4), opens the charge-bias
yoko and ramps it to `bias_v`, and checks the device file against the board. Then it runs each
step in order, printing its effective parameters first, as in the dry run, and saving its files
as it finishes.

To **stop**, press ++ctrl+c++. The files of steps that already finished are kept, and the yoko
connection is closed. Closing does not ramp the bias down: the voltage stays where the last step
left it.

!!! danger "If you had to kill Python outright"

    The continuous-tone steps (`constant_tone`, `constant_two_tone`) leave a tone playing if the
    process is killed hard (closing the window, ending the task) instead of stopped with
    ++ctrl+c++. Reconnect and call `soc.reset_gens()` to silence it; see
    [continuous tones](experiments/cw_tones.md#stray-tone-hazard).

To run steps one at a time from a Python console instead, connecting once and keeping the
connection, see [from a console](running_a_session.md#from-a-console-repl).

## 7. Find your data

Each step writes to a folder under the device's data root, which is set in its device file. For
this cooldown that is
`V:/t1Team/Data/2026-10-29_BFC_cooldown/<sample>/RFSOC`. Below it, the layout is:

```
<data root>/Q<qubit>//<path>/<path>_<date>/<path>_<date and time>_data.h5
                                           <path>_<date and time>_data.png
                                           <path>_<date and time>_data.json
                                           <path>_<date and time>_data_provenance.json
```

`Q<qubit>` is the session's `qubit_readout`, and `<path>` is the measurement's folder name (`T1`,
`SingleShot`, `TransmissionFF`, ...; each experiment page lists its own). The mix of `/`, `//`
and `\` in real paths is intentional and Windows handles it fine.

- The **`.png`** is the quickest look at a result.
- The **`.json`** holds every setting the measurement ran with; open it in any text editor.
- The **`.h5`** holds the data and the same settings. To load it in Python:

    ```python
    import json

    import h5py

    with h5py.File("path/to/..._data.h5", "r") as f:
        cfg = json.loads(f.attrs["config"])  # the exact settings it ran with
        data = {k: f[k][()] for k in f.keys()}  # every saved array
    ```

    More, including how to find the newest file of a measurement: [reading data
    offline](running_a_session.md#reading-data-offline).

- The **`_provenance.json`** records the code version, board, qubits and bias, so a result can
  always be traced back to what produced it.

When a measurement gives a new value for the chip (a resonator frequency, a π-pulse gain), it
goes into the device file by hand. Some steps print a ready-to-paste line for it; see
[calibration write-back](adding_a_device.md#calibration-write-back).

## 8. Where to go next

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **Read the concepts once**

    ---

    Short pages on the ideas everything else assumes: config regimes, the readout window,
    averaging, timing and units, IQ conventions. The [reading path](README.md) gives the order.

    [:octicons-arrow-right-24: Config regimes](concepts/config_regimes.md)

-   :material-chip:{ .lg .middle } **Bring up a chip**

    ---

    The order of measurements for a new sample, from finding the resonator to the coherence
    benchmark, with the settings to start from.

    [:octicons-arrow-right-24: Bringing up a new chip](bringup_workflow.md)

-   :material-flask-outline:{ .lg .middle } **Look up a measurement**

    ---

    What each step does, its pulse sequence, every setting, and what it saves.

    [:octicons-arrow-right-24: Experiments](experiments/README.md)

-   :material-lifebuoy:{ .lg .middle } **When something breaks**

    ---

    Search for the exact error text; most errors are listed with their cause and fix.

    [:octicons-arrow-right-24: Troubleshooting](troubleshooting.md)

</div>

## Browse the docs as a website

These pages are plain Markdown files in the `docs/` folder, so they read fine on GitHub or in
PyCharm. They also build into this website, with search, light and dark themes, and hover
definitions. To build it yourself, with the environment active:

```
pip install -r requirements-docs.txt
mkdocs serve
```

Then open <http://127.0.0.1:8765> in a browser. While `mkdocs serve` runs, the page reloads every
time you save a Markdown file, which makes it the easiest way to edit the docs. Stop it with
++ctrl+c++.

`mkdocs build` writes the whole site to the `site/` folder instead. Open `site/index.html`
straight from disk, with no server; search still works, so the folder can be copied anywhere,
for example to a shared drive. A new page has to be added to the `nav` list in `mkdocs.yml` to
appear on the site.
