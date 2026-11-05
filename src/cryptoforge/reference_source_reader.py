"""An opt-in closed-candle reader shared by research roles, never an entry policy.

Every frame binds an externally pinned, fully audited source ledger. A reader
contract must predate its prospective source window. Diagnostic frames cannot
be adopted by that contract. Durable delivery/acknowledgements belong to W7.
"""
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path
import shutil

from cryptoforge.local_source_provenance import (
    canonical, digest, parse, read_file, sha, stamp, _new_root, _write_new,
)
from cryptoforge.reference_source_ledger import (
    FLAGS, ReferenceLedger, audit_reference_ledger, _database, _runtime_paths,
    _sources_ready, _artifact,
)
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.reference_sources import MANDATORY, source_pairs

SCHEMA = 'reference-input-reader-v1'
ROLES = ('candidate', 'control', 'stress')
MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_FRAME_SECONDS = 75
MAX_ORIGINAL_ARTIFACT_BYTES = 1024 * 1024


def runtime_hashes():
    paths = _runtime_paths()
    paths['reference_source_reader.py'] = Path(__file__)
    paths['read_reference_sources.py'] = Path(__file__).resolve().parents[2] / 'scripts/read_reference_sources.py'
    current = {name: digest(path.read_bytes()) for name, path in paths.items()}
    if current != _LOADED_RUNTIME:
        raise ValueError('reader runtime changed; new process and namespace required')
    return current


def _now(clock):
    return stamp((clock or (lambda: datetime.now(UTC)))())


def _disk(path):
    path = Path(path)
    while not path.exists():
        path = path.parent
    if shutil.disk_usage(path).free < 2048 * 1024**2 + 3 * MAX_FRAME_BYTES:
        raise ValueError('reader disk reserve preserved')


def inference_envelope(raw):
    """Copy exact inference parameters; preserve the original under a separate SHA.

    Large training metrics/search traces are retained in the original file,
    never reinterpreted as financial evidence or included in a live model.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ORIGINAL_ARTIFACT_BYTES:
        raise ValueError('bounded original price artifact required')
    original = parse(raw)
    config = original['config']
    keys = ('timeframe','input_candle_state','feature_calculation_contract','feature_lookback_candles',
        'horizon_candles','target_version','fit_information_end','evaluation_information_end')
    target = config.get('target_version')
    if ('target_version' in original and original['target_version'] != target
            or not stamp(config['fit_information_end']) <= stamp(original['trained_at'])
            or type(original['pairs']) is not list or not original['pairs']):
        raise ValueError('original unambiguous model information/scope required')
    envelope = {key:original[key] for key in ('model_family','model_version','trained_at','pairs',
        'feature_names','weights','bias','means','stds')}
    envelope.update(config={key:config[key] for key in keys},
        inference_derivation=dict(schema_version='reference-price-inference-envelope-v1',
            original_artifact_sha256=digest(raw), original_artifact_bytes=len(raw),
            parameter_transformation='identity_no_fit_or_rounding', runtime=runtime_hashes(),
            live_model_publication_performed=False, **FLAGS))
    result = canonical(envelope)
    _artifact(result)
    return result


def prepare_inference_artifact(root, raw):
    envelope = inference_envelope(raw)
    _disk(Path(root).absolute())
    root = _new_root(root)
    # Preserve exact original bytes rather than reserializing its diagnostics.
    import os
    fd = os.open(root / 'original-artifact.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    artifact = parse(envelope)
    pin = _write_new(root / 'artifact.json', artifact)
    ready = _write_new(root / 'complete.json', dict(original_artifact_sha256=digest(raw),
        artifact_sha256=pin, runtime=runtime_hashes(), live_model_publication_performed=False, **FLAGS))
    return dict(root=str(root), original_artifact_sha256=digest(raw), artifact_sha256=pin,
        completion_sha256=ready, original_bytes=len(raw), inference_bytes=len(envelope),
        live_model_publication_performed=False, **FLAGS)


def audit_inference_artifact(reference):
    expected = {'root','original_artifact_sha256','artifact_sha256','completion_sha256',
        'original_bytes','inference_bytes','live_model_publication_performed'} | set(FLAGS)
    if (type(reference) is not dict or set(reference) != expected
            or reference['live_model_publication_performed'] is not False
            or any(reference[k] is not False for k in FLAGS)):
        raise ValueError('original inference artifact external pins required')
    root = Path(reference['root']).absolute()
    original = read_file(root / 'original-artifact.json', maximum=MAX_ORIGINAL_ARTIFACT_BYTES)
    artifact = read_file(root / 'artifact.json', maximum=65536)
    complete = read_file(root / 'complete.json', maximum=65536)
    if (root.resolve() != root or {p.name for p in root.iterdir()} != {'original-artifact.json','artifact.json','complete.json'}
            or digest(original) != sha(reference['original_artifact_sha256'])
            or digest(artifact) != sha(reference['artifact_sha256']) or digest(complete) != sha(reference['completion_sha256'])
            or len(original) != reference['original_bytes'] or len(artifact) != reference['inference_bytes']
            or artifact != inference_envelope(original)
            or complete != canonical(dict(original_artifact_sha256=digest(original), artifact_sha256=digest(artifact),
                runtime=runtime_hashes(), live_model_publication_performed=False, **FLAGS))):
        raise ValueError('original inference artifact derivation differs')
    return dict(original_artifact_sha256=digest(original), artifact_sha256=digest(artifact),
        inference_parameter_identity_pass=True, live_model_publication_performed=False, **FLAGS)


def freeze_reader(root, source_reference, *, clock=None):
    """Register this reader before a new, empty prospective source starts."""
    before = _now(clock)
    source = ReferenceLedger.open(source_reference, clock=clock)
    with source._lease():
        source._check(active=False)
        receipt = source._receipt()
        if (source.manifest['mode'] != 'prospective' or receipt['events'] or receipt['pending']
                or before < stamp(parse(read_file(source.root / 'registered.json'))['registered_at'])
                or not before < stamp(source.manifest['start'])):
            raise ValueError('empty original prospective source required before reader registration')
        value = dict(schema_version=SCHEMA, root=str(Path(root).absolute()),
            registered_at=before.isoformat(), start=source.manifest['start'], end=source.manifest['end'],
            source_initial_reference=source_reference, source_manifest_sha256=source_reference['manifest_sha256'],
            pairs=source.manifest['pairs'], artifact_sha256=source.manifest['artifact_sha256'],
            roles=list(ROLES), runtime=runtime_hashes(), maximum_frame_bytes=MAX_FRAME_BYTES,
            scope='reference_inputs_only_no_cash_entry_policy', **FLAGS)
        _disk(Path(root).absolute())
        root = _new_root(root, forbidden=(source.root,))
        pin = _write_new(root / 'reader.json', value)
        completed = _now(clock)
        if not before <= completed < stamp(value['start']):
            raise ValueError('reader registration missed original source start')
        ready = _write_new(root / 'registered.json', dict(reader_sha256=pin, registered_at=completed.isoformat()))
        final = _now(clock)
        if not completed <= final < stamp(value['start']):
            (root / 'registered.json').unlink()
            from cryptoforge.local_source_provenance import _sync
            _sync(root)
            raise ValueError('reader durable completion missed original source start')
    return dict(root=str(root), reader_sha256=pin, registration_sha256=ready)


def load_reader(reference):
    if type(reference) is not dict or set(reference) != {'root', 'reader_sha256', 'registration_sha256'}:
        raise ValueError('external original reader pins required')
    root = Path(reference['root']).absolute()
    raw = read_file(root / 'reader.json', maximum=65536)
    ready = read_file(root / 'registered.json', maximum=65536)
    if digest(raw) != sha(reference['reader_sha256']) or digest(ready) != sha(reference['registration_sha256']):
        raise ValueError('original reader registration differs')
    value, registered = parse(raw), parse(ready)
    expected = {'schema_version','root','registered_at','start','end','source_initial_reference',
        'source_manifest_sha256','pairs','artifact_sha256','roles','runtime','maximum_frame_bytes','scope'} | set(FLAGS)
    if (set(value) != expected or set(registered) != {'reader_sha256','registered_at'}
            or root.resolve() != root or {p.name for p in root.iterdir()} != {'reader.json', 'registered.json'}
            or raw != canonical(value) or ready != canonical(registered) or value['root'] != str(root)
            or value['schema_version'] != SCHEMA or value['runtime'] != runtime_hashes()
            or value['roles'] != list(ROLES) or value['maximum_frame_bytes'] != MAX_FRAME_BYTES
            or value['scope'] != 'reference_inputs_only_no_cash_entry_policy'
            or registered['reader_sha256'] != reference['reader_sha256']
            or not stamp(value['registered_at']) <= stamp(registered['registered_at']) < stamp(value['start']) < stamp(value['end'])
            or any(value.get(k) is not False for k in FLAGS)):
        raise ValueError('original prospective reader contract differs')
    initial = value['source_initial_reference']
    if (type(initial) is not dict or set(initial) != {'root','manifest_sha256','registration_sha256','database_sha256','head_sha256'}
            or initial['manifest_sha256'] != value['source_manifest_sha256']
            or initial['head_sha256'] != initial['manifest_sha256']
            or value['pairs'] != source_pairs([p for p in value['pairs'] if p not in MANDATORY])):
        raise ValueError('original empty source identity and fixed reader pairs required')
    for key in ('manifest_sha256','registration_sha256','database_sha256','head_sha256'):
        sha(initial[key])
    if value['artifact_sha256'] is not None:
        sha(value['artifact_sha256'])
    return value


def _snapshot(source_reference, *, clock=None):
    """Obtain only current-poll inputs, with first-seen times from audited history."""
    history = audit_reference_ledger(source_reference, clock=clock)
    source = ReferenceLedger.open(source_reference, clock=clock)
    with source._lease():
        observed = source._check(active=False)
        db = _database(source.path, source.policy, readonly=True)
        try:
            seq, head, pending = db.execute('SELECT seq,head,pending FROM state WHERE id=1').fetchone()
            if pending is not None:
                raise ValueError('unfinished original source poll cannot produce reader inputs')
            complete, windows = source._windows(db)
            if complete is None or observed < stamp(complete['completed_at']):
                raise ValueError('completed original source observation required before reader capture')
            complete_seq = db.execute("SELECT max(seq) FROM events WHERE kind='poll_complete'").fetchone()[0]
            copied = {}
            for pair, window in sorted(windows.items()):
                rows = []
                for row in window['derived']['rows']:
                    original = db.execute('SELECT raw,known_at,event_seq FROM versions WHERE source_id=? AND version=?',
                        (row['source_id'], row['version_sha256'])).fetchone()
                    if (original is None or original[0] != canonical(row['raw_row'])
                            or original[2] > window['event_seq'] or stamp(original[1]) > stamp(row['known_at'])):
                        raise ValueError('audited global first-seen source version missing')
                    rows.append(dict(row, first_seen_at=original[1], first_seen_event_sequence=original[2]))
                copied[pair] = dict(window, derived=dict(window['derived'], rows=rows))
            forecasts = []
            for kind, raw in db.execute('SELECT kind,payload FROM events WHERE seq>? ORDER BY seq', (complete_seq,)):
                if kind != 'forecast' or len(forecasts) >= len(source.manifest['pairs']):
                    raise ValueError('bounded original current-poll forecast batch required')
                event = parse(raw)
                if not stamp(event['payload']['predicted_at']) <= stamp(event['recorded_at']) <= observed:
                    raise ValueError('future original source forecast unavailable to reader')
                forecasts.append(event)
            value = dict(source_reference=source_reference, source_manifest=source.manifest,
                source_head_sequence=seq, source_head_sha256=head, source_audit=history,
                poll_complete=complete, windows=copied, forecasts=forecasts, source_observed_at=observed.isoformat())
            if len(canonical(value)) > MAX_FRAME_BYTES - 65536:
                raise ValueError('reader original source payload budget exhausted')
        finally:
            db.close()
        source._check(active=False)
    return value


def _bind_contract(value, reference, at):
    if reference is None:
        return 'diagnostic'
    contract = load_reader(reference)
    manifest, actual = value['source_manifest'], value['source_reference']
    initial = contract['source_initial_reference']
    if (manifest['mode'] != 'prospective' or actual['manifest_sha256'] != contract['source_manifest_sha256']
            or any(actual[k] != initial[k] for k in ('root', 'manifest_sha256', 'registration_sha256'))
            or manifest['pairs'] != contract['pairs'] or manifest['artifact_sha256'] != contract['artifact_sha256']
            or manifest['start'] != contract['start'] or manifest['end'] != contract['end']
            or not stamp(contract['start']) <= at <= stamp(contract['end'])):
        raise ValueError('original registered reader/source scope or window differs')
    return 'registered_reference_inputs_only'


def capture_frame(root, source_reference, *, reader_reference=None, clock=None):
    before = _now(clock)
    pins = runtime_hashes()
    value = _snapshot(source_reference, clock=clock)
    observed = stamp(value['source_observed_at'])
    scope = _bind_contract(value, reader_reference, observed)
    if not before <= observed <= before + timedelta(seconds=MAX_FRAME_SECONDS):
        raise ValueError('reader original snapshot wall/clock budget exhausted')
    frame = dict(schema_version=SCHEMA, root=str(Path(root).absolute()), runtime=pins, scope=scope,
        reader_reference=reader_reference, capture_started_at=before.isoformat(), roles=list(ROLES),
        worker_prediction_batch_available=False, **value, **FLAGS)
    if len(canonical(frame)) > MAX_FRAME_BYTES:
        raise ValueError('reader frame byte budget exhausted')
    _disk(Path(root).absolute())
    forbidden = [source_reference['root']]
    if reader_reference is not None:
        forbidden.append(reader_reference['root'])
    root = _new_root(root, forbidden=forbidden)
    pin = _write_new(root / 'frame.json', frame)
    completed = _now(clock)
    if runtime_hashes() != pins or not observed <= completed <= before + timedelta(seconds=MAX_FRAME_SECONDS):
        raise ValueError('reader capture completion drifted')
    if reader_reference is not None:
        _bind_contract(value, reader_reference, completed)
    ready = _write_new(root / 'complete.json', dict(frame_sha256=pin, completed_at=completed.isoformat()))
    final = _now(clock)
    if (not completed <= final <= before + timedelta(seconds=MAX_FRAME_SECONDS)
            or reader_reference is not None and final > stamp(value['source_manifest']['end'])):
        (root / 'complete.json').unlink()
        from cryptoforge.local_source_provenance import _sync
        _sync(root)
        raise ValueError('reader durable completion drifted')
    return dict(root=str(root), frame_sha256=pin, completion_sha256=ready)


def _load_frame(reference, expected_reader_reference):
    if type(reference) is not dict or set(reference) != {'root', 'frame_sha256', 'completion_sha256'}:
        raise ValueError('external original reader frame pins required')
    root = Path(reference['root']).absolute()
    raw = read_file(root / 'frame.json', maximum=MAX_FRAME_BYTES)
    ready = read_file(root / 'complete.json', maximum=65536)
    if digest(raw) != sha(reference['frame_sha256']) or digest(ready) != sha(reference['completion_sha256']):
        raise ValueError('original reader frame/completion pin differs')
    frame, completed = parse(raw), parse(ready)
    expected = {'schema_version','root','runtime','scope','reader_reference','capture_started_at','roles',
        'worker_prediction_batch_available','source_reference','source_manifest','source_head_sequence',
        'source_head_sha256','source_audit','poll_complete','windows','forecasts','source_observed_at'} | set(FLAGS)
    if (set(frame) != expected or set(completed) != {'frame_sha256','completed_at'}
            or root.resolve() != root or {p.name for p in root.iterdir()} != {'frame.json', 'complete.json'}
            or raw != canonical(frame) or ready != canonical(completed) or frame['root'] != str(root)
            or frame['schema_version'] != SCHEMA or frame['runtime'] != runtime_hashes()
            or frame['roles'] != list(ROLES) or frame['reader_reference'] != expected_reader_reference
            or completed['frame_sha256'] != reference['frame_sha256']
            or not stamp(frame['capture_started_at']) <= stamp(frame['source_observed_at']) <= stamp(completed['completed_at'])
                <= stamp(frame['capture_started_at']) + timedelta(seconds=MAX_FRAME_SECONDS)
            or frame['worker_prediction_batch_available'] is not False
            or any(frame.get(k) is not False for k in FLAGS)):
        raise ValueError('original reader frame schema/clock/scope differs')
    scope = _bind_contract(frame, expected_reader_reference, stamp(completed['completed_at']))
    if frame['scope'] != scope:
        raise ValueError('diagnostic frame cannot be adopted as registered inputs')
    return frame, raw


def audit_frame(reference, *, reader_reference=None):
    """Offline source replay; no live polling and no retrospective qualification."""
    frame, _ = _load_frame(reference, reader_reference)
    original = _snapshot(frame['source_reference'], clock=lambda: stamp(frame['source_observed_at']))
    if any(frame[k] != v for k, v in original.items()):
        raise ValueError('reader source/first-seen/forecast replay differs')
    return dict(frame_sha256=reference['frame_sha256'], source_frame_integrity_pass=True,
        source_rows_checked=sum(len(w['derived']['rows']) for w in frame['windows'].values()),
        original_forecasts_checked=len(frame['forecasts']), scope=frame['scope'],
        worker_prediction_batch_available=False, **FLAGS)


class ReferenceMarketReader:
    """Closed120 interface and original price diagnostics over ONE shared frame."""
    @classmethod
    def open(cls, reference, *, role, reader_reference=None, clock=None):
        if role not in ROLES:
            raise ValueError('explicit candidate/control/stress reader role required')
        audit_frame(reference, reader_reference=reader_reference)
        frame, raw = _load_frame(reference, reader_reference)
        obj = cls()
        obj.reference = parse(canonical(reference))
        obj.reader_reference = parse(canonical(reader_reference))
        obj.role, obj.clock, obj._raw = role, clock, raw
        obj._last_clock = _now(clock)
        if obj._last_clock < stamp(frame['source_observed_at']):
            raise ValueError('reader cannot receive a future source frame')
        return obj

    def _frame(self):
        frame, raw = _load_frame(self.reference, self.reader_reference)
        if raw != self._raw:
            raise ValueError('original delivered reader frame changed')
        now = _now(self.clock)
        if now < max(stamp(frame['source_observed_at']), self._last_clock):
            raise ValueError('reader consumer clock moved backwards')
        self._last_clock = now
        return frame, now

    def status(self):
        frame, now = self._frame()
        manifest = frame['source_manifest']
        inside = stamp(manifest['start']) <= now <= stamp(manifest['end'])
        ready = inside and _sources_ready(frame['windows'], now)
        return dict(frame_sha256=self.reference['frame_sha256'], role=self.role,
            closed_candles_ready=ready, source_window_open=inside,
            source_observed_at=frame['source_observed_at'],
            source_status={p:w['derived']['status'] for p,w in frame['windows'].items()},
            scope=frame['scope'], worker_prediction_batch_available=False, **FLAGS)

    def read_candles(self, pair, *, timeframe='5m', limit=120):
        frame, _ = self._frame()
        if timeframe != '5m' or type(limit) is not int or limit != 120 or pair not in frame['windows']:
            raise ValueError('original frozen pair/closed5m/bounded120 reader contract required')
        if not self.status()['closed_candles_ready']:
            raise ValueError('missing/failed/stale mandatory reference source blocks reader')
        return [CandleRow(pair, pair.replace('/', ''), datetime.fromtimestamp(r['open_ms']/1000, UTC),
            *[Decimal(v) for v in r['raw_row'][1:6]], cache_observed_at=stamp(r['known_at']))
            for r in frame['windows'][pair]['derived']['rows']]

    def original_forecasts(self):
        frame, now = self._frame()
        ready = self.status()['closed_candles_ready']
        return [dict(original=event, usable_price_input_now=ready and now < stamp(event['payload']['target_information_end']),
            entry_decision_available=False) for event in frame['forecasts']]

    def features(self, pair):
        from cryptoforge.model_training import extract_features
        candles = self.read_candles(pair)
        with localcontext(Context(prec=28)):
            return extract_features(candles, [r.volume for r in candles])


_paths = _runtime_paths()
_paths['reference_source_reader.py'] = Path(__file__)
_paths['read_reference_sources.py'] = Path(__file__).resolve().parents[2] / 'scripts/read_reference_sources.py'
_LOADED_RUNTIME = {name:digest(path.read_bytes()) for name,path in _paths.items()}
