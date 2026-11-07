"""Offline scientific report. Consumes recorded metrics only; never simulates."""
import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import statistics

CONTROLLERS = ('direct', 'cascaded', 'feedforward')
GATES = ('speed_gate', 'current_clamp', 'voltage_clamp', 'trip')
STATUSES = ('settled', 'not_settled', 'insufficient_horizon', 'incomplete')


def summarize(replay):
    if not replay['complete'] or replay['denominator'] != 213 or len(replay['slots']) != 213:
        raise ValueError('scientific report requires complete 213-slot replay')
    result = {}
    for cohort, denominator in [('named', 7), ('mc', 64)]:
        result[cohort] = {}
        for controller in CONTROLLERS:
            rows = [s for s in replay['slots'] if s['cohort'] == cohort and s['controller'] == controller]
            if len(rows) != denominator or any(s['status'] != 'complete' for s in rows):
                raise ValueError('report denominator or completion mismatch')
            summaries = [s['record']['summary'] for s in rows]
            metrics = [s['observational_metrics'] for s in summaries]
            result[cohort][controller] = {
                'denominator': denominator, 'legacy_success': sum(s['success'] for s in summaries),
                'settling_counts': {status: sum(m['tracking_settling_status'] == status for m in metrics) for status in STATUSES},
                'supplied_energy_J_median': statistics.median(m['supplied_energy_J'] for m in metrics),
                'regenerated_energy_J_median': statistics.median(m['regenerated_energy_J'] for m in metrics),
                'gate_fraction_median': {g: statistics.median(m['gate_fractions'][g] for m in metrics if m['gate_fractions'][g] is not None) for g in GATES}}
    expected = {'direct': 0, 'cascaded': 64, 'feedforward': 10}
    if any(result['mc'][c]['legacy_success'] != n for c, n in expected.items()):
        raise ValueError('historical negative outcomes changed')
    return result


def portable_json(path):
    data = Path(path).read_bytes()
    if b'/Users/' in data or b'/home/' in data or b'.superpowers/' in data:
        raise ValueError('private path found in proposed public data')
    return json.loads(data)


def sensitivity_review(sensitivity, disposition=None, data_sha256=None):
    disagreements = []
    for slot in sensitivity['slots']:
        comparison = slot['record']['comparison']
        differences = comparison['gate_duration_difference_s']
        if set(differences) != set(GATES) or any(type(v) not in (int, float) or not math.isfinite(v) for v in differences.values()):
            raise ValueError('invalid sensitivity review diagnostics')
        if type(comparison['events_same']) is not bool:
            raise ValueError('invalid sensitivity review events diagnostic')
        if not comparison['events_same'] or any(v != 0 for v in differences.values()):
            disagreements.append({'slot_id': slot['id'], 'gate_duration_difference_s': differences,
                                  'events_same': comparison['events_same']})
    if disagreements:
        digest = data_sha256 or hashlib.sha256((json.dumps(sensitivity, indent=2, allow_nan=False)+'\n').encode()).hexdigest()
        if (not isinstance(disposition, dict) or set(disposition) != {'sensitivity_sha256', 'reviewer', 'rationale'}
                or disposition['sensitivity_sha256'] != digest
                or any(not isinstance(disposition[k], str) or not disposition[k].strip() for k in ('reviewer', 'rationale'))):
            raise ValueError('sensitivity diagnostic review requires a hash-bound reviewer and rationale disposition')
    elif disposition is not None:
        raise ValueError('sensitivity review disposition supplied without diagnostic disagreements')
    return {'review_required': bool(disagreements), 'disagreements': disagreements, 'disposition': disposition}


def report_navigation(public_reproduction=False):
    links = [('runs.csv', 'All 213 rows (CSV)'), ('results.json', 'Full replay audit'),
             ('reference.json', 'Nine independent references'), ('sensitivity.json', '33 resolution comparisons'),
             ('manifest.json', 'File hashes')]
    if not public_reproduction:
        links = [('../../docs/metrics-v2.md', 'Metric definitions'), ('../report.html', 'Original report'), *links]
    return ' · '.join(f'<a href="{path}">{label}</a>' for path, label in links)


def render(replay_path, reference_path, sensitivity_path, out, request, public_reproduction=False, disposition=None):
    replay = portable_json(replay_path); refs = portable_json(reference_path); sensitivity = portable_json(sensitivity_path)
    summary = summarize(replay)
    if not refs['complete'] or len(refs['slots']) != 9 or not all(s['comparison']['passed'] for s in refs['slots']):
        raise ValueError('all nine independent comparisons must pass before report')
    if not sensitivity['complete'] or not sensitivity['numerical_passed'] or len(sensitivity['slots']) != 33 or not all(s['record']['comparison']['passed'] for s in sensitivity['slots']):
        raise ValueError('all 33 resolution comparisons must pass before report')
    review = sensitivity_review(sensitivity, disposition, hashlib.sha256(Path(sensitivity_path).read_bytes()).hexdigest())
    tool_identity = None
    if public_reproduction:
        from public_provenance import validate_request
        tool_identity = validate_request(request)
    label = 'public reproduction report' if public_reproduction else 'original measurement completion'
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    out.mkdir(exist_ok=False)
    # Public filenames are fixed, portable, and audited in the final manifest.
    for source, name in [(replay_path, 'results.json'), (reference_path, 'reference.json'), (sensitivity_path, 'sensitivity.json')]:
        (out/name).write_bytes(Path(source).read_bytes())
    (out/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    fields = ['slot', 'cohort', 'case', 'controller', 'legacy_success', 'legacy_aborted', 'legacy_tripped', 'legacy_excursion',
              'settling_status', 'settling_time_s', 'supplied_energy_J', 'regenerated_energy_J', 'net_work_J',
              'observed_duration_s', 'planned_duration_s', 'completed_steps', 'observation_step_s', *[g+'_fraction' for g in GATES], 'trace_sha256']
    flat = []
    for slot in replay['slots']:
        s = slot['record']['summary']; m = s['observational_metrics']
        flat.append(dict(zip(fields, [slot['id'], slot['cohort'], slot['case'], slot['controller'], s['success'], s['aborted'], s['tripped'], s['excursion'],
             m['tracking_settling_status'], m['tracking_settling_time_s'], m['supplied_energy_J'], m['regenerated_energy_J'], m['net_electrical_work_J'],
             m['observed_duration_s'], m['planned_duration_s'], m['completed_steps'], m['observation_step_s'], *[m['gate_fractions'][g] for g in GATES], slot['record']['trace_sha256']])))
    with (out/'runs.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(flat)

    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 180})
    colors = ['#36648b', '#b65835', '#48764a']
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout='constrained')
    for ax, cohort, title in zip(axes, ('named', 'mc'), ('Named scenarios (7/controller)', 'Frozen synthetic trials (64/controller)')):
        values = [summary[cohort][c]['settling_counts']['settled'] for c in CONTROLLERS]
        denominators = [summary[cohort][c]['denominator'] for c in CONTROLLERS]
        ax.bar(CONTROLLERS, values, color=colors, label='Tracking settled')
        ax.bar(CONTROLLERS, [n-v for n, v in zip(denominators, values)], bottom=values, color='#dedbd4', label='No qualifying tail')
        for i, (v, n) in enumerate(zip(values, denominators)):
            ax.text(i, n+.35, f'{v}/{n} settled', ha='center', fontsize=10)
        ax.set_ylim(0, max(denominators)*1.18); ax.set_title(title); ax.set_ylabel('Runs (complete fixed denominator)')
        ax.tick_params(axis='x', rotation=12)
    axes[0].legend(loc='upper left', bbox_to_anchor=(0., -.18), ncol=2, frameon=False)
    fig.suptitle('Finite-horizon tracking settling • accepted substep endpoints')
    for ext in ('png', 'pdf'): fig.savefig(out/f'settling.{ext}')
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout='constrained')
    for ax, key, title in zip(axes, ('supplied_energy_J', 'regenerated_energy_J'), ('Gross terminal supply', 'Gross terminal regeneration')):
        values = [[r[key] for r in flat if r['cohort'] == 'mc' and r['controller'] == c] for c in CONTROLLERS]
        # Paired trajectories connect the same frozen trial, never new samples.
        for trial in range(64): ax.plot(range(1, 4), [v[trial] for v in values], color='#777777', alpha=.13, linewidth=.7)
        bp = ax.boxplot(values, tick_labels=CONTROLLERS, patch_artist=True, widths=.4, showfliers=False)
        for box, color in zip(bp['boxes'], colors): box.set_facecolor(color); box.set_alpha(.7)
        ax.set_ylabel('Terminal energy (J)'); ax.set_title(title); ax.tick_params(axis='x', rotation=12); ax.set_ylim(bottom=0)
    fig.suptitle('Paired frozen Monte Carlo inputs • 64 trials/controller')
    for ext in ('png', 'pdf'): fig.savefig(out/f'energy.{ext}')
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout='constrained')
    for ax, cohort, title in zip(axes, ('named', 'mc'), ('Named scenarios (7/controller)', 'Frozen synthetic trials (64/controller)')):
        values = np.array([[summary[cohort][c]['gate_fraction_median'][g] for g in GATES] for c in CONTROLLERS])
        image = ax.imshow(values, vmin=0, vmax=1, cmap='Blues', aspect='auto')
        ax.set_xticks(range(4), ['Speed gate', 'Current clamp', 'Voltage clamp', 'Trip latch'], rotation=22, ha='right')
        ax.set_yticks(range(3), CONTROLLERS); ax.set_title(title)
        for i in range(3):
            for j in range(4): ax.text(j, i, f'{values[i,j]:.3f}', ha='center', va='center', color='white' if values[i,j] > .6 else 'black')
    fig.colorbar(image, ax=axes, label='Median accepted-duration fraction [0, 1]', shrink=.8)
    fig.suptitle('Duration-weighted gate occupancy • overlapping flags')
    for ext in ('png', 'pdf'): fig.savefig(out/f'gates.{ext}')
    plt.close(fig)

    def figure(name, caption):
        src = base64.b64encode((out/(name+'.png')).read_bytes()).decode()
        return f'<figure><img alt="{html.escape(caption)}" src="data:image/png;base64,{src}"><figcaption>{caption} · <a href="{name}.png">PNG</a> · <a href="{name}.pdf">PDF</a></figcaption></figure>'
    def cell(value):
        return html.escape('—' if value is None else f'{value:.6g}' if isinstance(value, float) else str(value))
    table_columns = ('slot', 'legacy_success', 'legacy_tripped', 'legacy_excursion', 'settling_status', 'settling_time_s', 'supplied_energy_J', 'regenerated_energy_J')
    table = '<table><thead><tr>'+''.join(f'<th>{html.escape(k)}</th>' for k in table_columns)+'</tr></thead><tbody>'
    table += ''.join('<tr>'+''.join('<td>'+cell(r[k])+'</td>' for k in table_columns)+'</tr>' for r in flat if r['cohort'] == 'named')+'</tbody></table>'
    dates = sorted(s['record']['utc'] for s in replay['slots'])
    source = replay['slots'][0]['record']['identities']
    max_ref = max(abs(e['difference_J']) for s in refs['slots'] for e in s['comparison']['energy'].values())
    max_sensitivity = max(abs(e['difference_J']) for s in sensitivity['slots'] for e in s['record']['comparison']['energy'].values())
    provenance_text = (f"Public reproduction tool source {tool_identity['source']['source_commit']}; request pins local source/runtime/executable bytes and does not prove guard enforcement. Data source commit {source['source_commit']}; binary SHA256 {source['binary_sha256']}. Data timestamps below belong to the consumed replay, not this report generation."
                       if public_reproduction else f"Source commit {source['source_commit']}; binary SHA256 {source['binary_sha256']}. Historical compiler bytes were observed after Task1 builds, not pinned before those builds; the accepted binary was pinned for this replay. Exact private commands and resource receipts are linked by hashes in public metadata; displayed simulator argv is explicitly normalized for portability.")
    review_text = ('Diagnostic disagreement was explicitly reviewed: '+json.dumps(review, sort_keys=True)
                   if review['review_required'] else 'Gate durations and event lists agree; no diagnostic review disposition is required.')
    text = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Actuator Lab — {label}</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;margin:40px auto;padding:0 24px;max-width:1180px;color:#20252b}}h1,h2{{line-height:1.2}}img{{width:100%;height:auto}}figure{{margin:36px 0}}figcaption{{font-size:14px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:7px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#eef1f3}}.table{{overflow-x:auto}}code{{overflow-wrap:anywhere}}a{{color:#205b83}}</style>
<h1>Actuator Lab: {label}</h1>
<p>213 fixed configurations: 21 named + 192 synthetic Monte Carlo runs. Every legacy CSV SHA256 and legacy summary field matches the October 2026 accepted experiment. New measurements ran {cell(dates[0])} through {cell(dates[-1])} UTC; publication is a separate later action.</p>
<p>Historical Monte Carlo success remains <strong>direct 0/64; cascaded 64/64; feedforward 10/64</strong>. Feedforward remains a post-observation ablation. Tracking settling is a separate metric: failed/tripped runs can have a qualifying tracking tail. No failed outcome leaves the denominator.</p>
<p>{report_navigation(public_reproduction)}</p>
{figure('settling', 'Settling requires a final uninterrupted in-band tail of at least 2 s. Counts are observed on accepted integration endpoints; this is not continuous-time proof.')}
{figure('energy', 'Gross positive and negative terminal work are separate. Lines connect the same frozen trial; boxes show quartiles and median, with 1.5-IQR whiskers. Values are descriptive synthetic comparisons, not battery efficiency.')}
{figure('gates', 'Each left-held gate flag is weighted by accepted integration time. The terminal controller row contributes no duration. Fractions overlap and need not sum to one.')}
<h2>All 21 named outcomes</h2><div class="table">{table}</div>
<h2>Independent numerical checks</h2><p>9/9 absolute-coordinate DOP853 checks passed at rtol 1e-11 and atol 1e-12, replaying the hash-verified applied-voltage, torque and drag schedule. Maximum gross-energy absolute difference: {max_ref:.6g} J. All 21 named + MC IDs 0,21,42,63 across three controllers (33/33) passed four-times-substep comparison; maximum gross-energy difference: {max_sensitivity:.6g} J. Each energy tolerance is 5e-5 J + 5e-5 times the absolute reference energy; settling status must agree, and settled times differ by at most one original controller interval. Individual values, gate differences and legacy outcome comparisons remain in the linked data.</p>
<h2>Scope and provenance</h2><p>These explicitly post-observation definitions complete original requested measurements without tuning controllers, resampling the cohort or changing original decisions. Split-power integrands are nonsmooth at sign crossings, so the old smooth fourth-order claim does not extend to gross quadrature. This synthetic one-axis numerical artifact provides no hardware, GPU, battery-recovery or continuous-safety validation, no personal-mastery evidence and no employer endorsement. Agent-assisted work does not establish sole human authorship.</p>
<p>{html.escape(provenance_text)} Original experiment: October 2026. Extension measurement and report dates are recorded separately.</p><p>{html.escape(review_text)}</p></html>'''
    (out/'report.html').write_text(text)
    provenance = {'report_utc': datetime.now(timezone.utc).isoformat(), 'measurement_start_utc': dates[0], 'measurement_end_utc': dates[-1],
                  'original_experiment': 'October 2026; original accepted integration update 2026-10-23',
                  'publication': 'not performed by report renderer', 'renderer_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'report_request_sha256': hashlib.sha256(Path(request).read_bytes()).hexdigest(),
                  'all_213_legacy_parity': True, 'reference_denominator': 9, 'sensitivity_denominator': 33}
    provenance.update(data_source_identity=source, tool_identity=tool_identity,
                      execution_kind='public_reproduction' if public_reproduction else 'historical_strict',
                      sensitivity_review=review,
                      input_sha256={name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in
                                    [('replay', replay_path), ('reference', reference_path), ('sensitivity', sensitivity_path)]})
    (out/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    files = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps({'schema_version': 1, 'files': files}, indent=2)+'\n')
    print(json.dumps({'report': 'report.html', 'rows': len(flat), 'files': len(files), 'bytes': sum(v['bytes'] for v in files.values()), 'summary': summary}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('replay', 'reference', 'sensitivity', 'output', 'request'): p.add_argument('--'+arg, required=True)
    p.add_argument('--public-reproduction', action='store_true')
    p.add_argument('--review-disposition', help='JSON sensitivity_sha256/reviewer/rationale, required for gate or event disagreements')
    args = p.parse_args(); out = Path(args.output).resolve(); cache = Path(os.environ['ACTUATOR_CACHE']).resolve()
    if cache not in out.parents: raise ValueError('report output must be staged in guarded cache')
    disposition = portable_json(args.review_disposition) if args.review_disposition else None
    render(args.replay, args.reference, args.sensitivity, out, args.request, args.public_reproduction, disposition)


if __name__ == '__main__':
    main()
