import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"python"))
from reference import DEFAULT,exact_constant,reference_integrate,reference_command

def config(**kwargs):
    return dict(plant=DEFAULT.copy(),initial=[0]*9,Tc=.01,ticks=10,target=0,scenario="fixed",controller="cascaded",pulse=.01,fixed_voltage=1,external=0,fault_voltage=12,drag_multiplier=30,**kwargs)

def test_matrix_reference_matches_independent_RL_analytic():
    p=dict(DEFAULT,k=0,b=0);x=np.zeros(9);x[3]=.1
    v=exact_constant(x,p,1,0,.025)
    np.testing.assert_allclose(v[:3],0,atol=1e-14)
    assert v[3]==pytest.approx(.5-.4*np.exp(-5),abs=1e-13)

def test_matrix_reference_matches_external_acceleration():
    p=dict(DEFAULT,k=0,b=0);x=np.zeros(9);x[:3]=[.3,.1,3]
    y=exact_constant(x,p,0,.005,1)
    np.testing.assert_allclose(y,[.45,.2,3,0],atol=1e-13)

def test_reduced_reference_rest_and_external_work_identity():
    c=config();c.update(fixed_voltage=0,external=.005,ticks=100);c["plant"]=dict(DEFAULT,k=0,b=0);c["initial"][1]=.1
    r=reference_integrate(c);x=r["states"][-1]
    assert x[0]==pytest.approx(.15,abs=1e-12)
    assert x[1]==pytest.approx(.2,abs=1e-12)
    assert x[7]==pytest.approx(.00075,abs=1e-12)
    assert x[8]==pytest.approx(.005,abs=1e-12)

def test_reference_controller_catches_wrong_command_sign():
    c=config();c.update(scenario="nominal",controller="direct",target=.1,ticks=1)
    r=reference_integrate(c)
    assert r["voltage"][0]==pytest.approx(-.48,abs=1e-14)
    assert r["states"][1,0]>0

def test_independent_matrix_and_adaptive_agree_for_coupled_case():
    c=config();c.update(external=.003,ticks=10);c["initial"][:4]=[.1,.2,40,.3]
    exact=exact_constant(c["initial"],c["plant"],1,.003,.1)
    adaptive=reference_integrate(c)["states"][-1,:4]
    np.testing.assert_allclose(adaptive,exact,atol=2e-11,rtol=1e-11)

def test_wrong_sign_fixture_cannot_pass_reference_oracle():
    c=config();c.update(ticks=1)
    correct=reference_integrate(c)["states"][-1,:4]
    mutant=correct.copy();mutant[1]*=-1
    assert np.max(np.abs(mutant-correct))>1e-3

def test_reference_feedforward_does_not_integrate_current_error():
    v,m=reference_command(.1,0,50,0,0,"feedforward",(.2,False),.01)
    assert v==pytest.approx(3,abs=1e-14) and m==(.2,False)
