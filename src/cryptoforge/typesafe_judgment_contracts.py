"""Research-only semantic contracts; no SDK imports, credentials or live calls."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import math
import re
from cryptoforge.research_training_diagnostics import exact_fields, number, digest, canonical


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', value):
        raise ValueError('bounded semantic identifier required')


def text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 4000:
        raise ValueError('bounded semantic text required')


def validate_catalog(catalog):
    if len(canonical(catalog).encode()) > 64_000:
        raise ValueError('semantic question catalog too large')
    exact_fields(catalog, {'schema_version', 'policy_version', 'questions'})
    if catalog['schema_version'] != 'semantic-research-questions-v1':
        raise ValueError('unsupported semantic catalog')
    text(catalog['policy_version'])
    questions = catalog['questions']
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 16:
        raise ValueError('one to sixteen questions required')
    for name, question in questions.items():
        identifier(name)
        if not isinstance(question, dict):
            raise ValueError('question object required')
        kind = question.get('type')
        extra = {'accept_below', 'accept_above'} if kind == 'noul' else {'minimum_confidence'}
        exact_fields(question, {'type', 'instructions', 'criteria'} | extra)
        text(question['instructions'])
        criteria = question['criteria']
        if kind == 'noul':
            exact_fields(criteria, {'true', 'false'})
            for value in criteria.values(): text(value)
            lo, hi = number(question['accept_below'], 0, 1), number(question['accept_above'], 0, 1)
            if not lo < 0.5 < hi:
                raise ValueError('explicit uncertainty interval required')
        elif kind == 'choice':
            if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 16 or 'unknown' not in criteria:
                raise ValueError('bounded choice including unknown required')
            for key, value in criteria.items():
                identifier(key)
                text(value)
            number(question['minimum_confidence'], 0, 1)
        elif kind == 'score':
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
                raise ValueError('ordered score criteria required')
            for value in criteria: text(value)
            number(question['minimum_confidence'], 0, 1)
        else:
            raise ValueError('unsupported judgment primitive')
    return catalog


def distribution(raw, keys):
    exact_fields(raw, set(keys))
    values = {k: number(v, 0, 1) for k, v in raw.items()}
    if not math.isclose(sum(values.values()), 1, abs_tol=1e-6):
        raise ValueError('probabilities must sum to one')
    return values


def normalize_answer(question, answer):
    kind = question['type']
    if kind == 'noul':
        exact_fields(answer, {'type', 'noul'})
        if answer['type'] != kind:
            raise ValueError('primitive mismatch')
        p = number(answer['noul'], 0, 1)
        decision = 'yes' if p >= question['accept_above'] else 'no' if p <= question['accept_below'] else None
        return {'status': 'available' if decision else 'abstain', 'type': kind,
                'probability': p, 'decision': decision}
    value_key = 'choice' if kind == 'choice' else 'score'
    exact_fields(answer, {'type', value_key, 'confidence', 'probabilities'})
    if answer['type'] != kind:
        raise ValueError('primitive mismatch')
    confidence = number(answer['confidence'], 0, 1)
    keys = question['criteria'].keys() if kind == 'choice' else [str(i) for i in range(len(question['criteria']))]
    probabilities = distribution(answer['probabilities'], keys)
    value = answer[value_key]
    if kind == 'choice':
        if not isinstance(value, str) or value not in probabilities or probabilities[value] < max(probabilities.values())-1e-6:
            raise ValueError('choice inconsistent with distribution')
    else:
        value = number(value, 0, len(question['criteria'])-1)
        if not math.isclose(value, sum(int(k)*p for k,p in probabilities.items()), abs_tol=1e-6):
            raise ValueError('score inconsistent with distribution')
    available = confidence >= question['minimum_confidence'] and value != 'unknown'
    return {'status': 'available' if available else 'abstain', 'type': kind,
            'value': value, 'confidence': confidence, 'probabilities': probabilities}


def evaluate_mock(state, catalog, response):
    validate_catalog(catalog)
    if len(canonical(state).encode()) > 32_000 or len(canonical(response).encode()) > 64_000:
        raise ValueError('semantic state or mock response too large')
    exact_fields(response, {'answers'})
    if not isinstance(response['answers'], dict) or set(response['answers'])-set(catalog['questions']):
        raise ValueError('unknown answer question')
    answers = {}
    for name, question in catalog['questions'].items():
        try:
            answers[name] = normalize_answer(question, response['answers'][name])
        except (ValueError, KeyError, TypeError):
            answers[name] = {'status': 'error', 'type': question['type'], 'error': 'invalid_or_missing_answer'}
    return {'schema_version': 'semantic-research-judgments-v2',
            'normalizer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'origin': 'mock',
            'model_revision': 'fixture-'+digest(response), 'state_sha256': digest(state),
            'question_catalog_sha256': digest(catalog), 'question_snapshot': deepcopy(catalog),
            'evaluated_at': datetime.now(timezone.utc).isoformat(), 'policy_version': catalog['policy_version'],
            'answers': answers, 'calibrated_policy': False, 'api_calls': 0}
