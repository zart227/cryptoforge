"""Plan by default; --apply-local explicitly writes local market data."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'scripts'))
from cryptoforge.local_source_provenance import canonical, _new_root, _write_new
from cryptoforge.reference_aware_feeder import build_plan, run_cycle


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--apply-local', action='store_true')
    args = p.parse_args(argv)
    plan = build_plan(ROOT, ROOT/'.local/state/live-universe.json')
    root = _new_root(args.output)
    _write_new(root/'plan.json', plan)
    result = dict(status='plan_only_no_network_or_database_access', primary_database_write_attempted=False,
        services_installed=False, live_admission_granted=False)
    if args.apply_local:
        from database_backend import read_env
        env = dict(os.environ, **read_env(ROOT/'.env'), PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT/'src'))
        bypass = ','.join(filter(None, (env.get('no_proxy',env.get('NO_PROXY','')), '127.0.0.1,localhost,::1')))
        env.update(no_proxy=bypass, NO_PROXY=bypass)
        result = run_cycle(plan, root, env=env)
    pin = _write_new(root/'result.json', result)
    sys.stdout.buffer.write(canonical(dict(root=str(root), result_sha256=pin, **{k:v for k,v in result.items() if k!='stages'}))+b'\n')
    return 0 if not args.apply_local or result['success'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('Reference-aware feeder failed: '+type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
