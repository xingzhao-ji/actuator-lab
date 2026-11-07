"""Public admission, additive checkpoint compatibility and diagnostic review."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))


def public_module():
    try:
        return importlib.import_module('public_provenance')
    except ModuleNotFoundError:
        pytest.fail('truthful public provenance producer is missing')


@pytest.fixture
def local_source(tmp_path):
    root = tmp_path/'source'; root.mkdir()
    (root/'source.txt').write_text('public source\n')
    for argv in (['init', '-q'], ['add', 'source.txt'],
                 ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                  'commit', '-qm', 'fixture']):
        subprocess.run(['git', *argv], cwd=root, check=True, capture_output=True)
    binary = tmp_path/'local-binary'; binary.write_bytes(b'local build, not the historical binary\n')
    return root, binary


def test_public_request_truthfully_pins_real_source_binary_runtime(local_source, tmp_path):
    p = public_module(); root, binary = local_source
    request = p.prepare_request(binary, root=root)
    path = tmp_path/'request.json'; path.write_text(json.dumps(request))
    identity = p.validate_request(path, binary=binary, root=root)
    assert identity['execution_kind'] == 'public_reproduction'
    assert identity['binary_sha256'] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert identity['source']['source_files'] == {'source.txt': hashlib.sha256(b'public source\n').hexdigest()}
    assert {'numpy', 'scipy'} <= set(identity['runtime']['packages'])
    assert not {'wrapper_sha256', 'guard_sha256'} & set(identity)
    assert str(root) not in json.dumps(identity)


@pytest.mark.parametrize('corruption', ['binary', 'source', 'runtime', 'schema', 'private', 'missing', 'nonfinite'])
def test_public_request_rejects_malformed_or_drifted_real_inputs(local_source, tmp_path, corruption):
    p = public_module(); root, binary = local_source
    request = p.prepare_request(binary, root=root)
    if corruption == 'binary': binary.write_bytes(b'changed executable')
    elif corruption == 'source': (root/'source.txt').write_text('uncommitted drift')
    elif corruption == 'runtime': request['runtime']['python_sha256'] = '0'*64
    elif corruption == 'schema': request['schema_version'] = True
    elif corruption == 'private': request['guard_sha256'] = '0'*64
    elif corruption == 'missing': del request['binary_sha256']
    else: request['schema_version'] = float('nan')
    path = tmp_path/'request.json'; path.write_text(json.dumps(request))
    with pytest.raises(ValueError): p.validate_request(path, binary=binary, root=root)


def retained():
    old = json.loads((ROOT/'evidence/checkpoints/original-paired/results.json').read_bytes())
    new = json.loads((ROOT/'evidence/metrics-v2/results.json').read_bytes())
    groups = {'named': [], 'monte_carlo': []}
    for group, cohort, marker in [('named', 'named', 'scenario'), ('monte_carlo', 'mc', 'id')]:
        for pair in old[group]:
            row = {marker: pair[marker]}
            for controller in ('direct', 'cascaded'):
                slot = next(s for s in new['slots'] if s['cohort'] == cohort and s['case'] == pair[marker] and s['controller'] == controller)
                row[controller] = {**slot['record']['summary'], 'summary_sha256': slot['record']['summary_sha256'],
                                   'trace_sha256': slot['record']['trace_sha256']}
            groups[group].append(row)
    return old, groups


def test_checkpoint_accepts_all_142_retained_additive_records():
    from experiments import checkpoint_unchanged
    old, new = retained()
    assert checkpoint_unchanged(old, new['named'], new['monte_carlo'], old['input_sha256'])
    assert all(a[c]['summary_sha256'] != b[c]['summary_sha256'] for group in new
               for a, b in zip(old[group], new[group]) for c in ('direct', 'cascaded'))


@pytest.mark.parametrize('corruption', ['value', 'event', 'type', 'trace', 'missing', 'ordering', 'extra', 'input'])
def test_checkpoint_rejects_legacy_or_trace_corruption(corruption):
    from experiments import checkpoint_unchanged
    old, new = retained(); row = new['named'][0]['direct']; digest = old['input_sha256']
    if corruption == 'value': row['completed_steps'] += 1
    elif corruption == 'event': row['events'].append('invented-event')
    elif corruption == 'type': row['success'] = int(row['success'])
    elif corruption == 'trace': row['trace_sha256'] = '0'*64
    elif corruption == 'missing': del row['reason']
    elif corruption == 'ordering': new['named'].reverse()
    elif corruption == 'extra': row['unexpected'] = 0
    else: digest = '0'*64
    assert not checkpoint_unchanged(old, new['named'], new['monte_carlo'], digest)


def sensitivity_fixture():
    return json.loads((ROOT/'evidence/metrics-v2/sensitivity.json').read_bytes())


@pytest.mark.parametrize('diagnostic', ['gate', 'events'])
def test_sensitivity_requires_explicit_bound_review_disposition(diagnostic):
    from metric_report import sensitivity_review
    sensitivity = sensitivity_fixture()
    comparison = sensitivity['slots'][0]['record']['comparison']
    if diagnostic == 'gate': comparison['gate_duration_difference_s']['speed_gate'] = .001
    else: comparison['events_same'] = False
    assert comparison['passed']  # Diagnostic disagreement is not an energy failure.
    with pytest.raises(ValueError, match='review'): sensitivity_review(sensitivity)
    disposition = {'sensitivity_sha256': hashlib.sha256((json.dumps(sensitivity, indent=2, allow_nan=False)+'\n').encode()).hexdigest(),
                   'reviewer': 'Fixture reviewer', 'rationale': 'Investigated retained diagnostic disagreement; energy and settling limits unchanged.'}
    review = sensitivity_review(sensitivity, disposition)
    assert review['review_required'] and len(review['disagreements']) == 1
    assert review['disposition'] == disposition
    disposition['sensitivity_sha256'] = '0'*64
    with pytest.raises(ValueError): sensitivity_review(sensitivity, disposition)


def test_historical_sensitivity_needs_no_disposition():
    from metric_report import sensitivity_review
    assert sensitivity_review(sensitivity_fixture()) == {'review_required': False, 'disagreements': [], 'disposition': None}


def test_public_records_accept_local_pin_but_detect_binary_identity_mismatch(local_source):
    import measurements as m
    root, binary = local_source
    request = public_module().prepare_request(binary, root=root)
    slot = json.loads((ROOT/'evidence/metrics-v2/results.json').read_bytes())['slots'][0]
    record = copy.deepcopy(slot['record'])
    record['identities'] = {**request['source'], 'execution_kind': 'public_reproduction',
                            'binary_sha256': request['binary_sha256'], 'runtime': request['runtime'], 'public_request': request}
    m.validate_record(record, slot)
    record['identities']['binary_sha256'] = 'b'*64
    with pytest.raises(ValueError): m.validate_record(record, slot)


def test_public_report_navigation_resolves_in_standalone_cache(tmp_path):
    from html.parser import HTMLParser
    from metric_report import report_navigation
    names = {'runs.csv', 'results.json', 'reference.json', 'sensitivity.json', 'manifest.json'}
    for name in names: (tmp_path/name).write_text('fixture')
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.targets = []
        def handle_starttag(self, tag, attrs):
            if tag == 'a': self.targets.append(dict(attrs)['href'])
    links = Links(); links.feed(report_navigation(public_reproduction=True))
    assert set(links.targets) == names
    assert all((tmp_path/href).is_file() for href in links.targets)
    assert str(ROOT) not in report_navigation(public_reproduction=True)
