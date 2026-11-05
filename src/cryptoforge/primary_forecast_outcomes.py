"""Bounded read-only market retrieval for prospective price diagnostics."""
from collections import defaultdict,Counter
import time
from datetime import UTC,datetime,timedelta
from cryptoforge.candle_contract import known_closed


def collect_primary_forecast_outcomes(memory,reader,*,as_of,maximum_forecasts=400,maximum_pairs=20,
                                     wall_seconds=20,monotonic=time.monotonic,policy_resolver=None,endpoint_reader=None):
    if type(maximum_pairs) is not int or maximum_pairs<1 or not 0<wall_seconds<=60:
        raise ValueError('bounded primary outcome work required')
    started=monotonic();rows=memory.matured_batch(as_of=as_of,limit=maximum_forecasts)
    groups=defaultdict(list)
    for row in rows:groups[(not row.get('outcome_pending',True),row['pair'])].append(row)
    counts=Counter();errors={};forecast_errors=[];read_pairs=0;lookups={};endpoints={};fallback_evidence=[]
    for (_,pair),forecasts in groups.items():
        if (pair not in lookups and read_pairs>=maximum_pairs) or monotonic()-started>=wall_seconds:
            counts['deferred_pair_or_wall_budget']+=len(forecasts);continue
        try:
            if pair not in lookups:
                read_pairs+=1;lookups[pair]=None
                candles=reader.read_candles(pair,timeframe='5m',limit=500)
                lookup={row.open_time+timedelta(minutes=5):row for row in candles}
                if len(lookup)!=len(candles):raise ValueError('duplicate primary price endpoint')
                lookups[pair]=lookup
            lookup=lookups[pair]
            if lookup is None:raise ValueError('pair evidence unavailable')
        except Exception as exc:
            errors[pair]=type(exc).__name__;counts['unavailable_or_invalid_pair_evidence']+=len(forecasts);continue
        from cryptoforge.live_learning_protocol import time as parse_time
        for index,forecast in enumerate(forecasts):
            if monotonic()-started>=wall_seconds:
                counts['deferred_pair_or_wall_budget']+=len(forecasts)-index;break
            try:
                target=parse_time(forecast['target_information_end'])
                candle=lookup.get(target)
                if endpoint_reader is not None and (candle is None or not known_closed(candle,step=timedelta(minutes=5),as_of=memory.clock())):
                    key=(pair,target)
                    if key not in endpoints and len(endpoints)>=8:
                        counts['deferred_public_endpoint_budget']+=1;continue
                    if key not in endpoints:
                        endpoints[key]=None
                        recovered=endpoint_reader.read_target_candle(pair,target=target)
                        endpoints[key]=recovered
                        if recovered is not None:
                            fallback_evidence.append({'pair':pair,'target_information_end':target.isoformat(),
                                'observed_at':recovered.cache_observed_at.isoformat(),
                                'source':'bybit_public_spot_kline','open_time':recovered.open_time.isoformat(),
                                **{name:str(getattr(recovered,name)) for name in ('open','high','low','close','volume')}})
                    if endpoints.get(key) is not None:candle=endpoints[key]
                if candle is None:counts['missing_target_candle']+=1;continue
                policy=policy_resolver(forecast['artifact_sha256']) if policy_resolver is not None and forecast.get('label_policy_known') is not True else None
                receipt=memory.record_outcome(forecast['forecast_id'],candle,original_policy=policy)
                counts[receipt['status']]+=1
            except Exception as exc:
                reasons={'primary price endpoint is not available yet':'endpoint_not_known_closed_at_observation',
                    'primary price endpoint identity mismatch':'endpoint_identity_mismatch',
                    'invalid primary endpoint OHLCV':'invalid_endpoint_ohlcv',
                    'finite price target and assumed cost required':'invalid_original_price_policy',
                    'cannot backdate a primary price correction':'backdated_price_correction'}
                reason=reasons.get(str(exc),'invalid_price_evidence') if isinstance(exc,ValueError) else 'diagnostic_storage_or_read_error'
                counts['invalid_price_endpoint_evidence']+=1
                if len(forecast_errors)<20:forecast_errors.append({'pair':pair,'forecast_id':forecast['forecast_id'],'reason':reason})
    partial=bool(errors or counts['missing_target_candle'] or counts['deferred_pair_or_wall_budget'] or counts['invalid_price_endpoint_evidence'] or counts['deferred_public_endpoint_budget'] or counts['diagnostic_storage_budget_preserved'])
    return {'status':'primary_price_diagnostics_partial' if partial else 'primary_price_diagnostics_collected',
        'as_of':as_of.isoformat(),'selected_forecasts':len(rows),'read_pairs':read_pairs,
        'public_endpoint_requests':len(endpoints),'public_endpoint_evidence':fallback_evidence,
        'counts':dict(counts),'pair_errors':errors,'wall_seconds':monotonic()-started,
        'selected_forecast_accounting_matches':sum(counts.values())==len(rows),
        'forecast_errors':forecast_errors,'forecast_error_details_capped':counts['invalid_price_endpoint_evidence']>len(forecast_errors),
        'collection_scope':'matured_targets_last36hours_not_complete_lifetime_history',
        'counts_as_real_executed_buys':False,'cash_training_rows_added':0,'live_promotion_allowed':False,
        'realized_portfolio_income_established':False}


class BybitPrimaryEndpointReader:
    """Fetch one exact historical spot candle; observe it now, never backdate it."""
    def __init__(self,client,*,clock=None):
        self.client=client;self.clock=clock or (lambda:datetime.now(UTC))

    def read_target_candle(self,pair,*,target):
        from cryptoforge.supabase_executor import CandleRow
        if target.tzinfo is None or target>self.clock():
            raise ValueError('closed primary target required')
        start=target-timedelta(minutes=5);symbol=pair.replace('/','')
        rows=self.client.get_klines(symbol,'5',1,start_ms=int(start.timestamp()*1000),
            end_ms=int(target.timestamp()*1000)-1)
        if not rows:return None
        if len(rows)!=1 or rows[0].symbol!=symbol or rows[0].start_ms!=int(start.timestamp()*1000):
            raise ValueError('primary price endpoint identity mismatch')
        row=rows[0]
        return CandleRow(pair,symbol,start,row.open,row.high,row.low,row.close,row.volume,
            cache_observed_at=self.clock())
