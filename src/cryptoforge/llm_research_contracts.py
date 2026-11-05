"""Parameter proposals only: validation never executes or promotes a model."""
import json
import re
from cryptoforge.research_training_diagnostics import exact_fields, number, validate_diagnostics

PROPOSAL_VERSION = 'llm-training-proposal-v1'
# A bounded starting search space; these are proposals, not production defaults.
CATALOG = {'l2': [0.0, 0.01, 0.1, 1.0], 'threshold': [0.55, 0.6, 0.65, 0.7],
           'lookback_candles': [500, 1000, 2000]}
FIELDS = {'schema_version', 'hypothesis_id', 'evidence_ids', 'rationale',
          'expected_effect', 'falsification', 'parameter', 'value'}


def strict_json(raw, *, max_bytes=64_000):
    if not isinstance(raw, str) or len(raw.encode()) > max_bytes:
        raise ValueError('bounded JSON text required')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite JSON number')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (json.JSONDecodeError, RecursionError):
        raise ValueError('invalid JSON response') from None


def validate_proposal(value, report):
    validate_diagnostics(report)
    return validate_proposal_shape(value, evidence_ids=set(report['evidence']))


def validate_proposal_shape(value, *, evidence_ids):
    """Schema/catalog checks only; does not establish report provenance."""
    exact_fields(value, FIELDS)
    if value['schema_version'] != PROPOSAL_VERSION:
        raise ValueError('unsupported proposal version')
    if not isinstance(value['hypothesis_id'], str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', value['hypothesis_id']):
        raise ValueError('invalid hypothesis identifier')
    ids = value['evidence_ids']
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or any(not isinstance(i, str) for i in ids):
        raise ValueError('bounded evidence references required')
    if len(ids) != len(set(ids)) or any(i not in evidence_ids for i in ids):
        raise ValueError('unknown or duplicate evidence reference')
    for field in ('rationale', 'expected_effect', 'falsification'):
        text = value[field]
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError('bounded explanation required')
    parameter = value['parameter']
    if not isinstance(parameter, str) or parameter not in CATALOG:
        raise ValueError('parameter outside catalog')
    number(value['value'], 0, 2000)
    if value['value'] not in CATALOG[parameter]:
        raise ValueError('value outside catalog')
    if parameter == 'lookback_candles' and type(value['value']) is not int:
        raise ValueError('integer history required')
    return value
