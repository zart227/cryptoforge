"""Read-only numerical audit from saved primary inputs, without fitting or orders."""
from datetime import datetime
import hashlib,json,math
from pathlib import Path
from cryptoforge.model_training import (FEATURE_NAMES,FEATURE_VERSION,MODEL_FAMILY,
    TrainingExample,fit_standardizer,predict_probability,evaluate_split)
from cryptoforge.classifier_diagnostics import split_diagnostics
from cryptoforge.source_contract import primary_training_sources,assert_source_dependencies
from cryptoforge.training_snapshot import load_training_snapshot,load_runtime_sources
from cryptoforge.feature_drift import training_feature_reference


def _time(value):
    stamp=datetime.fromisoformat(value)
    if stamp.tzinfo is None:raise ValueError('aware primary snapshot timestamp required')
    return stamp


def audit_primary_artifact(path,*,expected_sha256=None,require_current_source=True):
    path=Path(path);raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and sha!=expected_sha256:raise ValueError('primary artifact checksum mismatch')
    if not path.stem.endswith('-'+sha[:12]):raise ValueError('primary artifact filename checksum mismatch')
    artifact=json.loads(raw);config=artifact['config']
    if artifact.get('model_family')!=MODEL_FAMILY or artifact.get('feature_version')!=FEATURE_VERSION or artifact.get('feature_names')!=list(FEATURE_NAMES):
        raise ValueError('supported primary artifact schema required')
    if 'training_input_snapshot' not in config:raise ValueError('original primary input snapshot unavailable; do not reconstruct cache')
    snapshot=load_training_snapshot(config['training_input_snapshot']);metadata=snapshot['metadata']
    if snapshot.get('target_version')!='fixed-future-return-v1' or snapshot.get('counts_as_real_executed_buys') is not False:
        raise ValueError('primary candle examples must remain separate from executed buys')
    for key in ('data_snapshot_at','timeframe','feature_calculation_contract','feature_lookback_candles',
                'horizon_candles','min_label_return','round_trip_cost','implementation_hashes','source_admission','runtime_source_bundle'):
        if metadata.get(key)!=config.get(key):raise ValueError('primary artifact differs from original input metadata')
    source_matches=True
    try:assert_source_dependencies(config['implementation_hashes'],primary_training_sources())
    except ValueError:
        source_matches=False
        if require_current_source:raise
    load_runtime_sources(config['runtime_source_bundle'],config['implementation_hashes'])
    as_of=_time(metadata['data_snapshot_at']);threshold=config['min_label_return']
    splits={};seen=set()
    for split,rows in snapshot['splits'].items():
        values=[]
        for row in rows:
            example=TrainingExample(row['pair'],_time(row['open_time']),tuple(row['features']),row['label'],
                row['short_label'],row['future_return'],_time(row['label_end_time']))
            identity=(example.pair,example.open_time)
            if identity in seen:raise ValueError('duplicate primary snapshot identity')
            seen.add(identity)
            if (len(example.features)!=len(FEATURE_NAMES) or not all(math.isfinite(v) for v in (*example.features,example.future_return))
                or not example.open_time<example.label_end_time<=as_of
                or example.label!=int(example.future_return>threshold)
                or example.short_label!=int(example.future_return< -threshold)):
                raise ValueError('invalid primary snapshot labels, dimensions or availability')
            values.append(example)
        if not values or values!=sorted(values,key=lambda row:row.open_time):raise ValueError('nonempty chronological primary splits required')
        splits[split]=values
    for left,right in (('train','validation'),('validation','test')):
        if max(row.label_end_time for row in splits[left])>=min(row.open_time for row in splits[right]):
            raise ValueError('primary snapshot crosses purged split boundary')
    fit_end=max(row.label_end_time for row in splits['train']+splits['validation'])
    evaluation_end=max(row.label_end_time for row in splits['test'])
    if fit_end!=_time(config['fit_information_end']) or evaluation_end!=_time(config['evaluation_information_end']):
        raise ValueError('primary information boundaries differ from snapshot')
    means,stds=fit_standardizer([row.features for row in splits['train']])
    if means!=artifact['means'] or stds!=artifact['stds']:raise ValueError('normalization does not match train-only inputs')
    if artifact.get('feature_reference') is not None:
        reference=training_feature_reference([row.features for row in splits['train']],names=FEATURE_NAMES,means=means,stds=stds)
        if reference!=artifact['feature_reference']:raise ValueError('feature support does not match train-only inputs')
    diagnostics={};metrics={}
    for head,weight_key,bias_key,label_attr,metric_key in (
        ('long','weights','bias','label','metrics'),('short','short_weights','short_bias','short_label','short_metrics')
    ):
        weights=artifact[weight_key];bias=artifact[bias_key]
        rate=sum(getattr(row,label_attr) for row in splits['train'])/len(splits['train'])
        diagnostics[head]={};metrics[head]=[]
        for split in ('train','validation','test'):
            rows=splits[split];probabilities=[predict_probability(row.features,weights,bias,means,stds) for row in rows]
            diagnostics[head][split]=split_diagnostics(rows,probabilities,train_positive_rate=rate,
                threshold=artifact['threshold'],label_attr=label_attr)
            metrics[head].append(evaluate_split(split,rows,weights,bias,means,stds,label_attr=label_attr).__dict__)
        if metrics[head]!=artifact[metric_key]:raise ValueError('saved primary metrics differ from exact inputs')
    if diagnostics!=artifact['probability_diagnostics']:raise ValueError('saved probability diagnostics differ from exact inputs')
    return {'status':'exact_primary_inputs_and_metrics_verified' if source_matches else 'saved_inputs_and_metrics_match_current_numerics_source_differs','artifact_sha256':sha,
        'model_version':artifact['model_version'],'split_counts':config['training_input_snapshot']['split_counts'],
        'current_source_matches_fitted_source':source_matches,'archived_runtime_executed':False,
        'probability_diagnostics':diagnostics,'refitting_performed':False,'publication_performed':False,
        'counts_as_real_executed_buys':False,'live_profitability_established':False}
