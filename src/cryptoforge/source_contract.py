"""Refuse a frozen model replay when its feature/runtime dependencies changed."""
import hashlib,inspect
from pathlib import Path


def assert_source_dependencies(expected,functions):
    actual=source_hashes(functions)
    if any(expected.get(name)!=sha for name,sha in actual.items()):
        raise ValueError('frozen model source dependency changed; require a new fitted study')
    return actual


def source_hashes(functions):
    return {name:hashlib.sha256((function if isinstance(function,Path) else Path(inspect.getfile(function))).read_bytes()).hexdigest()
            for name,function in functions.items()}


def net_research_sources(head_name,head,*,runner=None,context=False):
    """Explicit feature/label dependencies, including observation-time guards."""
    from cryptoforge.archive import ArchiveReader
    from cryptoforge.candle_contract import known_closed
    from cryptoforge.causal_features import feature_snapshots
    from cryptoforge.model_training import fit_standardizer
    from cryptoforge.net_regression import evaluate_net_regressor
    from cryptoforge.research_protocol import assert_development_range
    from cryptoforge.supabase_executor import rsi
    from cryptoforge.trade_labels import build_trade_labels
    from cryptoforge.trade_risk_labels import trade_risk_outcome
    from cryptoforge.trade_simulator import SimulationConfig
    from cryptoforge.entry_risk import atr_entry_risk
    from cryptoforge.exit_rules import price_time_exit
    from cryptoforge.spot_buy_math import spot_acquisition
    functions={head_name:head,'archive_reader':ArchiveReader,'candle_contract':known_closed,
        'causal_features':feature_snapshots,'feature_standardizer':fit_standardizer,
        'net_evaluation':evaluate_net_regressor,'research_range':assert_development_range,
        'rsi_dependency':rsi,'trade_labels':build_trade_labels,'trade_risk_labels':trade_risk_outcome,
        'simulator':SimulationConfig,'entry_risk_dependency':atr_entry_risk,'exit_rule_dependency':price_time_exit,'buy_math_dependency':spot_acquisition,'source_manifest':net_research_sources}
    if runner is not None:functions['runner']=runner
    if context:
        from cryptoforge.context_features import context_snapshots
        from cryptoforge.closed_timeframes import aggregate_closed
        functions.update(context_features=context_snapshots,closed_timeframes=aggregate_closed)
    return functions


def primary_training_sources():
    from cryptoforge.training_snapshot import save_training_snapshot
    from cryptoforge.model_training import train_logistic_model
    from cryptoforge.candle_contract import closed_snapshot
    from cryptoforge.classifier_diagnostics import split_diagnostics
    from cryptoforge.supabase_executor import rsi
    from cryptoforge.feature_drift import training_feature_reference
    return {'primary_training':train_logistic_model,'candle_contract':closed_snapshot,
        'rsi_dependency':rsi,'classifier_diagnostics':split_diagnostics,
        'training_snapshot':save_training_snapshot,'feature_support':training_feature_reference,
        'source_manifest':primary_training_sources}
