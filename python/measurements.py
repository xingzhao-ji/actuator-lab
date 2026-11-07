"""Fixed-cohort metrics replay. No resampling, retries, or historical writes.

All worker artifacts must be staged under ACTUATOR_CACHE. Finalize consumes the
ledger only, preserving missing/error slots and malformed records after a stop.
"""
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

HISTORICAL = {'frozen-inputs.json': 'edfdd50e25169b5fe3b9e840a766bc3f5977a5bf490689104082376c34003159',
              'results.json': 'd69e150d0b2706265f118a8ef56f327c9ef2b45a5404b0f89fd05dea972c4e89'}
BINARY_SHA256 = '1a7bc1f771924f6ace2b2bfeb08cf775e1d242ae85b19da4be09d078b19e2dfd'
GATES = ('speed_gate', 'current_clamp', 'voltage_clamp', 'trip')
ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def write_new(path, value):
    with Path(path).open('xb') as stream:
        stream.write(encoded(value))


def utc():
    return datetime.now(timezone.utc).isoformat()


def checked_json(data):
    def bad(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(data, parse_constant=bad)


def make_plan(evidence):
    evidence = Path(evidence)
    for name, digest in HISTORICAL.items():
        if sha((evidence / name).read_bytes()) != digest:
            raise ValueError('historical identity mismatch: ' + name)
    historical = checked_json((evidence / 'results.json').read_bytes())
    frozen = checked_json((evidence / 'frozen-inputs.json').read_bytes())
    slots = []
    for cohort, key, marker in [('named', 'named', 'scenario'), ('mc', 'monte_carlo', 'id')]:
        for pair in historical[key]:
            # JSON object insertion order is the historical controller order.
            for controller, summary in pair.items():
                if controller == marker:
                    continue
                if controller not in ('direct', 'cascaded', 'feedforward'):
                    raise ValueError('unexpected historical controller')
                legacy = {k: v for k, v in summary.items() if k not in ('summary_sha256', 'trace_sha256')}
                config_argv(summary['config'])  # Reject unreconstructible fields.
                slots.append({'index': len(slots), 'id': f'{cohort}/{pair[marker]}/{controller}',
                              'cohort': cohort, 'case': pair[marker], 'controller': controller,
                              'config': summary['config'], 'config_sha256': sha(encoded(summary['config'])),
                              'legacy': legacy, 'trace_sha256': summary['trace_sha256'],
                              'historical_summary_sha256': summary['summary_sha256']})
    if len(slots) != 213 or len(historical['named']) != 7 or len(historical['monte_carlo']) != 64:
        raise ValueError('fixed denominator mismatch')
    if [p['scenario'] for p in historical['named']] != frozen['named_cases'] or [p['id'] for p in historical['monte_carlo']] != list(range(64)):
        raise ValueError('fixed cohort order mismatch')
    return {'schema_version': 1, 'historical_identities': HISTORICAL, 'denominator': 213,
            'binary_sha256': BINARY_SHA256, 'slots': slots}


def validate_plan(plan, evidence):
    expected = make_plan(evidence)
    if plan.get('mode') == 'sensitivity':
        expected = sensitivity_plan(expected)
    if plan != expected:
        raise ValueError('plan differs from fixed historical ordered slots')


def config_argv(c):
    scalar = ('scenario', 'controller', 'ticks', 'substeps', 'Tc', 'target', 'pulse', 'fixed_voltage', 'external', 'fault_voltage', 'drag_multiplier')
    if set(c) != set(scalar) | {'plant', 'initial'} or set(c['plant']) != {'Jb', 'Jw', 'R', 'L', 'k', 'b'} or len(c['initial']) != 9 or any(c['initial'][4:]):
        raise ValueError('configuration cannot be reconstructed exactly')
    result = []
    for key in scalar:
        result.extend(['--' + key.replace('_', '-'), str(c[key])])
    for key in ('Jb', 'Jw', 'R', 'L', 'k', 'b'):
        result.extend(['--' + key, str(c['plant'][key])])
    for key, value in zip(('theta0', 'wb0', 'ww0', 'i0'), c['initial'][:4]):
        result.extend(['--' + key, str(value)])
    return result


def finite(value, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError('invalid finite numeric metric')
    return value


def close(a, b):
    return abs(a-b) <= 1e-11 * max(1., abs(a), abs(b))


def validate_metrics(summary):
    m, c = summary['observational_metrics'], summary['config']
    if type(m['schema_version']) is not int or m['schema_version'] != 1 or m['units'] != {'time': 's', 'energy': 'J', 'gate_fraction': 'dimensionless'}:
        raise ValueError('metric schema/units mismatch')
    n = m['completed_steps']; h = finite(m['observation_step_s'], 0.)
    if type(n) is not int or n < 0 or n != summary['completed_steps'] or n > c['ticks']*c['substeps'] or h <= 0 or not close(h, c['Tc']/c['substeps']):
        raise ValueError('invalid integration denominator')
    duration, planned = finite(m['observed_duration_s'], 0.), finite(m['planned_duration_s'], 0.)
    if not close(duration, n*h) or not close(planned, c['ticks']*c['Tc']):
        raise ValueError('duration mismatch')
    if type(summary['aborted']) is not bool or (not summary['aborted'] and n != c['ticks']*c['substeps']):
        raise ValueError('completion mismatch')
    for key in ('last_violating_step', 'qualifying_tail_start_step'):
        v = m[key]
        if v is not None and (type(v) is not int or not 0 <= v <= n):
            raise ValueError('invalid tracking index')
    last, tail = m['last_violating_step'], m['qualifying_tail_start_step']
    if ((last is None and tail != 0) or (last == n and tail is not None)
            or (last is not None and last < n and tail != last+1)):
        raise ValueError('inconsistent tracking tail')
    dwell = math.ceil(math.nextafter(2./h, -math.inf))
    expected = ('incomplete' if summary['aborted'] else 'insufficient_horizon' if planned < 2. else
                'settled' if tail is not None and n-tail >= dwell else 'not_settled')
    if m['tracking_settling_status'] != expected:
        raise ValueError('invalid settling status')
    t = m['tracking_settling_time_s']
    if expected == 'settled':
        finite(t, 0.)
        if not close(t, tail*h): raise ValueError('settling time mismatch')
    elif t is not None:
        raise ValueError('nonsettled time must be null')
    supplied, regenerated = finite(m['supplied_energy_J'], 0.), finite(m['regenerated_energy_J'], 0.)
    net, residual = finite(m['net_electrical_work_J']), finite(m['energy_split_residual_J'])
    bound = 1e-10*max(1., supplied+regenerated, abs(net))
    if abs(residual) > bound or abs(supplied-regenerated-net) > bound or not close(residual, supplied-regenerated-net):
        raise ValueError('gross energy split identity failed')
    if set(m['gate_durations_s']) != set(GATES) or set(m['gate_fractions']) != set(GATES):
        raise ValueError('gate schema mismatch')
    for gate in GATES:
        d, f = finite(m['gate_durations_s'][gate], 0.), m['gate_fractions'][gate]
        if d > duration + 1e-12 or not close(d/h, round(d/h)):
            raise ValueError('gate duration outside accepted step count')
        if duration == 0:
            if f is not None: raise ValueError('zero duration fraction must be null')
        else:
            finite(f, 0.)
            if f > 1 or not close(f, d/duration): raise ValueError('gate fraction mismatch')


def validate_parity(actual, legacy, trace_hash, historical_trace_hash):
    old = {k: v for k, v in actual.items() if k != 'observational_metrics'}
    # Python equality treats bool/int as equal; canonical JSON also preserves types.
    if json.dumps(old, sort_keys=True) != json.dumps(legacy, sort_keys=True):
        raise ValueError('legacy summary mismatch')
    if trace_hash != historical_trace_hash:
        raise ValueError('legacy CSV hash mismatch')


def read_trace(data):
    rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(io.StringIO(data.decode()))]
    if not rows or any(not math.isfinite(v) for row in rows for v in row.values()):
        raise ValueError('empty/nonfinite legacy trace')
    return rows


def gate_occupancy(rows, observed_duration):
    if not rows or rows[0]['time'] != 0. or not close(rows[-1]['time'], observed_duration):
        raise ValueError('trace does not cover accepted duration')
    durations = dict.fromkeys(GATES, 0.)
    for left, right in zip(rows, rows[1:]):
        dt = right['time']-left['time']
        if dt <= 0: raise ValueError('trace time is not strictly increasing')
        for gate in GATES:
            if left[gate] not in (0, 1): raise ValueError('invalid held flag')
            durations[gate] += dt*left[gate]
    return durations


def validate_record(record, slot, parity=True):
    summary = record['summary']
    validate_metrics(summary)
    if record['config_sha256'] != sha(encoded(summary['config'])) or summary['config'] != slot['config']:
        raise ValueError('record config mismatch')
    if parity:
        validate_parity(summary, slot['legacy'], record['trace_sha256'], slot['trace_sha256'])
    for gate in GATES:
        if not close(record['csv_gate_durations_s'][gate], summary['observational_metrics']['gate_durations_s'][gate]):
            raise ValueError('independent CSV gate occupancy mismatch')
    if not close(record['csv_final_net_work_J'], summary['observational_metrics']['net_electrical_work_J']):
        raise ValueError('CSV final work mismatch')
    identity = record['identities']
    pinned = BINARY_SHA256
    if identity.get('execution_kind') == 'public_reproduction':
        from public_provenance import validate_schema
        request = validate_schema(identity['public_request'])
        pinned = request['binary_sha256']
        if (any(identity[k] != request['source'][k] for k in ('source_commit', 'source_manifest_sha256', 'source_files'))
                or identity['runtime'] != request['runtime']):
            raise ValueError('record public provenance mismatch')
    if identity['binary_sha256'] != pinned:
        raise ValueError('record binary mismatch')


def append_event(stream, event):
    stream.write(json.dumps(event, allow_nan=False) + '\n')
    stream.flush()
    os.fsync(stream.fileno())


def finalize(plan, ledger):
    slots = [dict(s, status='missing') for s in plan['slots']]
    index = {s['id']: i for i, s in enumerate(slots)}
    seen, errors = set(), []
    if Path(ledger).exists():
        for line_no, raw in enumerate(Path(ledger).read_bytes().splitlines(keepends=True), 1):
            try:
                if not raw.endswith(b'\n'): raise ValueError('unterminated ledger record')
                e = checked_json(raw); identity = e['slot_id']
                if identity not in index: raise ValueError('unknown slot')
                i = index[identity]
                if identity in seen: raise ValueError('duplicate slot')
                seen.add(identity)
                if i != line_no-1: errors.append({'line': line_no, 'error': 'out-of-order slot', 'slot_id': identity})
                status = e['status']
                if status not in ('complete', 'error'): raise ValueError('unknown event status')
                slots[i].update(status=status, record=e)
                if status == 'complete':
                    try:
                        validate_record(e, slots[i], parity=plan.get('mode', 'replay') == 'replay')
                    except (ValueError, KeyError, TypeError) as exc:
                        slots[i].update(status='invalid', validation_error=str(exc))
            except (ValueError, KeyError, TypeError) as exc:
                errors.append({'line': line_no, 'error': str(exc), 'raw': raw.decode(errors='replace')})
    counts = {k: sum(s['status'] == k for s in slots) for k in ('complete', 'error', 'missing', 'invalid')}
    return {'schema_version': 1, 'mode': plan.get('mode', 'replay'), 'plan_sha256': sha(encoded(plan)),
            'denominator': len(slots), 'complete': counts['complete'] == len(slots) and not errors,
            'counts': counts, 'ledger_errors': errors, 'slots': slots,
            'numerical_passed': counts['complete'] == len(slots) and not errors and all(s.get('record', {}).get('comparison', {}).get('passed', plan.get('mode', 'replay') == 'replay') for s in slots),
            'review_required': any(s.get('record', {}).get('comparison', {}).get('review_required', False) for s in slots),
            'ledger_sha256': sha(Path(ledger).read_bytes()) if Path(ledger).exists() else None}


def source_identity(root=ROOT):
    root = Path(root)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip():
        raise ValueError('measurement source must be clean and committed')
    files = subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines()
    hashes = {name: sha((root/name).read_bytes()) for name in files if (root/name).is_file()}
    return {'source_commit': commit, 'source_manifest_sha256': sha(encoded(hashes)), 'source_files': hashes}


def identities(binary, request_path, public_reproduction=False):
    if public_reproduction:
        from public_provenance import validate_request
        request = validate_request(request_path, binary=binary)
        return {**request['source'], 'execution_kind': 'public_reproduction',
                'binary_sha256': request['binary_sha256'], 'runtime': request['runtime'],
                'request_sha256': sha(Path(request_path).read_bytes()), 'public_request': request,
                'compiler_provenance': 'Locally supplied executable bytes pinned before launch; compiler/build provenance is not inferred.',
                'supervision': 'Public identity request is not evidence of guard enforcement.'}
    if sha(Path(binary).read_bytes()) != BINARY_SHA256: raise ValueError('binary identity drift')
    request = checked_json(Path(request_path).read_bytes())
    # Exact private paths/argv stay in immutable private request. Public hashes link them.
    return {**source_identity(), 'binary_sha256': BINARY_SHA256, 'python_version': platform.python_version(),
            'python_sha256': request['python_sha256'], 'request_sha256': sha(Path(request_path).read_bytes()),
            'wrapper_sha256': request['wrapper_sha256'], 'guard_sha256': request['guard_sha256'],
            'runtime_metadata_sha256': {Path(k).parent.name: v for k, v in request['runtime_metadata'].items()},
            'compiler_provenance': 'Task1 compiler bytes observed after builds; binary identity pinned for reuse, not pre-build provenance.'}


def invoke(binary, slot, directory, identity):
    output = directory / ('raw-' + str(slot['index']))
    command = [str(Path(binary).resolve()), 'simulate', '--output', str(output.resolve()), *config_argv(slot['config'])]
    # Persist exact private argv before launch; never put local absolute paths in public metadata.
    write_new(directory / ('command-' + str(slot['index']) + '.json'), command)
    if sha(Path(binary).read_bytes()) != identity['binary_sha256']:
        raise ValueError('binary identity drift before simulator launch')
    process = subprocess.run(command, capture_output=True, text=True, timeout=60)
    summary = checked_json((output/'summary.json').read_bytes())
    if process.returncode not in (0, 3) or (process.returncode == 3) != summary['aborted']:
        raise ValueError('simulator exit/result mismatch: ' + process.stderr)
    data = (output/'trace.csv').read_bytes(); rows = read_trace(data)
    record = {'slot_id': slot['id'], 'status': 'complete', 'utc': utc(), 'summary': summary,
              'summary_sha256': sha((output/'summary.json').read_bytes()), 'trace_sha256': sha(data),
              'config_sha256': sha(encoded(summary['config'])), 'identities': identity,
              'csv_gate_durations_s': gate_occupancy(rows, summary['observational_metrics']['observed_duration_s']),
              'csv_final_net_work_J': rows[-1]['W_e'],
              'command_display_kind': 'normalized for portability; exact argv retained privately by hash',
              'command_argv': ['actuator_lab', 'simulate', '--output', output.name, *config_argv(slot['config'])],
              'exact_command_sha256': sha(encoded(command)), 'stdout': process.stdout, 'stderr': process.stderr}
    return record, output


def energy_comparison(measured, reference):
    return {k: {'measured_J': measured[k], 'reference_J': reference[k], 'difference_J': measured[k]-reference[k],
                'tolerance_J': 5e-5 + 5e-5*abs(reference[k]),
                'passed': abs(measured[k]-reference[k]) <= 5e-5 + 5e-5*abs(reference[k])}
            for k in ('supplied_energy_J', 'regenerated_energy_J')}


def sensitivity_plan(plan):
    selected = [copy.deepcopy(s) for s in plan['slots'] if s['cohort'] == 'named' or s['case'] in (0, 21, 42, 63)]
    for i, slot in enumerate(selected):
        slot['index'] = i
        slot['config']['substeps'] *= 4
        slot['config_sha256'] = sha(encoded(slot['config']))
    return {**plan, 'mode': 'sensitivity', 'denominator': 33, 'slots': selected}


def compare_sensitivity(record, baseline):
    a = record['summary']; b = baseline['record']['summary']
    m, n = a['observational_metrics'], b['observational_metrics']
    energy = energy_comparison(m, n)
    status = m['tracking_settling_status'] == n['tracking_settling_status']
    time_delta = None if m['tracking_settling_time_s'] is None or n['tracking_settling_time_s'] is None else m['tracking_settling_time_s']-n['tracking_settling_time_s']
    time_ok = time_delta is None or abs(time_delta) <= b['config']['Tc'] + 1e-12
    outcomes = {k: {'baseline': b[k], 'fine': a[k], 'same': a[k] == b[k]} for k in ('success', 'aborted', 'tripped', 'excursion')}
    gate_differences = {g: m['gate_durations_s'][g]-n['gate_durations_s'][g] for g in GATES}
    events_same = a['events'] == b['events']
    return {'energy': energy, 'settling_status_same': status, 'settling_time_difference_s': time_delta,
            'settling_time_limit_s': b['config']['Tc'], 'settling_time_passed': time_ok,
            'gate_duration_difference_s': gate_differences,
            'legacy_outcomes': outcomes, 'events_same': events_same,
            'review_required': not events_same or any(v != 0 for v in gate_differences.values()),
            'passed': all(v['passed'] for v in energy.values()) and status and time_ok and all(v['same'] for v in outcomes.values())}


def run_phase(args, plan):
    output = Path(args.output)
    identity = identities(args.binary, args.request, getattr(args, 'public_reproduction', False))
    output.mkdir(exist_ok=False)
    write_new(output/'identities.json', identity)
    baseline = None
    baseline_provenance = None
    if args.mode == 'sensitivity':
        baseline = checked_json(Path(args.baseline).read_bytes())
        if not baseline['complete'] or baseline['denominator'] != 213: raise ValueError('complete replay required')
        baseline_provenance = {'baseline_sha256': sha(Path(args.baseline).read_bytes()),
                               'data_source_identity': baseline['slots'][0]['record']['identities']}
        if (baseline['slots'][0]['record']['identities']['source_commit'] != identity['source_commit']
                and not getattr(args, 'public_reproduction', False)):
            raise ValueError('sensitivity source differs from admitted replay source')
        baseline = {s['id']: s for s in baseline['slots']}
        plan = sensitivity_plan(plan)
    write_new(output/'plan.json', plan)
    ledger = output/'events.jsonl'
    failed = False
    with ledger.open('x') as stream:
        for slot in plan['slots']:
            try:
                record, raw = invoke(args.binary, slot, output, identity)
                validate_record(record, slot, parity=args.mode == 'replay')
                if baseline is not None:
                    record['comparison'] = compare_sensitivity(record, baseline[slot['id']])
                append_event(stream, record)
                print(json.dumps({'slot': slot['id'], 'status': 'complete', 'comparison': record.get('comparison', {}).get('passed'),
                                  'review_required': record.get('comparison', {}).get('review_required', False)}), flush=True)
                if baseline is not None and not record['comparison']['passed']:
                    failed = True
                    break  # Preserve raw data and halt for analysis, never retry.
                # Audit is durable before deleting only this slot's successful disposable data.
                (raw/'trace.csv').unlink(); (raw/'summary.json').unlink(); raw.rmdir()
            except Exception as exc:
                append_event(stream, {'slot_id': slot['id'], 'status': 'error', 'utc': utc(), 'error': type(exc).__name__ + ': ' + str(exc)})
                failed = True
                break
    result = finalize(plan, ledger)
    result['numerical_passed'] = not failed and result['complete']
    if baseline_provenance is not None:
        result.update(baseline_provenance)
    write_new(output/'results.json', result)
    return 0 if result['complete'] and not failed else 1


def staged(path):
    cache = Path(os.environ['ACTUATOR_CACHE']).resolve()
    resolved = Path(path).resolve()
    if resolved == cache or cache not in resolved.parents:
        raise ValueError('output must be a child of guarded ACTUATOR_CACHE')
    return resolved


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('plan', 'replay', 'finalize', 'sensitivity'))
    p.add_argument('--evidence', default='evidence'); p.add_argument('--plan'); p.add_argument('--output', required=True)
    p.add_argument('--binary'); p.add_argument('--request'); p.add_argument('--ledger'); p.add_argument('--baseline')
    p.add_argument('--public-reproduction', action='store_true', help='pin actual local bytes using a public_provenance request; separately identified new execution')
    args = p.parse_args(); args.output = staged(args.output)
    if args.mode == 'plan':
        write_new(args.output, make_plan(args.evidence)); return 0
    plan = checked_json(Path(args.plan).read_bytes()); validate_plan(plan, args.evidence)
    if args.mode == 'finalize':
        write_new(args.output, finalize(plan, args.ledger)); return 0
    return run_phase(args, plan)


if __name__ == '__main__':
    raise SystemExit(main())
