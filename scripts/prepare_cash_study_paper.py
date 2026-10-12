"""Prepare isolated disabled paper drafts; never activate a worker or alter legacy policies."""
import argparse,json
from pathlib import Path
from cryptoforge.cash_study_paths import load_cash_study,LEGACY_PROTOCOL_SHA256
from cryptoforge.cash_study_registry import require_collection_freeze
from cryptoforge.immutable_files import install_original


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,required=True)
    args=parser.parse_args();protocol,study=load_cash_study(args.protocol);require_collection_freeze(study)
    if study.protocol_sha256==LEGACY_PROTOCOL_SHA256:
        print(json.dumps({'status':'legacy_policies_preserved','paper_activated':False}));return
    drafts=(('config/paper-execution-policy-v1.json',study.execution_policy,'draft_execution_disabled'),
            ('config/paper-acceptance-policy-v1.json',study.acceptance_policy,'draft_not_preregistered'))
    for template,path,status in drafts:
        if path.exists():
            if json.loads(path.read_bytes())['protocol_version']!=protocol['protocol_version']:
                raise ValueError('existing paper namespace belongs to another protocol')
            continue
        policy=json.loads(Path(template).read_bytes());policy.update(protocol_version=protocol['protocol_version'],status=status)
        if path==study.execution_policy:policy['enabled']=False
        install_original(path,(json.dumps(policy,indent=2)+'\n').encode())
    print(json.dumps({'status':'separate_disabled_paper_drafts_prepared','protocol_sha256':study.protocol_sha256,
        'execution_policy':str(study.execution_policy.resolve()),'acceptance_policy':str(study.acceptance_policy.resolve()),
        'paper_activated':False,'live_promotion_allowed':False}))


if __name__=='__main__':main()
