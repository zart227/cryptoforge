"""Versioned semantic targets; changing a name never migrates learned outcomes."""
from dataclasses import dataclass,asdict


@dataclass(frozen=True)
class TargetContract:
    version: str
    outcome_kind: str
    fee_accounting: str
    sample_kind: str
    short_labels_allowed: bool


CONTRACTS={
    'fixed-future-return-v1':TargetContract('fixed-future-return-v1','future_close_price_return',
        'price_return_excludes_execution_fees','candle_endpoint',True),
    'spot-long-trade-net-v2':TargetContract('spot-long-trade-net-v2','simulated_net_pnl_over_entry_cost',
        'declared_simulator_cost_scenario','counterfactual_independent_entry',False),
    'spot-long-real-cash-recovery-dust-zero-v1':TargetContract('spot-long-real-cash-recovery-dust-zero-v1',
        'recovered_cash_minus_acquisition_cost_over_cost','observed_cash_recovery_residual_zero_convention',
        'observed_buy_cohort',False)}


def require_artifact_target(artifact, *, expected_target, allow_legacy_price=False):
    if expected_target not in CONTRACTS:raise ValueError('known expected target contract required')
    config=artifact.get('config') or {}
    declared=[container['target_version'] for container in (artifact,config) if 'target_version' in container]
    inferred=False
    if not declared:
        if (not allow_legacy_price or expected_target!='fixed-future-return-v1'
                or config.get('source')=='observed_real_cash_recovery_memory'
                or str(artifact.get('model_version','')).startswith('cash-recovery-')):
            raise ValueError('explicit artifact target required; migration cannot be inferred')
        target='fixed-future-return-v1';inferred=True
    else:
        if any(value!=declared[0] for value in declared):raise ValueError('artifact target declarations disagree')
        target=declared[0]
    if not isinstance(target,str) or target not in CONTRACTS:raise ValueError('unsupported artifact target version')
    if target=='fixed-future-return-v1' and config.get('source')=='observed_real_cash_recovery_memory':
        raise ValueError('cash provenance contradicts declared price target')
    if target!=expected_target:raise ValueError('artifact target incompatible with requested prediction task')
    return {'schema_version':'target-contract-description-v1',**asdict(CONTRACTS[target]),
        'legacy_primary_price_target_inferred':inferred,'target_migration_performed':False}
