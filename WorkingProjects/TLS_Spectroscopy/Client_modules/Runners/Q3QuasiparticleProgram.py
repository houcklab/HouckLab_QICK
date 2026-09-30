"""Local QICK program for Q3QuasiparticlePumping; production reset is reused."""

import math

from . import Q3QuasiparticlePumping as runner


def emit_cell(*, wait, record, condition, prepare_probe, delay_us,
              washout_us, ringdown_us):
    wait(washout_us)
    record('before', lambda: None)
    wait(ringdown_us)
    condition()
    record('conditioned', lambda: None)
    wait(ringdown_us)

    def probe():
        prepare_probe()
        wait(delay_us)

    record('probe', probe)
    wait(ringdown_us)


def emit_feedback_free_cell(*, wait, condition, prepare_probe, measure,
                           delay_us, washout_us, recovery_us, ringdown_us):
    wait(washout_us)
    condition()
    wait(recovery_us)
    prepare_probe()
    wait(delay_us)
    measure()
    wait(ringdown_us)


def make_program_class():
    from ..active_reset_OPX.programs import (
        OPXResetT1Program, _declare_common, _reserved_registers,
        allocate_registers, allocate_named_registers, resident_control_names,
        emit_t1_shot, _pulse_pi_and_align)

    class Q3QuasiparticleProgram(OPXResetT1Program):
        record_words = 24
        decode_dmem_records = staticmethod(runner.decode_records)

        def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
            values = dict(cfg)
            self.feedback_free = bool(values.get('qp_feedback_free', False))
            if self.feedback_free:
                from ..active_reset_OPX.records import decode_payload_records
                self.record_words = 2
                self.decode_dmem_records = decode_payload_records
                recovery = float(values.get('qp_recovery_us', 0.))
                if not math.isfinite(recovery) or recovery < 0:
                    raise ValueError('invalid conditioning recovery time')
            self.conditions = list(values['qp_conditions'])
            self.shots = int(values['qp_shots'])
            if self.shots < 1 or len(self.conditions) != 10:
                raise ValueError('positive shots and all ten q3 conditions required')
            if {(c['arm'], c['state']) for c in self.conditions} != {
                    (a, s) for a in runner.ARMS for s in ('g', 'e')}:
                raise ValueError('missing or duplicated conditioning arm')
            if not math.isfinite(values['qp_delay_us']) or values['qp_delay_us'] < 0:
                raise ValueError('invalid probe delay')
            if values.get('do_ff', True) or int(values['ff_park_gain']) != -25146:
                raise ValueError('this experiment requires q3 at park, without flux excursions')
            values['reps'] = self.shots * len(self.conditions)
            super().__init__(soccfg, values, payload_calibration, loop_calibration)

        def _drive(self, *, gain, phase=0., start='auto'):
            ch = self.cfg['qubit_ch']
            self.set_pulse_registers(
                ch=ch, style='arb', waveform='qubit', gain=int(gain),
                freq=self.freq2reg(self.cfg['qubit_pi_freq'], gen_ch=ch),
                phase=self.deg2reg(phase, gen_ch=ch))
            self.pulse(ch=ch, t=start)

        def _condition(self, arm):
            timing = self.conditioning_timing[arm]
            self.sync_all(0)
            for pulse in timing['pulses']:
                self._drive(gain=self.cfg['qubit_pi_gain'], phase=pulse['phase_deg'],
                            start=pulse['start_tick'])
            # QICK 0.2.133 sync_all truncates max timestamp + padding to ticks.
            # Absolute pulse timestamps preserve precisely 30-us start spacing.
            last = max(self._dac_ts + self._adc_ts)
            self.sync_all(timing['duration_ticks'] - int(last))

        def _record(self, index, stage, payload):
            emit_t1_shot(
                self, page=self.reset_page, regs=self.reset_regs,
                reset_scheme='opx_unbounded', payload_calibration=self.payload_calibration,
                loop_calibration=self.loop_calibration,
                park_up=lambda: None, park_down=lambda: None,
                prepare_excited=lambda: None, do_prepare=False,
                wait_payload=payload, measure_project=self._measure_project,
                play_pi=lambda: self.pulse(ch=self.cfg['qubit_ch']),
                prepare_reset=self._set_reset_pulse,
                label_prefix=f'QP_{index}_{stage.upper()}',
                wait_reset_ringdown=self._wait_reset_ringdown)

        def _cell(self, index, condition):
            def prepare():
                self._set_payload_pulse(gain=self.cfg['qubit_pi_gain']
                                        if condition['state'] == 'e' else 0)
                _pulse_pi_and_align(self)

            if self.feedback_free:
                def measure():
                    self._measure_raw()
                    for name in ('i', 'q'):
                        self.memw(self.reset_page, self.reset_regs[name], self.reset_regs['address'])
                        self.mathi(self.reset_page, self.reset_regs['address'],
                                   self.reset_regs['address'], '+', 1)
                emit_feedback_free_cell(
                    wait=lambda us: self.sync_all(self.us2cycles(us)),
                    condition=lambda: self._condition(condition['arm']),
                    prepare_probe=prepare, measure=measure,
                    delay_us=self.cfg['qp_delay_us'], washout_us=runner.WASHOUT_US,
                    recovery_us=self.cfg['qp_recovery_us'], ringdown_us=runner.RINGDOWN_US)
                return
            emit_cell(wait=lambda us: self.sync_all(self.us2cycles(us)),
                      record=lambda stage, payload: self._record(index, stage, payload),
                      condition=lambda: self._condition(condition['arm']),
                      prepare_probe=prepare, delay_us=self.cfg['qp_delay_us'],
                      washout_us=runner.WASHOUT_US, ringdown_us=runner.RINGDOWN_US)

        def make_program(self):
            _declare_common(self)
            self._declare_experiment()
            if not (self.reset_config.persistent_park and self.reset_config.hard_flux_steps):
                raise ValueError('persistent hard park required')
            ch = self.cfg['qubit_ch']
            samples = len(self.pulses[ch]['qubit']['data'])
            gencfg = self.soccfg['gens'][ch]
            pulse_ticks = math.ceil(samples / gencfg['samps_per_clk']
                                    * self.soccfg['fs_proc'] / gencfg['f_fabric'])
            self.conditioning_timing = {
                arm: runner.conditioning_schedule(
                    arm, pulse_ticks=pulse_ticks, period_ticks=self.us2cycles(runner.PERIOD_US),
                    pair_gap_ticks=max(1, self.us2cycles(.04)), lead_ticks=self.us2cycles(1.))
                for arm in runner.ARMS}
            self.reset_page = self.ch_page(ch)
            self.reset_regs = allocate_registers(self, self.reset_page)
            reserved = _reserved_registers(self, 0)
            if self.reset_page == 0:
                reserved.update(self.reset_regs.values())
            controls = allocate_named_registers(
                self, 0, resident_control_names(self.cfg, ('shot_loop', 'done')), reserved=reserved)
            self.regwi(self.reset_page, self.reset_regs['address'], self.record_base)
            self.regwi(0, controls['done'], 0)
            self.memwi(0, controls['done'], self.done_addr)
            self.regwi(0, controls['shot_loop'], self.shots - 1)
            self._initialize_stream(
                controls, total_shots=self.shots, records_per_shot=len(self.conditions),
                total_units=self.reps, records_per_unit=1, prefix='QP_STREAM')
            self._begin_park_lifecycle()
            self.label('QP_SHOT_LOOP')
            for index, condition in enumerate(self.conditions):
                self._cell(index, condition)
                self.mathi(0, controls['done'], controls['done'], '+', 1)
                self.memwi(0, controls['done'], self.done_addr)
                self._stream_after_shot()
            self.loopnz(0, controls['shot_loop'], 'QP_SHOT_LOOP')
            self._finish_stream()
            self._end_park_lifecycle()
            self.end()

    return Q3QuasiparticleProgram
