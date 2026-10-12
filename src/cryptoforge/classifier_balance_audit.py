"""Read-only support, preprocessing and natural-validation classifier audit."""
from datetime import datetime
from math import isclose
from cryptoforge.net_classifier import NetProfitClassifier,evaluate_net_classifier
from cryptoforge.net_training_snapshot import load_net_training_snapshot
from cryptoforge.model_training import fit_standardizer
from cryptoforge.research_evidence import verify_registered_report
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.train_window import prepare_training_window
from cryptoforge.train_window_audit import audit_train_window_study,_rows
from cryptoforge.training_snapshot import load_runtime_sources


def restore_net_classifier(saved):
    return NetProfitClassifier(**{**saved,'means':tuple(saved['means']),'stds':tuple(saved['stds']),
        'weights':tuple(saved['weights']),'class_weights':tuple(saved['class_weights']),
        'fit_information_end':datetime.fromisoformat(saved['fit_information_end']),
        'training_identities':tuple((pair,datetime.fromisoformat(stamp)) for pair,stamp in saved['training_identities'])})


def audit_classifier_balance(report,original,*,ledger_path,dependencies):
    verify_registered_report(report,ledger_path)
    audit_train_window_study(original,ledger_path=ledger_path)
    manifest=report['manifest'];base=manifest['base_config']
    if (manifest['scope']!='viewed_development_class_balance_natural_validation'
            or manifest['outer_test_evaluated'] is not False
            or manifest['original_study_sha256']!=original['study_sha256']
            or manifest['original_input_snapshot']!=original['manifest']['original_input_snapshot']):
        raise ValueError('original development classifier input mismatch')
    assert_source_dependencies(manifest['implementation_hashes'],dependencies)
    load_runtime_sources(manifest['original_runtime_sources'],manifest['implementation_hashes'])
    target=base['target_version'];snapshot=load_net_training_snapshot(manifest['original_input_snapshot'],target_version=target)
    train,validation=(_rows(snapshot['splits'][name]) for name in ('train','validation'))
    end=datetime.fromisoformat(original['manifest']['train_end']);validation_end=datetime.fromisoformat(original['manifest']['validation_end'])
    control=base['control_parameters']
    if control['half_life_days'] is not None:raise ValueError('uniform recency classifier design required')
    train=prepare_training_window(train,train_end=end,window_days=control['window_days']).rows
    means,stds=fit_standardizer([row.features for row in train]);n=len(train);positive=sum(row.label for row in train)
    if not 0<positive<n:raise ValueError('both classifier training classes required')
    seen=set()
    for result in report['results']:
        balance=result['parameters']['class_balance']
        if type(balance) is not bool or balance in seen:raise ValueError('unique boolean class-balance designs required')
        seen.add(balance);model=restore_net_classifier(result['model'])
        expected=(n/(2*(n-positive)),n/(2*positive)) if balance else (1.,1.)
        values=zip((*model.means,*model.stds,*model.class_weights,model.train_positive_rate),
                   (*means,*stds,*expected,positive/n))
        if (len(model.means)!=7 or len(model.stds)!=7 or len(model.weights)!=7
                or len(model.class_weights)!=2 or not all(isclose(a,b,rel_tol=1e-12,abs_tol=1e-12) for a,b in values)
                or model.fit_information_end!=max(row.label_end_time for row in train)
                or model.training_identities!=tuple((row.pair,row.open_time) for row in train)
                or model.live_eligible or model.probability_calibration_established):
            raise ValueError('train-only classifier support/preprocessing mismatch')
        metrics=evaluate_net_classifier(model,validation,as_of=validation_end,target_version=target)
        if metrics!=result['metrics']:raise ValueError('natural validation classifier diagnostics mismatch')
    if seen!={False,True}:raise ValueError('complete class-balance comparison required')
    return {'status':'original_classifier_validation_verified','audited_configurations':2,
        'refitting_performed':False,'optimizer_coefficients_reproduced':False,
        'evaluation_distribution':'original_unweighted_rows','probability_calibration_established':False,
        'live_promotion_allowed':False,'independent_profitability_established':False}
