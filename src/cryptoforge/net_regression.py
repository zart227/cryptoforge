"""Experimental train-only ridge head for net returns; never live compatible."""
from dataclasses import dataclass
from math import isfinite,sqrt
from cryptoforge.model_training import fit_standardizer,standardize

NET_TARGETS={'spot-long-trade-net-v2','spot-long-real-cash-recovery-dust-zero-v1'}


@dataclass(frozen=True)
class NetRegressor:
    means: tuple
    stds: tuple
    weights: tuple
    bias: float
    target_version: str
    ridge: float
    model_family: str='experimental-ridge-net-return-v1'
    live_eligible: bool=False

    def predict(self,features):
        if len(features)!=len(self.weights) or not all(isfinite(float(value)) for value in features):
            raise ValueError('net prediction feature schema mismatch')
        values=standardize(tuple(float(value) for value in features),self.means,self.stds)
        estimate=self.bias+sum(w*x for w,x in zip(self.weights,values))
        if not isfinite(estimate):raise ValueError('nonfinite expected net return')
        return estimate


def _solve(matrix,vector):
    augmented=[list(row)+[value] for row,value in zip(matrix,vector)];n=len(vector)
    for column in range(n):
        pivot=max(range(column,n),key=lambda row:abs(augmented[row][column]))
        augmented[column],augmented[pivot]=augmented[pivot],augmented[column]
        divisor=augmented[column][column]
        if not isfinite(divisor) or abs(divisor)<1e-12:raise ValueError('unstable net regression design')
        augmented[column]=[v/divisor for v in augmented[column]]
        for row in range(n):
            if row==column:continue
            factor=augmented[row][column]
            augmented[row]=[a-factor*b for a,b in zip(augmented[row],augmented[column])]
    weights=[row[-1] for row in augmented]
    if not all(isfinite(v) for v in weights):raise ValueError('nonfinite net regression coefficients')
    return weights


def fit_net_regressor(train,*,target_version,ridge,as_of,sample_weights=None):
    if target_version not in NET_TARGETS:raise ValueError('explicit net-return target required; gross targets forbidden')
    if as_of.tzinfo is None or not isfinite(ridge) or ridge<=0:raise ValueError('aware cutoff and positive finite ridge required')
    if len(train)<2:raise ValueError('at least two observed examples required')
    size=len(train[0].features)
    if size!=7:raise ValueError('registered candle-v1 seven-feature schema required')
    seen=set()
    for row in train:
        if row.short_label!=0:raise ValueError('Spot-long net head forbids short-target labels')
        identity=(row.pair,row.open_time)
        if identity in seen:raise ValueError('duplicate training sample identity')
        seen.add(identity)
        if row.open_time.tzinfo is None or row.label_end_time is None or row.label_end_time.tzinfo is None:
            raise ValueError('explicit aware label availability required')
        if not row.open_time<=row.label_end_time<=as_of:raise ValueError('future/unavailable net label')
        if len(row.features)!=size or not all(isfinite(v) for v in row.features) or not isfinite(row.future_return):
            raise ValueError('finite consistent features/targets required')
        if row.future_return< -1 or row.label!=int(row.future_return>0):raise ValueError('net target and profit label mismatch')
    weights_input=tuple(sample_weights) if sample_weights is not None else (1.,)*len(train)
    if len(weights_input)!=len(train) or any(isinstance(w,bool) or not isfinite(w) or w<=0 for w in weights_input):
        raise ValueError('positive finite sample weights matching train required')
    total=sum(weights_input)
    if not isfinite(total):raise ValueError('nonfinite sample weight total')
    normalized=tuple(w/total for w in weights_input)
    if any(w<=0 or not isfinite(w) for w in normalized):
        raise ValueError('sample weights underflow after normalization')
    try:
        if sample_weights is None:
            means,stds=fit_standardizer([row.features for row in train])
        else:
            means=tuple(sum(w*row.features[i] for w,row in zip(normalized,train)) for i in range(size))
            stds=tuple(sqrt(sum(w*(row.features[i]-means[i])**2 for w,row in zip(normalized,train))) or 1. for i in range(size))
    except ArithmeticError as exc:raise ValueError('unstable train-only net standardizer') from exc
    if not all(isfinite(v) for v in means+stds):raise ValueError('invalid train-only net standardizer')
    x=[standardize(row.features,means,stds) for row in train];bias=sum(w*row.future_return for w,row in zip(normalized,train))
    matrix=[[sum(w*values[i]*values[j] for w,values in zip(normalized,x))+(ridge if i==j else 0) for j in range(size)] for i in range(size)]
    vector=[sum(w*values[i]*(row.future_return-bias) for w,values,row in zip(normalized,x,train)) for i in range(size)]
    weights=_solve(matrix,vector)
    return NetRegressor(tuple(means),tuple(stds),tuple(weights),bias,target_version,ridge)


def evaluate_net_regressor(model,examples,*,as_of,target_version):
    if target_version!=model.target_version:raise ValueError('net evaluation target differs from fitted target')
    if as_of.tzinfo is None:raise ValueError('aware evaluation cutoff required')
    if not examples:return {'count':0,'mae':None,'rmse':None,'live_promotion_allowed':False}
    errors=[];seen=set()
    for row in examples:
        if getattr(row,'short_label',0)!=0:raise ValueError('Spot-long net evaluation forbids short-target labels')
        identity=(row.pair,row.open_time)
        if identity in seen:raise ValueError('duplicate net evaluation sample identity')
        seen.add(identity)
        if row.open_time.tzinfo is None or row.label_end_time is None or row.label_end_time.tzinfo is None or not row.open_time<=row.label_end_time<=as_of:
            raise ValueError('unordered or unavailable net evaluation outcome')
        validator=getattr(model,'validate_example',None)
        if validator is not None:validator(row,as_of=as_of)
        if hasattr(model,'feature_version') and getattr(row,'feature_version',None)!=model.feature_version:
            raise ValueError('net evaluation feature schema differs from fitted schema')
        if row.label_end_time is None or row.label_end_time.tzinfo is None or row.label_end_time>as_of:raise ValueError('unavailable net evaluation outcome')
        if not isfinite(row.future_return) or row.future_return< -1 or row.label!=int(row.future_return>0):
            raise ValueError('net evaluation target and label mismatch')
        error=model.predict(row.features)-row.future_return
        if not isfinite(error):raise ValueError('nonfinite net evaluation error')
        errors.append(error)
    mae=sum(abs(value) for value in errors)/len(errors);rmse=sqrt(sum(value*value for value in errors)/len(errors))
    if not isfinite(mae) or not isfinite(rmse):raise ValueError('nonfinite net evaluation metrics')
    return {'count':len(errors),'mae':mae,
            'rmse':rmse,
            'scope':'net_return_prediction_error_not_executed_portfolio_profit','live_promotion_allowed':False}
