"""One source-bound pending replay; no automatic parameter or source revisions."""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,UTC
from pathlib import Path
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.immutable_files import install_original

ROOT=Path(__file__).resolve().parents[1]
REQUEST=ROOT/'.local/state/pending-portfolio-replay-request-v2.json'
STATUS=ROOT/'.local/state/pending-portfolio-replay-status.json'
OUTPUT=ROOT/'.local/state/registered-detailed-portfolio-replay.json'
FILES=['scripts/retry_portfolio_replay.py','scripts/backtest_archive_portfolio.py',
    'src/cryptoforge/trade_simulator.py','src/cryptoforge/strategy_search.py','src/cryptoforge/night_research.py',
    'src/cryptoforge/archive.py','src/cryptoforge/exit_rules.py','src/cryptoforge/entry_risk.py',
    'src/cryptoforge/spot_buy_math.py','src/cryptoforge/source_contract.py','src/cryptoforge/research_protocol.py',
    'src/cryptoforge/research_attempts.py','src/cryptoforge/strategy_hypotheses.py',
    'config/strategy-hypothesis-catalog-v1.json','config/research-protocol-v1.json']


def hashes():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--register-only',action='store_true')
    args=parser.parse_args(argv)
    command=['scripts/backtest_archive_portfolio.py','--pair','BTC/USDT','--pair','ETH/USDT',
        '--max-candles','2000','--detailed-equity','--output',str(OUTPUT)]
    if not REQUEST.exists():
        raw=json.dumps({'observed_at':datetime.now(UTC).isoformat(),'sources':hashes(),'command':command,'orders_allowed':False},sort_keys=True).encode()
        install_original(REQUEST,raw)
    request=json.loads(REQUEST.read_bytes())
    if args.register_only:return 0
    result={'observed_at':datetime.now(UTC).isoformat(),'completed':False,'orders_allowed':False}
    if request.get('command')!=command or request.get('orders_allowed') is not False:
        result['status']='queued_request_changed_review_required'
    elif request['sources']!=hashes():result['status']='queued_source_changed_review_required'
    elif OUTPUT.exists():
        report=json.loads(OUTPUT.read_bytes())
        result.update(status='original_registered_replay_preserved',completed=True,study=report['research_study_sha256'])
    else:
        run=subprocess.run([sys.executable,*command],cwd=ROOT,capture_output=True,text=True,timeout=40)
        if run.returncode==0:
            report=json.loads(OUTPUT.read_bytes());result.update(status='registered_replay_completed',completed=True,study=report['research_study_sha256'])
        elif any(message in run.stderr for message in ('insufficient resources:','another offline research worker')):
            result['status']='deferred_by_resource_or_worker_guard'
        else:
            result['status']='registered_replay_failed';write_json_report(STATUS,result);raise RuntimeError('registered replay failed; inspect worker journal and attempt ledger')
    write_json_report(STATUS,result);print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
