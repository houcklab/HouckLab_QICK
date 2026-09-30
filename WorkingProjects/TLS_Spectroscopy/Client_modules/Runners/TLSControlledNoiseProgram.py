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
            expected={(p,s) for p in runner.PATTERNS for s in ('g','e')}
            if (self.logical_shots<1 or len(task['conditions'])!=6 or
                    {(c['pattern'],c['state']) for c in task['conditions']}!=expected):
                raise ValueError('noise program requires each of six conditions exactly once')
            self.condition_cfgs=[]
            for c in task['conditions']:
                arm=dict(flux_ghz=task['frequency_ghz'],drive_mhz=task['frequency_ghz']*1000,
                         gain=0,preparation_state=c['state'],reference_state=None,
                         pre_drive_us=runner.PRE_US,post_drive_us=task['hold_us'],shots=self.logical_shots)
                cfg=resident.arm_config(base,arm,{task['frequency_ghz']:int(center_gain)})
                cfg['noise_pattern']=c['pattern']
                self.condition_cfgs.append(cfg)
            run_cfg=dict(self.condition_cfgs[0],reps=6*self.logical_shots)
            resident.ResidentDriveProgram.__init__(self,soccfg,run_cfg,payload,loop)

        def _declare_experiment(self):
            super()._declare_experiment()
            cfg=self.cfg
            if self._t1_ff_compensation is None: raise ValueError('pinned flux correction required')
            g=self.soccfg['gens'][cfg['ff_ch']]
            _,during,_=modulation._target_segments(
                self._t1_ff_compensation,pre_us=runner.PRE_US+self._t1_ff_settle_us,
                hold_us=self.task['hold_us'],recovery_us=40.)
            self.waveforms,self.waveform_report=runner.waveforms(
                segments=during,park_gain=cfg['ff_park_gain'],target_gain=cfg['ff_gain'],
                endpoint_gains=self.endpoint_gains,core_cycles=self.task['core_cycles'],
                fabric_mhz=g['f_fabric'],samples_per_clock=g['samps_per_clk'],
                max_gain=ff_maxv(self,scaled=True),seed=self.task['seed'])
            park=sum(length for ch,_,_,length in self._ff_ramp_cache if ch==cfg['ff_ch'])
            total=park+sum(len(w) for w in self.waveforms.values())
            if total>ff_envelope_samples(self): raise ValueError('noise waveform exceeds envelope memory')
            self.waveform_report['envelope_samples']=total
            self.waveform_report['envelope_capacity']=ff_envelope_samples(self)
            for name,wave in self.waveforms.items():
                self.add_pulse(ch=cfg['ff_ch'],name='noise_'+name,idata=wave,qdata=np.zeros_like(wave))

        def _resident_excursion(self):
            cfg=self.cfg;park,target=cfg['ff_park_gain'],cfg['ff_gain']
            before,_,recovery=modulation._target_segments(
                self._t1_ff_compensation,pre_us=runner.PRE_US+self._t1_ff_settle_us,
                hold_us=self.task['hold_us'],recovery_us=40.)
            ff_pulse.play_relative_compensation_segments(self,park,target,before)
            if cfg['noise_pattern']=='off':
                for gain,length in self.waveform_report['off_segments']:
                    self.set_pulse_registers(ch=cfg['ff_ch'],style='const',freq=0,phase=0,
                                             gain=gain,length=length,stdysel='last')
                    self.pulse(ch=cfg['ff_ch'])
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
