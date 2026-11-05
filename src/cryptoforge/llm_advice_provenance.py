"""Read-only linkage of a completed advisor receipt to its private API journal.

This is local audit evidence, not a provider signature or a profitability claim.
No credential, full prompt or raw response is returned by the verifier.
"""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3

from cryptoforge.llm_research_contracts import strict_json, validate_proposal
from cryptoforge.research_training_diagnostics import digest, timestamp, validate_diagnostics
from cryptoforge.training_experiment_planner import read_json


def verify_advice(receipt_path, journal_path, *, dataset_sha256):
    receipt = read_json(receipt_path)
    if receipt.get('status') != 'completed' or 'advice' not in receipt:
        raise ValueError('completed real advisor receipt required')
    report = validate_diagnostics(receipt['diagnostics'])
    if report['partition'] != 'validation' or report['dataset_sha256'] != dataset_sha256:
        raise ValueError('advice report belongs to a different development dataset')
    advice = receipt['advice']
    if advice.get('provider') not in ('openrouter', 'ollama'):
        raise ValueError('mock or unrecognized advisor origin')
    key = advice.get('request_key')
    if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('journal request identity required')
    with sqlite3.connect(Path(journal_path).resolve().as_uri()+'?mode=ro', uri=True) as db:
        row = db.execute('SELECT status,request,payload,payload_sha256 FROM advisor_requests WHERE key=?', (key,)).fetchone()
    if not row or row[0] != 'completed':
        raise ValueError('request not completed in API journal')
    request, result = strict_json(row[1]), strict_json(row[2])
    if digest(request) != key or digest(result) != row[3]:
        raise ValueError('journal request or response checksum mismatch')
    observed = {k: v for k, v in advice.items() if k not in ('api_cached', 'request_key')}
    if digest(observed) != digest(result):
        raise ValueError('advisor receipt differs from API journal')
    if (digest(request['report']) != digest(report) or result['report_sha256'] != digest(report)
            or result['provider'] != request['provider'] or result['requested_model'] != request['model']):
        raise ValueError('request, report or model linkage mismatch')
    validate_proposal(result['proposal'], report)
    if result['proposal']['parameter'] not in request['parameters']:
        raise ValueError('proposal outside recorded request catalog')
    if result['provider'] == 'openrouter':
        price = result['price_receipt']
        if price['model'] != request['model'] or not price['model'].endswith(':free'):
            raise ValueError('recorded fixed free model required')
        try:
            prices = [Decimal(str(v)) for v in price['pricing'].values()]
            if not {'prompt', 'completion'} <= price['pricing'].keys() or not all(x.is_finite() and x == 0 for x in prices):
                raise ValueError('recorded model prices not zero')
        except (InvalidOperation, TypeError):
            raise ValueError('invalid recorded model pricing') from None
    start, end = timestamp(receipt['started_at']), timestamp(receipt['finished_at'])
    if end < start:
        raise ValueError('negative preparation duration')
    usage = result.get('usage', {})
    if not isinstance(usage, dict) or any(type(v) is not int or v < 0 for v in usage.values()):
        raise ValueError('invalid recorded token usage')
    return {'schema_version': 'verified-advice-origin-v1', 'request_key': key,
        'receipt_sha256': digest(receipt), 'response_sha256': digest(result),
        'report_sha256': digest(report), 'dataset_sha256': dataset_sha256,
        'provider': result['provider'], 'model': result['model'], 'usage': usage,
        'preparation_wall_seconds': (end-start).total_seconds(),
        'current_receipt_cached': advice['api_cached'],
        'original_request_cost_usd': 0.0 if result['provider'] == 'openrouter' else None,
        'cost_basis': 'recorded_zero_api_pricing_not_billing_audit',
        'full_search_cost_accounted': False, 'proposal': result['proposal']}
