"""Fixed arithmetic interpreter in a trusted namespace/cgroup; no Python candidate execution."""
import ast
import hashlib
import os
from pathlib import Path
import secrets
import signal
import subprocess

from cryptoforge import research_code_resources as resources, research_code_static as static
from cryptoforge import research_feature_windows as windows
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields


POLICY = {'schema_version': 'research-numeric-interpreter-v1', 'arithmetic': 'binary64_each_node',
    'max_abs_intermediate': 1e100, 'repetitions': 2, 'max_packet_bytes': 128000,
    'max_output_bytes': 32000, 'generic_python_execution_enabled': False}

# Only trusted code is passed to Python. Candidate input is a closed JSON expression tree.
WORKER = r'''
import json, math, os, socket, sys
mode, unit, group, parent_net = sys.argv[1:]
def exact(value, fields):
    if type(value) is not dict or set(value) != set(fields): raise ValueError('schema')
def number(value, limit):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit: raise ValueError('numeric')
    return float(value) if value else 0.0
def window(value):
    if type(value) is not list or not 1 <= len(value) <= 64: raise ValueError('window')
    result = []
    for row in value:
        exact(row, ('open','high','low','close','volume'))
        row = {key:number(val, 1e15 if key == 'volume' else 1e12) for key,val in row.items()}
        if row['volume'] < 0 or min(row[key] for key in ('open','high','low','close')) <= 0: raise ValueError('range')
        if not row['low'] <= min(row['open'],row['close']) <= max(row['open'],row['close']) <= row['high']: raise ValueError('range')
        result.append(row)
    return result
def output(value):
    exact(value, ('value',)); return {'value': number(value['value'], 1e12)}
required = 0
nodes = 0
def validate(node, level=0):
    global nodes, required
    nodes += 1
    if nodes > 512 or level > 32 or type(node) is not list or not node or type(node[0]) is not str: raise ValueError('tree')
    op = node[0]
    if op == 'const':
        if len(node) != 2: raise ValueError('arity')
        number(node[1], 1e6)
    elif op == 'read':
        if len(node) != 3 or type(node[1]) is not int or not -64 <= node[1] <= 63 or node[2] not in ('open','high','low','close','volume'): raise ValueError('read')
        required = max(required, node[1]+1 if node[1] >= 0 else -node[1])
    else:
        arity = {'pos':(1,1),'neg':(1,1),'abs':(1,1),'add':(2,2),'sub':(2,2),'mul':(2,2),'div':(2,2),'min':(2,4),'max':(2,4)}
        if op not in arity or not arity[op][0] <= len(node)-1 <= arity[op][1]: raise ValueError('operator')
        for child in node[1:]: validate(child, level+1)
def evaluate(node, data):
    op = node[0]
    if op == 'const': return number(node[1], 1e6)
    if op == 'read': return data[node[1]][node[2]]
    args = [evaluate(child, data) for child in node[1:]]
    if op == 'pos': result = +args[0]
    elif op == 'neg': result = -args[0]
    elif op == 'add': result = args[0]+args[1]
    elif op == 'sub': result = args[0]-args[1]
    elif op == 'mul': result = args[0]*args[1]
    elif op == 'div': result = args[0]/args[1]
    elif op == 'abs': result = abs(args[0])
    elif op == 'min': result = min(args)
    else: result = max(args)
    return number(result, 1e100)
controls = {}
for name in ('memory.max','memory.swap.max','pids.max','cpu.max'):
    with open('/probe-cgroup/'+name) as stream: controls[name] = stream.read().strip()
with open('/proc/self/status') as stream: status = dict(line.split(':',1) for line in stream if ':' in line)
checks = {
    'configured_limits': controls == {'memory.max':'67108864','memory.swap.max':'0','pids.max':'8','cpu.max':'25000 100000'},
    'network_namespace_differs': os.readlink('/proc/self/ns/net') != parent_net,
    'only_loopback': [name for _,name in socket.if_nameindex()] == ['lo'],
    'private_paths_hidden': not any(os.path.exists(path) for path in ('/home','/root','/run','/var','/workspace')),
    'environment_cleared': dict(os.environ) == {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PWD':'/tmp'},
    'no_capabilities': int(status['CapEff'].strip(),16) == 0,
    'no_new_privileges': status['NoNewPrivs'].strip() == '1',
}
if not all(checks.values()): raise ValueError('isolation')
raw = sys.stdin.buffer.read(128001)
if len(raw) > 128000: raise ValueError('packet')
packet = json.loads(raw)
exact(packet, ('schema_version','program','cases','outputs'))
if packet['schema_version'] != 'research-numeric-packet-v1': raise ValueError('version')
validate(packet['program'])
if type(packet['cases']) is not list or len(packet['cases']) != 14 or type(packet['outputs']) is not list or len(packet['outputs']) != 7: raise ValueError('cases')
results = []
for case in packet['cases']:
    exact(case, ('id','valid','window'))
    try: data = window(case['window'])
    except ValueError:
        results.append({'id':case['id'],'status':'input_rejected','value':None,'evaluations':0,'repeat_equal':None}); continue
    if len(data) < required:
        results.append({'id':case['id'],'status':'insufficient_window','value':None,'evaluations':0,'repeat_equal':None}); continue
    values = []
    for _ in range(2):
        try: values.append({'status':'valid_output','value':output({'value':evaluate(packet['program'],data)})['value']})
        except (ValueError,ArithmeticError,IndexError): values.append({'status':'numeric_invalid','value':None})
    results.append({'id':case['id'],**values[0],'evaluations':2,'repeat_equal':values[0] == values[1]})
output_checks = []
for case in packet['outputs']:
    exact(case, ('id','valid','output'))
    try: output(case['output']); accepted = True
    except ValueError: accepted = False
    output_checks.append({'id':case['id'],'accepted':accepted})
import hashlib
print(json.dumps({'schema_version':'research-numeric-child-v1','packet_sha256':hashlib.sha256(raw).hexdigest(),
    'unit':unit,'cgroup_path':group,'checks':checks,'results':results,'output_checks':output_checks,
    'required_window_size':required,'python_version':sys.version.split()[0]},allow_nan=False),flush=True)
'''
LAUNCHER = resources.LAUNCHER.replace(repr(resources.INNER), repr(WORKER))


def implementation():
    return {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in
        ('research_numeric_worker.py', 'research_code_resources.py', 'research_code_static.py',
         'research_feature_windows.py')}


_LOADED = implementation()


def guard():
    static._guard(); windows._guard(windows.POLICY)
    if implementation() != _LOADED: raise ValueError('numeric worker implementation changed')


def program(source):
    """Translate the already closed AST; never compile/eval/import source."""
    analysis = static._analyze(source)
    if analysis['verdict'] != 'passed_static_contract': raise ValueError('closed static contract required')
    node = ast.parse(source, feature_version=(3,12)).body[0].body[0].value.values[0]
    def convert(node):
        if isinstance(node, ast.Constant): return ['const', node.value]
        if isinstance(node, ast.Subscript): return ['read', static._literal_index(node.value.slice), node.slice.value]
        if isinstance(node, ast.UnaryOp): return ['neg' if isinstance(node.op, ast.USub) else 'pos', convert(node.operand)]
        if isinstance(node, ast.BinOp):
            return [{ast.Add:'add',ast.Sub:'sub',ast.Mult:'mul',ast.Div:'div'}[type(node.op)],convert(node.left),convert(node.right)]
        return [node.func.id,*[convert(arg) for arg in node.args]]
    return convert(node), analysis


def packet(source, selected):
    guard()
    tree, analysis = program(source)
    controls = windows.control_pack(windows.POLICY)
    cases = [*controls['window_cases'], {'id':'selected_window','valid':True,'window':windows.validate_window(selected)}]
    result = {'schema_version':'research-numeric-packet-v1','program':tree,'cases':cases,'outputs':controls['output_cases']}
    if len(canonical(result).encode()) > POLICY['max_packet_bytes']: raise ValueError('numeric packet limit')
    return result, analysis, controls['controls_sha256']


def run(packet):
    """One fixed worker. Host environment, paths, candidate source and metadata are absent."""
    guard(); runtime = resources._runtime()
    raw = canonical(packet).encode()
    if len(raw) > POLICY['max_packet_bytes']: raise ValueError('numeric packet limit')
    unit = 'cryptoforge-research-resource-' + secrets.token_hex(8) + '.scope'
    argv = resources.probe_argv(unit, 'observe', os.readlink('/proc/self/ns/net')); argv[-4] = LAUNCHER
    process = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True, env=resources._environment())
        raw_output, _ = process.communicate(raw, timeout=resources.PARENT_SECONDS)
        returncode = process.returncode
    finally:
        try: cleanup = resources.cleanup(unit)
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL); process.communicate(timeout=1)
    guard()
    if runtime != resources._runtime() or not cleanup['unit_removed'] or returncode != 0:
        raise ValueError('numeric worker or cleanup failed')
    if len(raw_output) > POLICY['max_output_bytes']: raise ValueError('numeric output limit')
    result = strict_json(raw_output.decode(), max_bytes=POLICY['max_output_bytes'])
    exact_fields(result, {'schema_version','packet_sha256','unit','cgroup_path','checks','results',
                         'output_checks','required_window_size','python_version'})
    group = result['cgroup_path']
    if (type(group) is not str or not group.startswith('/user.slice/') or not group.endswith('/'+unit)
            or any(part in ('','.','..') for part in group.split('/')[1:])
            or (Path('/sys/fs/cgroup')/group.lstrip('/')).exists()):
        raise ValueError('numeric cgroup cleanup unverified')
    exact_fields(result['checks'], {'configured_limits','network_namespace_differs','only_loopback',
        'private_paths_hidden','environment_cleared','no_capabilities','no_new_privileges'})
    if (result['schema_version'] != 'research-numeric-child-v1' or result['packet_sha256'] != hashlib.sha256(raw).hexdigest()
            or result['unit'] != unit or result['python_version'] != '3.12.3'
            or any(value is not True for value in result['checks'].values())):
        raise ValueError('numeric worker attestation mismatch')
    return {'child':result,'runtime':runtime,'unit_removed':True,'cgroup_removed':True}


def validate_result(observed, packet, required):
    """Independent checks of counts, refusals and contracts; no invented feature oracle."""
    child = observed['child']
    if child['required_window_size'] != required or len(child['results']) != 14 or len(child['output_checks']) != 7:
        raise ValueError('numeric control coverage mismatch')
    valid = True; evaluations = 0
    for case, result in zip(packet['cases'], child['results']):
        exact_fields(result, {'id','status','value','evaluations','repeat_equal'})
        if result['id'] != case['id']: raise ValueError('numeric control ordering mismatch')
        if not case['valid']: expected = 'input_rejected'
        elif len(case['window']) < required: expected = 'insufficient_window'
        else: expected = None
        if expected:
            if canonical(result) != canonical({'id':case['id'],'status':expected,'value':None,'evaluations':0,'repeat_equal':None}):
                raise ValueError('numeric invalid input was evaluated')
        else:
            if result['evaluations'] != 2 or type(result['evaluations']) is not int or result['repeat_equal'] is not True:
                raise ValueError('numeric repeat mismatch')
            if result['status'] == 'valid_output': windows.validate_output({'value':result['value']})
            elif result['status'] != 'numeric_invalid' or result['value'] is not None: raise ValueError('numeric status mismatch')
            valid = valid and result['status'] == 'valid_output'
        evaluations += result['evaluations']
    for case, result in zip(packet['outputs'], child['output_checks']):
        if canonical(result) != canonical({'id':case['id'],'accepted':case['valid']}): raise ValueError('output validator mismatch')
    return {'all_applicable_outputs_valid':valid,'arithmetic_evaluations':evaluations,
        'window_cases_checked':14,'output_contract_cases_checked':7,'repeat_checks_observed':True,
        'selected_window_status':child['results'][-1]['status'],
        'all_valid_windows_have_sufficient_history':not any(row['status']=='insufficient_window' for row in child['results'])}
