"""Bounded read-only market retrieval for prospective price diagnostics."""
from collections import defaultdict,Counter
import time


def collect_primary_forecast_outcomes(memory,reader,*,as_of,maximum_forecasts=400,maximum_pairs=20,
                                     wall_seconds=20,monotonic=time.monotonic,policy_resolver=None):
    if type(maximum_pairs) is not int or maximum_pairs<1 or not 0<wall_seconds<=60:
        raise ValueError('bounded primary outcome work required')
    started=monotonic();rows=memory.matured_batch(as_of=as_of,limit=maximum_forecasts)
    groups=defaultdict(list)
    for row in rows:groups[row['pair']].append(row)
    counts=Counter();errors={};forecast_errors=[];read_pairs=0
    for pair,forecasts in groups.items():
        if read_pairs>=maximum_pairs or monotonic()-started>=wall_seconds:
            counts['deferred_pair_or_wall_budget']+=len(forecasts);continue
        read_pairs+=1
        try:
            candles=reader.read_candles(pair,timeframe='5m',limit=500)
            from datetime import timedelta
            lookup={row.open_time+timedelta(minutes=5):row for row in candles}
            if len(lookup)!=len(candles):raise ValueError('duplicate primary price endpoint')
        except Exception as exc:
            errors[pair]=type(exc).__name__;counts['unavailable_or_invalid_pair_evidence']+=len(forecasts);continue
        from cryptoforge.live_learning_protocol import time as parse_time
        for index,forecast in enumerate(forecasts):
            if monotonic()-started>=wall_seconds:
                counts['deferred_pair_or_wall_budget']+=len(forecasts)-index;break
            try:
                candle=lookup.get(parse_time(forecast['target_information_end']))
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
    partial=bool(errors or counts['missing_target_candle'] or counts['deferred_pair_or_wall_budget'] or counts['invalid_price_endpoint_evidence'])
    return {'status':'primary_price_diagnostics_partial' if partial else 'primary_price_diagnostics_collected',
        'as_of':as_of.isoformat(),'selected_forecasts':len(rows),'read_pairs':read_pairs,
        'counts':dict(counts),'pair_errors':errors,'wall_seconds':monotonic()-started,
        'selected_forecast_accounting_matches':sum(counts.values())==len(rows),
        'forecast_errors':forecast_errors,'forecast_error_details_capped':counts['invalid_price_endpoint_evidence']>len(forecast_errors),
        'collection_scope':'matured_targets_last36hours_not_complete_lifetime_history',
        'counts_as_real_executed_buys':False,'cash_training_rows_added':0,'live_promotion_allowed':False,
        'realized_portfolio_income_established':False}
