"""q4 phase-cycled Hahn echo with the established native active reset."""
import math

from .Q4RepeatedT1 import reuse_reset_waveform
from .Q4RepeatedT2E import echo_pulse_starts
from ..active_reset_OPX.programs import OPXResetT1SweepProgram, emit_payload_reset_shot


class Q4EchoSweepProgram(OPXResetT1SweepProgram):
    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        self.echo_timing = []
        if cfg.get('do_ff') or cfg.get('ff_park_gain') != 0:
            raise ValueError('q4 echo requires zero flux and no excursion')
        frequency=float(cfg.get('qubit_pi_freq',math.nan))
        if not math.isfinite(frequency) or abs(frequency-4367.760)>.1 or cfg.get('read_pulse_freq') != 7026.520:
            raise ValueError('q4 pulse/readout frequencies required')
        if cfg.get('q4_echo_refocus_count',1) not in (1,2):raise ValueError('invalid refocusing pulse count')
        if not 0<=float(cfg.get('q4_echo_refocus_gap_us',.1))<=1:raise ValueError('invalid refocusing gap')
        if any(not 0<int(cfg[key])<=32000 for key in ('qubit_pi_gain','qubit_pi2_gain')):
            raise ValueError('echo gains must remain in 1..32000')
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
            count=self.cfg.get('q4_echo_refocus_count',1)
            starts=echo_pulse_starts(envelope_ticks,self.us2cycles(delay_us/2),count,
                                    self.us2cycles(self.cfg.get('q4_echo_refocus_gap_us',.1)))
            refocus_gain=self.cfg['qubit_pi2_gain'] if count==2 else self.cfg['qubit_pi_gain']
            self.regwi(page, gain_reg, refocus_gain)
            # Both halves of the split pi rotation have the same Y axis.
            # Large 32-bit phase words require the safe write path.
            self.safe_regwi(page, phase_reg, self.deg2reg(90, gen_ch=ch))
            for start in starts[1:-1]:self.pulse(ch=ch,t=start)
            self.regwi(page, gain_reg, self.cfg['qubit_pi2_gain'])
            self.safe_regwi(page, phase_reg, self.deg2reg(phase, gen_ch=ch))
            self.pulse(ch=ch, t=starts[-1])
            self.sync_all(self.us2cycles(.01))
            self.echo_timing.append(dict(requested_free_us=delay_us, analysis_phase_deg=phase,
                free_us=float(self.cycles2us(2*(starts[1]-envelope_ticks))),
                envelope_us=float(self.cycles2us(envelope_ticks)),
                pulse_start_ticks=starts,refocus_pulse_count=count,refocus_gain=refocus_gain,
                refocus_block_us=float(self.cycles2us(starts[-2]-starts[1]+envelope_ticks)),
                center_to_center_us=float(self.cycles2us(starts[-1]))))

        emit_payload_reset_shot(self, page=self.reset_page, regs=self.reset_regs,
            reset_scheme='opx_unbounded', payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration, park_up=park_up, park_down=park_down,
            emit_payload=echo, measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg['qubit_ch']),
            label_prefix=f'Q4_ECHO_{point_index}', wait_reset_ringdown=self._wait_reset_ringdown)
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))
