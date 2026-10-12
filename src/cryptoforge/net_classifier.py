"""Research-only profit classifier with train-only class weights, not calibrated odds."""
from dataclasses import dataclass
from math import isfinite,exp,log
from cryptoforge.model_training import fit_standardizer,standardize
from cryptoforge.net_regression import NET_TARGETS
from cryptoforge.classifier_diagnostics import probability_diagnostics


def _sigmoid(value):
    if value>=0:return 1/(1+exp(-value))
    e=exp(value);return e/(1+e)


def _validate(rows,as_of):
    if as_of.tzinfo is None or not rows:raise ValueError('aware nonempty net classification input required')
    seen=set()
    for row in rows:
        if row.short_label!=0:raise ValueError('Spot-long classifier forbids short-target labels')
        key=(row.pair,row.open_time)
        if key in seen:raise ValueError('duplicate net classifier sample')
        seen.add(key)
        if (row.open_time.tzinfo is None or row.label_end_time is None or row.label_end_time.tzinfo is None
            or not row.open_time<=row.label_end_time<=as_of):raise ValueError('unavailable net classifier outcome')
        if (len(row.features)!=7 or not all(isfinite(v) for v in row.features) or not isfinite(row.future_return)
            or row.future_return< -1 or row.label!=int(row.future_return>0)):raise ValueError('finite net profit labels required')


@dataclass(frozen=True)
class NetProfitClassifier:
    means: tuple
    stds: tuple
    weights: tuple
    bias: float
    train_positive_rate: float
    class_weights: tuple
    target_version: str
    fit_information_end: object
    training_identities: tuple
    model_family: str='experimental-weighted-net-profit-classifier-v1'
    live_eligible: bool=False
    probability_calibration_established: bool=False

    def predict_probability(self,features):
        if len(features)!=7 or not all(isfinite(v) for v in features):raise ValueError('finite seven-feature net input required')
        x=standardize(features,self.means,self.stds)
        value=self.bias+sum(w*v for w,v in zip(self.weights,x))
        if not isfinite(value):raise ValueError('finite net classifier score required')
        return _sigmoid(value)


def fit_net_classifier(train,*,target_version,as_of,class_balance=False,epochs=100,learning_rate=.05,l2=.001):
    if target_version not in NET_TARGETS:raise ValueError('net target required, gross candle target forbidden')
    if (type(class_balance) is not bool or type(epochs) is not int or epochs<1 or not isfinite(learning_rate)
        or learning_rate<=0 or not isfinite(l2) or l2<0):raise ValueError('finite explicit net classifier design required')
    _validate(train,as_of);n=len(train);positives=sum(row.label for row in train);negatives=n-positives
    if not positives or not negatives:raise ValueError('both observed profit classes required')
    cw=(n/(2*negatives),n/(2*positives)) if class_balance else (1.,1.)
    means,stds=fit_standardizer([row.features for row in train]);x=[standardize(row.features,means,stds) for row in train]
    weights=[0.]*7;rate=positives/n;bias=0. if class_balance else log(rate/(1-rate))
    for _ in range(epochs):
        gradient=[0.]*7;bias_gradient=0.
        for row,values in zip(train,x):
            error=(_sigmoid(bias+sum(w*v for w,v in zip(weights,values)))-row.label)*cw[row.label]
            bias_gradient+=error
            for index,value in enumerate(values):gradient[index]+=error*value
        bias-=learning_rate*bias_gradient/n
        weights=[weight-learning_rate*(value/n+l2*weight) for weight,value in zip(weights,gradient)]
        if not all(isfinite(v) for v in [bias,*weights]):raise ValueError('nonfinite net classifier optimization')
    return NetProfitClassifier(tuple(means),tuple(stds),tuple(weights),bias,rate,cw,target_version,
        max(row.label_end_time for row in train),tuple((row.pair,row.open_time) for row in train))


def evaluate_net_classifier(model,rows,*,as_of,target_version):
    if target_version!=model.target_version:raise ValueError('net classifier target mismatch')
    _validate(rows,as_of)
    result=probability_diagnostics([row.label for row in rows],[model.predict_probability(row.features) for row in rows],
        train_positive_rate=model.train_positive_rate,threshold=.5)
    train_identities=set(model.training_identities)
    result.update(evaluation_is_after_fit_information_end=min(row.open_time for row in rows)>model.fit_information_end,
        evaluation_reuses_training_identities=sum((row.pair,row.open_time) in train_identities for row in rows),
        independent_out_of_sample_established=False,evaluation_distribution='original_unweighted_rows',class_weights_fitted_on='train_only',
        class_weights=list(model.class_weights),probability_calibration_established=False,
        probability_interpretation='weighted_training_objective_score_requires_natural_distribution_calibration',
        realized_income_established=False,live_promotion_allowed=False)
    return result
