from decimal import Decimal
import json
import pytest

from cryptoforge.archive import ArchiveReader, download_archive
from cryptoforge.market_data import Candle
from cryptoforge.model_training import build_examples, extract_features
from test_model_training import make_training_candles


def test_paginated_archive_excludes_open_candle_and_resumes(tmp_path):
    class Client:
        calls=0
        def get_klines(self,symbol,interval,limit,*,start_ms,end_ms):
            self.calls+=1
            stamps=[i*300000 for i in range(1201) if start_ms <= i*300000 <= end_ms][-1000:]
            return [Candle(symbol,interval,t,*(Decimal(1) for _ in range(6))) for t in stamps]
    client=Client()
    report=download_archive(client,'BTCUSDT','5',0,1200*300000+1000,tmp_path,pause=0)
    assert report['candles']==1200
    assert report['missing_candles']==0
    assert client.calls==2
    download_archive(client,'BTCUSDT','5',0,1200*300000,tmp_path,pause=0)
    assert client.calls==2
    reader=ArchiveReader(tmp_path)
    assert len(reader.read_candles('BTC/USDT',limit=2000))==1200
    rows=json.loads((tmp_path/'BTCUSDT-5.json').read_text())
    rows.pop(100)
    (tmp_path/'BTCUSDT-5.json').write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='gaps'):
        reader.read_candles('BTC/USDT',limit=2000)


def test_linear_feature_builder_preserves_full_history_features():
    candles=make_training_candles(400)
    examples=build_examples('ETH/USDT',candles,horizon_candles=3)
    for index in (36,100,300,396):
        expected=extract_features(candles[:index+1],[c.volume for c in candles[:index+1]])
        assert examples[index-36].features == pytest.approx(expected,abs=1e-14)
