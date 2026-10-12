"""Frozen development protocol and resource checks, independent of live trading."""
from datetime import datetime


def validate_protocol(protocol: dict) -> None:
    if protocol.get('status') != 'frozen_development_only' or protocol.get('live_eligible') is not False:
        raise ValueError('only frozen offline development protocols are supported')
    ranges=protocol['data_policy']
    development_end=datetime.fromisoformat(ranges['development_end'])
    start=datetime.fromisoformat(ranges['final_reserved_start'])
    end=datetime.fromisoformat(ranges['final_reserved_end'])
    if any(t.tzinfo is None for t in (development_end,start,end)) or not development_end<start<end:
        raise ValueError('invalid or overlapping information ranges')
    if not protocol['baseline_pairs'] or not protocol['datasets']:
        raise ValueError('universe and dataset manifest required')
    risk=protocol['portfolio']
    if not 0<float(risk['stake'])<=float(risk['capital']) or risk['max_positions']<1:
        raise ValueError('invalid development capital')


def assert_development_range(protocol: dict, start: datetime, end: datetime):
    validate_protocol(protocol)
    limit=datetime.fromisoformat(protocol['data_policy']['development_end'])
    if start.tzinfo is None or end.tzinfo is None or start>end or end>limit:
        raise ValueError('research may only access frozen development history')


def assert_resources(protocol: dict, available_memory_mb: float, free_disk_mb: float):
    budget=protocol['resources']
    if available_memory_mb<budget['min_available_memory_mb'] or free_disk_mb<budget['min_free_disk_mb']:
        raise ValueError('insufficient resources: defer research, preserve executor')


def assert_executor_compatible(artifact: dict, *, feature_version: str, timeframe: str,
                               horizon: int, threshold: float, target_version: str):
    config=artifact.get('config',{})
    if (artifact.get('feature_version')!=feature_version or config.get('timeframe')!=timeframe or
        config.get('horizon_candles')!=horizon or
        config.get('target_version','fixed-future-return-v1')!=target_version or
        float(artifact.get('threshold',-1))!=threshold):
        raise ValueError('incompatible feature/timeframe/horizon/target/threshold contract')


def prepare_research(path='config/research-protocol-v1.json') -> dict:
    """Apply limits only inside an explicitly launched offline research process."""
    import hashlib
    import json
    from pathlib import Path
    import resource
    import shutil
    import signal
    import os
    import fcntl
    import atexit
    protocol=json.loads(Path(path).read_text())
    validate_protocol(protocol)
    memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    assert_resources(protocol,memory['MemAvailable']/1024,shutil.disk_usage('.').free/1024**2)
    for dataset in protocol['datasets']:
        if hashlib.sha256(Path(dataset['path']).read_bytes()).hexdigest()!=dataset['sha256']:
            raise ValueError('frozen dataset checksum changed: create a new protocol version')
    budget=protocol['resources']
    lock_path=Path('.local/state/offline-research.lock')
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    handle=lock_path.open('a')
    try:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise ValueError('another offline research worker is running')
    atexit.register(handle.close)
    memory_limit=budget['max_worker_memory_mb']*1024**2
    current_soft,current_hard=resource.getrlimit(resource.RLIMIT_AS)
    if current_hard!=resource.RLIM_INFINITY:
        memory_limit=min(memory_limit,current_hard)
    resource.setrlimit(resource.RLIMIT_AS,(memory_limit,current_hard))
    _,file_hard=resource.getrlimit(resource.RLIMIT_FSIZE)
    file_limit=budget['max_output_file_mb']*1024**2
    if file_hard!=resource.RLIM_INFINITY:
        file_limit=min(file_limit,file_hard)
    resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,file_hard))
    os.nice(max(0,budget['worker_nice']-os.getpriority(os.PRIO_PROCESS,0)))
    def timeout(signum,frame):
        raise TimeoutError('offline research exceeded frozen wall-time budget')
    signal.signal(signal.SIGALRM,timeout)
    signal.alarm(budget['max_wall_seconds'])
    return protocol
