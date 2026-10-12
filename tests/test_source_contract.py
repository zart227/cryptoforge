import hashlib,inspect
from pathlib import Path
import pytest
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.model_training import fit_standardizer


def test_missing_or_changed_frozen_dependency_refuses_replay():
    sha=hashlib.sha256(Path(inspect.getfile(fit_standardizer)).read_bytes()).hexdigest()
    assert assert_source_dependencies({'normalizer':sha},{'normalizer':fit_standardizer})=={'normalizer':sha}
    with pytest.raises(ValueError,match='changed'):assert_source_dependencies({'normalizer':'0'*64},{'normalizer':fit_standardizer})
    with pytest.raises(ValueError,match='changed'):assert_source_dependencies({},{'normalizer':fit_standardizer})


def test_net_manifest_covers_transitive_feature_observations_and_risk_labels():
    from cryptoforge.source_contract import net_research_sources,source_hashes
    from cryptoforge.context_regression import fit_context_regressor
    functions=net_research_sources('context_head',fit_context_regressor,context=True)
    assert {'candle_contract','causal_features','closed_timeframes','context_features',
            'trade_labels','trade_risk_labels','net_evaluation'} <= functions.keys()
    expected=source_hashes(functions)
    assert assert_source_dependencies(expected,functions)==expected
    del expected['candle_contract']
    with pytest.raises(ValueError,match='new fitted study'):assert_source_dependencies(expected,functions)
