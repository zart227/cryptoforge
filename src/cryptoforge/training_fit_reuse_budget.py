"""Experimental existing-journal adapter for bounded fit reuse.

This integrates the existing phase and ResearchAttempts accounting without
creating or migrating either database. It does not approve data, manifests,
experiments, changes to limits, or trading. No generated code is executed.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import stat

from cryptoforge import research_phase as phase, training_fit_reuse_worker as worker
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_attempts import ResearchAttempts, budget_key, identity
from cryptoforge.training_diagnostics import canonical, digest


planner = worker.reuse.planner
TABLES = {'studies', 'configurations', 'attempts', 'budgets', 'protocol_versions'}


def implementation():
    return {'adapter': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': worker.implementation(), 'phase': phase.implementation()}


_LOADED = implementation()


def _guard():
    worker._guard(); phase._guard()
    if implementation() != _LOADED: raise ValueError('fit_budget_adapter_source_changed')


def _private_file(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink() or not path.is_file():
        raise ValueError('existing_original_fit_journal_required')
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
        raise ValueError('owner_private_fit_journal_required')
    return path, st


class ExistingAttempts(ResearchAttempts):
    """Keep ResearchAttempts registration/limits while forbidding schema creation."""
    def _db(self):
        path, before = _private_file(self.path)
        db = sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, timeout=5)
        try:
            _, after = _private_file(path)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError('fit_journal_replaced_during_open')
            objects = set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))
            if objects != {('table', name) for name in TABLES}:
                raise ValueError('complete_existing_fit_journal_required')
            return db
        except BaseException:
            db.close(); raise


def _manifest(data, protocol, config):
    candidate = {'family': 'llm-offline-long-head-v1', **config}
    return candidate, {'schema_version': 'llm-offline-study-v1', 'grid': [candidate],
        'base_config': {'dataset_sha256': digest(data), 'protocol_sha256': digest(protocol)},
        'implementation_hashes': protocol['implementation_hashes']}


def _existing_protocol(ledger, protocol):
    db = ledger._db()
    try:
        maximum = db.execute('SELECT maximum FROM budgets WHERE protocol=?', (digest(protocol),)).fetchone()
        version = db.execute('SELECT id FROM protocol_versions WHERE version=?', (protocol['version'],)).fetchone()
        if maximum != (protocol['maximum_per_family'],) or version != (digest(protocol),):
            raise ValueError('existing_frozen_fit_protocol_and_budget_required')
    finally: db.close()


def _attempt(ledger, study, candidate):
    db = ledger._db()
    try:
        return db.execute('SELECT status,payload FROM attempts WHERE study=? AND configuration=?',
            (study, identity(candidate))).fetchone()
    finally: db.close()


def _other_studies(ledger, protocol):
    """Detect a repeated effective configuration in a different native study."""
    db = ledger._db()
    try:
        rows = db.execute('SELECT id,payload FROM studies WHERE protocol=? LIMIT 501', (digest(protocol),)).fetchall()
    finally: db.close()
    if len(rows) > 500: raise ValueError('bounded_existing_study_history_required')
    effects = {}
    for study, raw in rows:
        manifest = strict_json(raw, max_bytes=2_000_000)
        if type(manifest) is not dict or type(manifest.get('grid')) is not list or len(manifest['grid']) > 50:
            raise ValueError('bounded_native_study_manifest_required')
        if identity(manifest) != study: raise ValueError('existing_native_study_identity_mismatch')
        for candidate in manifest['grid']:
            effects.setdefault(budget_key(candidate, manifest), set()).add(study)
    return effects


def _claims(path, studies):
    result = []
    for study in studies:
        claim = path.parent/(path.name+'.'+study+'.claim')
        fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical({'study_id': study, 'status': 'claimed'})+'\n')
            stream.flush(); os.fsync(stream.fileno())
        result.append(claim)
    return result


def _mark_failed(ledger, entries):
    # Never rewrite a completed row; a partial completion remains visible.
    for entry in entries:
        row = _attempt(ledger, entry['study'], entry['candidate'])
        if row is not None and row[0] == 'reserved':
            ledger.record(entry['study'], entry['candidate'],
                {'status': 'failed', 'error': 'offline experiment failed'}, failed=True)


def run_existing(research, dataset, protocol, configurations, *, evidence_context, cancel_event=None):
    """Read completed results only until original manifests are verified.

    Fresh execution is intentionally unavailable through this public entry
    point. The private implementation can be exercised with synthetic journals;
    using private Python functions is not a security boundary.
    """
    return _run_existing(research, dataset, protocol, configurations, evidence_context=evidence_context,
        cancel_event=cancel_event, _allow_unqualified_fresh=False)


def _run_existing(research, dataset, protocol, configurations, *, evidence_context, cancel_event=None,
                  _allow_unqualified_fresh=False):
    """Experimental ordinary one-parameter evaluations under both budgets.

    The caller is responsible for study and source approval. Declared context
    hashes are not original-manifest verification or a new budget allocation.
    Completed legacy results are returned from their native cache; only fresh
    configurations in this invocation share numerical work. Failed/incomplete
    past attempts are never repeated. This is an opt-in research API, not a
    production trainer, LLM proposal dispatcher, or trade authorization.
    """
    _guard()
    if type(_allow_unqualified_fresh) is not bool: raise ValueError('explicit_private_fixture_flag_required')
    if type(research) is not phase.PhaseResearchCoordinator:
        raise ValueError('existing_phase_coordinator_required')
    worker._cancel(cancel_event)
    protocol, configurations, evidence_context = deepcopy((protocol, configurations, evidence_context))
    data, _ = planner.load_development(dataset)
    full_plan = worker.reuse.plan(data, protocol, configurations, evidence_context=evidence_context)
    path, _ = _private_file(research.paths['fit'])
    _private_file(research.budget.path)
    ledger = ExistingAttempts(path)
    _existing_protocol(ledger, protocol)
    entries = []
    for evaluation in full_plan['evaluations']:
        config = evaluation['configuration']; candidate, manifest = _manifest(data, protocol, config)
        inputs = {'dataset_sha256': digest(data), 'protocol_sha256': digest(protocol), 'config': config}
        outer_identity = research._identity(inputs); key = research.budget._key('fit', outer_identity, 0)
        entries.append({'evaluation': evaluation, 'candidate': candidate, 'manifest': manifest,
            'study': identity(manifest), 'inputs': inputs, 'outer_identity': outer_identity, 'key': key})
    if len({e['key'] for e in entries}) != len(entries): raise ValueError('distinct_original_fit_effects_required')
    # The same native worker lock serializes ResearchAttempts writes. A failed
    # process keeps its claim files and cannot silently retry those effects.
    with planner.ledger_lock(path):
        _guard(); _existing_protocol(ledger, protocol); worker._cancel(cancel_event)
        effects = _other_studies(ledger, protocol)
        with research.budget._connection() as db:
            research.budget._check(db)
            cached = [research.budget._cached(db, e['key'], e['outer_identity'], 'fit') for e in entries]
        fresh = []
        for entry, prior in zip(entries, cached, strict=True):
            key = budget_key(entry['candidate'], entry['manifest'])
            if effects.get(key, set()) - {entry['study']}:
                raise ValueError('effective_fit_in_other_study_requires_reconciliation')
            row = _attempt(ledger, entry['study'], entry['candidate'])
            if prior is None:
                if row is not None: raise ValueError('existing_inner_attempt_requires_individual_reconciliation')
                fresh.append(entry)
            else:
                if row is None or row[0] != 'completed': raise ValueError('common_cache_requires_completed_original_fit')
                original = strict_json(row[1], max_bytes=2_000_000)
                saved = prior[0]['result']
                if (digest(original['artifact']) != original['artifact_sha256']
                        or original['artifact_sha256'] != saved['artifact_sha256']
                        or canonical(original['reports']) != canonical(saved['reports'])):
                    raise ValueError('original_inner_and_common_cache_mismatch')
                if ('fit_reuse' in saved and saved['fit_reuse']['binding']['context_sha256'] != full_plan['context_sha256']):
                    raise ValueError('cached_fit_reuse_context_changed')
                entry['cached_result'] = saved
        if fresh and not _allow_unqualified_fresh:
            raise ValueError('fresh_fit_disabled_until_original_manifests_and_protocol_qualified')
        # Pre-existing claims represent interrupted work, even with no row.
        for entry in fresh:
            claim = path.parent/(path.name+'.'+entry['study']+'.claim')
            if claim.exists() or claim.is_symlink(): raise ValueError('prior_claim_requires_investigation')
        actual = {}; calls = {}; batch_receipt = None

        def execute_batch():
            nonlocal batch_receipt
            claims = _claims(path, [e['study'] for e in fresh])
            registered = []
            try:
                snapshot = planner.save_development_snapshot(path, data)
                for entry in fresh:
                    if _attempt(ledger, entry['study'], entry['candidate']) is not None:
                        raise ValueError('fit_attempt_changed_during_admission')
                    study = ledger.register(entry['manifest'], protocol_id=digest(protocol),
                        maximum_per_family=protocol['maximum_per_family'], protocol_version=protocol['version'])
                    if study != entry['study']: raise ValueError('original_study_identity_mismatch')
                    registered.append(entry)
                # Each callback verifies both original reservations and claims.
                def admitted(evaluation, context):
                    entry = fresh[evaluation['index']]
                    if context != full_plan['context_sha256'] or evaluation['configuration'] != entry['evaluation']['configuration']:
                        raise ValueError('logical_fit_identity_mismatch')
                    if not claims[evaluation['index']].is_file(): raise ValueError('original_fit_claim_missing')
                    row = _attempt(ledger, entry['study'], entry['candidate'])
                    if row is None or row[0] != 'reserved': raise ValueError('original_inner_reservation_missing')
                    with research.budget._connection() as db:
                        research.budget._check(db)
                        outer = db.execute('SELECT status,input_sha FROM coordinated_phase_actions WHERE key=?',
                            (entry['key'],)).fetchone()
                        if outer != ('reserved', digest(entry['outer_identity'])):
                            raise ValueError('original_common_reservation_missing')
                wall = min(worker.POLICY['wall_seconds'], research.budget.resource_policy['wall_ms_by_kind']['fit']/1000-1)
                if wall < .001: raise ValueError('fit_allocation_must_cover_cleanup')
                batch_receipt = worker.run(data, protocol, [e['evaluation']['configuration'] for e in fresh],
                    evidence_context=evidence_context, admit=admitted, wall_seconds=wall, cancel_event=cancel_event)
                batch = batch_receipt['worker']['result']; seen_l2 = set()
                for entry, item, binding in zip(fresh, batch['results'], batch['result_bindings'], strict=True):
                    l2 = entry['evaluation']['configuration']['l2']; physical_fit = l2 not in seen_l2; seen_l2.add(l2)
                    result = {**item, 'protocol_sha256': digest(protocol), 'dataset_sha256': digest(data),
                        'development_snapshot': snapshot, 'completed_at': datetime.now(timezone.utc).isoformat(),
                        'elapsed_seconds': batch_receipt['parent_worker_wall_seconds'],
                        'budget_usage': ledger.budget_usage(digest(protocol)), 'training_executed': physical_fit,
                        'environment': {'schema_version':'fit-reuse-worker-environment-v1',
                            'worker_implementation':worker.implementation(), 'worker_usage':batch_receipt['worker']['usage']},
                        'fit_reuse': {'adapter_implementation':_LOADED, 'batch_sha256':batch['batch_sha256'],
                            'binding':binding, 'shared_batch_wall_seconds':batch_receipt['parent_worker_wall_seconds'],
                            'declared_evidence_not_independently_verified':True}}
                    ledger.record(entry['study'], entry['candidate'], result)
                    actual[entry['key']] = {**result, 'cached':False, 'study_id':entry['study']}
                _guard()
            except Exception:
                _mark_failed(ledger, registered)
                raise

        def reserve(index):
            entry = fresh[index]; invoked = False
            def operation():
                nonlocal invoked
                invoked = True
                if index+1 < len(fresh): reserve(index+1)
                else: execute_batch()
                result = actual[entry['key']]
                return {'result':result, 'observed':{**phase.common.ZERO_USAGE,
                    'numeric_fits':int(result['training_executed'])}}
            call = research._dispatch('fit', entry['inputs'], operation, cancel_event=cancel_event)
            if not invoked: raise ValueError('fit_effect_changed_to_cache_during_admission')
            calls[entry['key']] = call
        if fresh: reserve(0)
        for entry in entries:
            if 'cached_result' in entry:
                def forbidden(): raise AssertionError('existing completed fit must remain cached')
                call = research._dispatch('fit', entry['inputs'], forbidden, cancel_event=cancel_event)
                if not call['coordinator_cached']: raise ValueError('fit_cache_changed_during_read')
                calls[entry['key']] = call
        return {'schema_version':'existing-fit-reuse-budget-result-v1', 'plan':full_plan,
            'calls':[calls[e['key']] for e in entries], 'fresh_logical_evaluations':len(fresh),
            'cached_logical_evaluations':len(entries)-len(fresh), 'batch_worker':batch_receipt,
            'legacy_cache_without_fit_reuse_context':sum('cached_result' in e and 'fit_reuse' not in e['cached_result'] for e in entries),
            'native_common_and_inner_accounting_used':True,
            'new_limits_or_refunds':False, 'original_manifests_verified':False,
            'study_approved':False, 'production_compatible':False}
