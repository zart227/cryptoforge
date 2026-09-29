"""Windows paper-only supervisor: one instance, bounded restart backoff."""
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    config_path = ROOT / 'config/freqtrade.active-paper.json'
    config = json.loads(config_path.read_text())
    if config.get('dry_run') is not True or config.get('trading_mode') != 'spot':
        raise ValueError('Supervisor requires paper Spot configuration')
    # Do not inherit live database, keys or trading overrides from another shell.
    env = {k: v for k, v in os.environ.items() if not k.startswith('FREQTRADE__')}
    lock_path = ROOT / 'data/live-pilot/paper-supervisor.lock'
    with lock_path.open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        delay = 5
        for attempt in range(10):
            started = time.monotonic()
            result = subprocess.run([sys.executable, '-m', 'freqtrade', 'trade',
                '--config', str(config_path), '--userdir', 'user_data',
                '--dry-run', '--db-url', 'sqlite:///./data/live-pilot/tradesv3.paper.sqlite',
                '--logfile', 'logs/freqtrade-active-paper.log', '--no-color'], env=env)
            if result.returncode == 0:
                return 0
            print(f'Paper worker exited ({result.returncode}); attempt {attempt + 1}/10', flush=True)
            if attempt == 9:
                return result.returncode
            if time.monotonic() - started > 300:
                delay = 5
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return 1


if __name__ == '__main__':
    sys.exit(main())
