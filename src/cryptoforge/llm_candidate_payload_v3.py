"""Offline candidate request contract with explicit new wire identity.

Previewing a payload never reserves a journal or dispatches a request. This is
not a provider adapter: existing journals cannot use its proposed identity until
an explicitly versioned, verified accounting/transport integration exists.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from cryptoforge import llm_audited_provider_v2 as candidate
from cryptoforge import llm_prompt_preflight as prompt
from cryptoforge import llm_research_advisor as advisor
from cryptoforge import llm_research_requests as requests
from cryptoforge.research_training_diagnostics import canonical, digest, validate_diagnostics

POLICY={'schema_version':'candidate-payload-contract-v3',
        'provider':'openrouter','model':candidate.CANDIDATE_MODEL,
        'parameters':['l2','threshold'],'max_completion_tokens':2048,
        'max_prompt_price':'0','max_completion_price':'0',
        'journal_or_transport_integration_enabled':False,'native_input_bound_verified':False}


def implementation():
    names=('llm_candidate_payload_v3.py','llm_prompt_preflight.py','llm_research_advisor.py',
           'llm_research_requests.py','llm_research_contracts.py','training_diagnostics.py')
    return {'sources':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names},
            'v2_candidate':candidate.implementation()}


_LOADED=implementation(); _POLICY=canonical(POLICY)


def _guard():
    candidate._guard()
    if (implementation()!=_LOADED or canonical(POLICY)!=_POLICY
            or POLICY['model']!=candidate.CANDIDATE_MODEL):
        raise ValueError('fixed_candidate_payload_v3_required')


def preview(report):
    """Build a prospective request and separate identity, with no I/O effects."""
    _guard(); report=deepcopy(validate_diagnostics(report))
    if report['partition']!='validation':raise ValueError('validation_report_required')
    adapter=advisor.FreeAdvisor(provider='openrouter',model=POLICY['model'],parameters=tuple(POLICY['parameters']))
    legacy=adapter.preflight(report)
    # Preserve the pinned factory's messages and zero-price routing; change only
    # the documented completion-limit field in this separate contract.
    payload=deepcopy(legacy['payload'])
    limit=payload.pop('max_tokens')
    if limit!=POLICY['max_completion_tokens']:raise ValueError('fixed_completion_limit_required')
    payload['max_completion_tokens']=limit
    size=len(canonical(payload).encode('utf-8'))
    if size>prompt.MAX_REQUEST_BYTES:raise ValueError('serialized provider payload byte limit exceeded')
    original_inputs=requests.ResearchRequests._inputs(None,adapter,report)
    contract={'schema_version':'candidate-prospective-request-identity-v3',
        'legacy_native_inputs':original_inputs,'payload_sha256':digest(payload),
        'policy_sha256':digest(POLICY),'implementation':_LOADED}
    _guard()
    return {'schema_version':'candidate-payload-preview-v3','payload':payload,
        'request_payload_sha256':digest(payload),'request_payload_bytes':size,
        'legacy_native_request_key':digest(original_inputs),
        'prospective_v3_request_identity':digest(contract),'prospective_identity_inputs':contract,
        'input_preflight':{**legacy['audit'],'request_payload_bytes':size,
            'request_payload_sha256':digest(payload),'payload_contract_version':'candidate-payload-contract-v3'},
        'legacy_native_payload_sha256':legacy['audit']['request_payload_sha256'],
        'new_native_input_token_limit_verified':False,
        'request_or_journal_admission_authorized':False,'transport_or_accounting_connected':False}


def admit_new_completion(report):
    """Fail closed until a separately qualified native input-bound integration."""
    preview(report)
    prompt.require_verified_limit(True)
    raise ValueError('candidate_v3_transport_and_accounting_not_integrated')
