"""Experiment-local fixed-duration feedback and repeated corrected flux visits.

No production reset code is changed. Every reset saves all five IQ pairs;
failed final verification is retained, not retried or labelled successful.
"""
from . import TLSRepeatedLoading as runner
from ..active_reset_OPX.programs import (
    OPXResetT1Program, _declare_common, _reserved_registers,
    allocate_named_registers, resident_control_names, _pulse_pi_and_align,
    TimingMatchedReferenceDMemProgram,
)


class LoadingReferenceProgram(TimingMatchedReferenceDMemProgram):
    """Known-state references with the same four readout/zero-pi opportunities."""

    def _emit_reference(self):
        if not (self.reset_config.persistent_park and self.reset_config.hard_flux_steps):
            raise ValueError('loading references require persistent hard park')
        page = self.reset_page
        gain = self.sreg(self.cfg['qubit_ch'], 'gain')
        excited = bool(self.cfg['prep_excited'])
        rounds, guard, prior_gain = runner.reference_settings(self.cfg)
        change_readout = rounds and prior_gain != self.cfg['read_pulse_gain']
        if change_readout:
            self.regwi(self.ch_page(self.cfg['res_ch']), self.sreg(self.cfg['res_ch'], 'gain'), prior_gain)
        if rounds:
            for k in range(rounds):
                if k:
                    self.sync_all(self.us2cycles(self.reset_config.reset_settle_us))
                self._measure_raw()
                self.sync_all(self.us2cycles(guard))
                self.regwi(page, gain, self.cfg['qubit_pi_gain']
                           if excited and k == rounds-1 else 0)
                _pulse_pi_and_align(self)
            self.sync_all(self.us2cycles(self.reset_config.reset_settle_us))
        else:
            self.regwi(page, gain, self.cfg['qubit_pi_gain'] if excited else 0)
            _pulse_pi_and_align(self)
        if change_readout:
            self.regwi(self.ch_page(self.cfg['res_ch']), self.sreg(self.cfg['res_ch'], 'gain'),
                       int(self.cfg['read_pulse_gain']))
        self._measure_raw()
        for name in ('i', 'q'):
            self.memw(page, self.reset_regs[name], self.reset_regs['address'])
            self.mathi(page, self.reset_regs['address'], self.reset_regs['address'], '+', 1)
        self.sync_all(self.us2cycles(self.reset_config.inter_shot_delay_us))


class RepeatedLoadingProgram(OPXResetT1Program):
    record_words = runner.RECORD_WORDS
    decode_dmem_records = staticmethod(runner.decode_records)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        self.task = dict(cfg['loading_task'])
        runner.write_schedule(self.task['writes'])
        reference = self.task.get('reference_state')
        if reference not in (None, 'g', 'e'):
            raise ValueError('invalid reference preparation')
        probes = self.task['probes_us']
        if (reference is None and sorted(probes) != [.1, 40.]) or (reference and probes != [.1]):
            raise ValueError('use paired short/long probes or a short reference')
        if int(self.task['shots']) != self.task['shots'] or self.task['shots'] < 2:
            raise ValueError('positive integral shot count required')
        if not cfg.get('do_ff') or not cfg.get('opx_persistent_park') or not cfg.get('opx_hard_flux_steps'):
            raise ValueError('corrected excursions and persistent hard park required')
        if cfg.get('flux_predistortion_overlap_payload_readout', True):
            raise ValueError('readout must follow the full flux return')
        if cfg.get('flux_predistortion_recovery_us') != 40.:
            raise ValueError('this test requires the established 40-us return')
        for key in ('ff_gain', 'loading_probe_gain'):
            if not -32768 <= int(cfg[key]) <= 32767:
                raise ValueError('flux gain outside signed DAC range')
        if int(cfg['ff_park_gain']) != -25146 or float(cfg['qubit_pi_freq']) != 4367.292:
            raise ValueError('q3 park configuration required')
        if 'loading_final_readout_gain' in cfg and (
                cfg['read_pulse_gain'] != 1200 or cfg['loading_final_readout_gain'] != 1880):
            raise ValueError('reduced loading readout requires feedback gain 1200 and final gain 1880')
        self._sync_ticks = 0
        self.timing = {}
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def sync_all(self, t=0):
        # Mirror this QICK version's truncation. These are scheduled hardware
        # times, not an assertion about the delivered analog impulse response.
        self._sync_ticks += max(0, int(max(self._dac_ts+self._adc_ts)+t))
        return super().sync_all(t)

    def _save_iq(self):
        for name in ('i', 'q'):
            self.memw(self.reset_page, self.reset_regs[name], self.reset_regs['address'])
            self.mathi(self.reset_page, self.reset_regs['address'], self.reset_regs['address'], '+', 1)

    def _fixed_reset(self, label):
        page, regs = self.reset_page, self.reset_regs
        for k in range(runner.RESET_ROUNDS):
            cal = self.payload_calibration if k == 0 else self.loop_calibration
            self._measure_project(cal, 'payload' if k == 0 else 'loop')
            self._save_iq()
            self._set_reset_pulse()
            gain_reg = self.sreg(self.cfg['qubit_ch'], 'gain')
            self.regwi(page, gain_reg, 0)
            self.safe_regwi(page, regs['threshold'], cal.assembly_thresholds()['excited'])
            op = '>' if cal.assembly_plan()['excited_above'] else '<'
            self.condj(page, regs['z'], op, regs['threshold'], f'{label}_FIRE_{k}')
            self.condj(page, regs['z'], '==', regs['z'], f'{label}_PLAY_{k}')
            self.label(f'{label}_FIRE_{k}')
            self.regwi(page, gain_reg, int(self.cfg.get('reset_pi_gain', self.cfg['qubit_pi_gain'])))
            self.label(f'{label}_PLAY_{k}')
            # Both outcomes play the same waveform for the same duration.
            # wait_all has already consumed 10 us beyond the ADC end; 20 us
            # scheduled guard leaves headroom for projection/branch instructions.
            self.sync_all(self.us2cycles(runner.GUARD_US))
            _pulse_pi_and_align(self)
        self._measure_project(self.loop_calibration, 'loop')
        self._save_iq()
        self.sync_all(self.us2cycles(runner.GUARD_US))

    def _cell(self, index, probe_us):
        page, regs = self.reset_page, self.reset_regs
        label = f'LOAD_{index}'
        self.sync_all(self.us2cycles(runner.WASHOUT_US))
        if 'loading_final_readout_gain' in self.cfg:
            # Restore weak gain after the preceding trial's strong final readout.
            self.regwi(self.ch_page(self.cfg['res_ch']), self.sreg(self.cfg['res_ch'], 'gain'),
                       int(self.cfg['read_pulse_gain']))
        self.regwi(page, regs['slot'], runner.SLOTS-1)
        self.regwi(page, regs['dose'], self.task['writes'])
        self.label(label+'_SLOT')
        start = self._sync_ticks
        self._fixed_reset(label+'_RESET')
        reset_ticks = self._sync_ticks-start
        self._set_payload_pulse(gain=0)
        self.condj(page, regs['slot'], '<', regs['dose'], label+'_EXCITE')
        self.condj(page, regs['z'], '==', regs['z'], label+'_VISIT')
        self.label(label+'_EXCITE')
        self.regwi(page, self.sreg(self.cfg['qubit_ch'], 'gain'), int(self.cfg['qubit_pi_gain']))
        self.label(label+'_VISIT')
        _pulse_pi_and_align(self)
        prep_ticks = self._sync_ticks-start-reset_ticks
        load_start = self._sync_ticks
        self._wait_t1_payload(runner.LOAD_US)
        visit_ticks = self._sync_ticks-load_start
        cycle_ticks = self._sync_ticks-start
        self.loopnz(page, regs['slot'], label+'_SLOT')
        # No bank handoff or passive washout occurs inside the train.
        start = self._sync_ticks
        self._fixed_reset(label+'_FINAL')
        final_reset_ticks = self._sync_ticks-start
        self._set_payload_pulse(gain=0)
        _pulse_pi_and_align(self)
        original = self.cfg['ff_gain']
        self.cfg['ff_gain'] = self.cfg['loading_probe_gain']
        try:
            self._wait_t1_payload(probe_us)
        finally:
            self.cfg['ff_gain'] = original
        if self.task.get('reference_state') is not None:
            self._set_payload_pulse(gain=self.cfg['qubit_pi_gain'] if self.task['reference_state']=='e' else 0)
            _pulse_pi_and_align(self)
        if 'loading_final_readout_gain' in self.cfg:
            self.regwi(self.ch_page(self.cfg['res_ch']), self.sreg(self.cfg['res_ch'], 'gain'),
                       int(self.cfg['loading_final_readout_gain']))
        self._measure_raw()
        self._save_iq()
        self.sync_all(self.us2cycles(runner.GUARD_US))
        us = lambda ticks: float(self.cycles2us(ticks))
        self.timing.update(reset_us=us(reset_ticks), load_cycle_us=us(cycle_ticks),
                           load_excursion_us=us(visit_ticks),
                           nominal_write_train_us=runner.SLOTS*us(cycle_ticks),
                           last_load_end_to_probe_start_us=40.+us(final_reset_ticks+prep_ticks),
                           timing_note='scheduled target interval includes 0.5 us arrival; excludes host transport between complete trials')

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        if self._t1_ff_compensation is None:
            raise ValueError('native flux compensation is required')
        self.reset_page = self.ch_page(self.cfg['qubit_ch'])
        self.reset_regs = allocate_named_registers(
            self, self.reset_page, ('i','q','z','status','address','threshold','slot','dose'))
        reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self, 0, resident_control_names(self.cfg, ('shot_loop','done')), reserved=reserved)
        self.regwi(self.reset_page, self.reset_regs['address'], self.record_base)
        self.regwi(0, controls['done'], 0)
        self.memwi(0, controls['done'], self.done_addr)
        self.regwi(0, controls['shot_loop'], int(self.task['shots'])-1)
        count = len(self.task['probes_us'])
        self._initialize_stream(controls, total_shots=self.task['shots'], records_per_shot=count,
                                total_units=self.task['shots'], records_per_unit=count, prefix='LOAD_STREAM')
        self._begin_park_lifecycle()
        self.label('LOAD_SHOT_LOOP')
        for index, probe in enumerate(self.task['probes_us']):
            self._cell(index, probe)
        self.mathi(0, controls['done'], controls['done'], '+', count)
        self.memwi(0, controls['done'], self.done_addr)
        self._stream_after_shot()
        self.loopnz(0, controls['shot_loop'], 'LOAD_SHOT_LOOP')
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


class LoadingFeedbackCheckProgram(OPXResetT1Program):
    """Park-only test of the loading reset, with an independent final readout."""

    record_words = 12  # five weak readouts plus the final strong readout
    _fixed_reset = RepeatedLoadingProgram._fixed_reset
    _save_iq = RepeatedLoadingProgram._save_iq

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        from .TLSRepeatedLoadingFeedbackCheck import checked_readout_gain
        if cfg.get('do_ff') or not cfg.get('opx_persistent_park') or not cfg.get('opx_hard_flux_steps'):
            raise ValueError('feedback check requires persistent hard park without excursions')
        checked_readout_gain(cfg.get('read_pulse_gain'))
        if cfg.get('ff_park_gain') != -25146:
            raise ValueError('feedback check requires q3 park')
        if cfg['check_initial_state'] not in ('g', 'e') or cfg.get('check_reference_state') not in (None, 'g', 'e'):
            raise ValueError('unknown feedback-check preparation')
        expected_gain = cfg['qubit_pi_gain'] if cfg['check_feedback'] else 0
        if cfg.get('reset_pi_gain') != expected_gain:
            raise ValueError('feedback and sham must use their specified correction gains')
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def decode_dmem_records(self, words, expected_records=None):
        from .TLSRepeatedLoadingFeedbackCheck import decode_records
        return decode_records(words, expected_records)

    def _emit_body(self):
        # The base benchmark reserves a ground-threshold scratch register;
        # this fixed-reset helper uses it for its single branch threshold.
        self.reset_regs['threshold'] = self.reset_regs['ground']
        self.sync_all(self.us2cycles(self.reset_config.inter_shot_delay_us))
        self._set_payload_pulse(gain=self.cfg['qubit_pi_gain'] if self.cfg['check_initial_state']=='e' else 0)
        _pulse_pi_and_align(self)
        ro_page, ro_gain = self.ch_page(self.cfg['res_ch']), self.sreg(self.cfg['res_ch'], 'gain')
        self.regwi(ro_page, ro_gain, self.cfg['read_pulse_gain'])
        self._fixed_reset('CHECK_RESET')
        # A matched zero/pi slot supplies independent final-readout references.
        self._set_payload_pulse(gain=self.cfg['qubit_pi_gain'] if self.cfg.get('check_reference_state')=='e' else 0)
        _pulse_pi_and_align(self)
        self.regwi(ro_page, ro_gain, 1880)
        self._measure_raw()
        self._save_iq()
        self.sync_all(self.us2cycles(runner.GUARD_US))
