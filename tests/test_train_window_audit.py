from copy import deepcopy
import json
import pytest
from cryptoforge.train_window_audit import audit_train_window_study
from cryptoforge.train_window_study import run_train_window_study
from test_train_window_study import examples,options


def test_original_saved_window_models_are_verified_without_refitting(tmp_path):
    kwargs=options(tmp_path)
    report=run_train_window_study(*examples(),**kwargs)
    before=kwargs['ledger'].path.read_bytes()
    audit=audit_train_window_study(report,ledger_path=kwargs['ledger'].path)
    assert audit['audited_configurations']==2
    assert not audit['refitting_performed'] and not audit['archived_code_executed']
    assert audit['ledger_authenticity_verified']
    assert kwargs['ledger'].path.read_bytes()==before


@pytest.mark.parametrize('field', ['weights','means','bias'])
def test_changed_model_coefficients_and_preprocessing_fail(tmp_path,field):
    report=deepcopy(run_train_window_study(*examples(),**options(tmp_path)))
    model=report['results'][0]['model']
    if field=='bias':model[field]+=.1
    else:model[field][0]+=.1
    with pytest.raises(ValueError,match='numerical mismatch'):
        audit_train_window_study(report)


def test_altered_report_fails_registered_verification_before_numeric_replay(tmp_path):
    kwargs=options(tmp_path)
    report=deepcopy(run_train_window_study(*examples(),**kwargs))
    report['results'][0]['model']['bias']+=.1
    with pytest.raises(ValueError,match='immutable completed'):
        audit_train_window_study(report,ledger_path=kwargs['ledger'].path)


def test_audit_command_verifies_report_and_ledger_end_to_end(tmp_path,capsys):
    from scripts.audit_train_windows import main
    kwargs=options(tmp_path)
    report=run_train_window_study(*examples(),**kwargs)
    path=tmp_path/'report.json';path.write_text(json.dumps(report))
    assert main(['--report',str(path),'--ledger',str(kwargs['ledger'].path)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['ledger_authenticity_verified']
    assert not result['refitting_performed']
