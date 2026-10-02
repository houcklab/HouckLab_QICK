"""q4 phase-cycled Hahn echo with the established native active reset."""
import math

from .Q4RepeatedT1 import reuse_reset_waveform
from ..active_reset_OPX.programs import OPXResetT1SweepProgram, emit_payload_reset_shot


class Q4EchoSweepProgram(OPXResetT1SweepProgram):
    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        self.echo_timing = []
        if cfg.get('do_ff') or cfg.get('ff_park_gain') != 0:
            raise ValueError('q4 echo requires zero flux and no excursion')
        if cfg.get('qubit_pi_freq') != 4367.760 or cfg.get('read_pulse_freq') != 7026.520:
            raise ValueError('q4 pulse/readout frequencies required')
        delays = cfg['opx_t1_delays_us']
        if len(delays) % 2 or any(delays[k] != delays[k+1] for k in range(0,len(delays),2)):
            raise ValueError('echo requires adjacent phase pairs at equal delays')
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def _declare_experiment(self):
        super()._declare_experiment()
        reuse_reset_waveform(self)

    def _emit_t1_point(self, point_index, delay_us):
        park_up, park_down = self._shot_park_callbacks()
        phase = (0, 180)[point_index % 2]

        def echo():
            ch = self.cfg['qubit_ch']
            page = self.ch_page(ch)
            phase_reg, gain_reg = self.sreg(ch, 'phase'), self.sreg(ch, 'gain')
            self._set_payload_pulse(gain=self.cfg['qubit_pi2_gain'])
            self.pulse(ch=ch, t=0)
            envelope_ticks = float(self._dac_ts[ch])
            # Equal gaps and exactly centered refocusing pulse, including the
            # fractional generator-to-tProcessor clock conversion.
            spacing = math.ceil(envelope_ticks) + self.us2cycles(delay_us/2)
            self.regwi(page, gain_reg, self.cfg['qubit_pi_gain'])
            # This generator has 32-bit phase; 90/180 degrees exceed the
            # tProcessor's direct-immediate range.
            self.safe_regwi(page, phase_reg, self.deg2reg(90, gen_ch=ch))
            self.pulse(ch=ch, t=spacing)
            self.regwi(page, gain_reg, self.cfg['qubit_pi2_gain'])
            self.safe_regwi(page, phase_reg, self.deg2reg(phase, gen_ch=ch))
            self.pulse(ch=ch, t=2*spacing)
            self.sync_all(self.us2cycles(.01))
            self.echo_timing.append(dict(requested_free_us=delay_us, analysis_phase_deg=phase,
                free_us=float(self.cycles2us(2*(spacing-envelope_ticks))),
                envelope_us=float(self.cycles2us(envelope_ticks)),
                pulse_start_ticks=[0, spacing, 2*spacing],
                center_to_center_us=float(self.cycles2us(2*spacing))))

        emit_payload_reset_shot(self, page=self.reset_page, regs=self.reset_regs,
            reset_scheme='opx_unbounded', payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration, park_up=park_up, park_down=park_down,
            emit_payload=echo, measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg['qubit_ch']),
            label_prefix=f'Q4_ECHO_{point_index}', wait_reset_ringdown=self._wait_reset_ringdown)
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))
