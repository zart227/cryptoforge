import pytest
from cryptoforge.paper_runtime import paper_runtime_hashes,verify_paper_runtime


def test_paper_freeze_binds_all_current_execution_sources():
    hashes=paper_runtime_hashes()
    assert {'worker','wallet','market','activation','exit_rules','shared_exit_indicator','candle_contract','results_exporter','acceptance_evaluator','worker_runner','export_runner','evaluation_runner'}<=set(hashes)
    verify_paper_runtime({'implementation_hashes':hashes})


def test_missing_or_changed_execution_source_cannot_use_old_policy():
    with pytest.raises(ValueError,match='runtime differs'):verify_paper_runtime({})
    hashes=paper_runtime_hashes();hashes['exit_rules']='0'*64
    with pytest.raises(ValueError,match='runtime differs'):verify_paper_runtime({'implementation_hashes':hashes})


def test_saved_execution_source_bundle_is_checksum_verified(tmp_path):
    from cryptoforge.paper_runtime import paper_runtime_sources
    from cryptoforge.training_snapshot import save_runtime_sources
    hashes=paper_runtime_hashes()
    reference=save_runtime_sources(tmp_path,paper_runtime_sources(),hashes)
    verify_paper_runtime({'implementation_hashes':hashes,'runtime_source_bundle':reference})
    reference={**reference,'sha256':'0'*64}
    with pytest.raises(ValueError,match='checksum'):
        verify_paper_runtime({'implementation_hashes':hashes,'runtime_source_bundle':reference})
