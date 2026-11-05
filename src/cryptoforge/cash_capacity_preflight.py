"""Metadata-only count/resource preflight; no outcome or execution admission.

Long-horizon counts assume every planned poll/tick is actually completed. They
are required capacity, not observed completeness, forecasts of RSS or returns.
"""
from datetime import UTC,datetime
import os
from pathlib import Path

from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,stamp
from cryptoforge.paired_cash_rehearsal import PairedCashRehearsal,MAXIMUM_SECONDS,MAXIMUM_RUN_SECONDS,_runtime as runner_runtime
from cryptoforge.cash_entry_contract import FLAGS
from cryptoforge.cash_worker_application import CashApplicationPolicy
from cryptoforge.reference_source_ledger import ReferencePolicy
from cryptoforge.reference_delivery import DeliveryPolicy
from cryptoforge.paper_worker_capture_v2 import WorkerCapturePolicyV2
from cryptoforge.paper_capture_v3 import SegmentedLifecycle
from cryptoforge.evidence_segments import SegmentPolicy
from cryptoforge.native_paper_archive_v2 import NativeArchivePolicy
from cryptoforge.paper_wallet_replay_v2 import ReplayPolicyV2


def _runtime():
    value=dict(runner_runtime(),cash_capacity_preflight=digest(Path(__file__).read_bytes()),
        cash_capacity_cli=digest((Path(__file__).resolve().parents[2]/'scripts/check_cash_capacity.py').read_bytes()))
    if '_LOADED' in globals() and value!=_LOADED:raise ValueError('loaded cash capacity runtime changed')
    return value


def _bound(path,pin,maximum=131072):
    raw=read_file(path,maximum=maximum)
    if digest(raw)!=pin:raise ValueError('original capacity metadata pin differs')
    return parse(raw)


def _us(value):
    delta=stamp(value)-datetime(1970,1,1,tzinfo=UTC)
    return ((delta.days*86400+delta.seconds)*1000000+delta.microseconds)


def _ceil(a,b):return (a+b-1)//b


def capacity_preflight(reference,*,requested_start=None,requested_end=None,free_disk_bytes=None):
    runner=PairedCashRehearsal.open(reference);outer=runner.manifest
    if (requested_start is None)!=(requested_end is None):raise ValueError('both requested capacity bounds required')
    start=stamp(requested_start or outer['start']);end=stamp(requested_end or outer['end']);duration=_us(end)-_us(start)
    if not 0<duration<=366*86400*1000000:raise ValueError('bounded positive capacity horizon required')
    if free_disk_bytes is not None and (type(free_disk_bytes) is not int or free_disk_bytes<0):raise ValueError('explicit free disk bytes required')
    source_ref=outer['initial_state']['source'];queue_ref=outer['initial_state']['queue']
    source=_bound(Path(source_ref['root'])/'manifest.json',source_ref['manifest_sha256'])
    queue=_bound(Path(queue_ref['root'])/'manifest.json',queue_ref['manifest_sha256'])
    source_policy=ReferencePolicy(**source['policy']);queue_policy=DeliveryPolicy(**queue['policy'])
    pairs=len(source['pairs']);roles=tuple(outer['workers']);checks=[]
    source_polls=(_us(end)-1)//300000000-_us(start)//300000000+1
    source_events=source_polls*(pairs+2)
    def check(component,metric,required,limit):
        checks.append(dict(component=component,metric=metric,required=required,limit=limit,capacity_pass=required<=limit))
    check('runner','minimum_supported_duration_us',20000000,duration)
    check('runner','maximum_supported_duration_us',duration,MAXIMUM_SECONDS*1000000)
    check('source','events_for_full_poll_coverage',source_events,source_policy.maximum_events)
    minimum_versions=pairs*(120+source_polls-1);maximum_versions=pairs*120*source_polls
    check('source','minimum_versions_without_revisions',minimum_versions,source_policy.maximum_versions)
    check('delivery','source_events',source_events,queue_policy.maximum_source_events)
    check('delivery','whole_poll_batches',source_polls,queue_policy.maximum_batches)
    check('delivery','ingest_offer_ack_events',source_polls*(1+2*len(roles)),queue_policy.maximum_events)
    worker_data={};ticks_by_role={};bytes_budget=source_policy.maximum_database_bytes+queue_policy.maximum_database_bytes+queue_policy.maximum_scratch_database_bytes
    replay_seconds=0
    for role in roles:
        worker_ref=outer['workers'][role];root=Path(worker_ref['root'])
        registered=_bound(root/'registration.json',worker_ref['registration_sha256'])
        worker=_bound(root/'protocol.json',registered['protocol_sha256'])
        if worker['role']!=role or worker['root']!=str(root) or any(worker[k]!=outer[k] for k in ('start','end')):
            raise ValueError('original three-role capacity metadata differs')
        lifecycle=SegmentedLifecycle.from_payload(worker['lifecycle']);storage=SegmentPolicy(**worker['storage_policy'])
        native=NativeArchivePolicy(**worker['native_policy']);capture=WorkerCapturePolicyV2(**worker['capture_policy'])
        app_ref=outer['initial_state']['applications'][role];app=_bound(Path(app_ref['root'])/'manifest.json',app_ref['manifest_sha256'])
        app_policy=CashApplicationPolicy(**app['policy'])
        replay_ref=outer['replays'][role]
        replay=_bound(Path(replay_ref['root'])/'registration.json',replay_ref['replay_registration_sha256'])
        replay_policy=ReplayPolicyV2(**replay['policy'])
        ticks=_ceil(duration,lifecycle.poll_seconds*1000000);ticks_by_role[role]=ticks
        capture_events=ticks*capture.events_per_tick+7
        check(role,'application_groups',ticks,app_policy.maximum_groups)
        check(role,'v1_application_schema_hard_group_limit',ticks,1024)
        check(role,'application_worst_group_bytes_envelope',ticks*app_policy.maximum_group_bytes,app_policy.maximum_bytes)
        check(role,'capture_events_envelope',capture_events,storage.maximum_events)
        segment_capacity=storage.maximum_segments*min(storage.maximum_segment_events,storage.maximum_segment_bytes//storage.maximum_record_bytes)
        check(role,'segment_event_capacity',capture_events,segment_capacity)
        check(role,'minimum_native_marks_and_worker_reports',2*ticks,native.maximum_records)
        worker_data[role]=dict(poll_seconds=lifecycle.poll_seconds,ticks=ticks,events_per_tick_envelope=capture.events_per_tick,
            capture_events_envelope=capture_events,configured_minimum_available_memory_bytes=lifecycle.minimum_available_memory_bytes)
        bytes_budget+=storage.maximum_total_bytes+native.maximum_total_bytes+app_policy.maximum_bytes+replay_policy.maximum_scratch_bytes+1024**2
        replay_seconds+=replay_policy.maximum_wall_seconds
    operations=2*source_polls+sum(ticks_by_role.values())+2*len(roles)
    check('runner','journal_records',2*operations,256)
    original_lead=max(0,_us(outer['start'])-_us(outer['registered_at']))
    wall_seconds=_ceil(original_lead+duration,1000000)+30+replay_seconds
    check('runner','lead_window_endpoint_replay_seconds_envelope',wall_seconds,MAXIMUM_RUN_SECONDS)
    bytes_budget+=256*131072+2048*1024**2
    if free_disk_bytes is None:
        stats=os.statvfs(runner.root);free_disk_bytes=stats.f_bavail*stats.f_frsize
    check('host','configured_caps_scratch_and_disk_reserve_bytes',bytes_budget,free_disk_bytes)
    blockers=[dict(component=v['component'],metric=v['metric'],required=v['required'],limit=v['limit']) for v in checks if not v['capacity_pass']]
    return dict(schema_version='metadata-only-cash-capacity-preflight-v1',observed_at=datetime.now(UTC).isoformat(),
        reference=reference,original_start=outer['start'],original_end=outer['end'],requested_start=start.isoformat(),requested_end=end.isoformat(),
        hypothetical_new_window=(start,end)!=(stamp(outer['start']),stamp(outer['end'])),duration_us=duration,
        assumptions='complete_planned_closed_poll_and_role_tick_coverage_no_claim_of_actual_availability_or_income',
        pair_count=pairs,source_polls=source_polls,source_events=source_events,minimum_versions_without_revisions=minimum_versions,
        maximum_versions_if_every_row_revised=maximum_versions,ticks_by_role=ticks_by_role,worker_data=worker_data,
        coordinator_operations=operations,journal_records=2*operations,configured_caps_plus_reserve_bytes=bytes_budget,
        free_disk_bytes_observed_or_supplied=free_disk_bytes,checks=checks,blockers=blockers,count_and_budget_capacity_pass=not blockers,
        execution_ready=False,new_registration_required=True,metadata_only=True,outcome_stores_read=False,
        observed_memory_or_io_capacity_inferred=False,existing_limits_relaxed=False,runtime=_runtime(),**FLAGS)


_LOADED=_runtime()
