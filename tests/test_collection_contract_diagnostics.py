from cryptoforge.collection_contract_diagnostics import describe_collection_contract


def row(order,state='legacy_asof_snapshot',contract=None):
    result={'pair':'ETH/USDT','entry_order':order,'input_candle_state':state}
    if contract is not None:result['feature_input_contract']=contract
    return result


def test_closed_primary_does_not_turn_eight_legacy_buys_into_compatible_examples():
    rows=[row(str(i)) for i in range(8)]
    result=describe_collection_contract({'input_candle_state':'legacy_asof_snapshot'},rows,
        primary_input={'input_candle_state':'closed_only','lookback_candles':120})
    assert result['status']=='separate_frozen_input_contract_study_required'
    assert result['distinct_buys']==8 and result['observed_buys_by_original_window']=={'unknown_original_window':8}
    assert not result['frozen_protocol_changed'] and not result['changes_readiness_gates']


def test_same_state_does_not_certify_an_unknown_original_window_or_count_versions_twice():
    result=describe_collection_contract({'input_candle_state':'closed_only'},[row('1','closed_only')]*2,
        primary_input={'input_candle_state':'closed_only','lookback_candles':120})
    assert result['distinct_buys']==1 and result['status']=='input_state_matches_exact_window_not_preregistered'
    assert not result['sample_growth_guaranteed']


def test_explicit_contract_requires_exact_match_not_just_closed_state():
    contract={'input_candle_state':'closed_only','lookback_candles':120}
    protocol={'input_candle_state':'closed_only','feature_input_contract':contract}
    assert describe_collection_contract(protocol,[],primary_input=contract)['status']=='declared_input_contract_matches'
    assert describe_collection_contract(protocol,[],primary_input={**contract,'lookback_candles':36})['status']=='separate_frozen_input_contract_study_required'
