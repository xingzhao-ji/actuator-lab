"""Audit boundaries: corrupt inputs, dropped slots, altered physics, partial ledgers."""
import copy
import importlib
import json
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))


def module(name='measurements'):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pytest.fail(f'{name} implementation is missing')


def plan():
    return module().make_plan(ROOT / 'evidence')


def summary():
    c = {'Tc': 1.0, 'ticks': 3, 'substeps': 2}
    m = dict(schema_version=1, units={'time': 's', 'energy': 'J', 'gate_fraction': 'dimensionless'},
             tracking_settling_status='settled', tracking_settling_time_s=0.5,
             observation_step_s=0.5, completed_steps=6, observed_duration_s=3.0,
             planned_duration_s=3.0, supplied_energy_J=2.0, regenerated_energy_J=0.5,
             net_electrical_work_J=1.5, energy_split_residual_J=0.0,
             last_violating_step=0, qualifying_tail_start_step=1,
             gate_durations_s={'speed_gate': 1.5, 'current_clamp': 0., 'voltage_clamp': 0., 'trip': 0.},
             gate_fractions={'speed_gate': 0.5, 'current_clamp': 0., 'voltage_clamp': 0., 'trip': 0.})
    return {'config': c, 'aborted': False, 'completed_steps': 6, 'success': False,
            'events': ['schedule@1'], 'observational_metrics': m}


def test_plan_full_denominator_order_and_negative_outcomes():
    p = plan()
    assert len(p['slots']) == 213
    assert [s['id'] for s in p['slots'][:4]] == ['named/nominal/direct', 'named/nominal/cascaded', 'named/nominal/feedforward', 'named/pulse/direct']
    assert p['slots'][-1]['id'] == 'mc/63/feedforward'
    assert [sum(s['legacy']['success'] for s in p['slots'] if s['cohort'] == 'mc' and s['controller'] == c)
            for c in ('direct', 'cascaded', 'feedforward')] == [0, 64, 10]
    assert len([s for s in p['slots'] if s['cohort'] == 'named' and s['case'] == 'stuck_positive' and not s['legacy']['success']]) == 3


@pytest.mark.parametrize('filename', ['frozen-inputs.json', 'results.json'])
def test_wrong_historical_hash_rejected(tmp_path, filename):
    for name in ('frozen-inputs.json', 'results.json'):
        (tmp_path / name).write_bytes((ROOT / 'evidence' / name).read_bytes())
    with (tmp_path / filename).open('ab') as f:
        f.write(b' ')
    with pytest.raises(ValueError, match='identity'):
        module().make_plan(tmp_path)


@pytest.mark.parametrize('damage', ['duplicate', 'missing', 'order', 'legacy'])
def test_plan_tampering_rejected(damage):
    p = plan()
    if damage == 'duplicate': p['slots'][1] = copy.deepcopy(p['slots'][0])
    if damage == 'missing': p['slots'].pop()
    if damage == 'order': p['slots'][0], p['slots'][1] = p['slots'][1], p['slots'][0]
    if damage == 'legacy': p['slots'][0]['legacy']['events'] = ['invented@0']
    with pytest.raises(ValueError):
        module().validate_plan(p, ROOT / 'evidence')


def test_config_argv_includes_stored_zeroes():
    s = plan()['slots'][0]
    args = module().config_argv(s['config'])
    opts = dict(zip(args[::2], args[1::2]))
    assert opts['--theta0'] == '0'
    assert opts['--ww0'] == '0'
    assert opts['--substeps'] == '20'
    assert set(opts) == {'--scenario', '--controller', '--ticks', '--substeps', '--Tc', '--target', '--pulse', '--fixed-voltage', '--external', '--fault-voltage', '--drag-multiplier', '--Jb', '--Jw', '--R', '--L', '--k', '--b', '--theta0', '--wb0', '--ww0', '--i0'}


@pytest.mark.parametrize('damage', ['legacy', 'events', 'trace'])
def test_exact_parity_including_event_ledger(damage):
    s = summary(); expected = {k: v for k, v in s.items() if k != 'observational_metrics'}
    actual = copy.deepcopy(s)
    trace_hash = 'a' * 64
    if damage == 'legacy': actual['success'] = True
    if damage == 'events': actual['events'] = []
    if damage == 'trace': trace_hash = 'b' * 64
    with pytest.raises(ValueError):
        module().validate_parity(actual, expected, trace_hash, 'a' * 64)


@pytest.mark.parametrize('key,value', [('supplied_energy_J', -1.), ('regenerated_energy_J', float('nan')),
    ('observed_duration_s', float('inf')), ('completed_steps', True), ('supplied_energy_J', '2'),
    ('tracking_settling_time_s', 2.5), ('energy_split_residual_J', 1.), ('observation_step_s', 0.)])
def test_invalid_metrics_rejected(key, value):
    s = summary(); s['observational_metrics'][key] = value
    with pytest.raises(ValueError): module().validate_metrics(s)


def test_zero_duration_fraction_must_be_null():
    s = summary(); m = s['observational_metrics']
    s.update(aborted=True, completed_steps=0)
    m.update(completed_steps=0, observed_duration_s=0., tracking_settling_status='incomplete', tracking_settling_time_s=None,
             supplied_energy_J=0., regenerated_energy_J=0., net_electrical_work_J=0., last_violating_step=0, qualifying_tail_start_step=None)
    m['gate_durations_s'] = dict.fromkeys(m['gate_durations_s'], 0.)
    m['gate_fractions'] = dict.fromkeys(m['gate_fractions'], None)
    module().validate_metrics(s)
    m['gate_fractions']['speed_gate'] = 0.
    with pytest.raises(ValueError): module().validate_metrics(s)


def test_gate_occupancy_terminal_row_and_partial_interval():
    rows = [dict(time=0., speed_gate=1, current_clamp=0, voltage_clamp=0, trip=0),
            dict(time=1., speed_gate=0, current_clamp=1, voltage_clamp=0, trip=0),
            dict(time=1.5, speed_gate=0, current_clamp=1, voltage_clamp=1, trip=1)]
    assert module().gate_occupancy(rows, 1.5) == {'speed_gate': 1., 'current_clamp': .5, 'voltage_clamp': 0., 'trip': 0.}
    with pytest.raises(ValueError): module().gate_occupancy(rows, 2.)


def test_interrupted_and_malformed_ledgers_keep_all_slots(tmp_path):
    p = plan(); ledger = tmp_path / 'events.jsonl'
    ledger.write_text('{"slot_id":"named/nominal/direct","status":"error","error":"retained"}\n{"slot_id":')
    result = module().finalize(p, ledger)
    assert len(result['slots']) == 213
    assert result['counts'] == {'complete': 0, 'error': 1, 'missing': 212, 'invalid': 0}
    assert result['complete'] is False
    assert result['ledger_errors'][0]['raw'] == '{"slot_id":'
    assert result['slots'][0]['status'] == 'error'
    assert result['slots'][-1]['status'] == 'missing'
    assert [sum(s['legacy']['success'] for s in result['slots'] if s['cohort'] == 'mc' and s['controller'] == c) for c in ('direct', 'cascaded', 'feedforward')] == [0, 64, 10]


def test_duplicate_and_out_of_order_events_reject_completion(tmp_path):
    p = plan(); ledger = tmp_path / 'events.jsonl'
    ledger.write_text('\n'.join(json.dumps({'slot_id': p['slots'][i]['id'], 'status': 'error'}) for i in (1, 0, 0)) + '\n')
    r = module().finalize(p, ledger)
    assert not r['complete']
    assert len(r['slots']) == 213
    assert r['ledger_errors']


def test_forged_complete_event_cannot_count_as_valid(tmp_path):
    p = plan(); ledger = tmp_path / 'events.jsonl'
    ledger.write_text('{"slot_id":"named/nominal/direct","status":"complete"}\n')
    r = module().finalize(p, ledger)
    assert r['counts'] == {'complete': 0, 'error': 0, 'missing': 212, 'invalid': 1}


@pytest.mark.parametrize('voltage,i0,supply,regen', [
    (2., 0., 2.*(1.-(1.-math.exp(-2.))/2.), 0.),
    (2., -1., 2.*(1.-(1.-math.exp(-2.))) + (1.-math.log(2.)), 1.-math.log(2.)),
    (0., 1., 0., 0.),
])
def test_independent_reference_analytic_electrical_transient(voltage, i0, supply, regen):
    # R=2,L=1,k=0: i(t)=V/2+(i0-V/2)exp(-2t); crossing at log(2)/2.
    r = module('metric_reference').integrate_interval([0., 0., 0., i0, 0., 0.],
        {'Jb': .05, 'Jw': .001, 'R': 2., 'L': 1., 'k': 0., 'b': 0.},
        voltage, 0., 1., 1., [0., .5, 1.])
    assert r[-1, 4] == pytest.approx(supply, abs=2e-10)
    assert r[-1, 5] == pytest.approx(regen, abs=2e-10)
    assert r[-1, 3] == pytest.approx(voltage/2 + (i0-voltage/2)*math.exp(-2.), abs=1e-10)


def test_reference_absolute_mechanics():
    r = module('metric_reference').integrate_interval([0., 1., 3., 0., 0., 0.],
        {'Jb': 2., 'Jw': 1., 'R': 2., 'L': 1., 'k': 0., 'b': 0.},
        0., 4., 1., 1., [0., 1.])
    assert r[-1, :4] == pytest.approx([2., 3., 3., 0.], abs=1e-10)


def test_reference_tracking_last_violation_and_short_tail():
    fn = module('metric_reference').tracking
    assert fn([False, True, True, True, True], .5, False) == {'status': 'not_settled', 'time_s': None, 'last_violating_step': 0, 'tail_start_step': 1}
    assert fn([True]*5, .5, False)['time_s'] == 0.
    assert fn([True]*4, .5, False)['status'] == 'insufficient_horizon'
    assert fn([True]*5, .5, True)['status'] == 'incomplete'


def test_finalizer_rejects_nonfinite_and_truncated_complete_json(tmp_path):
    p = plan(); ledger = tmp_path/'events.jsonl'
    ledger.write_text('{"slot_id":"named/nominal/direct","status":"error","value":NaN}\n')
    r = module().finalize(p, ledger)
    assert r['counts']['missing'] == 213 and not r['complete']
    ledger.write_text('{"slot_id":"named/nominal/direct","status":"error"}')
    r = module().finalize(p, ledger)
    assert r['counts']['missing'] == 213 and r['ledger_errors']


def test_actual_binary_boundary_argv_metrics_and_audit(tmp_path):
    import os
    m = module(); s = copy.deepcopy(plan()['slots'][0])
    s['config']['ticks'] = 1
    s['config_sha256'] = m.sha(m.encoded(s['config']))
    binary = Path(os.environ['ACTUATOR_CACHE'])/'build/actuator_lab'
    record, raw = m.invoke(binary, s, tmp_path, {'binary_sha256': m.BINARY_SHA256})
    m.validate_record(record, s, parity=False)
    assert record['summary']['completed_steps'] == 20
    assert record['summary']['observational_metrics']['tracking_settling_status'] == 'insufficient_horizon'
    assert len((raw/'trace.csv').read_text().splitlines()) == 3
    assert record['exact_command_sha256'] == m.sha((tmp_path/'command-0.json').read_bytes())
    assert record['summary']['config'] == s['config']


def test_report_preserves_named_mc_denominators_and_counts():
    slots = plan()['slots']
    for slot in slots:
        slot['status'] = 'complete'
        slot['record'] = {'summary': {**slot['legacy'], 'observational_metrics': summary()['observational_metrics']}}
    result = module('metric_report').summarize({'complete': True, 'denominator': 213, 'slots': slots})
    assert result['named']['direct']['denominator'] == 7
    assert result['mc']['cascaded']['denominator'] == 64
    assert [result['mc'][c]['legacy_success'] for c in ('direct', 'cascaded', 'feedforward')] == [0, 64, 10]
    assert result['mc']['feedforward']['settling_counts']['settled'] == 64
    assert result['mc']['direct']['supplied_energy_J_median'] == 2.
    assert result['mc']['direct']['regenerated_energy_J_median'] == .5


def test_reference_interrupted_finalizer_preserves_nine_slots(tmp_path):
    ledger = tmp_path/'reference.jsonl'
    ledger.write_text('{"slot_id":"named/nominal/direct","status":"error","error":"stop"}\n{"slot_id":')
    p = {'denominator': 9, 'slots': ['named/'+case+'/'+c for case in ('nominal', 'bias', 'stuck_positive') for c in ('direct', 'cascaded', 'feedforward')]}
    r = module('metric_reference').finalize_reference(p, ledger)
    assert len(r['slots']) == 9 and not r['complete']
    assert r['slots'][0]['status'] == 'error'
    assert sum(s['status'] == 'missing' for s in r['slots']) == 8
    assert r['ledger_errors'][0]['raw'] == '{"slot_id":'
