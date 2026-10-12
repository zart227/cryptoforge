from dataclasses import replace
import gzip,json
from pathlib import Path
import pytest
from cryptoforge.training_snapshot import save_training_snapshot,load_training_snapshot
from cryptoforge.model_training import build_examples,chronological_splits
from test_model_training import make_training_candles


def fixture():
    examples=build_examples('ETH/USDT',make_training_candles(160),horizon_candles=3)
    train,validation,test=chronological_splits(examples)
    return {'train':train,'validation':validation,'test':test}


def test_exact_examples_survive_cache_changes_and_keep_private_content_address(tmp_path):
    splits=fixture();reference=save_training_snapshot(tmp_path,splits=splits,metadata={'source_sha':'a'*64})
    payload=load_training_snapshot(reference)
    original=payload['splits']['train'][0]['features']
    splits['train'][0]=replace(splits['train'][0],features=(0.,)*7)
    assert load_training_snapshot(reference)['splits']['train'][0]['features']==original
    assert not payload['counts_as_real_executed_buys']
    assert payload['target_version']=='fixed-future-return-v1'
    assert Path(reference['path']).stat().st_mode & 0o777 == 0o600
    assert save_training_snapshot(tmp_path,splits=fixture(),metadata={'source_sha':'a'*64})==reference


def test_corruption_and_changed_counts_cannot_be_read_as_original_inputs(tmp_path):
    reference=save_training_snapshot(tmp_path,splits=fixture(),metadata={})
    with pytest.raises(ValueError,match='counts'):
        load_training_snapshot({**reference,'split_counts':{'train':1,'validation':1,'test':1}})
    path=Path(reference['path']);payload=load_training_snapshot(reference)
    payload['splits']['test'][0]['future_return']=.9
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    with pytest.raises(ValueError,match='checksum'):load_training_snapshot(reference)


def test_invalid_sizes_and_nonfinite_examples_do_not_create_usable_snapshots(tmp_path):
    splits=fixture();splits['train'][0]=replace(splits['train'][0],future_return=float('nan'))
    with pytest.raises(ValueError):save_training_snapshot(tmp_path,splits=splits,metadata={})
    assert not list(tmp_path.glob('*.gz'))
    with pytest.raises(ValueError,match='bounded'):
        load_training_snapshot({'schema_version':'primary-training-input-snapshot-v1','compression':'gzip','uncompressed_bytes':2**40})


def test_runtime_source_copies_are_verified_and_never_executed(tmp_path):
    from cryptoforge.source_contract import primary_training_sources,source_hashes
    from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources
    functions=primary_training_sources();hashes=source_hashes(functions)
    reference=save_runtime_sources(tmp_path,functions,hashes)
    payload=load_runtime_sources(reference,hashes)
    assert not payload['automatically_execute_archived_code']
    assert payload['sources']['primary_training']['sha256']==hashes['primary_training']
    with pytest.raises(ValueError,match='fitted implementation'):
        load_runtime_sources(reference,{**hashes,'primary_training':'0'*64})
