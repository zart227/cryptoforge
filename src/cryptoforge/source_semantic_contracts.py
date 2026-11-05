"""Versioned source-packet bridge to the existing budgeted local decision client."""
from copy import deepcopy
import hashlib
from pathlib import Path

from cryptoforge import local_semantic_contracts as local, semantic_event_review as events
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp
from cryptoforge.typesafe_judgment_contracts import normalize_answer


SCHEMA = 'local-semantic-source-request-v2'
RESULT_SCHEMA = 'local-semantic-source-result-v2'
MAX_REQUEST_BYTES = 180000


def implementation():
    return {'source_contracts': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'event_review': events._implementation(), 'local_contracts': local.implementation()}


def prepare_request(snapshot, bundle, packet, *, endpoint, digest_pin, version=local.SUPPORTED_SERVER_VERSION):
    events.validate_packet(packet, snapshot, bundle)
    if version != local.SUPPORTED_SERVER_VERSION:
        raise ValueError('checked Ollama 0.40.5 digest-reference profile required')
    pin = local.model_digest(digest_pin)
    reference = 'sha256-' + pin.removeprefix('sha256:') + ':local'
    wire = {'model': reference, 'state': deepcopy(packet['model_state']), 'keep_alive': 0,
        'questions': {name: {key: deepcopy(q[key]) for key in ('type', 'instructions', 'criteria')}
                      for name, q in packet['catalog']['questions'].items()}}
    size = len(canonical(wire).encode())
    if size > local.MAX_WIRE_BYTES:
        raise ValueError('bounded source semantic wire required; no truncation')
    core = {'schema_version': SCHEMA, 'origin': 'closed_source_event_packet',
        'endpoint': local.local_endpoint(endpoint), 'snapshot': deepcopy(snapshot), 'registry_bundle': deepcopy(bundle),
        'packet': deepcopy(packet), 'catalog': deepcopy(packet['catalog']),
        'model_digest': pin, 'model_reference': reference, 'server_version': version,
        'wire_request': wire, 'wire_bytes': size, 'implementation': implementation(),
        'hard_input_token_limit_verified': False, 'byte_limit_is_token_limit': False,
        'upstream_development_lineage_verified': False}
    result = {**core, 'request_sha256': digest(core)}
    if len(canonical(result).encode()) > MAX_REQUEST_BYTES:
        raise ValueError('bounded source request including original evidence required; no truncation')
    return result


def validate_request(request):
    exact_fields(request, {'schema_version', 'origin', 'endpoint', 'snapshot', 'registry_bundle', 'packet', 'catalog',
        'model_digest', 'model_reference', 'server_version', 'wire_request', 'wire_bytes', 'implementation',
        'hard_input_token_limit_verified', 'byte_limit_is_token_limit', 'upstream_development_lineage_verified',
        'request_sha256'})
    rebuilt = prepare_request(request['snapshot'], request['registry_bundle'], request['packet'],
        endpoint=request['endpoint'], digest_pin=request['model_digest'], version=request['server_version'])
    if canonical(rebuilt) != canonical(request):
        raise ValueError('source semantic request or implementation changed')
    return request


def compose_review(request, result):
    """Compose only normalized local-client results; never relabel a mock as live."""
    validate_request(request)
    packet = request['packet']
    if (result.get('schema_version') != RESULT_SCHEMA or result.get('origin') != 'ollama_local_systemone'
            or result.get('request_sha256') != request['request_sha256']
            or result.get('source_packet_sha256') != packet['packet_sha256']
            or result.get('inference_identity_sha256') != local.inference_identity(request)
            or result.get('state_sha256') != packet['model_state_sha256']
            or result.get('question_catalog_sha256') != packet['question_catalog_sha256']
            or result.get('model_digest') != request['model_digest']
            or result.get('question_snapshot') != request['catalog']):
        raise ValueError('bound normalized source result required')
    received = timestamp(result['metadata']['response_received_at'])
    if received > timestamp(result['metadata']['checked_at']):
        raise ValueError('source response receipt follows metadata check')
    timestamp(result['semantic_journal_finished_at'])
    answers = result['answers']; questions = request['catalog']['questions']
    exact_fields(answers, set(questions))
    # Check the typed normalized shape too; no caller-supplied choice or quote.
    for name, answer in answers.items():
        if not isinstance(answer, dict):
            raise ValueError('normalized source answer object required')
        if answer.get('status') == 'error':
            if answer != {'status': 'error', 'type': 'choice', 'error': 'invalid_or_missing_answer'}:
                raise ValueError('invalid normalized source error')
        else:
            raw = {'type': answer.get('type'), 'choice': answer.get('value'),
                'confidence': answer.get('confidence'), 'probabilities': answer.get('probabilities')}
            if normalize_answer(questions[name], raw) != answer:
                raise ValueError('normalized source choice changed')
    selected = {key: value.get('value') for key, value in answers.items() if value['status'] == 'available'}
    proposal, status, reason = None, 'abstain', 'invalid_uncertain_or_incomplete_judgment'
    if selected.get('asset') == 'no_match':
        status, reason = 'no_match', 'no_closed_asset_matches_focal_occurrence'
    elif all(value['status'] == 'available' for value in answers.values()):
        if selected['source_support'] != 'sufficient': reason = 'source_' + selected['source_support']
        elif selected['market_scope'] == 'mixed': reason = 'ambiguous_focal_market_scope'
        elif selected['event_state'] == 'not_stated': reason = 'no_focal_event_claim_not_a_negative_label'
        elif selected['evidence'] == 'no_match': reason = 'missing_supporting_chunk'
        else:
            state = packet['model_state']
            asset = next(row for row in state['asset_options'] if row['option'] == selected['asset'])
            evidence = next(row for row in state['evidence_options'] if row['option'] == selected['evidence'])
            proposal = {'proposed_asset_id': asset['asset_id'], 'event_type': state['event_type'],
                'event_state': selected['event_state'], 'market_scope': selected['market_scope'],
                'message_kind': selected['message_kind'], 'event_time': None, 'evidence': deepcopy(evidence),
                'focus': deepcopy(state['focus']), 'requires_human_review': True, 'source_claim_only': True}
            status, reason = 'review_required', 'provider_claim_requires_independent_review'
    core = {'schema_version': 'source-semantic-review-v1', 'origin': 'ollama_local_systemone',
        'source_origin': packet['source_origin'], 'registry_origin': packet['registry_origin'],
        'packet_sha256': packet['packet_sha256'], 'request_sha256': request['request_sha256'],
        'inference_identity_sha256': result['inference_identity_sha256'], 'response_sha256': result['response_sha256'],
        'question_catalog_sha256': packet['question_catalog_sha256'], 'answers': deepcopy(answers),
        'status': status, 'reason': reason, 'annotation_proposal': proposal,
        'judgment_received_at': received.isoformat(), 'journal_finished_at': result['semantic_journal_finished_at'],
        'timestamp_assurance': 'local_worker_and_journal_clocks_not_external_attestation',
        'inference_available_at': None, 'historical_feature_availability_verified': False,
        'resolved_asset_id': None, 'human_gold': False, 'context_grounding_verified': False,
        'global_token_identity_verified': False, 'external_truth_verified': False, 'policy_calibrated': False,
        'source_coverage_verified': False, 'empty_or_no_match_is_negative_label': False,
        'event_labels_created': False, 'training_features_created': False, 'can_authorize_trades': False}
    return {**core, 'review_sha256': digest(core)}
