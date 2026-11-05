"""Original source replay, repeated-version ordering and temporal audit boundaries."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

from cryptoforge import research_revision_bridge as m
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge.research_training_diagnostics import canonical, digest


MAIN = reviewed_main.live_main_project()
CONTEXT = {'schema_version': 'research-revision-context-v1', 'audited_at': '2026-10-23T07:00:00Z'}


@pytest.fixture
def protocol():
    def interval(start, end): return {'decision_start': start, 'decision_end': end}
    return {'schema_version': 'research-data-protocol-v1', 'registered_at': '2026-10-23T00:00:00Z',
        'symbols': ['BTCUSDT', 'ETHUSDT'], 'timeframe_seconds': 300, 'feature_window_candles': 120,
        'feature_version': 'candle-v1', 'feature_calculation_contract': 'bounded-window-candle-v1',
        'target_version': 'fixed-future-return-v1', 'horizon_candles': 3, 'embargo_candles': 3,
        'decision_delay_seconds': 120, 'fit_information_end': '2026-10-22T10:16:00Z',
        'validation_information_end': '2026-10-22T10:51:00Z', 'partitions': {
            'train': interval('2026-10-22T10:00:00Z', '2026-10-22T10:05:00Z'),
            'validation': interval('2026-10-22T10:35:00Z', '2026-10-22T10:40:00Z'),
            'final_test': interval('2026-10-24T00:00:00Z', '2026-10-25T00:00:00Z'),
            'forward': interval('2026-10-26T00:00:00Z', '2026-10-27T00:00:00Z')}}


@pytest.fixture
def exposure(): return {'schema_version': 'research-data-exposures-v1', 'coverage': 'declared_only', 'entries': []}


@pytest.fixture(scope='module')
def native_fixture(tmp_path_factory, request):
    # This synthetic scenario has fixed holdout dates. Keep its audit clock fixed
    # without changing the production current-time gate or any real evidence.
    original = m.datetime
    class ScenarioClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 23, 7, tzinfo=timezone.utc).astimezone(tz)
    m.datetime = ScenarioClock
    request.addfinalizer(lambda: setattr(m, 'datetime', original))
    base = tmp_path_factory.mktemp('native-reference')
    project = base/'main'
    for name in m.POLICY['reviewed_sources']:
        relative = Path('scripts' if name in ('capture_reference_sources.py', 'audit_local_source_provenance.py') else 'src/cryptoforge')/name
        (project/relative).parent.mkdir(parents=True, exist_ok=True)
        reviewed_main.copy_live_main_path(relative, project / relative)
    reviewed_main.copy_live_main_path(Path('src/cryptoforge/__init__.py'), project/'src/cryptoforge/__init__.py')
    (project/'.local/state').mkdir(parents=True)
    script = base/'make.py'
    script.write_text('''
import base64,json,sys
from pathlib import Path
from datetime import datetime,UTC,timedelta
from cryptoforge import reference_source_ledger as s,reference_sources as r
class Clock:
    now=datetime(2026,10,22,10,0,10,tzinfo=UTC)
    def __call__(self):return self.now
c=Clock();start=int(c.now.timestamp()*1000)//300000*300000
class Client:
    def fetch(self,pair,anchor):
        before=c();c.now+=timedelta(seconds=.05)
        rows=[]
        for i in range(120):
            opened=anchor-300000*(i+1)
            close='100.5' if anchor==start+900000 and opened==start-300000 else '101'
            rows.append([str(opened),'100','102','99',close,'10','1000'])
        raw=s.canonical(dict(retCode=0,result=dict(category='spot',symbol=pair.replace('/',''),list=rows),time=int(c().timestamp()*1000)))
        return dict(pair=pair,anchor_ms=anchor,url=r.request_url(pair,anchor),prepared_at=before.isoformat(),completed_at=c().isoformat(),elapsed_seconds=.05,http_status=200,error_type=None,raw_body_base64=base64.b64encode(raw).decode(),raw_body_sha256=s.digest(raw))
ledger=s.ReferenceLedger.create(Path(sys.argv[1]),clock=c)
for minute in (0,15,35,50):
    c.now=datetime(2026,10,22,10,minute,10,tzinfo=UTC)
    ledger.poll(Client())
Path(sys.argv[2]).write_text(json.dumps(ledger.receipt()['reference']))
class Failed:
    def fetch(self,pair,anchor):
        before=c();c.now+=timedelta(seconds=.05)
        return dict(pair=pair,anchor_ms=anchor,url=r.request_url(pair,anchor),prepared_at=before.isoformat(),completed_at=c().isoformat(),elapsed_seconds=.05,http_status=None,error_type='URLError',raw_body_base64='',raw_body_sha256=s.digest(b''))
c.now=datetime(2026,10,22,10,20,10,tzinfo=UTC)
failed=s.ReferenceLedger.create(Path(sys.argv[1]).parent/'failed',clock=c);failed.poll(Failed())
Path(sys.argv[2]).with_name('failed-reference.json').write_text(json.dumps(failed.receipt()['reference']))
c.now=datetime(2026,10,22,10,0,10,tzinfo=UTC)
mixed=s.ReferenceLedger.create(Path(sys.argv[1]).parent/'mixed',clock=c);mixed.poll(Client())
c.now=datetime(2026,10,22,10,35,10,tzinfo=UTC);mixed.poll(Failed())
Path(sys.argv[2]).with_name('mixed-reference.json').write_text(json.dumps(mixed.receipt()['reference']))
''')
    output = base/'reference.json'
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(project/'src'), 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8'}
    subprocess.run([sys.executable, '-B', str(script), str(project/'.local/state/ledger'), str(output)],
                   env=env, cwd=project, capture_output=True, check=True, timeout=15)
    return project, json.loads(output.read_text())


@pytest.fixture(scope='module')
def native_projection(native_fixture, tmp_path_factory):
    project, reference = native_fixture
    directory = tmp_path_factory.mktemp('native-projection')
    protocol = {'validation_information_end': '2026-10-22T10:51:00Z',
                'partitions': {'final_test': {'decision_start': '2026-10-24T00:00:00Z'}}}
    return m._project(project, reference, protocol, directory)


@pytest.fixture
def projection(native_projection): return deepcopy(native_projection)


def test_real_native_source_replay_and_consistent_metadata_are_not_data_admission(projection, protocol, exposure):
    report = m.audit(projection, protocol, exposure, CONTEXT)
    assert report['status'] == 'metadata_consistent' and report['samples_metadata_consistent'] == 4
    assert report['observed_deliveries'] == 960 and report['unique_versions'] == 262
    assert report['native_audit']['events_checked'] == 16
    assert report['source_mode'] == 'diagnostic'
    assert len(report['source_exposures_recorded_automatically']) == 8
    for key in ('training_data_admitted', 'source_features_labels_parity_verified', 'exposure_inventory_complete',
                'forecast_or_inference_performed', 'network_request_performed', 'production_promotion_authorized',
                'source_poll_completeness_verified', 'historical_known_at_verified'):
        assert report[key] is False


def test_return_to_old_value_uses_latest_delivery_and_preserves_first_seen(projection, protocol):
    _, timeline = m.validate_projection(projection, protocol, CONTEXT)
    opened = '2026-10-22T09:55:00+00:00'
    history = [r for r in timeline if r['symbol'] == 'BTCUSDT' and r['open_time'] == opened]
    assert len(history) == 4
    assert history[0]['revision_sha256'] == history[2]['revision_sha256']
    assert history[1]['revision_sha256'] != history[2]['revision_sha256']
    assert history[0]['first_seen_at'] == history[2]['first_seen_at']
    index = {('BTCUSDT', opened): history}
    selected, error = m.temporal._choose(index, 'BTCUSDT', m.temporal._time(opened), m.temporal._time('2026-10-22T10:37:00Z'))
    assert error is None and selected['source_sha256'] == history[2]['source_sha256']
    assert selected['revision_sha256'] == history[0]['revision_sha256']


def test_partial_poll_rows_not_visible_until_all_mandatory_responses_completed(projection, protocol):
    _, timeline = m.validate_projection(projection, protocol, CONTEXT)
    row = next(r for r in timeline if r['symbol'] == 'BTCUSDT')
    assert row['known_at'] == projection['polls'][0]['completed_at']
    assert m.temporal._time(row['observed_at']) < m.temporal._time(row['known_at'])
    index = {('BTCUSDT', row['open_time']): [row]}
    chosen, error = m.temporal._choose(index, 'BTCUSDT', m.temporal._time(row['open_time']), m.temporal._time(row['observed_at']))
    assert chosen is None and error == 'late'


def test_native_negative_history_stays_explicit_no_synthetic_rows(native_fixture, tmp_path, protocol, exposure):
    project, _ = native_fixture
    reference = json.loads((project.parent/'failed-reference.json').read_text())
    projection = m._project(project, reference, protocol, tmp_path)
    report = m.audit(projection, protocol, exposure, CONTEXT)
    assert report['native_audit']['source_trace_integrity_pass'] is True
    assert report['observed_deliveries'] == 0 and report['unique_versions'] == 0
    assert report['samples_metadata_consistent'] == 0 and report['status'] == 'blocked'
    assert all('mandatory_reference_unavailable_or_stale' in s['issues'] for s in report['samples'])


def test_failed_latest_poll_does_not_reuse_earlier_success(native_fixture, tmp_path, protocol, exposure):
    project, _ = native_fixture
    reference = json.loads((project.parent/'mixed-reference.json').read_text())
    projection = m._project(project, reference, protocol, tmp_path)
    report = m.audit(projection, protocol, exposure, CONTEXT)
    assert report['native_audit']['latest_status'] == {'BTC/USDT': 'unavailable', 'ETH/USDT': 'unavailable'}
    assert report['observed_deliveries'] == 240
    assert all('mandatory_reference_unavailable_or_stale' in s['issues'] for s in report['samples'][2:])


def test_late_input_and_label_cutoffs_stay_explicit(projection, protocol, exposure):
    protocol['decision_delay_seconds'] = 0
    protocol['fit_information_end'] = '2026-10-22T10:15:00Z'
    report = m.audit(projection, protocol, exposure, CONTEXT)
    assert report['status'] == 'blocked'
    assert 'feature_late' in report['samples'][0]['issues']
    assert 'label_late' in report['samples'][0]['issues']
    assert 'mandatory_reference_unavailable_or_stale' in report['samples'][0]['issues']


def test_old_good_poll_is_not_fresh_for_later_decision(projection, protocol, exposure):
    protocol['partitions']['validation'] = {'decision_start': '2026-10-22T11:10:00Z', 'decision_end': '2026-10-22T11:15:00Z'}
    protocol['validation_information_end'] = '2026-10-22T11:30:00Z'
    report = m.audit(projection, protocol, exposure, CONTEXT)
    assert 'mandatory_reference_unavailable_or_stale' in report['samples'][-1]['issues']


@pytest.mark.parametrize('change', [
    lambda p:p.update(network_request_performed=True),
    lambda p:p.update(forecast_or_inference_performed=True),
    lambda p:p['native_audit'].update(forecasts_checked=1),
    lambda p:p['native_audit'].update(forecasts_checked=False),
    lambda p:p['native_audit'].update(source_poll_completeness_verified=True),
    lambda p:p['native_audit'].update(original_source_forecast_linkage_pass=True),
    lambda p:p['native_audit'].update(scope='prospective'),
    lambda p:p['native_audit'].update(events_checked=15),
    lambda p:p['native_audit'].update(versions_checked=1),
    lambda p:p['loaded_source_hashes'].update(backend='a'*64),
    lambda p:p['rows'][0].update(source_id='a'*64),
    lambda p:p['rows'][0].update(first_seen_at='2026-10-22T10:40:00Z'),
    lambda p:p['rows'][0].update(observed_at='2026-10-22T09:00:00Z'),
    lambda p:p['rows'][0].update(event_seq=999),
    lambda p:p['rows'][0].update(response_sha256='a'*64),
    lambda p:p['rows'][0].update(open_ms=p['rows'][0]['open_ms']+1),
    lambda p:p['rows'].pop(),
    lambda p:p['rows'].append(deepcopy(p['rows'][0])),
    lambda p:p['polls'][0]['responses'].pop(),
    lambda p:p['polls'][0]['responses'][0].update(event_seq=999),
    lambda p:p['polls'][0]['responses'][0].update(latest_close_ms=0),
    lambda p:p['polls'][0]['responses'][0].update(status='stale'),
    lambda p:p['polls'][0].update(completed_at='2026-10-23T08:00:00Z'),
    lambda p:p['polls'][1].update(anchor_ms=p['polls'][0]['anchor_ms']),
    lambda p:p['source_manifest'].update(mandatory_pairs=[]),
])
def test_projected_provenance_cannot_be_reinterpreted_as_admission(projection, protocol, exposure, change):
    change(projection)
    with pytest.raises((ValueError, TypeError, KeyError)):
        m.audit(projection, protocol, exposure, CONTEXT)


def test_source_after_development_cutoff_refused_before_native_replay(native_fixture, tmp_path):
    project, reference = native_fixture
    protocol = {'validation_information_end': '2026-10-22T10:40:00Z', 'partitions': {'final_test': {'decision_start': '2026-10-24T00:00:00Z'}}}
    with pytest.raises(ValueError, match='native_reference_projection_refused'):
        m._project(project, reference, protocol, tmp_path)
    assert not list(reference_path(reference).parent.glob('reference-audit-*'))


def reference_path(reference): return Path(reference['root'])


def test_private_prepare_verify_original_bytes_and_no_scratch_leak(native_fixture, tmp_path, protocol, exposure):
    project, reference = native_fixture
    original = hashlib.sha256((reference_path(reference)/'source.sqlite').read_bytes()).hexdigest()
    report = m.prepare(tmp_path/'pack', project, reference, protocol, exposure)
    assert m.verify(tmp_path/'pack') == report
    assert hashlib.sha256((reference_path(reference)/'source.sqlite').read_bytes()).hexdigest() == original
    assert not list(tmp_path.glob('reference-projection-*'))
    assert not list(reference_path(reference).parent.glob('reference-audit-*'))
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode) == 0o700
    for path in (tmp_path/'pack').iterdir(): assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match='new_revision_audit'):
        m.prepare(tmp_path/'pack', project, reference, protocol, exposure)
    stored = json.loads((tmp_path/'pack/audit.json').read_text())
    stored['training_data_admitted'] = True
    stored['audit_sha256'] = digest({k:v for k,v in stored.items() if k != 'audit_sha256'})
    (tmp_path/'pack/audit.json').write_text(canonical(stored)+'\n')
    with pytest.raises(ValueError, match='revision_audit_or_implementation'):
        m.verify(tmp_path/'pack')


def test_reference_pin_and_runtime_mismatch_refused(native_fixture):
    project, reference = native_fixture
    bad = {**reference, 'database_sha256': 'a'*64}
    with pytest.raises(ValueError, match='pin_mismatch'): m._reference(bad, project)
    with pytest.raises(ValueError): m._reference({**reference, 'extra': True}, project)


def test_fixed_policy_and_config(projection, protocol, exposure):
    config = Path(m.__file__).parents[2]/'config/research-revision-bridge-v1.json'
    assert json.loads(config.read_text()) == m.POLICY
    with pytest.raises(ValueError, match='fixed_revision'):
        m.audit(projection, protocol, exposure, CONTEXT, {**m.POLICY, 'maximum_events': 129})


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('fixed',15), KeyboardInterrupt()])
def test_fixed_worker_environment_deadline_kill_and_reap(monkeypatch, tmp_path, protocol, failure):
    observed = {}
    class Process:
        pid = 43210
        calls = 0
        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1: raise failure
            return 0
    process = Process()
    def popen(args, **kwargs): observed.update(args=args, **kwargs); return process
    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    monkeypatch.setattr(m.os, 'killpg', lambda pid,sig:observed.update(killed=pid))
    with pytest.raises(type(failure)):
        m._project(tmp_path, {}, protocol, tmp_path)
    assert process.calls == 2 and observed['killed'] == 43210
    assert observed['stdin'] == subprocess.DEVNULL and observed['start_new_session'] is True
    assert 'research_revision_worker.py' in observed['args'][2]
    assert set(observed['env']) == {'PATH','PYTHONPATH','PYTHONDONTWRITEBYTECODE','LANG','TZ','PYTHONHASHSEED'}


def test_safe_cli_failure_omits_paths_and_exception(tmp_path, capsys):
    assert m.main(['verify','--directory',str(tmp_path/'secret-name')]) == 2
    output = capsys.readouterr().out
    assert 'secret-name' not in output and 'Traceback' not in output
