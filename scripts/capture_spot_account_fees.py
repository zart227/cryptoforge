"""Read current account fee rates; never update execution settings or orders."""
import argparse,hashlib,json,os,shlex,shutil
from datetime import UTC,datetime
from pathlib import Path
from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.fee_observation import normalize_fee_observation,save_fee_observation
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',action='append',required=True)
    parser.add_argument('--directory',type=Path,default=Path('.local/account-fee-observations'))
    args=parser.parse_args();pairs=sorted(set(args.pair))
    if not pairs or len(pairs)>20 or any(not p.endswith('/USDT') or len(p.split('/'))!=2 for p in pairs):parser.error('bounded explicit USDT pairs required')
    if shutil.disk_usage('.').free<(2048+2)*1024**2:print(json.dumps({'status':'deferred_disk_reserve'}));return
    if Path('.env').exists():
        for line in Path('.env').read_text().splitlines():
            key,separator,value=line.partition('=');key=key.strip().removeprefix('export ')
            if separator and key in {'BYBIT_API_KEY','BYBIT_API_SECRET'}:
                values=shlex.split(value,comments=True)
                if len(values)==1:os.environ.setdefault(key,values[0])
    deps={'adapter':BybitPrivateClient,'normalizer':normalize_fee_observation,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps);runtime=save_runtime_sources(args.directory/'runtime',deps,hashes)
    receipts=[];errors={}
    try:
        client=BybitPrivateClient.from_env();client.timeout_seconds=2;client.synchronize_time(max_attempts=1)
        account=hashlib.sha256(client.api_key.encode()).hexdigest()
    except Exception as exc:print(json.dumps({'status':'unverified','error_class':type(exc).__name__}));return
    for pair in pairs:
        try:
            symbol=pair.replace('/','');started=datetime.now(UTC)
            payload=client._private_get('/v5/account/fee-rate',{'category':'spot','symbol':symbol})
            observed=datetime.now(UTC)
            ref,receipt=save_fee_observation(args.directory,payload,symbol=symbol,started_at=started,observed_at=observed,
                now=datetime.now(UTC),account_scope=account,implementation_hashes=hashes,runtime_source_bundle=runtime)
            receipts.append({'pair':pair,'rates':receipt['rates'],'receipt':ref})
        except Exception as exc:errors[pair]=type(exc).__name__
    print(json.dumps({'observations':receipts,'errors':errors,'execution_settings_changed':False}))


if __name__=='__main__':main()
