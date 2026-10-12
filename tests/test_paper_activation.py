from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import hashlib,json
import pytest

from cryptoforge.live_learning_protocol import load_protocol,time
from cryptoforge.prospective_shadow import ShadowLedger
from cryptoforge.paper_activation import load_activation
from test_prospective_shadow import candidate


def fixtures(tmp_path):
    protocol_path=tmp_path/'protocol.json';raw=Path('config/live-cash-recovery-protocol-v1.json').read_bytes()
    protocol_path.write_bytes(raw);protocol_path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
    protocol=load_protocol(protocol_path)
    manifest,artifact=candidate();artifact_path=tmp_path/'model.json';artifact_bytes=json.dumps(artifact).encode();artifact_path.write_bytes(artifact_bytes)
    manifest.update(artifact_path=str(artifact_path),artifact_sha256=hashlib.sha256(artifact_bytes).hexdigest(),
                    protocol_sha256=hashlib.sha256(raw).hexdigest())
    manifest_path=tmp_path/'candidate.json';manifest_raw=json.dumps(manifest).encode();manifest_path.write_bytes(manifest_raw)
    selected=time(manifest['selected_at']);shadow=tmp_path/'shadow.sqlite';ledger=ShadowLedger(shadow,clock=lambda:selected)
    ledger.freeze_candidate(manifest_raw,registered_at=selected)
    policy_path=tmp_path/'policy.json';policy=json.loads(Path('config/paper-execution-policy-v1.json').read_bytes())
    from cryptoforge.paper_runtime import paper_runtime_hashes
    policy['implementation_hashes']=paper_runtime_hashes()
    policy.update(status='frozen',enabled=True);policy_bytes=json.dumps(policy).encode();policy_path.write_bytes(policy_bytes)
    receipt=ledger.freeze_paper_policy(policy_bytes,protocol_sha=manifest['protocol_sha256'],candidate_sha=manifest['artifact_sha256'])
    policy_path.with_suffix('.freeze.json').write_text(json.dumps(receipt))
    from cryptoforge.paper_acceptance import AcceptanceRegistry
    acceptance_path=tmp_path/'paper-acceptance-policy-v1.json'
    acceptance=json.loads(Path('config/paper-acceptance-policy-v1.json').read_bytes());acceptance['status']='frozen'
    acceptance_raw=json.dumps(acceptance).encode();acceptance_path.write_bytes(acceptance_raw)
    receipt=AcceptanceRegistry(tmp_path/'paper-acceptance-registry.sqlite',clock=lambda:selected).freeze(acceptance_raw,protocol_sha=manifest['protocol_sha256'])
    acceptance_path.with_suffix('.freeze.json').write_text(json.dumps(receipt))
    now=time(protocol['windows']['paper']['start'])+timedelta(days=1,seconds=1)
    return protocol_path,policy_path,manifest_path,shadow,now


def activate(paths):return load_activation(*paths[:4],now=paths[4])


def test_missing_candidate_makes_no_wallet_or_market_connection(tmp_path):
    path=tmp_path/'protocol.json';raw=Path('config/live-cash-recovery-protocol-v1.json').read_bytes();path.write_bytes(raw)
    path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
    result=load_activation(path,tmp_path/'policy.json',tmp_path/'absent.json',tmp_path/'absent.sqlite',
                           now=time('2026-10-08T12:00:00Z'))
    assert not result['enabled'] and not (tmp_path/'absent.sqlite').exists()


def test_qualified_frozen_candidate_and_policy_only_enable_inside_paper_window(tmp_path):
    paths=fixtures(tmp_path);assert activate(paths)['enabled']
    early=(*paths[:4],time('2026-10-08T12:00:00Z'))
    with pytest.raises(ValueError):activate(early)  # future candidate not known yet
    before=(*paths[:4],time('2026-12-17T12:00:00Z'))
    assert activate(before)['status']=='outside_paper_window'


def test_changed_policy_and_forged_receipt_cannot_activate(tmp_path):
    paths=fixtures(tmp_path);p=paths[1]
    policy=json.loads(p.read_bytes());policy['wallet']['capital']='1000';p.write_text(json.dumps(policy))
    with pytest.raises(ValueError,match='changed after'):activate(paths)


def test_receipt_timestamp_alone_is_not_observed_policy_freeze(tmp_path):
    paths=fixtures(tmp_path);p=paths[1].with_suffix('.freeze.json');receipt=json.loads(p.read_bytes())
    receipt['observed_at']='2026-11-19T07:00:00+00:00';p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match='observed immutable'):activate(paths)
