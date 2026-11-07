"""Real binary serialization, finite numbers, statuses and failed-run evidence."""
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import pytest
BINARY = Path(os.environ.get('ACTUATOR_CACHE', Path.home()/'.cache/job-apps-runtime/actuator-lab'))/'build/actuator_lab'
GATES = ('speed_gate', 'current_clamp', 'voltage_clamp', 'trip')
def run(path, *args):
    proc = subprocess.run([str(BINARY), 'simulate', '--output', str(path), *map(str,args)], capture_output=True, text=True, timeout=15)
    summary = json.loads((path/'summary.json').read_text(), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    return proc, summary, summary['observational_metrics']
@pytest.mark.parametrize('ticks,status,time', [(200,'settled',0),(199,'insufficient_horizon',None)])
def test_real_cli_horizon_boundary(tmp_path,ticks,status,time):
    proc,s,m = run(tmp_path/'run','--ticks',ticks,'--target',0)
    assert proc.returncode == 0,proc.stderr
    assert m['schema_version']==1
    assert m['tracking_settling_status']==status and m['tracking_settling_time_s']==time
    assert m['completed_steps']==s['completed_steps']==ticks*20
    assert m['observation_step_s']==.0005
    assert m['observed_duration_s']==pytest.approx(ticks*.01)
    assert m['planned_duration_s']==pytest.approx(ticks*.01)
    assert m['last_violating_step'] is None and m['qualifying_tail_start_step']==0
    for gate in GATES:
        assert m['gate_durations_s'][gate]==m['gate_fractions'][gate]==0
    assert m['supplied_energy_J']==m['regenerated_energy_J']==m['net_electrical_work_J']==m['energy_split_residual_J']==0

def test_real_cli_preserves_aborted_prefix_and_denominator(tmp_path):
    proc,s,m = run(tmp_path/'run','--scenario','fixed','--ticks',12000,'--fixed-voltage',12,'--external',.05)
    assert proc.returncode==3 and s['aborted'] and not s['success']
    assert m['tracking_settling_status']=='incomplete' and m['tracking_settling_time_s'] is None
    assert 0<m['completed_steps']==s['completed_steps']<240000
    duration=m['completed_steps']*m['observation_step_s']
    assert m['observed_duration_s']==duration<m['planned_duration_s']
    for gate in GATES:
        assert m['gate_fractions'][gate]==m['gate_durations_s'][gate]/duration
    rows=list(csv.DictReader((tmp_path/'run/trace.csv').open()))
    assert m['net_electrical_work_J']==float(rows[-1]['W_e'])
    assert s['events'][-1].startswith('abort@step')
    assert abs(m['energy_split_residual_J'])<=1e-10*max(1,m['supplied_energy_J']+m['regenerated_energy_J'])
    assert all(math.isfinite(m[k]) and m[k]>=0 for k in ('supplied_energy_J','regenerated_energy_J','observed_duration_s'))

def test_real_cli_gates_exclude_terminal_row(tmp_path):
    proc,s,m = run(tmp_path/'run','--scenario','stuck_positive','--ticks',600)
    assert proc.returncode==0 and s['tripped']
    rows=list(csv.DictReader((tmp_path/'run/trace.csv').open()))
    for gate in GATES:
        intervals=sum(int(row[gate]) for row in rows[:-1])
        assert m['gate_durations_s'][gate]==pytest.approx(intervals*.01)
        assert m['gate_fractions'][gate]==pytest.approx(intervals/600)
    assert m['net_electrical_work_J']==float(rows[-1]['W_e'])
    assert m['supplied_energy_J']>0
