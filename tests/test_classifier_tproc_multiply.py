"""tProc-v1 products use signed low 16 bits of BOTH operands, not int32 math."""
import math
from dataclasses import replace
import numpy as np
import pytest
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
    ClassifierCalibration, _fixed_point_coefficients, fit_classifier,
)


def signed16(x):
    return (np.asarray(x,dtype=np.int64)+32768)%65536-32768


@pytest.mark.parametrize('theta',[0.,math.pi,.001,-.001,math.pi/2,-math.pi/2,math.pi/4,-math.pi/4,2.4])
@pytest.mark.parametrize('raw_scale',[100,11000,32767])
def test_emitted_multiply_matches_python_projection(theta,raw_scale):
    shift,c,s=_fixed_point_coefficients(theta,raw_scale)
    f=ClassifierCalibration(1,'loop',theta,shift,c,s,-1,1,raw_scale,{})
    plan=f.assembly_plan()
    assert 0 <= plan['c_abs'] <= 32767 and 0 <= plan['s_abs'] <= 32767
    endpoints=np.array([-raw_scale,-1,0,1,raw_scale])
    i,q=(v.ravel() for v in np.meshgrid(endpoints,endpoints))
    ci=signed16(i)*signed16(plan['c_abs']);sq=signed16(q)*signed16(plan['s_abs'])
    hardware=ci+sq if plan['combine_op']=='+' else ci-sq
    if not plan['excited_above']:hardware=-hardware
    np.testing.assert_array_equal(hardware,f.project(i,q))


def test_axis_aligned_calibration_no_longer_emits_wrapping_32768_coefficient():
    gi=np.linspace(2000,11000,2000,dtype=int);ei=-gi;q=np.zeros_like(gi)
    fit=fit_classifier(gi,q,ei,q,context='loop',ground_confidence_fidelity=.7)
    assert abs(fit.c_int)<=32767
    assert fit.holdout['ground_accept']>.2 and fit.holdout['excited_fire']==1
    assert fit.holdout['false_ground_accept']==0
    assert np.all(fit.project(gi,q)<fit.project(ei,q))


@pytest.mark.parametrize('c,s',[(32768,1),(-32768,1),(1,32768),(1,-32768),(65536,0)])
def test_old_unsafe_calibrations_remain_readable_but_cannot_emit(c,s):
    f=ClassifierCalibration(1,'loop',0.,15,c,s,-1,1,11000,{})
    restored=ClassifierCalibration.from_dict(f.to_dict())
    assert restored.project([1],[0])[0]==c
    with pytest.raises(ValueError,match='16-bit'):
        restored.assembly_plan()


def test_quality_guard_rejects_unsafe_hardware_projection():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import CalibrationBundle,validate_confident_calibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import ReferenceAxis
    safe=ClassifierCalibration(1,'payload',0.,0,1,0,-1,1,11000,{'ground_accept':.8,'excited_fire':.8})
    for unsafe in [replace(safe,c_int=-32768),replace(safe,max_abs_raw=32768)]:
        b=CalibrationBundle(1,safe,unsafe,ReferenceAxis.from_centers(-1,0,1,0),{})
        with pytest.raises(ValueError,match='16-bit'):
            validate_confident_calibration(b)
