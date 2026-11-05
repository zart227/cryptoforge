"""Select only from the complete immutable validation grids of both heads."""
import argparse,hashlib,json
from datetime import datetime,UTC
from decimal import Decimal
from pathlib import Path
from cryptoforge.research_attempts import identity
from cryptoforge.validation_evidence import select_registered_validation_reports
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.atomic_reports import write_json_report


def rank_eligible_heads(choices):
    eligible=[]
    for choice in choices:
        selected=choice['selection']['selected_report_sha256']
        if selected is None:continue
        report=next(item for item in choice['reports'] if item['sha256']==selected)['payload']
        metrics=report['portfolio'];cash=Decimal(metrics['initial_cash'])
        eligible.append(((Decimal(metrics['stress_net_pnl'])/cash,Decimal(metrics['net_pnl'])/cash,
                          Decimal(report['candidate']['threshold']),not choice['class_balance']),choice,selected))
    if not eligible:return None
    _,choice,selected=max(eligible,key=lambda item:item[0])
    return {'class_balance':choice['class_balance'],'study_sha256':choice['study_sha256'],
            'report_sha256':selected,'threshold':choice['selection']['selected_threshold']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--unweighted',type=Path,required=True);parser.add_argument('--balanced',type=Path,required=True)
    parser.add_argument('--fold',type=int,default=0);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('immutable selection report already exists')
    plan_raw=args.plan.read_bytes();plan=json.loads(plan_raw);choices=[];now=datetime.now(UTC)
    deps={'ranker':rank_eligible_heads,'verifier':select_registered_validation_reports,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps)
    for balanced,directory in ((False,args.unweighted),(True,args.balanced)):
        studies=[item for item in plan['studies'] if item['manifest']['fold_index']==args.fold
            and item['manifest']['training_policy']['class_balance']==balanced]
        if len(studies)!=1:raise ValueError('one original study per declared head required')
        study=studies[0];manifest=study['manifest'];policy=manifest['selection_policy']
        complete=json.loads((directory/'completed.json').read_bytes())
        if complete['study_sha256']!=study['study_sha256'] or complete['validation_trials_completed']!=3:
            raise ValueError('complete original head evidence required')
        paths={identity(candidate):directory/(identity(candidate)+'.json') for candidate in manifest['grid']}
        selected=select_registered_validation_reports(Path('.local/state/research-attempts.sqlite'),
            study_sha256=study['study_sha256'],reports=paths,validation_start=datetime.fromisoformat(policy['validation_start']),
            validation_end=datetime.fromisoformat(policy['validation_end']),minimum_trades=policy['minimum_trades'],maximum_drawdown=policy['maximum_drawdown'])
        reports=[]
        for path in paths.values():
            raw=path.read_bytes();report=json.loads(raw)
            if report['test_rewards_read'] is not False:raise ValueError('test rewards cannot enter selection')
            reports.append({'sha256':hashlib.sha256(raw).hexdigest(),'path':str(path.resolve()),'payload':report})
        choices.append({'class_balance':balanced,'study_sha256':study['study_sha256'],'selection':selected,'reports':reports})
    winner=rank_eligible_heads(choices)
    output={'observed_at':now.isoformat(),'plan_sha256':hashlib.sha256(plan_raw).hexdigest(),'fold_index':args.fold,
        'heads':choices,'winner':winner,'no_candidate_cash_only':winner is None,'completed_heads':2,'completed_validation_trials':6,
        'test_rewards_read':False,'fold_selection_freeze_performed':False,'independent_evaluation_completed':False,
        'ranking':'stress_return_then_net_return_then_higher_threshold_then_unweighted',
        'implementation_hashes':hashes,'runtime_source_bundle':save_runtime_sources(args.output.parent/'selection-runtime',deps,hashes),
        'live_promotion_allowed':False}
    assert_source_dependencies(hashes,deps);write_json_report(args.output,output)
    print(json.dumps({'winner':winner,'completed_heads':2,'completed_validation_trials':6,'no_candidate_cash_only':winner is None}))


if __name__=='__main__':main()
