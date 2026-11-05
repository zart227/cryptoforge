"""Read-only inspection of one original incomplete managed feeder cycle.

The report never authorizes a retry or infers whether a missing stage wrote to
the database. It does not open a database, invoke a provider, or repair files.
"""
from pathlib import Path
import re

from cryptoforge.local_source_provenance import canonical, digest, parse, read_file, stamp, validate_observation
from cryptoforge.managed_reference_feeder import ManagedReferenceFeeder, _inventory
from cryptoforge.reference_aware_feeder import build_plan, MAX_CHILD_BYTES


def inspect_incomplete_feeder(reference, cycle, *, clock=None):
    obj = ManagedReferenceFeeder.open(reference, clock=clock)
    if type(cycle) is not str or not re.fullmatch(r'cycle-[0-9a-f]{32}', cycle):
        raise ValueError('original cycle identifier required')
    folder = obj.root / 'cycles' / cycle
    if folder.resolve() != folder or not folder.is_dir() or folder.is_symlink():
        raise ValueError('original cycle directory required')
    with obj._lease():
        obj._check()
        if (folder / 'complete.json').exists():
            raise ValueError('cycle already has a completion receipt')
        inventory = _inventory(folder)
        if sum(value['bytes'] for value in inventory.values()) > obj.policy.maximum_cycle_bytes:
            raise ValueError('cycle exceeds original byte budget')
        def read(name, limit):
            raw = read_file(folder / name, maximum=limit)
            if digest(raw) != inventory[name]['sha256']:
                raise ValueError('cycle file changed during inspection')
            value = parse(raw)
            if raw != canonical(value):
                raise ValueError('canonical original cycle receipt required')
            return value
        if 'started.json' not in inventory:
            raise ValueError('original cycle start receipt missing')
        started = read('started.json', 65536)
        if started.get('registration') != reference or not stamp(obj.manifest['registered_at']) <= stamp(started['started_at']) <= stamp(obj.clock()):
            raise ValueError('cycle start/registration differs')
        before_present = 'before.json' in inventory
        if before_present:
            before = read('before.json', 4 * 1024**2)
            if (before.get('rest_instance_identity_verified') is not True
                    or before.get('row_binding', {}).get('sql_identity_sha256') != obj.manifest['sql_identity_sha256']):
                raise ValueError('cycle original precheck identity differs')
        plan = build_plan(Path(obj.manifest['repository']), Path(obj.manifest['repository']) / '.local/state/live-universe.json')
        plan_present = 'run/plan.json' in inventory
        if plan_present and read('run/plan.json', 65536) != plan:
            raise ValueError('original cycle plan/runtime differs')
        if any(re.fullmatch(r'run/stage-[0-9]+\.json', name) and name not in
               {f'run/stage-{n}.json' for n in range(1, 5)} for name in inventory):
            raise ValueError('unexpected stage receipt')
        stage_names = [value['name'] for value in plan['stages']]
        recorded = []; missing = False
        for number, expected in enumerate(plan['stages'], 1):
            name = f'run/stage-{number}.json'
            if name not in inventory:
                missing = True;continue
            if missing or not plan_present or not before_present:
                raise ValueError('cycle contains noncontiguous stage receipts')
            if number > 2 and any(not previous['reported_success'] for previous in recorded):
                raise ValueError('stage occurred after failed prerequisite')
            stage = read(name, 16 * 1024**2)
            if stage.get('stage') != expected['name'] or type(stage.get('success')) is not bool:
                raise ValueError('cycle stage receipt differs')
            if stage['success']:
                if (stage.get('exit_code') != 0 or type(stage.get('output_bytes')) is not int
                        or not 0 <= stage['output_bytes'] <= MAX_CHILD_BYTES
                        or not re.fullmatch('[0-9a-f]{64}', str(stage.get('output_sha256', '')))):
                    raise ValueError('successful stage receipt differs')
            original_observation_valid = False
            if stage['success'] and expected['pair']:
                obs = stage.get('observation')
                if type(obs) is not dict:
                    raise ValueError('original source observation missing')
                facts = validate_observation(obs['raw_observation'])
                if (digest(canonical(facts)) != obs['original_integrity_sha256']
                        or facts['query']['pair'] != expected['pair'] or facts['candle_freshness_pass'] is not True
                        or len(facts['records']) != 120):
                    raise ValueError('original source observation differs')
                original_observation_valid = True
            if stage['success'] and expected['name'] == 'select':
                selected = read('run/selected-universe.json', 65536)
                pairs = selected.get('pairs')
                if (set(selected) != {'pairs'} or type(pairs) is not list or not 1 <= len(pairs) <= 20
                        or len(set(pairs)) != len(pairs)
                        or any(type(pair) is not str or not re.fullmatch('[A-Z0-9]{1,24}/USDT', pair) for pair in pairs)):
                    raise ValueError('original selected universe differs')
            recorded.append(dict(stage=expected['name'], reported_success=stage['success'],
                                 observation_integrity_pass=original_observation_valid,
                                 output_original_bytes_available=False))
        next_stage = stage_names[len(recorded)] if len(recorded) < len(stage_names) else None
        if next_stage is None:
            effect = 'completion_missing_after_recorded_stages'
        elif len(recorded) >= 2 and any(not stage['reported_success'] for stage in recorded):
            effect = 'not_attempted_under_recorded_stage_control_flow'
        else:
            effect = 'unknown_stage_effect'
        final_inventory = _inventory(folder)
        if final_inventory != inventory or (folder / 'complete.json').exists():
            raise ValueError('cycle changed during inspection')
        return dict(reference=reference, cycle=cycle, observed_at=stamp(obj.clock()).isoformat(), started_at=started['started_at'],
                    precheck_receipt_present=before_present, plan_receipt_present=plan_present,
                    recorded_stages=recorded, first_missing_stage=next_stage, effect=effect,
                    retained_files=inventory, stage_output_reverified=False,
                    current_database_compared=False, retry_authorized=False, source_modified=False,
                    live_admission_granted=False, economic_profitability_established=False)
