"""Recover original exit reasons from log lines matched to saved exchange orders."""
import ast
from datetime import UTC, datetime
import hashlib
import re


LINE = re.compile(r'^decision=approve_exit pair=(\S+) reasons=(.*?) order=(\{.*\})$')


def recover_exit_line(line, exchange_order, *, source, line_number):
    if len(line) > 1_000_000:
        raise ValueError('bounded log line required')
    match = LINE.fullmatch(line.rstrip('\r\n'))
    if not match:
        raise ValueError('original approve_exit log line required')
    pair, reasons, raw_order = match.groups()
    response = ast.literal_eval(raw_order)
    if not isinstance(response, dict) or not isinstance(response.get('result'), dict):
        raise ValueError('successful exchange acknowledgment required')
    result = response['result']
    if (response.get('retCode') != 0 or not result.get('orderId')
            or result['orderId'] != exchange_order.get('orderId')
            or result.get('orderLinkId') != exchange_order.get('orderLinkId')
            or exchange_order.get('symbol') != pair.replace('/', '')
            or exchange_order.get('side') != 'Sell'):
        raise ValueError('log does not match exact exchange sell order')
    stamp = response.get('time')
    if type(stamp) is not int or stamp <= 0:
        raise ValueError('exchange response timestamp required')
    if not reasons:
        raise ValueError('nonempty original exit reasons required')
    return {'pair':pair, 'decision':'approve_exit', 'mode':'live',
        'decided_at':datetime.fromtimestamp(stamp/1000, UTC).isoformat(),
        'reasons':reasons.split('; '),
        'features':{'order':response,
            'decision_context_provenance':'original_executor_stdout_exact_exchange_order',
            'decided_at_source':'exchange_ack_time_proxy_original_decision_timestamp_unavailable',
            'feature_capture_status':'missing_original_feature_snapshot',
            'source_log':source, 'source_line':line_number,
            'source_line_sha256':hashlib.sha256(line.encode()).hexdigest()},
        'idempotency_key':f"executor:live:{pair}:order:{result['orderId']}"}
