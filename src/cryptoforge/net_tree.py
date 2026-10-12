"""Small deterministic experimental regression tree for net-return diagnostics."""
from dataclasses import dataclass
from math import isfinite
from cryptoforge.net_regression import NET_TARGETS


@dataclass(frozen=True)
class NetTree:
    root: dict
    target_version: str
    maximum_depth: int
    minimum_leaf: int
    model_family: str='experimental-causal-net-tree-v1'
    live_eligible: bool=False

    def predict(self,features):
        if len(features)!=7 or not all(isfinite(float(value)) for value in features):raise ValueError('net tree feature schema mismatch')
        node=self.root
        while 'feature' in node:
            node=node['left'] if float(features[node['feature']])<=node['threshold'] else node['right']
        return node['value']


def fit_net_tree(train,*,target_version,maximum_depth,minimum_leaf,as_of,maximum_thresholds=9):
    if target_version not in NET_TARGETS or as_of.tzinfo is None:raise ValueError('explicit net target and aware cutoff required')
    if type(maximum_depth) is not int or not 1<=maximum_depth<=4 or type(minimum_leaf) is not int or minimum_leaf<2:
        raise ValueError('bounded tree design required')
    if type(maximum_thresholds) is not int or not 1<=maximum_thresholds<=9:raise ValueError('bounded threshold grid required')
    seen=set()
    for row in train:
        if row.short_label!=0:raise ValueError('Spot-long net tree forbids short-target labels')
        key=(row.pair,row.open_time)
        if key in seen:raise ValueError('duplicate net tree sample')
        seen.add(key)
        if row.label_end_time is None or row.open_time.tzinfo is None or row.label_end_time.tzinfo is None or not row.open_time<=row.label_end_time<=as_of:
            raise ValueError('unavailable net tree label')
        if len(row.features)!=7 or not all(isfinite(v) for v in row.features) or not isfinite(row.future_return):raise ValueError('finite net tree data required')
        if row.future_return< -1 or row.label!=int(row.future_return>0):raise ValueError('net tree target mismatch')
    if len(train)<minimum_leaf:raise ValueError('insufficient tree leaf support')
    def loss(rows):
        mean=sum(row.future_return for row in rows)/len(rows)
        return mean,sum((row.future_return-mean)**2 for row in rows)
    def grow(rows,depth):
        mean,base_loss=loss(rows);leaf={'value':mean,'count':len(rows)}
        if depth>=maximum_depth or len(rows)<2*minimum_leaf:return leaf
        best=None
        for feature in range(7):
            values=sorted({row.features[feature] for row in rows})
            if len(values)<2:continue
            indices=sorted({min(len(values)-2,int((len(values)-1)*i/(maximum_thresholds+1))) for i in range(1,maximum_thresholds+1)})
            for index in indices:
                threshold=values[index]/2+values[index+1]/2
                left=[row for row in rows if row.features[feature]<=threshold]
                right=[row for row in rows if row.features[feature]>threshold]
                if min(len(left),len(right))<minimum_leaf:continue
                score=loss(left)[1]+loss(right)[1]
                candidate=(score,feature,threshold,left,right)
                if best is None or candidate[:3]<best[:3]:best=candidate
        if best is None or best[0]>=base_loss-1e-15:return leaf
        _,feature,threshold,left,right=best
        return {'feature':feature,'threshold':threshold,'count':len(rows),'value':mean,
                'left':grow(left,depth+1),'right':grow(right,depth+1)}
    return NetTree(grow(list(train),0),target_version,maximum_depth,minimum_leaf)
