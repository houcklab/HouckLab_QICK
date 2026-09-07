import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitLongTimeSpecVsFlux import QubitLongTimeSpecVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner


def acquire(soc, soccfg, suffix, resonator_fit_parameters):
    p = {
        "shots": 100,
        "relax_delay_us": 100.0,
        "spec_amp": 15000,
        "spec_len_us": 1.0,
    }
    frequencies = np.arange(4200.0, 4400.0, 1.0)
    dc_gains = np.arange(-26000.0, -19999.0, 1000.0)
    cfg = runner._spec_cfg(p, extra={
        "qubit_freq_start": float(frequencies[0]),
        "qubit_freq_stop": 4400.0,
        "qubit_freq_step": 1.0,
        "qubit_freq_expts": int(frequencies.size),
        "qua_order_max_records_per_block": 262144,
    })
    if resonator_fit_parameters is None:
        cfg.pop("resonator_fit_parameters", None)
    else:
        cfg["resonator_fit_parameters"] = list(resonator_fit_parameters)
    experiment = QubitLongTimeSpecVsFlux(
        soc=soc,
        soccfg=soccfg,
        path=runner.QUBIT,
        outerFolder=runner.outerFolder,
        suffix=suffix,
        cfg=cfg,
        step_tag="2",
        dc_vec=dc_gains,
        long_time_ns=2000.0,
        average_window_ns=0.0,
        readout_after_park=False,
        park_voltage=runner.BASELINE_DC_OFFSET,
        advanced_fit=False,
        live_plot=True,
        resonator_lookup_csv=None,
    )
    experiment.acquire(progress=True)


def main():
    soc, soccfg = runner.makeProxy()
    acquire(soc, soccfg, "P2_AB_Flat_Readout", None)
    acquire(soc, soccfg, "P2_AB_Tracked_Readout", runner.RESONATOR_FIT_PARAMS)


if __name__ == "__main__":
    main()
