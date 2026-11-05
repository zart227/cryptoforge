"""Prospective, exact cash-entry hypotheses over retained closed source polls.

These rules consume candles, never a price-label probability. Their thresholds
are explicit research hypotheses, not expected returns or qualified strategies.
"""
from dataclasses import asdict,dataclass
from datetime import UTC,datetime,timedelta
from fractions import Fraction
from pathlib import Path

from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new,_sync
from cryptoforge.reference_delivery import ReferenceDelivery,ROLES,runtime_hashes as delivery_runtime
from cryptoforge.reference_source_ledger import _sources_ready

FLAGS=dict(full_worker_or_host_qualified=False,paper_evidence_pass=False,
    economic_profitability_established=False,live_admission_granted=False)


@dataclass(frozen=True)
class CashEntryRule:
    role:str
    family:str
    lookback_candles:int
    round_trip_cost_bps:int
    minimum_momentum_buffer_bps:int
    minimum_volume_ratio_bps:int
    maximum_last_range_bps:int

    def __post_init__(self):
        values=asdict(self)
        limits=dict(lookback_candles=(2,119),round_trip_cost_bps=(1,1000),
            minimum_momentum_buffer_bps=(0,1000),minimum_volume_ratio_bps=(1,100000),
            maximum_last_range_bps=(1,10000))
        if (self.role not in ROLES or self.family not in ('cash_only','momentum_breakout_v1')
                or any(type(values[k]) is not int or not lo<=values[k]<=hi for k,(lo,hi) in limits.items())):
            raise ValueError('explicit bounded cash-entry hypothesis required')

    @property
    def strategy_sha256(self):
        return digest(canonical(dict(schema_version='cash-entry-hypothesis-v1',rule=asdict(self),
            interpretation='closed_past_signal_not_future_profit_or_model_probability')))


def _current_runtime():
    return dict(delivery_runtime(),cash_entry_contract=digest(Path(__file__).read_bytes()),
        cash_entry_cli=digest((Path(__file__).resolve().parents[2]/'scripts/cash_reference_application.py').read_bytes()))


def runtime_hashes():
    value=_current_runtime()
    if value!=_LOADED_RUNTIME:raise ValueError('cash contract runtime changed; new process/namespace required')
    return value


def _queue_identity(queue):
    return {k:queue.reference[k] for k in ('root','manifest_sha256','registration_sha256')}


def freeze_cash_contract(root,queue,*,rules,closeout_seconds,maximum_decision_latency_seconds=30,clock=None):
    if type(queue) is not ReferenceDelivery or type(rules) not in (list,tuple):
        raise ValueError('original queue and explicit three-role rules required')
    before=stamp((clock or (lambda:datetime.now(UTC)))())
    with queue._lease():
        queue._check();receipt=queue._receipt();pairs=queue.source_manifest['pairs']
        typed=[r if type(r) is CashEntryRule else CashEntryRule(**r) for r in rules]
        by_role={r.role:r for r in typed}
        if (len(typed)!=3 or set(by_role)!=set(ROLES) or by_role['control'].family!='cash_only'
                or by_role['candidate'].family!='momentum_breakout_v1' or by_role['stress'].family!='momentum_breakout_v1'
                or by_role['stress'].round_trip_cost_bps<by_role['candidate'].round_trip_cost_bps
                or any(asdict(by_role['stress'])[k]!=asdict(by_role['candidate'])[k] for k in asdict(by_role['candidate']) if k not in ('role','round_trip_cost_bps'))
                or queue.manifest['mode']!='prospective' or queue.manifest['artifact_sha256'] is not None
                or receipt['events'] or receipt['batches'] or receipt['source_events']
                or queue.policy.maximum_source_events_per_batch!=len(pairs)+2
                or not stamp(queue.manifest['registered_at'])<=before<stamp(queue.manifest['start'])
                or type(closeout_seconds) is not int or not 1<=closeout_seconds<(stamp(queue.manifest['end'])-stamp(queue.manifest['start'])).total_seconds()
                or type(maximum_decision_latency_seconds) is not int or not 1<=maximum_decision_latency_seconds<=30):
            raise ValueError('empty prospective one-poll queue and explicit cash/control/stress contract required')
        value=dict(schema_version='cash-reference-entry-contract-v1',root=str(Path(root).absolute()),
            registered_at=before.isoformat(),queue_identity=_queue_identity(queue),source_manifest_sha256=queue.manifest['source_manifest_sha256'],
            start=queue.manifest['start'],end=queue.manifest['end'],pairs=pairs,closeout_seconds=closeout_seconds,
            entry_cutoff=(stamp(queue.manifest['end'])-timedelta(seconds=closeout_seconds)).isoformat(),
            maximum_decision_latency_seconds=maximum_decision_latency_seconds,
            rules={r:asdict(by_role[r]) for r in ROLES},strategies={r:by_role[r].strategy_sha256 for r in ROLES},
            runtime=runtime_hashes(),arithmetic='exact_rational_from_original_decimal_strings',
            opportunity_scope='every_fixed_pair_in_each_delivered_completed_poll_including_negative_skip_failure',
            control_scope='hold_cash_control_not_legacy_active_model',price_label_probability_consumed=False,**FLAGS)
        root=_new_root(root,forbidden=(queue.root,Path(queue.manifest['source_identity']['root'])))
        pin=_write_new(root/'contract.json',value)
        completed=stamp((clock or (lambda:datetime.now(UTC)))())
        if not before<=completed<stamp(value['start']):raise ValueError('cash contract missed prospective start')
        ready=_write_new(root/'registered.json',dict(contract_sha256=pin,registered_at=completed.isoformat()))
        if not completed<=stamp((clock or (lambda:datetime.now(UTC)))())<stamp(value['start']):
            (root/'registered.json').unlink();_sync(root);raise ValueError('cash contract durable completion missed start')
    reference=dict(root=str(root),contract_sha256=pin,registration_sha256=ready)
    load_cash_contract(reference)
    return reference


def load_cash_contract(reference):
    if type(reference) is not dict or set(reference)!={'root','contract_sha256','registration_sha256'}:
        raise ValueError('original cash contract pins required')
    root=Path(reference['root']).absolute();raw=read_file(root/'contract.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
    value=parse(raw);registered=parse(ready)
    if (root.resolve()!=root or value['root']!=str(root) or {p.name for p in root.iterdir()}!={'contract.json','registered.json'}
            or digest(raw)!=sha(reference['contract_sha256']) or digest(ready)!=sha(reference['registration_sha256'])
            or value['schema_version']!='cash-reference-entry-contract-v1' or value['runtime']!=runtime_hashes()
            or value['arithmetic']!='exact_rational_from_original_decimal_strings'
            or value['price_label_probability_consumed'] is not False or any(value[k] is not False for k in FLAGS)
            or registered['contract_sha256']!=reference['contract_sha256']
            or not stamp(value['registered_at'])<=stamp(registered['registered_at'])<stamp(value['start'])<stamp(value['entry_cutoff'])<stamp(value['end'])
            or set(value['rules'])!=set(ROLES) or any(CashEntryRule(**value['rules'][r]).strategy_sha256!=value['strategies'][r] for r in ROLES)):
        raise ValueError('original prospective cash contract differs')
    return value


def _ratio(value):
    if type(value) is not str or not 0<len(value)<=64:raise ValueError('bounded original decimal string required')
    from decimal import Decimal
    number=Decimal(value)
    if not number.is_finite() or abs(number.as_tuple().exponent)>24 or len(number.as_tuple().digits)>44:
        raise ValueError('bounded finite candle decimal required')
    return Fraction(number)


def _metrics(rule,rows):
    if len(rows)!=120:raise ValueError('complete closed120 cash inputs required')
    last=rows[-1]['raw_row'];prior=[row['raw_row'] for row in rows[-rule.lookback_candles-1:-1]]
    close=_ratio(last[4]);base=_ratio(prior[0][4]);volume=_ratio(last[5])
    if min(close,base)<=0:raise ValueError('positive cash candle prices required')
    average=sum((_ratio(r[5]) for r in prior),Fraction(0))/len(prior)
    momentum=(close/base-1)*10000;span=(_ratio(last[2])-_ratio(last[3]))/close*10000
    breakout=close>max(_ratio(r[2]) for r in prior)
    values=dict(momentum_bps=momentum,last_range_bps=span,volume_ratio_bps=volume/average*10000 if average else None)
    metrics={k:[v.numerator,v.denominator] if v is not None else None for k,v in values.items()}
    if average<=0:return 'zero_baseline_volume',metrics
    if momentum<rule.round_trip_cost_bps+rule.minimum_momentum_buffer_bps:return 'momentum_below_cost_buffer',metrics
    if not breakout:return 'not_breakout',metrics
    if volume*10000<average*rule.minimum_volume_ratio_bps:return 'volume_below_threshold',metrics
    if span>rule.maximum_last_range_bps:return 'last_range_too_wide',metrics
    return 'enter',metrics


def evaluate_cash_packet(contract,contract_sha256,packet,role,*,observed_at):
    """Pure decision derivation. Caller must obtain the packet from its pinned queue."""
    now=stamp(observed_at);sha(contract_sha256)
    if role not in ROLES or packet['delivery']['role']!=role:raise ValueError('original cash role required')
    if not stamp(contract['start'])<=now<stamp(contract['end']):raise ValueError('cash decision outside frozen window')
    events=packet['source_events'];prepared=[e['payload'] for e in events if e['kind']=='poll_prepared'];complete=[e['payload'] for e in events if e['kind']=='poll_complete']
    responses=[e['payload'] for e in events if e['kind']=='source_response']
    if (len(prepared)!=1 or len(complete)!=1 or len(events)!=len(contract['pairs'])+2
            or len(responses)!=len(contract['pairs']) or prepared[0]['pairs']!=contract['pairs']
            or complete[0]['poll_id']!=prepared[0]['poll_id']
            or [v['observation']['pair'] for v in responses]!=contract['pairs']
            or any(v['poll_id']!=prepared[0]['poll_id'] for v in responses)
            or set(packet['source_view']['windows'])!=set(contract['pairs'])
            or not stamp(complete[0]['completed_at'])<=stamp(packet['delivery']['offered_at'])<=now):
        raise ValueError('one complete original poll for every fixed pair required')
    rule=CashEntryRule(**contract['rules'][role]);view=packet['source_view'];decisions=[];predictions=[]
    for pair in contract['pairs']:
        reason=None;metrics={}
        if now>=stamp(contract['entry_cutoff']):reason='entry_window_finished'
        elif (now-stamp(complete[0]['completed_at'])).total_seconds()>contract['maximum_decision_latency_seconds']:reason='source_batch_expired'
        elif view['missing_source_poll_slots']:reason='source_poll_gap'
        elif not _sources_ready(view['windows'],now):reason='source_unavailable'
        elif rule.family=='cash_only':reason='hold_cash_control'
        else:reason,metrics=_metrics(rule,view['windows'][pair]['derived']['rows'])
        opportunity=digest(canonical(dict(contract_sha256=contract_sha256,role=role,poll_id=complete[0]['poll_id'],pair=pair)))
        decision=dict(opportunity=opportunity,pair=pair,role=role,decision_at=now.isoformat(),reason=reason,would_enter=reason=='enter',
            strategy_sha256=contract['strategies'][role],poll_id=complete[0]['poll_id'],metrics=metrics,
            source_window_sha256=digest(canonical(view['windows'].get(pair))),source_completed_at=complete[0]['completed_at'])
        decisions.append(decision)
        predictions.append(dict(candidate_sha256=decision['strategy_sha256'],opportunity=opportunity,pair=pair,
            predicted_at=now.isoformat(),observed_at=now.isoformat(),would_enter=decision['would_enter']))
    return dict(decisions=decisions,predictions=predictions,source_id=packet['delivery']['delivery_id'],
        source_observed_at=now.isoformat(),source_sha256=digest(canonical(predictions)),
        all_fixed_pairs_recorded=True,price_label_probability_consumed=False,**FLAGS)


_LOADED_RUNTIME=_current_runtime()
