import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"python"))
from experiments import aggregate

def test_failures_and_abort_stay_in_paired_denominator():
    pairs=[{"direct":{"success":False,"aborted":True},"cascaded":{"success":True,"aborted":False}},
           {"direct":{"success":True,"aborted":False},"cascaded":{"success":False,"aborted":False}}]
    a=aggregate(pairs)
    assert a["denominator"]==2
    assert a["direct_success"]==a["cascaded_success"]==1
    assert a["direct_aborted"]==1 and a["cascaded_aborted"]==0

def test_missing_pair_is_error_not_denominator_filter():
    with pytest.raises((ValueError,KeyError)):aggregate([{"direct":{"success":False,"aborted":True}}])
