"""QICK compilation for the finite controlled-frequency-noise experiment."""
import numpy as np


def make_program_class():
    from . import TLSControlledNoise as runner
    from . import TLSPumpProbeResidentDrive as resident
    from . import TLSPumpProbeShotAlternating as alternating
    from . import TLSFluxModulatedT1 as modulation
    from ..Helpers import ff_pulse
    from ..Helpers.PulseFunctions import ff_envelope_samples,ff_maxv

    class NoiseProgram(alternating.ShotAlternatingResidentProgram):
        def __init__(self,soccfg,base,task,payload,loop,*,center_gain,endpoint_gains):
            self.task=dict(task)
            self.endpoint_gains=tuple(endpoint_gains)
            self.logical_shots=int(task['shots'])
            paired=bool(task.get('paired_polarity',False))
            if paired and task.get('playback')!='const_segments':
                raise ValueError('paired polarity requires constant-segment long-hold mode')
            expected={(p,s,pol) for p in runner.PATTERNS for s in ('g','e')
                      for pol in (((0,) if p=='off' else (1,-1)) if paired else (1,))}
            if (self.logical_shots<1 or len(task['conditions'])!=len(expected) or
                    {(c['pattern'],c['state'],c.get('polarity',1)) for c in task['conditions']}!=expected):
                raise ValueError('noise program requires each preparation, pattern and polarity exactly once')
            self.condition_cfgs=[]
            for c in task['conditions']:
                arm=dict(flux_ghz=task['frequency_ghz'],drive_mhz=task['frequency_ghz']*1000,
                         gain=0,preparation_state=c['state'],reference_state=None,
                         pre_drive_us=runner.PRE_US,post_drive_us=task['hold_us'],shots=self.logical_shots)
                cfg=resident.arm_config(base,arm,{task['frequency_ghz']:int(center_gain)})
                cfg['noise_pattern']=c['pattern']+('_inverse' if c.get('polarity',1)==-1 and c['pattern']!='off' else '')
                self.condition_cfgs.append(cfg)
            run_cfg=dict(self.condition_cfgs[0],reps=len(self.condition_cfgs)*self.logical_shots)
            resident.ResidentDriveProgram.__init__(self,soccfg,run_cfg,payload,loop)

        def _declare_experiment(self):
            super()._declare_experiment()
            cfg=self.cfg
            if self._t1_ff_compensation is None: raise ValueError('pinned flux correction required')
            g=self.soccfg['gens'][cfg['ff_ch']]
            segmented=self.task.get('playback')=='const_segments'
            if segmented and (g['type']!='axis_signal_gen_v4' or
                              not np.isclose(g['f_fabric'],self.soccfg['fs_proc'])):
                raise ValueError('constant noise playback requires the verified v4 generator/tProc clocks')
            _,during,_=modulation._target_segments(
                self._t1_ff_compensation,pre_us=runner.PRE_US+self._t1_ff_settle_us,
                hold_us=self.task['hold_us'],recovery_us=40.)
            waveform_builder=runner.paired_waveforms if self.task.get('paired_polarity',False) else runner.waveforms
            self.waveforms,self.waveform_report=waveform_builder(
                segments=during,park_gain=cfg['ff_park_gain'],target_gain=cfg['ff_gain'],
                endpoint_gains=self.endpoint_gains,core_cycles=self.task['core_cycles'],
                fabric_mhz=g['f_fabric'],samples_per_clock=g['samps_per_clk'],
                max_gain=ff_maxv(self,scaled=True),seed=self.task['seed'],
                dc_tick_quantum=16 if segmented else 1)
            park=sum(length for ch,_,_,length in self._ff_ramp_cache if ch==cfg['ff_ch'])
            total=park+(0 if segmented else sum(len(w) for w in self.waveforms.values()))
            if total>ff_envelope_samples(self): raise ValueError('noise waveform exceeds envelope memory')
            self.waveform_report['envelope_samples']=total
            self.waveform_report['envelope_capacity']=ff_envelope_samples(self)
            if not segmented:
                for name,wave in self.waveforms.items():
                    self.add_pulse(ch=cfg['ff_ch'],name='noise_'+name,idata=wave,qdata=np.zeros_like(wave))

        def _resident_excursion(self):
            cfg=self.cfg;park,target=cfg['ff_park_gain'],cfg['ff_gain']
            before,_,recovery=modulation._target_segments(
                self._t1_ff_compensation,pre_us=runner.PRE_US+self._t1_ff_settle_us,
                hold_us=self.task['hold_us'],recovery_us=40.)
            ff_pulse.play_relative_compensation_segments(self,park,target,before)
            segmented=self.task.get('playback')=='const_segments'
            if cfg['noise_pattern']=='off' or segmented:
                segments=(self.waveform_report['off_segments'] if cfg['noise_pattern']=='off' else
                          self.waveform_report['pattern_segments'][cfg['noise_pattern']])
                for gain,length in segments:
                    before_instructions=len(self.prog_list)
                    self.set_pulse_registers(ch=cfg['ff_ch'],style='const',freq=0,phase=0,
                                             gain=gain,length=length,stdysel='last')
                    self.pulse(ch=cfg['ff_ch'])
                    if segmented:
                        emitted=self.prog_list[before_instructions:]
                        cycles=runner.const_issue_cycles(emitted)
                        # Five regwi + one set cost 14 clocks. Equal generator/
                        # tProc clocks leave at least two per 16-clock chip.
                        if cycles+2>length:
                            raise ValueError('constant noise segment exceeds tProc issue budget')
                        self.waveform_report['max_const_issue_instructions']=max(
                            self.waveform_report.get('max_const_issue_instructions',0),len(emitted))
                        self.waveform_report['max_const_issue_cycles']=max(
                            self.waveform_report.get('max_const_issue_cycles',0),cycles)
                        self.waveform_report['min_const_issue_margin_cycles']=min(
                            self.waveform_report.get('min_const_issue_margin_cycles',length),length-cycles)
            else:
                self.set_pulse_registers(ch=cfg['ff_ch'],style='arb',freq=0,phase=0,
                                         gain=ff_maxv(self),waveform='noise_'+cfg['noise_pattern'],
                                         outsel='input',stdysel='last')
                self.pulse(ch=cfg['ff_ch'])
            self.sync_all(0)
            ff_pulse.play_relative_compensation_segments(self,park,target,recovery)
            ff_pulse.play_hard_step(self,park)
            self.sync_all(0)

    return NoiseProgram
