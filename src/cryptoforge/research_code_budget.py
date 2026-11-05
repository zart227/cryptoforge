"""Explicit shared-budget extension for exact previews, never candidate execution."""
import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sqlite3

from cryptoforge import research_code_preview as preview
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp


CODE_TABLE = 'coordinated_code_extension'
POLICY = {'schema_version': 'coordinated-code-check-budget-v3', 'maximum_actions': 3,
    'input_tokens': 0, 'output_tokens': 0, 'wall_ms': 5000, 'free_only': True,
    'stage': 'exact_preview_only', 'candidate_execution_enabled': False}
SOURCE_NAMES = ('research_code_budget.py', 'research_run_budget.py', 'research_resource_budget.py',
    'research_semantic_budget.py', 'research_code_preview.py', 'semantic_source_collector.py',
    'training_diagnostics.py', 'llm_research_contracts.py', 'llm_research_coordinator.py')
HISTORY_TABLES = ('coordinated_policy', 'coordinated_actions', 'coordinated_resource_policy',
    'coordinated_resources', 'coordinated_semantic_extension')


def implementation():
    return {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() for name in SOURCE_NAMES}


def validate_policy(policy):
    if canonical(policy) != canonical(POLICY):
        raise ValueError('fixed preview-only code budget policy required')
    return deepcopy(POLICY)


def configuration(policy, manifest, resources, semantic):
    if semantic is None:
        raise ValueError('code budget requires existing v2 semantic configuration')
    return {'schema_version': 'coordinated-code-configuration-v3', 'policy': validate_policy(policy),
        'base_manifest_sha256': digest(manifest), 'resource_policy_sha256': digest(resources),
        'semantic_configuration_sha256': digest(semantic), 'preview_policy_sha256': digest(preview.POLICY),
        'implementation': implementation()}


def history_digest(db, table):
    if table not in HISTORY_TABLES:
        raise ValueError('fixed code migration history table required')
    order = 'key' if table in ('coordinated_actions', 'coordinated_resources') else 'id'
    checksum = hashlib.sha256()
    for row in db.execute(f'SELECT * FROM {table} ORDER BY {order}'):
        raw = canonical(list(row)).encode()
        checksum.update(len(raw).to_bytes(8, 'big')); checksum.update(raw)
    return checksum.hexdigest()


def check_extension(db, config, *, present):
    if config is None:
        if present:
            raise ValueError('explicit code policy required for migrated journal')
        return None
    if not present:
        raise ValueError('explicit code budget migration required')
    if config['implementation'] != implementation():
        raise ValueError('code implementation changed; restart required')
    row = db.execute('SELECT payload,sha FROM coordinated_code_extension WHERE id=1').fetchone()
    if row is None or db.execute('SELECT count(*) FROM coordinated_code_extension').fetchone()[0] != 1:
        raise ValueError('code extension record missing')
    payload = strict_json(row[0], max_bytes=64000)
    exact_fields(payload, {'schema_version', 'configuration', 'migration'})
    if (digest(payload) != row[1] or payload['schema_version'] != 'coordinated-code-extension-v3'
            or canonical(payload['configuration']) != canonical(config)):
        raise ValueError('persisted code configuration or implementation changed')
    audit = payload['migration']
    exact_fields(audit, {'migrated_at', 'prior_action_count', 'prior_tables_sha256'})
    timestamp(audit['migrated_at'])
    exact_fields(audit['prior_tables_sha256'], set(HISTORY_TABLES))
    if type(audit['prior_action_count']) is not int or audit['prior_action_count'] < 0:
        raise ValueError('invalid code migration count')
    for value in audit['prior_tables_sha256'].values():
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('invalid code migration table digest')
    return payload


def validate_history(db, validate_usage):
    """Refuse unresolved/corrupt v2 history; never repair rows or refund attempts."""
    for kind, questions, status, raw, sha, observed, observed_sha in db.execute(
            'SELECT kind,questions,status,payload,payload_sha,observed,observed_sha FROM coordinated_actions'):
        if (kind not in ('proposal', 'semantic_fixture', 'semantic_live', 'fit') or type(questions) is not int
                or (not 1 <= questions <= 16 if kind in ('semantic_fixture', 'semantic_live') else questions != 0)):
            raise ValueError('invalid prior code migration history')
        if status in ('failed', 'cancelled', 'timed_out'):
            if any(value is not None for value in (raw, sha, observed, observed_sha)):
                raise ValueError('unexpected failed history result')
        elif status == 'completed':
            envelope = strict_json(raw, max_bytes=2_000_000)
            exact_fields(envelope, {'result', 'observed', 'tokens'} if isinstance(envelope, dict) and 'tokens' in envelope else {'result', 'observed'})
            validate_usage(envelope['observed'], kind)
            if (digest(envelope) != sha or canonical(envelope['observed']) != observed
                    or digest(envelope['observed']) != observed_sha):
                raise ValueError('prior result checksum mismatch')
        else:
            raise ValueError('unfinished or invalid common history; code migration requires inactive journal')


def migrate(budget):
    if budget.code_configuration is None:
        raise ValueError('explicit code policy required')
    if not budget.path.is_file():
        raise ValueError('existing v2 common journal required')
    from cryptoforge import research_run_budget as common
    from cryptoforge.research_resource_budget import resource_snapshot
    if common._source_sha() != common._LOADED_SHA:
        raise ValueError('common budget source changed; restart required')
    expected = configuration(budget.code_policy, budget.manifest, budget.resource_policy, budget.semantic_configuration)
    if canonical(expected) != canonical(budget.code_configuration):
        raise ValueError('code implementation changed; restart required')
    db = sqlite3.connect(budget.path.as_uri() + '?mode=rw', uri=True, timeout=5)
    try:
        db.execute('BEGIN IMMEDIATE')
        tables = budget._check_objects(db)
        budget._check_manifest(db)
        common.check_extension(db, budget.semantic_configuration, present=common.EXTENSION_TABLE in tables)
        if common.EXTENSION_TABLE not in tables:
            raise ValueError('existing v2 migration required before code budget')
        if CODE_TABLE in tables:
            result = check_extension(db, budget.code_configuration, present=True)
            resource_snapshot(db, budget.resource_policy, budget.semantic_policy, budget.code_policy)
            already = True
        else:
            validate_history(db, common.validate_usage)
            resource_snapshot(db, budget.resource_policy, budget.semantic_policy)
            checksums = {name: history_digest(db, name) for name in HISTORY_TABLES}
            result = {'schema_version': 'coordinated-code-extension-v3',
                'configuration': budget.code_configuration, 'migration': {
                    'migrated_at': budget._now().isoformat(),
                    'prior_action_count': db.execute('SELECT count(*) FROM coordinated_actions').fetchone()[0],
                    'prior_tables_sha256': checksums}}
            db.execute('CREATE TABLE coordinated_code_extension (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, sha TEXT NOT NULL)')
            db.execute('INSERT INTO coordinated_code_extension VALUES (1,?,?)', (canonical(result), digest(result)))
            result = check_extension(db, budget.code_configuration, present=True)
            if any(history_digest(db, name) != checksum for name, checksum in checksums.items()):
                raise ValueError('code migration changed existing history')
            already = False
        if common._source_sha() != common._LOADED_SHA or implementation() != expected['implementation']:
            raise ValueError('code budget implementation changed during migration')
        db.commit()
        return {'schema_version': 'coordinated-code-migration-result-v3', 'already_migrated': already,
            'extension': result, 'extension_sha256': digest(result), 'action_reserved': False,
            'candidate_execution_enabled': False, 'candidate_executions': 0, 'api_calls': 0}
    except BaseException:
        db.rollback(); raise
    finally:
        db.close()


def check_preview(budget, directory, *, cancel_event=None):
    """One effect identity across copies/wording; revalidate bytes even on cache hit."""
    from cryptoforge.research_run_budget import BudgetCancelled, ZERO_USAGE
    if cancel_event is not None and cancel_event.is_set():
        raise BudgetCancelled('code check cancelled before admission')
    if budget.code_configuration is None:
        raise ValueError('explicit migrated code budget required')
    before = preview.read_preview(directory)
    identity = {'candidate_identity_sha256': before['candidate_identity_sha256']}
    def operation():
        if cancel_event is not None and cancel_event.is_set():
            raise BudgetCancelled('code check cancelled after reservation')
        checked = preview.read_preview(directory)
        if checked['preview_sha256'] != before['preview_sha256']:
            raise ValueError('preview changed after admission')
        return {'result': {'schema_version': 'budgeted-code-preview-check-v3',
            'candidate_identity_sha256': checked['candidate_identity_sha256'],
            'preview_sha256': checked['preview_sha256'], 'exact_preview_verified': True,
            'attempt_budget_reserved': True, 'reservation_scope': 'shared_preview_check_only',
            'candidate_execution_budget_reserved': False,
            'candidate_execution_enabled': False, 'candidate_executed': False, 'syntax_checked': False,
            'training_executed': False, 'evidence_ids_verified': False, 'model_provenance_verified': False,
            'can_authorize_trades': False}, 'observed': dict(ZERO_USAGE)}
    call = budget.run('code_check', identity, operation, cancel_event=cancel_event)
    after = preview.read_preview(directory)
    if after['preview_sha256'] != before['preview_sha256']:
        raise ValueError('preview changed during code check or cache read')
    return {**call, 'current_preview_sha256': after['preview_sha256'],
        'current_preview_revalidated': True, 'admission_is_execution_permission': False}


def main(argv=None):
    from cryptoforge.research_run_budget import ResearchRunBudget, BudgetCancelled, BudgetTimedOut
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'proposal-ledger', 'semantic-ledger', 'fit-ledger', 'semantic-live-ledger',
                 'semantic-live-policy', 'code-policy', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--resource-policy', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('migrate-code-budget'); sub.add_parser('status')
    check = sub.add_parser('code-check'); check.add_argument('--preview', type=Path, required=True)
    args = parser.parse_args(argv)
    protected = [args.database, args.proposal_ledger, args.semantic_ledger, args.fit_ledger,
        args.semantic_live_ledger, args.semantic_live_policy, args.code_policy, args.policy, args.resource_policy]
    if args.output.resolve() in {p.resolve() for p in protected if p is not None}:
        parser.error('output must be separate from journals and policy inputs')
    if args.command == 'code-check' and args.output.resolve().is_relative_to(args.preview.resolve()):
        parser.error('output must be outside preview bundle')
    def read(path):
        return preview.files._json(path.parent, path.name, 64000) if path is not None else None
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        receipt = {'schema_version': 'coordinated-code-receipt-v3', 'status': 'started', 'command': args.command}
        stream.write(canonical(receipt) + '\n'); stream.flush(); os.fsync(stream.fileno())
        try:
            budget = ResearchRunBudget(args.database, {'proposal': args.proposal_ledger,
                'semantic_fixture': args.semantic_ledger, 'fit': args.fit_ledger},
                semantic_live_ledger=args.semantic_live_ledger, semantic_live_policy=read(args.semantic_live_policy),
                code_check_policy=read(args.code_policy), policy=read(args.policy), resource_policy=read(args.resource_policy))
            result = migrate(budget) if args.command == 'migrate-code-budget' else (
                check_preview(budget, args.preview) if args.command == 'code-check' else None)
            receipt.update(status='completed', result=result, budget=budget.snapshot()); code = 0
        except (BudgetCancelled, KeyboardInterrupt):
            receipt.update(status='cancelled', safe_error='code_check_cancelled'); code = 130
        except BudgetTimedOut:
            receipt.update(status='timed_out', safe_error='code_check_timed_out'); code = 1
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, sqlite3.Error):
            receipt.update(status='failed', safe_error='code_inputs_or_budget_rejected'); code = 1
        stream.seek(0); stream.truncate(); stream.write(canonical(receipt) + '\n'); stream.flush(); os.fsync(stream.fileno())
    print('Code budget receipt saved; candidate execution remains disabled')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
