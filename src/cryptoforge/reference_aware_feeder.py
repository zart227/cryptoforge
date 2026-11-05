"""Opt-in local feeder cycle: mandatory references before dynamic selection.

Planning performs no network/credential/DB access. Applying writes market data
only; it does not install a service or grant strategy/worker admission.
"""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import fcntl
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
from time import monotonic

from cryptoforge.backend import resolve_backend
from cryptoforge.local_source_observer import LocalPostgresObserver
from cryptoforge.local_source_provenance import canonical, digest, validate_observation, _write_new, _sync, parse, read_file, stamp

MANDATORY = ('BTC/USDT', 'ETH/USDT')
MAX_CHILD_BYTES = 65536
MAX_STAGE_SECONDS = 75
MAX_ADDRESS_SPACE = 512*1024**2


def build_plan(repository, universe_file):
    root = Path(repository).absolute()
    universe = Path(universe_file).absolute()
    if root.resolve() != root or universe.resolve() != universe or not universe.is_relative_to(root/'.local/state'):
        raise ValueError('canonical local feeder paths required')
    scripts = root/'scripts'
    common = ['--candle-limit', '121', '--bybit-timeout', '5', '--supabase-timeout', '5']
    stages = [dict(name='reference_'+p.split('/')[0].lower(), pair=p,
        argv=[sys.executable, str(scripts/'sync_supabase_market_data.py'), '--pair', p, *common]) for p in MANDATORY]
    stages += [dict(name='select', pair=None, argv=[sys.executable, str(scripts/'select_live_universe.py'),
        '--output', str(universe), '--limit', '20', '--cheap-shortlist-size', '80',
        '--expensive-shortlist-size', '32', '--candle-limit', '120']),
        dict(name='selected_sync', pair=None, argv=[sys.executable, str(scripts/'sync_supabase_market_data.py'),
            '--live-config', str(universe), *common])]
    paths = dict(reference_aware_feeder=Path(__file__),
        cli=scripts/'run_reference_aware_feeder.py', sync=scripts/'sync_supabase_market_data.py',
        selector=scripts/'select_live_universe.py', market_data=root/'src/cryptoforge/market_data.py',
        scanner=root/'src/cryptoforge/scanner.py',
        market_writer=root/'src/cryptoforge/supabase_market.py',
        backend=root/'src/cryptoforge/backend.py',
        observer=root/'src/cryptoforge/local_source_observer.py',
        provenance=root/'src/cryptoforge/local_source_provenance.py')
    return dict(schema_version='reference-aware-local-feeder-v1', root=str(root), universe_file=str(universe),
        stages=stages, runtime={name:digest(path.read_bytes()) for name,path in paths.items()},
        maximum_stage_seconds=MAX_STAGE_SECONDS, maximum_child_output_bytes=MAX_CHILD_BYTES,
        maximum_child_address_space_bytes=MAX_ADDRESS_SPACE,
        mandatory_reference_pairs=list(MANDATORY), reference_candle_limit=121,
        reason_for_121='public_latest_may_include_one_open_bar_readers_still_require_120_closed',
        live_config_modified=False, services_installed=False, paper_evidence_pass=False,
        economic_profitability_established=False, live_admission_granted=False)


def bounded_stage(argv, env, cwd):
    prlimit = Path('/usr/bin/prlimit')
    if not prlimit.is_file():
        raise ValueError('required child address-space limiter unavailable')
    command = [str(prlimit), f'--as={MAX_ADDRESS_SPACE}', '--', *argv]
    started = monotonic()
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=True, close_fds=True) as child:
        try:
            output = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    left = MAX_STAGE_SECONDS-(monotonic()-started)
                    if left <= 0 or not selector.select(left):
                        raise ValueError('feeder child wall budget exhausted')
                    chunk = os.read(child.stdout.fileno(), min(4096, MAX_CHILD_BYTES+1-len(output)))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_CHILD_BYTES:
                        raise ValueError('feeder child output budget exhausted')
            code = child.wait(timeout=max(.001, MAX_STAGE_SECONDS-(monotonic()-started)))
            return code, bytes(output)
        finally:
            # Kill remaining descendants too; a reaped leader can still have a
            # subprocess holding the output pipe or continuing a failed stage.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


@contextmanager
def _lease(root):
    path = root/'.local/state/reference-aware-feeder.lock'
    fd = os.open(path, os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_nlink != 1:
            raise ValueError('single-link local feeder lease required')
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _reported_sync(raw, expected):
    text = raw.decode('utf-8', errors='strict')
    if any(line.startswith('failed=') for line in text.splitlines()):
        return False
    lines = [line.split('=',1)[1] for line in text.splitlines() if line.startswith('synced_pairs=')]
    return len(lines) == 1 and set(filter(None, lines[0].split(','))) == set(expected)


def _cooldown_path(root):
    return root/'.local/state/reference-aware-feeder-cooldown.json'


def _now():
    return datetime.now(UTC)


def _cooldown(root):
    path = _cooldown_path(root)
    if path.resolve() != path or path.is_symlink():
        raise ValueError('canonical feeder cooldown state required')
    if not path.exists():
        return None
    value = parse(read_file(path, maximum=4096))
    at, until = stamp(value['observed_at']), stamp(value['blocked_until'])
    if set(value) != {'observed_at','blocked_until'} or until-at != timedelta(minutes=10) or _now() < at:
        raise ValueError('original feeder cooldown/clock differs')
    return value if _now() < until else None


def _rate_pause(raw):
    text = raw.decode('utf-8', errors='replace').lower()
    return any(marker in text for marker in ('rate-limit', 'rate limited', 'http 403', 'http 429', '10006', '10429'))


def _pause(root):
    at = _now()
    value = dict(observed_at=at.isoformat(), blocked_until=(at+timedelta(minutes=10)).isoformat())
    path = _cooldown_path(root)
    temporary = path.with_name('.'+path.name+'.tmp')
    fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary, path)
    _sync(path.parent)
    return value


def run_cycle(plan, output_root, *, env, invoke=None, observe=None):
    """Explicit write-capable path. Both references are attempted independently.

    Selection begins only after both sync receipts AND closed120 SQL probes pass.
    Partial selected-sync success is failure, even when the old CLI exits zero.
    """
    root = Path(plan['root'])
    output_root = Path(output_root).absolute()
    if output_root.resolve() != output_root or not output_root.is_dir() or {p.name for p in output_root.iterdir()}-{'plan.json'}:
        raise ValueError('new unused feeder cycle output required; no silent resume')
    if (output_root/'plan.json').exists() and (output_root/'plan.json').read_bytes() != canonical(plan):
        raise ValueError('original feeder plan differs')
    if plan != build_plan(root, Path(plan['universe_file'])):
        raise ValueError('feeder plan/runtime differs')
    if resolve_backend(env).name != 'local':
        raise ValueError('explicit local backend required; no fallback')
    invoke = invoke or bounded_stage
    observe = observe or (lambda pair: LocalPostgresObserver(root).read(pair=pair, limit=120))
    results, identity, selected_pairs, paused, attempted = [], None, None, None, False
    with _lease(root):
        paused = _cooldown(root)
        for number, stage in enumerate(plan['stages'], 1):
            if paused:
                break
            if shutil.disk_usage(output_root).free < 2048*1024**2+16*1024**2:
                raise ValueError('feeder disk reserve preserved')
            if number > 2 and not all(row['success'] for row in results):
                break
            if plan != build_plan(root, Path(plan['universe_file'])):
                raise ValueError('feeder runtime changed during cycle')
            try:
                argv = list(stage['argv'])
                if stage['name'] == 'selected_sync':
                    argv[argv.index('--live-config')+1] = str(Path(output_root)/'selected-universe.json')
                attempted = attempted or stage['name'] != 'select'
                code, raw = invoke(argv, env, root)
                if plan != build_plan(root, Path(plan['universe_file'])):
                    raise ValueError('feeder runtime changed during child stage')
                if type(code) is not int or type(raw) is not bytes or len(raw) > MAX_CHILD_BYTES:
                    raise ValueError('bounded typed feeder stage result required')
                if _rate_pause(raw):
                    paused = _pause(root)
                ok = code == 0
                observation = None
                if stage['pair']:
                    ok = ok and _reported_sync(raw, [stage['pair']])
                    if ok:
                        observed = observe(stage['pair'])
                        facts = validate_observation(observed)
                        ok = (facts['candle_freshness_pass'] is True and len(facts['records']) == 120
                            and facts['query']['pair'] == stage['pair'] and facts['query']['timeframe'] == '5m')
                        current_identity = (facts['identity_sha256'], facts['schema_sha256'])
                        ok = ok and (identity is None or current_identity == identity)
                        identity = identity or current_identity
                        observation = dict(raw_observation=observed, original_integrity_sha256=digest(canonical(facts)))
                elif stage['name'] == 'select' and ok:
                    universe = parse(read_file(Path(plan['universe_file']), maximum=4*1024**2))
                    pairs = universe['pairs']
                    ok = (type(pairs) is list and 0 < len(pairs) <= 20
                        and all(type(p) is str and re.fullmatch('[A-Z0-9]{1,24}/USDT', p) for p in pairs)
                        and len(set(pairs)) == len(pairs))
                    if ok:
                        selected_pairs = pairs
                        _write_new(Path(output_root)/'selected-universe.json', dict(pairs=pairs))
                elif stage['name'] == 'selected_sync' and ok:
                    ok = _reported_sync(raw, selected_pairs)
                result = dict(stage=stage['name'], success=ok, exit_code=code,
                    output_bytes=len(raw), output_sha256=digest(raw), observation=observation)
            except Exception as exc:
                result = dict(stage=stage['name'], success=False, error_type=type(exc).__name__)
            _write_new(Path(output_root)/f'stage-{number}.json', result)
            results.append(result)
        success = len(results) == 4 and all(r['success'] for r in results)
        return dict(success=success, reference_refresh_verified=len(results)>=2 and all(r['success'] for r in results[:2]),
            stages=results, primary_database_write_attempted=attempted, venue_cooldown=paused,
            scope='one_opt_in_cycle_not_continuous_source_or_rest_instance_qualification',
            full_worker_or_host_qualified=False, services_installed=False,
            economic_profitability_established=False, paper_evidence_pass=False, live_admission_granted=False)
