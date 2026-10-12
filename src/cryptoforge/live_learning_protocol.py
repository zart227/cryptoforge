"""Readiness for a frozen, prospective real-execution experiment; no fitting."""
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from math import isfinite
from pathlib import Path

from cryptoforge.cash_recovery import TARGET_VERSION,MAX_RESIDUAL_COST_FRACTION
from cryptoforge.model_training import FEATURE_VERSION

SPLITS=('train','validation','sealed_test','paper')


def buy_key(row):
    return hashlib.sha256((row['pair']+'|'+row['entry_order']).encode()).hexdigest()


def time(value):
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('timezone-aware experiment times required')
    return result.astimezone(UTC)


def load_protocol(path: Path) -> dict:
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=path.with_suffix('.sha256').read_text().strip():
        raise ValueError('frozen live protocol checksum mismatch')
    protocol=json.loads(raw);validate_protocol(protocol)
    return protocol


def validate_protocol(protocol):
    if (protocol['status']!='frozen_collection_only' or protocol['target_version']!=TARGET_VERSION
        or protocol['feature_version']!=FEATURE_VERSION or protocol['automatic_training_allowed'] is not False
        or protocol['live_promotion_allowed'] is not False or protocol.get('market')!='bybit_global_spot'):
        raise ValueError('unsupported experimental protocol')
    for key in ('embargo_seconds','minimum_example_snapshot_freshness_seconds'):
        if type(protocol[key]) is not int or protocol[key]<1:raise ValueError('positive integer temporal safeguards required')
    if protocol['input_candle_state'] not in {'legacy_asof_snapshot','closed_only'}:
        raise ValueError('one explicit candle input contract required')
    contract=protocol.get('feature_input_contract')
    if contract is not None:
        width=contract.get('lookback_candles')
        if (contract.get('feature_version')!=FEATURE_VERSION or contract.get('timeframe')!='5m'
            or contract.get('input_candle_state')!=protocol['input_candle_state']
            or contract.get('calculation_contract')!='bounded-window-candle-v1'
            or type(width) is not int or not 36<=width<=1000):
            raise ValueError('explicit compatible feature input contract required')
    if Decimal(protocol['maximum_residual_cost_fraction'])!=MAX_RESIDUAL_COST_FRACTION:
        raise ValueError('cash recovery residual policy mismatch')
    previous=time(protocol['frozen_at'])
    for split in SPLITS:
        window=protocol['windows'][split];start=time(window['start']);end=time(window['end_exclusive'])
        if start!=previous or end-start<=timedelta(seconds=2*protocol['embargo_seconds']):
            raise ValueError('ordered contiguous windows with sufficient embargo required')
        if any(type(value) is not int or value<1 for value in protocol['minimums'][split].values()):
            raise ValueError('positive integer readiness minima required')
        previous=end
    if len(set(protocol['development_buy_keys']))!=len(protocol['development_buy_keys']):
        raise ValueError('duplicate development buy keys')
    if any(not isinstance(key,str) or len(key)!=64 or any(c not in '0123456789abcdef' for c in key)
           for key in protocol['development_buy_keys']):raise ValueError('development buy hashes required')
    for field in ('maximum_pair_fraction','maximum_entry_day_fraction'):
        fraction=Decimal(protocol[field])
        if not fraction.is_finite() or not 0<fraction<=1:raise ValueError('invalid concentration bound')


def collection_is_healthy(current,protocol,now):
    try:
        age=now-time(current['snapshot_observed_at'])
        scope=current.get('observation_scope') or {}
        return (timedelta(0)<=age<=timedelta(seconds=protocol['minimum_example_snapshot_freshness_seconds'])
                and current.get('accounting_quality_verified') is True
                and current.get('source_binding_verified') is True
                and not current.get('snapshot_truncated') and not current.get('source_binding_mismatches')
                and not current.get('observation_errors')
                and not (current.get('collection_coverage') or {}).get('unexplained_omissions',0)
                and scope.get('eligible_pair_count',0)<=scope.get('observed_pair_count',scope.get('maximum_pairs',0)))
    except (ValueError,KeyError,TypeError):return False


def split_cutoff(protocol,split,as_of):
    return min(as_of,time(protocol['windows'][split]['end_exclusive'])-timedelta(seconds=protocol['embargo_seconds']))


def evaluate_readiness(protocol,snapshots,*,as_of: datetime,source_healthy: bool,include_training_rows: bool=False):
    validate_protocol(protocol)
    if as_of.tzinfo is None:raise ValueError('timezone-aware readiness time required')
    training_rows={};summaries={};assigned={};overlaps=set();embargo=timedelta(seconds=protocol['embargo_seconds'])
    known=set(protocol['development_buy_keys']);freeze=time(protocol['frozen_at'])
    for split in SPLITS:
        window=protocol['windows'][split];start=time(window['start']);end=time(window['end_exclusive'])
        cutoff=split_cutoff(protocol,split,as_of);rows=[];excluded=Counter();seen=set()
        for row in snapshots.get(split,[]):
            key=buy_key(row)
            if key in seen:raise ValueError('duplicate buy order within snapshot')
            seen.add(key)
            try:
                entry=time(row['entry_at']);available=time(row['label_available_at'])
                feature_time=time(row['example']['open_time']);closed=time(row['closed_at'])
                if not feature_time<=entry<=closed<=available or available>cutoff:
                    raise ValueError('information_not_available_at_split_cutoff')
                if row['target_version']!=protocol['target_version'] or row.get('feature_version')!=FEATURE_VERSION:
                    raise ValueError('incompatible_target_or_features')
                if row.get('input_candle_state')!=protocol['input_candle_state']:
                    raise ValueError('incompatible_candle_input_state')
                if protocol.get('feature_input_contract') is not None and row.get('feature_input_contract')!=protocol['feature_input_contract']:
                    raise ValueError('incompatible_feature_calculation_contract')
                features=row['example']['features']
                if len(features)!=7 or not all(isfinite(float(value)) for value in features):
                    raise ValueError('invalid_original_features')
                if split!='train' and key in known:raise ValueError('development_buy_not_independent')
                development=(key in known and entry<freeze)
                if not (split=='train' and development):
                    lower=start if split=='train' else start+embargo
                    if not lower<=entry<end:raise ValueError('outside_entry_window_or_embargo')
                if split=='paper' and (row.get('evaluation_mode')!='paper' or not row.get('candidate_artifact_sha256')):
                    raise ValueError('candidate_paper_execution_evidence_required')
            except (ValueError,KeyError,TypeError) as exc:
                excluded[str(exc)]+=1;continue
            if key in assigned and assigned[key]!=split:overlaps.add(key)
            assigned[key]=split;rows.append(row)
        if include_training_rows and split in {'train','validation'}:training_rows[split]=rows
        pair_counts=Counter(row['pair'] for row in rows)
        days=Counter(time(row['entry_at']).date().isoformat() for row in rows)
        stats={'buy_orders':len(rows),'entry_days':len(days),'pairs':len(pair_counts)}
        # Holdout reward/label distributions never influence collection readiness.
        if split in {'train','validation'}:
            if any(row['example']['label'] not in (0,1) for row in rows):
                raise ValueError('invalid binary training label')
            labels=Counter(int(row['example']['label']) for row in rows)
            stats.update(positive=labels[1],negative=labels[0])
        failures=[{'gate':name,'actual':stats.get(name,0),'required':minimum}
                  for name,minimum in protocol['minimums'][split].items() if stats.get(name,0)<minimum]
        for name,counts,bound in [('pair_concentration',pair_counts,protocol['maximum_pair_fraction']),
                                   ('entry_day_concentration',days,protocol['maximum_entry_day_fraction'])]:
            share=Decimal(max(counts.values(),default=0))/len(rows) if rows else Decimal(0)
            if share>Decimal(bound):failures.append({'gate':name,'actual':str(share),'maximum':bound})
        if as_of<end:failures.append({'gate':'window_not_finished','ends_at':end.isoformat()})
        summaries[split]={'counts':stats,'failures':failures,'ready':not failures,
                          'excluded':dict(excluded),'snapshot_cutoff':cutoff.isoformat(),
                          'outcomes_hidden':split in {'sealed_test','paper'}}
    blocked=[]
    if not source_healthy:blocked.append('unverified_stale_or_incomplete_collection_snapshot')
    if overlaps:blocked.append('buy_identity_crosses_split_boundaries')
    result={'protocol_version':protocol['protocol_version'],'as_of':as_of.isoformat(),'splits':summaries,
            'cross_split_buy_conflicts':len(overlaps),'blocked_reasons':blocked,
            'data_ready_for_offline_fit':not blocked and summaries['train']['ready'] and summaries['validation']['ready'],
            'sealed_test_data_ready':not blocked and summaries['sealed_test']['ready'],
            'automatic_training_allowed':False,'live_promotion_allowed':False,
            'paper_harness_implemented':False,'profitability_established':False}
    if include_training_rows:result['_training_rows']=training_rows
    return result



def collection_contract_counts(rows):
    seen=set();counts=Counter()
    for row in rows:
        key=buy_key(row)
        if key in seen:raise ValueError('duplicate collection buy identity')
        seen.add(key);counts[row.get('input_candle_state','unknown')]+=1
    return {'distinct_buys':len(seen),'by_input_candle_state':dict(counts),
            'different_contracts_mixed_for_training':False}
