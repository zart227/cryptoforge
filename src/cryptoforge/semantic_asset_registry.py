"""Source-evidenced exact alias candidates; never semantic grounding or execution."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

from cryptoforge import semantic_source_collector as collector, semantic_source_snapshot as snapshots
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp


MAX_REGISTRY_BYTES = 4_000_000
PAIR = re.compile(r'(?<![\w/])[A-Z0-9]{1,20}/?USDT(?![\w/])')


def _implementation():
    return {'asset_registry':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'capture_dependencies':collector._implementation()}


def _pattern(surface):
    # Exact Unicode code points/case; no substring, normalization or fuzzy match.
    return re.compile(r'(?<![\w/])'+re.escape(surface)+r'(?![\w/])')


def _sha(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise ValueError('full SHA256 required')


def _compile(definition, evidence):
    exact_fields(definition, {'schema_version','registry_version','origin','assets'})
    if (definition['schema_version'] != 'semantic-asset-definitions-v1'
            or definition['origin'] not in ('synthetic','assistant_curated_source_candidates')):
        raise ValueError('explicit asset candidate definitions and origin required')
    snapshots._text(definition['registry_version'],100,identifier=True)
    assets = definition['assets']
    if not isinstance(assets,list) or not 1 <= len(assets) <= 128:
        raise ValueError('one to 128 closed assets required')
    if not isinstance(evidence,list) or not 1 <= len(evidence) <= 16:
        raise ValueError('one to 16 source evidence records required')
    by_hash = {}
    for row in evidence:
        exact_fields(row, {'raw_sha256','source_recorded_at','source_url','title','original_text',
                          'receipt_sha256','commit_sha256'})
        for key in ('raw_sha256','receipt_sha256','commit_sha256'): _sha(row[key])
        timestamp(row['source_recorded_at'])
        snapshots._text(row['title'],1024); snapshots._text(row['original_text'],32000)
        collector.transport.article_url(row['source_url'])
        if row['raw_sha256'] in by_hash:
            raise ValueError('unique explicit capture hash per registry required')
        by_hash[row['raw_sha256']] = deepcopy(row)
    seen,normalized,aliases,used = set(),[],[],set()
    for asset in assets:
        exact_fields(asset, {'asset_id','ticker','aliases'})
        asset_id,ticker = asset['asset_id'],asset['ticker']
        if (not isinstance(asset_id,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,119}',asset_id)
                or asset_id in seen or not isinstance(ticker,str) or not re.fullmatch('[A-Z0-9]{1,20}',ticker)):
            raise ValueError('unique namespace asset ID and explicit ticker required')
        seen.add(asset_id)
        rows = asset['aliases']
        if not isinstance(rows,list) or not 1 <= len(rows) <= 8:
            raise ValueError('one to eight aliases per asset required')
        local,clean = set(),[]
        for alias in rows:
            exact_fields(alias, {'surface','kind','capture_sha256'})
            surface,kind = alias['surface'],alias['kind']
            snapshots._text(surface,120)
            if not isinstance(kind,str) or kind not in {'pair','ticker','name'}:
                raise ValueError('explicit pair/ticker/name alias kind required')
            if any(ord(c)<32 for c in surface) or surface != surface.strip():
                raise ValueError('literal printable alias required')
            if (kind == 'ticker' and surface != ticker) or (kind == 'pair' and surface not in {ticker+'USDT',ticker+'/USDT'}):
                raise ValueError('alias must agree with declared ticker and USDT quote')
            if (kind,surface) in local:
                raise ValueError('duplicate alias within one asset')
            local.add((kind,surface)); _sha(alias['capture_sha256'])
            source = by_hash.get(alias['capture_sha256'])
            if source is None:
                raise ValueError('alias evidence must name a supplied capture')
            proof = None
            for field in ('title','original_text'):
                match = _pattern(surface).search(source[field])
                if match:
                    proof = {'capture_sha256':alias['capture_sha256'],'field':field,
                        'start':match.start(),'end':match.end(),'text_sha256':digest(source[field]),
                        'source_recorded_at':source['source_recorded_at']}
                    break
            if proof is None:
                raise ValueError('exact standalone alias evidence span required')
            clean.append(deepcopy(alias)); used.add(alias['capture_sha256'])
            aliases.append({'asset_id':asset_id,'ticker':ticker,'kind':kind,'surface':surface,'proof':proof})
        normalized.append({'asset_id':asset_id,'ticker':ticker,
                           'aliases':sorted(clean,key=lambda r:(r['kind'],r['surface']))})
    if len(aliases)>512 or used != set(by_hash):
        raise ValueError('bounded aliases and no unused source evidence required')
    definition = {**deepcopy(definition),'assets':sorted(normalized,key=lambda r:r['asset_id'])}
    core = {'schema_version':'semantic-asset-registry-v1','definition':definition,
        'source_evidence':sorted(by_hash.values(),key=lambda r:r['raw_sha256']),
        'aliases':sorted(aliases,key=lambda r:(r['kind'],r['surface'],r['asset_id'])),
        'scope':'bybit_global_spot_usdt_lexical_candidates_only',
        'identity_assurance':'declared_namespace_identity_and_exact_source_spelling',
        'raw_verification_at_freeze':True,'publisher_identity_attested':False,
        'global_token_identity_verified':False,'listing_or_tradability_verified':False,
        'human_gold':False,'implementation':_implementation()}
    result = {**core,'registry_sha256':digest(core)}
    if len(canonical(result).encode()) > MAX_REGISTRY_BYTES:
        raise ValueError('registry byte limit exceeded; no truncation')
    return result


def freeze(directory, *, definition, captures):
    if not isinstance(captures,list) or not 1 <= len(captures) <= 16:
        raise ValueError('one to 16 explicit completed captures required')
    evidence = []
    for path in captures:
        verified = collector.read_capture(path)
        row,chain = verified['row'],verified['evidence']
        evidence.append({'raw_sha256':row['capture_sha256'],'source_recorded_at':row['recorded_at'],
            'source_url':row['source_url'],'title':row['title'],'original_text':row['original_text'],
            'receipt_sha256':chain['receipt_sha256'],'commit_sha256':chain['commit_sha256']})
    registry = _compile(definition,evidence)
    directory = Path(directory); directory.mkdir(mode=0o700)
    collector._write(directory,'registry.json',registry); collector._sync(directory)
    registered = datetime.now(timezone.utc).isoformat()
    if any(timestamp(registered)<timestamp(r['source_recorded_at']) for r in evidence):
        raise ValueError('registry clock precedes known source capture; incomplete registration')
    commit = collector._seal({'schema_version':'semantic-asset-registration-v1',
        'registry_sha256':registry['registry_sha256'],'registered_at':registered,
        'time_assurance':'local_after_registry_fsync_not_external_clock_attestation'},'registration_sha256')
    collector._write(directory,'registration.json',commit)
    collector._sync(directory); collector._sync(directory.parent)
    return {'registry':registry,'registration':commit}


def validate_bundle(bundle):
    exact_fields(bundle, {'registry','registration'})
    registry,commit = bundle['registry'],bundle['registration']
    if not isinstance(registry,dict):
        raise ValueError('closed registry required')
    rebuilt = _compile(registry.get('definition'),registry.get('source_evidence'))
    if canonical(rebuilt) != canonical(registry):
        raise ValueError('registry content, proof or implementation changed')
    collector._check(commit,'registration_sha256',{'schema_version','registry_sha256','registered_at','time_assurance'})
    if (commit['schema_version'] != 'semantic-asset-registration-v1'
            or commit['registry_sha256'] != registry['registry_sha256']
            or commit['time_assurance'] != 'local_after_registry_fsync_not_external_clock_attestation'
            or any(timestamp(commit['registered_at']) < timestamp(r['source_recorded_at']) for r in registry['source_evidence'])):
        raise ValueError('bound registry registration time required')
    return bundle


def read_registry(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('registered asset directory required')
    return validate_bundle({'registry':collector._json(directory,'registry.json',MAX_REGISTRY_BYTES),
                            'registration':collector._json(directory,'registration.json')})


def _known(bundle, decision):
    registered = timestamp(bundle['registration']['registered_at'])
    return [r for r in bundle['registry']['aliases']
            if max(registered,timestamp(r['proof']['source_recorded_at'])) <= decision]


def _lookup(known, surface, kind):
    matches = [r for r in known if r['surface'] == surface and r['kind'] == kind]
    candidates = sorted({r['asset_id'] for r in matches})
    return {'surface':surface,'kind':kind,
        'status':'unknown' if not candidates else 'unique_alias' if len(candidates)==1 else 'ambiguous',
        'candidate_asset_id':candidates[0] if len(candidates)==1 else None,
        'candidates':candidates,'resolved_asset_id':None,'requires_context_review':True,
        'context_grounding_verified':False,'can_authorize_trades':False}


def lookup(bundle, *, surface, kind, decision_time):
    validate_bundle(bundle); snapshots._text(surface,120)
    if not isinstance(kind,str) or kind not in {'pair','ticker','name'}:
        raise ValueError('explicit alias kind required')
    decision = timestamp(decision_time)
    core = {'schema_version':'semantic-asset-lookup-v1',
        'registry_origin':bundle['registry']['definition']['origin'],
        'registry_sha256':bundle['registry']['registry_sha256'],
        'registration_sha256':bundle['registration']['registration_sha256'],
        'decision_time':decision.isoformat(),**_lookup(_known(bundle,decision),surface,kind),'api_calls':0}
    return {**core,'lookup_sha256':digest(core)}


def resolve_snapshot(snapshot, bundle, *, decision_time, ttl_seconds):
    validate_bundle(bundle)
    view = snapshots.as_of(snapshot,decision_time=decision_time,ttl_seconds=ttl_seconds)
    known = _known(bundle,timestamp(decision_time))
    texts = view['model_state']['texts']
    if len(texts)>16 or sum(len((r['title']+r['original_text']).encode()) for r in texts)>1_000_000:
        raise ValueError('bounded source candidate batch required')
    mentions = []
    for row in texts:
        for field in ('title','original_text'):
            text = row[field]; spans = set()
            def add(matches,kind):
                for match in matches:
                    spans.add((match.start(),match.end(),kind))
                    if len(spans)+len(mentions)>128:
                        raise ValueError('mention limit exceeded; no truncation')
            add(PAIR.finditer(text),'pair')
            for alias in {(r['surface'],r['kind']) for r in known}:
                add(_pattern(alias[0]).finditer(text),alias[1])
            for start,end,kind in sorted(spans):
                mentions.append({'content_sha256':row['content_sha256'],'field':field,
                    'start':start,'end':end,'offset_unit':'unicode_code_points',
                    'field_sha256':digest(text),'lookup':_lookup(known,text[start:end],kind)})
                if len(mentions)>128:
                    raise ValueError('mention limit exceeded; no truncation')
    core = {'schema_version':'semantic-asset-candidates-v1','source_origin':snapshot['origin'],
        'registry_origin':bundle['registry']['definition']['origin'],
        'source_snapshot_sha256':snapshot['snapshot_sha256'],'source_view_sha256':view['view_sha256'],
        'registry_sha256':bundle['registry']['registry_sha256'],
        'registration_sha256':bundle['registration']['registration_sha256'],
        'decision_time':view['decision_time'],'ttl_seconds':ttl_seconds,'mentions':mentions,
        'candidate_state_sha256':digest(mentions),'lexical_coverage_verified':False,
        'context_grounding_verified':False,'source_coverage_verified':False,
        'empty_result_is_negative_label':False,'event_labels_created':False,
        'global_token_identity_verified':False,'can_authorize_trades':False,
        'api_calls':0,'training_executed':False}
    return {**core,'candidates_sha256':digest(core)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    build = commands.add_parser('freeze'); build.add_argument('--definition',type=Path,required=True)
    build.add_argument('--capture',type=Path,action='append',required=True)
    build.add_argument('--directory',type=Path,required=True)
    query = commands.add_parser('lookup'); query.add_argument('--surface',required=True)
    query.add_argument('--kind',choices=['pair','ticker','name'],required=True)
    resolve = commands.add_parser('resolve'); resolve.add_argument('--snapshot',type=Path,required=True)
    resolve.add_argument('--ttl-seconds',type=int,required=True)
    for sub in (query,resolve):
        sub.add_argument('--registry',type=Path,required=True); sub.add_argument('--decision-time',required=True)
        sub.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    if args.command == 'freeze':
        result = freeze(args.directory,definition=snapshots._read(args.definition,128000),captures=args.capture)
        print('Asset candidate registry frozen at '+result['registration']['registered_at'])
        return 0
    bundle = read_registry(args.registry)
    if args.command == 'lookup':
        result = lookup(bundle,surface=args.surface,kind=args.kind,decision_time=args.decision_time)
    else:
        result = resolve_snapshot(snapshots._read(args.snapshot,snapshots.MAX_SNAPSHOT_BYTES),bundle,
            decision_time=args.decision_time,ttl_seconds=args.ttl_seconds)
    collector._write(args.output.parent,args.output.name,result)
    print('Exact asset candidates saved; no semantic judgment, network or training')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
