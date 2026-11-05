"""Native closed-window compatibility, exact price-label reference and refusal paths."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

from cryptoforge import research_value_audit as m
from cryptoforge.research_training_diagnostics import digest,canonical
import test_research_revision_bridge as previous
from test_research_revision_bridge import native_fixture


@pytest.fixture(scope='module')
def value_base(native_fixture,tmp_path_factory):
    project,reference=native_fixture
    for name in m.REVIEWED_VALUE_RUNTIME:
        relative=Path('src/cryptoforge')/('__init__.py' if name=='cryptoforge' else name+'.py')
        from cryptoforge import research_reviewed_main_runtime as reviewed_main
        reviewed_main.copy_live_main_path(relative, project/relative)
    protocol=previous.protocol.__wrapped__();exposure=previous.exposure.__wrapped__()
    directory=tmp_path_factory.mktemp('source-value-base')/'revision'
    m.revisions.prepare(directory,project,reference,protocol,exposure)
    binding,reference,selections=m.bind_source_pack(directory)
    temporary=tmp_path_factory.mktemp('native-values')
    native=m._native(project,reference,selections,m.TARGET,temporary)
    return project,directory,binding,reference,selections,native


def compose(base,*,native=None,target=None):
    _,_,binding,reference,selections,saved=base
    return m.compose(binding,reference,selections,target or m.TARGET,native or saved)


def test_native_features_runtime_training_and_reference_match(value_base):
    report=compose(value_base)
    assert report['status']=='values_consistent'
    assert report['native_feature_windows_checked']==4 and report['native_training_examples_checked']==4
    assert report['source_rows_read']==492 and report['numeric_mismatch_samples']==0
    assert report['complete_numeric_samples']==4
    assert all(s['extractor_runtime_bit_parity'] and s['training_runtime_bit_parity'] for s in report['samples'])
    assert all(s['fraction_return_and_labels_match_native'] for s in report['samples'])
    for key in ('training_data_admitted','target_parameters_approved','independent_full_feature_oracle_verified',
                'main_trainer_actual_source_selection_verified','fit_performed','model_prediction_performed',
                'numeric_prototype_worker_executed','provider_called','production_promotion_authorized'):
        assert report[key] is False


def test_native_label_time_convention_and_equality_threshold(value_base):
    native=value_base[-1]
    sample=native['samples'][0]
    assert sample['training_input_end_time']=='2026-10-22T09:55:00+00:00'
    assert sample['label_end_time']=='2026-10-22T10:15:00+00:00'
    assert sample['future_return_hex']==float(0).hex() and sample['long_label']==sample['short_label']==0


@pytest.mark.parametrize('future,threshold,long,short',[
    ('101','0',1,0),('99','0',0,1),('100','0',0,0),
    ('100.3','0.003',0,0),('99.7','0.003',0,0),('100.4','0.003',1,0),('99.6','0.003',0,1),
])
def test_exact_decimal_quote_return_and_strict_float_domain_labels(value_base,future,threshold,long,short):
    native=deepcopy(value_base[-1]);target={**m.TARGET,'min_label_return':threshold,'round_trip_cost':'0'}
    native['target_sha256']=digest(target)
    for sample in native['samples']:
        sample.update(reference_close='100',future_close=future,
            future_return_hex=float((m._endpoint(future)-m._endpoint('100'))/m._endpoint('100')).hex(),
            long_label=long,short_label=short)
    report=compose(value_base,native=native,target=target)
    assert report['numeric_mismatch_samples']==0
    assert all(s['fraction_float_domain_labels']==[long,short] for s in report['samples'])


def test_label_reference_mismatch_stays_a_recorded_failure(value_base):
    native=deepcopy(value_base[-1]);native['samples'][0]['future_return_hex']=float(.5).hex()
    report=compose(value_base,native=native)
    assert report['status']=='blocked' and report['numeric_mismatch_samples']==1
    assert report['samples'][0]['fraction_return_and_labels_match_native'] is False


@pytest.mark.parametrize('price,expected_long,expected_short',[('102',1,0),('99',0,1),('101.303',0,0)])
def test_real_native_producer_future_changes_labels_without_changing_prior_features(value_base,tmp_path,price,expected_long,expected_short):
    project,_,_,_,_,original=value_base
    script=(project.parent/'make.py').read_text()
    old="close='100.5' if anchor==start+900000 and opened==start-300000 else '101'"
    assert script.count(old)==1
    script=script.replace(old,"close="+repr(price)+" if opened==start+600000 else ('100.5' if anchor==start+900000 and opened==start-300000 else '101')")
    path=tmp_path/'make-variant.py';path.write_text(script)
    source_root=project/'.local/variants'/tmp_path.name/'ledger';source_root.parent.mkdir(parents=True)
    ref_path=tmp_path/'reference.json'
    subprocess.run([sys.executable,'-B',str(path),str(source_root),str(ref_path)],cwd=project,
        env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(project/'src'),'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'},
        capture_output=True,check=True,timeout=15)
    source_pack=tmp_path/'revision'
    m.revisions.prepare(source_pack,project,json.loads(ref_path.read_text()),previous.protocol.__wrapped__(),previous.exposure.__wrapped__())
    binding,reference,selections=m.bind_source_pack(source_pack)
    native=m._native(project,reference,selections,m.TARGET,tmp_path)
    result=native['samples'][0]
    assert result['long_label']==expected_long and result['short_label']==expected_short
    assert result['extractor_feature_hex']==original['samples'][0]['extractor_feature_hex']
    assert result['training_feature_hex']==original['samples'][0]['training_feature_hex']
    assert m.compose(binding,reference,selections,m.TARGET,native)['numeric_mismatch_samples']==0


def test_worker_rejects_selected_values_observed_after_decision(value_base,tmp_path):
    project,_,_,reference,selections,_=value_base
    selections=deepcopy(selections);selections[0]['features'][0]['known_at']='2026-10-24T00:00:00Z'
    with pytest.raises(ValueError,match='native_value_compatibility_refused'):
        m._native(project,reference,selections,m.TARGET,tmp_path)


@pytest.mark.parametrize('field',['runtime_feature_hex','extractor_feature_hex','training_feature_hex'])
def test_feature_bit_difference_not_hidden_by_tolerance(value_base,field):
    native=deepcopy(value_base[-1]);native['samples'][0][field][0]=float(.123).hex()
    report=compose(value_base,native=native)
    assert report['status']=='blocked' and report['numeric_mismatch_samples']==1


def test_unavailable_labels_never_become_zero_or_fake_training_examples(value_base,tmp_path):
    project,directory,_,_,_,_=value_base
    projection=m.temporal._read(directory,'projection.json',m.revisions.POLICY['maximum_projection_bytes'])
    protocol=m.temporal._read(directory,'protocol.json',64000)
    protocol['fit_information_end']='2026-10-22T10:15:00Z'
    # Native source rows are present, but original poll completion is after this cutoff.
    exposure=previous.exposure.__wrapped__()
    source=tmp_path/'source'
    m.revisions.prepare(source,project,projection['reference'],protocol,exposure)
    binding,reference,selections=m.bind_source_pack(source)
    target=m.TARGET;native=m._native(project,reference,selections,target,tmp_path)
    report=m.compose(binding,reference,selections,target,native)
    assert report['native_feature_windows_checked']==4 and report['native_training_examples_checked']==2
    assert native['samples'][0]['future_return_hex'] is None and native['samples'][0]['long_label'] is None
    assert native['samples'][0]['training_status']=='unavailable' and report['status']=='blocked'


@pytest.mark.parametrize('change',[
    lambda n:n.update(fit_performed=True),lambda n:n.update(model_prediction_performed=True),
    lambda n:n.update(network_request_performed=True),lambda n:n.update(decimal_precision=50),
    lambda n:n.update(feature_names=list(reversed(m.POLICY['feature_order']))),
    lambda n:n.update(selections_sha256='a'*64),lambda n:n.update(target_sha256='a'*64),
    lambda n:n.update(source_rows_read=0),lambda n:n['loaded_value_runtime'].update(model_training='a'*64),
    lambda n:n['samples'][0].update(long_label=True),lambda n:n['samples'][0].update(future_return_hex='nan'),
    lambda n:n['samples'][0].update(label_end_time='2026-10-22T10:10:00Z'),
    lambda n:n['samples'][0].update(runtime_feature_hex=['0x0.0p+0']),
])
def test_native_contract_tampering_refused(value_base,change):
    native=deepcopy(value_base[-1]);change(native)
    with pytest.raises(ValueError):compose(value_base,native=native)


@pytest.mark.parametrize('field,value',[
    ('target_version','profit-net-v2'),('fee_accounting','net_after_fees'),('min_label_return','NaN'),
    ('min_label_return',.003),('round_trip_cost','0.1'),('min_label_return','1e-3'),
])
def test_target_not_inferred_or_silently_changed(field,value):
    target={**m.TARGET,field:value}
    with pytest.raises(ValueError):m.validate_target(target)


def test_artifact_private_replay_and_rehashed_result_tampering(value_base,tmp_path,monkeypatch):
    project,source,_,_,_,_=value_base
    report=m.prepare(tmp_path/'pack',project,source)
    monkeypatch.setattr(m,'_native',lambda *_:pytest.fail('offline verify must not run another native worker'))
    assert m.verify(tmp_path/'pack')==report
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode)==0o700
    for p in (tmp_path/'pack').iterdir():assert stat.S_IMODE(p.stat().st_mode)==0o600
    with pytest.raises(ValueError,match='new_value_audit'):m.prepare(tmp_path/'pack',project,source)
    result=json.loads((tmp_path/'pack/audit.json').read_text());result['training_data_admitted']=True
    result['audit_sha256']=digest({k:v for k,v in result.items() if k!='audit_sha256'})
    (tmp_path/'pack/audit.json').write_text(canonical(result)+'\n')
    with pytest.raises(ValueError,match='value_audit_or_implementation'):m.verify(tmp_path/'pack')


def test_policy_config_and_source_pin_guard(value_base):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-value-audit-v1.json').read_text())==m.POLICY
    _,_,binding,reference,selections,native=value_base
    with pytest.raises(ValueError,match='fixed_value_audit'):
        m.compose(binding,reference,selections,m.TARGET,native,{**m.POLICY,'maximum_samples':17})


@pytest.mark.parametrize('failure',[subprocess.TimeoutExpired('fixed',15),KeyboardInterrupt()])
def test_native_worker_fixed_environment_deadline_and_reap(value_base,tmp_path,monkeypatch,failure):
    observed={}
    class Process:
        pid=43210;calls=0
        def wait(self,timeout=None):
            self.calls+=1
            if self.calls==1:raise failure
            return 0
    process=Process()
    def popen(args,**kwargs):observed.update(args=args,**kwargs);return process
    monkeypatch.setattr(m.subprocess,'Popen',popen)
    import os
    monkeypatch.setattr(os,'killpg',lambda pid,sig:observed.update(killed=pid))
    project,_,_,reference,selections,_=value_base
    with pytest.raises(type(failure)):m._native(project,reference,selections,m.TARGET,tmp_path)
    assert process.calls==2 and observed['killed']==43210
    assert observed['stdin']==subprocess.DEVNULL and observed['start_new_session'] is True
    assert set(observed['env'])=={'PATH','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONHASHSEED','LANG','TZ'}


def test_safe_cli_failure_does_not_relay_private_path(tmp_path,capsys):
    assert m.main(['verify','--directory',str(tmp_path/'private-key-value')])==2
    output=capsys.readouterr().out
    assert 'private-key-value' not in output and 'Traceback' not in output
