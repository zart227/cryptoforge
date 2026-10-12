from copy import deepcopy
import sqlite3
import pytest
from cryptoforge.ablation_audit import audit_ablation_study
from cryptoforge.ablation_study import run_registered_ablation
from test_ablation_study import setup
from cryptoforge.research_attempts import encoded,identity


def test_frozen_ablation_models_are_replayed_without_refit(tmp_path):
    original,kwargs=setup(tmp_path);report=run_registered_ablation(original,**kwargs)
    before=kwargs['ledger'].path.read_bytes()
    audit=audit_ablation_study(report,original,ledger_path=kwargs['ledger'].path)
    assert audit['audited_configurations']==2
    assert not audit['refitting_performed']
    assert kwargs['ledger'].path.read_bytes()==before


@pytest.mark.parametrize('field',['removed_indices','metrics'])
def test_tampered_mask_or_metrics_are_rejected_by_immutable_ledger(tmp_path,field):
    original,kwargs=setup(tmp_path);report=deepcopy(run_registered_ablation(original,**kwargs))
    if field=='removed_indices':report['results'][0]['model'][field]=[1]
    else:report['results'][0][field]['rmse']+=.1
    with pytest.raises(ValueError,match='immutable completed'):
        audit_ablation_study(report,original,ledger_path=kwargs['ledger'].path)


def test_numerical_audit_detects_faulty_recorded_weight_even_when_mask_hides_it(tmp_path):
    original,kwargs=setup(tmp_path);report=deepcopy(run_registered_ablation(original,**kwargs))
    # Simulate a faulty producer in an isolated fixture DB: output predictions
    # do not change because this coefficient belongs to the removed feature.
    result=report['results'][0];result['model']['fitted']['weights'][0]=.25
    with sqlite3.connect(kwargs['ledger'].path) as db:
        db.execute('UPDATE attempts SET payload=? WHERE study=? AND configuration=?',
                   (encoded(result),report['study_sha256'],identity(result['parameters'])))
    with pytest.raises(ValueError,match='numerical mismatch'):
        audit_ablation_study(report,original,ledger_path=kwargs['ledger'].path)
