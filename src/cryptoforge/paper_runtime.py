"""Bind prospective execution to the source files observed at policy freeze."""
from cryptoforge.source_contract import source_hashes
from pathlib import Path


def paper_runtime_sources():
    from cryptoforge.paper_worker import PaperWorker
    from cryptoforge.paper_wallet import PaperWallet
    from cryptoforge.paper_market import observe_market
    from cryptoforge.paper_observations import SharedExitObservations
    from cryptoforge.paper_activation import load_activation
    from cryptoforge.exit_rules import price_time_exit
    from cryptoforge.supabase_executor import exit_signal
    from cryptoforge.candle_contract import known_closed
    from cryptoforge.market_data import BybitPublicClient
    from cryptoforge.paper_results import export_results
    from cryptoforge.paper_acceptance import evaluate_paper
    from cryptoforge.paper_policy_design import validate_execution_design
    from cryptoforge.spot_buy_math import spot_acquisition
    return {'worker':PaperWorker,'wallet':PaperWallet,'market':observe_market,
        'exit_observations':SharedExitObservations,'activation':load_activation,'exit_rules':price_time_exit,
        'shared_exit_indicator':exit_signal,'candle_contract':known_closed,'public_client':BybitPublicClient,
        'results_exporter':export_results,'acceptance_evaluator':evaluate_paper,'execution_design':validate_execution_design,'buy_math':spot_acquisition,
        'source_hash_dependency':source_hashes,'runtime_manifest':paper_runtime_sources,
        'worker_runner':Path(__file__).resolve().parents[2]/'scripts/run_cash_paper.py',
        'export_runner':Path(__file__).resolve().parents[2]/'scripts/export_cash_paper.py',
        'evaluation_runner':Path(__file__).resolve().parents[2]/'scripts/evaluate_cash_paper.py'}


def paper_runtime_hashes():return source_hashes(paper_runtime_sources())


def verify_paper_runtime(policy):
    expected=policy.get('implementation_hashes')
    if not isinstance(expected,dict) or expected!=paper_runtime_hashes():
        raise ValueError('paper execution runtime differs from observed freeze; require a new preregistered study')
    if policy.get('runtime_source_bundle') is not None:
        from cryptoforge.training_snapshot import load_runtime_sources
        load_runtime_sources(policy['runtime_source_bundle'],expected)
