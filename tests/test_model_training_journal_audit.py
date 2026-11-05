import hashlib,json

import pytest

from cryptoforge.model_training_journal_audit import audit_training_journal


def pin(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def source(tmp_path):
    promotion={'promoted':False,'count':420,'incumbent':'incumbent-v1',
               'candidate':{'signals':2,'mean_net_signal_return':0.013},'accuracy':0.7333,
               'majority_baseline':0.7286,'round_trip_cost':0.003,'reason':'insufficient_signals',
               'comparison_blocked_reason':'incompatible_feature_calculation_contract',
               'scope':'fixed_candle_return_signal_screen_not_executed_cash_or_portfolio_income'}
    lines=['model_training version=candidate-v2 pairs=20 test:n=1140:acc=0.752:precision=0.750:recall=0.011',
           'promotion='+repr(promotion)]
    for head in ('long','short'):
        lines.append(f'probability_quality head={head} split=test log_loss=0.4 baseline_log_loss=0.5 brier=0.1 baseline_brier=0.2 max_probability=0.8 signals=4 threshold=0.5')
    path=tmp_path/'metrics.json';path.write_text(json.dumps({'filtered_journal':'\n'.join(lines),'requested_window_msk':'fixed','orders_placed':False,'source_is_live_executions':False}))
    return path


def run(path):return audit_training_journal(path,pin(path))


def change(path,fn):
    data=json.loads(path.read_text());data['filtered_journal']=fn(data['filtered_journal']);path.write_text(json.dumps(data))


def test_distinct_supports_and_price_scope_remain_separate(source):
    r=run(source)
    assert r['model_test']['examples']==1140 and r['promotion']['sample_count']==420 and r['promotion']['signals']==2
    assert r['candidate_model_version']=='candidate-v2' and r['incumbent_model_version']=='incumbent-v1'
    assert r['quality_test']['long']['log_loss']<r['quality_test']['long']['baseline_log_loss']
    assert not r['promotion']['promoted'] and not r['current_incumbent_comparison_established']
    assert not r['executed_cash_profit_established'] and not r['live_promotion_allowed']


def test_missing_quality_or_duplicate_promotion_is_rejected(source):
    change(source,lambda s:'\n'.join(x for x in s.splitlines() if 'head=short' not in x))
    with pytest.raises(ValueError,match='quality metrics missing'):run(source)


def test_malformed_duplicate_and_nonfinite_metrics_are_rejected(source):
    change(source,lambda s:s.replace('log_loss=0.4','log_loss=nan',1))
    with pytest.raises(ValueError,match='invalid quality metric'):run(source)


def test_unsafe_promotion_expression_is_not_executed(source,tmp_path):
    marker=tmp_path/'should-not-exist'
    change(source,lambda s:'\n'.join('promotion=__import__("pathlib").Path('+repr(str(marker))+').touch()' if x.startswith('promotion=') else x for x in s.splitlines()))
    with pytest.raises(ValueError,match='invalid promotion record'):run(source)
    assert not marker.exists()


def test_unknown_scope_is_not_cash_profit(source):
    change(source,lambda s:s.replace('fixed_candle_return_signal_screen_not_executed_cash_or_portfolio_income','cash_live'))
    with pytest.raises(ValueError,match='price-screen scope'):run(source)


def test_journal_hash_or_source_alias_is_rejected(source,tmp_path):
    with pytest.raises(ValueError,match='hash mismatch'):audit_training_journal(source,'0'*64)
    alias=tmp_path/'alias';alias.symlink_to(source)
    with pytest.raises(ValueError,match='canonical'):audit_training_journal(alias,pin(source))


def test_signal_count_cannot_exceed_promotion_sample(source):
    change(source,lambda s:s.replace("'signals': 2", "'signals': 421"))
    with pytest.raises(ValueError,match='signal support'):run(source)


def test_nonboolean_promoted_is_rejected(source):
    change(source,lambda s:s.replace("'promoted': False", "'promoted': 0"))
    with pytest.raises(ValueError,match='typed promotion'):run(source)
