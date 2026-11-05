"""Native default JSON precision, exact same-wire replay and local-only query bounds."""
import base64
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
from pathlib import Path
import stat

import pytest
from cryptoforge import research_native_rest_audit as m
from cryptoforge.research_training_diagnostics import canonical,digest
from test_research_revision_bridge import native_fixture
from test_research_value_audit import value_base


CUTOFF='2026-10-22T10:16:00+00:00'


def packet(*,numbers=False,empty=False,late=False):
    wires={};last=datetime(2026,10,22,10,10,tzinfo=timezone.utc)
    for pair in m.POLICY['pairs']:
        records=[]
        for i in range(0 if empty else 144):
            row={'pair':pair,'symbol':pair.replace('/',''),'open_time':(last-timedelta(minutes=5*i)).isoformat(),
                'open':'12345.123456789123','high':'12346.123456789123','low':'12344.123456789123',
                'close':'12345.123456789123','volume':'12345678.123456789123',
                'ingested_at':'2026-10-22T10:17:00+00:00' if late else '2026-10-22T10:15:30+00:00'}
            raw=canonical(row)
            if numbers:
                for value in set(row[k] for k in ('open','high','low','close','volume')):raw=raw.replace(json.dumps(value),value)
            records.append(raw)
        raw=('['+','.join(records)+']').encode()
        wires[pair]={'body_base64':base64.b64encode(raw).decode(),'retrieved_at':'2026-10-22T10:15:31+00:00'}
    return {'mode':'retained_wire_replay','as_of':CUTOFF,'wires':wires}


@pytest.fixture(scope='module')
def rest_base(value_base,tmp_path_factory):
    project=value_base[0];parent=tmp_path_factory.mktemp('rest-fixture')
    request=packet();result=m._native(project,request,parent)
    return project,request,result


def test_actual_native_reader_exact_string_quotes_and_same_wire_loader(rest_base):
    project,request,result=rest_base;report=m.compose(request,result)
    assert report['status']=='available_scalars_match_wire'
    assert report['comparison']['scalar_fields_checked']==1440 and report['comparison']['scalar_mismatch_count']==0
    assert len(report['comparison']['native']['examples'])==44
    assert report['comparison']['all_native_examples_equal_exact_parser'] is True
    assert report['actual_local_api_requests']==0 and not report['operational_native_reader_exercised']
    assert all(r['query']['limit']==['144'] and r['method']=='GET' and not r['auth_values_copied'] for r in result['trace'])
    assert not report['historical_first_seen_or_revisions_verified'] and not report['training_data_admitted']


def test_numeric_wire_precision_loss_is_visible_and_exact_parser_uses_original_bytes(rest_base,tmp_path):
    request=packet(numbers=True);result=m._native(rest_base[0],request,tmp_path);report=m.compose(request,result)
    assert report['status']=='decimal_transport_mismatch' and report['comparison']['scalar_mismatch_count']>0
    samples=report['comparison']['scalar_mismatch_examples'];assert 1<=len(samples)<=12
    assert any(Decimal(s['wire_decimal'])!=Decimal(s['native_decimal']) for s in samples)
    assert len(report['comparison']['exact_same_wire']['examples'])==44
    assert result['wires']==request['wires'] and result['local_api_requests']==0


def test_empty_response_is_not_a_vacuous_training_success(rest_base,tmp_path):
    request=packet(empty=True);result=m._native(rest_base[0],request,tmp_path);report=m.compose(request,result)
    assert report['status']=='no_rows_available' and report['comparison']['scalar_fields_checked']==0
    assert report['comparison']['native']['examples']==[] and not report['training_data_admitted']


def test_native_postlimit_asof_filter_excludes_rows_updated_after_cutoff(rest_base,tmp_path):
    request=packet(late=True);result=m._native(rest_base[0],request,tmp_path);report=m.compose(request,result)
    assert report['comparison']['native']['examples']==[]
    assert all('no known closed' in v for v in report['comparison']['native']['source_admission']['excluded_pairs'].values())
    assert report['comparison']['reader_query_contains_asof_filter'] is False


@pytest.mark.parametrize('change',[
    lambda r:r.update(fit_performed=True),lambda r:r.update(database_writes=True),
    lambda r:r.update(model_prediction_performed=True),lambda r:r.update(local_api_requests=2),
    lambda r:r.update(as_of='2026-10-24T00:00:00Z'),lambda r:r['loaded_value_runtime'].update(model_training='a'*64),
    lambda r:r['comparison'].update(scalar_mismatch_count=1441),
    lambda r:r['comparison'].update(reader_query_contains_asof_filter=True),
    lambda r:r['trace'].reverse(),
])
def test_native_contract_or_scope_claim_tampering_refused(rest_base,change):
    result=deepcopy(rest_base[-1]);change(result)
    with pytest.raises(ValueError):m.compose(rest_base[1],result)


@pytest.mark.parametrize('mutation',[
    lambda rows:rows[0].update(pair='AVAX/USDT'),lambda rows:rows[0].update(ingested_at=None),
    lambda rows:rows[0].update(volume='NaN'),lambda rows:rows[0].update(close='1e100000'),
    lambda rows:rows[0].update(close='1e-18'),lambda rows:rows.append(rows[0]),
])
def test_invalid_raw_row_cannot_be_normalized_into_valid_native_evidence(rest_base,tmp_path,mutation):
    request=packet();wire=request['wires']['BTC/USDT'];rows=json.loads(base64.b64decode(wire['body_base64']))
    mutation(rows);wire['body_base64']=base64.b64encode(canonical(rows).encode()).decode()
    with pytest.raises(ValueError,match='native_local_rest_worker_refused'):m._native(rest_base[0],request,tmp_path)


def test_private_pack_fresh_replay_rejects_rehashed_transport_or_admission_forgery(rest_base,tmp_path):
    project,request,_=rest_base;directory=tmp_path/'pack';report=m._prepare(directory,project,request)
    assert m.verify(directory)==report
    assert stat.S_IMODE(directory.stat().st_mode)==0o700 and all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in directory.iterdir())
    with pytest.raises(ValueError):m._prepare(directory,project,request)
    result=json.loads((directory/'native.json').read_text());result['comparison']['scalar_mismatch_count']=1
    (directory/'native.json').write_text(canonical(result)+'\n')
    with pytest.raises(ValueError,match='retained_wire_native_replay_differs'):m.verify(directory)


def test_future_cutoff_and_policy_expansion_are_not_admitted(tmp_path):
    with pytest.raises(ValueError):m.prepare(tmp_path/'pack',tmp_path,as_of='2100-01-01T00:00:00Z')
    with pytest.raises(ValueError):m._guard({**m.POLICY,'maximum_local_gets':3})
    assert json.loads((Path(m.__file__).parents[2]/'config/research-native-rest-audit-v1.json').read_text())==m.POLICY
    assert m.main(['verify','--directory',str(tmp_path/'missing')])==2


def test_duplicate_json_fields_are_rejected_before_native_last_wins_parsing(rest_base,tmp_path):
    request=packet();wire=request['wires']['BTC/USDT'];raw=base64.b64decode(wire['body_base64'])
    needle=b'"pair":"BTC/USDT"';assert needle in raw
    raw=raw.replace(needle,needle+b',"pair":"BTC/USDT"',1);wire['body_base64']=base64.b64encode(raw).decode()
    with pytest.raises(ValueError):m._native(rest_base[0],request,tmp_path)


def test_cli_native_timeout_is_safe_refusal_without_retry(rest_base,tmp_path,monkeypatch):
    calls=[]
    def timeout(*a,**k):
        calls.append(1);raise m.subprocess.TimeoutExpired('fixed native reader',15)
    monkeypatch.setattr(m,'_native',timeout)
    assert m.main(['prepare','--directory',str(tmp_path/'timeout'),'--project',str(rest_base[0])])==2
    assert calls==[1] and not (tmp_path/'timeout').exists()
