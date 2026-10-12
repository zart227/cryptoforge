from pathlib import Path
import pytest
from cryptoforge.net_training_snapshot import save_net_training_snapshot, load_net_training_snapshot
from test_net_regression import examples

TARGET='spot-long-trade-net-v2'


def save(tmp_path):
    return save_net_training_snapshot(tmp_path,train=examples(),validation=examples(),
                                      target_version=TARGET,metadata={})


def test_original_net_rows_are_private_and_content_addressed(tmp_path):
    reference=save(tmp_path)
    payload=load_net_training_snapshot(reference,target_version=TARGET)
    assert payload['splits']['train'][0]['future_return']==-.04
    assert payload['target_version']==TARGET
    assert not payload['counts_as_real_executed_buys']
    assert not payload['outer_test_included']
    assert Path(reference['path']).stat().st_mode & 0o777 == 0o600
    assert reference==save(tmp_path)


def test_changed_counts_corruption_and_price_contract_fail(tmp_path):
    reference=save(tmp_path)
    with pytest.raises(ValueError,match='contract'):
        load_net_training_snapshot({**reference,'split_counts':{}},target_version=TARGET)
    with pytest.raises(ValueError,match='explicit target'):
        load_net_training_snapshot(reference,target_version='fixed-future-return-v1')
    path=Path(reference['path']);path.write_bytes(path.read_bytes()+b'corrupt')
    with pytest.raises((ValueError,OSError,EOFError)):
        load_net_training_snapshot(reference,target_version=TARGET)
