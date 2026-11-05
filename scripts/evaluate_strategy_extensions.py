"""Register catalogued strategy comparisons before evaluating viewed development."""
import argparse,json
from pathlib import Path
from cryptoforge.strategy_extension_study import freeze_study,evaluate_study
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.research_protocol import prepare_research


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--register',action='store_true');group.add_argument('--receipt',type=Path)
    parser.add_argument('--resource-protocol',type=Path)
    args=parser.parse_args();directory=Path('.local/state/strategy-extension-studies');ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
    if args.register:
        receipt=freeze_study(directory,ledger,args.resource_protocol);path=directory/receipt['study_sha256']/'protocol.json'
        if path.exists():
            if json.loads(path.read_bytes())!=receipt:raise ValueError('original observed receipt changed')
        else:write_json_report(path,receipt)
        print(json.dumps({'registered_study':receipt['study_sha256'],'receipt':str(path.resolve()),'configuration_budget_reserved':4}));return
    receipt=json.loads(args.receipt.read_bytes());output=args.receipt.with_name('results.json')
    protocol=prepare_research(receipt['manifest'].get('resource_protocol_path','config/research-protocol-v1.json'))
    result=evaluate_study(receipt,ledger,directory,protocol)
    if output.exists():
        if json.loads(output.read_bytes())!=result:raise ValueError('original report is immutable')
    else:write_json_report(output,result)
    print(json.dumps({'completed_configurations':result['completed_configurations'],'live_promotion_allowed':False}))


if __name__=='__main__':main()
