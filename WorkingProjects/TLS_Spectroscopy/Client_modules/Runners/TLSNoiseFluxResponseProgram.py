"""Finite, explicitly timed QICK programs for the even-phase diagnostic."""
import numpy as np


def issue_cycles(instructions):
    # tProc-v1 ctrl.sv DECODE plus REGWI0 / SET0..2 / MATHI0..3.
    # Large frequency/phase words expand to bitwi and mathi in QICK safe_regwi.
    costs={'regwi':2,'set':4,'bitwi':5,'mathi':5}
    if any(i['name'] not in costs for i in instructions):
        raise ValueError('unverified opcode in phase-response queue')
    return sum(costs[i['name']] for i in instructions)


def make_program_class():
    from . import TLSNoiseFluxResponse as runner
    from . import TLSPumpProbeResidentDrive as resident
    from . import TLSPumpProbeShotAlternating as alternating
    from ..Helpers import ff_pulse
    from ..Helpers.PulseFunctions import ff_maxv

    class ResponseProgram(alternating.ShotAlternatingResidentProgram):
        def __init__(self,soccfg,base,task,payload,loop,*,center_gain):
            self.task=dict(task)
            self.logical_shots=int(task['shots'])
            if self.logical_shots<2 or task['conditions']!=runner.conditions(task['kind'],task['block']):
                raise ValueError('unexpected phase-reference schedule')
            self.condition_cfgs=[]
            for condition in task['conditions']:
                arm=dict(flux_ghz=runner.TARGET_GHZ,drive_mhz=runner.DRIVE_MHZ,
                         gain=0,preparation_state='g',pre_drive_us=runner.PRE_US,
                         post_drive_us=runner.POST_US,shots=self.logical_shots)
                cfg=resident.arm_config(base,arm,{runner.TARGET_GHZ:int(center_gain)})
                cfg['response_condition']=condition
                self.condition_cfgs.append(cfg)
            cfg=dict(self.condition_cfgs[0],reps=len(self.condition_cfgs)*self.logical_shots)
            resident.ResidentDriveProgram.__init__(self,soccfg,cfg,payload,loop)

        def _declare_experiment(self):
            super()._declare_experiment()
            cfg=self.cfg
            gen=self.soccfg['gens'][cfg['ff_ch']]
            fabric=gen['f_fabric']
            if (gen['type']!='axis_signal_gen_v4' or
                    not np.isclose(fabric,self.soccfg['fs_proc']) or
                    not np.isclose(fabric,self.soccfg['gens'][cfg['qubit_ch']]['f_fabric'])):
                raise ValueError('requires verified equal generator and tProc clocks')
            self.timing_report=runner.timing(fabric)
            t=self.timing_report
            self.parts=resident.resident_segments(
                self._t1_ff_compensation,pre_us=runner.PRE_US+self._t1_ff_settle_us,
                pulse_us=t['window_cycles']/fabric,post_us=runner.POST_US,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            level=self.parts[0][-1][0]
            dc=round(cfg['ff_park_gain']+level*(cfg['ff_gain']-cfg['ff_park_gain']))
            self.waveforms={}
            self.segments={}
            t.update(dc_gain=dc,conditions={},sample_units='one fabric clock per saved DAC code')
            for c in self.task['conditions']:
                pattern=self.task['kind'] if c['state']=='phase' and self.task['kind'] in ('static','fast') else 'off'
                offset=runner.offset_waveform(t,pattern,self.task['amplitude'] if pattern!='off' else 0,
                                              c['polarity'] if pattern!='off' else 0,
                                              self.task['placement'],seed=self.task['seed'])
                wave=dc+offset
                if np.max(np.abs(wave))>min(ff_maxv(self,scaled=True),32767):
                    raise ValueError('flux waveform clips')
                edges=np.r_[0,np.flatnonzero(np.diff(wave))+1,len(wave)]
                segments=[(int(wave[a]),int(b-a),int(a)) for a,b in zip(edges[:-1],edges[1:])]
                self.waveforms[c['name']]=wave
                self.segments[c['name']]=segments
                t['conditions'][c['name']]={'flux_segments_gain_length_start':segments}

        def _resident_excursion(self):
            cfg=self.cfg;c=cfg['response_condition'];t=self.timing_report
            park,target=cfg['ff_park_gain'],cfg['ff_gain']
            before,after,recovery=self.parts
            ff_pulse.play_relative_compensation_segments(self,park,target,before)
            self.sync_all(0)
            first=len(self.prog_list)
            # Queue the unchanged initial DC level, then the microwave pulses,
            # then the remaining flux edges before the first offset begins.
            def flux(segment):
                gain,length,start=segment
                self.set_pulse_registers(ch=cfg['ff_ch'],style='const',freq=0,phase=0,
                                         gain=gain,length=length,stdysel='last')
                self.pulse(ch=cfg['ff_ch'],t=start)
            flux(self.segments[c['name']][0])
            half,full=t['pi2_cycles'],t['pi_cycles']
            finish=t['pulse_starts'][-1]+half
            pulses=[]
            if c['state']=='phase':
                if self.task['kind']=='pulse_control':
                    pulses=[(finish-2*half-4,half,0),(finish-half,half,c['phase'])]
                else:
                    pulses=list(zip(t['pulse_starts'],t['pulse_lengths'],(0,90,c['phase'])))
            elif c['state'] in ('e','half','two_pi'):
                length={'e':full,'half':half,'two_pi':2*full}[c['state']]
                pulses=[(finish-length,length,0)]
            for start,length,phase in pulses:
                self.set_pulse_registers(ch=cfg['qubit_ch'],style='const',
                    freq=self.freq2reg(runner.DRIVE_MHZ,gen_ch=cfg['qubit_ch']),
                    phase=self.deg2reg(phase,gen_ch=cfg['qubit_ch']),gain=30000,length=length)
                self.pulse(ch=cfg['qubit_ch'],t=start)
            microwave_issue=issue_cycles(self.prog_list[first:])
            if microwave_issue+16>t['lead_cycles']:
                raise ValueError('microwave queue exceeds verified lead-time budget')
            for segment in self.segments[c['name']][1:]:flux(segment)
            issue=issue_cycles(self.prog_list[first:])
            deadline=(self.segments[c['name']][1][2] if len(self.segments[c['name']])>1 else t['lead_cycles'])
            if issue+16>deadline:
                raise ValueError('flux queue exceeds first-offset deadline')
            t['conditions'][c['name']].update(microwave_start_length_phase=pulses,issue_cycles=issue,
                microwave_issue_cycles=microwave_issue,first_flux_edge_deadline=deadline,
                issue_margin_cycles=min(t['lead_cycles']-microwave_issue,deadline-issue))
            self.sync_all(0)
            ff_pulse.play_relative_compensation_segments(self,park,target,after)
            ff_pulse.play_relative_compensation_segments(self,park,target,recovery)
            ff_pulse.play_hard_step(self,park)
            self.sync_all(0)

    return ResponseProgram
