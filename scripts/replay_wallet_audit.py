"""Verify saved wallet reconciliation read-only, without another account request."""
import argparse
import json
from pathlib import Path
from cryptoforge.execution_market_evidence import _load
from cryptoforge.inventory_audit import verify_inventory
from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.execution_identity import unique_executions
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.training_snapshot import load_runtime_sources


def replay(path):
    report=json.loads(path.read_bytes())
    deps={'wallet':BybitPrivateClient,'inventory':verify_inventory,'identity':unique_executions,
          'runner':Path(__file__).with_name('audit_cached_wallet.py').resolve()}
    assert_source_dependencies(report['implementation_hashes'],deps)
    load_runtime_sources(report['runtime_source_bundle'],report['implementation_hashes'])
    inputs=_load(report['input_reference'])
    actual=verify_inventory(inputs['fills'],inputs['transactions'],inputs['normalized_wallet_coins'])
    if actual!=report['inventory_audit']:raise ValueError('saved wallet reconciliation differs from source replay')
    if report['historical_fills_complete_certified'] is not False or report['live_promotion_allowed'] is not False:
        raise ValueError('source diagnostic scope changed')
    return {'replay_matches':True,'consistent':actual['consistent'],'tracked_coins':len(actual['coins']),
            'current_wallet_requeried':False,'historical_fills_complete_certified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    print(json.dumps(replay(parser.parse_args().report)))


if __name__=='__main__':main()
