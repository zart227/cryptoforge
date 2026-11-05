from datetime import UTC,datetime
import hashlib,json
import urllib.request

import pytest

from cryptoforge.model_registry_observation import model_event_getter,observe_model_registry

NOW=datetime(2030,1,2,12,tzinfo=UTC)


@pytest.fixture
def source(tmp_path):
    p=tmp_path/'audit.json';p.write_text(json.dumps({'schema_version':'model-training-journal-audit-v1',
        'candidate_model_version':'candidate-v2','incumbent_model_version':'incumbent-v1',
        'executed_cash_profit_established':False,'orders_placed':False}))
    return p,hashlib.sha256(p.read_bytes()).hexdigest()


def get(kind):
    version='incumbent-v1' if kind=='model.active' else 'candidate-v2'
    return [{'occurred_at':'2030-01-02T11:00:00+00:00','model_version':version,
             'trained_at':'2030-01-01T00:00:00+00:00','artifact_sha256':'a'*64}],hashlib.sha256(kind.encode()).hexdigest()


def run(source,getter=get):return observe_model_registry(*source,get=getter,clock=lambda:NOW)


def test_registry_event_identity_does_not_claim_loaded_or_profit(source):
    r=run(source)
    assert r['active_event_matches_training_incumbent'] and r['latest_candidate_event_matches_training_candidate']
    assert not r['active_executor_loaded_model_proved'] and not r['executed_cash_profit_established']
    assert not r['database_instance_binding_proved'] and not r['orders_placed']


def test_missing_candidate_is_unknown(source):
    def fetch(kind):return ([],hashlib.sha256(b'[]').hexdigest()) if kind=='model.candidate' else get(kind)
    r=run(source,fetch)
    assert r['events']['model.candidate']['event'] is None and r['latest_candidate_event_matches_training_candidate'] is None


def test_unexpected_fields_or_malformed_identity_fail(source):
    def extra(kind):
        rows,p=get(kind);rows[0]['secret']='never-output';return rows,p
    with pytest.raises(ValueError,match='projection differs'):run(source,extra)
    def bad(kind):
        rows,p=get(kind);rows[0]['artifact_sha256']='not-a-pin';return rows,p
    with pytest.raises(ValueError,match='identity'):run(source,bad)


def test_future_or_retroactive_event_fail(source):
    def future(kind):
        rows,p=get(kind);rows[0]['occurred_at']='2030-01-03T00:00:00+00:00';return rows,p
    with pytest.raises(ValueError,match='future model event'):run(source,future)
    def retro(kind):
        rows,p=get(kind);rows[0]['trained_at']='2030-01-02T11:30:00+00:00';return rows,p
    with pytest.raises(ValueError,match='trained after event'):run(source,retro)


def test_invalid_pin_alias_and_changed_input_fail(source,tmp_path):
    p,h=source
    with pytest.raises(ValueError,match='hash mismatch'):observe_model_registry(p,'0'*64,get=get,clock=lambda:NOW)
    link=tmp_path/'alias';link.symlink_to(p)
    with pytest.raises(ValueError,match='canonical'):observe_model_registry(link,h,get=get,clock=lambda:NOW)
    def changed(kind):p.write_text(p.read_text()+' ');return get(kind)
    with pytest.raises(ValueError,match='changed'):run(source,changed)


def test_only_numeric_loopback_and_model_event_allowlist():
    with pytest.raises(ValueError,match='loopback'):model_event_getter('https://example.org','secret')
    with pytest.raises(ValueError,match='loopback'):model_event_getter('http://localhost:54321','secret')
    fetch=model_event_getter('http://127.0.0.1:54321','secret')
    with pytest.raises(ValueError,match='allowlist'):fetch('trade.opened')


def test_getter_is_get_only_no_proxy_redirect_and_redacts_key(monkeypatch):
    handlers=[];calls=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'[]'
    class Opener:
        def open(self,req,timeout):calls.append(req);return Response()
    def build(*a):handlers.extend(a);return Opener()
    monkeypatch.setattr(urllib.request,'build_opener',build)
    rows,h=model_event_getter('http://127.0.0.1:54321','private-token')('model.active')
    assert rows==[] and h==hashlib.sha256(b'[]').hexdigest()
    assert calls[0].get_method()=='GET' and isinstance(handlers[0],urllib.request.ProxyHandler) and not handlers[0].proxies
    assert 'private-token' not in str((rows,h))


def test_invalid_json_duplicate_or_oversized_results_fail(monkeypatch):
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'[{"model_version":"a","model_version":"b"}]'
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    with pytest.raises(ValueError,match='duplicate'):
        model_event_getter('http://127.0.0.1:54321','token')('model.active')
