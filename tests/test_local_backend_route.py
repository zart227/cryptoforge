from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path

import pytest

from test_reference_aware_feeder import observation
from test_local_source_provenance import NOW
from cryptoforge.local_backend_route import validate_route, bind_rows, observe_backend_route, NGINX, IMAGES, FIELDS
from cryptoforge.local_source_observer import query_sql
from cryptoforge.local_source_provenance import canonical,digest


ROOT=Path('/synthetic/project')


def topology():
    values={}
    for i,service in enumerate(('db','rest','api'),1):
        values[service]=dict(Id=str(i)*64,Image=IMAGES[service],State=dict(Running=True,StartedAt=NOW.isoformat()),
            Config=dict(Labels={'com.docker.compose.project':'cryptoforge-database',
                'com.docker.compose.project.working_dir':str(ROOT/'docker'),'com.docker.compose.service':service},
                Env=[],Entrypoint=None,Cmd=None),Mounts=[],
            NetworkSettings=dict(Networks={'isolated':dict(Aliases=[service],IPAddress='172.21.0.'+str(i))},Ports={}))
    values['api']['Config'].update(Entrypoint=['/docker-entrypoint.sh'],Cmd=['nginx','-g','daemon off;'])
    values['api']['NetworkSettings']['Ports']={'80/tcp':[dict(HostIp='127.0.0.1',HostPort='54321')]}
    values['api']['Mounts']=[dict(Type='bind',Source=str(ROOT/'docker/database-nginx.conf'),Destination='/etc/nginx/nginx.conf',RW=False)]
    values['rest']['Config'].update(Cmd=['/bin/postgrest'],Env=['PGRST_DB_URI=postgres://authenticator:never-save-secret@db:5432/cryptoforge','PGRST_DB_SCHEMAS=public'])
    values['rest']['NetworkSettings']['Ports']={'3000/tcp':None}
    network=dict(Id='4'*64,Name='isolated',Driver='bridge',Labels={'com.docker.compose.project':'cryptoforge-database'},Containers={v['Id']:{} for v in values.values()})
    return values,network


def route(values=None,network=None,nginx=NGINX):
    default,n=topology()
    return validate_route(values or default,ROOT,nginx,endpoint='unix:///var/run/docker.sock',network=network or n,nginx_mtime=NOW-timedelta(days=1))


def reads():
    before=observation('BTC/USDT');after=deepcopy(before)
    after.update(prepared_at=(NOW+timedelta(seconds=3)).isoformat(),completed_at=(NOW+timedelta(seconds=4)).isoformat(),
        query_sha256=digest(query_sql('BTC/USDT','5m',120,NOW+timedelta(seconds=3)).encode()))
    data=json.loads(after['raw_response']);data['database_clock']=(NOW+timedelta(seconds=3)).isoformat();after['raw_response']=json.dumps(data)
    rows=[{k:v for k,v in json.loads(r['raw_json']).items() if k in FIELDS} for r in json.loads(before['raw_response'])['rows']]
    body=canonical(rows).decode()
    response=dict(prepared_at=(NOW+timedelta(seconds=1.2)).isoformat(),completed_at=(NOW+timedelta(seconds=2)).isoformat(),
        body=body,body_sha256=digest(body.encode()),url='original')
    return before,response,after


def test_exclusive_owned_topology_discards_all_secrets():
    value=route()
    assert value['backend_url']=='http://127.0.0.1:54321'
    assert 'never-save-secret' not in str(value) and 'PGRST_DB_URI' not in str(value)


@pytest.mark.parametrize('fault',['image','owner','public_port','writable_mount','alternate_db','duplicate_env','alias','extra_container','extra_network','entrypoint','nginx'])
def test_bad_routes_fail_closed(fault):
    values,network=topology();nginx=NGINX
    if fault=='image':values['rest']['Image']='sha256:'+'0'*64
    if fault=='owner':values['db']['Config']['Labels']['com.docker.compose.project.working_dir']='/another'
    if fault=='public_port':values['api']['NetworkSettings']['Ports']['80/tcp'][0]['HostIp']='0.0.0.0'
    if fault=='writable_mount':values['api']['Mounts'][0]['RW']=True
    if fault=='alternate_db':values['rest']['Config']['Env'][0]='PGRST_DB_URI=postgres://authenticator:secret@other:5432/cryptoforge'
    if fault=='duplicate_env':values['rest']['Config']['Env'].append(values['rest']['Config']['Env'][0])
    if fault=='alias':values['api']['NetworkSettings']['Networks']['isolated']['Aliases'].append('db')
    if fault=='extra_container':network['Containers']['f'*64]={}
    if fault=='extra_network':values['rest']['NetworkSettings']['Networks']['another']=dict(Aliases=['rest'],IPAddress='172.22.0.2')
    if fault=='entrypoint':values['rest']['Config']['Cmd']=['/bin/other']
    if fault=='nginx':nginx=NGINX.replace(b'rest:3000',b'elsewhere:3000')
    with pytest.raises(ValueError):route(values,network,nginx)


def test_closed_uuid_value_rows_bind_causally_and_staleness_is_explicit():
    before,response,after=reads()
    result=bind_rows(before,response,after)
    assert result['rows']==120 and result['candle_freshness_pass'] is True
    assert len(result['normalized_rows_sha256'])==64


@pytest.mark.parametrize('fault',['uuid','price','missing','mixed_sql','future','body_sha','duplicate_json','numeric_bool','huge_exponent','extra_column'])
def test_changed_or_incomplete_rows_cannot_attest_instance(fault):
    before,response,after=reads()
    rows=json.loads(response['body'])
    if fault=='uuid':rows[0]['id']='00000000-0000-0000-0000-999999999999'
    if fault=='price':rows[0]['close']='100.000000000001'
    if fault=='missing':rows.pop()
    if fault=='numeric_bool':rows[0]['close']=True
    if fault=='huge_exponent':rows[0]['close']='1e999999999'
    if fault=='extra_column':rows[0]['unrequested']='unexpected'
    if fault=='mixed_sql':
        v=json.loads(after['raw_response']);v['system_identifier']='7500123412341234124';after['raw_response']=json.dumps(v)
    if fault=='future':response['completed_at']=(NOW+timedelta(seconds=4)).isoformat()
    response['body']=canonical(rows).decode();response['body_sha256']=digest(response['body'].encode())
    if fault=='body_sha':response['body_sha256']='0'*64
    if fault=='duplicate_json':response['body']='[{"id":"a","id":"b"}]';response['body_sha256']=digest(response['body'].encode())
    with pytest.raises(ValueError):bind_rows(before,response,after)


def test_orchestration_checks_route_twice_and_keeps_auth_out_of_receipt():
    before,response,after=reads();observations=iter([before,after]);count=[]
    def inspect():count.append(True);return route()
    def request(url,key):
        assert key=='synthetic-api-secret'
        return dict(response,url=url)
    result=observe_backend_route(ROOT,dict(CRYPTOFORGE_BACKEND='local',CRYPTOFORGE_LOCAL_API_KEY='synthetic-api-secret'),
        inspect=inspect,observe=lambda:next(observations),request=request)
    assert len(count)==2 and result['rest_instance_identity_verified'] is True
    assert 'synthetic-api-secret' not in str(result)
    assert result['live_admission_granted'] is False


def test_changed_topology_and_cloud_backend_never_attest():
    before,response,after=reads();observations=iter([before,after]);routes=iter([route(),dict(route(),network_id='f'*64)])
    with pytest.raises(ValueError,match='topology'):
        observe_backend_route(ROOT,dict(CRYPTOFORGE_BACKEND='local',CRYPTOFORGE_LOCAL_API_KEY='test'),
            inspect=lambda:next(routes),observe=lambda:next(observations),request=lambda u,k:dict(response,url=u))
    with pytest.raises(ValueError,match='fixed local'):
        observe_backend_route(ROOT,dict(CRYPTOFORGE_BACKEND='supabase',SUPABASE_URL='https://example.supabase.co',SUPABASE_SERVICE_ROLE_KEY='test'))


@pytest.mark.parametrize('fault',[None,'changed_config','extra_config'])
def test_real_command_shape_suppresses_nginx_diagnostics_but_checks_full_dump(tmp_path,monkeypatch,fault):
    import os
    import stat
    from types import SimpleNamespace
    from datetime import datetime,UTC
    from cryptoforge.local_backend_route import inspect_route
    monkeypatch.delenv('DOCKER_HOST',raising=False);monkeypatch.delenv('DOCKER_CONTEXT',raising=False)
    root=tmp_path/'repo';(root/'docker').mkdir(parents=True)
    (root/'docker/database-nginx.conf').write_bytes(NGINX)
    values,network=topology()
    for service,value in values.items():
        value['Config']['Labels']['com.docker.compose.project.working_dir']=str(root/'docker')
        value['State']['StartedAt']=(datetime.now(UTC)+timedelta(seconds=1)).isoformat()
    values['api']['Mounts'][0]['Source']=str(root/'docker/database-nginx.conf')
    socket_path=tmp_path/'docker.sock';original_stat=Path.stat
    def path_stat(path,*args,**kwargs):
        if path==socket_path:return SimpleNamespace(st_mode=stat.S_IFSOCK|0o600,st_uid=os.getuid())
        return original_stat(path,*args,**kwargs)
    monkeypatch.setattr(Path,'stat',path_stat)
    def command(argv):
        if argv==['docker','context','show']:return b'local\n'
        if argv==['docker','context','inspect','local']:
            return canonical([dict(Endpoints=dict(docker=dict(Host='unix://'+str(socket_path))))])
        if argv[:2]==['docker','compose']:return values[argv[-1]]['Id'].encode()
        if argv[:2]==['docker','inspect']:return canonical([next(v for v in values.values() if v['Id']==argv[-1])])
        if argv[:3]==['docker','network','inspect']:return canonical([network])
        assert argv==['docker','exec',values['api']['Id'],'nginx','-q','-T']
        config=NGINX.replace(b'rest:3000',b'elsewhere:3000') if fault=='changed_config' else NGINX
        if fault=='extra_config':config+=b'\n# configuration file /etc/nginx/extra.conf:\nserver {}\n'
        return b'# configuration file /etc/nginx/nginx.conf:\n'+config
    if fault:
        with pytest.raises(ValueError,match='nginx'):inspect_route(root,command=command)
    else:assert inspect_route(root,command=command)['database']=='cryptoforge'
