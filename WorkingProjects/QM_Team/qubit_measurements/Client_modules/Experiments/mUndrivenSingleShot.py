"""Single-shot readout with NO qubit drive at all.

Same resonator/readout probing scheme as `mSingleShotProgramFFMUX.SingleShotProgram`
(same const tone on `res_ch`, same `declare_readout` window, same
`adc_trig_offset` -> tone-length coupling, same per-shot `acc_buf` extraction and
length normalization), with every qubit-side element removed: the qubit generator
is never declared, no Gaussian envelope is added, no marker trigger fires, and
`body()` contains nothing but the measurement. The DAC on `qubit_ch` is therefore
idle for the whole program.

Use it to look at the raw IQ cloud the readout produces on an undriven qubit:
whether it is one blob or two, how wide it is, and what fraction of shots sit in
the secondary blob (residual/thermal excited population, or a parity/charge
split). Nothing here calibrates a threshold against a known |e> reference, so no
readout fidelity is reported — a fidelity number is meaningless without a
deliberately prepared excited state (use SingleShotProgramFFMUX for that).

Analysis is deliberately assumption-light: the cloud is projected onto its own
principal axis and a 1-component Gaussian fit is compared against a 2-component
one by BIC. Two blobs are only claimed when the 2-component model actually wins
and the two centers are separated by more than `min_separation_sigma` combined
widths, so shot noise on a single blob does not get reported as structure.
"""

import matplotlib.pyplot as plt
import numpy as np
from qick import *

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.shot_buffers import raw_shot_buffers

import time


class UndrivenSingleShotProgram(AveragerProgram):
    """Readout-only single-shot program: probe the resonator, never touch the qubit."""

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = cfg["shots"]
        # acc_buf is overwritten every round, so per-shot data only survives with
        # a single round (see Helpers/shot_buffers).
        cfg["rounds"] = 1

        if cfg["readout_length"] <= 0:
            raise ValueError("cfg['readout_length'] must be positive")
        if not cfg["ro_chs"]:
            raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
        for delay_key in ("adc_trig_offset", "relax_delay"):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])  # convert f_res to dac register value

        # Identical readout-window arithmetic to SingleShotProgram, so the blobs
        # seen here integrate the same physical ADC window and are directly
        # comparable with the driven single-shot clouds. The resonator tone starts
        # at t=0 while ADC integration starts adc_trig_offset later, so the tone
        # must cover offset + window; each duration is converted on its owning
        # hardware clock and the tone is then extended by the minimum number of
        # generator cycles needed after cross-clock rounding.
        required_tone_us = cfg["adc_trig_offset"] + cfg["readout_length"]
        cfg.setdefault("length", required_tone_us)
        if cfg["length"] < required_tone_us:
            raise ValueError(
                "cfg['length'] must cover cfg['adc_trig_offset'] + "
                f"cfg['readout_length'] ({cfg['length']} us < "
                f"{required_tone_us} us)"
            )

        self.adc_trig_offset_cycles = self.us2cycles(cfg["adc_trig_offset"])
        requested_tone_cycles = self.us2cycles(cfg["length"], gen_ch=cfg["res_ch"])
        self.readout_window_cycles = {
            ch: self.us2cycles(cfg["readout_length"], ro_ch=ch)
            for ch in cfg["ro_chs"]
        }

        f_time = self.soccfg["tprocs"][0]["f_time"]
        res_f_fabric = self.soccfg["gens"][cfg["res_ch"]]["f_fabric"]
        adc_end_tproc = max(
            self.adc_trig_offset_cycles
            + self.readout_window_cycles[ch]
            * f_time / self.soccfg["readouts"][ch]["f_output"]
            for ch in cfg["ro_chs"]
        )
        required_tone_cycles = int(np.ceil(
            adc_end_tproc * res_f_fabric / f_time - 1e-12
        ))
        self.readout_tone_cycles = max(requested_tone_cycles, required_tone_cycles)
        self.readout_tone_extension_cycles = (
            self.readout_tone_cycles - requested_tone_cycles
        )

        for ch in cfg["ro_chs"]:  # readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.readout_window_cycles[ch],
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res,
                                 phase=cfg["res_phase"], gain=cfg["pulse_gain"],
                                 length=self.readout_tone_cycles)

        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        # No qubit pulse, no marker trigger: the only thing that happens in a
        # shot is the resonator probe.
        self.sync_all()
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.adc_trig_offset_cycles,
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True,
                readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):
        start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        end = time.time()

        print('time', end - start)
        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []
        # di_buf/dq_buf are averaged over reps from qick ~0.2.29x on; pull the
        # raw per-shot stream out of acc_buf instead (see Helpers/shot_buffers).
        di_buf, dq_buf = raw_shot_buffers(self)
        for i in range(len(di_buf)):
            ro_ch = self.cfg["ro_chs"][i]
            norm = self.us2cycles(self.cfg['readout_length'], ro_ch=ro_ch)
            all_i.append(di_buf[i].reshape((1, self.cfg["reps"])) / norm)
            all_q.append(dq_buf[i].reshape((1, self.cfg["reps"])) / norm)
        return all_i, all_q


def analyze_undriven_cloud(i_shots, q_shots, min_separation_sigma=2.0,
                           random_state=0):
    """Describe one undriven IQ cloud: center, width, principal axis, blob count.

    The cloud is projected onto the principal axis of its own covariance (the
    direction along which any second blob must lie), then a 1- vs 2-component
    Gaussian mixture fit on that 1-D projection is compared by BIC. `n_blobs` is
    2 only if the 2-component model has the lower BIC AND the centers are farther
    apart than `min_separation_sigma` * (sigma_0 + sigma_1) / 2, so that noise on
    a single blob is not reported as a second state.

    Returns a dict of plain floats/arrays (h5-writable). `n_blobs` is 0 when the
    fit could not be performed at all.
    """
    iq = np.column_stack([np.asarray(i_shots, dtype=float).ravel(),
                          np.asarray(q_shots, dtype=float).ravel()])
    n_shots = len(iq)

    out = {
        "n_shots": n_shots,
        "center": np.array([np.nan, np.nan]),
        "cov": np.full((2, 2), np.nan),
        "axis": np.array([np.nan, np.nan]),
        "axis_angle": np.nan,
        "projection": np.full(n_shots, np.nan),
        "n_blobs": 0,
        "blob_weights": np.array([np.nan, np.nan]),
        "blob_means_proj": np.array([np.nan, np.nan]),
        "blob_sigmas_proj": np.array([np.nan, np.nan]),
        "blob_centers_iq": np.full((2, 2), np.nan),
        "separation_sigma": np.nan,
        "secondary_population": np.nan,
        "bic_1": np.nan,
        "bic_2": np.nan,
        "labels": np.zeros(n_shots, dtype=int),
        "rms_radius": np.nan,
        "sigma_along_axis": np.nan,
        "sigma_across_axis": np.nan,
        "axis_minor": np.array([np.nan, np.nan]),
    }
    if n_shots < 2:
        return out

    center = np.median(iq, axis=0)
    cov = np.cov(iq, rowvar=False)
    out["center"] = center
    out["cov"] = cov

    # Principal axis = eigenvector of the largest eigenvalue.
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    axis = eigvecs[:, 0]
    if axis[0] < 0:  # fix the sign so repeated runs project the same way
        axis = -axis
    across = eigvecs[:, 1]

    diff = iq - center
    proj = diff @ axis
    out["axis"] = axis
    out["axis_minor"] = across
    out["axis_angle"] = float(np.arctan2(axis[1], axis[0]))
    out["projection"] = proj
    out["rms_radius"] = float(np.sqrt(np.mean(np.sum(diff ** 2, axis=1))))
    out["sigma_along_axis"] = float(np.sqrt(max(eigvals[0], 0.0)))
    out["sigma_across_axis"] = float(np.sqrt(max(eigvals[1], 0.0)))

    if np.std(proj) <= 0:
        # Every shot landed on the same value (saturated/disconnected readout).
        # A mixture fit here only produces a degenerate-covariance warning.
        print("[UndrivenSingleShot] zero spread in the IQ cloud - check that the "
              "readout tone is actually reaching the ADC.")
        out["n_blobs"] = 1
        out["blob_weights"] = np.array([1.0, 0.0])
        out["blob_means_proj"] = np.array([0.0, np.nan])
        out["blob_sigmas_proj"] = np.array([0.0, np.nan])
        out["blob_centers_iq"] = np.array([center, [np.nan, np.nan]])
        out["secondary_population"] = 0.0
        out["separation_sigma"] = 0.0
        return out

    try:
        from sklearn.mixture import GaussianMixture

        x = proj.reshape(-1, 1)
        gm1 = GaussianMixture(n_components=1, random_state=random_state).fit(x)
        gm2 = GaussianMixture(n_components=2, random_state=random_state,
                              n_init=5).fit(x)
        bic1 = float(gm1.bic(x))
        bic2 = float(gm2.bic(x))
        out["bic_1"] = bic1
        out["bic_2"] = bic2

        means2 = gm2.means_.ravel()
        sigmas2 = np.sqrt(gm2.covariances_.ravel())
        weights2 = gm2.weights_.ravel()
        # order by projection so component 0 is always the same side
        order2 = np.argsort(means2)
        means2, sigmas2, weights2 = means2[order2], sigmas2[order2], weights2[order2]

        mean_sigma = float(np.mean(sigmas2))
        separation = float(abs(means2[1] - means2[0]))
        separation_sigma = separation / mean_sigma if mean_sigma > 0 else np.inf
        out["separation_sigma"] = separation_sigma

        two_blobs = (bic2 < bic1) and (separation_sigma >= min_separation_sigma)

        if two_blobs:
            labels2 = gm2.predict(x)
            # remap predict()'s component ids onto the sorted ordering
            remap = np.empty(2, dtype=int)
            remap[order2] = np.arange(2)
            labels = remap[labels2]
            # the minority component is the "secondary" blob
            minor = int(np.argmin(weights2))
            out["n_blobs"] = 2
            out["blob_weights"] = weights2
            out["blob_means_proj"] = means2
            out["blob_sigmas_proj"] = sigmas2
            out["blob_centers_iq"] = np.array([center + m * axis for m in means2])
            out["secondary_population"] = float(weights2[minor])
            out["labels"] = labels
        else:
            mean1 = float(gm1.means_.ravel()[0])
            sigma1 = float(np.sqrt(gm1.covariances_.ravel()[0]))
            out["n_blobs"] = 1
            out["blob_weights"] = np.array([1.0, 0.0])
            out["blob_means_proj"] = np.array([mean1, np.nan])
            out["blob_sigmas_proj"] = np.array([sigma1, np.nan])
            out["blob_centers_iq"] = np.array([center + mean1 * axis,
                                               [np.nan, np.nan]])
            out["secondary_population"] = 0.0
            out["labels"] = np.zeros(n_shots, dtype=int)

    except Exception as err:
        print(f"[UndrivenSingleShot] blob fit failed ({err}); "
              f"reporting cloud statistics only.")

    return out


class UndrivenSingleShot(ExperimentClass):
    """Acquire and display the single-shot IQ cloud with the qubit drive off.

    cfg keys used (all shared with SingleShotProgramFFMUX so the same
    single-shot-regime config works unchanged): res_ch, nqz, ro_chs, pulse_freq,
    pulse_gain, res_phase, readout_length, adc_trig_offset, relax_delay, shots,
    optional length, optional Read_Indeces. Optional analysis knob:
    `blob_min_separation_sigma` (default 2.0).

    No qubit key (f_ge, qubit_ch, qubit_gain, sigma, number_of_pulses, ...) is
    read or required.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, cfg=cfg, config_file=config_file,
                         progress=progress)

    def _read_indices(self, n_reads):
        read_indices = self.cfg.get("Read_Indeces", None)
        if read_indices is None:
            read_indices = list(range(n_reads))
        elif isinstance(read_indices, (int, np.integer)):
            read_indices = [int(read_indices)]
        else:
            read_indices = list(read_indices)
        read_indices = read_indices[:n_reads]
        if not read_indices:
            read_indices = list(range(n_reads))
        return read_indices

    def acquire(self, progress=False):
        self.data = {'config': self.cfg, 'data': {}}

        prog = UndrivenSingleShotProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True)

        read_indices = self._read_indices(len(shots_i))
        min_sep = self.cfg.get("blob_min_separation_sigma", 2.0)

        d = self.data['data']
        d['read_indices'] = np.asarray(read_indices)
        self.results = {}

        for i, read_index in enumerate(read_indices):
            i_shots = np.asarray(shots_i[i][0])
            q_shots = np.asarray(shots_q[i][0])
            res = analyze_undriven_cloud(i_shots, q_shots,
                                         min_separation_sigma=min_sep)
            self.results[read_index] = res

            tag = str(read_index)
            d['i' + tag] = i_shots
            d['q' + tag] = q_shots
            d['labels' + tag] = res['labels']
            d['projection' + tag] = res['projection']
            d['center' + tag] = res['center']
            d['cov' + tag] = res['cov']
            d['axis' + tag] = res['axis']
            d['axis_angle' + tag] = res['axis_angle']
            d['n_blobs' + tag] = res['n_blobs']
            d['blob_weights' + tag] = res['blob_weights']
            d['blob_means_proj' + tag] = res['blob_means_proj']
            d['blob_sigmas_proj' + tag] = res['blob_sigmas_proj']
            d['blob_centers_iq' + tag] = res['blob_centers_iq']
            d['separation_sigma' + tag] = res['separation_sigma']
            d['secondary_population' + tag] = res['secondary_population']
            d['bic_1' + tag] = res['bic_1']
            d['bic_2' + tag] = res['bic_2']
            d['rms_radius' + tag] = res['rms_radius']
            d['sigma_along_axis' + tag] = res['sigma_along_axis']
            d['sigma_across_axis' + tag] = res['sigma_across_axis']

            print(
                f"[UndrivenSingleShot] Read {read_index}: N={res['n_shots']}, "
                f"center=({res['center'][0]:.3f}, {res['center'][1]:.3f}), "
                f"cloud sigma major/minor={res['sigma_along_axis']:.3f}/"
                f"{res['sigma_across_axis']:.3f}, n_blobs={res['n_blobs']}"
            )
            if res['n_blobs'] == 2:
                print(
                    f"    two blobs: separation={res['separation_sigma']:.2f} sigma, "
                    f"secondary population={100 * res['secondary_population']:.2f}%, "
                    f"BIC 1-comp={res['bic_1']:.1f} vs 2-comp={res['bic_2']:.1f}"
                )
                print(
                    f"    per-blob width along axis = "
                    f"{res['blob_sigmas_proj'][0]:.3f} / "
                    f"{res['blob_sigmas_proj'][1]:.3f} "
                    f"(weights {res['blob_weights'][0]:.3f} / "
                    f"{res['blob_weights'][1]:.3f}); centers "
                    f"({res['blob_centers_iq'][0][0]:.3f}, "
                    f"{res['blob_centers_iq'][0][1]:.3f}) and "
                    f"({res['blob_centers_iq'][1][0]:.3f}, "
                    f"{res['blob_centers_iq'][1][1]:.3f})"
                )
            elif res['n_blobs'] == 1:
                print(
                    f"    single blob (BIC 1-comp={res['bic_1']:.1f} vs "
                    f"2-comp={res['bic_2']:.1f}, best 2-comp separation="
                    f"{res['separation_sigma']:.2f} sigma < "
                    f"{min_sep} sigma threshold)"
                )

        return self.data

    def display(self, data=None, plotDisp=False, figNum=1, ran=None, **kwargs):
        if data is None:
            data = self.data
        d = data['data']

        read_indices = [int(r) for r in np.atleast_1d(d['read_indices'])]
        n_rows = len(read_indices)

        fig, axes = plt.subplots(n_rows, 2, figsize=(12, 4.6 * n_rows),
                                 num=figNum, squeeze=False)

        for row, read_index in enumerate(read_indices):
            tag = str(read_index)
            i_shots = np.asarray(d['i' + tag])
            q_shots = np.asarray(d['q' + tag])
            labels = np.asarray(d['labels' + tag])
            proj = np.asarray(d['projection' + tag])
            center = np.asarray(d['center' + tag])
            centers_iq = np.asarray(d['blob_centers_iq' + tag])
            weights = np.asarray(d['blob_weights' + tag])
            means = np.asarray(d['blob_means_proj' + tag])
            sigmas = np.asarray(d['blob_sigmas_proj' + tag])
            n_blobs = int(np.asarray(d['n_blobs' + tag]))
            sep_sigma = float(np.asarray(d['separation_sigma' + tag]))
            p_secondary = float(np.asarray(d['secondary_population' + tag]))

            ax = axes[row][0]
            if n_blobs == 2:
                for lbl, colour in ((0, 'tab:blue'), (1, 'tab:red')):
                    sel = labels == lbl
                    ax.plot(i_shots[sel], q_shots[sel], '.', markersize=2.5,
                            alpha=0.35, color=colour,
                            label=f"blob {lbl} ({100 * weights[lbl]:.1f}%)")
                for lbl in (0, 1):
                    if not np.any(np.isnan(centers_iq[lbl])):
                        ax.plot(centers_iq[lbl][0], centers_iq[lbl][1], 'kx',
                                markersize=11, markeredgewidth=2)
                ax.legend(markerscale=4, fontsize=8)
            else:
                ax.plot(i_shots, q_shots, '.', markersize=2.5, alpha=0.35,
                        color='tab:blue')
                ax.plot(center[0], center[1], 'kx', markersize=11,
                        markeredgewidth=2)
            ax.set_xlabel('I')
            ax.set_ylabel('Q')
            ax.set_aspect('equal', adjustable='datalim')
            ax.grid(True, alpha=0.3)
            ax.set_title(f"Read {read_index}: undriven IQ cloud "
                         f"(N={len(i_shots)} shots)")

            ax = axes[row][1]
            nbins = max(30, int(np.sqrt(len(proj))))
            counts, edges, _ = ax.hist(proj, bins=nbins, color='0.7',
                                       density=True)
            grid = np.linspace(edges[0], edges[-1], 500)
            if np.isfinite(means[0]) and sigmas[0] > 0:
                components = {}
                total = np.zeros_like(grid)
                for lbl in range(2):
                    if not np.isfinite(means[lbl]) or not (sigmas[lbl] > 0):
                        continue
                    comp = (weights[lbl] / (sigmas[lbl] * np.sqrt(2 * np.pi))
                            * np.exp(-0.5 * ((grid - means[lbl]) / sigmas[lbl]) ** 2))
                    components[lbl] = comp
                    total = total + comp
                ax.plot(grid, total, 'k-', linewidth=1.6, zorder=2,
                        label=f"{max(n_blobs, 1)}-Gaussian fit")
                if n_blobs == 2:
                    # drawn on top of the total, which would otherwise hide the
                    # dominant component exactly
                    for lbl, colour in ((0, 'tab:blue'), (1, 'tab:red')):
                        if lbl in components:
                            ax.plot(grid, components[lbl], '--', linewidth=1.4,
                                    color=colour, zorder=3,
                                    label=f"blob {lbl} "
                                          f"({100 * weights[lbl]:.1f}%)")
                ax.legend(fontsize=8)
            ax.set_xlabel('projection onto principal axis')
            ax.set_ylabel('density')
            ax.grid(True, alpha=0.3)
            if n_blobs == 2:
                sub = (f"2 blobs, separation {sep_sigma:.2f} sigma, "
                       f"secondary {100 * p_secondary:.2f}%")
            elif n_blobs == 1:
                sub = "1 blob (no second blob resolved)"
            else:
                sub = "fit unavailable"
            ax.set_title(f"Read {read_index}: {sub}")

        fig.suptitle(
            f"{self.titlename} — no qubit drive\n"
            f"readout {self.cfg['readout_length']} us @ "
            f"{self.cfg['pulse_freq']} MHz, gain {self.cfg['pulse_gain']}, "
            f"relax_delay {self.cfg['relax_delay']} us"
        )
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
