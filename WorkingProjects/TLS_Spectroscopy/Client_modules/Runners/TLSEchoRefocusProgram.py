"""Matched elapsed-time Hahn X/Y and two-pulse CPMG during a corrected visit.

Elapsed time is the separation of the first and final pi/2 pulse centers.
The refocusing centers divide this interval at 1/2 (Hahn) or 1/4 and 3/4
(CPMG). Pulse lengths and all gaps are expressed on the measured board clock.
"""

import math

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSEchoSquareMap as square


TIMES_US = (.35, .455, .65, .95, 1.35)
SEQUENCES = ("hahn_x", "hahn_y", "cpmg2_y")
DECAY_TIMES_US = (.35, .65, .95, 1.35, 1.8, 2.4, 3.2, 4.2)
DECAY_SEQUENCES = ("hahn_y", "cpmg2_y")
MAX_WINDOW_US = 1.4107
DECAY_MAX_WINDOW_US = 4.3
GUARD_US = .01


def timing_report(program, elapsed_us, sequence, *, phase_deg=0):
    """Return a schedule without changing the program or emitting instructions."""
    return _timing_report(program, elapsed_us, sequence, phase_deg=phase_deg,
                          max_window_us=MAX_WINDOW_US)


def _timing_report(program, elapsed_us, sequence, *, phase_deg, max_window_us):
    elapsed_us = float(elapsed_us)
    if not math.isfinite(elapsed_us) or elapsed_us <= 0:
        raise ValueError("refocusing elapsed time must be finite and positive")
    if sequence not in SEQUENCES or phase_deg not in square.PHASES_DEG:
        raise ValueError("unknown refocusing sequence or analysis phase")
    qubit_ch, flux_ch = program.cfg["qubit_ch"], program.cfg["ff_ch"]
    period = float(program.cycles2us(1))
    if not math.isfinite(period) or period <= 0 or any(
            not math.isclose(float(program.cycles2us(1, gen_ch=channel)),
                             period, rel_tol=1e-12, abs_tol=0.)
            for channel in (qubit_ch, flux_ch)):
        raise ValueError("refocusing requires equal generator and tProcessor clocks")
    half = int(program.us2cycles(square.PI2_US, gen_ch=qubit_ch))
    full = int(program.us2cycles(square.PI_US, gen_ch=qubit_ch))
    guard = int(program.us2cycles(GUARD_US))
    elapsed = 4 * int(program.us2cycles(elapsed_us / 4))
    if min(half, full, guard, elapsed) <= 0 or (half - full) % 2:
        raise ValueError("clock quantization cannot place symmetric pulse centers")
    offset = (half - full) // 2
    if sequence == "cpmg2_y":
        starts = [0, elapsed // 4 + offset, 3 * elapsed // 4 + offset, elapsed]
        lengths = [half, full, full, half]
        phases = [0, 90, 90, int(phase_deg)]
    else:
        starts = [0, elapsed // 2 + offset, elapsed]
        lengths = [half, full, half]
        phases = [0, 0 if sequence == "hahn_x" else 90, int(phase_deg)]
    gaps = [start - previous - length for previous, length, start in
            zip(starts[:-1], lengths[:-1], starts[1:])]
    window = elapsed + half + guard
    if min(gaps) < guard or gaps != gaps[::-1]:
        raise ValueError("refocusing requires symmetric positive finite-pulse gaps")
    if window * period > max_window_us + 1e-12:
        raise ValueError("refocusing science window exceeds the bounded hold")
    centers = [start + length / 2 for start, length in zip(starts, lengths)]
    return {"sequence": sequence, "requested_elapsed_us": elapsed_us,
            "clock_period_us": period, "elapsed_cycles": elapsed,
            "elapsed_us": elapsed * period, "window_cycles": window,
            "window_us": window * period, "pulse_starts_cycles": starts,
            "pulse_centers_cycles": centers, "pulse_lengths_cycles": lengths,
            "pulse_starts_us": [value * period for value in starts],
            "pulse_centers_us": [value * period for value in centers],
            "pulse_lengths_us": [value * period for value in lengths],
            "pulse_phases_deg": phases, "gaps_cycles": gaps,
            "gaps_us": [value * period for value in gaps],
            "final_guard_cycles": guard, "final_guard_us": guard * period}


def decay_timing_report(program, elapsed_us, sequence, *, phase_deg=0):
    """Matched long sequences, or adjacent pi/2 controls at the final-pulse time."""
    if sequence not in (*DECAY_SEQUENCES, "late_control"):
        raise ValueError("unknown decay sequence")
    timing = _timing_report(program, elapsed_us,
                           "hahn_y" if sequence == "late_control" else sequence,
                           phase_deg=phase_deg, max_window_us=DECAY_MAX_WINDOW_US)
    if sequence == "late_control":
        placement = timing["elapsed_cycles"]
        half = timing["pulse_lengths_cycles"][0]
        guard = timing["final_guard_cycles"]
        starts = [placement - half - guard, placement]
        if starts[0] < 0:
            raise ValueError("late control requires a nonnegative leading delay")
        period = timing["clock_period_us"]
        centers = [value + half / 2 for value in starts]
        timing.update({"sequence": sequence,
                       "placement_elapsed_cycles": placement,
                       "placement_elapsed_us": placement * period,
                       "elapsed_cycles": half + guard,
                       "elapsed_us": (half + guard) * period,
                       "pulse_starts_cycles": starts,
                       "pulse_starts_us": [value * period for value in starts],
                       "pulse_centers_cycles": centers,
                       "pulse_centers_us": [value * period for value in centers],
                       "pulse_lengths_cycles": [half, half],
                       "pulse_lengths_us": [half * period, half * period],
                       "pulse_phases_deg": [0, int(phase_deg)],
                       "gaps_cycles": [guard], "gaps_us": [guard * period]})
    return timing


def make_program(parent):
    """Use an identical flux envelope for every sequence at a given elapsed time."""
    class RefocusProgram(parent):
        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

            cfg = self.cfg
            timing = timing_report(self, cfg["refocus_elapsed_us"],
                                   cfg["refocus_sequence"],
                                   phase_deg=cfg["echo_phase_deg"])
            park, target = int(cfg["ff_park_gain"]), int(cfg["ff_gain"])
            if park == target or self._t1_ff_compensation is None:
                raise ValueError("refocusing requires a corrected target visit")
            pre = float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us
            post = float(cfg["opx_resident_post_us"])
            window = timing["window_us"]
            if not all(math.isfinite(value) and value > 0 for value in (pre, post)):
                raise ValueError("refocusing needs positive finite pre/post holds")
            target_segments, recovery = ff_pulse.compensation_round_trip_segments(
                self._t1_ff_compensation, pre + window + post,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            before, tail = ff_pulse.split_compensation_segments(target_segments, pre)
            during, after = ff_pulse.split_compensation_segments(tail, window)
            if not before or not during or not after:
                raise ValueError("correction does not cover the refocusing window")
            held = float(before[-1][0])
            if (sum(duration for _, duration in during) < window - 1e-9 or
                    not math.isfinite(held) or not all(
                        math.isfinite(float(level)) and abs(float(level) - held) <= 1e-12
                        for level, _ in during)):
                raise ValueError("refocusing requires constant correction during science")
            timing.update({"science_start_us": pre, "science_end_us": pre + window,
                           "held_coefficient": held, "target_hold_us": pre + window + post})
            cfg["refocus_timing"] = timing
            cfg["ff_hold"] = float(cfg["opx_resident_pre_us"]) + window + post
            ff_pulse.play_relative_compensation_segments(self, park, target, before)
            self.sync_all(0)
            waits = timing["gaps_cycles"] + [timing["final_guard_cycles"]]
            for length, phase, wait in zip(timing["pulse_lengths_cycles"],
                                           timing["pulse_phases_deg"], waits):
                self.set_pulse_registers(
                    ch=cfg["qubit_ch"], style="const",
                    freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                                       gen_ch=cfg["qubit_ch"]),
                    phase=self.deg2reg(phase, gen_ch=cfg["qubit_ch"]),
                    gain=square.GAIN_DAC, length=length)
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(wait)
            ff_pulse.play_relative_compensation_segments(self, park, target, after)
            ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
            ff_pulse.play_hard_step(self, park)
            self.sync_all(0)

    return RefocusProgram


def _flux_events(program, park, target, segments):
    """Quantize with the same lengths, clipping and chunking as ff_pulse."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

    channel = program.cfg["ff_ch"]
    maxv = ff_pulse.PulseFunctions.ff_maxv(program, scaled=True)
    cursor = 0
    events = []
    for coefficient, duration in segments:
        coefficient, duration = float(coefficient), float(duration)
        if not math.isfinite(coefficient) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("flux schedule requires finite levels and positive durations")
        gain = int(min(maxv, max(-maxv, round(park + coefficient * (target - park)))))
        total = max(int(program.us2cycles(duration, gen_ch=channel)), 3)
        count = max(1, (total + ff_pulse._MAX_CONST_LEN - 1) // ff_pulse._MAX_CONST_LEN)
        base, extra = divmod(total, count)
        for chunk in range(count):
            length = max(base + (1 if chunk < extra else 0), 3)
            events.append({"coefficient": coefficient, "gain_dac": gain,
                           "start_cycles": cursor, "length_cycles": length,
                           "start_us": float(program.cycles2us(cursor, gen_ch=channel)),
                           "duration_us": float(program.cycles2us(length, gen_ch=channel))})
            cursor += length
    return events, cursor


def make_decay_program(parent):
    """Play the full corrected flux tail concurrently with explicit pulse times.

    The old builder relies on a constant DAC command during its short science
    window. This opt-in builder schedules every correction segment, including
    transitions within long pulse trains, from a shared science epoch. It must
    not call sync_all between microwave pulses: the queued flux tail already
    extends to the end of the visit.
    """
    class RefocusDecayProgram(parent):
        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

            cfg = self.cfg
            timing = decay_timing_report(self, cfg["refocus_elapsed_us"],
                                         cfg["refocus_sequence"],
                                         phase_deg=cfg["echo_phase_deg"])
            park, target = int(cfg["ff_park_gain"]), int(cfg["ff_gain"])
            if park == target or self._t1_ff_compensation is None:
                raise ValueError("refocusing decay requires a corrected target visit")
            pre = float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us
            post = float(cfg["opx_resident_post_us"])
            window = timing["window_us"]
            if not all(math.isfinite(value) and value > 0 for value in (pre, post)):
                raise ValueError("refocusing decay needs positive finite pre/post holds")
            target_segments, recovery = ff_pulse.compensation_round_trip_segments(
                self._t1_ff_compensation, pre + window + post,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            before, tail = ff_pulse.split_compensation_segments(target_segments, pre)
            if (not before or not tail or not recovery or
                    sum(duration for _, duration in tail) < window + post - 1e-9):
                raise ValueError("correction does not cover the decay visit")
            _, prefix_cycles = _flux_events(self, park, target, before)
            events, tail_cycles = _flux_events(self, park, target, tail)
            if tail_cycles <= timing["window_cycles"]:
                raise ValueError("quantized flux visit must include the full science and post hold")
            period = timing["clock_period_us"]
            timing.update({"concurrent_flux_correction": True,
                           "nominal_science_start_us": pre,
                           "science_start_cycles": prefix_cycles,
                           "science_start_us": prefix_cycles * period,
                           "science_end_us": (prefix_cycles + timing["window_cycles"]) * period,
                           "nominal_target_hold_us": pre + window + post,
                           "target_hold_cycles": prefix_cycles + tail_cycles,
                           "target_hold_us": (prefix_cycles + tail_cycles) * period,
                           "science_and_post_flux_events": events})
            cfg["refocus_timing"] = timing
            cfg["ff_hold"] = float(cfg["opx_resident_pre_us"]) + window + post
            ff_pulse.play_relative_compensation_segments(self, park, target, before)
            self.sync_all(0)
            for event in events:
                self.set_pulse_registers(
                    ch=cfg["ff_ch"], style="const", freq=0, phase=0,
                    stdysel="last", gain=event["gain_dac"], length=event["length_cycles"])
                self.pulse(ch=cfg["ff_ch"], t=event["start_cycles"])
            for start, length, phase in zip(timing["pulse_starts_cycles"],
                                            timing["pulse_lengths_cycles"],
                                            timing["pulse_phases_deg"]):
                self.set_pulse_registers(
                    ch=cfg["qubit_ch"], style="const",
                    freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]), gen_ch=cfg["qubit_ch"]),
                    phase=self.deg2reg(phase, gen_ch=cfg["qubit_ch"]),
                    gain=square.GAIN_DAC, length=length)
                self.pulse(ch=cfg["qubit_ch"], t=start)
            self.sync_all(0)
            ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
            ff_pulse.play_hard_step(self, park)
            self.sync_all(0)

    return RefocusDecayProgram
