from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from cryptoforge import research_code_preview as preview
from cryptoforge.research_training_diagnostics import canonical, digest


PATH = 'research/feature_candidate.py'
BASE = "def candidate_features(window):\n    return {'value': 0.0}\n"
PATCH = ("--- a/" + PATH + "\n+++ b/" + PATH + "\n@@ -1,2 +1,2 @@\n"
         " def candidate_features(window):\n-    return {'value': 0.0}\n+    return {'value': 1.0}\n")


def proposal(base=BASE, patch=PATCH):
    return {'schema_version': 'research-code-patch-proposal-v1', 'origin': 'mock', 'path': PATH,
        'base_text': base, 'base_sha256': hashlib.sha256(base.encode()).hexdigest(), 'unified_diff': patch,
        'policy_sha256': digest(preview.POLICY), 'hypothesis': 'Synthetic interface fixture only.',
        'falsification': 'No training benefit is claimed.', 'evidence_ids': ['a' * 64]}


def test_preview_hashes_exact_bytes_and_does_not_promote_or_execute_code():
    value = proposal(); original = deepcopy(value)
    result = preview.prepare(value, preview.POLICY)
    assert value == original and result['candidate_text'] == BASE.replace('0.0', '1.0')
    assert result['identity']['candidate_sha256'] == hashlib.sha256(result['candidate_text'].encode()).hexdigest()
    for flag in ('syntax_checked', 'candidate_executed', 'semantic_safety_verified', 'attempt_budget_reserved',
                 'execution_authorized', 'training_executed', 'can_authorize_trades', 'model_provenance_verified', 'evidence_ids_verified'):
        assert result[flag] is False
    assert result['origin'] == 'mock' and result['api_calls'] == 0


def test_hypothesis_or_evidence_changes_do_not_multiply_effective_candidate_identity():
    value = proposal(); first = preview.prepare(value, preview.POLICY)
    value['hypothesis'] = 'Different wording.'; value['evidence_ids'] = ['b' * 64]
    second = preview.prepare(value, preview.POLICY)
    assert second['proposal_sha256'] != first['proposal_sha256']
    assert second['candidate_identity_sha256'] == first['candidate_identity_sha256']


@pytest.mark.parametrize('path', ['../feature.py', '/tmp/feature.py', 'research/../feature.py',
    'research\\feature_candidate.py', 'research/feature_candidate.py\t', 'research/feature_candidate.py/extra',
    'src/cryptoforge/live_risk.py', 'tests/test_model_training.py', 'pyproject.toml', '.env', '.git/config'])
def test_paths_outside_exact_virtual_allowlist_are_rejected(path):
    value = proposal(); value['path'] = path
    value['unified_diff'] = PATCH.replace(PATH, path)
    with pytest.raises(ValueError): preview.prepare(value, preview.POLICY)


@pytest.mark.parametrize('field,value', [('allowed_path', 'src/cryptoforge/live_risk.py'), ('execution_enabled', True),
    ('max_changed_lines', 1000), ('max_hunks', 100), ('max_diff_bytes', 64000)])
def test_policy_cannot_silently_expand_or_enable_execution(field, value):
    policy = {**preview.POLICY, field: value}; item = proposal(); item['policy_sha256'] = digest(policy)
    with pytest.raises(ValueError): preview.prepare(item, policy)


@pytest.mark.parametrize('mutation', ['bad_base', 'wrong_policy', 'commands', 'live_origin', 'empty_evidence',
    'duplicate_evidence', 'non_hash_evidence', 'blank_hypothesis', 'unknown_schema'])
def test_proposal_contract_does_not_accept_commands_or_fabricated_provenance(mutation):
    value = proposal()
    if mutation == 'bad_base': value['base_sha256'] = 'b' * 64
    elif mutation == 'wrong_policy': value['policy_sha256'] = 'b' * 64
    elif mutation == 'commands': value['commands'] = ['echo forbidden']
    elif mutation == 'live_origin': value['origin'] = 'verified_openrouter'
    elif mutation == 'empty_evidence': value['evidence_ids'] = []
    elif mutation == 'duplicate_evidence': value['evidence_ids'] *= 2
    elif mutation == 'non_hash_evidence': value['evidence_ids'] = ['invented']
    elif mutation == 'blank_hypothesis': value['hypothesis'] = ' '
    else: value['schema_version'] = 'other'
    with pytest.raises(ValueError): preview.prepare(value, preview.POLICY)


@pytest.mark.parametrize('patch', [
    'diff --git a/x b/x\n' + PATCH,
    PATCH.replace('--- a/', '--- /dev/null '),
    PATCH.replace('@@ -1,2 +1,2 @@', '@@ -1,2 +2,2 @@'),
    PATCH.replace('@@ -1,2 +1,2 @@', '@@ -1,3 +1,2 @@'),
    PATCH.replace('@@ -1,2 +1,2 @@', '@@ -1,2 +1,3 @@'),
    PATCH.replace('@@ -1,2 +1,2 @@', '@@ -0,0 +1,2 @@'),
    PATCH.replace('@@ -1,2 +1,2 @@', '@@ -1,2 +1,2 @@ function'),
    PATCH.replace(' def candidate_features', ' def wrong_features'),
    PATCH + '\\ No newline at end of file\n',
    PATCH + '--- a/second.py\n+++ b/second.py\n',
    PATCH.replace('+    return', 'GIT binary patch\n+    return'),
    PATCH.replace('\n', '\r\n'), PATCH[:-1], PATCH + '\x00\n', '\ufeff' + PATCH,
])
def test_extended_fuzzy_partial_binary_and_malformed_diffs_are_rejected(patch):
    with pytest.raises(ValueError): preview.prepare(proposal(patch=patch), preview.POLICY)


def test_multiple_hunks_handle_exact_new_coordinates_and_reject_overlap():
    base = 'one\ntwo\nthree\nfour\n'
    patch = '--- a/'+PATH+'\n+++ b/'+PATH+'\n@@ -1 +1,2 @@\n-one\n+ONE\n+extra\n@@ -4 +5 @@\n-four\n+FOUR\n'
    assert preview.apply_exact_diff(base, patch, preview.POLICY) == 'ONE\nextra\ntwo\nthree\nFOUR\n'
    with pytest.raises(ValueError): preview.apply_exact_diff(base, patch.replace('@@ -4 +5 @@', '@@ -1 +5 @@'), preview.POLICY)


def test_unicode_is_exact_and_only_lf_splits_unified_lines():
    base = "value = 'α\u2028β'\n"
    patch = '--- a/'+PATH+'\n+++ b/'+PATH+"\n@@ -1 +1 @@\n-value = 'α\u2028β'\n+value = '🔎\u2028β'\n"
    assert preview.apply_exact_diff(base, patch, preview.POLICY) == "value = '🔎\u2028β'\n"
    with pytest.raises(ValueError): preview.apply_exact_diff(base.replace('α', 'a'), patch, preview.POLICY)


def test_effectively_unchanged_context_only_and_size_limits_fail():
    with pytest.raises(ValueError): preview.apply_exact_diff(BASE, PATCH.replace("{'value': 1.0}", "{'value': 0.0}"), preview.POLICY)
    context = '--- a/'+PATH+'\n+++ b/'+PATH+'\n@@ -1,2 +1,2 @@\n' + ''.join(' '+line+'\n' for line in BASE.split('\n')[:-1])
    with pytest.raises(ValueError): preview.apply_exact_diff(BASE, context, preview.POLICY)
    with pytest.raises(ValueError): preview.apply_exact_diff('x' * 16001 + '\n', PATCH, preview.POLICY)
    with pytest.raises(ValueError): preview.apply_exact_diff(BASE, PATCH + 'x' * 32000 + '\n', preview.POLICY)


def test_hunk_and_changed_line_limits_are_enforced_without_truncation():
    base = ''.join('old'+str(i)+'\n' for i in range(70))
    patch = '--- a/'+PATH+'\n+++ b/'+PATH+'\n@@ -1,70 +1,70 @@\n'
    patch += ''.join('-'+line+'\n' for line in base.split('\n')[:-1])
    patch += ''.join('+new'+str(i)+'\n' for i in range(70))
    with pytest.raises(ValueError, match='changed-line'): preview.apply_exact_diff(base, patch, preview.POLICY)
    patch = '--- a/'+PATH+'\n+++ b/'+PATH+'\n'
    for i in range(9): patch += '@@ -'+str(i+1)+' +'+str(i+1)+' @@\n-old'+str(i)+'\n+new'+str(i)+'\n'
    with pytest.raises(ValueError, match='too many'): preview.apply_exact_diff(base, patch, preview.POLICY)


def test_source_with_side_effects_is_only_copied_never_imported(tmp_path):
    marker = tmp_path/'must-not-exist'
    replacement = "open("+repr(str(marker))+", 'w').write('forbidden')\n"
    patch = '--- a/'+PATH+'\n+++ b/'+PATH+'\n@@ -1,2 +1 @@\n' + ''.join('-'+line+'\n' for line in BASE.split('\n')[:-1]) + '+'+replacement
    root = tmp_path/'preview'
    result = preview.stage_preview(root, proposal(patch=patch), preview.POLICY)
    assert not marker.exists() and not result['candidate_executed']
    assert (root/'candidate'/PATH).read_text() == replacement
    assert preview.read_preview(root) == result


def test_preview_is_private_exclusive_and_rejects_copy_or_parent_symlink_tampering(tmp_path):
    root = tmp_path/'preview'; result = preview.stage_preview(root, proposal(), preview.POLICY)
    assert preview.read_preview(root) == result
    for path in root.rglob('*'): assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
    with pytest.raises(FileExistsError): preview.stage_preview(root, proposal(), preview.POLICY)
    candidate = root/'candidate'/PATH; candidate.write_text('forged\n')
    with pytest.raises(ValueError): preview.read_preview(root)
    candidate.unlink(); candidate.symlink_to(root/'base'/PATH)
    with pytest.raises(OSError): preview.read_preview(root)
    candidate.unlink(); (root/'candidate/research').rmdir()
    (root/'candidate/research').symlink_to(root/'base/research', target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'): preview.read_preview(root)


def test_bad_proposal_does_not_create_output_and_cli_never_changes_repo(tmp_path):
    value = proposal(); value['base_sha256'] = 'b' * 64
    root = tmp_path/'bad'
    with pytest.raises(ValueError): preview.stage_preview(root, value, preview.POLICY)
    assert not root.exists()
    source = tmp_path/'proposal.json'; source.write_text(canonical(proposal()))
    policy = tmp_path/'policy.json'; policy.write_text(canonical(preview.POLICY))
    root = tmp_path/'private'
    assert preview.main(['prepare', '--proposal', str(source), '--policy', str(policy), '--directory', str(root)]) == 0
    assert preview.main(['verify', '--directory', str(root)]) == 0
    assert not (tmp_path/PATH).exists()


def test_checked_in_config_matches_fixed_disabled_policy():
    path = Path(__file__).parents[1]/'config/research-code-preview-v1.json'
    assert json.loads(path.read_text()) == preview.POLICY
