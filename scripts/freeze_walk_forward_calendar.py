"""Save original future calendar and runtime without reading outcome data."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime,UTC,timedelta
from cryptoforge.walk_forward_schedule import make_schedule
from cryptoforge.walk_forward import folds
from cryptoforge.walk_forward_selection import fold_payload
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.immutable_files import install_original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('.local/state/walk-forward-calendars'))
    parser.add_argument('--first-test-start');args=parser.parse_args();now=datetime.now(UTC)
    first=datetime.fromisoformat(args.first_test_start.replace('Z','+00:00')) if args.first_test_start else now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=2)
    schedule=make_schedule(observed_at=now,first_test_start=first)
    gate_path=Path('config/net-classifier-balance-research-v1.json');raw=gate_path.read_bytes()
    gate_sha=hashlib.sha256(raw).hexdigest()
    if gate_sha!=gate_path.with_suffix('.sha256').read_text().strip():raise ValueError('original split design checksum mismatch')
    schedule['parent_design_sha256']=gate_sha
    deps={'schedule':make_schedule,'folds':folds,'fold_payload':fold_payload,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps);schedule['implementation_hashes']=hashes
    schedule['runtime_source_bundle']=save_runtime_sources(args.directory/'runtime',deps,hashes)
    assert_source_dependencies(hashes,deps)
    payload=(json.dumps(schedule,sort_keys=True,indent=2)+'\n').encode();sha=hashlib.sha256(payload).hexdigest()
    path=args.directory/sha/'calendar.json';path.parent.mkdir(parents=True,exist_ok=True)
    install_original(path,payload)
    print(json.dumps({'calendar_sha256':sha,'path':str(path.resolve()),'test_windows':len(schedule['folds']),
        'first_test_start':schedule['folds'][0]['test_start'],'last_test_end':schedule['folds'][-1]['test_end'],
        'selection_procedure_preregistered':False,'live_promotion_allowed':False}))


if __name__=='__main__':main()
