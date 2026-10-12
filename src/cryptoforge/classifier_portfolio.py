"""Explicit fixed-threshold adapter for research-only net profit scores."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ClassifierEntryScore:
    model: object
    threshold: float
    live_eligible: bool = False

    def __post_init__(self):
        if isinstance(self.threshold,bool) or not isfinite(self.threshold) or not 0<=self.threshold<=1:
            raise ValueError('explicit finite probability threshold required')

    def predict(self,features):
        # net_entry_signals accepts positive entry scores. This adapter keeps the
        # classifier diagnostic's >= convention, including exactly p==threshold.
        probability=self.model.predict_probability(features)
        if not isfinite(probability) or not 0<=probability<=1:
            raise ValueError('finite probability score in [0,1] required')
        return 1. if probability>=self.threshold else -1.
