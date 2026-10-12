"""Fixed seven-feature ablation procedure; no automatic feature selection."""
from dataclasses import dataclass,replace
from math import isfinite
from cryptoforge.net_regression import fit_net_regressor
from cryptoforge.model_training import FEATURE_NAMES


def _mask(features,removed):
    if len(features)!=len(FEATURE_NAMES) or not all(isfinite(value) for value in features):
        raise ValueError('finite original seven-feature vector required')
    return tuple(0. if index in removed else value for index,value in enumerate(features))


@dataclass(frozen=True)
class AblatedNetRegressor:
    fitted: object
    removed_indices: tuple
    target_version: str
    model_family: str='experimental-ablated-ridge-net-return-v1'
    live_eligible: bool=False

    def predict(self,features):return self.fitted.predict(_mask(features,self.removed_indices))


def fit_ablated_net_regressor(train,*,removed_indices,target_version,ridge,as_of,sample_weights=None):
    removed=tuple(removed_indices)
    if (not removed or len(set(removed))!=len(removed) or len(removed)>=len(FEATURE_NAMES)
        or any(type(index) is not int or not 0<=index<len(FEATURE_NAMES) for index in removed)):
        raise ValueError('explicit unique proper subset of feature indices required')
    # Mask both train and inference with the same immutable specification.
    masked=[replace(row,features=_mask(row.features,removed)) for row in train]
    fitted=fit_net_regressor(masked,target_version=target_version,ridge=ridge,as_of=as_of,
                             sample_weights=sample_weights)
    return AblatedNetRegressor(fitted,tuple(sorted(removed)),target_version)


def ablation_description(model):
    return {'removed_indices':list(model.removed_indices),
        'removed_feature_names':[FEATURE_NAMES[index] for index in model.removed_indices],
        'preprocessing_fitted_on':'masked_train_only','feature_selection_performed':False,
        'validation_refits_preprocessing':False,'live_promotion_allowed':False}
