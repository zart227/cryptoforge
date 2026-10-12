"""Train-only feature support diagnostics; no clipping or entry policy changes."""
from math import isfinite


def training_feature_reference(rows,*,names,means,stds):
    if not rows or not len(names)==len(means)==len(stds):raise ValueError('paired train-only feature reference required')
    if any(len(row)!=len(names) or not all(isfinite(v) for v in row) for row in rows):
        raise ValueError('finite consistent training features required')
    if not all(isfinite(v) for v in (*means,*stds)) or any(v<=0 for v in stds):raise ValueError('finite train normalization required')
    return {'schema_version':'train-feature-support-v1','source_split':'train','count':len(rows),
        'names':list(names),'minimums':[min(row[i] for row in rows) for i in range(len(names))],
        'maximums':[max(row[i] for row in rows) for i in range(len(names))],
        'means':list(means),'stds':list(stds),'changes_entry_policy':False}


def feature_drift(features,reference):
    names=reference['names'];arrays=[reference[key] for key in ('minimums','maximums','means','stds')]
    if reference.get('source_split')!='train' or reference.get('schema_version')!='train-feature-support-v1':
        raise ValueError('explicit train-only feature support required')
    if not names or len(features)!=len(names) or any(len(values)!=len(names) for values in arrays):
        raise ValueError('feature support dimensions differ')
    if not all(isfinite(v) for values in [features,*arrays] for v in values) or any(v<=0 for v in reference['stds']):
        raise ValueError('finite feature support required')
    outside=[name for name,value,lower,upper in zip(names,features,reference['minimums'],reference['maximums'])
        if value<lower or value>upper]
    magnitude=max(abs((value-center)/scale) for value,center,scale in zip(features,reference['means'],reference['stds']))
    if not isfinite(magnitude):raise ValueError('nonfinite feature support distance')
    return {'outside_train_range_features':outside,'outside_train_range_count':len(outside),
        'maximum_absolute_train_standardized_value':magnitude,'changes_entry_policy':False,
        'profitability_established':False}
