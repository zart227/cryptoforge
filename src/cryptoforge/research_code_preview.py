"""Exact one-file research diff preview; never imports or executes candidate code."""
import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import re

from cryptoforge import semantic_source_collector as files, training_diagnostics
from cryptoforge.training_diagnostics import canonical, digest, exact_fields


POLICY = {'schema_version': 'research-code-preview-policy-v1', 'allowed_path': 'research/feature_candidate.py',
    'max_base_bytes': 16000, 'max_diff_bytes': 32000, 'max_candidate_bytes': 32000,
    'max_hunks': 8, 'max_changed_lines': 128, 'execution_enabled': False}
MAX_PROPOSAL_BYTES = 128000
HUNK = re.compile(r'@@ -([1-9][0-9]*)(?:,([1-9][0-9]*))? \+([1-9][0-9]*)(?:,([1-9][0-9]*))? @@\n')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _implementation():
    return {'preview': _sha(Path(__file__).read_bytes()),
            'canonical': _sha(Path(training_diagnostics.__file__).read_bytes())}


def _text(value, maximum):
    if (not isinstance(value, str) or not value.strip() or not value.endswith('\n')
            or any(c in value for c in ('\r', '\x00', '\ufeff')) or len(value.encode()) > maximum):
        raise ValueError('bounded UTF-8 LF text with final newline required; no binary/BOM/CR')
    return value


def apply_exact_diff(base, patch, policy):
    if canonical(policy) != canonical(POLICY):
        raise ValueError('fixed preview-only allowlist policy required')
    _text(base, policy['max_base_bytes']); _text(patch, policy['max_diff_bytes'])
    lines = [line + '\n' for line in patch.split('\n')[:-1]]
    old = [line + '\n' for line in base.split('\n')[:-1]]
    path = policy['allowed_path']
    if lines[:2] != ['--- a/' + path + '\n', '+++ b/' + path + '\n']:
        raise ValueError('one exact allowlisted file; no Git metadata, rename, mode or path variants')
    out, cursor, index, hunks, changed = [], 0, 2, 0, 0
    while index < len(lines):
        match = HUNK.fullmatch(lines[index])
        if match is None: raise ValueError('strict positive-range unified hunk required')
        hunks += 1
        if hunks > policy['max_hunks']: raise ValueError('too many patch hunks')
        start, old_count, new_start, new_count = [int(v or 1) for v in match.groups()]
        start -= 1
        if start < cursor or start > len(old): raise ValueError('overlapping or out-of-range hunk')
        out.extend(old[cursor:start])
        if new_start != len(out) + 1: raise ValueError('new hunk position mismatch')
        consumed = emitted = 0; index += 1
        while index < len(lines) and not lines[index].startswith('@@ '):
            line = lines[index]; prefix, value = line[:1], line[1:]
            if prefix not in (' ', '+', '-'): raise ValueError('plain text context/add/delete lines only')
            if prefix in (' ', '-'):
                if start + consumed >= len(old) or old[start + consumed] != value:
                    raise ValueError('exact hunk context mismatch; no fuzzy or whitespace matching')
                consumed += 1
            if prefix in (' ', '+'): out.append(value); emitted += 1
            if prefix in ('-', '+'): changed += 1
            if consumed > old_count or emitted > new_count or changed > policy['max_changed_lines']:
                raise ValueError('patch line count or changed-line limit exceeded')
            index += 1
        if consumed != old_count or emitted != new_count: raise ValueError('incomplete hunk line counts')
        cursor = start + consumed
    if not hunks or not changed: raise ValueError('nonempty effective diff required')
    out.extend(old[cursor:]); candidate = ''.join(out)
    _text(candidate, policy['max_candidate_bytes'])
    if candidate == base: raise ValueError('unchanged candidate is not a code experiment')
    return candidate


def prepare(proposal, policy):
    if len(canonical(proposal).encode()) > MAX_PROPOSAL_BYTES:
        raise ValueError('bounded research code proposal required')
    exact_fields(proposal, {'schema_version', 'origin', 'path', 'base_text', 'base_sha256', 'unified_diff',
        'policy_sha256', 'hypothesis', 'falsification', 'evidence_ids'})
    if (proposal['schema_version'] != 'research-code-patch-proposal-v1'
            or proposal['origin'] not in ('mock', 'external_unverified')
            or proposal['path'] != POLICY['allowed_path'] or proposal['policy_sha256'] != digest(policy)):
        raise ValueError('explicit unverified proposal and fixed research-only path required')
    for name in ('hypothesis', 'falsification'):
        value = proposal[name]
        if not isinstance(value, str) or not value.strip() or len(value.encode()) > 2000:
            raise ValueError('bounded hypothesis and falsification required')
    evidence = proposal['evidence_ids']
    if (not isinstance(evidence, list) or not 1 <= len(evidence) <= 16
            or any(not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value) for value in evidence)
            or len(set(evidence)) != len(evidence)):
        raise ValueError('explicit unique evidence hashes required; upstream verification remains separate')
    base = _text(proposal['base_text'], POLICY['max_base_bytes'])
    if proposal['base_sha256'] != _sha(base.encode()): raise ValueError('base bytes changed')
    candidate = apply_exact_diff(base, proposal['unified_diff'], policy)
    identity = {'path': proposal['path'], 'base_sha256': proposal['base_sha256'],
                'candidate_sha256': _sha(candidate.encode()), 'policy_sha256': digest(policy)}
    core = {'schema_version': 'research-code-preview-v1', 'origin': proposal['origin'],
        'proposal_sha256': digest(proposal), 'policy': deepcopy(policy), 'identity': identity,
        'candidate_text': candidate, 'candidate_identity_sha256': digest(identity),
        'base_assurance': 'caller_supplied_text_not_git_or_working_tree_attestation',
        'evidence_ids_verified': False, 'model_provenance_verified': False, 'syntax_checked': False,
        'candidate_executed': False, 'semantic_safety_verified': False, 'attempt_budget_reserved': False,
        'execution_authorized': False, 'training_executed': False, 'can_authorize_trades': False,
        'implementation': _implementation(), 'api_calls': 0}
    return {**core, 'preview_sha256': digest(core)}


def stage_preview(directory, proposal, policy):
    result = prepare(proposal, policy)
    directory = Path(directory); directory.mkdir(mode=0o700)
    files._write(directory, 'proposal.json', proposal); files._write(directory, 'policy.json', policy)
    for prefix, text in (('base', proposal['base_text']), ('candidate', result['candidate_text'])):
        parent = directory / prefix / 'research'; parent.mkdir(mode=0o700, parents=True)
        (directory / prefix).chmod(0o700)
        files._write(parent, 'feature_candidate.py', text.encode()); files._sync(parent); files._sync(parent.parent)
    files._write(directory, 'preview.json', result); files._sync(directory); files._sync(directory.parent)
    return result


def read_preview(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir(): raise ValueError('private preview directory required')
    proposal = files._json(directory, 'proposal.json', MAX_PROPOSAL_BYTES)
    policy = files._json(directory, 'policy.json', 4000)
    rebuilt = prepare(proposal, policy)
    if canonical(files._json(directory, 'preview.json', MAX_PROPOSAL_BYTES)) != canonical(rebuilt):
        raise ValueError('preview or implementation changed')
    for prefix, expected in (('base', proposal['base_text']), ('candidate', rebuilt['candidate_text'])):
        for parent in (directory / prefix, directory / prefix / 'research'):
            if parent.is_symlink() or not parent.is_dir(): raise ValueError('preview parent symlink refused')
        raw = files._read(directory / prefix / 'research', 'feature_candidate.py', POLICY['max_candidate_bytes'])
        if raw != expected.encode(): raise ValueError('private source copy changed')
    return rebuilt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    preview = sub.add_parser('prepare')
    preview.add_argument('--proposal', type=Path, required=True); preview.add_argument('--policy', type=Path, required=True)
    for command in (preview, sub.add_parser('verify')): command.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        proposal = files._json(args.proposal.parent, args.proposal.name, MAX_PROPOSAL_BYTES)
        policy = files._json(args.policy.parent, args.policy.name, 4000)
        stage_preview(args.directory, proposal, policy)
    else: read_preview(args.directory)
    print('Exact code preview verified; candidate not imported, executed or applied to repository')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
