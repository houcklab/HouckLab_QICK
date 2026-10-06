"""Shared support for the retained fast TLS acquisition runners.

Lifted from retired diagnostics without changing calibration, correction,
memory checks, environment restoration, or NAS checkpoint behavior.
Hardware is imported only by the runners on their explicit acquisition path.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np

DATA_ROOT = Path("Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC")
CORRECTION_RELATIVE = Path(
    "q3/q3_2026_09_15/"
    "q3_05_42_07_Qubit_Flux_Step_Response_CLOSED_LOOP_RESIDUAL_075_CANDIDATE.json"
)
CORRECTION_SHA256 = "7f4884732d5a66dcf280119b075a003827206c28f5377199a96dec7542b60b82"


def base_config():
    """Explicit q3 settings; never inherit a measurement-PC q4 override.

    Park pi verified 2026-09-29 (q3_park_pi2_calibration_...223007Z_7464f640).
    Readout/reset calibration is freshly measured, not copied from that run.
    """
    return dict(
        res_ch=0, qubit_ch=1, ff_ch=3, ro_chs=[0], nqz=2, qubit_nqz=2,
        ff_nqz=1, mixer_freq=0., cavity_LO=0, reps=250,
        relax_delay=1000., flux_settle_time_us=.5, ff_ramp_length=4.,
        adc_trig_offset=.5, res_phase=165., read_pulse_style='const',
        read_length=3.5, readout_guard_us=1., readout_thermalization_us=10.,
        read_pulse_gain=1880, read_pulse_freq=6933.026,
        qubit_pulse_style='arb', qubit_freq=4367.292, qubit_pi_freq=4367.292,
        qubit_pi_gain=13500, qubit_pi2_gain=7993, qubit_gain=13500,
        qubit_drag_beta=0., qubit_anharmonicity_mhz=-180.,
        qubit_length=.25, sigma=.2, flat_top_length=None,
        reset_read_delay_us=2., reset_meas_syncdelay_us=10., reset_max_iters=3,
        ff_park_gain=-25146, ff_park_settle_us=1.,
        FF_Qubits={'1': {'channel': 3, 'delay_time': 0.}},
        trig_buffer_start=.02, trig_buffer_end=.02, trig_delay=.082,
        use_switch=False, cavity_winding_freq=0, cavity_winding_offset=0,
        do_ff=False, opx_reference_flux_cycle=False,
        # Same verified timing as FivePointApplesToApples, for BOTH calibration
        # and science. Do not fall back to the legacy 2-us accumulator wait.
        opx_feedback_read_timing='official_wait_all',
        opx_feedback_pre_measure_sync=True, opx_feedback_flush_mode='off',
        opx_read_delay_us=10.,
    )


@contextmanager
def q3_context(tls, data_root):
    keys=('BaseConfig','QUBIT','SET_YOKO','outerFolder','FLUX_FIT_PARAMS',
          'BASELINE_DC_OFFSET','TARGET_DC_OFFSET','FLUX_TAIL_COMPENSATION_GAIN')
    missing=object()
    saved={k:getattr(tls,k,missing) for k in keys}
    tls.BaseConfig=base_config()
    tls.QUBIT, tls.SET_YOKO, tls.outerFolder='q3',False,str(data_root)
    try:
        yield
    finally:
        for k,v in saved.items():
            if v is missing:
                if hasattr(tls,k): delattr(tls,k)
            else: setattr(tls,k,v)


def preflight(program):
    instructions=len(program.compile())
    capacity=int(program.soccfg['tprocs'][0]['pmem_size'])
    if instructions>capacity: raise ValueError('instruction memory exceeded')
    memory=[]
    for ch,pulses in enumerate(program.pulses):
        limit=int(program.soccfg['gens'][ch]['maxlen'])
        used=max((int(p['addr'])+len(p['data']) for p in pulses.values()),default=0)
        if used>limit: raise ValueError('waveform memory exceeded')
        memory.append(dict(channel=ch,used_samples=used,capacity_samples=limit))
    return dict(instructions=instructions,capacity=capacity,waveform_memory=memory,
                record_words=program.record_words)


def _scan_key(key):
    return key.startswith(("Q3_5PT_", "Q3_FLUXPRED_")) or key in {
        "Q3_PROTOCOL_CROSSOVER_PHASE", "Q3_FLUX_TAIL_GAIN", "Q3_CODE_COMMIT",
    }


@contextmanager
def scan_environment(correction):
    """Override prior diagnostic settings for this run, then restore them."""
    previous = {key: value for key, value in os.environ.items() if _scan_key(key)}
    for key in previous:
        os.environ.pop(key)
    try:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[4],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        os.environ.update({
            # Neutral model OFF selects the native correction path, which is ON.
            "Q3_FLUXPRED_MODE": "off",
            "Q3_FLUX_TAIL_GAIN": "1.0",
            "Q3_5PT_CORRECTION_JSON": str(correction),
            "Q3_CODE_COMMIT": commit,
        })
        yield
    finally:
        for key in list(os.environ):
            if _scan_key(key):
                os.environ.pop(key)
        os.environ.update(previous)


def checked_correction(data_root, correction_json=None):
    """Resolve and verify the shared, pinned NAS artifact before hardware imports."""
    data_root = Path(data_root)
    correction = Path(correction_json) if correction_json else data_root / CORRECTION_RELATIVE
    if not correction.is_file():
        raise FileNotFoundError(f"Required correction file unavailable: {correction}")
    if hashlib.sha256(correction.read_bytes()).hexdigest() != CORRECTION_SHA256:
        raise RuntimeError("Correction checksum differs from the September 24 audit.")
    if not data_root.is_dir():
        raise FileNotFoundError(f"NAS data directory unavailable: {data_root}")
    return correction


def _checkpoint(path, payload):
    """Checkpoint silently, including during transient Windows/NAS rename locks."""
    path = Path(path)
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for delay in (.05, .1, .2, .4, .8, 1., 1., None):
        try:
            os.replace(pending, path)
            return
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)


def checkpoint(path, payload):
    def encode(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(f'unsupported metadata type {type(value).__name__}')
    _checkpoint(path, json.loads(json.dumps(payload, default=encode)))
