"""Execute emitted branches, including both fixed-point projection signs."""
import operator
import pytest
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import control_flow
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import TerminalStatus


class TraceProgram:
    def __init__(self):
        self.code = []
    def regwi(self, page, reg, value, *comment): self.code.append(('write',reg,value))
    def mathi(self, page, dst, src, op, value): self.code.append(('add',dst,src,value))
    def condj(self, page, a, op, b, label): self.code.append(('jump',a,op,b,label))
    def label(self, label): self.code.append(('label',label))


def execute(decisions, sign, required):
    fit=ClassifierCalibration(1,'payload',0.,0,sign,0,-10,10,100,{})
    regs=dict(z=1,ground=2,excited=3,attempts=4,pi_count=5,status=6)
    p=TraceProgram()
    control_flow.emit_unbounded_reset_state_machine(p,page=0,regs=regs,
        payload_calibration=fit,loop_calibration=fit,
        measure_next=lambda:p.code.append(('measure',)),play_pi=lambda:p.code.append(('pi',)),
        label_prefix='TEST',wait_reset_ringdown=lambda:p.code.append(('wait',)),
        require_loop_readout=required)
    labels={e[1]:i for i,e in enumerate(p.code) if e[0]=='label'}
    state={regs['z']:sign*decisions[0]};i=0;reads=0;pi=0;waits=0
    ops={'<=':operator.le,'>=':operator.ge,'==':operator.eq}
    for _ in range(1000):
        if i==len(p.code): return state[regs['attempts']],pi,reads,waits,state[regs['status']]
        e=p.code[i];i+=1
        if e[0]=='write':state[e[1]]=e[2]
        elif e[0]=='add':state[e[1]]=state[e[2]]+e[3]
        elif e[0]=='jump' and ops[e[2]](state[e[1]],state[e[3]]):i=labels[e[4]]
        elif e[0]=='measure':
            reads+=1;state[regs['z']]=sign*decisions[reads]
        elif e[0]=='pi':pi+=1
        elif e[0]=='wait':waits+=1
    raise AssertionError('branch graph did not terminate')


@pytest.mark.parametrize('sign',[1,-1])
@pytest.mark.parametrize('decisions,ordinary,confirmed',[
    ([-20,-20],(0,0),(1,0)),
    ([-20,30,-20],(0,0),(2,1)),
    ([30,-20],(1,1),(1,1)),
    ([0,-20],(1,0),(1,0)),
    ([-10,-10],(0,0),(1,0)),
    ([10,-10],(1,0),(1,0)),
])
def test_required_loop_readout_changes_only_initial_ground_exit(sign,decisions,ordinary,confirmed):
    for required,expected in [(False,ordinary),(True,confirmed)]:
        attempts,pi,reads,waits,status=execute(decisions,sign,required)
        assert (attempts,pi)==expected
        assert reads==waits==attempts
        assert status==int(TerminalStatus.CONFIRMED_GROUND)


def test_benchmark_forwards_confirmation_and_rejects_unsupported_schemes(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import programs
    p=TraceProgram();seen=[]
    monkeypatch.setattr(programs,'emit_unbounded_reset_state_machine',lambda *a,**kw:seen.append(kw))
    monkeypatch.setattr(programs,'emit_record',lambda *a,**kw:None)
    kwargs=dict(page=0,regs={'initial_z':1,'z':2},preparation=0,payload_calibration=None,
        loop_calibration=None,max_reset_attempts=8,park_up=lambda:None,park_down=lambda:None,
        prepare_excited=lambda:None,measure_project=lambda *a:None,measure_verification=lambda:None,
        play_pi=lambda:None,label_prefix='TEST',require_loop_readout=True)
    programs.emit_benchmark_shot(p,reset_scheme='opx_unbounded',**kwargs)
    assert seen[0]['require_loop_readout'] is True
    for scheme in ['none','opx']:
        with pytest.raises(ValueError,match='unbounded'):
            programs.emit_benchmark_shot(p,reset_scheme=scheme,**kwargs)
