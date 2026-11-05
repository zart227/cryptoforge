"""Numerical primitive for one admitted batch, with ephemeral fit reuse only.

No CLI, subprocess, journal, persistent cache or admission authority. The caller
must reserve every logical evaluation before any model work. Tests supply only
synthetic data/admission callbacks; no operational study uses this primitive yet.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from cryptoforge import research_fit_graph as graph
from cryptoforge import training_experiment_planner as planner
from cryptoforge.llm_research_contracts import CATALOG
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, number

POLICY = {'schema_version':'ephemeral-training-fit-reuse-v1','maximum_logical_evaluations':7,
    'maximum_physical_fit_feature_operations':14000000,'cache_lifetime':'one_function_call',
    'target':'existing_isolated_long_head_only','all_logical_admissions_before_any_fit':True,
    'persistent_cache_or_ledger_writes':False,'admission_or_new_allowance_granted':False,
    'main_primary_multihead_trainer_integrated':False}


def implementation():
    return {'primitive':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reviewed_graph':graph.implementation(),'planner':planner.implementation_hashes()}


_LOADED=implementation();_POLICY=canonical(POLICY)


def _guard():
    if implementation()!=_LOADED or canonical(POLICY)!=_POLICY:raise ValueError('fit_reuse_implementation_changed')
    graph.review_contract()


def _configurations(configurations):
    if type(configurations) is not list or not 1<=len(configurations)<=7:raise ValueError('bounded_logical_configurations_required')
    allowed=[dict(planner.BASELINE)]
    for name in ('l2','threshold'):
        allowed.extend({**planner.BASELINE,name:float(value)} for value in CATALOG[name] if value!=planner.BASELINE[name])
    keys={digest(v) for v in allowed};result=[]
    for value in configurations:
        exact_fields(value,{'l2','threshold'})
        config={k:number(v,0,1) for k,v in value.items()}
        if digest(config) not in keys:raise ValueError('baseline_or_single_parameter_catalog_change_required')
        result.append(config)
    if len({digest(v) for v in result})!=len(result):raise ValueError('unique_logical_configurations_required')
    return result


def _evidence(value):
    exact_fields(value,{'schema_version','raw_source_manifest_sha256','source_revision_manifest_sha256',
        'exposure_inventory_sha256','execution_protocol_sha256'})
    if value['schema_version']!='fit-reuse-evidence-context-v1':raise ValueError('explicit_evidence_context_required')
    if any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v)
           for k,v in value.items() if k!='schema_version'):raise ValueError('exact_evidence_digest_required')
    return deepcopy(value)


def plan(data,protocol,configurations,*,evidence_context):
    """Validate computational identity without fitting, predicting or admitting."""
    _guard();data=deepcopy(data);protocol=deepcopy(protocol)
    data,splits=planner.parse_development(data);planner.validate_protocol(protocol,data,splits)
    configs=_configurations(configurations);evidence=_evidence(evidence_context)
    context={'schema_version':'fit-reuse-computational-context-v1','dataset_sha256':digest(data),
        'protocol_sha256':digest(protocol),'implementation':deepcopy(_LOADED),'evidence_context':evidence,
        'target_version':data['target_version'],'feature_version':data['feature_version'],
        'feature_names':data['feature_names'],'fit_label':'label','epochs':protocol['epochs'],
        'learning_rate':protocol['learning_rate'],'training_rows':len(splits['train']),
        'validation_rows':len(splits['validation'])}
    identity=digest(context);evaluations=[]
    for index,config in enumerate(configs):
        fit_key=digest(['long-head-fit-and-probabilities',identity,config['l2']])
        evaluations.append({'index':index,'configuration':config,'fit_key':fit_key,
            'prediction_key':digest(['train-validation-probabilities',fit_key,context['dataset_sha256']]),
            'logical_evaluation_key':digest(['logical-evaluation',identity,config]),
            'logical_charge_required':True})
    n=len(configs);fits=len({e['fit_key'] for e in evaluations});train=len(splits['train']);total=train+len(splits['validation'])
    operations=fits*train*protocol['epochs']*len(planner.model_training.FEATURE_NAMES)
    if operations>POLICY['maximum_physical_fit_feature_operations']:raise ValueError('bounded_physical_batch_operations_required')
    return {'schema_version':'fit-reuse-batch-plan-v1','context':context,'context_sha256':identity,
        'standardizer_key':digest(['train-only-standardizer',identity]),
        'evaluations':evaluations,'counts':{'logical_evaluations':n,'standardizer_fits':1,'long_head_fits':fits,
            'probability_evaluations':fits*total,'optimizer_training_row_presentations':fits*train*protocol['epochs'],
            'optimizer_feature_operations':operations,'diagnostic_reports':2*n},
        'evidence_digests_verified_against_original_sources':False,'study_or_budget_approved':False}


def evaluate_admitted_batch(data,protocol,configurations,*,evidence_context,admit):
    """Caller-owned admission must succeed for all configs before any fit.

    This callback seam is not a security or authorization boundary. A future
    fixed budget adapter must verify actual original manifests/protocol/history;
    merely supplying hashes/callbacks does not approve a study or raise a cap.
    """
    if not callable(admit):raise ValueError('explicit_logical_admission_callback_required')
    data=deepcopy(data);protocol=deepcopy(protocol)
    batch=plan(data,protocol,configurations,evidence_context=evidence_context)
    data,splits=planner.parse_development(data)
    for evaluation in batch['evaluations']:
        supplied=admit(deepcopy(evaluation),batch['context_sha256'])
        if supplied is not None:raise ValueError('admission_callback_must_return_none_or_raise')
        _guard()
    train=splits['train'];model=planner.model_training
    means,stds=model.fit_standardizer([row.features for row in train])
    fitted={};results=[]
    actual={'logical_evaluations':len(batch['evaluations']),'standardizer_fits':1,'long_head_fits':0,
        'probability_evaluations':0,'optimizer_training_row_presentations':0,'optimizer_feature_operations':0,'diagnostic_reports':0}
    for evaluation in batch['evaluations']:
        config=evaluation['configuration'];key=evaluation['fit_key']
        if key not in fitted:
            weights,bias=model.fit_logistic_head(train,means,stds,learning_rate=protocol['learning_rate'],
                epochs=protocol['epochs'],label_attr='label',l2=config['l2'])
            predictions={}
            for name,rows in splits.items():
                predictions[name]=[{'pair':r.pair,'open_time':r.open_time.isoformat(),
                    'label_end_time':r.label_end_time.isoformat(),'label':r.label,
                    'probability':model.predict_probability(r.features,weights,bias,means,stds)} for r in rows]
                actual['probability_evaluations']+=len(rows)
            fitted[key]=(weights,bias,predictions);actual['long_head_fits']+=1
            actual['optimizer_training_row_presentations']+=len(train)*protocol['epochs']
            actual['optimizer_feature_operations']+=len(train)*protocol['epochs']*len(model.FEATURE_NAMES)
        weights,bias,predictions=fitted[key];reports={}
        for name,rows in predictions.items():
            diagnostics=planner.build_diagnostics({'partition':name,'dataset_sha256':protocol['dataset_sha256'],
                'source_sha256':digest(protocol['implementation_hashes']),'development_end':protocol['development_end'],
                'rows':rows},threshold=config['threshold'])
            selected=[r for r in rows if r['probability']>=config['threshold']]
            reports[name]={'diagnostics':diagnostics,'selected_observations':len(selected),
                'selected_positive_rate':sum(r['label'] for r in selected)/len(selected) if selected else None}
            actual['diagnostic_reports']+=1
        artifact={'schema_version':'offline-long-head-v1','family':model.MODEL_FAMILY,
            'target_version':'fixed-future-return-v1','feature_version':model.FEATURE_VERSION,
            'feature_names':list(model.FEATURE_NAMES),'weights':weights,'bias':bias,'means':means,'stds':stds,
            'config':config,'fit_information_end':protocol['development_end'],'production_compatible':False}
        # Separate copies prevent mutation of one threshold artifact affecting
        # another result that shared the same fitted numerical dependency.
        results.append(deepcopy({'artifact':artifact,'artifact_sha256':digest(artifact),'reports':reports}))
    _guard()
    if actual!=batch['counts']:raise ValueError('physical_operation_count_mismatch')
    bindings=[{'logical_evaluation_key':e['logical_evaluation_key'],'context_sha256':batch['context_sha256'],
        'fit_key':e['fit_key'],'prediction_key':e['prediction_key'],'artifact_sha256':r['artifact_sha256'],
        'reports_sha256':digest(r['reports'])} for e,r in zip(batch['evaluations'],results,strict=True)]
    result={'schema_version':'fit-reuse-batch-result-v1','plan':batch,'results':results,'result_bindings':bindings,'actual_counts':actual,
        'persistent_model_cache_reused':False,'logical_evaluation_charges_reduced':False,
        'external_budgets_or_approval_attested':False,'production_compatible':False}
    return {**result,'batch_sha256':digest(result)}
