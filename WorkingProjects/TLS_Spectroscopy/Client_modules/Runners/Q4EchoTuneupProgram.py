"""Native reset payloads for the finite q4 pulse diagnostic."""
import math
from .Q4EchoTuneup import payload_pulses
from .Q4RepeatedT1 import reuse_reset_waveform
from ..active_reset_OPX.programs import OPXResetT1SweepProgram,emit_payload_reset_shot


class Q4TuneupProgram(OPXResetT1SweepProgram):
    def __init__(self,soccfg,cfg,payload_calibration,loop_calibration):
        self.timing=[]
        if cfg.get('do_ff') or cfg.get('ff_park_gain')!=0 or cfg.get('read_pulse_freq')!=7026.520:
            raise ValueError('q4 diagnostic requires fixed-frequency q4 settings')
        arms=cfg['q4_tuneup_conditions']
        if not arms or len(arms)!=len(cfg['opx_t1_delays_us']):raise ValueError('condition count mismatch')
        for arm in arms:payload_pulses(arm)
        super().__init__(soccfg,cfg,payload_calibration,loop_calibration)

    def _declare_experiment(self):
        super()._declare_experiment();reuse_reset_waveform(self)

    def _emit_t1_point(self,index,delay_us):
        arm=self.cfg['q4_tuneup_conditions'][index]
        park_up,park_down=self._shot_park_callbacks()
        def payload():
            ch=self.cfg['qubit_ch'];page=self.ch_page(ch);pulses=payload_pulses(arm)
            self._set_payload_pulse(gain=pulses[0][0])
            self.safe_regwi(page,self.sreg(ch,'freq'),self.freq2reg(arm['frequency_mhz'],gen_ch=ch))
            self.pulse(ch=ch,t=0)
            envelope=float(self._dac_ts[ch]);spacing=math.ceil(envelope)+self.us2cycles(arm['delay_us'])
            for k,(gain,phase) in enumerate(pulses[1:],1):
                self.regwi(page,self.sreg(ch,'gain'),gain)
                self.safe_regwi(page,self.sreg(ch,'phase'),self.deg2reg(phase,gen_ch=ch))
                self.pulse(ch=ch,t=k*spacing)
            self.sync_all(self.us2cycles(.01))
            self.timing.append(dict(condition=arm,pulse_start_ticks=[k*spacing for k in range(len(pulses))],
                actual_gap_us=float(self.cycles2us(spacing-envelope)),envelope_us=float(self.cycles2us(envelope)),
                phases_deg=[phase for gain,phase in pulses],gains=[gain for gain,phase in pulses]))
        emit_payload_reset_shot(self,page=self.reset_page,regs=self.reset_regs,
            reset_scheme='opx_unbounded',payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,park_up=park_up,park_down=park_down,
            emit_payload=payload,measure_project=self._measure_project,prepare_reset=self._set_reset_pulse,
            play_pi=lambda:self.pulse(ch=self.cfg['qubit_ch']),label_prefix=f'Q4_TUNE_{index}',
            wait_reset_ringdown=self._wait_reset_ringdown)
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))
