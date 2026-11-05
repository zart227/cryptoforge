"""Read-only provenance and recomputation of research paper evidence.

This verifies a finished, quiescent local study, never grants live admission or
executes archived code. Existing collection/paper formats are research-only.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import importlib
import json
from math import isfinite
import os
from pathlib import Path
import sqlite3
import stat

from cryptoforge.cash_study_paths import load_cash_study, LEGACY_PROTOCOL_SHA256
from cryptoforge.cash_study_registry import CashStudyRegistry
from cryptoforge.execution_controls import unique_fields
from cryptoforge.live_learning_protocol import time
from cryptoforge.model_training import predict_probability
from cryptoforge.paper_acceptance import AcceptanceRegistry, evaluate_paper
from cryptoforge.paper_policy_design import validate_execution_design
from cryptoforge.paper_results import export_results
from cryptoforge.paper_runtime import verify_paper_runtime, paper_runtime_hashes
from cryptoforge.prospective_shadow import ShadowLedger, validate_candidate
from cryptoforge.runtime_approval import require_sha


ROLES = ('candidate', 'baseline_control', 'stress_candidate')
MAXIMUM_BYTES = 64 * 1024 * 1024
SOURCE_MODULES = ('strategy_evidence', 'cash_study_paths', 'cash_study_registry',
    'live_learning_protocol', 'prospective_shadow', 'paper_acceptance',
    'paper_results', 'paper_runtime', 'paper_policy_design', 'training_snapshot',
    'source_contract', 'execution_controls', 'model_training')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    value = json.loads(raw, object_pairs_hook=unique_fields,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON evidence')))
    canonical(value)
    if not isinstance(value, dict):
        raise ValueError('evidence object required')
    return value


def implementation_hashes():
    result = {name: digest(Path(importlib.import_module('cryptoforge.' + name).__file__).read_bytes())
        for name in SOURCE_MODULES}
    launcher = Path(__file__).resolve().parents[2] / 'scripts/audit_strategy_evidence.py'
    result['audit_launcher'] = digest(launcher.read_bytes())
    result.update({'paper:' + name: value for name, value in paper_runtime_hashes().items()})
    return result


class EvidenceFiles:
    """Bound original bytes and inode; detect replacement/mutation during audit."""
    def __init__(self):
        self.files = {}
        self.locations = {}

    def read(self, path, *, sqlite=False):
        location = Path(path).absolute()
        if location.is_symlink() or not stat.S_ISREG(location.stat().st_mode):
            raise ValueError('regular non-symlink evidence file required')
        path = location.resolve()
        if location in self.locations and self.locations[location] != path:
            raise ValueError('evidence path retargeted during audit')
        self.locations[location] = path
        if sqlite:
            self.clean_database(path)
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('regular evidence file required')
            if not 0 < before.st_size <= MAXIMUM_BYTES:
                raise ValueError('bounded nonempty evidence file required')
            raw = stream.read(MAXIMUM_BYTES + 1)
            after = os.fstat(stream.fileno())
        final = path.stat()
        signature = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if (len(raw) != before.st_size or signature(before) != signature(after)
                or signature(before) != signature(final)):
            raise ValueError('evidence changed during read')
        record = dict(path=str(path), sha256=digest(raw), size_bytes=len(raw),
            device=before.st_dev, inode=before.st_ino, sqlite=sqlite)
        if str(path) in self.files and record != self.files[str(path)]:
            raise ValueError('evidence changed during audit')
        self.files[str(path)] = record
        if sqlite:
            self.strict_database(path)
        return raw

    @staticmethod
    def clean_database(path):
        if any(os.path.lexists(str(path) + suffix) for suffix in ('-wal', '-shm', '-journal')):
            raise ValueError('finished quiescent SQLite evidence without sidecars required')

    @staticmethod
    def strict_database(path):
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            if db.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                raise ValueError('DELETE-mode evidence database required')
            if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise ValueError('evidence database integrity check failed')
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                if not name.replace('_', '').isalnum():
                    raise ValueError('unsupported evidence table name')
                columns = {row[1] for row in db.execute('PRAGMA table_info("' + name + '")')}
                if 'payload' in columns:
                    for (payload,) in db.execute('SELECT payload FROM "' + name + '"'):
                        parse(payload)
                if name in {'state', 'worker_state'} and {'key', 'value'} <= columns:
                    for (payload,) in db.execute('SELECT value FROM "' + name + '" WHERE key IN (?,?)',
                            ('policy', 'identity')):
                        parse(payload)
            db.rollback()
        finally:
            db.close()

    def verify(self):
        for location, target in self.locations.items():
            if location.is_symlink() or location.resolve() != target:
                raise ValueError('evidence path retargeted during audit')
        for path, record in list(self.files.items()):
            self.read(path, sqlite=record['sqlite'])


def clock_value(clock):
    now = clock() if clock else datetime.now(UTC)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware current evidence clock required')
    return now.astimezone(UTC)


def verify_freezes(files, study, protocol, *, expected_artifact_sha256, now):
    manifest_raw = files.read(study.candidate)
    manifest = parse(manifest_raw)
    if (manifest['protocol_sha256'] != study.protocol_sha256
            or manifest['artifact_sha256'] != expected_artifact_sha256):
        raise ValueError('candidate differs from reviewed protocol/model pin')
    artifact_raw = files.read(manifest['artifact_path'])
    if digest(artifact_raw) != expected_artifact_sha256:
        raise ValueError('candidate artifact checksum mismatch')
    artifact = parse(artifact_raw)
    validate_candidate(manifest, artifact, protocol, now=now)
    files.read(study.predictions, sqlite=True)
    ledger = ShadowLedger(study.predictions)
    selected = ledger.verify_freeze(manifest_raw)
    first_test = time(protocol['windows']['sealed_test']['start']) + timedelta(seconds=protocol['embargo_seconds'])
    if (abs((selected-time(manifest['selected_at'])).total_seconds()) > 5
            or not selected < first_test or selected > now):
        raise ValueError('candidate original registration is late or unavailable')
    raw = files.read(study.execution_policy)
    policy = parse(raw)
    receipt = parse(files.read(study.execution_policy.with_suffix('.freeze.json')))
    ledger.verify_paper_policy(raw, receipt)
    first_paper = time(protocol['windows']['paper']['start']) + timedelta(seconds=protocol['embargo_seconds'])
    if (policy['status'] != 'frozen' or policy['enabled'] is not True
            or policy['protocol_version'] != protocol['protocol_version']
            or receipt['candidate_sha256'] != expected_artifact_sha256
            or receipt['protocol_sha256'] != study.protocol_sha256
            or not selected <= time(receipt['observed_at']) < first_paper
            or time(receipt['observed_at']) > now):
        raise ValueError('paper execution policy original identity/chronology mismatch')
    validate_execution_design(policy)
    verify_paper_runtime(policy)
    if policy.get('runtime_source_bundle') is not None:
        files.read(policy['runtime_source_bundle']['path'])
    acceptance_raw = files.read(study.acceptance_policy)
    acceptance = parse(acceptance_raw)
    acceptance_receipt = parse(files.read(study.acceptance_policy.with_suffix('.freeze.json')))
    files.read(study.acceptance_registry, sqlite=True)
    AcceptanceRegistry(study.acceptance_registry).verify(acceptance_raw, acceptance_receipt)
    if (acceptance['status'] != 'frozen' or acceptance['allow_real_promotion'] is not False
            or acceptance['protocol_version'] != protocol['protocol_version']
            or acceptance_receipt['protocol_sha256'] != study.protocol_sha256
            or not time(protocol['frozen_at']) <= time(acceptance_receipt['observed_at']) < first_paper
            or time(acceptance_receipt['observed_at']) > now):
        raise ValueError('paper acceptance original identity/chronology mismatch')
    return manifest, artifact, policy, acceptance, first_paper


def verify_opportunities(study, roles, manifest, artifact, protocol, *, start, end):
    """Match role source identities/payloads to the original shadow ledger."""
    predictions = ShadowLedger(study.predictions).rows()
    original = {}
    for row in predictions:
        if row['candidate_sha256'] != manifest['artifact_sha256']:
            continue
        predicted = time(row['predicted_at'])
        if not start <= predicted < end:
            continue
        if (not predicted <= time(row['observed_at']) <= predicted + timedelta(seconds=5)
                or time(row['feature_observed_at']) > predicted
                or row['input_candle_state'] != protocol['input_candle_state']
                or row.get('feature_input_contract') != protocol.get('feature_input_contract')
                or Decimal(str(row['threshold'])) != Decimal(str(manifest['threshold']))
                or type(row['would_enter']) is not bool or row['baseline_would_enter'] is not True):
            raise ValueError('original prospective opportunity contract mismatch')
        features = row['features']
        if len(features) != 7 or not all(isfinite(float(value)) for value in features):
            raise ValueError('original model features must be finite and complete')
        probability = predict_probability(tuple(float(value) for value in features),
            artifact['weights'], artifact['bias'], artifact['means'], artifact['stds'])
        if (not isfinite(float(row['probability'])) or abs(probability - row['probability']) > 1e-12
                or row['would_enter'] != (probability >= float(manifest['threshold']))):
            raise ValueError('original prediction differs from pinned model recomputation')
        key = digest((row['candidate_sha256'] + '|' + row['opportunity']).encode())
        if key in original:
            raise ValueError('duplicate original prospective opportunity')
        original[key] = row
    if not original:
        raise ValueError('original prospective paper opportunities required')
    for role, result in roles.items():
        seen = [row['id'] for row in result['seen_predictions']]
        if len(seen) != len(set(seen)) or set(seen) != set(original):
            raise ValueError('role omitted or invented original opportunities')
        intents = {row['id']: row for row in result['intents']}
        if len(intents) != len(result['intents']):
            raise ValueError('duplicate role intent identity')
        acquired_intents = {row['paper_buy_intent'] for row in result['campaigns']}
        buy_fills = {row['intent_id']: row for row in result['fills'] if row['side'] == 'Buy'}
        expected_buys = set()
        for seen_row in result['seen_predictions']:
            key = seen_row['id']
            source = original[key]
            expected_enter = source['baseline_would_enter'] if role == 'baseline_control' else source['would_enter']
            observed, predicted = time(seen_row['observed_at']), time(source['predicted_at'])
            deadline = predicted + timedelta(seconds=result['policy']['config']['signal_expiry_seconds'])
            if not predicted <= observed < end:
                raise ValueError('role source observation clock mismatch')
            status = seen_row['status']
            if not expected_enter:
                if status != 'candidate_rejected':
                    raise ValueError('role source decision differs from original model gate')
            elif status == 'queued':
                identity = 'paper-buy:' + key
                expected_buys.add(identity)
                intent = intents.get(identity)
                if (intent is None or intent['side'] != 'Buy' or intent['pair'] != source['pair']
                        or not predicted <= time(intent['created_at']) < deadline
                        or time(intent['created_at']) >= end-timedelta(seconds=protocol['embargo_seconds'])
                        or not observed <= time(intent['observed_at']) < end
                        or not time(intent['created_at']) <= observed <= time(intent['created_at'])+timedelta(seconds=5)
                        or intent['status'] not in {'filled', 'pending', 'rejected'}):
                    raise ValueError('queued original opportunity has no matching causal Buy intent')
                if ((intent['status'] == 'filled') != (identity in acquired_intents)
                        or (intent['status'] == 'rejected' and not intent.get('reason'))):
                    raise ValueError('original Buy intent and acquisition outcome disagree')
                if intent['status'] == 'filled':
                    fill = buy_fills.get(identity)
                    if (fill is None or time(fill['signal_time']) != time(intent['created_at'])
                            or time(fill['filled_at']) != time(intent['observed_at'])):
                        raise ValueError('filled Buy original intent clocks disagree')
            elif status == 'source_prediction_expired':
                if observed < deadline:
                    raise ValueError('source expiry contradicts original clock')
            elif status == 'paper_entry_window_finished':
                if observed < end-timedelta(seconds=protocol['embargo_seconds']):
                    raise ValueError('entry-window rejection precedes frozen cutoff')
            else:
                raise ValueError('role omitted accepted original model opportunity')
        if {row['id'] for row in result['intents'] if row['side'] == 'Buy'} != expected_buys:
            raise ValueError('role contains a Buy outside queued original opportunities')
        acquired = set()
        for campaign in result['campaigns']:
            source = campaign['source_prediction']
            if not isinstance(source, dict):
                raise ValueError('campaign original prediction required')
            key = digest((source['candidate_sha256'] + '|' + source['opportunity']).encode())
            if key not in original:
                raise ValueError('campaign source absent from original ledger')
            if key in acquired:
                raise ValueError('duplicate acquisition from one original opportunity')
            acquired.add(key)
            if campaign['paper_buy_intent'] != 'paper-buy:' + key:
                raise ValueError('acquisition identity differs from original opportunity')
            # Order bindings may have been attached after the worker observed it.
            ignored = {'order_id', 'bound_at', 'causal_order_link_id'}
            expected = {key: value for key, value in original[key].items() if key not in ignored}
            actual = {key: value for key, value in source.items() if key not in ignored}
            if role == 'baseline_control':
                expected = {**expected, 'original_candidate_would_enter': expected['would_enter'],
                    'would_enter': expected['baseline_would_enter']}
            predicted, entry = time(source['predicted_at']), time(campaign['entry_at'])
            if (expected['would_enter'] is not True or not predicted < entry < end
                    or entry >= predicted + timedelta(seconds=result['policy']['config']['signal_expiry_seconds'])):
                raise ValueError('campaign violates original entry decision or opportunity clock')
            if canonical(actual) != canonical(expected) or campaign['pair'] != source['pair']:
                raise ValueError('campaign borrowed or changed original prediction')


def verify_mark_cash(wallet_path, result, *, start, end):
    """Replay cash/remaining lots; retained marks do not contain original quotes.

    Marks before and after one fill can share a timestamp. Original cash selects
    the state, without assuming that the pre-fill mark was made after the fill.
    Multiple simultaneous fills lack an original ordering and require review.
    """
    tolerance = Decimal('1e-20')
    def number(value):
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed < 0:
            raise ValueError('finite nonnegative mark replay amount required')
        return parsed
    def same(left, right):
        return abs(number(left)-number(right)) <= tolerance
    def apply_fill(state, fill):
        cash, lots = deepcopy(state)
        quantity = number(fill['quantity'])
        if fill['side'] == 'Buy':
            cash -= number(fill['cost'])
            lots[fill['intent_id']] = [fill['pair'], quantity, number(fill['cost'])]
        else:
            cash += number(fill['proceeds'])
            left = quantity
            for lot in lots.values():
                if lot[0] != fill['pair'] or not left:
                    continue
                sold = min(left, lot[1])
                if sold:
                    lot[2] *= (lot[1]-sold)/lot[1]
                    lot[1] -= sold
                    left -= sold
            if left > tolerance:
                raise ValueError('mark replay sold unavailable inventory')
        number(cash)
        return cash, lots
    fills = sorted(result['fills'], key=lambda row: (time(row['filled_at']), row['intent_id']))
    if any(time(a['filled_at']) == time(b['filled_at']) for a, b in zip(fills, fills[1:])):
        raise ValueError('simultaneous paper fills require original ordering review')
    state = (number(result['capital']), {})
    position = 0
    checked = unreplayed = 0
    previous = start
    db = sqlite3.connect(Path(wallet_path).resolve().as_uri()+'?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        for stamp, raw in db.execute('SELECT observed_at,payload FROM marks ORDER BY id'):
            mark, observed = parse(raw), time(stamp)
            if (not previous <= observed <= end or time(mark['observed_at']) != observed
                    or mark.get('mode') != 'paper' or mark.get('live_eligible') is not False
                    or mark.get('valuation') != 'conditional_top_book_liquidation_after_fee_slip_dust_zero_assumption'):
                raise ValueError('original mark identity or chronology differs')
            previous = observed
            while position < len(fills) and time(fills[position]['filled_at']) < observed:
                state = apply_fill(state, fills[position]); position += 1
            choices = [(position, state)]
            if position < len(fills) and time(fills[position]['filled_at']) == observed:
                choices.append((position+1, apply_fill(state, fills[position])))
            matching = [(index, value) for index, value in choices if same(mark['cash'], value[0])]
            if len(matching) != 1:
                raise ValueError('original equity mark cash differs from fill replay')
            position, state = matching[0]
            cash, lots = state
            inventory = {}
            for pair, quantity, basis in lots.values():
                if quantity:
                    inventory[pair] = inventory.get(pair, Decimal(0))+basis
            groups = []
            for key in ('missing_mark_pairs', 'uncertain_liquidation_pairs', 'nontradable_small_basis_pairs'):
                values = mark[key]
                if (not isinstance(values, list) or any(type(pair) is not str for pair in values)
                        or len(values) != len(set(values)) or not set(values) <= set(inventory)):
                    raise ValueError('original mark inventory coverage differs')
                groups.append(set(values))
            missing, uncertain, dust = groups
            if any(a & b for i, a in enumerate(groups) for b in groups[i+1:]):
                raise ValueError('contradictory original mark inventory coverage')
            if bool(missing or uncertain) != (mark['equity'] is None) or bool(missing) != (mark['gross_bid_equity'] is None):
                raise ValueError('original mark unknown valuation was replaced or hidden')
            cap = number(result['policy']['config']['stake'])*number(result['policy']['config']['max_dust_basis_fraction'])
            if any(inventory[pair] > cap for pair in dust):
                raise ValueError('material inventory cannot become assumed zero-value dust')
            if mark['gross_bid_equity'] is not None and number(mark['gross_bid_equity']) < cash-tolerance:
                raise ValueError('original mark gross equity is below replayed cash')
            if mark['equity'] is not None:
                equity = number(mark['equity'])
                if equity < cash-tolerance or equity > number(mark['gross_bid_equity'])+tolerance:
                    raise ValueError('original liquidation equity contradicts cash or gross value')
                if set(inventory) == dust:
                    if not same(equity, cash) or (not inventory and not same(mark['gross_bid_equity'], cash)):
                        raise ValueError('flat or dust-zero equity differs from replayed cash')
                else:
                    unreplayed += 1
            else:
                unreplayed += 1
            checked += 1
    finally:
        db.close()
    for fill in fills[position:]:
        state = apply_fill(state, fill)
    if not same(state[0], result['cash']):
        raise ValueError('original final cash differs from fill replay')
    for campaign in result['campaigns']:
        lot = state[1].get(campaign['paper_buy_intent'])
        if lot is None or not same(lot[1], campaign['remaining_quantity']) or not same(lot[2], campaign['remaining_basis']):
            raise ValueError('original remaining lot differs from mark cash replay')
    return dict(marks_checked=checked, cash_replay_verified=True,
        unreplayed_liquidation_marks=unreplayed,
        historical_liquidation_values_verified=bool(checked) and not unreplayed,
        scope='fill_cash_and_flat_or_recorded_dust_zero_marks_not_historical_quote_certification')


def audit_strategy_evidence(protocol_path, *, expected_artifact_sha256,
                            state_root=Path('.local/state'), clock=None):
    """Return a sealed or recomputed research preview; invalid evidence raises."""
    require_sha(expected_artifact_sha256)
    now = clock_value(clock)
    sources = implementation_hashes()
    files = EvidenceFiles()
    protocol_path, state_root = Path(protocol_path).resolve(), Path(state_root).resolve()
    protocol_raw = files.read(protocol_path)
    parse(protocol_raw)
    files.read(protocol_path.with_suffix('.sha256'))
    protocol, study = load_cash_study(protocol_path, state_root=state_root)
    if digest(protocol_raw) != study.protocol_sha256:
        raise ValueError('protocol changed during load')
    if study.protocol_sha256 == LEGACY_PROTOCOL_SHA256:
        raise ValueError('legacy collection lacks original observed registry; no retrospective admission')
    registry_path = state_root / 'cash-study-registry.sqlite'
    files.read(registry_path, sqlite=True)
    collection = CashStudyRegistry(registry_path).get(study.protocol_sha256)
    if collection is None or not time(collection['observed_at']) <= now:
        raise ValueError('original observed collection registration required')
    if (collection.get('schema_version') != 'observed-collection-protocol-v1'
            or collection.get('live_promotion_allowed') is not False):
        raise ValueError('research-only original collection receipt required')
    if canonical(parse(collection['protocol_payload'])) != canonical(protocol):
        raise ValueError('original registered protocol differs from selected protocol')
    end = time(protocol['windows']['paper']['end_exclusive'])
    result = dict(schema_version='strategy-evidence-audit-v1', as_of=now.isoformat(),
        protocol_sha256=study.protocol_sha256, expected_artifact_sha256=expected_artifact_sha256,
        live_admission_granted=False, live_profitability_established=False,
        scope='original_local_research_provenance_and_recomputation_not_live_qualification',
        remaining_live_gates=['independent_strategy_qualification', 'live_eligible_evidence_policy',
            'actual_account_runtime_operational_qualification', 'explicit_operator_rollout'],
        implementation_sha256=sources)
    if now < end:
        result.update(status='sealed_until_paper_end', performance_hidden=True,
            paper_end=end.isoformat(), paper_evidence_pass=False, candidate_identity_verified=False)
    else:
        manifest, artifact, policy, acceptance, start = verify_freezes(files, study, protocol,
            expected_artifact_sha256=expected_artifact_sha256, now=now)
        retained = parse(files.read(study.paper_results))
        export_clock = time(retained['as_of'])
        if (retained['schema_version'] != 'paper-role-export-v1'
                or retained['simulated'] is not True or retained['performance_publication_hidden'] is not False
                or retained['real_training_examples_allowed'] is not False
                or retained['live_promotion_allowed'] is not False
                or set(retained['roles']) != set(ROLES) or not end <= export_clock <= now):
            raise ValueError('complete finished research role export required')
        recomputed, mark_audits = {}, {}
        config = validate_execution_design(policy)
        for role in ROLES:
            wallet, worker = study.paper_role_paths(role)
            files.read(wallet, sqlite=True)
            files.read(worker, sqlite=True)
            current = export_results(wallet, worker, as_of=export_clock)
            expected_policy, expected_config = deepcopy(policy), config
            expected_policy['evaluation_role'] = role
            if role == 'stress_candidate':
                multiplier = Decimal(acceptance['stress_cost_multiplier'])
                expected_config = replace(config, entry_fee=config.entry_fee * multiplier,
                    exit_fee=config.exit_fee * multiplier, slippage=config.slippage * multiplier,
                    cost_assumption_id=config.cost_assumption_id + ':stress-x' + str(multiplier))
                expected_policy['wallet'] = {**expected_policy['wallet'],
                    **{key: str(getattr(expected_config, key)) for key in
                       ('entry_fee', 'exit_fee', 'slippage', 'cost_assumption_id')}}
            wallet_config = json.loads(json.dumps(asdict(expected_config), default=str))
            if (canonical(current['worker_policy']) != canonical(expected_policy)
                    or canonical(current['policy']['config']) != canonical(wallet_config)
                    or current['candidate_artifact_sha256'] != expected_artifact_sha256):
                raise ValueError('role differs from originally frozen model/execution policy')
            current['evaluation_role'] = role
            if canonical(current) != canonical(retained['roles'][role]):
                raise ValueError('retained role differs from original database recomputation')
            mark_audits[role] = verify_mark_cash(wallet, current, start=start, end=end)
            recomputed[role] = current
        verify_opportunities(study, recomputed, manifest, artifact, protocol, start=start, end=end)
        saved_acceptance = parse(files.read(study.paper_acceptance))
        acceptance_clock = time(saved_acceptance['as_of'])
        if not export_clock <= acceptance_clock <= now:
            raise ValueError('acceptance precedes original export or uses future clock')
        evaluation = evaluate_paper(recomputed['candidate'], recomputed['baseline_control'],
            recomputed['stress_candidate'], acceptance, window_start=start, window_end=end,
            as_of=acceptance_clock, preregistered=True)
        evaluation['protocol_version'] = protocol['protocol_version']
        if canonical(evaluation) != canonical(saved_acceptance):
            raise ValueError('retained acceptance differs from original recomputation')
        marks_verified = all(row['historical_liquidation_values_verified'] for row in mark_audits.values())
        result.update(status='research_evidence_recomputed', performance_hidden=False,
            candidate_identity_verified=True,
            paper_evidence_pass=evaluation['paper_evidence_pass'] and marks_verified,
            conditional_evaluation_pass=evaluation['paper_evidence_pass'],
            historical_liquidation_values_verified=marks_verified, mark_cash_audits=mark_audits,
            evaluation=evaluation,
            recomputed_role_sha256={role: digest(canonical(row)) for role, row in recomputed.items()},
            original_opportunities_verified=True, artifact_contract=dict(
                feature_version=artifact['feature_version'], threshold=manifest['threshold'],
                target_version=artifact['config']['target_version'],
                feature_input_contract=artifact['config'].get('feature_input_contract')))
        if not marks_verified:
            result['remaining_live_gates'].append('historical_equity_valuation_source_qualification')
    files.verify()
    if implementation_hashes() != sources:
        raise ValueError('evidence verifier implementation changed during audit')
    result['input_files'] = list(files.files.values())
    result['audit_sha256'] = digest(canonical(result))
    return result
