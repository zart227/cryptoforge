"""Offline CLI evidence can be audited from its actual original inputs."""
import hashlib,json
from pathlib import Path
from scripts import train_archive_model
from cryptoforge.primary_training_audit import audit_primary_artifact


def test_offline_archive_command_saves_original_inputs_and_runtime(tmp_path,monkeypatch):
    import cryptoforge.research_protocol as research
    path=tmp_path/'ETHUSDT-5.json'
    rows=[{'symbol':'ETHUSDT','interval':'5','start_ms':1767225600000+i*300000,
           'open':'100','high':'101','low':'99','close':'100','volume':'1000','turnover':'100000'} for i in range(1200)]
    path.write_text(json.dumps(rows))
    protocol=json.loads((Path(__file__).resolve().parents[1]/'config/research-protocol-v1.json').read_text())
    protocol['datasets']=[{'pair':'ETH/USDT','path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
    monkeypatch.setattr(research,'prepare_research',lambda:protocol)
    train_archive_model.main(['--pair','ETH/USDT','--directory',str(tmp_path),'--max-candles','1200','--epochs','1'])
    artifact=next((tmp_path/'models').glob('pure-python-logistic-*.json'))
    payload=json.loads(artifact.read_bytes())
    assert payload['live_eligible'] is False and payload['automatic_publication_allowed'] is False
    assert payload['config']['feature_calculation_contract']=='bounded-window-candle-v1'
    audit=audit_primary_artifact(artifact)
    assert audit['status']=='exact_primary_inputs_and_metrics_verified'
    assert audit['current_source_matches_fitted_source'] and not audit['refitting_performed']
