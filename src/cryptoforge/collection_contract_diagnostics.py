"""Explain collection compatibility without changing a frozen study or its gates."""
from collections import Counter
import json
from cryptoforge.live_learning_protocol import buy_key


def describe_collection_contract(protocol,rows,*,primary_input=None):
    seen=set();states=Counter();windows=Counter()
    for row in rows:
        key=buy_key(row)
        if key in seen:continue
        seen.add(key);states[row.get('input_candle_state','unknown')]+=1
        contract=row.get('feature_input_contract')
        windows[json.dumps(contract,sort_keys=True) if contract is not None else 'unknown_original_window']+=1
    expected=protocol.get('feature_input_contract')
    if primary_input is None:status='primary_input_configuration_unknown'
    elif primary_input.get('input_candle_state')!=protocol['input_candle_state']:
        status='separate_frozen_input_contract_study_required'
    elif expected is not None and primary_input!=expected:
        status='separate_frozen_input_contract_study_required'
    elif expected is None:status='input_state_matches_exact_window_not_preregistered'
    else:status='declared_input_contract_matches'
    return {'status':status,'expected_input_candle_state':protocol['input_candle_state'],
        'expected_feature_input_contract':expected,'distinct_buys':len(seen),
        'observed_buys_by_state':dict(states),'observed_buys_by_original_window':dict(windows),
        'latest_saved_primary_input':primary_input,
        'primary_scope':'local_saved_configuration_not_live_registry_or_future_buy_guarantee',
        'frozen_protocol_changed':False,'different_contracts_merged':False,
        'sample_growth_guaranteed':False,'changes_readiness_gates':False}
