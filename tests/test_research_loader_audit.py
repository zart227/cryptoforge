"""Native latest-at-fit loader must not masquerade as causal runtime selection."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys

import pytest
from cryptoforge import research_loader_audit as m
from cryptoforge.training_diagnostics import canonical,digest
import test_research_revision_bridge as previous
from test_research_revision_bridge import native_fixture
from test_research_value_audit import value_base


@pytest.fixture(scope='module')
def loader_base(value_base,tmp_path_factory):
    project,source,*_=value_base
    directory=tmp_path_factory.mktemp('loader-source')/'values'
    m.values.prepare(directory,project,source)
    binding,packet,selections,expected=m.bind(directory)
    native=m._run(project,packet,directory.parent)
    return project,directory,binding,packet,selections,expected,native


def compose(base,native=None):
    _,_,binding,packet,selections,expected,saved=base
    return m.compose(binding,packet,selections,expected,saved if native is None else native)


def test_real_native_loader_detects_revised_train_feature_and_label(loader_base):
    report=compose(loader_base)
    assert report['status']=='blocked' and report['value_comparisons']==4
    assert report['value_mismatches']==2 and report['version_mismatch_samples']==2
    assert report['native_loader_invocations']==2 and report['native_reader_calls']==4
    train=[s for s in report['samples'] if s['partition']=='train']
    validation=[s for s in report['samples'] if s['partition']=='validation']
    assert all(s['values_match'] is False and s['version_differences']=={'feature':1,'label':0} for s in train)
    assert all(s['compatible'] and s['values_match'] and s['version_differences']=={'feature':0,'label':0} for s in validation)
    assert all(s['training_status']=='checked' for s in loader_base[-2]['samples'])
    # Common-core M15 parity alone passed; invoking the actual loader exposes revisions.
    assert m.values.verify(loader_base[1])['status']=='values_consistent'
    assert report['actual_native_loader_checked'] is True
    for key in ('operational_postgresql_reader_checked','production_lookback_config_verified','training_data_admitted',
                'fit_performed','model_prediction_performed','provider_called','candidate_numeric_worker_executed',
                'production_promotion_authorized','statistical_validation_complete'):
        assert report[key] is False


def test_snapshot_selection_preserves_original_known_at_and_only_uses_development(loader_base):
    packet=loader_base[3]
    assert [s['partition'] for s in packet['sessions']]==['train','validation']
    assert all(s['pairs']==['BTC/USDT','ETH/USDT'] for s in packet['sessions'])
    for session in packet['sessions']:
        cutoff=m.values.temporal._time(session['as_of'])
        for rows in session['rows'].values():
            assert len(rows)<=512
            assert all(m.values.temporal._time(r['known_at'])<=cutoff for r in rows)
            assert all(m.values.temporal._time(r['open_time'])+timedelta(minutes=5)<=cutoff for r in rows)
            assert len({r['open_time'] for r in rows})==len(rows)
    causal=loader_base[4][0]['features'][-1]
    current=next(r for r in packet['sessions'][0]['rows']['BTC/USDT'] if r['open_time']==causal['open_time'])
    assert current['source_id']==causal['source_id'] and current['revision_sha256']!=causal['revision_sha256']
    assert current['known_at']>causal['known_at']


def test_current_cutoff_does_not_erase_original_unavailable_causal_training(loader_base):
    native=deepcopy(loader_base[-1]);expected=deepcopy(loader_base[-2]);expected['samples'][0]['training_status']='unavailable'
    report=m.compose(loader_base[2],loader_base[3],loader_base[4],expected,native)
    assert report['samples'][0]['values_match'] is None
    assert report['samples'][0]['version_differences'] is None
    assert report['samples'][0]['issues']==['causal_training_example_unavailable']
    assert report['status']=='blocked'


@pytest.mark.parametrize('alter',[
    lambda n:n.update(fit_performed=True),lambda n:n.update(network_request_performed=True),
    lambda n:n.update(model_prediction_performed=True),lambda n:n.update(operational_postgresql_reader_checked=True),
    lambda n:n.update(actual_native_loader_invoked=False),lambda n:n.update(packet_sha256='a'*64),
    lambda n:n['loaded_value_runtime'].update(model_training='a'*64),
    lambda n:n.update(decimal_precision=50),lambda n:n.update(source_rows_read=0),
    lambda n:n['sessions'][0]['reader_trace'][0].update(limit=256),
    lambda n:n['sessions'][0]['reader_trace'][0].update(returned=0),
    lambda n:n['sessions'][0]['samples'][0]['example'].update(long_label=True),
    lambda n:n['sessions'][0]['samples'][0]['example'].update(future_return_hex='nan'),
    lambda n:n['sessions'][0]['samples'][0]['example'].update(label_end_time='2026-10-24T00:00:00Z'),
    lambda n:n['sessions'][0]['samples'].reverse(),
])
def test_native_contract_or_reader_trace_cannot_be_forged(loader_base,alter):
    native=deepcopy(loader_base[-1]);alter(native)
    with pytest.raises(ValueError):compose(loader_base,native)


@pytest.mark.parametrize('change',[
    lambda p:p['sessions'][0]['rows']['BTC/USDT'][0].update(known_at='2026-10-24T00:00:00Z'),
    lambda p:p['sessions'][0]['rows']['BTC/USDT'][0].update(revision_sha256='a'*64),
    lambda p:p['sessions'][0]['rows']['BTC/USDT'].reverse(),
])
def test_native_worker_refuses_future_missing_or_unordered_original_versions(loader_base,tmp_path,change):
    packet=deepcopy(loader_base[3]);change(packet)
    with pytest.raises(ValueError,match='native_loader_check_refused'):m._native(loader_base[0],packet,tmp_path)


def test_prepare_and_fresh_native_verify_preserve_private_files_and_original_source(loader_base,tmp_path):
    project,value_pack,*_=loader_base
    reference=loader_base[3]['reference'];database=Path(reference['root'])/'source.sqlite'
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    directory=tmp_path/'loader';report=m.prepare(directory,project,value_pack)
    assert m.verify(directory)==report
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before
    assert stat.S_IMODE(directory.stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in directory.iterdir())
    with pytest.raises(ValueError,match='new_loader_audit'):m.prepare(directory,project,value_pack)
    native=json.loads((directory/'native.json').read_text())
    native['sessions'][0]['samples'][0]['example']['feature_hex'][0]=float(.123).hex()
    (directory/'native.json').write_text(canonical(native)+'\n')
    with pytest.raises(ValueError,match='fresh_native_loader_replay_differs'):m.verify(directory)


def test_rehashed_audit_admission_forgery_rejected(loader_base,tmp_path):
    directory=tmp_path/'loader';m.prepare(directory,loader_base[0],loader_base[1])
    report=json.loads((directory/'audit.json').read_text());report['training_data_admitted']=True
    report['audit_sha256']=digest({k:v for k,v in report.items() if k!='audit_sha256'})
    (directory/'audit.json').write_text(canonical(report)+'\n')
    with pytest.raises(ValueError,match='loader_audit_or_implementation_changed'):m.verify(directory)


def test_config_policy_and_original_source_hash_pins(loader_base):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-loader-audit-v1.json').read_text())==m.POLICY
    with pytest.raises(ValueError,match='fixed_loader_policy'):m.compose(*loader_base[2:],{**m.POLICY,'lookback_candles':1024})


def test_cli_prepare_verify_and_refusal(loader_base,tmp_path):
    base=Path(m.__file__).parents[2];directory=tmp_path/'cli'
    for args in (["prepare","--project",str(loader_base[0]),"--value-pack",str(loader_base[1])],['verify']):
        p=subprocess.run([sys.executable,'-B','-m','cryptoforge.research_loader_audit',*args,'--directory',str(directory)],
            cwd=base,env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(base/'src'),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=20)
        assert p.returncode==0 and 'blocked; admission disabled' in p.stdout
    assert m.main(['verify','--directory',str(tmp_path/'missing')])==2


def variant_value_pack(loader_base,tmp_path,*,volume_revision=False):
    project=loader_base[0]
    script=(project.parent/'make.py').read_text()
    old="close='100.5' if anchor==start+900000 and opened==start-300000 else '101'"
    assert script.count(old)==1;script=script.replace(old,"close='101'")
    if volume_revision:
        old="rows.append([str(opened),'100','102','99',close,'10','1000'])"
        assert script.count(old)==1
        script=script.replace(old,"rows.append([str(opened),'100','102','99',close,('11' if anchor==start+900000 and opened==start-300000*100 else '10'),'1000'])")
    maker=tmp_path/'make.py';maker.write_text(script)
    source_root=project/'.local'/tmp_path.name/'ledger';source_root.parent.mkdir(parents=True)
    reference=tmp_path/'reference.json'
    subprocess.run([sys.executable,'-B',str(maker),str(source_root),str(reference)],cwd=project,
        env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(project/'src'),'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'},capture_output=True,check=True,timeout=15)
    source=tmp_path/'revision'
    m.values.revisions.prepare(source,project,json.loads(reference.read_text()),previous.protocol.__wrapped__(),previous.exposure.__wrapped__())
    value=tmp_path/'values';m.values.prepare(value,project,source)
    return value


def test_real_native_loader_all_samples_match_when_original_versions_stable(loader_base,tmp_path):
    value=variant_value_pack(loader_base,tmp_path)
    report=m.prepare(tmp_path/'loader',loader_base[0],value)
    assert report['status']=='loader_matches_causal_samples'
    assert report['value_comparisons']==4 and report['value_mismatches']==0 and report['version_mismatch_samples']==0
    assert all(s['compatible'] for s in report['samples'])
    assert report['training_data_admitted'] is False


def test_changed_original_version_is_visible_even_when_all_feature_values_match(loader_base,tmp_path):
    value=variant_value_pack(loader_base,tmp_path,volume_revision=True)
    report=m.prepare(tmp_path/'loader',loader_base[0],value)
    assert report['status']=='blocked' and report['value_mismatches']==0 and report['version_mismatch_samples']==2
    assert all(s['values_match'] for s in report['samples'])
    assert all(s['issues']==['native_loader_versions_differ_from_decision_asof'] for s in report['samples'] if s['partition']=='train')


def test_native_loader_stale_source_exclusion_remains_missing_example(loader_base,tmp_path):
    packet=deepcopy(loader_base[3]);packet['sessions'][0]['as_of']='2026-10-22T10:26:00Z'
    native=m._native(loader_base[0],packet,tmp_path)
    train=native['sessions'][0]
    assert train['source_admission']['coverage_fraction']==0.0
    assert all(reason=='stale closed training source' for reason in train['source_admission']['excluded_pairs'].values())
    assert all(s['example'] is None for s in train['samples'])
    report=m.compose(loader_base[2],packet,loader_base[4],loader_base[-2],native)
    assert all(s['values_match'] is None and s['version_differences'] is None and s['issues']==['native_loader_example_unavailable'] for s in report['samples'] if s['partition']=='train')
    assert report['status']=='blocked'
