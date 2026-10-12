import hashlib
import json
from decimal import Decimal
import pytest
from cryptoforge.universe_evidence import verify_probe, DAY_MS


def probe(tmp_path):
    rows = [dict(symbol='TESTUSDT', interval='60', start_ms=i*3600000,
                 open='100', high='101', low='99', close='100', volume='1', turnover='100000')
            for i in range(24)]
    raw = json.dumps({'query':dict(category='spot',symbol='TESTUSDT',interval='60',start=0,end=DAY_MS-1),
                      'candles':rows}).encode()
    path = tmp_path/'evidence.json'; path.write_bytes(raw)
    return dict(symbol='TESTUSDT',snapshot_path=str(path),source_sha256=hashlib.sha256(raw).hexdigest(),
                status='complete_prior_day',candles=24,prior_day_turnover_usdt='2400000',
                prior_day_range_fraction='.02',liquidity_eligible=True)


def test_verified_prior_day_metrics(tmp_path):
    assert verify_probe(probe(tmp_path),as_of_ms=DAY_MS)['turnover']==Decimal('2400000')


def test_future_window_cannot_be_reused(tmp_path):
    with pytest.raises(ValueError,match='prior UTC day'):
        verify_probe(probe(tmp_path),as_of_ms=2*DAY_MS)


def test_tampered_evidence_rejected(tmp_path):
    result=probe(tmp_path); (tmp_path/'evidence.json').write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):
        verify_probe(result,as_of_ms=DAY_MS)


def test_forged_eligible_or_metrics_rejected(tmp_path):
    result=probe(tmp_path);result['prior_day_turnover_usdt']='99999999'
    with pytest.raises(ValueError,match='metrics mismatch'):
        verify_probe(result,as_of_ms=DAY_MS)


def test_older_delisted_response_only_proves_exclusion(tmp_path):
    result=probe(tmp_path)
    path=tmp_path/'evidence.json';evidence=json.loads(path.read_bytes())
    evidence['candles']=evidence['candles'][:1]
    evidence['candles'][0]['start_ms']=-3600000
    raw=json.dumps(evidence).encode();path.write_bytes(raw)
    result.update(source_sha256=hashlib.sha256(raw).hexdigest(),candles=1,
                  status='no_complete_prior_day',liquidity_eligible=False)
    assert not verify_probe(result,as_of_ms=DAY_MS)['eligible']
    result['liquidity_eligible']=True
    with pytest.raises(ValueError,match='eligibility mismatch'):
        verify_probe(result,as_of_ms=DAY_MS)
