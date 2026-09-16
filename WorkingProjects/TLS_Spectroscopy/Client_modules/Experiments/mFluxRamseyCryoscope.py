import datetime
import time

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, fluxpred_command as fpc
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    acquire_with_retry, split_reps, suppress_stdout,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, readout_thermalization_us, set_readout_pulse,
)
from fluxpred.core import Command, probe_fits_constant_segment

ARMS = ("g", "e", "i", "q")
QUADRATURE_ARMS = ("i", "q")
VISIT_ORDERS = (("g", "e", "i", "q"), ("q", "i", "e", "g"),
                ("e", "g", "q", "i"), ("i", "q", "g", "e"))


class FluxRamseyCryoscopeProgram(AveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def _set_qubit_pulse(self, gain, phase_deg, waveform="qubit", freq_mhz=None):
        cfg = self.cfg
        frequency = cfg["cryoscope_probe_freq"] if freq_mhz is None else freq_mhz
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(frequency), gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(float(phase_deg), gen_ch=cfg["qubit_ch"]),
            gain=int(gain), waveform=waveform)

    def _arm(self):
        arm = str(self.cfg.get("cryoscope_arm", "i")).lower()
        if arm not in ARMS:
            raise ValueError(f"cryoscope_arm must be one of {ARMS}, got {arm!r}")
        return arm

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg["shots"])
        for key in ("qubit_pi_gain", "qubit_pi2_gain", "cryoscope_probe_freq"):
            if key not in cfg or not np.isfinite(float(cfg[key])):
                raise ValueError(f"{key} must be finite")
        if int(cfg["qubit_pi_gain"]) <= 0 or int(cfg["qubit_pi2_gain"]) <= 0:
            raise ValueError("qubit_pi_gain and qubit_pi2_gain must be positive")
        self._arm()
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        self.declare_gen(ch=cfg["ff_ch"], nqz=cfg.get("ff_nqz", 1))
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ro_ch, freq=cfg["read_pulse_freq"],
                length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                gen_ch=cfg["res_ch"])
        self._read_freq_reg = self.freq2reg(
            cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        add_qubit_gaussian(self)
        if active_reset.uses_feedback(cfg):
            add_qubit_gaussian(
                self, name="qubit_reset",
                sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
                drag_beta=float(cfg.get("reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        set_readout_pulse(self, self._read_freq_reg)
        self._build_flux_plans()
        self.synci(200)

    def _build_flux_plans(self):
        cfg = self.cfg
        command = cfg["cryoscope_command"]
        pulse_ns = float(cfg["cryoscope_pulse_ns"])
        actual_ns = fpc.qubit_pulse_ns(self.soccfg, channel=cfg["qubit_ch"],
                                       sigma_us=float(cfg["sigma"]))
        if actual_ns > pulse_ns+1e-9:
            raise ValueError(
                f"the compiled qubit envelope is {actual_ns:.3f} ns but the flux timeline "
                f"reserved only {pulse_ns:.3f} ns for it; the alignment would stretch the flux "
                f"history. Rebuild the delay grid with pulse_ns >= {actual_ns:.3f}")
        self.qubit_pulse_ns = actual_ns
        parts = fpc.split_for_probe(
            command, probe_start_ns=float(cfg["cryoscope_delay_ns"]),
            probe_window_ns=float(cfg["cryoscope_window_ns"]), pulse_ns=pulse_ns)
        self.probe_level = parts["probe_level"]
        self.probe_start_ns = parts["probe_start_ns"]
        self.probe_end_ns = parts["probe_end_ns"]
        self.flux_plans = {}
        for name in ("before", "first_pulse", "probe", "second_pulse"):
            part = parts[name]
            if part is None:
                self.flux_plans[name] = None
                continue
            if name == "probe":
                part = fpc.freeze_probe_segment(part)
            self.flux_plans[name] = fpc.compile_for_program(
                part, self, channel=cfg["ff_ch"], park_gain=cfg["ff_park_gain"],
                scale_gain=cfg["cryoscope_scale_gain"],
                max_instructions=int(cfg.get("cryoscope_max_instructions", 4096)))
        park_return = Command([0.0, float(cfg.get("cryoscope_park_return_us", 4.0))*1000.0], [0.0])
        self.flux_plans["park_return"] = fpc.compile_for_program(
            park_return, self, channel=cfg["ff_ch"], park_gain=cfg["ff_park_gain"],
            scale_gain=cfg["cryoscope_scale_gain"],
            max_instructions=int(cfg.get("cryoscope_max_instructions", 4096)))
        self.flux_report = {
            name: fpc.plan_report(plan, plan.normalized_command)
            for name, plan in self.flux_plans.items() if plan is not None}

    def _play(self, name):
        plan = self.flux_plans.get(name)
        if plan is not None:
            fpc.emit_part(plan, self, channel=self.cfg["ff_ch"])

    def body(self):
        cfg = self.cfg
        arm = self._arm()
        self.sync_all(self.us2cycles(0.05))
        if active_reset.uses_feedback(cfg):
            reset_read_gain = cfg.get("reset_read_pulse_gain")
            if reset_read_gain is not None:
                set_readout_pulse(self, self._read_freq_reg, gain=int(reset_read_gain))
            self._set_qubit_pulse(
                int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])), 0.0, "qubit_reset",
                cfg.get("reset_pi_freq", cfg["qubit_pi_freq"]))
            active_reset.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
            if reset_read_gain is not None:
                set_readout_pulse(self, self._read_freq_reg)
        if active_reset.heralds(cfg):
            self.measure(
                pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                wait=True, syncdelay=self.us2cycles(cfg.get("herald_delay", 8.0)))
        self.sync_all(self.us2cycles(float(cfg.get("cryoscope_prepark_us", 0.5))))
        self._play("before")
        self.sync_all(0)
        if arm != "g":
            gain = cfg["qubit_pi_gain"] if arm == "e" else cfg["qubit_pi2_gain"]
            self._set_qubit_pulse(int(gain), 0.0)
            self.pulse(ch=cfg["qubit_ch"])
        self._play("first_pulse")
        self.sync_all(0)
        self._play("probe")
        self.sync_all(0)
        if arm in QUADRATURE_ARMS:
            phase = 0.0 if arm == "i" else float(cfg.get("cryoscope_q_phase_deg", 90.0))
            self._set_qubit_pulse(int(cfg["qubit_pi2_gain"]), phase)
            self.pulse(ch=cfg["qubit_ch"])
        self._play("second_pulse")
        self.sync_all(0)
        self.measure(
            pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True, syncdelay=self.us2cycles(0.01))
        self._play("park_return")
        self.sync_all(self.us2cycles(
            cfg.get("active_reset_post_measure_delay_us", readout_thermalization_us(cfg))
            if active_reset.uses_feedback(cfg) else cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        n_herald = int(active_reset.heralds(self.cfg))
        super().acquire(soc, load_pulses=load_pulses,
                        readouts_per_experiment=1+n_reset+n_herald, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["ro_chs"][0])
        n_reset = active_reset.active_reset_readouts(self.cfg)
        n_herald = int(active_reset.heralds(self.cfg))
        reads = 1+n_reset+n_herald
        shots_i = self.di_buf[0].reshape((self.cfg["reps"], reads))/length
        shots_q = self.dq_buf[0].reshape((self.cfg["reps"], reads))/length
        if n_herald:
            return (shots_i[:, n_reset], shots_q[:, n_reset],
                    shots_i[:, n_reset+1], shots_q[:, n_reset+1])
        empty = np.full(self.cfg["reps"], np.nan)
        return empty, empty.copy(), shots_i[:, n_reset], shots_q[:, n_reset]


class FluxRamseyCryoscope(ExperimentClass):

    def __init__(self, *args, command=None, delays_ns=None, windows_ns=(40.0, 400.0),
                 probe_freq_ghz=None, scale_gain=None, shots=60, rounds=2, calib_params=None,
                 pulse_ns=None, hold_ns=None, recovery_ns=None, heartbeat_s=5.0,
                 min_reference_contrast=0.05, reverse_delays=False, readout_span_ns=None,
                 save=True, **kw):
        cfg = dict(kw.get("cfg") or {})
        if command is None:
            raise ValueError("command is required; build it with fluxpred_command.build_timeline")
        if delays_ns is None or not len(delays_ns):
            raise ValueError("delays_ns is required")
        if probe_freq_ghz is None:
            raise ValueError("probe_freq_ghz is required")
        if scale_gain is None:
            raise ValueError("scale_gain is required")
        if calib_params is None:
            calib_params = cfg.get("calib_params")
        if calib_params is None:
            raise ValueError("calib_params is required")
        cfg["shots"] = cfg["reps"] = int(shots)
        cfg["cryoscope_probe_freq"] = float(np.ravel(probe_freq_ghz)[0])*1000.0
        cfg["cryoscope_scale_gain"] = float(scale_gain)
        kw["cfg"] = cfg
        super().__init__(*args, **kw)
        self.command = command
        self.delays_ns = np.asarray(delays_ns, dtype=float)
        self.windows_ns = tuple(float(value) for value in windows_ns)
        if len(self.windows_ns) != 2 or self.windows_ns[0] >= self.windows_ns[1]:
            raise ValueError("windows_ns must be a (coarse, fine) pair with coarse < fine")
        self.probe_freq_ghz = np.broadcast_to(
            np.asarray(probe_freq_ghz, dtype=float), self.delays_ns.shape).astype(float)
        self.scale_gain = float(scale_gain)
        self.shots = int(shots)
        self.rounds = max(1, min(int(rounds), self.shots))
        self.calib_params = dict(calib_params)
        self.pulse_ns = (float(pulse_ns) if pulse_ns is not None
                         else 4.0*float(cfg["sigma"])*1000.0)
        self.hold_ns = float(hold_ns) if hold_ns is not None else float(command.edges_ns[-1])
        self.recovery_ns = (float(recovery_ns) if recovery_ns is not None
                            else float(command.edges_ns[-1])-self.hold_ns)
        self.heartbeat_s = float(heartbeat_s)
        self.min_reference_contrast = float(min_reference_contrast)
        self.reverse_delays = bool(reverse_delays)
        self.readout_span_ns = (float(readout_span_ns) if readout_span_ns is not None
                                else float(cfg["read_length"])*1000.0
                                + float(cfg.get("adc_trig_offset", 0.0))*1000.0)
        self.save = bool(save)
        self._validate_probe_placement()

    def _validate_probe_placement(self):
        span = (2.0*self.pulse_ns+max(self.windows_ns)+self.readout_span_ns)
        horizon = float(self.command.edges_ns[-1])
        bad = [float(delay) for delay in self.delays_ns
               if not probe_fits_constant_segment(self.command, delay, span)]
        if bad:
            raise ValueError(
                f"{len(bad)} probe delay(s) do not sit inside one constant flux segment, so the "
                f"frozen-probe observable would not be exact: {bad[:5]} ns")
        overrun = [float(delay) for delay in self.delays_ns if delay+span > horizon]
        if overrun:
            raise ValueError(
                f"{len(overrun)} probe delay(s) run past the {horizon/1000.0:g} us flux timeline")

    def _point(self, delay_index, delay_ns, window_ns, arm, reps):
        cfg = dict(self.cfg)
        cfg["cryoscope_probe_freq"] = float(self.probe_freq_ghz[delay_index])*1000.0
        cfg["cryoscope_command"] = self.command
        cfg["cryoscope_delay_ns"] = float(delay_ns)
        cfg["cryoscope_window_ns"] = float(window_ns)
        cfg["cryoscope_pulse_ns"] = self.pulse_ns
        cfg["cryoscope_arm"] = arm
        cfg["shots"] = cfg["reps"] = int(reps)
        with suppress_stdout():
            prog = FluxRamseyCryoscopeProgram(self.soccfg, cfg)
            herald_i, herald_q, shot_i, shot_q = acquire_with_retry(
                prog, self.soc, load_pulses=True, progress=False)
        return prog, herald_i, herald_q, shot_i, shot_q

    def _tasks(self):
        tasks = []
        for delay_index, delay_ns in enumerate(self.delays_ns):
            order = VISIT_ORDERS[delay_index % len(VISIT_ORDERS)]
            point = []
            for window_index, window_ns in enumerate(self.windows_ns):
                arms = ARMS if window_index == 0 else QUADRATURE_ARMS
                point.extend((window_index, window_ns, arm) for arm in arms)
            point.sort(key=lambda item: (order.index(item[2]), item[0]))
            tasks.append((delay_index, float(delay_ns), tuple(point), order))
        return tasks

    def acquire(self, progress=True, plotDisp=False):
        tasks = self._tasks()
        if self.reverse_delays:
            tasks = list(reversed(tasks))
        total = sum(len(point) for _, _, point, _ in tasks)
        start = time.time()
        last_beat = start
        done = 0
        records = {}
        visit_orders = []
        flux_report = None
        print(f"[cryoscope] {len(self.delays_ns)} delays x {len(self.windows_ns)} windows, "
              f"{self.shots} shots/arm, {total} acquisitions, "
              f"probe {float(self.probe_freq_ghz[0]):.6f}..{float(self.probe_freq_ghz[-1]):.6f} GHz, scan "
              f"{'reversed' if self.reverse_delays else 'forward'}")
        for delay_index, delay_ns, point, order in tasks:
            populations = {}
            keep_fraction = {}
            visit_orders.append(list(order))
            for window_index, window_ns, arm in point:
                pieces = {"herald_i": [], "herald_q": [], "i": [], "q": []}
                for reps in split_reps(self.shots, self.rounds):
                    if reps <= 0:
                        continue
                    prog, hi, hq, si, sq = self._point(
                        delay_index, delay_ns, window_ns, arm, reps)
                    if flux_report is None:
                        flux_report = prog.flux_report
                    pieces["herald_i"].append(np.asarray(hi, dtype=float))
                    pieces["herald_q"].append(np.asarray(hq, dtype=float))
                    pieces["i"].append(np.asarray(si, dtype=float))
                    pieces["q"].append(np.asarray(sq, dtype=float))
                merged = {name: np.concatenate(parts) for name, parts in pieces.items()}
                final = discriminate_shots(merged["i"], merged["q"], self.calib_params)
                if active_reset.heralds(self.cfg):
                    keep = active_reset.herald_keep(
                        merged["herald_i"], merged["herald_q"], self.calib_params)
                else:
                    keep = np.ones(final.size, dtype=bool)
                key = arm if arm in ("g", "e") else f"{arm}{window_index}"
                populations[key] = float(np.mean(final[keep])) if np.any(keep) else np.nan
                keep_fraction[key] = float(np.mean(keep))
                done += 1
                now = time.time()
                if progress and (now-last_beat >= self.heartbeat_s or done == total):
                    last_beat = now
                    progress_counter(done-1, total, start_time=start,
                                     label=f"[cryoscope] {delay_ns/1000.0:8.2f}us "
                                           f"w={window_ns:.0f}ns {arm}")
            records[delay_index] = {"delay_ns": float(delay_ns), "populations": populations,
                                    "keep_fraction": keep_fraction}
        records = [records[index] for index in sorted(records)]
        self.records = records
        self.flux_report = flux_report
        self.data = {
            "meta_dict": {k: v for k, v in self.cfg.items() if k != "cryoscope_command"},
            "delays_ns": self.delays_ns,
            "windows_ns": np.asarray(self.windows_ns),
            "probe_freq_ghz": self.probe_freq_ghz,
            "scale_gain": self.scale_gain,
            "pulse_ns": self.pulse_ns,
            "hold_ns": self.hold_ns,
            "recovery_ns": self.recovery_ns,
            "shots_per_point": self.shots,
            "rounds": self.rounds,
            "calib_params": dict(self.calib_params),
            "normalized_command": self.command.to_dict(),
            "flux_report": flux_report,
            "records": records,
            "arm_visit_orders": visit_orders,
            "reverse_delays": bool(self.reverse_delays),
            "elapsed_s": time.time()-start,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if self.save:
            self.pickle_data()
        return self.data
