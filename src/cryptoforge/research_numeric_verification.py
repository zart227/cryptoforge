"""Frozen two-window verification using existing v4 attempts, no new quota or runtime."""
import argparse
import ast
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
import hashlib
import math
import os
from pathlib import Path
import sys
import time

from cryptoforge import research_numeric_controls as numeric, research_numeric_worker as worker
from cryptoforge import research_code_static as static, research_code_preview as preview
from cryptoforge import research_code_resources as resources, research_feature_windows as windows
from cryptoforge import research_run_budget as common
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp


POLICY = {'schema_version':'research-numeric-verification-v1','selected_window_bars':[1,2],
    'seed_window_bars':3,'reference':'fraction_with_binary64_rounding_at_each_node',
    'comparison':'exact_normalized_float_hex','cross_process_scope':'13_shared_fixed_window_cases',
    'metamorphic_rules':['row_permutation','unavailable_future_values'],
    'maximum_new_v4_actions':2,'new_budget_or_migration':False,'generic_python_execution_enabled':False}


def implementation():
    return {'verification':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'fraction_library':hashlib.sha256(Path(sys.modules[Fraction.__module__].__file__).read_bytes()).hexdigest(),
        'numeric':numeric.implementation()}


_LOADED = implementation()
_POLICY_SHA = digest(POLICY)


def _guard(policy=POLICY):
    numeric._guard()
    if digest(policy) != _POLICY_SHA or digest(POLICY) != _POLICY_SHA or implementation() != _LOADED:
        raise ValueError('fixed verification policy and implementation required')


def _float(value, maximum):
    value = float(value)
    if not math.isfinite(value) or abs(value) > maximum: raise ArithmeticError('numeric_contract')
    return value if value else 0.0


def reference(source, cases):
    """Independent AST traversal; Fraction operations replace the worker's float arithmetic.

    This trusted bounded verifier is not another worker launch. Its time and
    evaluation count are reported separately from v4 handler resource accounting.
    """
    analysis = static._analyze(source)
    if analysis['verdict'] != 'passed_static_contract': raise ValueError('closed source required')
    expression = ast.parse(source,feature_version=(3,12)).body[0].body[0].value.values[0]
    required = 0
    for node in ast.walk(expression):
        if isinstance(node,ast.Subscript) and isinstance(node.value,ast.Subscript):
            index = ast.literal_eval(node.value.slice)
            required = max(required,index+1 if index >= 0 else -index)
    def evaluate(node,data):
        if isinstance(node,ast.Constant): return _float(node.value,1e6)
        if isinstance(node,ast.Subscript): return data[ast.literal_eval(node.value.slice)][node.slice.value]
        if isinstance(node,ast.UnaryOp):
            value=Fraction(evaluate(node.operand,data)); result=-value if isinstance(node.op,ast.USub) else value
        elif isinstance(node,ast.BinOp):
            left,right=Fraction(evaluate(node.left,data)),Fraction(evaluate(node.right,data))
            if isinstance(node.op,ast.Add):result=left+right
            elif isinstance(node.op,ast.Sub):result=left-right
            elif isinstance(node.op,ast.Mult):result=left*right
            else:result=left/right
        else:
            values=[Fraction(evaluate(argument,data)) for argument in node.args]
            if node.func.id=='abs':result=abs(values[0])
            elif node.func.id=='min':result=min(values)
            else:result=max(values)
        return _float(result,1e100)
    if type(cases) is not list or len(cases) != 14:raise ValueError('fixed reference coverage required')
    results=[];evaluations=0
    for case in cases:
        exact_fields(case,{'id','valid','window'})
        try:data=windows.validate_window(case['window'])
        except ValueError:status,value='input_rejected',None
        else:
            if len(data)<required:status,value='insufficient_window',None
            else:
                evaluations+=1
                try:value=_float(evaluate(expression,data),1e12);status='valid_output'
                except (ArithmeticError,ValueError,IndexError):status,value='numeric_invalid',None
        results.append({'id':case['id'],'status':status,'value':value})
    return {'required_window_size':required,'results':results,'reference_evaluations':evaluations}


def _normalized(rows):
    return [{'id':row['id'],'status':row['status'],
        'value_hex':float(row['value']).hex() if row['value'] is not None else None} for row in rows]


def metamorphic(capture, requests):
    """Selection-only invariance, not reexecution of a candidate or authentic market causality."""
    results=[]
    future=deepcopy(capture);cutoff=timestamp(requests[0]['decision_time']);step=capture['timeframe_seconds']
    changed=0
    for row in future['candles']:
        if max(timestamp(row['open_time'])+timedelta(seconds=step),timestamp(row['observed_at']))>cutoff:
            row.update(open=1e12,high=1e12,low=1e12,close=1e12,volume=0.0);changed+=1
    if not changed and len(future['candles'])<windows.POLICY['max_capture_candles']:
        epoch=int(cutoff.timestamp());opened=cutoff.replace(microsecond=0)-timedelta(seconds=epoch%step)
        closed=opened+timedelta(seconds=step)
        if closed<=timestamp(capture['development_end']):
            future['candles'].append({'open_time':opened.isoformat(),'observed_at':closed.isoformat(),
                'open':1e12,'high':1e12,'low':1e12,'close':1e12,'volume':0.0})
            future['captured_at']=max(timestamp(future['captured_at']),closed).isoformat();changed=1
    future['source_export_sha256']=digest({'synthetic_metamorphic':True,'original':capture['source_export_sha256']})
    for request in requests:
        baseline=windows.prepare(capture,request,windows.POLICY)
        reversed_capture=deepcopy(capture);reversed_capture['candles'].reverse()
        permutation=windows.prepare(reversed_capture,request,windows.POLICY)
        tail=windows.prepare(future,request,windows.POLICY) if changed else None
        def same(other):
            return (baseline['status']=='prepared' and other['status']=='prepared'
                and baseline['payload']==other['payload']
                and baseline['window_identity_sha256']==other['window_identity_sha256'])
        results.append({'bars':request['bars'],'row_permutation_invariant':same(permutation),
            'future_value_invariant':same(tail) if tail else None,
            'future_rows_changed_or_added':changed,'transformed_capture_sha256':digest(future) if changed else None})
    return {'scope':'input_selection_only','synthetic_transformation':True,'results':results,
        'candidate_reexecutions':0,'upstream_or_financial_causality_proven':False}


def _inputs(budget, preview_directory, seed_directory, capture):
    _guard()
    if type(budget) is not numeric.NumericControlBudget:raise ValueError('existing numeric v4 budget required')
    checked=preview.read_preview(preview_directory)
    static._registered_preview(numeric._ReadAdapter(budget),checked)
    seed=windows.read_window(seed_directory,capture)
    if seed['status']!='prepared' or seed['payload']['bars']!=POLICY['seed_window_bars']:
        raise ValueError('prepared three-bar seed required')
    requests=[{'schema_version':'research-window-request-v1','decision_time':seed['payload']['decision_time'],'bars':bars}
        for bars in POLICY['selected_window_bars']]
    cases=[]
    for request in requests:
        selected=windows.prepare(capture,request,windows.POLICY)
        if selected['status']!='prepared':raise ValueError('prepared verification windows required')
        packet,analysis,controls_sha=worker.packet(checked['candidate_text'],selected['payload']['window'])
        identity={'candidate_identity_sha256':checked['candidate_identity_sha256'],
            'window_identity_sha256':selected['window_identity_sha256'],'controls_sha256':controls_sha,
            'worker_policy_sha256':digest(worker.POLICY)}
        key=digest({'kind':'numeric_control','identity':identity,'configuration_sha256':digest(budget.configuration)})
        cases.append({'id':'bars_'+str(request['bars']),'request':request,'window':selected,'packet':packet,
            'required':analysis['required_window_size'],'identity':identity,'operation_key':key})
    return checked,seed,cases


def _manifest(budget,checked,seed,cases,capture,before,runtime):
    core={'schema_version':'research-numeric-verification-plan-v1','policy':deepcopy(POLICY),
        'candidate_identity_sha256':checked['candidate_identity_sha256'],'preview_sha256':checked['preview_sha256'],
        'seed_window_identity_sha256':seed['window_identity_sha256'],'capture_sha256':digest(capture),
        'budget_configuration_sha256':digest(budget.configuration),'budget_before':before,
        'runtime':runtime,'implementation':deepcopy(_LOADED),
        'cases':[{'id':case['id'],'request':case['request'],'window_pack_sha256':case['window']['window_pack_sha256'],
            'packet_sha256':digest(case['packet']),'operation_key':case['operation_key'],'identity':case['identity']} for case in cases],
        'metamorphic':metamorphic(capture,[case['request'] for case in cases])}
    return {**core,'plan_sha256':digest(core)}


def prepare(directory,budget,preview_directory,seed_directory,capture,policy):
    _guard(policy);checked,seed,cases=_inputs(budget,preview_directory,seed_directory,capture)
    plan=_manifest(budget,checked,seed,cases,capture,budget.snapshot(),resources._runtime())
    directory=Path(directory);directory.mkdir(mode=0o700)
    for case in cases:windows.stage_window(directory/case['id'],capture,case['request'],windows.POLICY)
    preview.files._write(directory,'plan.json',plan);preview.files._sync(directory);preview.files._sync(directory.parent)
    return plan


def _read_plan(directory,budget,preview_directory,seed_directory,capture):
    directory=Path(directory)
    if directory.is_symlink() or not directory.is_dir():raise ValueError('private protocol directory required')
    saved=preview.files._json(directory,'plan.json',128000)
    checked,seed,cases=_inputs(budget,preview_directory,seed_directory,capture)
    expected=_manifest(budget,checked,seed,cases,capture,saved['budget_before'],saved['runtime'])
    if canonical(expected)!=canonical(saved) or saved['runtime']!=resources._runtime():raise ValueError('frozen verification plan changed')
    for case in cases:
        if windows.read_window(directory/case['id'],capture)!=case['window']:raise ValueError('verification window changed')
    return saved,checked,cases


def _persisted(budget,key,identity):
    with budget._connection() as db:
        budget._check(db)
        row=db.execute('SELECT input_sha,status,payload,payload_sha FROM coordinated_numeric_actions WHERE key=?',(key,)).fetchone()
        if row is None or row[:2]!=(digest(identity),'completed'):raise ValueError('completed matching v4 action required')
        result=strict_json(row[2],max_bytes=64000)
        if digest(result)!=row[3] or result['identity']!=identity:raise ValueError('persisted control result mismatch')
        return result


def _evidence(budget,case,source,runtime):
    result=_persisted(budget,case['operation_key'],case['identity'])
    if result['packet_sha256']!=digest(case['packet']):raise ValueError('persisted packet mismatch')
    summary=worker.validate_result(result['observation'],case['packet'],case['required'])
    if result['summary']!=summary:raise ValueError('persisted control summary mismatch')
    observation=result['observation'];child=observation['child']
    exact_fields(observation,{'child','runtime','unit_removed','cgroup_removed'})
    exact_fields(child,{'schema_version','packet_sha256','unit','cgroup_path','checks','results',
        'output_checks','required_window_size','python_version'})
    exact_fields(child['checks'],{'configured_limits','network_namespace_differs','only_loopback',
        'private_paths_hidden','environment_cleared','no_capabilities','no_new_privileges'})
    group=child['cgroup_path'];unit=child['unit']
    if (type(group) is not str or type(unit) is not str or resources.UNIT.fullmatch(unit) is None
            or not group.startswith('/user.slice/') or not group.endswith('/'+unit)
            or any(part in ('','.','..') for part in group.split('/')[1:])
            or (Path('/sys/fs/cgroup')/group.lstrip('/')).exists()):raise ValueError('removed fixed worker scope required')
    if (observation['runtime']!=runtime or observation['unit_removed'] is not True or observation['cgroup_removed'] is not True
            or child['python_version']!='3.12.3' or child['schema_version']!='research-numeric-child-v1'
            or child['packet_sha256']!=digest(case['packet'])
            or any(flag is not True for flag in child['checks'].values())):raise ValueError('fixed runtime evidence required')
    started=time.monotonic_ns();expected=reference(source,case['packet']['cases'])
    elapsed=max(0,(time.monotonic_ns()-started+999999)//1000000)
    observed=_normalized(child['results']);reference_rows=_normalized(expected['results'])
    return {'id':case['id'],'operation_key':case['operation_key'],'result_sha256':digest(result),
        'unit':child['unit'],'runtime_sha256':digest(runtime),'observed_results_sha256':digest(observed),
        'reference_results_sha256':digest(reference_rows),'reference_matches':observed==reference_rows
            and expected['required_window_size']==child['required_window_size'],
        'worker_evaluation_attempts':summary['arithmetic_evaluations'],'reference_evaluations':expected['reference_evaluations'],
        'reference_wall_ms':elapsed,'shared_fixed_results_sha256':digest(observed[:-1]),
        'selected_window_status':summary['selected_window_status']}


def _summary(plan,evidence):
    complete=len(evidence)==2
    independent=complete and len({case['unit'] for case in evidence})==2
    shared=complete and len({case['shared_fixed_results_sha256'] for case in evidence})==1
    references=complete and all(case['reference_matches'] for case in evidence)
    selected=complete and all(case['selected_window_status']=='valid_output' for case in evidence)
    transforms=plan['metamorphic']['results']
    selection=all(case['row_permutation_invariant'] and case['future_value_invariant'] is True for case in transforms)
    return {'complete':complete,'distinct_worker_scopes':independent,'shared_13_fixture_reproducibility':bool(independent and shared),
        'reference_agreement':references,'selected_windows_valid':selected,'selection_metamorphic_checks_passed':selection,
        'verification_passed':bool(independent and shared and references and selected and selection),
        'whole_packet_reexecution_proven':False,'financial_feature_formula_or_utility_proven':False,
        'upstream_causality_proven':False,'generic_python_executed':False,'training_executed':False,
        'can_authorize_trades':False,'trusted_reference_cost_in_v4_handler_measurement':False}


def execute(directory,budget,preview_directory,seed_directory,capture):
    plan,checked,cases=_read_plan(directory,budget,preview_directory,seed_directory,capture)
    receipt={'schema_version':'research-numeric-verification-receipt-v1','status':'started','plan_sha256':plan['plan_sha256'],
        'cases':[],'implementation':deepcopy(_LOADED),'new_v4_actions':0,'invocation_worker_evaluations':0}
    directory=Path(directory)
    fd=os.open(directory/'receipt.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        def save():
            record={**receipt,'receipt_sha256':digest(receipt)}
            stream.seek(0);stream.truncate();stream.write(canonical(record)+'\n');stream.flush();os.fsync(stream.fileno())
            preview.files._sync(directory)
            return record
        save()
        try:
            for case in cases:
                _guard()
                invocation=budget.check(preview_directory,directory/case['id'],capture)
                receipt['new_v4_actions']+=invocation['new_actions']
                receipt['invocation_worker_evaluations']+=invocation['invocation_arithmetic_evaluations']
                evidence=_evidence(budget,case,checked['candidate_text'],plan['runtime'])
                receipt['cases'].append(evidence);save()
                if not evidence['reference_matches']:break
            _read_plan(directory,budget,preview_directory,seed_directory,capture)
            receipt['summary']=_summary(plan,receipt['cases'])
            receipt['status']='completed' if receipt['summary']['verification_passed'] else 'verification_failed'
            receipt['budget_after']=budget.snapshot()
        except (KeyboardInterrupt,common.BudgetCancelled):receipt.update(status='cancelled',safe_error='verification_cancelled')
        except common.BudgetTimedOut:receipt.update(status='timed_out',safe_error='verification_timed_out')
        except Exception:receipt.update(status='failed',safe_error='verification_inputs_budget_or_worker_rejected')
        return save()


def verify(directory,budget,preview_directory,seed_directory,capture):
    plan,checked,cases=_read_plan(directory,budget,preview_directory,seed_directory,capture)
    saved=preview.files._json(directory,'receipt.json',128000)
    exact_fields(saved,{'schema_version','status','plan_sha256','cases','implementation','new_v4_actions',
        'invocation_worker_evaluations','summary','budget_after','receipt_sha256'})
    if (saved['schema_version']!='research-numeric-verification-receipt-v1' or type(saved['cases']) is not list
            or type(saved['new_v4_actions']) is not int or not 0<=saved['new_v4_actions']<=2
            or type(saved['invocation_worker_evaluations']) is not int or not 0<=saved['invocation_worker_evaluations']<=32
            or saved['new_v4_actions']==0 and saved['invocation_worker_evaluations']!=0):raise ValueError('bounded verification observations required')
    core={key:value for key,value in saved.items() if key!='receipt_sha256'}
    if digest(core)!=saved['receipt_sha256'] or saved['status'] not in ('completed','verification_failed'):
        raise ValueError('completed verification receipt required')
    if saved['plan_sha256']!=plan['plan_sha256'] or saved['implementation']!=_LOADED or len(saved['cases'])>2:
        raise ValueError('verification receipt binding mismatch')
    evidence=[]
    for case,stored in zip(cases,saved['cases']):
        current=_evidence(budget,case,checked['candidate_text'],plan['runtime'])
        if type(stored['reference_wall_ms']) is not int or stored['reference_wall_ms']<0:raise ValueError('reference wall observation required')
        current['reference_wall_ms']=stored['reference_wall_ms']
        if canonical(current)!=canonical(stored):raise ValueError('verification evidence changed')
        evidence.append(current)
    if _summary(plan,evidence)!=saved['summary']:raise ValueError('verification summary mismatch')
    expected_status='completed' if saved['summary']['verification_passed'] else 'verification_failed'
    if saved['status']!=expected_status:raise ValueError('verification verdict mismatch')
    _guard()
    return {'schema_version':'research-numeric-verification-readback-v1','receipt_sha256':saved['receipt_sha256'],
        'verification_passed':saved['summary']['verification_passed'],'database_read_only':True,
        'new_worker_launches':0,'new_v4_actions':0,'trusted_reference_recomputed':True}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('database','proposal-ledger','semantic-ledger','fit-ledger','semantic-live-ledger',
        'semantic-live-policy','code-policy','numeric-policy','verification-policy','preview','seed-window','capture','directory'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--policy',type=Path);parser.add_argument('--resource-policy',type=Path)
    parser.add_argument('command',choices=('prepare','execute','verify'))
    args=parser.parse_args(argv)
    protected=[path.resolve() for name,path in vars(args).items() if isinstance(path,Path) and name!='directory']
    if args.command=='prepare' and any(args.directory.resolve()==path or args.directory.resolve().is_relative_to(path) for path in protected):
        parser.error('new verification directory must be separate from journals and source bundles')
    def read(path):return preview.files._json(path.parent,path.name,512000) if path is not None else None
    legacy=common.ResearchRunBudget(args.database,{'proposal':args.proposal_ledger,'semantic_fixture':args.semantic_ledger,'fit':args.fit_ledger},
        policy=read(args.policy),resource_policy=read(args.resource_policy),semantic_live_ledger=args.semantic_live_ledger,
        semantic_live_policy=read(args.semantic_live_policy),code_check_policy=read(args.code_policy))
    budget=numeric.NumericControlBudget(legacy,read(args.numeric_policy))
    params=(args.directory,budget,args.preview,args.seed_window,read(args.capture))
    _guard(read(args.verification_policy))
    if args.command=='prepare':result=prepare(*params,read(args.verification_policy));code=0
    elif args.command=='execute':result=execute(*params);code=0 if result['status']=='completed' else 2
    else:result=verify(*params);code=0 if result['verification_passed'] else 2
    print('Frozen numeric verification '+args.command+' completed; generic Python disabled')
    return code


if __name__=='__main__':raise SystemExit(main())
