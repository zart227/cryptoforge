"""Experimental ridge head for the explicit 24-feature contextual schema."""
from dataclasses import dataclass
from datetime import timedelta
from math import isfinite
from cryptoforge.context_features import FEATURE_VERSION,FEATURE_NAMES
from cryptoforge.model_training import fit_standardizer,standardize,dot
from cryptoforge.net_regression import _solve,NET_TARGETS


@dataclass(frozen=True)
class ContextExample:
    pair: str
    open_time: object
    feature_available_at: object
    label_available_at: object
    features: tuple
    future_return: float
    label: int
    feature_version: str=FEATURE_VERSION

    @property
    def label_end_time(self):return self.label_available_at


@dataclass(frozen=True)
class ContextRegressor:
    means: tuple
    stds: tuple
    weights: tuple
    bias: float
    target_version: str
    ridge: float
    feature_version: str=FEATURE_VERSION
    model_family: str='experimental-context-net-ridge-v2'
    live_eligible: bool=False

    def validate_example(self,row,*,as_of):
        validate_context_example(row,as_of=as_of)

    def predict(self,features):
        if self.feature_version!=FEATURE_VERSION:raise ValueError('context schema mismatch')
        if len(features)!=len(FEATURE_NAMES):raise ValueError('context feature dimensions differ')
        values=standardize(features,self.means,self.stds)
        result=self.bias+dot(self.weights,values)
        if not isfinite(result):raise ValueError('nonfinite context net forecast')
        return result


def validate_context_example(row,*,as_of):
    if row.feature_version!=FEATURE_VERSION or len(row.features)!=len(FEATURE_NAMES):raise ValueError('context schema mismatch')
    if as_of.tzinfo is None or any(stamp.tzinfo is None for stamp in (row.open_time,row.feature_available_at,row.label_available_at)) or not row.open_time<=row.feature_available_at<=row.label_available_at<=as_of:
        raise ValueError('unavailable contextual labels or features')
    if row.feature_available_at>row.open_time+timedelta(minutes=5):
        raise ValueError('context features unavailable at simulated entry decision')
    if not all(isfinite(v) for v in row.features) or not isfinite(row.future_return) or row.future_return< -1 or row.label!=int(row.future_return>0):
        raise ValueError('invalid contextual net data')


def fit_context_regressor(train,*,target_version,ridge,as_of):
    if target_version not in NET_TARGETS or as_of.tzinfo is None or not isfinite(ridge) or ridge<=0:
        raise ValueError('explicit net target, aware cutoff and positive ridge required')
    if len(train)<2:raise ValueError('insufficient contextual examples')
    seen=set()
    for row in train:
        key=(row.pair,row.open_time)
        if key in seen:raise ValueError('duplicate contextual sample')
        seen.add(key)
        validate_context_example(row,as_of=as_of)
    means,stds=fit_standardizer([row.features for row in train]);n=len(train);size=len(FEATURE_NAMES)
    x=[standardize(row.features,means,stds) for row in train];bias=sum(row.future_return for row in train)/n
    matrix=[[sum(values[i]*values[j] for values in x)/n+(ridge if i==j else 0) for j in range(size)] for i in range(size)]
    vector=[sum(values[i]*(row.future_return-bias) for values,row in zip(x,train))/n for i in range(size)]
    weights=_solve(matrix,vector)
    return ContextRegressor(tuple(means),tuple(stds),tuple(weights),bias,target_version,ridge)
