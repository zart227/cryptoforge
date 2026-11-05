"""Read-only, same-host Docker api -> rest -> db route and closed-row binding.

This attests the observed local topology and one bounded row set. It grants no
historical availability, strategy, paper, host-capacity or live-order admission.
Docker inspection secrets are discarded before returning or persisting anything.
"""
from datetime import UTC, datetime
from decimal import Decimal
import os
from pathlib import Path
import re
import stat
from time import monotonic
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from cryptoforge.backend import resolve_backend
from cryptoforge.local_source_observer import LocalPostgresObserver, bounded_process
from cryptoforge.local_source_provenance import canonical, digest, parse, read_file, stamp, validate_observation

IMAGES = dict(db='sha256:0027bef26712baaee437a4ea48fdf3d2d2e2bc5f0d81615374408ca320f3c7e3',
    rest='sha256:b574528fe109c8343c1247155734d03df8c34b462f342dca0ccc20244fc36ef9',
    api='sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236')
NGINX = b'''events { worker_connections 128; }
http {
  access_log off;
  server {
    listen 80;
    client_max_body_size 32m;
    location /rest/v1/ {
      proxy_pass http://rest:3000/;
      proxy_read_timeout 60s;
      proxy_set_header Host $host;
    }
    location / { return 404; }
  }
}
'''
FIELDS = ['id','exchange','market_type','symbol','pair','timeframe','open_time','close_time',
          'open','high','low','close','volume','turnover','source']
NUMBERS = ('open','high','low','close','volume','turnover')


def _command(argv):
    return bounded_process(argv, '', maximum_bytes=1024**2, maximum_seconds=10)


def inspect_route(repository, *, command=None):
    root = Path(repository).absolute()
    if root.resolve() != root:
        raise ValueError('canonical local route repository required')
    command = command or _command
    context = command(['docker','context','show']).decode().strip()
    if not re.fullmatch('[A-Za-z0-9_.-]{1,80}', context):
        raise ValueError('bounded Docker context required')
    info = parse(command(['docker','context','inspect',context]))
    endpoint = os.environ.get('DOCKER_HOST') or info[0]['Endpoints']['docker']['Host']
    if os.environ.get('DOCKER_HOST') and os.environ.get('DOCKER_CONTEXT'):
        raise ValueError('unambiguous local Docker context required')
    address = urlsplit(endpoint)
    if address.scheme != 'unix' or address.netloc or address.query or address.fragment:
        raise ValueError('same-host Unix Docker endpoint required')
    sock = Path(address.path)
    if not stat.S_ISSOCK(sock.stat().st_mode) or sock.stat().st_uid not in (0, os.getuid()):
        raise ValueError('owned local Docker socket required')
    compose = ['docker','compose','--env-file',str(root/'.local/database/compose.env'),
               '-f',str(root/'docker/database.compose.yml')]
    containers = {}
    for service in ('db','rest','api'):
        identity = command(compose+['ps','-q',service]).decode().strip()
        if not re.fullmatch('[0-9a-f]{64}', identity):
            raise ValueError('one complete owned container per service required')
        value = parse(command(['docker','inspect',identity]))
        if type(value) is not list or len(value) != 1:
            raise ValueError('one original container inspection required')
        containers[service] = value[0]
    nginx = read_file(root/'docker/database-nginx.conf', maximum=4096)
    # -q suppresses successful config-test diagnostics on stderr. Without it,
    # Docker's merged stdout/stderr may append diagnostics after the dump.
    active = command(['docker','exec',containers['api']['Id'],'nginx','-q','-T'])
    header = b'# configuration file /etc/nginx/nginx.conf:\n'
    if header not in active or active.split(header,1)[1].strip() != NGINX.strip():
        raise ValueError('bounded exact nginx route configuration required')
    network_name = next(iter(containers['api']['NetworkSettings']['Networks']))
    network = parse(command(['docker','network','inspect',network_name]))[0]
    return validate_route(containers, root, nginx, endpoint=endpoint,
        network=network,
        nginx_mtime=datetime.fromtimestamp((root/'docker/database-nginx.conf').stat().st_mtime, UTC))


def validate_route(containers, root, nginx, *, endpoint, nginx_mtime, network):
    """Discard secret Config.Env after checking the original inspected topology."""
    root = Path(root)
    if set(containers) != {'db','rest','api'} or nginx != NGINX:
        raise ValueError('exact composed local route required')
    result = {}
    for service, c in containers.items():
        labels = c['Config']['Labels']
        if (c['Id'] in {v['id'] for v in result.values()} or not re.fullmatch('[0-9a-f]{64}', c['Id'])
                or c['Image'] != IMAGES[service] or c['State']['Running'] is not True
                or labels.get('com.docker.compose.project') != 'cryptoforge-database'
                or labels.get('com.docker.compose.service') != service
                or labels.get('com.docker.compose.project.working_dir') != str(root/'docker')):
            raise ValueError('owned pinned local container differs')
        networks = c['NetworkSettings']['Networks']
        if len(networks) != 1:
            raise ValueError('single isolated composed network required')
        network_name, entry = next(iter(networks.items()))
        if service not in entry['Aliases'] or not entry['IPAddress']:
            raise ValueError('original Docker service alias required')
        result[service] = dict(id=c['Id'], image=c['Image'], started_at=c['State']['StartedAt'],
            network=network_name, ip=entry['IPAddress'], aliases=entry['Aliases'])
    if len({c['network'] for c in result.values()}) != 1 or len({c['ip'] for c in result.values()}) != 3:
        raise ValueError('isolated same-network service route required')
    if (set(network['Containers']) != {c['id'] for c in result.values()}
            or network['Name'] != result['api']['network'] or network['Driver'] != 'bridge'
            or network['Labels'].get('com.docker.compose.project') != 'cryptoforge-database'):
        raise ValueError('exclusive composed service network required')
    api = containers['api']
    if (api['NetworkSettings']['Ports'] != {'80/tcp':[dict(HostIp='127.0.0.1',HostPort='54321')]}
            or containers['rest']['NetworkSettings']['Ports'] != {'3000/tcp':None}
            or api['Config'].get('Cmd') != ['nginx','-g','daemon off;']
            or api['Config'].get('Entrypoint') != ['/docker-entrypoint.sh']):
        raise ValueError('exclusive loopback nginx publication required')
    mount = api['Mounts']
    if (len(mount) != 1 or mount[0]['Type'] != 'bind' or mount[0]['RW'] is not False
            or mount[0]['Source'] != str(root/'docker/database-nginx.conf')
            or mount[0]['Destination'] != '/etc/nginx/nginx.conf'
            or stamp(nginx_mtime) > stamp(api['State']['StartedAt'])):
        raise ValueError('original read-only nginx config must predate container start')
    rest = containers['rest']
    if rest['Mounts'] or rest['Config'].get('Entrypoint') is not None or rest['Config'].get('Cmd') != ['/bin/postgrest']:
        raise ValueError('pinned PostgREST executable/config required')
    values = rest['Config']['Env']
    env = dict(v.split('=',1) for v in values if '=' in v)
    if len(env) != sum('=' in v for v in values):
        raise ValueError('duplicate PostgREST environment key')
    uri = urlsplit(env['PGRST_DB_URI'])
    if (uri.scheme not in ('postgres','postgresql') or uri.hostname != 'db' or uri.port != 5432
            or uri.path != '/cryptoforge' or uri.username != 'authenticator' or not uri.password
            or uri.query or uri.fragment or env.get('PGRST_DB_SCHEMAS') != 'public'):
        raise ValueError('explicit PostgREST db route required')
    # Service DNS aliases must be unique within the inspected composed network.
    for service in ('db','rest','api'):
        if any(service in result[other]['aliases'] for other in result if other != service):
            raise ValueError('ambiguous composed service alias')
    return dict(schema_version='local-docker-rest-route-v1', docker_endpoint=endpoint,
        containers=result, nginx_sha256=digest(nginx), database='cryptoforge',
        network_id=network['Id'], backend_url='http://127.0.0.1:54321', secrets_retained=False)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        raise ValueError('local route redirects forbidden')


def rest_rows(url, key):
    started = monotonic()
    before = datetime.now(UTC)
    req = Request(url, headers={'apikey':key,'Authorization':'Bearer '+key,'Accept':'application/json'})
    with build_opener(ProxyHandler({}), _NoRedirect()).open(req, timeout=2) as response:
        if response.status != 200:
            raise ValueError('local REST bounded read failed')
        data = bytearray()
        while True:
            if monotonic()-started > 5:
                raise ValueError('local REST read wall budget exhausted')
            block = response.read1(min(65536, 512*1024+1-len(data)))
            if not block:
                break
            data.extend(block)
            if len(data) > 512*1024:
                raise ValueError('local REST byte budget exhausted')
    return dict(prepared_at=before.isoformat(), completed_at=datetime.now(UTC).isoformat(),
        url=url, body=bytes(data).decode(), body_sha256=digest(bytes(data)))


def _rows(rows):
    result = []
    for row in rows:
        value = {k:row[k] for k in FIELDS}
        for name in NUMBERS:
            if type(value[name]) is bool or len(str(value[name])) > 128:
                raise ValueError('bounded original numeric lexeme required')
            number = Decimal(str(value[name]))
            if not number.is_finite() or abs(number.as_tuple().exponent) > 128 or len(number.as_tuple().digits) > 128:
                raise ValueError('finite original route row required')
            value[name] = list(number.as_integer_ratio())
        for name in ('open_time','close_time'):
            value[name] = stamp(value[name]).isoformat()
        result.append(value)
    return sorted(result, key=lambda row:row['open_time'])


def bind_rows(before, response, after):
    a, b = validate_observation(before), validate_observation(after)
    if (a['identity_sha256'] != b['identity_sha256'] or before['query'] != after['query']
            or not stamp(before['completed_at']) <= stamp(response['prepared_at']) <= stamp(response['completed_at']) <= stamp(after['prepared_at'])
            or digest(response['body'].encode()) != response['body_sha256']):
        raise ValueError('stable causal SQL/REST/SQL reads required')
    sql_a = _rows([parse(row['raw_json'], decimal=True) for row in parse(before['raw_response'])['rows']])
    sql_b = _rows([parse(row['raw_json'], decimal=True) for row in parse(after['raw_response'])['rows']])
    actual = parse(response['body'], decimal=True)
    if type(actual) is not list or len(actual) != before['query']['limit'] or len(sql_a) != len(actual):
        raise ValueError('complete bounded REST rows required')
    if any(type(row) is not dict or set(row) != set(FIELDS) for row in actual):
        raise ValueError('exact bounded REST projection required')
    if canonical(sql_a) != canonical(sql_b) or canonical(sql_a) != canonical(_rows(actual)):
        raise ValueError('original closed UUID/value row binding differs')
    return dict(sql_identity_sha256=a['identity_sha256'], sql_schema_sha256=a['schema_sha256'],
        rows=len(sql_a), normalized_rows_sha256=digest(canonical(sql_a)),
        observed_at=after['completed_at'], latest_candle_age_seconds=b['latest_candle_age_seconds'],
        candle_freshness_pass=b['candle_freshness_pass'])


def observe_backend_route(repository, env, *, pair='BTC/USDT', inspect=None, observe=None, request=None):
    backend = resolve_backend(env)
    if backend.name != 'local' or backend.url != 'http://127.0.0.1:54321' or pair not in ('BTC/USDT','ETH/USDT'):
        raise ValueError('fixed local backend/reference pair required')
    root = Path(repository).absolute()
    inspect = inspect or (lambda:inspect_route(root))
    observe = observe or (lambda:LocalPostgresObserver(root).read(pair=pair,limit=120))
    request = request or rest_rows
    route = inspect()
    before = observe()
    query = dict(select=','.join(FIELDS), exchange='eq.bybit', market_type='eq.spot', pair='eq.'+pair,
        timeframe='eq.5m', close_time='lte.'+before['prepared_at'], order='open_time.desc', limit='120')
    url = backend.url+'/rest/v1/market_candles?'+urlencode(query)
    response = request(url, backend.key)
    after = observe()
    if response['url'] != url or canonical(route) != canonical(inspect()):
        raise ValueError('original local topology/request changed during read')
    rows = bind_rows(before,response,after)
    if before['query'] != dict(pair=pair,timeframe='5m',limit=120):
        raise ValueError('bounded original reference route query required')
    return dict(schema_version='local-rest-instance-observation-v1', route=route, row_binding=rows,
        sql_before=before, rest_response=response, sql_after=after,
        rest_instance_identity_verified=True, scope='observed_local_topology_and_120_specific_closed_rows',
        historical_known_at_verified=False, source_poll_completeness_verified=False,
        full_worker_or_host_qualified=False, economic_profitability_established=False,
        paper_evidence_pass=False, live_admission_granted=False)
