import copy
import json
from pathlib import Path

import pytest

from cryptoforge.semantic_annotation_benchmark import freeze_benchmark, evaluate_benchmark, public_view, main
from cryptoforge.training_diagnostics import digest
from cryptoforge.typesafe_judgment_contracts import evaluate_mock


def inputs():
    catalog={'schema_version':'semantic-research-questions-v1','policy_version':'fixture-policy-v1',
        'questions':{'supported':{'type':'noul','instructions':'Does the evidence support the claim?',
             'criteria':{'true':'Supported','false':'Unsupported'},'accept_below':0.2,'accept_above':0.8}}}
    states=[{'experiment':{'fixture_id':i}} for i in range(8)]
    gold={'schema_version':'semantic-gold-v1','label_origin':'synthetic_fixture', 'examples':[
        {'record_id':digest({'record':i}),'group_id':digest({'group':i//2}),
         'state_sha256':digest(state),'labels':{'supported':'yes' if i%2==0 else 'no'}}
        for i,state in enumerate(states)]}
    return catalog, gold, {e['record_id']:s for e,s in zip(gold['examples'],states)}


def predictions(plan,states,partition='annotation_holdout', probability=0.9):
    return {record:evaluate_mock(states[record],plan['catalog'],{'answers':{
        'supported':{'type':'noul','noul':probability}}}) for record in plan['partitions'][partition]}


def test_group_holdout_reproducible_independent_of_input_order():
    catalog,gold,_=inputs()
    plan=freeze_benchmark(gold,catalog,seed=42)
    gold['examples'].reverse()
    assert freeze_benchmark(gold,catalog,seed=42)==plan
    groups={e['record_id']:e['group_id'] for e in gold['examples']}
    calibration={groups[r] for r in plan['partitions']['calibration']}
    held={groups[r] for r in plan['partitions']['annotation_holdout']}
    assert held and calibration and not calibration & held


def test_brier_denominators_and_selective_accuracy():
    catalog,gold,states=inputs()
    plan=freeze_benchmark(gold,catalog,seed=42)
    result=evaluate_benchmark(plan,predictions(plan,states),partition='annotation_holdout')
    metric=result['questions']['supported']
    assert metric['count']==2 and metric['available_count']==2
    assert metric['selective_accuracy']==0.5
    assert metric['mean_loss']==pytest.approx((0.01+0.81)/2)
    assert not result['live_model_quality_evaluated'] and not result['independent_trading_evidence']
    assert result['prediction_origin']=='mock' and result['label_origin']=='synthetic_fixture'


def test_abstentions_and_errors_are_not_silently_negative_labels():
    catalog,gold,states=inputs()
    plan=freeze_benchmark(gold,catalog)
    preds=predictions(plan,states,probability=0.5)
    first=next(iter(preds))
    preds[first]=evaluate_mock(states[first],catalog,{'answers':{}})
    result=evaluate_benchmark(plan,preds,partition='annotation_holdout')['questions']['supported']
    assert result['coverage']==0 and result['selective_accuracy'] is None
    assert result['error_count']==1 and result['abstain_count']==1
    assert result['scored_count']==1 and result['mean_loss']==0.25


def test_insufficient_gold_accepts_no_fake_correctness():
    catalog,gold,states=inputs()
    for e in gold['examples']:e['labels']['supported']=None
    plan=freeze_benchmark(gold,catalog)
    metric=evaluate_benchmark(plan,predictions(plan,states),partition='annotation_holdout')['questions']['supported']
    assert metric['labeled_count']==0 and metric['mean_loss'] is None
    assert metric['selective_accuracy'] is None and metric['expected_abstention_count']==2
    assert metric['available_on_insufficient_gold_count']==2


@pytest.mark.parametrize('tamper', ['policy','labels','partition','origin','state','status'])
def test_tampering_rejected(tamper):
    catalog,gold,states=inputs()
    plan=freeze_benchmark(gold,catalog)
    preds=predictions(plan,states)
    first=next(iter(preds))
    if tamper=='policy':plan['catalog']['questions']['supported']['accept_above']=0.95
    elif tamper=='labels':plan['gold']['examples'][0]['labels']['supported']='no'
    elif tamper=='partition':plan['partitions']['annotation_holdout'].append(plan['partitions']['calibration'][0])
    elif tamper=='origin':preds[first]['origin']='typesafe_api'
    elif tamper=='state':preds[first]['state_sha256']='0'*64
    else:preds[first]['answers']['supported']['decision']='no'
    with pytest.raises(ValueError):evaluate_benchmark(plan,preds,partition='annotation_holdout')


def test_exact_partition_coverage_and_group_collisions_required():
    catalog,gold,states=inputs()
    plan=freeze_benchmark(gold,catalog)
    with pytest.raises(ValueError,match='coverage'):
        evaluate_benchmark(plan,{},partition='annotation_holdout')
    gold['examples'][2]['state_sha256']=gold['examples'][0]['state_sha256']
    with pytest.raises(ValueError,match='cross groups'):
        freeze_benchmark(gold,catalog)


def test_choice_and_score_losses_use_all_valid_probabilities():
    catalog,gold,states=inputs()
    catalog['questions']={
        'mechanism':{'type':'choice','instructions':'Which mechanism?',
                     'criteria':{'threshold':'Threshold','unknown':'Missing'},'minimum_confidence':0.8},
        'clarity':{'type':'score','instructions':'How clear?', 'criteria':['Unclear','Clear'],'minimum_confidence':0.8}}
    for e in gold['examples']:e['labels']={'mechanism':'threshold','clarity':1}
    plan=freeze_benchmark(gold,catalog)
    raw={'answers':{'mechanism':{'type':'choice','choice':'threshold','confidence':0.9,
                               'probabilities':{'threshold':0.9,'unknown':0.1}},
                    'clarity':{'type':'score','score':0.7,'confidence':0.2,'probabilities':{'0':0.3,'1':0.7}}}}
    preds={r:evaluate_mock(states[r],catalog,raw) for r in plan['partitions']['annotation_holdout']}
    metrics=evaluate_benchmark(plan,preds,partition='annotation_holdout')['questions']
    assert metrics['mechanism']['mean_loss']==pytest.approx(0.02)
    assert metrics['clarity']['mean_loss']==pytest.approx(0.3)
    assert metrics['clarity']['selective_accuracy'] is None


def test_cli_freeze_before_predictions_and_private_non_overwriting_outputs(tmp_path):
    catalog,gold,states=inputs()
    for name,value in [('questions',catalog),('gold',gold)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value))
    plan_path=tmp_path/'plan.json'
    args=['freeze','--gold',str(tmp_path/'gold.json'),'--questions',str(tmp_path/'questions.json'),'--output',str(plan_path)]
    assert main(args)==0
    with pytest.raises(FileExistsError):main(args)
    plan=json.loads(plan_path.read_text())
    prediction_path=tmp_path/'predictions.json'
    prediction_path.write_text(json.dumps(predictions(plan,states)))
    output=tmp_path/'evaluation.json'
    assert main(['score','--plan',str(plan_path),'--predictions',str(prediction_path),
                 '--partition','annotation_holdout','--output',str(output)])==0
    assert output.stat().st_mode & 0o777==0o600


def test_public_prediction_manifest_has_no_gold_or_other_partition():
    catalog,gold,_=inputs()
    plan=freeze_benchmark(gold,catalog)
    public=public_view(plan,partition='annotation_holdout')
    assert not public['contains_gold_labels']
    assert all('labels' not in e for e in public['examples'])
    assert {e['record_id'] for e in public['examples']}==set(plan['partitions']['annotation_holdout'])
    assert not {e['record_id'] for e in public['examples']} & set(plan['partitions']['calibration'])
