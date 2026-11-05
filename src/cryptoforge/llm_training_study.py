"""Frozen, equal-attempt development replay; never an independent efficacy claim.

LLM suggestions must be collected before freezing. No adaptive API calls, final
 test, economic performance estimates or promotion happen in this module.
"""
import argparse
import hashlib
import os
from pathlib import Path
import random

from cryptoforge.llm_research_contracts import CATALOG, validate_proposal_shape
from cryptoforge.training_diagnostics import canonical, digest, exact_fields
from cryptoforge.training_experiment_planner import (
    BASELINE, freeze_protocol, load_development, read_json, run_experiment,
)


def study_sources():
    root = Path(__file__).parent
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
            ('llm_training_study.py', 'llm_research_advisor.py', 'llm_research_requests.py', 'llm_advice_provenance.py')}


def config_for(proposal):
    if proposal.get('parameter') not in BASELINE:
        raise ValueError('study supports only l2 and threshold')
    config = dict(BASELINE)
    config[proposal['parameter']] = float(proposal['value'])
    return config


def freeze_study(dataset, proposals, *, version, seed=0, epochs=50, verified_origins=None):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('32-bit integer search seed required')
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 6:
        raise ValueError('one to six unique LLM suggestions required')
    data, _ = load_development(dataset)
    # Provenance of externally supplied suggestions is not certified by replay.
    # Exact baseline evidence is checked by run_experiment at execution time.
    configs = []
    for proposal in proposals:
        known_ids = {'overall'} | {'pair:'+row['pair'] for row in data['validation']}
        validate_proposal_shape(proposal, evidence_ids=known_ids)
        config = config_for(proposal)
        if config == BASELINE or config in configs:
            raise ValueError('duplicate or unchanged suggestion wastes comparison budget')
        configs.append(config)
    choices = [(parameter, value) for parameter in sorted(BASELINE)
               for value in CATALOG[parameter] if value != BASELINE[parameter]]
    random.Random(seed).shuffle(choices)
    controls = []
    for i, (parameter, value) in enumerate(choices[:len(proposals)]):
        controls.append({'schema_version': 'llm-training-proposal-v1',
            'hypothesis_id': f'control-{i}', 'evidence_ids': ['overall'],
            'rationale': 'Precommitted seeded random search.', 'expected_effect': 'Measure development loss.',
            'falsification': 'Do not infer independent efficacy from this replay.',
            'parameter': parameter, 'value': value})
    if verified_origins is not None:
        if len(verified_origins) != len(proposals):
            raise ValueError('one verified origin per suggestion required')
        for origin, proposal in zip(verified_origins, proposals):
            if origin['proposal'] != proposal or origin['dataset_sha256'] != digest(data):
                raise ValueError('verified origin differs from suggestion or dataset')
    return {'schema_version': 'llm-training-replay-v2', 'seed': seed,
            'protocol': freeze_protocol(dataset, version=version, maximum=len(proposals)+1, epochs=epochs),
            'study_sources': study_sources(), 'control': controls, 'llm': proposals,
            'metric': 'validation_brier_score', 'independent_evidence': False,
            'suggestion_origin': 'verified_local_api_journal' if verified_origins is not None else 'external_unverified',
            'verified_origins': verified_origins}


def run_study(dataset, study, directory, *, advice_paths=None, request_journal=None):
    exact_fields(study, {'schema_version', 'seed', 'protocol', 'study_sources', 'control', 'llm', 'metric', 'independent_evidence', 'suggestion_origin', 'verified_origins'})
    if study['schema_version'] != 'llm-training-replay-v2' or study['independent_evidence'] is not False:
        raise ValueError('development replay required')
    origins = None
    if study['verified_origins'] is not None:
        if not advice_paths or request_journal is None:
            raise ValueError('verified replay requires original receipts and API journal')
        from cryptoforge.llm_advice_provenance import verify_advice
        origins = [verify_advice(path, request_journal, dataset_sha256=study['protocol']['dataset_sha256']) for path in advice_paths]
    expected = freeze_study(dataset, study['llm'], version=study['protocol']['version'],
                            seed=study['seed'], epochs=study['protocol']['epochs'], verified_origins=origins)
    if canonical(study) != canonical(expected):
        raise ValueError('frozen comparison, source or dataset changed')
    directory = Path(directory)
    # New directory excludes cherry-picking cached history from a previous search.
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    frozen = directory/'study.json'
    with frozen.open('x') as stream:
        os.chmod(frozen, 0o600)
        stream.write(canonical(study)+'\n')
    arms = {}
    for name in ('control', 'llm'):
        ledger = directory/(name+'.sqlite')
        baseline = run_experiment(dataset, study['protocol'], ledger)
        evidence = baseline['reports']['validation']['diagnostics']
        if origins is not None:
            if any(origin['report_sha256'] != digest(evidence) for origin in origins):
                raise ValueError('LLM did not see this exact baseline diagnostics')
        results = [baseline]
        for proposal in study[name]:
            results.append(run_experiment(dataset, study['protocol'], ledger, proposal=proposal, report=evidence))
        if any(result['cached'] for result in results):
            raise ValueError('comparison requires fresh equal-count attempts')
        arms[name] = {'attempts': len(results), 'fit_seconds': sum(r['elapsed_seconds'] for r in results),
            'results': [{'study_id': r['study_id'], 'config': r['artifact']['config'],
                         'artifact_sha256': r['artifact_sha256'],
                         'validation_brier_score': r['reports']['validation']['diagnostics']['evidence']['overall']['brier_score']}
                        for r in results]}
    result = {'schema_version': 'llm-training-replay-result-v2', 'study_sha256': digest(study),
              'arms': arms, 'independent_evidence': False, 'profitability_evaluated': False,
              'api_calls_during_replay': 0, 'suggestion_origin': study['suggestion_origin'],
              'preparation': {'receipt_wall_seconds': sum(o['preparation_wall_seconds'] for o in origins) if origins else None,
                              'token_usage': [o['usage'] for o in origins] if origins else [],
                              'full_search_cost_accounted': False},
              'conclusion': 'development_replay_only_no_efficacy_conclusion'}
    output = directory/'result.json'
    with output.open('x') as stream:
        os.chmod(output, 0o600)
        stream.write(canonical(result)+'\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze')
    selection = freeze.add_mutually_exclusive_group(required=True)
    selection.add_argument('--proposals', type=Path)
    selection.add_argument('--advice-receipts', type=Path, nargs='+')
    freeze.add_argument('--request-journal', type=Path)
    freeze.add_argument('--output', type=Path, required=True)
    freeze.add_argument('--version', required=True)
    freeze.add_argument('--seed', type=int, default=0)
    freeze.add_argument('--epochs', type=int, default=50)
    run = sub.add_parser('run')
    run.add_argument('--study', type=Path, required=True)
    run.add_argument('--directory', type=Path, required=True)
    run.add_argument('--advice-receipts', type=Path, nargs='+')
    run.add_argument('--request-journal', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'freeze':
        origins = None
        if args.advice_receipts:
            if not args.request_journal:
                parser.error('--advice-receipts requires --request-journal')
            from cryptoforge.llm_advice_provenance import verify_advice
            data, _ = load_development(args.dataset)
            origins = [verify_advice(p, args.request_journal, dataset_sha256=digest(data)) for p in args.advice_receipts]
            proposals = [o['proposal'] for o in origins]
        else:
            proposals = read_json(args.proposals)
        study = freeze_study(args.dataset, proposals, version=args.version,
                             seed=args.seed, epochs=args.epochs, verified_origins=origins)
        fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical(study)+'\n')
    else:
        run_study(args.dataset, read_json(args.study), args.directory,
                  advice_paths=args.advice_receipts, request_journal=args.request_journal)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
