"""Resume one observed study subject to the original offline worker reserves."""
import argparse,json,os,subprocess,sys
from datetime import datetime,UTC
from pathlib import Path
from cryptoforge.research_attempts import identity
from cryptoforge.strategy_extension_study import dependencies
from cryptoforge.extension_report_evidence import verify_extension_report
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.buy_hold_context import buy_hold_context
from cryptoforge.source_contract import net_research_sources
from cryptoforge.research_evidence import verify_registered_report

ROOT=Path(__file__).resolve().parents[1]


def run(receipt_path):
    status={'observed_at':datetime.now(UTC).isoformat(),'completed':False,'live_promotion_allowed':False}
    try:
        receipt=json.loads(receipt_path.read_bytes());manifest=receipt['manifest'];sha=receipt['study_sha256']
        if identity(manifest)!=sha or receipt_path.parent.name!=sha:raise ValueError('observed study receipt changed')
        if manifest['scope']=='catalog_extensions_fixed_vs_atr_development':
            source_dependencies=dependencies();verifier=verify_extension_report
            runner=ROOT/'scripts/evaluate_strategy_extensions.py'
        elif manifest['scope']=='fixed_stake_buy_hold_development_context':
            source_dependencies=net_research_sources('passive',buy_hold_context,runner=ROOT/'scripts/evaluate_buy_hold_context.py')
            verifier=verify_registered_report;runner=ROOT/'scripts/evaluate_buy_hold_context.py'
        else:raise ValueError('fixed supported research scope required')
        output=receipt_path.with_name('results.json')
        if output.exists():
            report=json.loads(output.read_bytes())
            if report['study_sha256']!=sha:raise ValueError('foreign extension report')
            status.update(verifier(report,ROOT/'.local/state/research-attempts.sqlite'),status='completed',completed=True)
        else:
            assert_source_dependencies(manifest['implementation_hashes'],source_dependencies)
            proc=subprocess.run([sys.executable,str(runner),'--receipt',str(receipt_path)],
                cwd=ROOT,capture_output=True,text=True,timeout=135,env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'PYTHONDONTWRITEBYTECODE':'1'})
            if proc.returncode==0:
                if not output.exists():raise ValueError('process success has no complete evidence')
                return run(receipt_path)
            if any(message in proc.stderr for message in ('insufficient resources:','another offline research worker')):
                status['status']='deferred_resource_or_worker_guard'
            else:status.update(status='blocked_study_failure',exit_code=proc.returncode,error_tail=proc.stderr[-2000:])
    except Exception as exc:status.update(status='blocked_contract_or_source',error_class=type(exc).__name__)
    write_json_report(receipt_path.with_name('status.json'),status);return status


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.receipt)))


if __name__=='__main__':main()
