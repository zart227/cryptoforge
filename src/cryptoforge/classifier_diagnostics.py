"""Fixed-threshold diagnostics; never select a model or a trading threshold."""
from math import isfinite, log


def _average_precision(labels,probabilities):
    positives=sum(labels)
    if not positives:return None
    groups={}
    for label,p in zip(labels,probabilities):
        bucket=groups.setdefault(p,[0,0]);bucket[0]+=label;bucket[1]+=1
    true_positive=observed=0;result=0.
    for p,(positive,count) in sorted(groups.items(),reverse=True):
        true_positive+=positive;observed+=count
        result+=(positive/positives)*(true_positive/observed)
    return result


def probability_diagnostics(labels, probabilities, *, train_positive_rate, threshold):
    if len(labels) != len(probabilities):
        raise ValueError('paired labels and probabilities required')
    if not isfinite(train_positive_rate) or not 0 <= train_positive_rate <= 1:
        raise ValueError('finite train-only baseline required')
    if not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('finite fixed threshold required')
    if any(label not in (0, 1) for label in labels):
        raise ValueError('binary labels required')
    if any(not isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError('finite probabilities in [0,1] required')
    baseline = min(max(train_positive_rate, 1e-12), 1 - 1e-12)
    def loss(values):
        return sum(-y*log(min(max(p, 1e-12), 1-1e-12))
                   -(1-y)*log(1-min(max(p, 1e-12), 1-1e-12))
                   for y, p in zip(labels, values))/len(labels) if labels else None
    bins = []
    for index in range(5):
        paired = [(y, p) for y, p in zip(labels, probabilities) if min(int(p*5), 4) == index]
        bins.append({'lower_probability': index/5, 'upper_probability': (index+1)/5,
                     'count': len(paired),
                     'mean_probability': sum(p for y,p in paired)/len(paired) if paired else None,
                     'positive_fraction': sum(y for y,p in paired)/len(paired) if paired else None})
    signals = sum(p >= threshold for p in probabilities)
    positives=sum(labels);negatives=len(labels)-positives
    true_positive=sum(y==1 and p>=threshold for y,p in zip(labels,probabilities))
    true_negative=sum(y==0 and p<threshold for y,p in zip(labels,probabilities))
    return {'count': len(labels), 'observed_positive_rate': sum(labels)/len(labels) if labels else None,
            'train_positive_rate': train_positive_rate, 'fixed_threshold': threshold,
            'signals': signals, 'probability_min': min(probabilities) if probabilities else None,
            'probability_max': max(probabilities) if probabilities else None,
            'probability_mean': sum(probabilities)/len(probabilities) if probabilities else None,
            'log_loss': loss(probabilities), 'baseline_log_loss': loss([baseline]*len(labels)),
            'brier': sum((p-y)**2 for y,p in zip(labels, probabilities))/len(labels) if labels else None,
            'baseline_brier': sum((baseline-y)**2 for y in labels)/len(labels) if labels else None,
            'calibration_bins': bins, 'all_rejected': bool(labels) and signals == 0,
            'average_precision':_average_precision(labels,probabilities),
            'average_precision_definition':'noninterpolated_precision_recall_steps_grouped_equal_scores',
            'random_ranking_prevalence_reference':positives/len(labels) if labels else None,
            'balanced_accuracy':(true_positive/positives+true_negative/negatives)/2 if positives and negatives else None,
            'fixed_threshold_precision':true_positive/signals if signals else None,
            'fixed_threshold_recall':true_positive/positives if positives else None,
            'selection_uses_these_diagnostics': False, 'live_profitability_established': False}


def split_diagnostics(examples, probabilities, *, train_positive_rate, threshold, label_attr='label'):
    if len(examples) != len(probabilities):
        raise ValueError('paired examples and probabilities required')
    result = probability_diagnostics([getattr(e, label_attr) for e in examples], probabilities,
                                    train_positive_rate=train_positive_rate, threshold=threshold)
    result['by_pair'] = {}
    for pair in sorted({e.pair for e in examples}):
        paired = [(e,p) for e,p in zip(examples,probabilities) if e.pair == pair]
        result['by_pair'][pair] = probability_diagnostics([getattr(e,label_attr) for e,p in paired],
            [p for e,p in paired], train_positive_rate=train_positive_rate, threshold=threshold)
    return result
