"""Frozen development comparison of catalogued extensions and ATR risk controls."""
from dataclasses import asdict
from datetime import UTC,datetime,timedelta
from decimal import Decimal
import hashlib,json
from pathlib import Path
from cryptoforge.archive import ArchiveReader
from cryptoforge.strategy_extensions import ExtensionSpec,extension_signal
from cryptoforge.entry_risk import atr_entry_risk
from cryptoforge.supabase_executor import entry_signal
from cryptoforge.trade_simulator import SimulationConfig,simulate_portfolio
from cryptoforge.portfolio_diagnostics import portfolio_diagnostics
from cryptoforge.equity_blocks import daily_changes,block_interval
from cryptoforge.research_attempts import identity,ResearchAttempts
from cryptoforge.source_contract import net_research_sources,source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import _save_raw,save_runtime_sources,load_runtime_sources
from cryptoforge.research_protocol import validate_protocol

ROOT=Path(__file__).resolve().parents[2]


def dependencies():
    deps=net_research_sources('study',evaluate_candidate,runner=ROOT/'scripts/evaluate_strategy_extensions.py')
    deps.update(extensions=extension_signal,baseline=entry_signal,ledger=ResearchAttempts,
        portfolio_diagnostics=portfolio_diagnostics,daily_blocks=daily_changes,block_bootstrap=block_interval)
    return deps


def config():return SimulationConfig(exit_minimum_policy='preserve_inventory')


def freeze_study(directory,ledger,resource_protocol_path=None):
    protocol_raw=(ROOT/'config/research-protocol-v1.json').read_bytes();protocol=json.loads(protocol_raw)
    validate_protocol(protocol)
    resource_path=Path(resource_protocol_path or ROOT/'config/research-protocol-v1.json').resolve()
    resource_raw=resource_path.read_bytes();resource_protocol=json.loads(resource_raw)
    validate_protocol(resource_protocol)
    expected=json.loads(protocol_raw)
    expected['resources']['min_available_memory_mb']=resource_protocol['resources']['min_available_memory_mb']
    observed={key:value for key,value in resource_protocol.items() if key!='resource_override'}
    if identity(expected)!=identity(observed) or resource_protocol['resources']['min_available_memory_mb']<1024:
        raise ValueError('only authorized memory reserve may differ from original protocol')
    catalog_raw=(ROOT/'config/strategy-extensions-catalog-v1.json').read_bytes();catalog=json.loads(catalog_raw)
    if [item['family'] for item in catalog['families']]!=['support_bounce','compression_breakout']:
        raise ValueError('original catalog families required')
    for filename,expected in catalog['source_sha256'].items():
        if hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()!=expected:
            raise ValueError('catalog source changed; require a new observed catalog')
    for dataset in protocol['datasets']:
        if hashlib.sha256((ROOT/dataset['path']).read_bytes()).hexdigest()!=dataset['sha256']:raise ValueError('original dataset changed')
    deps=dependencies();hashes=source_hashes(deps);runtime=save_runtime_sources(directory/'runtime',deps,hashes)
    manifest={'scope':'catalog_extensions_fixed_vs_atr_development','grid':[{'family':family,'risk':risk} for family in
        ('support_bounce','compression_breakout') for risk in ('fixed','atr')],
        'base_config':asdict(config()),'implementation_hashes':hashes,'runtime_source_bundle':runtime,
        'protocol_sha256':hashlib.sha256(protocol_raw).hexdigest(),'catalog_sha256':hashlib.sha256(catalog_raw).hexdigest(),
        'resource_protocol_path':str(resource_path),'resource_protocol_sha256':hashlib.sha256(resource_raw).hexdigest(),
        'datasets':protocol['datasets'],'pairs':protocol['baseline_pairs'],'input_policy':'tail5000_first3500_development',
        'entry_context_candles':120,'baseline_flags':{'allow_intraday_reversion':True,'allow_emerging_momentum':True},
        'extension_specs':[asdict(ExtensionSpec(family)) for family in ('support_bounce','compression_breakout')],
        'atr_design':{'period':14,'stop_multiple':'1.5','target_multiple':'3','minimum_stop':'.005','maximum_stop':'.04',
            'minimum_target':'.01','maximum_target':'.08','hold_bars':12},
        'stress_multiplier':2,'bootstrap':{'minimum_days':14,'block_days':2,'repetitions':2000,'seed':20261013},
        'historical_execution_rules_certified':False,'independent_evidence':False,'live_promotion_allowed':False}
    # Preserve the original protocol's existing budget identity convention.
    manifest['budget_protocol_id']=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    sha=ledger.register(manifest,protocol_id=manifest['budget_protocol_id'],
        maximum_per_family=protocol['search_limits']['max_configurations_per_family'],protocol_version=protocol['protocol_version'])
    # JSON conversion preserves exactly the ledger's canonical Decimal encoding.
    return {'study_sha256':sha,'manifest':json.loads(json.dumps(manifest,default=str))}


def signal_sets(data,manifest,family):
    baseline={};extension={}
    for pair,rows in data.items():
        base=[];selected=[];spec=ExtensionSpec(family)
        for index in range(manifest['entry_context_candles']-1,len(rows)-1):
            observed=rows[index].open_time+timedelta(minutes=5)
            allowed,_=entry_signal(rows[index-119:index+1],**manifest['baseline_flags'])
            if allowed:base.append(rows[index].open_time)
            if extension_signal(rows,index,spec,as_of=observed)['would_enter']:selected.append(rows[index].open_time)
        baseline[pair]=base;extension[pair]=selected
    return baseline,extension


def evaluate_candidate(data,manifest,candidate):
    if candidate not in manifest['grid']:raise ValueError('declared complete-grid candidate required')
    baseline,selected=signal_sets(data,manifest,candidate['family'])
    cfg=config();stress=cfg.stress_costs(manifest['stress_multiplier']);risk=candidate['risk']
    def run(signals,costs):
        plans=None
        if risk=='atr':
            plans={}
            for pair,stamps in signals.items():
                indexes={row.open_time:index for index,row in enumerate(data[pair])}
                design={key:Decimal(value) if isinstance(value,str) else value for key,value in manifest['atr_design'].items()}
                for stamp in stamps:
                    plans[(pair,stamp)]=atr_entry_risk(data[pair],indexes[stamp],as_of=stamp+timedelta(minutes=5),**design)
        outcome=simulate_portfolio(data,signals,costs,entry_risks=plans)
        diagnostics=portfolio_diagnostics(outcome,signals)
        diagnostics.update(final_cash=str(outcome.final_cash),drawdown_bound=str(outcome.max_drawdown))
        return outcome,diagnostics
    outcomes={};roles={}
    for name,signals,costs in (('baseline',baseline,cfg),('filtered',selected,cfg),
            ('stress_baseline',baseline,stress),('stress_filtered',selected,stress)):
        outcomes[name],roles[name]=run(signals,costs)
    paired={}
    for prefix in ('','stress_'):
        left,right=(outcomes[prefix+name] for name in ('filtered','baseline'))
        if [stamp for stamp,_ in left.equity]!=[stamp for stamp,_ in right.equity]:raise ValueError('same shared-wallet equity grid required')
        a,b=(daily_changes(item,initial_capital=cfg.capital) for item in (left,right))
        days=a['bootstrap_eligible_full_days'];other=b['bootstrap_eligible_full_days']
        if set(days)!=set(other):raise ValueError('paired full-day coverage required')
        changes={day:str(Decimal(days[day])-Decimal(other[day])) for day in days}
        paired[prefix+'candidate_minus_baseline']={'block_interval':block_interval(changes,**manifest['bootstrap']),
            'daily_equity_difference_fraction_initial_capital':changes,'unclosed_inventory':bool(left.open_positions or right.open_positions)}
    return {'candidate':candidate,'roles':roles,'initial_capital':str(cfg.capital),'paired_differences':paired,
        'cash_only_baseline':{'net_pnl':'0','final_cash':str(cfg.capital)},
        'candidate_can_introduce_new_opportunities':True,'filter_subset_of_baseline_verified':False,
        'baseline_risk_method':risk,'scope':'development_strategy_extension_comparison_not_ML_filter',
        'model_fitting_performed':False,'independent_evidence':False,'live_promotion_allowed':False}


def evaluate_study(receipt,ledger,directory,protocol):
    manifest=receipt['manifest'];sha=receipt['study_sha256']
    if identity(manifest)!=sha:raise ValueError('registered manifest changed')
    assert_source_dependencies(manifest['implementation_hashes'],dependencies())
    load_runtime_sources(manifest['runtime_source_bundle'],manifest['implementation_hashes'])
    resource_path=Path(manifest.get('resource_protocol_path',ROOT/'config/research-protocol-v1.json'))
    resource_raw=resource_path.read_bytes()
    if identity(protocol)!=identity(json.loads(resource_raw)):
        raise ValueError('original research protocol required')
    if hashlib.sha256(resource_raw).hexdigest()!=manifest.get('resource_protocol_sha256',manifest['protocol_sha256']):
        raise ValueError('registered execution resource profile changed')
    if hashlib.sha256((ROOT/'config/research-protocol-v1.json').read_bytes()).hexdigest()!=manifest['protocol_sha256']:
        raise ValueError('original protocol changed')
    data={pair:ArchiveReader(ROOT/'.local/archive',protocol=protocol).read_candles(pair,limit=5000)[:3500] for pair in manifest['pairs']}
    if any(len(rows)!=3500 for rows in data.values()):raise ValueError('complete frozen development slice required')
    original=_save_raw(directory/'inputs',json.dumps({pair:[asdict(row) for row in rows] for pair,rows in data.items()},sort_keys=True,default=str).encode())
    results=[]
    for candidate in manifest['grid']:
        prior=ledger.result(sha,candidate)
        if prior is None:
            started=datetime.now(UTC);result=evaluate_candidate(data,manifest,candidate)
            assert_source_dependencies(manifest['implementation_hashes'],dependencies())
            result.update(study_sha256=sha,execution_started_at=started.isoformat(),execution_finished_at=datetime.now(UTC).isoformat(),input_snapshot=original)
            ledger.record(sha,candidate,result);prior=result
        results.append(prior)
    return {'study_sha256':sha,'manifest':manifest,'results':results,'completed_configurations':len(results),
        'independent_evidence':False,'live_promotion_allowed':False}
