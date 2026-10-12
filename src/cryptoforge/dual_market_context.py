"""Experimental BTC/ETH context extension; no existing model schema is changed."""
from dataclasses import replace
from datetime import timedelta
from math import log,sqrt,isfinite
from cryptoforge.causal_features import feature_snapshots
from cryptoforge.candle_contract import known_closed
from cryptoforge.context_features import context_snapshots,FEATURE_NAMES as BASE_NAMES

FEATURE_VERSION='experimental-dual-market-context-v1'
FEATURE_NAMES=(*BASE_NAMES,'eth_return_12','relative_eth_return_12','eth_vol_12',
               'btc_return_correlation_12','eth_return_correlation_12')


def _returns(rows,index):
    return [log(float(rows[i].close/rows[i-1].close)) for i in range(index-11,index+1)]


def _correlation(left,right):
    a=sum(left)/len(left);b=sum(right)/len(right)
    x=[v-a for v in left];y=[v-b for v in right]
    denominator=sqrt(sum(v*v for v in x)*sum(v*v for v in y))
    if denominator==0:return None
    return max(-1.,min(1.,sum(v*w for v,w in zip(x,y))/denominator))


def dual_context_snapshots(pair,candles,btc_candles,eth_candles,*,as_of):
    base,base_quality=context_snapshots(pair,candles,btc_candles,as_of=as_of)
    references=feature_snapshots('ETH/USDT',eth_candles,as_of=as_of)
    step=timedelta(minutes=5)
    groups=[[row for row in series if known_closed(row,step=step,as_of=as_of)]
            for series in (candles,btc_candles,eth_candles)]
    if any(row.symbol!='ETHUSDT' for row in groups[2]):raise ValueError('ETH market identity required')
    indices=[{row.open_time:i for i,row in enumerate(series)} for series in groups]
    refs={row.open_time:row for row in references};result=[];excluded={}
    for snapshot in base:
        stamp=snapshot.open_time
        if stamp not in refs:
            excluded['missing_aligned_eth_context']=excluded.get('missing_aligned_eth_context',0)+1;continue
        own_index,btc_index,eth_index=[index[stamp] for index in indices]
        own_returns,btc_returns,eth_returns=[_returns(series,index) for series,index in
            zip(groups,(own_index,btc_index,eth_index))]
        btc_correlation=_correlation(own_returns,btc_returns)
        eth_correlation=_correlation(own_returns,eth_returns)
        if btc_correlation is None or eth_correlation is None:
            excluded['undefined_return_correlation']=excluded.get('undefined_return_correlation',0)+1;continue
        er=float(groups[2][eth_index].close/groups[2][eth_index-12].close-1)
        mean=sum(eth_returns)/12;vol=sqrt(sum((value-mean)**2 for value in eth_returns)/12)
        values=(*snapshot.features,er,snapshot.features[7]-er,vol,btc_correlation,eth_correlation)
        if not all(isfinite(value) for value in values):raise ValueError('finite dual context required')
        result.append(replace(snapshot,features=tuple(values),feature_version=FEATURE_VERSION,
            feature_available_at=max(snapshot.feature_available_at,refs[stamp].feature_available_at)))
    return result,{'feature_version':FEATURE_VERSION,'feature_names':list(FEATURE_NAMES),'count':len(result),
        'excluded':excluded,'base_context_quality':base_quality,'unknown_context_filled':False,
        'undefined_correlation_filled':False,'live_model_input_allowed':False,
        'independent_profitability_established':False}
