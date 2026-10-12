"""Causal entry signals for a frozen experimental net head, no labels read."""
from datetime import timedelta
from cryptoforge.causal_features import feature_snapshots
from cryptoforge.live_learning_protocol import time


def net_entry_signals(model,data,ranges,config):
    selected={};baseline={}
    step=timedelta(minutes=5);horizon=step*(config.hold_bars+config.entry_delay_bars)
    for pair,rows in data.items():
        start=time(ranges[pair]['validation_start']);end=time(ranges[pair]['development_end'])
        snapshots=feature_snapshots(pair,rows,as_of=end)
        opportunities=[snapshot for snapshot in snapshots if start<=snapshot.open_time
            and snapshot.feature_available_at<=snapshot.open_time+step
            and snapshot.feature_available_at+horizon<end]
        baseline[pair]=[snapshot.open_time for snapshot in opportunities]
        selected[pair]=[snapshot.open_time for snapshot in opportunities if model.predict(snapshot.features)>0]
    return selected,baseline
