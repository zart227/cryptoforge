"""Native scalar arithmetic equivalence; no fitting, predictions or provider calls."""
import math
from pathlib import Path
import random
import statistics
import time

import pytest
from cryptoforge import research_dot_optimization as m
from cryptoforge import model_training as native


def outcome(function,left,right):
    try:
        value=function(left,right)
        return ('result',type(value).__name__,value.hex() if type(value) is float else value)
    except (ValueError,OverflowError,TypeError) as error:return ('error',type(error).__name__,str(error))


@pytest.mark.parametrize('left,right',[
    ([],[]),([0.],[-0.]),([1.,-1.,1e-100],[1e100,1e100,1e100]),
    ([1e308,1e308,-1e308],[1.,1.,1.]),([float('inf')],[0.]),([float('nan')],[1.]),
    ([1.,2.],[1.]),([1e308],[1e308]),([1e-300],[1e-300]),([1,2,3],[.5,.2,.1]),
    (['bad'],[1.]),([True],[1.]),
])
def test_exact_binary64_results_and_exception_contract_match_native(left,right):
    assert outcome(native.dot,left,right)==outcome(m.fast_dot,left,right)


def test_deterministic_adversarial_vectors_match_native_bitwise():
    rng=random.Random(271026)
    for n in range(2000):
        dimension=(0,1,7,14)[n%4]
        left=[rng.uniform(-1.,1.)*10.**rng.randint(-150,150) for _ in range(dimension)]
        right=[rng.uniform(-1.,1.)*10.**rng.randint(-150,150) for _ in range(dimension)]
        assert outcome(native.dot,left,right)==outcome(m.fast_dot,left,right)


def test_review_patch_only_accepts_exact_current_native_source_and_does_not_apply(tmp_path):
    source=Path(native.__file__).read_bytes();before=source;result=m.reviewed_patch(source)
    assert '+    result=sum(map(_dot_mul,left,right))' in result['patch']
    assert '+from operator import mul as _dot_mul' in result['patch']
    assert not result['review']['production_applied'] and not result['review']['genuine_LLM_patch']
    assert Path(native.__file__).read_bytes()==before
    with pytest.raises(ValueError):m.reviewed_patch(source+b'\n')


def test_bounded_scalar_CPU_comparison_records_measurements_without_speed_assertion(tmp_path):
    left=[.03,-.02,.11,.34,-.7,.00004,.9];right=(.5,.6,-.3,.8,.9,.01,-.6)
    measurements={'native':[],'proposed':[]};calls_per_round=20000;rounds=7
    for index in range(rounds):
        order=(('native',native.dot),('proposed',m.fast_dot)) if index%2==0 else (('proposed',m.fast_dot),('native',native.dot))
        for name,function in order:
            began=time.process_time_ns()
            for _ in range(calls_per_round):function(left,right)
            measurements[name].append(time.process_time_ns()-began)
    medians={k:statistics.median(v) for k,v in measurements.items()}
    report={'schema_version':'synthetic-scalar-dot-CPU-comparison-v1','only_scalar_fixture_arithmetic':True,
        'rounds':rounds,'calls_per_variant':rounds*calls_per_round,'dimension':7,'CPU_nanoseconds_by_round':measurements,
        'median_CPU_nanoseconds':medians,'proposed_to_native_CPU_ratio':medians['proposed']/medians['native'],
        'whole_training_speedup_measured':False,'model_fit_prediction_provider_or_budget_actions':0,
        'review':m.reviewed_patch(Path(native.__file__).read_bytes())['review']}
    path=tmp_path/'dot-benchmark.json'
    from cryptoforge.research_training_diagnostics import canonical
    path.write_text(canonical(report));path.chmod(0o600)
