"""Run one bounded virtual-paper tick; no private keys or exchange-order client."""
from datetime import UTC,datetime
from dataclasses import replace
from copy import deepcopy
from decimal import Decimal
import argparse
import json
from pathlib import Path

from cryptoforge.paper_activation import load_activation
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args();_,study=load_cash_study(args.protocol)
    now=datetime.now(UTC)
    result={'as_of':now.isoformat(),'live_promotion_allowed':False,'mode':'paper','paper_worker_implemented':True}
    try:
        activation=load_activation(args.protocol,study.execution_policy,study.candidate,study.predictions,now=now)
        if not activation['enabled']:result.update(status=activation['status'],network_requests=0,wallet_initialized=False)
        else:
            from cryptoforge.market_data import BybitPublicClient
            from cryptoforge.paper_market import observe_market
            from cryptoforge.paper_wallet import PaperWallet
            from cryptoforge.paper_worker import PaperWorker
            from cryptoforge.prospective_shadow import ShadowLedger
            from cryptoforge.supabase_executor import CandleRow,exit_signal
            from cryptoforge.archive_quality import validate_candles
            client=BybitPublicClient(timeout=3,max_retries=0)
            import time
            tick_started=time.monotonic()
            def check_budget():
                if time.monotonic()-tick_started>=20:raise TimeoutError("shared paper tick budget exhausted")
            def indicators(pair):
                check_budget()
                from cryptoforge.candle_contract import closed_snapshot
                candles=client.get_klines(pair.replace('/',''),interval='5',limit=120)
                as_of=datetime.now(UTC);known=[row for row in candles if row.start_ms<=int(as_of.timestamp()*1000)]
                if len(known)<36:raise ValueError('insufficient current exit history')
                quality=validate_candles(known,now_ms=int(as_of.timestamp()*1000)+300000)
                if quality['gap_ranges']:raise ValueError('exit history has gaps')
                rows=[CandleRow(pair,row.symbol,datetime.fromtimestamp(row.start_ms/1000,UTC),
                               row.open,row.high,row.low,row.close,row.volume) for row in known]
                if activation['protocol']['input_candle_state']=='closed_only':
                    rows=closed_snapshot(rows,timeframe='5m',as_of=as_of)
                if not rows or (as_of-rows[-1].open_time).total_seconds()>600:
                    raise ValueError('stale current exit history')
                return exit_signal(rows)
            from cryptoforge.paper_observations import SharedExitObservations
            shared_indicators=SharedExitObservations(indicators,max_age_seconds=activation['config'].quote_max_age_seconds)
            predictions=ShadowLedger(study.predictions).rows()
            market_cache={}
            def shared_market(pair):
                cached=market_cache.get(pair)
                if cached and (datetime.now(UTC)-datetime.fromisoformat(cached[0]['observed_at'])).total_seconds()<=activation['config'].quote_max_age_seconds:
                    return cached
                check_budget()
                market_cache[pair]=observe_market(client,pair)
                return market_cache[pair]
            role_reports={}
            for role in ('candidate','baseline_control','stress_candidate'):
                prefix='cash-paper' if role=='candidate' else 'cash-paper-'+role.replace('_','-')
                config=activation['config'];policy=deepcopy(activation['policy']);policy['evaluation_role']=role
                selected=predictions
                if role=='baseline_control':
                    selected=[{**row,'original_candidate_would_enter':row['would_enter'],
                               'would_enter':row.get('baseline_would_enter',False)} for row in predictions]
                elif role=='stress_candidate':
                    acceptance=activation['acceptance']
                    multiplier=Decimal(acceptance['stress_cost_multiplier'])
                    config=replace(config,entry_fee=config.entry_fee*multiplier,exit_fee=config.exit_fee*multiplier,
                                   slippage=config.slippage*multiplier,
                                   cost_assumption_id=config.cost_assumption_id+':stress-x'+str(multiplier))
                    policy['wallet']={**policy['wallet'],'entry_fee':str(config.entry_fee),'exit_fee':str(config.exit_fee),
                        'slippage':str(config.slippage),'cost_assumption_id':config.cost_assumption_id}
                wallet_path,worker_path=study.paper_role_paths(role)
                wallet=PaperWallet(wallet_path,
                    candidate_sha=activation['manifest']['artifact_sha256'],config=config)
                worker=PaperWorker(wallet,worker_path,policy=policy,
                                   market=shared_market,exit_indicator=shared_indicators)
                role_reports[role]=worker.tick(selected,window_start=activation['window_start'],
                    window_end=activation['window_end'],entry_cutoff=activation['entry_cutoff'])
            result.update(status='paper_roles_tick_complete',roles=role_reports)
            result['wallet_initialized']=True
    except Exception as exc:result.update(status='paper_activation_or_tick_error',error=type(exc).__name__)
    output=study.paper_worker_report;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,default=str,indent=2));output.chmod(0o600)
    print(json.dumps({'status':result['status'],'wallet_initialized':result.get('wallet_initialized',False),
                     'promotion_allowed':False,'output':str(output.resolve())}))
    return 1 if result['status']=='paper_activation_or_tick_error' else 0


if __name__=='__main__':raise SystemExit(main())
