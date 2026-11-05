"""Native source-value compatibility evidence; no fit, prediction or data admission."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import math
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_revision_bridge as revisions
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge import research_data_protocol as temporal, research_local_export as private
from cryptoforge import semantic_source_collector as files
from cryptoforge.training_diagnostics import canonical, digest, exact_fields


REVIEWED_VALUE_RUNTIME = {'bybit_private': 'b1695348785e1f418a50e4b6dafb6302a6e96dd9871f67b6fe1a1c11b7df8ade',
 'candle_contract': '31d8e205bcf37d56b82939a6e0c96e3f4bcc251ee8344a95c2c4e0cdd23b9ca4',
 'cryptoforge': 'b86a73500010a249293fdddaee182c18773a0b942f2d0d919718b73456fe2bd6',
 'market_data': '1f2df39adca641db0f0d987375ade7eeceab80b82d84091c6012e99eeedff46a',
 'model_training': '9afb8aab375ec786aa8f9c9a7f617a5db642e49fcfbf45d311a413a05e63aeb7',
 'night_research': '672e1686043c5e62e020ea57f28160ad1d951b9eba3b54d68d03f9dda3a527ff',
 'night_research_cli': '3c302ce4cd291579cb66960d8b2dd5e4f6b0faedf9fcd915905f4e8fa727b6d0',
 'order_observer': '8f2ed2fce69ee412e8378ae77b7e296b9c9e8f5b5d281d1a5ccca9280fd78190',
 'supabase_executor': 'b3a8530632498fc1291f1eecd2aae085b58fc6f4bc2a4b8c89c5bfcf4eb1910c',
 'supabase_market': '458d0792427d412e86c48df19d5aab38b7ddb1b37019cce6a7c4fcc52fbed435',
 'target_contracts': '7f24650731e5e5896e54848c37e10de7a108ac8fda9fb89963cb3a307a35550d'}
POLICY = {'schema_version': 'research-value-audit-policy-v1', 'maximum_samples': 16,
    'maximum_packet_bytes': 2097152, 'maximum_result_bytes': 262144,
    'decimal_precision': 28, 'decimal_rounding': 'ROUND_HALF_EVEN',
    'feature_order': ['return_1','return_3','range_12','volume_ratio','ema_gap','rsi_14','candle_body'],
    'reviewed_value_runtime': REVIEWED_VALUE_RUNTIME, 'training_admission_enabled': False}
TARGET_FIELDS = {'schema_version', 'target_version', 'min_label_return', 'round_trip_cost', 'fee_accounting'}
TARGET = {'schema_version': 'research-price-value-target-v1', 'target_version': 'fixed-future-return-v1',
    'min_label_return': '0.003', 'round_trip_cost': '0.002', 'fee_accounting': 'price_return_excludes_execution_fees'}


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': hashlib.sha256(Path(__file__).with_name('research_value_worker.py').read_bytes()).hexdigest(),
        'revision_bridge': revisions.implementation(),
        'fraction_reference': hashlib.sha256(Path(sys.modules[Fraction.__module__].__file__).read_bytes()).hexdigest()}


_LOADED = implementation()


def _guard(policy):
    if canonical(policy) != canonical(POLICY): raise ValueError('fixed_value_audit_policy_required')
    if implementation() != _LOADED: raise ValueError('value_audit_source_changed_restart_required')


def validate_target(target):
    exact_fields(target, TARGET_FIELDS)
    if any(target[k] != TARGET[k] for k in ('schema_version','target_version','fee_accounting')):
        raise ValueError('explicit_price_target_required')
    for name in ('min_label_return', 'round_trip_cost'):
        value = target[name]
        if type(value) is not str or re.fullmatch(r'0(?:\.\d{1,12})?', value) is None or not 0 <= Decimal(value) <= Decimal('0.1'):
            raise ValueError('bounded_decimal_target_parameter_required')
    if Decimal(target['min_label_return']) < Decimal(target['round_trip_cost']):
        raise ValueError('label_threshold_below_declared_cost')


def main_profile(project):
    source = revisions.main_profile(project); values = {}
    for name in REVIEWED_VALUE_RUNTIME:
        values[name] = hashlib.sha256(reviewed_main.reviewed_value_module_bytes(project, name)).hexdigest()
    if values != REVIEWED_VALUE_RUNTIME: raise ValueError('native_value_runtime_requires_review')
    return {'source': source, 'values': values}


def bind_source_pack(directory):
    directory = private._safe_directory(directory, private=True)
    report = revisions.verify(directory)
    names = ('policy.json','projection.json','protocol.json','exposure.json','context.json','audit.json')
    hashes = {n: hashlib.sha256(private._private_read(directory,n,temporal.POLICY['max_report_bytes'])).hexdigest() for n in names}
    projection = temporal._read(directory,'projection.json',revisions.POLICY['maximum_projection_bytes'])
    protocol = temporal._read(directory,'protocol.json',64000)
    context = temporal._read(directory,'context.json',64000)
    if len(report['samples']) > POLICY['maximum_samples']: raise ValueError('value_audit_sample_budget_exceeded')
    _, timeline = revisions.validate_projection(projection,protocol,context)
    index = {}
    for row in timeline: index.setdefault((row['symbol'],row['open_time']),[]).append(row)
    selections = []
    for i,sample in enumerate(report['samples']):
        anchor = temporal._time(sample['decision_anchor']); decision = temporal._time(sample['decision_time'])
        cutoff = temporal._time(protocol['fit_information_end' if sample['partition']=='train' else 'validation_information_end'])
        groups = []
        for name, opens, limit in (('feature',[anchor-timedelta(minutes=5*(120-j)) for j in range(120)],decision),
                                  ('label',[anchor+timedelta(minutes=5*j) for j in range(3)],cutoff)):
            chosen = [temporal._choose(index,sample['symbol'],opened,limit) for opened in opens]
            unavailable = any(error for _,error in chosen)
            if name == 'feature' and 'mandatory_reference_unavailable_or_stale' in sample['issues']: unavailable = True
            if name == 'label' and any(k in sample['issues'] for k in ('label_crosses_next_partition_purge','label_not_complete_by_information_cutoff')): unavailable = True
            groups.append(None if unavailable else [row for row,_ in chosen])
        selections.append({'id': i, 'partition': sample['partition'], 'symbol': sample['symbol'],
            'decision_anchor': sample['decision_anchor'], 'decision_time': sample['decision_time'],
            'label_end_time': sample['label_end_time'], 'information_end': cutoff.isoformat(),
            'metadata_issues': sample['issues'], 'features': groups[0], 'labels': groups[1]})
    binding = {'schema_version': 'research-value-source-binding-v1', 'directory': str(directory),
        'files': hashes, 'revision_audit_sha256': report['audit_sha256'], 'projection_sha256': digest(projection)}
    return binding, projection['reference'], selections


def _native(project, reference, selections, target, directory):
    packet = {'reference': reference, 'selections': selections, 'target': target}
    if len(canonical(packet).encode()) > POLICY['maximum_packet_bytes']: raise ValueError('value_audit_packet_byte_limit')
    files._write(directory,'packet.json',packet)
    args = [sys.executable,'-B',str(Path(__file__).with_name('research_value_worker.py')),
            '--input',str(directory/'packet.json'),'--output',str(directory/'native.json')]
    env = {'PATH':'/usr/bin:/bin','PYTHONPATH':reviewed_main.worker_pythonpath(project),'PYTHONDONTWRITEBYTECODE':'1',
           'PYTHONHASHSEED':'0','LANG':'C.UTF-8','TZ':'UTC'}
    proc = None
    import os
    with os.fdopen(os.open(directory/'worker.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
        try:
            proc = subprocess.Popen(args,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=stream,
                stderr=stream,start_new_session=True,preexec_fn=revisions._limits)
            if proc.wait(timeout=15) != 0: raise ValueError('native_value_compatibility_refused')
            return temporal._read(directory,'native.json',POLICY['maximum_result_bytes'])
        finally:
            if proc is not None:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                proc.wait()


def _hex(value):
    if type(value) is not str or len(value)>40: raise ValueError('bounded_float_hex_required')
    try: number = float.fromhex(value)
    except ValueError: raise ValueError('float_hex_required') from None
    if not math.isfinite(number) or number.hex() != value: raise ValueError('finite_canonical_float_hex_required')
    return number


def _endpoint(value):
    if type(value) is not str or len(value)>64 or re.fullmatch(r'\d{1,36}(?:\.\d{1,24})?',value) is None or Decimal(value)<=0:
        raise ValueError('bounded_exact_endpoint_quote_required')
    return Fraction(Decimal(value))


def compose(binding,reference,selections,target,native,policy=POLICY):
    _guard(policy); validate_target(target)
    exact_fields(native,{'schema_version','reference','selections_sha256','target_sha256','loaded_value_runtime',
        'loaded_source_runtime','feature_names','decimal_precision','decimal_rounding','target_contract',
        'source_rows_read','samples','fit_performed','model_prediction_performed','network_request_performed','source_modified'})
    expected_contract = {'version':'fixed-future-return-v1','outcome_kind':'future_close_price_return',
        'fee_accounting':'price_return_excludes_execution_fees','sample_kind':'candle_endpoint','short_labels_allowed':True}
    if (native['schema_version']!='research-native-values-v1' or native['reference']!=reference
            or native['selections_sha256']!=digest(selections) or native['target_sha256']!=digest(target)
            or native['loaded_value_runtime']!=REVIEWED_VALUE_RUNTIME or native['loaded_source_runtime']!=revisions.POLICY['reviewed_sources']
            or native['feature_names']!=POLICY['feature_order'] or native['decimal_precision']!=28
            or native['decimal_rounding']!='ROUND_HALF_EVEN' or native['target_contract']!=expected_contract
            or any(native[k] is not False for k in ('fit_performed','model_prediction_performed','network_request_performed','source_modified'))
            or type(native['samples']) is not list or len(native['samples'])!=len(selections)):
        raise ValueError('fixed_native_value_contract_required')
    summaries = []; rows_read = 0
    feature_count = training_count = mismatch_count = 0
    threshold = float(Decimal(target['min_label_return']))
    for selection,result in zip(selections,native['samples']):
        exact_fields(result,{'id','feature_status','runtime_feature_hex','extractor_feature_hex','runtime_contract',
            'training_status','training_feature_hex','future_return_hex','long_label','short_label','reference_close',
            'future_close','label_end_time','training_input_end_time'})
        if result['id'] != selection['id']: raise ValueError('fixed_sample_order_required')
        feature_available = selection['features'] is not None
        training_available = feature_available and selection['labels'] is not None
        if result['feature_status'] != ('checked' if feature_available else 'unavailable') or result['training_status'] != ('checked' if training_available else 'unavailable'):
            raise ValueError('missing_values_cannot_be_fabricated')
        feature_match = training_match = return_match = None; reference_hex = None; independent_labels = None
        if feature_available:
            feature_count += 1; rows_read += 120
            for key in ('runtime_feature_hex','extractor_feature_hex'):
                if type(result[key]) is not list or len(result[key])!=7: raise ValueError('seven_native_features_required')
                for value in result[key]: _hex(value)
            expected = {'feature_version':'candle-v1','timeframe':'5m','input_candle_state':'closed_only',
                        'calculation_contract':'bounded-window-candle-v1','lookback_candles':120}
            if result['runtime_contract']!=expected: raise ValueError('resolved_runtime_contract_required')
            feature_match = result['runtime_feature_hex']==result['extractor_feature_hex']
        elif any(result[k] is not None for k in ('runtime_feature_hex','extractor_feature_hex','runtime_contract')):
            raise ValueError('unavailable_feature_values_must_stay_null')
        if training_available:
            training_count += 1; rows_read += 3
            if type(result['training_feature_hex']) is not list or len(result['training_feature_hex'])!=7: raise ValueError('seven_training_features_required')
            for value in result['training_feature_hex']: _hex(value)
            native_return = _hex(result['future_return_hex'])
            if any(type(result[k]) is not int or result[k] not in (0,1) for k in ('long_label','short_label')): raise ValueError('binary_native_labels_required')
            if result['label_end_time']!=selection['label_end_time'] or temporal._time(result['training_input_end_time'])!=temporal._time(selection['decision_anchor'])-timedelta(minutes=5):
                raise ValueError('native_label_endpoint_time_mismatch')
            exact_return = (_endpoint(result['future_close'])-_endpoint(result['reference_close']))/_endpoint(result['reference_close'])
            reference_return = float(exact_return); reference_hex = reference_return.hex()
            independent_labels = [int(reference_return>threshold),int(reference_return< -threshold)]
            return_match = result['future_return_hex']==reference_hex and [result['long_label'],result['short_label']]==independent_labels
            training_match = result['training_feature_hex']==result['runtime_feature_hex']
        elif any(result[k] is not None for k in ('training_feature_hex','future_return_hex','long_label','short_label','reference_close','future_close','label_end_time','training_input_end_time')):
            raise ValueError('unavailable_training_values_must_stay_null')
        mismatch = any(v is False for v in (feature_match,training_match,return_match))
        mismatch_count += int(mismatch)
        summaries.append({'id':selection['id'],'partition':selection['partition'],'symbol':selection['symbol'],
            'decision_time':selection['decision_time'],'metadata_issues':selection['metadata_issues'],
            'feature_values_checked':feature_available,'training_values_checked':training_available,
            'extractor_runtime_bit_parity':feature_match,'training_runtime_bit_parity':training_match,
            'fraction_return_hex':reference_hex,'fraction_return_and_labels_match_native':return_match,
            'fraction_float_domain_labels':independent_labels,'numeric_mismatch':mismatch})
    if type(native['source_rows_read']) is not int or native['source_rows_read']!=rows_read: raise ValueError('source_value_read_count_mismatch')
    complete = sum(s['training_values_checked'] and not s['numeric_mismatch'] and not s['metadata_issues'] for s in summaries)
    core = {'schema_version':'research-value-audit-v1','status':'values_consistent' if complete==len(summaries) and summaries else 'blocked',
        'binding_sha256':digest(binding),'reference_sha256':digest(reference),'selections_sha256':digest(selections),
        'target_sha256':digest(target),'native_sha256':digest(native),'policy_sha256':digest(policy),
        'samples':summaries,'sample_count':len(summaries),'native_feature_windows_checked':feature_count,
        'native_training_examples_checked':training_count,'source_rows_read':rows_read,'numeric_mismatch_samples':mismatch_count,
        'complete_numeric_samples':complete,'feature_names':POLICY['feature_order'],'target_parameters_approved':False,
        'return_reference':'exact_decimal_lexemes_fraction_then_binary64_vs_native_decimal28_binary64',
        'independent_full_feature_oracle_verified':False,'main_trainer_actual_source_selection_verified':False,
        'training_data_admitted':False,'fit_performed':False,'model_prediction_performed':False,
        'numeric_prototype_worker_executed':False,'provider_called':False,'source_modified':False,
        'production_promotion_authorized':False,'implementation':_LOADED}
    _guard(policy)
    return {**core,'audit_sha256':digest(core)}


def prepare(directory,project,source_pack,target=TARGET):
    _guard(POLICY); validate_target(target); directory=Path(directory).absolute(); project=private._safe_directory(project)
    private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_value_audit_directory_required')
    binding,reference,selections=bind_source_pack(source_pack); before=main_profile(project)
    with tempfile.TemporaryDirectory(prefix='native-values-',dir=directory.parent) as tmp:
        native=_native(project,reference,selections,target,Path(tmp))
    if main_profile(project)!=before or bind_source_pack(source_pack)!=(binding,reference,selections): raise ValueError('native_value_source_changed_during_audit')
    report=compose(binding,reference,selections,target,native)
    directory.mkdir(mode=0o700)
    for name,value in (('policy.json',POLICY),('binding.json',binding),('selection.json',selections),
                        ('target.json',target),('native.json',native),('audit.json',report)):
        files._write(directory,name,value)
    files._sync(directory);files._sync(directory.parent)
    return report


def verify(directory):
    directory=private._safe_directory(directory,private=True)
    policy=temporal._read(directory,'policy.json',16000);binding=temporal._read(directory,'binding.json',16000)
    current,reference,selections=bind_source_pack(binding['directory'])
    if current!=binding or selections!=temporal._read(directory,'selection.json',POLICY['maximum_packet_bytes']): raise ValueError('original_value_binding_changed')
    report=compose(binding,reference,selections,temporal._read(directory,'target.json',4000),
        temporal._read(directory,'native.json',POLICY['maximum_result_bytes']),policy)
    if canonical(report)!=canonical(temporal._read(directory,'audit.json',POLICY['maximum_result_bytes'])): raise ValueError('value_audit_or_implementation_changed')
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','verify'):
        c=subs.add_parser(name);c.add_argument('--directory',type=Path,required=True)
        if name=='prepare':
            for arg in ('project','source-pack','target'):c.add_argument('--'+arg,type=Path,required=True)
    args=p.parse_args(argv)
    try: report=verify(args.directory) if args.command=='verify' else prepare(args.directory,args.project,args.source_pack,temporal._read(args.target.parent,args.target.name,4000))
    except Exception: print('Native value audit refused; training admission disabled');return 2
    print('Native value audit verified: '+report['status']+'; training admission disabled');return 0


if __name__=='__main__': raise SystemExit(main())
