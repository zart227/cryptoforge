"""Inspect diagnostic storage capacity and uncollected price endpoints."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cryptoforge.forecast_memory_health import inspect_forecast_health
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory


def capacity_environment(env_file):
    """Read only the capacity setting; a project file overrides inherited env."""
    env = dict(os.environ)
    if env_file is None:
        return env, 'environment_or_default'
    key = 'CRYPTOFORGE_PRIMARY_FORECAST_MAXIMUM_MB'
    for raw in env_file.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        if name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        env[key] = value
    return env, 'env_file_with_environment_fallback'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--path', type=Path, required=True)
    p.add_argument('--env-file', type=Path, help='read the capacity setting from the specified project environment file')
    args = p.parse_args()
    env, source = capacity_environment(args.env_file)
    memory = PrimaryForecastMemory.from_env(args.path, env=env)
    result = inspect_forecast_health(args.path, maximum_database_bytes=memory.maximum_database_mb * 1024**2)
    result['capacity_configuration_source'] = source
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Forecast health inspection blocked: ' + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
