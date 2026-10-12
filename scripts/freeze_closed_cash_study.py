"""Freeze a separate future closed-only collection study; never train or trade."""
import argparse
from copy import deepcopy
from datetime import UTC,datetime,timedelta
import hashlib,json,os,tempfile
from pathlib import Path
from cryptoforge.cash_study_paths import DEFAULT_PROTOCOL,load_cash_study
from cryptoforge.cash_study_registry import CashStudyRegistry
from cryptoforge.experience_memory import available_experiences
from cryptoforge.live_learning_protocol import load_protocol,buy_key
from cryptoforge.immutable_files import install_original


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol-version',default='live-cash-recovery-closed-v1.0')
    parser.add_argument('--lookback-candles',type=int,default=120)
    parser.add_argument('--output',type=Path,default=Path('config/live-cash-recovery-closed-protocol-v1.json'))
    args=parser.parse_args(argv)
    if not 36<=args.lookback_candles<=1000:raise ValueError('closed study window must be in [36,1000]')
    registry=CashStudyRegistry(Path('.local/state/cash-study-registry.sqlite'))
    receipt=registry.by_version(args.protocol_version)
    if receipt:
        raw=receipt['protocol_payload'].encode();protocol=json.loads(raw)
        if (protocol['input_candle_state']!='closed_only'
            or protocol['feature_input_contract']['lookback_candles']!=args.lookback_candles):
            raise ValueError('frozen collection version cannot change its input contract')
        initial_path=Path('.local/state/cash-studies')/receipt['protocol_sha256']/'initial-memory-snapshot.json'
        if 'initial_snapshot_payload' in receipt:
            install_original(initial_path,receipt['initial_snapshot_payload'].encode())
        elif not initial_path.exists() or hashlib.sha256(initial_path.read_bytes()).hexdigest()!=protocol['development_snapshot_sha256']:
            raise ValueError('original initial snapshot must be restored from its backup')
    else:
        if args.output.exists() or args.output.with_suffix('.sha256').exists():
            raise ValueError('unregistered collection files exist; preserve them and choose a new version/path')
        protocol=deepcopy(load_protocol(DEFAULT_PROTOCOL));now=datetime.now(UTC)
        known=available_experiences(Path('.local/state/live-experience-memory.sqlite'),target=protocol['target_version'],as_of=now)
        snapshot=json.dumps({'as_of':now.isoformat(),'examples':known},sort_keys=True,default=str).encode()
        snapshot_sha=hashlib.sha256(snapshot).hexdigest()
        protocol.update(protocol_version=args.protocol_version,frozen_at=now.isoformat(),input_candle_state='closed_only',
            feature_input_contract={'feature_version':'candle-v1','timeframe':'5m','input_candle_state':'closed_only',
                'calculation_contract':'bounded-window-candle-v1','lookback_candles':args.lookback_candles},
            development_buy_keys=sorted({buy_key(row) for row in known}),development_snapshot_sha256=snapshot_sha,
            note='Separate forward closed-only study; legacy buys are not new closed-only samples. No automatic fitting, live promotion or paper activation.')
        cursor=now
        for split,days in (('train',28),('validation',14),('sealed_test',28),('paper',28)):
            end=cursor+timedelta(days=days)
            protocol['windows'][split]={'start':cursor.isoformat(),'end_exclusive':end.isoformat()};cursor=end
        raw=(json.dumps(protocol,indent=2)+'\n').encode();receipt=registry.freeze(raw,initial_snapshot=snapshot)
        sha=receipt['protocol_sha256']
        install_original(Path('.local/state/cash-studies')/sha/'initial-memory-snapshot.json',snapshot)
    install_original(args.output,raw)
    install_original(args.output.with_suffix('.sha256'),(receipt['protocol_sha256']+'\n').encode())
    protocol,study=load_cash_study(args.output)
    print(json.dumps({'protocol':str(args.output.resolve()),'protocol_sha256':study.protocol_sha256,
        'observed_at':receipt['observed_at'],'input_contract':protocol['feature_input_contract'],
        'known_buy_keys_training_only':len(protocol['development_buy_keys']),
        'training_minimum_buys':protocol['minimums']['train']['buy_orders'],
        'train_end':protocol['windows']['train']['end_exclusive'],'live_promotion_allowed':False}))


if __name__=='__main__':main()
