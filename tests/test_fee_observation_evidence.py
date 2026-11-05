from pathlib import Path
from datetime import timedelta
import json,pytest
from test_fee_observation import NOW,packet
from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.fee_observation import normalize_fee_observation,save_fee_observation
from cryptoforge.fee_observation_evidence import verify_fee_observation
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw


def fixture(tmp_path):
    source=packet();source['time']=int(NOW.timestamp()*1000)
    dependencies={'adapter':BybitPrivateClient,'normalizer':normalize_fee_observation,
        'runner':Path(__file__).resolve().parents[1]/'scripts/capture_spot_account_fees.py'}
    hashes=source_hashes(dependencies)
    return save_fee_observation(tmp_path,source,symbol='APTUSDT',started_at=NOW,observed_at=NOW,now=NOW,
        account_scope='a'*64,implementation_hashes=hashes,runtime_source_bundle=save_runtime_sources(tmp_path,dependencies,hashes))


def test_actual_rate_replay_does_not_certify_fee_currency_or_history(tmp_path):
    ref,receipt=fixture(tmp_path)
    verified=verify_fee_observation(ref,account_scope='a'*64,as_of=NOW)
    assert verified['rates']['takerFeeRate']=='0.0018' and not verified['actual_fill_fee_asset_verified']
    with pytest.raises(ValueError,match='scope'):verify_fee_observation(ref,account_scope='b'*64,as_of=NOW)
    with pytest.raises(ValueError,match='stale'):verify_fee_observation(ref,account_scope='a'*64,as_of=NOW+timedelta(hours=2))


def test_changed_rate_cannot_replace_original_account_response(tmp_path):
    ref,receipt=fixture(tmp_path);receipt['rates']['takerFeeRate']='0'
    changed=_save_raw(tmp_path,json.dumps(receipt,sort_keys=True).encode())
    with pytest.raises(ValueError,match='original response'):verify_fee_observation(changed,account_scope='a'*64,as_of=NOW)
