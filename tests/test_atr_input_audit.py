import json
from scripts import audit_atr_inputs


def test_resource_defer_does_not_overwrite_prior_numeric_audit(tmp_path,monkeypatch):
    output=tmp_path/'audit.json';original='{"status":"completed_input_audit","observed_at":"original"}'
    output.write_text(original)
    def blocked():raise ValueError('insufficient resources: defer research, preserve executor')
    monkeypatch.setattr(audit_atr_inputs,'prepare_research',blocked)
    assert audit_atr_inputs.main(['--output',str(output)])==0
    assert output.read_text()==original
    status=json.loads((tmp_path/'audit-status.json').read_bytes())
    assert not status['completed'] and not status['fit_performed'] and not status['orders_allowed']


def test_bad_frozen_source_is_not_treated_as_temporary_resource_defer(tmp_path,monkeypatch):
    import pytest
    def corrupt():raise ValueError('frozen dataset checksum changed: create a new protocol version')
    monkeypatch.setattr(audit_atr_inputs,'prepare_research',corrupt)
    with pytest.raises(ValueError,match='checksum'):
        audit_atr_inputs.main(['--output',str(tmp_path/'audit.json')])
    assert not (tmp_path/'audit.json').exists()


def test_completed_source_audit_is_cached_without_repeating_input_calculations(tmp_path,monkeypatch):
    from test_trade_simulator import history
    protocol={'baseline_pairs':['ETH/USDT'],'datasets':[{'pair':'ETH/USDT','path':str(tmp_path/'ETHUSDT-5.json'),'sha256':'0'*64}]}
    monkeypatch.setattr(audit_atr_inputs,'prepare_research',lambda:protocol)
    class Reader:
        calls=0
        def __init__(self,*args,**kwargs):pass
        def read_candles(self,*args,**kwargs):
            Reader.calls+=1;return history(count=2000)
    monkeypatch.setattr(audit_atr_inputs,'ArchiveReader',Reader)
    output=tmp_path/'audit.json'
    assert audit_atr_inputs.main(['--output',str(output)])==0
    original=output.read_bytes();report=json.loads(original)
    assert report['cases'][0]['input_cases_checked']==99 and not report['fit_performed']
    assert audit_atr_inputs.main(['--output',str(output)])==0
    assert output.read_bytes()==original and Reader.calls==1
    assert json.loads((tmp_path/'audit-status.json').read_bytes())['status']=='original_completed_audit_preserved'
