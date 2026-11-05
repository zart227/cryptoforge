"""Read-only static review of an already registered preview; never executes it."""
import argparse
import ast
import hashlib
import math
from pathlib import Path
import sqlite3
import sys
import time

from cryptoforge import research_code_budget as code, research_code_preview as preview
from cryptoforge import research_run_budget as common
from cryptoforge.research_resource_budget import resource_snapshot
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields
from cryptoforge.llm_research_contracts import strict_json


POLICY = {'schema_version': 'research-feature-static-contract-v1', 'path': 'research/feature_candidate.py',
    'function': 'candidate_features', 'argument': 'window', 'output_key': 'value',
    'candle_fields': ['open', 'high', 'low', 'close', 'volume'],
    'max_source_bytes': 32000, 'max_ast_nodes': 512, 'max_ast_depth': 32,
    'max_window_candles': 64, 'max_abs_literal': 1000000,
    'candidate_execution_enabled': False}


def implementation():
    return {'static_checker': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python_ast': hashlib.sha256(Path(ast.__file__).read_bytes()).hexdigest(),
        'preview_and_common': code.implementation()}


_LOADED = implementation()


def _guard():
    if implementation() != _LOADED or common._source_sha() != common._LOADED_SHA:
        raise ValueError('static review implementation changed; restart required')


class ContractRejected(ValueError):
    def __init__(self, rule, node=None):
        self.issue = {'rule': rule, 'line': getattr(node, 'lineno', None),
                      'column': getattr(node, 'col_offset', None)}


def _literal_index(node):
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(node.op, ast.USub) else 1; node = node.operand
    if not isinstance(node, ast.Constant) or type(node.value) is not int:
        raise ContractRejected('literal_window_index_required', node)
    value = sign * node.value
    if not -POLICY['max_window_candles'] <= value < POLICY['max_window_candles']:
        raise ContractRejected('window_index_outside_contract', node)
    return value


def _expression(node, reads):
    if isinstance(node, ast.Constant):
        if (type(node.value) not in (int, float) or abs(node.value) > POLICY['max_abs_literal']
                or not math.isfinite(node.value)):
            raise ContractRejected('finite_bounded_numeric_literal_required', node)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        _expression(node.operand, reads)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        _expression(node.left, reads); _expression(node.right, reads)
        if isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and node.right.value == 0:
            raise ContractRejected('literal_zero_denominator', node)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ('abs', 'min', 'max'):
            raise ContractRejected('call_outside_closed_numeric_set', node)
        if node.keywords or (len(node.args) != 1 if node.func.id == 'abs' else not 2 <= len(node.args) <= 4):
            raise ContractRejected('fixed_numeric_call_arity_required', node)
        for argument in node.args: _expression(argument, reads)
    elif isinstance(node, ast.Subscript):
        inner = node.value
        if (not isinstance(inner, ast.Subscript) or not isinstance(inner.value, ast.Name)
                or inner.value.id != POLICY['argument'] or not isinstance(node.slice, ast.Constant)
                or type(node.slice.value) is not str or node.slice.value not in POLICY['candle_fields']):
            raise ContractRejected('closed_window_candle_field_required', node)
        reads.add((_literal_index(inner.slice), node.slice.value))
    else:
        raise ContractRejected('expression_outside_static_contract', node)


def _analyze(source):
    """Pure bounded AST inspection, private to tests and registered review."""
    syntax, nodes, depth, reads = False, 0, 0, set()
    try:
        preview._text(source, POLICY['max_source_bytes'])
        tree = ast.parse(source, filename=POLICY['path'], mode='exec', type_comments=True, feature_version=(3, 12))
        syntax = True; pending = [(tree, 0)]
        while pending:
            node, level = pending.pop(); nodes += 1; depth = max(depth, level)
            if nodes > POLICY['max_ast_nodes']: raise ContractRejected('ast_node_limit')
            if depth > POLICY['max_ast_depth']: raise ContractRejected('ast_depth_limit')
            pending.extend((child, level + 1) for child in ast.iter_child_nodes(node))
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.type_ignores:
            raise ContractRejected('single_function_module_required')
        function = tree.body[0]; args = function.args
        if (function.name != POLICY['function'] or function.decorator_list or function.returns is not None
                or function.type_comment is not None or function.type_params or args.posonlyargs
                or len(args.args) != 1 or args.args[0].arg != POLICY['argument']
                or args.args[0].annotation is not None or args.args[0].type_comment is not None
                or args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.kw_defaults
                or len(function.body) != 1 or not isinstance(function.body[0], ast.Return)):
            raise ContractRejected('exact_feature_function_signature_and_body_required', function)
        returned = function.body[0].value
        if (not isinstance(returned, ast.Dict) or len(returned.keys) != 1
                or not isinstance(returned.keys[0], ast.Constant)
                or type(returned.keys[0].value) is not str or returned.keys[0].value != POLICY['output_key']):
            raise ContractRejected('single_value_output_required', returned)
        _expression(returned.values[0], reads)
        issue, verdict = None, 'passed_static_contract'
    except ContractRejected as error:
        issue, verdict = error.issue, 'rejected'
    except SyntaxError as error:
        issue = {'rule': 'python_syntax', 'line': error.lineno, 'column': error.offset}
        verdict = 'rejected'
    except (ValueError, UnicodeError, MemoryError, RecursionError):
        issue, verdict = {'rule': 'source_or_parser_limit', 'line': None, 'column': None}, 'rejected'
    return {'schema_version': 'research-feature-static-analysis-v1', 'verdict': verdict,
        'syntax_parsed': syntax, 'issue': issue, 'ast_nodes_observed': nodes, 'ast_depth_observed': depth,
        'window_reads': [{'index': index, 'field': field} for index, field in sorted(reads)] if issue is None else [],
        'required_window_size': max((index + 1 if index >= 0 else -index for index, _ in reads), default=0) if issue is None else None,
        'bytecode_created': False, 'candidate_imported': False, 'candidate_executed': False,
        'input_availability_verified': False, 'numeric_validity_verified': False,
        'runtime_contract_verified': False, 'independent_dynamic_tests_executed': False,
        'feature_utility_verified': False, 'execution_authorized': False}


def _registered_preview(budget, checked):
    """Verify the persisted completed row in one read-only SQLite transaction."""
    if budget.code_configuration is None or not budget.path.is_file():
        raise ValueError('existing migrated code-check journal required')
    identity = {'candidate_identity_sha256': checked['candidate_identity_sha256']}
    key = digest({'kind': 'code_check', 'identity': identity, 'questions': 0,
        'executor': common._LOADED_SHA, 'code_configuration_sha256': digest(budget.code_configuration)})
    db = sqlite3.connect(budget.path.as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        tables = budget._check_objects(db); budget._check_manifest(db); budget._check_extension(db, tables)
        resource_snapshot(db, budget.resource_policy, budget.semantic_policy, budget.code_policy)
        row = db.execute('''SELECT kind,input_sha,questions,status,payload,payload_sha,observed,observed_sha
            FROM coordinated_actions WHERE key=?''', (key,)).fetchone()
        if row is None or row[:4] != ('code_check', digest(identity), 0, 'completed'):
            raise ValueError('matching completed preview reservation required; no new attempt or retry')
        envelope = strict_json(row[4], max_bytes=64000)
        exact_fields(envelope, {'result', 'observed'})
        if (digest(envelope) != row[5] or canonical(envelope['observed']) != row[6]
                or digest(envelope['observed']) != row[7] or canonical(envelope['observed']) != canonical(common.ZERO_USAGE)):
            raise ValueError('registered preview checksum or usage mismatch')
        result = envelope['result']
        fields = {'schema_version', 'candidate_identity_sha256', 'preview_sha256', 'exact_preview_verified',
            'attempt_budget_reserved', 'reservation_scope', 'candidate_execution_budget_reserved',
            'candidate_execution_enabled', 'candidate_executed', 'syntax_checked', 'training_executed',
            'evidence_ids_verified', 'model_provenance_verified', 'can_authorize_trades'}
        exact_fields(result, fields)
        expected = {name: False for name in fields - {'schema_version', 'candidate_identity_sha256',
            'preview_sha256', 'exact_preview_verified', 'attempt_budget_reserved', 'reservation_scope'}}
        expected.update(schema_version='budgeted-code-preview-check-v3',
            candidate_identity_sha256=checked['candidate_identity_sha256'], preview_sha256=result['preview_sha256'],
            exact_preview_verified=True, attempt_budget_reserved=True, reservation_scope='shared_preview_check_only')
        if (canonical(result) != canonical(expected) or not isinstance(result['preview_sha256'], str)
                or len(result['preview_sha256']) != 64 or any(c not in '0123456789abcdef' for c in result['preview_sha256'])):
            raise ValueError('registered preview result differs from closed v3 contract')
        return {'operation_key': key, 'original_envelope_sha256': row[5],
            'original_preview_sha256': result['preview_sha256'],
            'common_journal_path_sha256': digest(str(budget.path)), 'manifest_sha256': digest(budget.manifest),
            'code_configuration_sha256': digest(budget.code_configuration),
            'scope': 'existing_completed_preview_not_static_or_execution_reservation',
            'database_read_only': True, 'new_common_actions': 0}
    finally:
        db.close()


def review(budget, directory, policy):
    _guard()
    if canonical(policy) != canonical(POLICY):
        raise ValueError('fixed independent static contract required')
    before = preview.read_preview(directory)
    proof = _registered_preview(budget, before)
    started = time.monotonic_ns(); analysis = _analyze(before['candidate_text'])
    elapsed = (time.monotonic_ns() - started + 999999) // 1000000
    after = preview.read_preview(directory)
    if after['preview_sha256'] != before['preview_sha256']:
        raise ValueError('preview changed during static review')
    _guard()
    core = {'schema_version': 'research-code-static-review-v1', 'policy': strict_json(canonical(POLICY)),
        'candidate_identity_sha256': before['candidate_identity_sha256'],
        'current_preview_sha256': before['preview_sha256'], 'registration': proof, 'analysis': analysis,
        'implementation': _LOADED, 'python_version': list(sys.version_info[:3]), 'analysis_wall_ms': elapsed,
        'static_cost_in_common_resource_journal': False, 'new_attempt_reserved': False,
        'candidate_execution_budget_reserved': False, 'evidence_ids_verified': False,
        'model_provenance_verified': False, 'execution_authorized': False, 'training_executed': False,
        'can_authorize_trades': False, 'operational_database_connections': 0, 'provider_requests': 0,
        'sqlite_connections': 1, 'shared_journal_reads': 1}
    return {**core, 'review_sha256': digest(core)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'proposal-ledger', 'semantic-ledger', 'fit-ledger', 'semantic-live-ledger',
                 'semantic-live-policy', 'code-policy', 'preview', 'static-policy', 'directory'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--policy', type=Path); parser.add_argument('--resource-policy', type=Path)
    args = parser.parse_args(argv)
    def read(path): return preview.files._json(path.parent, path.name, 64000) if path is not None else None
    budget = common.ResearchRunBudget(args.database, {'proposal': args.proposal_ledger,
        'semantic_fixture': args.semantic_ledger, 'fit': args.fit_ledger},
        policy=read(args.policy), resource_policy=read(args.resource_policy),
        semantic_live_ledger=args.semantic_live_ledger, semantic_live_policy=read(args.semantic_live_policy),
        code_check_policy=read(args.code_policy))
    result = review(budget, args.preview, read(args.static_policy))
    args.directory.mkdir(mode=0o700)
    preview.files._write(args.directory, 'review.json', result)
    preview.files._sync(args.directory); preview.files._sync(args.directory.parent)
    print('Independent static review: ' + result['analysis']['verdict'] + '; candidate not executed')
    return 0 if result['analysis']['verdict'] == 'passed_static_contract' else 2


if __name__ == '__main__':
    raise SystemExit(main())
