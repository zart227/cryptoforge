import pytest
from cryptoforge.execution_log_recovery import recover_exit_line


ORDER=dict(orderId='123',orderLinkId='cf-original',symbol='PONSUSDT',side='Sell')
LINE="decision=approve_exit pair=PONS/USDT reasons=exit_trend_down=True; stop_loss=True order={'retCode': 0, 'result': {'orderId': '123', 'orderLinkId': 'cf-original'}, 'time': 1791393446899}\n"


def test_recovers_logged_reasons_and_labels_missing_feature_timestamp():
    row=recover_exit_line(LINE,ORDER,source='saved.log',line_number=42)
    assert row['reasons']==['exit_trend_down=True','stop_loss=True']
    assert row['features']['source_line']==42
    assert row['features']['feature_capture_status']=='missing_original_feature_snapshot'
    assert 'proxy' in row['features']['decided_at_source']
    assert row['features']['order']['result']['orderId']=='123'


@pytest.mark.parametrize('change',[dict(orderId='456'),dict(orderLinkId='cf-other'),dict(symbol='ETHUSDT'),dict(side='Buy')])
def test_foreign_order_never_recovers_by_timestamp_or_pair_alone(change):
    with pytest.raises(ValueError):recover_exit_line(LINE,{**ORDER,**change},source='log',line_number=1)


def test_log_input_is_not_executable():
    malicious="decision=approve_exit pair=PONS/USDT reasons=stop_loss=True order={'result': __import__('os').system('false')}"
    with pytest.raises((ValueError,SyntaxError)):
        recover_exit_line(malicious,ORDER,source='log',line_number=1)
