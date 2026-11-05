"""Prove selected-sync partial effects without network or a database."""
import json
import sys

import pytest

import scripts.sync_supabase_market_data as sync


class FakeBybit:
    def __init__(self,*args,**kwargs):pass
    def get_tickers(self,symbol):return [symbol]
    def get_klines(self,symbol,**kwargs):return [symbol]


class FakeClient:
    @classmethod
    def from_env(cls,**kwargs):return cls()


def run_sync(monkeypatch,tmp_path,pairs,*,fault=None):
    effects=[]
    class FakeWriter:
        def __init__(self,client):pass
        def write_tickers(self,records):effects.append(('ticker',records[0]))
        def write_candles(self,records):
            if fault=='interrupt':raise KeyboardInterrupt()
            if fault=='candle-failure' and records[0]==pairs[-1].replace('/',''):
                raise ValueError('simulated candle failure')
            effects.append(('candles',records[0]))
        def write_bot_health(self,component,status,message,payload):effects.append(('health',status,tuple(payload['synced_pairs']),tuple(payload['failed'])))
        def write_selected_universe(self,**kwargs):effects.append(('selected_universe',))
    config=tmp_path/'selected.json';config.write_text(json.dumps({'pairs':pairs}))
    monkeypatch.setattr(sync,'BybitPublicClient',FakeBybit)
    monkeypatch.setattr(sync,'SupabaseRestClient',FakeClient)
    monkeypatch.setattr(sync,'SupabaseMarketWriter',FakeWriter)
    monkeypatch.setattr(sys,'argv',['sync_supabase_market_data.py','--live-config',str(config),'--candle-limit','121'])
    return effects,sync.main


def test_one_pair_can_write_ticker_and_fail_before_candles(monkeypatch,tmp_path):
    effects,main=run_sync(monkeypatch,tmp_path,['AAA/USDT'],fault='candle-failure')
    assert main()==1
    assert effects==[('ticker','AAAUSDT'),('health','error',(),('AAA/USDT',))]


def test_partial_sync_may_return_zero_with_warning(monkeypatch,tmp_path):
    effects,main=run_sync(monkeypatch,tmp_path,['AAA/USDT','BBB/USDT'],fault='candle-failure')
    assert main()==0
    assert effects==[('ticker','AAAUSDT'),('candles','AAAUSDT'),('ticker','BBBUSDT'),
                     ('health','warning',('AAA/USDT',),('BBB/USDT',))]


def test_unexpected_process_termination_can_leave_ticker_without_health(monkeypatch,tmp_path):
    effects,main=run_sync(monkeypatch,tmp_path,['AAA/USDT'],fault='interrupt')
    with pytest.raises(KeyboardInterrupt):main()
    assert effects==[('ticker','AAAUSDT')]


def test_no_scan_does_not_write_selected_universe(monkeypatch,tmp_path):
    effects,main=run_sync(monkeypatch,tmp_path,['AAA/USDT'])
    assert main()==0
    assert effects==[('ticker','AAAUSDT'),('candles','AAAUSDT'),('health','ok',('AAA/USDT',),())]
