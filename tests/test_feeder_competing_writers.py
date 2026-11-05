from datetime import UTC,datetime
from pathlib import Path
import hashlib,json

import pytest

from cryptoforge.feeder_competing_writers import compare_writers

NOW=datetime(2030,1,2,12,tzinfo=UTC)


def pin(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def setup(tmp_path):
    host=tmp_path/'host.json';selection=tmp_path/'selected.json'
    host.write_text(json.dumps({'services_changed':False,'database_modified':False,'training_journal_synced_pairs':'synced_pairs=AAA/USDT,BBB/USDT\n'}))
    selection.write_text(json.dumps({'historical_effect':'unknown','retry_authorized':False,'observations':[{'pair':'BBB/USDT'},{'pair':'CCC/USDT'}]}))
    return host,pin(host),selection,pin(selection)


def get(table,query):
    assert table=='bot_health' and query['limit']=='1'
    row={'component':'supabase_market_sync','status':'ok','observed_at':'2030-01-02T11:59:00+00:00',
         'payload':{'pairs':['AAA/USDT','BBB/USDT'],'synced_pairs':['AAA/USDT','BBB/USDT'],
                    'failed':{},'host':'private-host'}}
    return [row],hashlib.sha256(b'local-response').hexdigest()


def run(setup,getter=get):return compare_writers(*setup,get=getter,clock=lambda:NOW)


def test_overlap_and_exact_health_match_are_not_attribution(setup):
    r=run(setup)
    assert r['training_and_selected_overlap']==['BBB/USDT']
    assert r['current_local_health']['training_journal_exact_sync_list_match']
    assert r['current_local_health']['selected_and_health_synced_overlap']==['BBB/USDT']
    assert not r['writer_attribution_proved'] and not r['retry_authorized']
    assert not r['journal_entry_timestamp_retained'] and 'private-host' not in json.dumps(r)


def test_no_health_row_is_unknown_not_failure_or_match(setup):
    r=run(setup,lambda *_:([],hashlib.sha256(b'[]').hexdigest()))
    assert r['current_local_health'] is None and r['historical_selected_sync_effect']=='unknown'


def test_secret_error_details_are_not_emitted(setup):
    def with_error(table,query):
        rows,p=get(table,query);rows[0]['payload']['failed']={'AAA/USDT':'private-token-in-error'}
        return rows,p
    r=run(setup,with_error)
    assert r['current_local_health']['failed_pair_count']==1
    assert 'private-token-in-error' not in json.dumps(r)


def test_bad_health_shape_or_future_time_fails(setup):
    def invalid(table,query):
        rows,p=get(table,query);rows[0]['payload']['synced_pairs']=['XXX/USDT'];return rows,p
    with pytest.raises(ValueError,match='outside request'):run(setup,invalid)
    def future(table,query):
        rows,p=get(table,query);rows[0]['observed_at']='2030-01-03T00:00:00+00:00';return rows,p
    with pytest.raises(ValueError,match='future health'):run(setup,future)
    with pytest.raises(ValueError,match='bounded local health'):run(setup,lambda *_:([{},{}],'f'*64))


def test_invalid_journal_and_changed_pin_fail_before_network(setup):
    host,_,selected,sp=setup
    host.write_text(json.dumps({'services_changed':False,'database_modified':False,'training_journal_synced_pairs':'synced_pairs=AAA/USDT\nsynced_pairs=BBB/USDT\n'}))
    with pytest.raises(ValueError,match='single filtered'):compare_writers(host,pin(host),selected,sp,get=get,clock=lambda:NOW)
    with pytest.raises(ValueError,match='hash mismatch'):run(setup)


def test_input_changed_during_request_fails(setup):
    host,_,_,_=setup
    def modify(table,query):
        host.write_text(host.read_text()+' ')
        return get(table,query)
    with pytest.raises(ValueError,match='changed during'):run(setup,modify)


def test_duplicate_or_non_pair_values_fail(setup):
    def duplicate(table,query):
        rows,p=get(table,query);rows[0]['payload']['pairs']=['AAA/USDT','AAA/USDT'];return rows,p
    with pytest.raises(ValueError,match='bounded unique'):run(setup,duplicate)
    def nested(table,query):
        rows,p=get(table,query);rows[0]['payload']['pairs']=[{'value':'AAA/USDT'}];return rows,p
    with pytest.raises(ValueError,match='bounded unique'):run(setup,nested)


def test_output_contains_no_credentials_from_response(setup):
    def private(table,query):
        rows,p=get(table,query);rows[0]['payload']['api_key']='hidden-secret';return rows,p
    r=run(setup,private)
    assert 'hidden-secret' not in json.dumps(r) and r['raw_health_response_retained'] is False
