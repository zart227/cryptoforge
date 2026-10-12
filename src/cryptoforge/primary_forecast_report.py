"""Streaming exploratory diagnostics; no model selection or portfolio claims."""
from decimal import Decimal
from datetime import UTC, datetime
from math import log


def primary_forecast_report(memory,*,as_of,maximum_rows=10000):
    if type(maximum_rows) is not int or maximum_rows<1:raise ValueError('bounded forecast report required')
    count=0;truncated=False;groups={}
    from contextlib import closing
    with closing(memory.iter_labeled_asof(as_of=as_of)) as rows:
        for _,forecast,outcome in rows:
            if count>=maximum_rows:truncated=True;break
            count+=1;sha=forecast['artifact_sha256']
            group=groups.setdefault(sha,{'model_version':forecast.get('model_version'),'price_endpoints':0,
                'original_policy_unknown':0,'classified_endpoints':0,'positives':0,'brier_sum':0.,'loss_sum':0.,
                'fixed_threshold_signals':0,'signal_return_minus_cost_sum':Decimal(0),
                'signal_positive_estimates':0,'outside_train_support_endpoints':0,'entry_days':set(),'pairs':set(),'signal_cohorts':{},'baseline_opportunity_cohorts':{},'signal_days':{}})
            group.setdefault('baseline_signal_true_endpoints',0)
            group.setdefault('baseline_signal_unknown_endpoints',0)
            group.setdefault('baseline_fixed_threshold_signals',0)
            group.setdefault('baseline_signal_return_minus_cost_sum',Decimal(0))
            group['price_endpoints']+=1;group['pairs'].add(forecast['pair'])
            group['entry_days'].add(forecast['predicted_at'][:10])
            baseline=forecast.get('baseline_entry_signal')
            group['baseline_signal_true_endpoints']+=int(baseline is True)
            group['baseline_signal_unknown_endpoints']+=int(baseline is None)
            if (forecast.get('input_drift') or {}).get('outside_train_range_count',0):group['outside_train_support_endpoints']+=1
            p=forecast.get('long_probability');label=outcome.get('label')
            if p is None or label is None:
                group['original_policy_unknown']+=1;continue
            group['classified_endpoints']+=1;group['positives']+=label
            group['brier_sum']+=(p-label)**2;clipped=min(max(p,1e-12),1-1e-12)
            group['loss_sum']+=-label*log(clipped)-(1-label)*log(1-clipped)
            if baseline is True:
                value=Decimal(outcome['price_return_minus_assumed_cost'])
                for key in ('all_baseline_signals','probability_at_least_0.5' if p>=.5 else 'probability_below_0.5'):
                    cohort=group['baseline_opportunity_cohorts'].setdefault(key,{'signals':0,'positive_estimates':0,'return_sum':Decimal(0)})
                    cohort['signals']+=1;cohort['positive_estimates']+=int(value>0);cohort['return_sum']+=value
            if p>=.5:
                value=Decimal(outcome['price_return_minus_assumed_cost'])
                group['fixed_threshold_signals']+=1;group['signal_return_minus_cost_sum']+=value
                day=datetime.fromisoformat(forecast['predicted_at']).astimezone(UTC).date().isoformat()
                group['signal_days'][day]=group['signal_days'].get(day,0)+1
                group['signal_positive_estimates']+=int(value>0)
                drift=forecast.get('input_drift')
                support=('unknown' if not isinstance(drift,dict) or type(drift.get('outside_train_range_count')) is not int or drift['outside_train_range_count']<0 else
                    'outside_train_range' if drift.get('outside_train_range_count',0) else 'within_train_range')
                for key in ('pair:'+forecast['pair'],'support:'+support):
                    cohort=group['signal_cohorts'].setdefault(key,{'signals':0,'positive_estimates':0,'return_sum':Decimal(0)})
                    cohort['signals']+=1;cohort['positive_estimates']+=int(value>0);cohort['return_sum']+=value
                if baseline is True:
                    group['baseline_fixed_threshold_signals']+=1
                    group['baseline_signal_return_minus_cost_sum']+=value
    for group in groups.values():
        n=group['classified_endpoints'];signals=group['fixed_threshold_signals']
        brier=group.pop('brier_sum');loss=group.pop('loss_sum')
        group['brier']=brier/n if n else None
        group['log_loss']=loss/n if n else None
        value=group.pop('signal_return_minus_cost_sum')
        group['mean_signal_price_return_minus_assumed_cost']=str(value/signals) if signals else None
        baseline_signals=group['baseline_fixed_threshold_signals'];value=group.pop('baseline_signal_return_minus_cost_sum')
        group['baseline_mean_signal_price_return_minus_assumed_cost']=str(value/baseline_signals) if baseline_signals else None
        group['entry_days']=len(group['entry_days']);group['pairs']=sorted(group['pairs'])
        signal_days=group.pop('signal_days')
        pair_counts={key.removeprefix('pair:'):cohort['signals']
                     for key,cohort in group['signal_cohorts'].items() if key.startswith('pair:')}
        group['signal_concentration']={
            'by_pair':pair_counts,'by_utc_day':signal_days,
            'signal_pairs':len(pair_counts),'signal_days':len(signal_days),
            'largest_pair_fraction':str(Decimal(max(pair_counts.values()))/signals) if signals else None,
            'largest_day_fraction':str(Decimal(max(signal_days.values()))/signals) if signals else None,
            'scope':'forecast_signals_not_independent_executed_trades',
            'changes_admission_gates':False}
        for cohort in [*group['signal_cohorts'].values(),*group['baseline_opportunity_cohorts'].values()]:
            cohort['mean_price_return_minus_assumed_cost']=str(cohort.pop('return_sum')/cohort['signals'])
            cohort['independent_profitability_established']=False
    return {'as_of':as_of.isoformat(),'observed_endpoints':count,'snapshot_truncated':truncated,'by_model':groups,
        'scope':'exploratory_prospective_candle_targets_not_executed_cash_or_shared_portfolio',
        'fixed_diagnostic_threshold':.5,'model_selection_performed':False,
        'baseline_comparison_scope':'same_observed_baseline_opportunities_candle_payoffs_not_actual_gate_decisions_or_causal_execution_benefit',
        'cash_training_rows_added':0,'live_promotion_allowed':False,'realized_income_established':False}
