from dataclasses import asdict,replace
from datetime import timedelta
from copy import deepcopy
import pytest
from cryptoforge.classifier_balance_audit import audit_classifier_balance
from cryptoforge.net_classifier import fit_net_classifier,evaluate_net_classifier
from cryptoforge.research_attempts import identity
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.train_window_study import run_train_window_study
from test_train_window_study import examples,options,END
from scripts.evaluate_classifier_balance import dependencies


def fixture(tmp_path):
    kwargs=options(tmp_path);train,validation=examples()
    train=[replace(row,future_return=-.01,label=0) if i<2 else row for i,row in enumerate(train)]
    original=run_train_window_study(train,validation,**kwargs)
    grid=[{'family':'net-class-balance','class_balance':balance} for balance in (False,True)]
    hashes=source_hashes(dependencies())
    runtime=save_runtime_sources(tmp_path/'runtime',dependencies(),hashes)
    manifest={'grid':grid,'base_config':{'target_version':'spot-long-trade-net-v2',
        'control_parameters':original['results'][0]['parameters']},'implementation_hashes':hashes,
        'original_study_sha256':original['study_sha256'],'original_input_snapshot':original['manifest']['original_input_snapshot'],
        'original_runtime_sources':runtime,'scope':'viewed_development_class_balance_natural_validation',
        'outer_test_evaluated':False}
    ledger=kwargs['ledger'];study=ledger.register(manifest,protocol_id='classifier-audit-fixture',maximum_per_family=2)
    results=[]
    for candidate in grid:
        model=fit_net_classifier(train,target_version='spot-long-trade-net-v2',as_of=END,
            class_balance=candidate['class_balance'],epochs=3)
        metrics=evaluate_net_classifier(model,validation,as_of=END+timedelta(days=1),target_version=model.target_version)
        result={'parameters':candidate,'model':asdict(model),'metrics':metrics}
        ledger.record(study,candidate,result);results.append(ledger.result(study,candidate))
    return {'manifest':manifest,'study_sha256':study,'results':results},original,ledger.path


def test_original_training_support_and_natural_validation_replay(tmp_path):
    report,original,path=fixture(tmp_path);before=path.read_bytes()
    result=audit_classifier_balance(report,original,ledger_path=path,dependencies=dependencies())
    assert result['audited_configurations']==2
    assert not result['refitting_performed'] and not result['optimizer_coefficients_reproduced']
    assert path.read_bytes()==before


def test_changed_validation_distribution_is_rejected_by_ledger(tmp_path):
    report,original,path=fixture(tmp_path);report=deepcopy(report)
    report['results'][0]['metrics']['count']+=100
    with pytest.raises(ValueError,match='immutable completed'):
        audit_classifier_balance(report,original,ledger_path=path,dependencies=dependencies())
