"""Readonly API/exchange usage reconciliation, including rejected completions.

No historical debit is applied. Native reported usage is evidence, not an account
invoice or a new allowance. Separate journals are never silently summed together.
"""
import argparse
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import os
from pathlib import Path
import sqlite3
import stat

from cryptoforge import llm_audited_provider as capture
from cryptoforge import research_phase_semantic_cli as existing
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest

TOKEN_FIELDS=('prompt_tokens','completion_tokens','total_tokens')


def implementation():
    return {'usage':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'capture_sha256':digest(capture.implementation()),
        'existing_files_sha256':hashlib.sha256(Path(existing.__file__).read_bytes()).hexdigest()}


_LOADED=implementation()


def _guard():
    if implementation()!=_LOADED:raise ValueError('exchange_usage_source_changed')


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _tokens(value):
    result={k:None for k in TOKEN_FIELDS};invalid=[]
    if value is None:return result,invalid
    if type(value) is not dict:return result,['native_usage_not_an_object']
    for key in TOKEN_FIELDS:
        count=value.get(key)
        if count is None:continue
        if type(count) is not int or not 0<=count<=10000000:invalid.append('invalid_'+key)
        else:result[key]=count
    if all(v is not None for v in result.values()) and result['total_tokens']!=result['prompt_tokens']+result['completion_tokens']:
        invalid.append('inconsistent_native_total')
    return result,invalid


def _journal(path):
    path=existing.existing(path);info=path.stat()
    if stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():raise ValueError('private_original_API_journal_required')
    sidecars=[Path(str(path)+suffix) for suffix in ('-wal','-shm','-journal')]
    if any(p.exists() or p.is_symlink() for p in sidecars):raise ValueError('quiescent_standalone_API_journal_required')
    before=_sha(path);db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=5)
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        objects=set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))
        if objects!={('table','request_policy'),('table','advisor_requests')}:raise ValueError('original_API_tables_required')
        policy=db.execute('SELECT id,maximum FROM request_policy').fetchall()
        if len(policy)!=1 or policy[0][0]!=1 or type(policy[0][1]) is not int or not 1<=policy[0][1]<=20:
            raise ValueError('original_API_policy_required')
        rows=db.execute('SELECT key,utc_day,status,request,payload,payload_sha256 FROM advisor_requests ORDER BY key LIMIT 4097').fetchall()
        if len(rows)>4096:raise ValueError('bounded_API_history_required')
    finally:db.close()
    if _sha(path)!=before or any(p.exists() or p.is_symlink() for p in sidecars):raise ValueError('API_journal_changed_during_readonly_snapshot')
    records=[]
    for key,day,status,request_raw,payload_raw,payload_sha in rows:
        inputs=strict_json(request_raw,max_bytes=128000)
        if (type(inputs) is not dict or digest(inputs)!=key or status not in ('completed','failed','timed_out','cancelled','reserved')
                or inputs.get('provider') not in ('openrouter','ollama') or type(inputs.get('model')) is not str
                or not 1<=len(inputs['model'])<=200 or type(inputs.get('report')) is not dict):
            raise ValueError('original_API_request_identity_required')
        if type(day) is not str or date.fromisoformat(day).isoformat()!=day:raise ValueError('original_API_day_required')
        report_sha=digest(inputs['report']);payload=None
        if status=='completed':
            payload=strict_json(payload_raw,max_bytes=512000)
            if type(payload) is not dict or digest(payload)!=payload_sha or payload['report_sha256']!=report_sha:
                raise ValueError('original_completed_API_payload_required')
        elif payload_raw is not None or payload_sha is not None:
            raise ValueError('failed_API_payload_not_native')
        tokens,errors=_tokens(payload.get('usage') if payload is not None else None)
        reference=payload.get('exchange_capture',{}) if payload is not None else {}
        if type(reference) is not dict:raise ValueError('normalized_capture_reference_object_required')
        claims=reference.get('available') is True
        if claims and (reference.get('request_key')!=key or any(not capture._sha(reference.get(k))
                for k in ('capture_sha256','exchange_manifest_sha256'))):raise ValueError('original_normalized_capture_reference_required')
        records.append({'request_key':key,'utc_day':day,'API_status':status,'provider':inputs['provider'],
            'requested_model_sha256':digest(inputs['model']),'report_sha256':report_sha,'usage':tokens,'usage_errors':errors,
            'usage_origin':'normalized_completed_cache' if payload is not None else 'no_normalized_completed_payload',
            'wire_capture_available':False,'provider_reported_native_credits':None,
            'local_outcome':None,'capture_sha256':None,
            'cache_claims_capture':claims,'recorded_capture_sha256':reference.get('capture_sha256') if claims else None,
            'recorded_exchange_manifest_sha256':reference.get('exchange_manifest_sha256') if claims else None})
    return {'API_journal_path_sha256':digest(str(path)),'file_sha256':before,'persisted_daily_maximum':policy[0][1],
        'read_only_snapshots':1,'explicit_SQL_statements':5,'records':records}


def reconcile(journals,capture_directories=()):
    _guard()
    if type(journals) is not list or not 1<=len(journals)<=16 or type(capture_directories) not in (list,tuple) or len(capture_directories)>64:
        raise ValueError('bounded_explicit_usage_inputs_required')
    sources=[_journal(Path(path)) for path in journals]
    if len({s['API_journal_path_sha256'] for s in sources})!=len(sources):raise ValueError('unique_original_journals_required')
    indexed={(s['API_journal_path_sha256'],r['request_key']):r for s in sources for r in s['records']}
    seen={};duplicates=0
    for directory in capture_directories:
        checked=capture.verify_attempt(directory);binding=checked['binding'];identity=(binding['API_journal_path_sha256'],binding['request_key'])
        if identity not in indexed:raise ValueError('capture_requires_its_original_API_journal_and_row')
        row=indexed[identity]
        if (any(row[k]!=binding[k] for k in ('report_sha256','provider'))
                or row['requested_model_sha256']!=digest(binding['requested_model'])):
            raise ValueError('capture_and_API_identity_mismatch')
        evidence={'capture_sha256':checked['capture_sha256'],'validation':checked['validation'],'local_outcome':checked['local_outcome']}
        if identity in seen:
            if seen[identity]!=evidence:raise ValueError('conflicting_capture_copies_for_one_attempt')
            duplicates+=1;continue
        seen[identity]=evidence;row['local_outcome']=checked['local_outcome']['status'];row['capture_sha256']=checked['capture_sha256']
        if checked['capture_available']:
            if row['API_status']=='completed':
                if not row['cache_claims_capture']:raise ValueError('legacy_completed_cache_cannot_be_upgraded_to_original_wire')
                manifest=capture._read(Path(directory)/'exchange','manifest.json')
                if (row['recorded_capture_sha256']!=checked['capture_sha256']
                        or row['recorded_exchange_manifest_sha256']!=digest(manifest)):
                    raise ValueError('original_cache_capture_reference_mismatch')
            validation=checked['validation'];tokens,errors=_tokens(validation['usage'])
            # On a successful cache, normalized fields must agree with the body.
            # A missing normalized field is a gap, never proof of zero usage.
            if row['API_status']=='completed' and any(row['usage'][k] is not None and row['usage'][k]!=tokens[k] for k in TOKEN_FIELDS):
                raise ValueError('normalized_and_captured_usage_disagree')
            cost=capture.audit._cost({'cost':validation['provider_reported_cost_usd']})
            row.update(usage=tokens,usage_errors=sorted(set(errors+validation['usage_errors'])),
                usage_origin='cleaned_original_transport_response',wire_capture_available=True,
                exchange_validation=validation['status'],provider_reported_native_credits=cost)
    summaries=[]
    for source in sources:
        records=source['records'];known={k:sum(r['usage'][k] for r in records if r['usage'][k] is not None) for k in TOKEN_FIELDS}
        unknown={k:sum(r['usage'][k] is None for r in records) for k in TOKEN_FIELDS}
        costs=[r['provider_reported_native_credits'] for r in records if r['provider_reported_native_credits'] is not None]
        with localcontext() as context:
            context.prec=80;cost_total=str(sum((Decimal(v) for v in costs),Decimal(0)))
        summaries.append({'API_journal_path_sha256':source['API_journal_path_sha256'],'file_sha256':source['file_sha256'],
            'persisted_daily_maximum':source['persisted_daily_maximum'],'attempts':len(records),
            'known_native_token_subtotals':known,'unknown_token_attempts_by_field':unknown,
            'known_native_credit_subtotal':cost_total,'known_credit_attempts':len(costs),'unknown_credit_attempts':len(records)-len(costs),
            'original_exchange_captures':sum(r['wire_capture_available'] for r in records),
            'completed_payloads_without_provided_original_wire':sum(r['API_status']=='completed' and not r['wire_capture_available'] for r in records),
            'status_disagreements':[r['request_key'] for r in records if r['local_outcome'] is not None and r['local_outcome']!=r['API_status']],
            'read_only_snapshots':1,'explicit_SQL_statements':5,'records':records})
    core={'schema_version':'readonly-exchange-usage-reconciliation-v1','implementation':_LOADED,'journals':summaries,
        'duplicate_capture_copies_not_counted_twice':duplicates,'captured_attempts':len(seen),
        'cross_journal_global_total':None,'account_invoice_or_jobpilot_global_spend_verified':False,
        'catalog_zero_price_is_reported_charge':False,'native_credit_values_are_USD_invoice':False,
        'unknown_values_mean_zero':False,'common_budget_debits_applied':False,'new_allowance_or_refund':False,
        'provider_requests_credentials_model_or_journal_write_actions':0}
    _guard();return {**core,'report_sha256':digest(core)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--journal',type=Path,action='append',required=True)
    parser.add_argument('--capture-directory',type=Path,action='append',default=[]);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);output=args.output.absolute()
    if output.parent.resolve()!=output.parent or any(output.resolve()==p.resolve() or output.resolve().is_relative_to(p.resolve()) for p in args.journal+args.capture_directory):
        parser.error('output_must_be_separate_from_original_inputs')
    try:
        result=reconcile(args.journal,args.capture_directory)
        with os.fdopen(os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600),'w') as stream:
            stream.write(canonical(result)+'\n');stream.flush();os.fsync(stream.fileno())
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,sqlite3.Error):
        print('Usage reconciliation refused; no debit, refund or allowance applied');return 2
    print('Readonly per-journal usage saved; unknown usage and global account totals remain explicit');return 0


if __name__=='__main__':raise SystemExit(main())
