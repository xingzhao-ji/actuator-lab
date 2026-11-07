"""Independent absolute-coordinate DOP853 reference; no production metric imports.

State: body angle, absolute body speed, absolute wheel speed, current, positive
terminal work, negative terminal work magnitude. Actual recorded voltages,
external torques and bearing multipliers are left-held over each CSV interval.
"""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
import subprocess
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp


def integrate_interval(initial, plant, voltage, external, multiplier, duration, times):
    jb, jw, resistance, inductance, coupling, drag = (plant[k] for k in ('Jb', 'Jw', 'R', 'L', 'k', 'b'))
    def equations(_t, y):
        theta, body_speed, wheel_speed, current, supplied, regenerated = y
        electromagnetic = coupling*current
        friction = drag*multiplier*(wheel_speed-body_speed)
        power = voltage*current
        return [body_speed, (external+friction-electromagnetic)/jb,
                (electromagnetic-friction)/jw,
                (voltage-resistance*current-coupling*(wheel_speed-body_speed))/inductance,
                max(power, 0.), max(-power, 0.)]
    solution = solve_ivp(equations, (0., duration), initial, method='DOP853',
                         rtol=1e-11, atol=1e-12, t_eval=np.asarray(times))
    if not solution.success or not np.isfinite(solution.y).all():
        raise ValueError('independent DOP853 integration failed: ' + solution.message)
    return solution.y.T


def tracking(in_band, h, aborted):
    # Derive the final uninterrupted tail from endpoint booleans independently.
    last = next((j for j in range(len(in_band)-1, -1, -1) if not in_band[j]), None)
    tail = 0 if last is None else last+1 if last+1 < len(in_band) else None
    horizon = (len(in_band)-1)*h
    if aborted: status = 'incomplete'
    elif horizon < 2.: status = 'insufficient_horizon'
    elif tail is not None and (len(in_band)-1-tail)*h >= 2.-1e-13: status = 'settled'
    else: status = 'not_settled'
    return {'status': status, 'time_s': tail*h if status == 'settled' else None,
            'last_violating_step': last, 'tail_start_step': tail}


def reference(config, data, aborted=False):
    rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(io.StringIO(data.decode()))]
    state = np.array([*config['initial'][:4], 0., 0.])
    h = config['Tc']/config['substeps']
    observed = [abs(state[0]-config['target']) <= .01 and abs(state[1]) <= .002]
    max_error = [0., 0., 0., 0.]
    for left, right in zip(rows, rows[1:]):
        dt = right['time']-left['time']; steps = round(dt/h)
        if steps <= 0 or abs(steps*h-dt) > 1e-11: raise ValueError('CSV interval not aligned to original endpoints')
        points = np.linspace(0., dt, steps+1)
        values = integrate_interval(state, config['plant'], left['voltage'], left['external_torque'], left['bearing_multiplier'], dt, points)
        observed.extend(bool(v) for v in ((np.abs(values[1:, 0]-config['target']) <= .01) & (np.abs(values[1:, 1]) <= .002)))
        state = values[-1]
        for j, key in enumerate(('theta', 'omega_body', 'omega_wheel', 'current')):
            max_error[j] = max(max_error[j], abs(state[j]-right[key]))
    return {'supplied_energy_J': float(state[4]), 'regenerated_energy_J': float(state[5]),
            'tracking': tracking(observed, h, aborted), 'observed_endpoints': len(observed),
            'observation_step_s': h, 'maximum_controller_row_absolute_state_error': dict(zip(('theta_rad', 'body_rad_s', 'wheel_rad_s', 'current_A'), max_error)),
            'rtol': 1e-11, 'atol': 1e-12, 'coordinates': 'absolute body and wheel angular velocities', 'solver': 'DOP853'}


def compare(result, metric, interval):
    energy = {}
    for key in ('supplied_energy_J', 'regenerated_energy_J'):
        delta = metric[key]-result[key]; tolerance = 5e-5+5e-5*abs(result[key])
        energy[key] = {'reference_J': result[key], 'measured_J': metric[key], 'difference_J': delta, 'tolerance_J': tolerance, 'passed': abs(delta) <= tolerance}
    status = result['tracking']['status'] == metric['tracking_settling_status']
    a, b = result['tracking']['time_s'], metric['tracking_settling_time_s']
    delta = None if a is None or b is None else b-a
    time_ok = delta is None or abs(delta) <= interval+1e-12
    return {'energy': energy, 'settling_status_same': status, 'settling_time_difference_s': delta,
            'settling_time_limit_s': interval, 'settling_time_passed': time_ok,
            'passed': all(e['passed'] for e in energy.values()) and status and time_ok}


def finalize_reference(plan, ledger):
    done, errors = {}, []
    if Path(ledger).exists():
        for n, raw in enumerate(Path(ledger).read_bytes().splitlines(keepends=True), 1):
            try:
                if not raw.endswith(b'\n'): raise ValueError('unterminated ledger record')
                def invalid(value): raise ValueError('nonfinite JSON: '+value)
                record = json.loads(raw, parse_constant=invalid)
                slot = record['slot_id']
                if slot not in plan['slots'] or slot in done: raise ValueError('unknown/duplicate reference slot')
                if n > len(plan['slots']) or slot != plan['slots'][n-1]: raise ValueError('reference slot order mismatch')
                if record['status'] not in ('complete', 'error'): raise ValueError('invalid reference status')
                if record['status'] == 'complete':
                    if not isinstance(record['comparison']['passed'], bool): raise ValueError('invalid comparison verdict')
                    for key in ('supplied_energy_J', 'regenerated_energy_J'):
                        value = record['reference'][key]
                        if type(value) not in (int, float) or not math.isfinite(value) or value < 0: raise ValueError('invalid reference energy')
                done[slot] = record
            except (KeyError, TypeError, ValueError) as exc:
                errors.append({'line': n, 'error': str(exc), 'raw': raw.decode(errors='replace')})
    slots = [done.get(slot, {'slot_id': slot, 'status': 'missing'}) for slot in plan['slots']]
    complete = not errors and all(s['status'] == 'complete' and s['comparison']['passed'] for s in slots)
    return {**plan, 'complete': complete, 'slots': slots, 'ledger_errors': errors,
            'ledger_sha256': hashlib.sha256(Path(ledger).read_bytes()).hexdigest() if Path(ledger).exists() else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay'); p.add_argument('--finalize-plan'); p.add_argument('--ledger'); p.add_argument('--evidence', default='evidence')
    p.add_argument('--output', required=True); p.add_argument('--request')
    args = p.parse_args()
    cache = Path(os.environ['ACTUATOR_CACHE']).resolve(); out = Path(args.output).resolve()
    if cache not in out.parents: raise ValueError('reference output must be staged in cache')
    if args.finalize_plan:
        result = finalize_reference(json.loads(Path(args.finalize_plan).read_bytes()), args.ledger)
        with out.open('x') as stream: stream.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
        return 0
    replay_bytes = Path(args.replay).read_bytes(); replay = json.loads(replay_bytes)
    if not replay['complete'] or replay['denominator'] != 213: raise ValueError('complete 213 replay required')
    selected = [s for s in replay['slots'] if s['cohort'] == 'named' and s['case'] in ('nominal', 'bias', 'stuck_positive')]
    if len(selected) != 9: raise ValueError('reference denominator mismatch')
    identity = selected[0]['record']['identities']
    root = Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip():
        raise ValueError('reference source must be clean and committed')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if commit != identity['source_commit'] or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != identity['source_files']['python/metric_reference.py']:
        raise ValueError('reference source differs from admitted replay source')
    out.mkdir(exist_ok=False)
    plan = {'denominator': 9, 'slots': [s['id'] for s in selected], 'replay_sha256': hashlib.sha256(replay_bytes).hexdigest(),
            'request_sha256': hashlib.sha256(Path(args.request).read_bytes()).hexdigest(),
            'source_commit': selected[0]['record']['identities']['source_commit'],
            'reference_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    records = []; failed = False
    with (out/'events.jsonl').open('x') as stream:
        for slot in selected:
            try:
                path = Path(args.evidence)/'traces'/f"{slot['case']}-{slot['controller']}.csv.gz"
                data = gzip.decompress(path.read_bytes()); digest = hashlib.sha256(data).hexdigest()
                if digest != slot['trace_sha256'] or digest != slot['record']['trace_sha256']:
                    raise ValueError('retained held-input trace identity mismatch')
                result = reference(slot['config'], data, slot['legacy']['aborted'])
                comparison = compare(result, slot['record']['summary']['observational_metrics'], slot['config']['Tc'])
                record = {'slot_id': slot['id'], 'status': 'complete', 'utc': datetime.now(timezone.utc).isoformat(),
                          'trace_sha256': digest, 'reference': result, 'comparison': comparison}
            except Exception as exc:
                record = {'slot_id': slot['id'], 'status': 'error', 'error': type(exc).__name__+': '+str(exc)}
            stream.write(json.dumps(record, allow_nan=False)+'\n'); stream.flush(); os.fsync(stream.fileno())
            records.append(record); print(json.dumps(record), flush=True)
            if record['status'] == 'error' or not record['comparison']['passed']:
                failed = True; break
    result = finalize_reference(plan, out/'events.jsonl')
    (out/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return int(not result['complete'])


if __name__ == '__main__':
    raise SystemExit(main())
