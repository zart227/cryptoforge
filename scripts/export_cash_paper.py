"""Export isolated simulation evidence; do not publish rewards before paper end."""
from cryptoforge.atomic_reports import write_json_report
from datetime import UTC,datetime
import argparse
import json
from pathlib import Path

from cryptoforge.live_learning_protocol import load_protocol,time
from cryptoforge.paper_results import export_results
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args();now=datetime.now(UTC);protocol,study=load_cash_study(args.protocol)
    roles={}
    for role in ('candidate','baseline_control','stress_candidate'):
        prefix='cash-paper' if role=='candidate' else 'cash-paper-'+role.replace('_','-')
        wallet,worker=study.paper_role_paths(role)
        data=export_results(wallet,worker,as_of=now)
        data['evaluation_role']=role;roles[role]=data
    result={'as_of':now.isoformat(),'schema_version':'paper-role-export-v1','roles':roles,'simulated':True,
            'performance_publication_hidden':now<time(protocol['windows']['paper']['end_exclusive']),
            'real_training_examples_allowed':False,'live_promotion_allowed':False}
    out=study.paper_results;out.parent.mkdir(parents=True,exist_ok=True)
    write_json_report(out,result)
    print(json.dumps({'roles':{r:d['status'] for r,d in roles.items()},'performance_hidden':result['performance_publication_hidden'],
                     'live_promotion_allowed':False,'output':str(out.resolve())}))


if __name__=='__main__':main()
