import json
from pathlib import Path
import sqlite3

import pytest

from test_llm_training_experiments import setup, proposal
from cryptoforge.llm_research_advisor import FreeAdvisor, DEFAULT_MODEL
from cryptoforge.llm_research_requests import ResearchRequests
from cryptoforge.llm_advice_provenance import verify_advice
from cryptoforge.llm_training_study import freeze_study, run_study
from cryptoforge.training_diagnostics import digest


def origin(tmp_path):
    path, data, protocol, _, _, report = setup(tmp_path)
    def transport(url, *args, **kwargs):
        if url.endswith('/models'):
            return {'data': [{'id': DEFAULT_MODEL, 'pricing': {'prompt': '0', 'completion': '0'}}]}
        return {'model': DEFAULT_MODEL, 'usage': {'prompt_tokens': 50, 'completion_tokens': 20},
                'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal())}}]}
    journal = tmp_path/'api.sqlite'
    advice = ResearchRequests(journal).propose(FreeAdvisor(api_key='private-key',
        parameters=('l2','threshold'), transport=transport), report)
    receipt = {'status': 'completed', 'diagnostics': report, 'advice': advice,
               'started_at': '2026-10-16T00:00:00+00:00', 'finished_at': '2026-10-16T00:00:02+00:00'}
    file = tmp_path/'advice.json'
    file.write_text(json.dumps(receipt))
    return path, data, journal, file, receipt


def test_readonly_verified_link_excludes_secrets_and_reports_partial_cost(tmp_path):
    _, data, journal, file, _ = origin(tmp_path)
    result = verify_advice(file, journal, dataset_sha256=digest(data))
    assert result['preparation_wall_seconds'] == 2
    assert result['usage'] == {'prompt_tokens':50,'completion_tokens':20}
    assert result['original_request_cost_usd'] == 0
    assert not result['full_search_cost_accounted']
    assert 'private-key' not in json.dumps(result)
    with pytest.raises(ValueError, match='different development dataset'):
        verify_advice(file, journal, dataset_sha256='0'*64)


@pytest.mark.parametrize('mutation', ['proposal','mock','status','duration'])
def test_receipt_forgery_or_invalid_origin_rejected(tmp_path, mutation):
    _, data, journal, file, receipt = origin(tmp_path)
    if mutation == 'proposal': receipt['advice']['proposal']['value'] = 1.0
    elif mutation == 'mock': receipt['advice']['provider'] = 'mock'
    elif mutation == 'status': receipt['status'] = 'failed'
    else: receipt['finished_at'] = '2026-10-15T00:00:00+00:00'
    file.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        verify_advice(file, journal, dataset_sha256=digest(data))


def test_changed_journal_cannot_authenticate_original_receipt(tmp_path):
    _, data, journal, file, _ = origin(tmp_path)
    with sqlite3.connect(journal) as db:
        db.execute("UPDATE advisor_requests SET payload_sha256=?",('0'*64,))
    with pytest.raises(ValueError, match='checksum mismatch'):
        verify_advice(file, journal, dataset_sha256=digest(data))


def test_verified_replay_rechecks_journal_and_exact_baseline(tmp_path):
    path, data, journal, file, _ = origin(tmp_path)
    provenance = verify_advice(file, journal, dataset_sha256=digest(data))
    study = freeze_study(path,[provenance['proposal']],version='linked-v1',epochs=5,verified_origins=[provenance])
    with pytest.raises(ValueError, match='requires original receipts'):
        run_study(path,study,tmp_path/'missing')
    assert not (tmp_path/'missing').exists()
    result = run_study(path,study,tmp_path/'verified',advice_paths=[file],request_journal=journal)
    assert result['suggestion_origin'] == 'verified_local_api_journal'
    assert result['preparation']['receipt_wall_seconds'] == 2
    assert not result['preparation']['full_search_cost_accounted']
    assert not result['independent_evidence']


def test_different_fit_baseline_cannot_claim_same_advice(tmp_path):
    path, data, journal, file, _ = origin(tmp_path)
    provenance=verify_advice(file,journal,dataset_sha256=digest(data))
    study=freeze_study(path,[provenance['proposal']],version='wrong-epochs',epochs=3,verified_origins=[provenance])
    with pytest.raises(ValueError,match='exact baseline diagnostics'):
        run_study(path,study,tmp_path/'wrong',advice_paths=[file],request_journal=journal)
    assert not (tmp_path/'wrong/result.json').exists()
