"""Natural prospective price calibration against a frozen training prevalence."""
from datetime import UTC,datetime
from math import isfinite
from cryptoforge.classifier_diagnostics import probability_diagnostics


def evaluate_migration_rows(rows,*,protocol_sha,artifact_sha,train_positive_rate,frozen_at,as_of,pairs,threshold=.5):
    if frozen_at.tzinfo is None or as_of.tzinfo is None or frozen_at>as_of:
        raise ValueError('ordered aware evaluation clocks required')
    if threshold!=.5:raise ValueError('original fixed threshold required')
    if isinstance(train_positive_rate,bool) or not isfinite(train_positive_rate) or not 0<=train_positive_rate<=1:
        raise ValueError('frozen train prevalence required')
    groups={};seen=set();unknown=0
    for identity,forecast,outcome in rows:
        if identity in seen:raise ValueError('unique paired endpoint identities required')
        seen.add(identity)
        if forecast.get('migration_protocol_sha256')!=protocol_sha or forecast['artifact_sha256']!=artifact_sha:
            raise ValueError('original frozen forecast identity required')
        if (forecast.get('target_version')!='fixed-future-return-v1' or forecast['pair'] not in pairs
                or outcome.get('source_kind')!='primary_future_candle_return_diagnostic_v1'
                or outcome.get('forecast_id')!=identity or outcome.get('counts_as_real_executed_buys') is not False):
            raise ValueError('original paired price target required')
        predicted=datetime.fromisoformat(forecast['predicted_at'])
        available=datetime.fromisoformat(outcome['label_available_at'])
        if predicted.tzinfo is None or available.tzinfo is None or not frozen_at<=predicted<available<=as_of:
            raise ValueError('prospective outcome availability required')
        target_end=datetime.fromisoformat(outcome['target_information_end'])
        if target_end.tzinfo is None or not predicted<target_end<=available:
            raise ValueError('closed future target endpoint required')
        p=forecast.get('long_probability');label=outcome.get('label')
        if label is None or p is None:unknown+=1;continue
        if outcome.get('original_label_policy_available') is not True:raise ValueError('original label policy required')
        if type(label) is not int or label not in (0,1) or isinstance(p,bool) or not isfinite(p) or not 0<=p<=1:
            raise ValueError('known binary label and finite probability required')
        day=predicted.astimezone(UTC).date().isoformat()
        for key in ('all','pair:'+forecast['pair'],'day:'+day):
            ys,ps=groups.setdefault(key,([],[]));ys.append(label);ps.append(p)
    reports={key:probability_diagnostics(ys,ps,train_positive_rate=train_positive_rate,threshold=threshold)
             for key,(ys,ps) in sorted(groups.items())}
    for report in reports.values():
        report['brier_difference_vs_frozen_prevalence']=report['brier']-report['baseline_brier']
        report['log_loss_difference_vs_frozen_prevalence']=report['log_loss']-report['baseline_log_loss']
    return {'as_of':as_of.isoformat(),'protocol_sha256':protocol_sha,'artifact_sha256':artifact_sha,
        'frozen_train_positive_rate':train_positive_rate,'endpoint_count':len(seen),'unknown_policy_endpoints':unknown,
        'diagnostics':reports,'scope':'exploratory_price_calibration_not_portfolio_income',
        'overlapping_endpoints_are_independent':False,'parameter_selection_performed':False,
        'independent_admission_granted':False,'live_promotion_allowed':False}
