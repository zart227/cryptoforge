"""Bounded, append-only evidence segments with a durable append intention.

The catalogue commits the exact next frame BEFORE writing it. Recovery may
finish only that frame's matching prefix; it never truncates or replaces data.
This is storage integrity, not paper/economic/production admission.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3

MAX_CATALOG_BYTES = 8*1024*1024
KINDS = {'genesis', 'prepared', 'complete', 'terminated'}
CATALOG_TABLES = {
    'identity': 'CREATE TABLE identity (pin TEXT NOT NULL)',
    'head': '''CREATE TABLE head (id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL,sha TEXT NOT NULL,
              active INTEGER NOT NULL,closed INTEGER NOT NULL,pending TEXT,
              recovery_epoch INTEGER NOT NULL DEFAULT 0)''',
    'segments': '''CREATE TABLE segments (ordinal INTEGER PRIMARY KEY,first_seq INTEGER NOT NULL,
                  last_seq INTEGER NOT NULL,count INTEGER NOT NULL,previous TEXT NOT NULL,
                  bytes INTEGER NOT NULL,sealed_sha TEXT)''',
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate segmented evidence field')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite segmented evidence')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def require_sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('explicit evidence SHA256 required')
    return value


@dataclass(frozen=True)
class SegmentPolicy:
    maximum_events: int
    maximum_segments: int
    maximum_segment_events: int
    maximum_segment_bytes: int
    maximum_record_bytes: int
    maximum_total_bytes: int

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in asdict(self).values()):
            raise ValueError('explicit positive segment budgets required')
        if (self.maximum_events > 2**63-1 or self.maximum_segments > 4096
                or not 256 <= self.maximum_record_bytes <= 256*1024
                or not self.maximum_record_bytes <= self.maximum_segment_bytes <= 64*1024*1024
                or self.maximum_total_bytes < self.maximum_segment_bytes
                or self.maximum_total_bytes > 2**63-1):
            raise ValueError('bounded segment policy required')
        capacity = min(self.maximum_segment_events, self.maximum_segment_bytes//self.maximum_record_bytes)
        if self.maximum_events > self.maximum_segments*capacity:
            raise ValueError('segment count cannot hold the frozen maximum event budget')


def _guard(path, *, limit, allow_journal=False):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink():
        raise ValueError('evidence path cannot use symlinks')
    info = path.stat()
    if not path.is_file() or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError('bounded single-link evidence file required')
    for suffix in ('-wal', '-shm', '-journal'):
        if suffix == '-journal' and allow_journal:
            continue
        if Path(str(path)+suffix).exists():
            raise ValueError('evidence sidecar requires writer recovery or review')
    return info


def _fingerprint(path, *, limit):
    before = _guard(path, limit=limit)
    sha = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(65536), b''):
            sha.update(chunk)
    after = _guard(path, limit=limit)
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if identity(before) != identity(after):
        raise ValueError('evidence source changed during hashing')
    return dict(sha256=sha.hexdigest(), identity=identity(after))


def _record(seq, kind, payload, previous):
    body = dict(sequence=seq, kind=kind, payload=payload, previous_sha256=previous)
    return {**body, 'sha256': digest(canonical(body))}


def _frame(record):
    return canonical(record)+b'\n'


def _verified_frame(raw, sequence, previous):
    record = parse(raw)
    if (type(record) is not dict or record.get('kind') not in KINDS
            or type(record.get('payload')) is not dict
            or type(record.get('sequence')) is not int
            or record != _record(sequence, record['kind'], record['payload'], previous)
            or raw != _frame(record)):
        raise ValueError('global source event hash chain differs')
    return record


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class SegmentedEventLog:
    @classmethod
    def create(cls, root, *, source_protocol_sha256, policy):
        require_sha(source_protocol_sha256)
        if not isinstance(policy, SegmentPolicy):
            raise ValueError('typed immutable segment policy required')
        root = Path(root).absolute()
        if root.resolve() != root or root.is_symlink():
            raise ValueError('new nonsymlink evidence namespace required')
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        manifest = dict(schema_version='segmented-evidence-v1', root=str(root),
            source_protocol_sha256=source_protocol_sha256, policy=asdict(policy),
            implementation_sha256=digest(Path(__file__).read_bytes()),
            registered_at=datetime.now(UTC).isoformat(), research_only=True, live_eligible=False)
        raw = canonical(manifest)
        with (root/'manifest.json').open('xb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        (root/'manifest.json').chmod(0o600)
        (root/'segments').mkdir(mode=0o700)
        pin = digest(raw)
        first = root/'segments'/'000001.jsonl'
        with first.open('xb') as output:
            output.flush()
            os.fsync(output.fileno())
        first.chmod(0o600)
        (root/'writer.lock').touch(mode=0o600, exist_ok=False)
        db = sqlite3.connect(root/'catalog.sqlite')
        try:
            for schema in CATALOG_TABLES.values():
                db.execute(schema)
            with db:
                db.execute('INSERT INTO identity VALUES (?)', (pin,))
                db.execute('INSERT INTO head(id,seq,sha,active,closed,pending) VALUES (1,0,?,1,0,NULL)', (pin,))
                db.execute('INSERT INTO segments VALUES (1,1,0,0,?,0,NULL)', (pin,))
        finally:
            db.close()
        (root/'catalog.sqlite').chmod(0o600)
        for directory in (root/'segments', root, *root.parents):
            _sync_directory(directory)
        return cls.open(root, expected_manifest_sha256=pin)

    @classmethod
    def _load(cls, root, pin):
        require_sha(pin)
        root = Path(root).absolute()
        _guard(root/'manifest.json', limit=65536)
        raw = (root/'manifest.json').read_bytes()
        manifest = parse(raw)
        if (digest(raw) != pin or manifest.get('schema_version') != 'segmented-evidence-v1'
                or manifest.get('root') != str(root) or manifest.get('research_only') is not True
                or manifest.get('live_eligible') is not False
                or manifest.get('implementation_sha256') != digest(Path(__file__).read_bytes())):
            raise ValueError('original segmented evidence manifest/source pin differs')
        require_sha(manifest['source_protocol_sha256'])
        obj = cls()
        obj.root, obj.manifest, obj.manifest_sha256 = root, manifest, pin
        obj.policy = SegmentPolicy(**manifest['policy'])
        if (root/'segments').is_symlink() or (root/'segments').resolve() != root/'segments':
            raise ValueError('original segment directory required')
        return obj

    @classmethod
    def open(cls, root, *, expected_manifest_sha256):
        obj = cls._load(root, expected_manifest_sha256)
        with obj._lease(writer=True):
            db = obj._db(writer=True)
            try:
                obj._validate_files(db, verify_hashes=True, allow_pending=True)
                obj._recover(db)
                obj._validate_files(db, verify_hashes=True)
            finally:
                db.close()
        return obj

    @contextmanager
    def _lease(self, *, writer):
        path = self.root/'writer.lock'
        _guard(path, limit=0)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if writer else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def _db(self, *, writer):
        fresh = self._load(self.root, self.manifest_sha256)
        if fresh.manifest != self.manifest or fresh.policy != self.policy:
            raise ValueError('in-memory segment identity differs from original freeze')
        path = self.root/'catalog.sqlite'
        _guard(path, limit=MAX_CATALOG_BYTES, allow_journal=writer)
        db = sqlite3.connect(str(path) if writer else path.as_uri()+'?mode=ro', uri=not writer, timeout=1)
        try:
            if writer:
                db.execute('PRAGMA synchronous=FULL')
            else:
                db.execute('PRAGMA query_only=ON')
            # Validate metadata BEFORE selecting from any application object.
            # An identity VIEW must never get a chance to execute a SQL expression.
            objects = db.execute('SELECT name,type,sql FROM sqlite_master').fetchmany(4)
            normalized = lambda sql: ' '.join(sql.split()).casefold()
            if (len(objects) != len(CATALOG_TABLES) or any(kind != 'table' for _, kind, _ in objects)
                    or {name: normalized(sql) for name, _, sql in objects}
                    != {name: normalized(sql) for name, sql in CATALOG_TABLES.items()}):
                raise ValueError('original segment catalogue schema required')
            # SQLite alone recovers its own hot rollback journal. Never unlink it.
            pin = db.execute('SELECT pin FROM identity').fetchmany(2)
            if pin != [(self.manifest_sha256,)] or db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
                raise ValueError('original DELETE-mode segment catalogue required')
            journal = Path(str(path)+'-journal')
            if writer and journal.exists():
                # A crash before pager spill can leave a NON-hot SQLite journal.
                # Let SQLite finish a transaction on the already verified active
                # catalogue; never unlink sidecars or rewrite a sealed catalogue.
                _guard(journal, limit=MAX_CATALOG_BYTES+65536)
                if self._head(db)[3]:
                    raise ValueError('sealed catalogue sidecar requires review')
                with db:
                    db.execute('UPDATE head SET recovery_epoch=recovery_epoch+1 WHERE id=1')
            _guard(path, limit=MAX_CATALOG_BYTES)
            if {child.name for child in self.root.iterdir()} != {'manifest.json', 'catalog.sqlite', 'writer.lock', 'segments'}:
                raise ValueError('unregistered file in segmented evidence namespace')
            self._check_inventory(db)
            return db
        except Exception:
            db.close()
            raise

    def _path(self, ordinal):
        if type(ordinal) is not int or not 1 <= ordinal <= self.policy.maximum_segments:
            raise ValueError('bounded segment ordinal required')
        return self.root/'segments'/f'{ordinal:06d}.jsonl'

    def _head(self, db):
        row = db.execute('SELECT seq,sha,active,closed,pending FROM head WHERE id=1').fetchone()
        if (not row or type(row[0]) is not int or not 0 <= row[0] <= self.policy.maximum_events
                or row[3] not in (0, 1)):
            raise ValueError('original global event counter required')
        require_sha(row[1])
        return row

    def _storage(self, db):
        head = self._head(db)
        sealed = db.execute('SELECT coalesce(sum(bytes),0) FROM segments WHERE ordinal!=?', (head[2],)).fetchone()[0]
        active = self._path(head[2])
        size = _guard(active, limit=self.policy.maximum_segment_bytes).st_size if active.exists() else 0
        return sealed+size+sum((self.root/name).stat().st_size for name in ('manifest.json', 'catalog.sqlite', 'writer.lock'))

    def _check_inventory(self, db):
        head = self._head(db)
        expected = set()
        for ordinal, count, size in db.execute('SELECT ordinal,count,bytes FROM segments ORDER BY ordinal'):
            if ordinal != len(expected)+1:
                raise ValueError('original bounded segment inventory required')
            expected.add(self._path(ordinal).name)
        # Rotation registers the new empty segment before creating its file.
        active = self._path(head[2])
        if head[4] is not None and not active.exists():
            pending = parse(head[4])
            if (pending.get('ordinal') != head[2] or pending.get('offset') != 0
                    or (count, size) != (0, 0)):
                raise ValueError('missing committed segment inventory')
            expected.discard(active.name)
        observed = set()
        for path in (self.root/'segments').iterdir():
            if path.name not in expected:
                raise ValueError('unregistered segment inventory')
            observed.add(path.name)
        if observed != expected:
            raise ValueError('missing segment inventory')

    def _verify_active_prefix(self, path, *, size, count, first, previous):
        """Verify only committed bytes; pending tail is recovered separately."""
        info = _guard(path, limit=self.policy.maximum_segment_bytes)
        read, observed = 0, 0
        with path.open('rb') as source:
            while read < size:
                raw = source.readline(min(self.policy.maximum_record_bytes+1, size-read))
                if not raw or len(raw) > self.policy.maximum_record_bytes or not raw.endswith(b'\n'):
                    raise ValueError('partial or oversized committed source frame')
                record = _verified_frame(raw, first+observed, previous)
                previous = record['sha256']
                read += len(raw)
                observed += 1
        after = _guard(path, limit=self.policy.maximum_segment_bytes)
        identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if read != size or observed != count or identity(info) != identity(after):
            raise ValueError('committed active source count/identity differs')
        return previous

    def _validate_files(self, db, *, verify_hashes, allow_pending=False):
        head = self._head(db)
        pending = parse(head[4]) if allow_pending and head[4] is not None else None
        expected, previous, last_seq = set(), self.manifest_sha256, 0
        rows = 0
        for ordinal, first, last, count, before, size, sealed in db.execute('SELECT * FROM segments ORDER BY ordinal'):
            rows += 1
            path = self._path(ordinal)
            expected.add(path.name)
            if (ordinal != rows or first != last_seq+1 or last != first+count-1 or before != previous
                    or count < 0 or count > self.policy.maximum_segment_events
                    or size < 0 or size > self.policy.maximum_segment_bytes):
                raise ValueError('segment boundaries or global sequence differ')
            if pending is not None and ordinal == head[2]:
                actual = _guard(path, limit=self.policy.maximum_segment_bytes).st_size if path.exists() else 0
                if (not size <= actual <= size+len(_frame(pending['record']))
                        or (not path.exists() and size)):
                    raise ValueError('pending segment prefix size differs')
                if not path.exists():
                    expected.remove(path.name)
            elif _guard(path, limit=self.policy.maximum_segment_bytes).st_size != size:
                raise ValueError('segment size differs from retained catalogue')
            if ordinal < head[2] or head[3]:
                require_sha(sealed)
                if verify_hashes and _fingerprint(path, limit=self.policy.maximum_segment_bytes)['sha256'] != sealed:
                    raise ValueError('sealed segment SHA differs')
            elif sealed is not None:
                raise ValueError('active segment cannot be prematurely sealed')
            if ordinal == head[2] and not head[3] and verify_hashes and path.exists():
                previous = self._verify_active_prefix(path, size=size, count=count, first=first, previous=previous)
            elif count:
                # Read the last bounded frame without loading the segment.
                with path.open('rb') as source:
                    start = max(0, size-self.policy.maximum_record_bytes-1)
                    source.seek(start)
                    tail = source.read(size-start).splitlines()
                record = parse(tail[-1])
                if record['sequence'] != last:
                    raise ValueError('segment tail sequence differs')
                previous = record['sha256']
            last_seq = last
        if (rows != head[2] or last_seq != head[0] or previous != head[1]
                or {path.name for path in (self.root/'segments').iterdir()} != expected
                or self._storage(db) > self.policy.maximum_total_bytes):
            raise ValueError('missing/extra segment or global storage/head drift')

    def _write_frame(self, path, offset, frame):
        created = False
        if not path.exists():
            if offset:
                raise ValueError('missing prior segment cannot be recreated')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            created = True
        info = _guard(path, limit=self.policy.maximum_segment_bytes)
        if not offset <= info.st_size <= offset+len(frame):
            raise ValueError('unexpected bytes after durable append intention')
        with path.open('rb') as source:
            source.seek(offset)
            prefix = source.read(len(frame)+1)
        if not frame.startswith(prefix):
            raise ValueError('partial frame differs; review required without truncation')
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (info.st_dev, info.st_ino):
                raise ValueError('segment inode changed before append')
            remaining = memoryview(frame)[len(prefix):]
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError('segment write did not advance')
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        after = _guard(path, limit=self.policy.maximum_segment_bytes)
        if (after.st_dev, after.st_ino, after.st_size) != (info.st_dev, info.st_ino, offset+len(frame)):
            raise ValueError('segment changed during append')
        if created:
            _sync_directory(path.parent)

    def _recover(self, db):
        head = self._head(db)
        if head[4] is None:
            return
        pending = parse(head[4])
        record, ordinal, offset = pending['record'], pending['ordinal'], pending['offset']
        row = db.execute('SELECT count,bytes,sealed_sha FROM segments WHERE ordinal=?', (ordinal,)).fetchone()
        if (head[3] or ordinal != head[2] or record['sequence'] != head[0]+1
                or record != _record(head[0]+1, record['kind'], record['payload'], head[1])
                or not row or row[1] != offset or row[2] is not None):
            raise ValueError('original pending append intention differs')
        frame = _frame(record)
        if (record['kind'] not in KINDS or len(frame) > self.policy.maximum_record_bytes
                or offset+len(frame) > self.policy.maximum_segment_bytes
                or record['sequence'] > self.policy.maximum_events):
            raise ValueError('pending append violates original budgets')
        self._write_frame(self._path(ordinal), offset, frame)
        with db:
            db.execute('UPDATE segments SET count=count+1,last_seq=?,bytes=? WHERE ordinal=?',
                       (record['sequence'], offset+len(frame), ordinal))
            db.execute('UPDATE head SET seq=?,sha=?,pending=NULL WHERE id=1',
                       (record['sequence'], record['sha256']))

    def append(self, kind, payload, *, expected_sequence):
        if kind not in KINDS or type(payload) is not dict or type(expected_sequence) is not int or expected_sequence < 1:
            raise ValueError('typed evidence event and expected sequence required')
        payload = parse(canonical(payload))
        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if re.search(r'(?i)secret|api.?key|authorization|password|token|cookie|service.?role|private.?key', key):
                        raise ValueError('credentials cannot enter segmented evidence')
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(payload)
        with self._lease(writer=True):
            db = self._db(writer=True)
            try:
                self._recover(db)
                head = self._head(db)
                if expected_sequence <= head[0]:
                    row = db.execute('SELECT ordinal,first_seq,previous FROM segments WHERE first_seq<=? AND last_seq>=?',
                                     (expected_sequence, expected_sequence)).fetchone()
                    if not row:
                        raise ValueError('original retry sequence is missing')
                    _guard(self._path(row[0]), limit=self.policy.maximum_segment_bytes)
                    sequence, previous = row[1], row[2]
                    with self._path(row[0]).open('rb') as source:
                        while True:
                            frame = source.readline(self.policy.maximum_record_bytes+1)
                            if not frame:
                                raise ValueError('original retry frame is missing')
                            if len(frame) > self.policy.maximum_record_bytes or not frame.endswith(b'\n'):
                                raise ValueError('corrupt retry source frame')
                            record = _verified_frame(frame, sequence, previous)
                            sequence, previous = sequence+1, record['sha256']
                            if record['sequence'] == expected_sequence:
                                if record['kind'] != kind or record['payload'] != payload:
                                    raise ValueError('retry cannot change the original event')
                                return dict(sequence=expected_sequence, sha256=record['sha256'], duplicate=True)
                if head[3] or expected_sequence != head[0]+1 or expected_sequence > self.policy.maximum_events:
                    raise ValueError('closed ledger, sequence gap or global event budget exhausted')
                record = _record(expected_sequence, kind, payload, head[1])
                frame = _frame(record)
                if len(frame) > self.policy.maximum_record_bytes:
                    raise ValueError('event exceeds frozen record budget')
                if self._storage(db)+len(frame)+3*self.policy.maximum_record_bytes+65536 > self.policy.maximum_total_bytes:
                    raise ValueError('global storage budget exhausted before append')
                active = db.execute('SELECT count,bytes FROM segments WHERE ordinal=?', (head[2],)).fetchone()
                ordinal, offset = head[2], active[1]
                rotate = active[0] >= self.policy.maximum_segment_events or offset+len(frame) > self.policy.maximum_segment_bytes
                sealed = None
                if rotate:
                    if ordinal >= self.policy.maximum_segments:
                        raise ValueError('global segment budget exhausted')
                    sealed = _fingerprint(self._path(ordinal), limit=self.policy.maximum_segment_bytes)['sha256']
                    ordinal, offset = ordinal+1, 0
                else:
                    if _guard(self._path(ordinal), limit=self.policy.maximum_segment_bytes).st_size != offset:
                        raise ValueError('unrecorded active segment bytes require review')
                pending = canonical(dict(record=record, ordinal=ordinal, offset=offset)).decode()
                with db:
                    if rotate:
                        db.execute('UPDATE segments SET sealed_sha=? WHERE ordinal=?', (sealed, head[2]))
                        db.execute('INSERT INTO segments VALUES (?,?,?,?,?,0,NULL)',
                                   (ordinal, expected_sequence, head[0], 0, head[1]))
                    db.execute('UPDATE head SET active=?,pending=? WHERE id=1', (ordinal, pending))
                self._recover(db)
                return dict(sequence=expected_sequence, sha256=record['sha256'], duplicate=False)
            finally:
                db.close()

    def seal(self):
        with self._lease(writer=True):
            db = self._db(writer=True)
            try:
                self._recover(db)
                self._validate_files(db, verify_hashes=True)
                head = self._head(db)
                if not head[3]:
                    sha = _fingerprint(self._path(head[2]), limit=self.policy.maximum_segment_bytes)['sha256']
                    with db:
                        db.execute('UPDATE segments SET sealed_sha=? WHERE ordinal=?', (sha, head[2]))
                        db.execute('UPDATE head SET closed=1 WHERE id=1')
                catalog_pin = _fingerprint(self.root/'catalog.sqlite', limit=MAX_CATALOG_BYTES)['sha256']
                return dict(sequence=head[0], head_sha256=head[1], manifest_sha256=self.manifest_sha256,
                            catalog_sha256=catalog_pin)
            finally:
                db.close()

    def iter_events(self, *, expected_head_sha256, expected_catalog_sha256):
        """Read-only generator, at most one bounded frame in memory per yield."""
        require_sha(expected_head_sha256)
        require_sha(expected_catalog_sha256)
        with self._lease(writer=False):
            db = self._db(writer=False)
            try:
                db.execute('BEGIN')
                head = self._head(db)
                if not head[3] or head[4] is not None or head[1] != expected_head_sha256:
                    raise ValueError('sealed original event head required; recover pending via writer')
                before = _fingerprint(self.root/'catalog.sqlite', limit=MAX_CATALOG_BYTES)
                if before['sha256'] != expected_catalog_sha256:
                    raise ValueError('original sealed catalogue pin differs')
                self._validate_files(db, verify_hashes=True)
                previous, sequence = self.manifest_sha256, 0
                for ordinal, first, last, count, prior, size, sealed in db.execute('SELECT * FROM segments ORDER BY ordinal'):
                    path = self._path(ordinal)
                    identity = _guard(path, limit=self.policy.maximum_segment_bytes)
                    sha, observed, bytes_read = hashlib.sha256(), 0, 0
                    with path.open('rb') as source:
                        while True:
                            raw = source.readline(self.policy.maximum_record_bytes+1)
                            if not raw:
                                break
                            if len(raw) > self.policy.maximum_record_bytes or not raw.endswith(b'\n'):
                                raise ValueError('partial or oversized source frame')
                            sequence += 1
                            observed += 1
                            bytes_read += len(raw)
                            record = _verified_frame(raw, sequence, previous)
                            sha.update(raw)
                            previous = record['sha256']
                            yield record
                    after = _guard(path, limit=self.policy.maximum_segment_bytes)
                    if (observed != count or sequence != last or bytes_read != size or sha.hexdigest() != sealed
                            or (identity.st_dev, identity.st_ino, identity.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_mtime_ns)):
                        raise ValueError('segment source/count/SHA changed')
                if sequence != head[0] or previous != head[1] or before != _fingerprint(self.root/'catalog.sqlite', limit=MAX_CATALOG_BYTES):
                    raise ValueError('original catalogue/head changed during streaming verification')
                # A late directory mutation cannot hide a missing/extra source.
                self._validate_files(db, verify_hashes=False)
                fresh = self._load(self.root, self.manifest_sha256)
                if fresh.manifest != self.manifest or fresh.policy != self.policy:
                    raise ValueError('original manifest changed during streaming verification')
            finally:
                db.close()

    def audit(self, *, expected_head_sha256, expected_catalog_sha256):
        count = 0
        for record in self.iter_events(expected_head_sha256=expected_head_sha256,
                                       expected_catalog_sha256=expected_catalog_sha256):
            count += 1
        return dict(schema_version='segmented-evidence-audit-v1', events_checked=count,
            head_sha256=expected_head_sha256, manifest_sha256=self.manifest_sha256,
            catalog_sha256=expected_catalog_sha256,
            source_protocol_sha256=self.manifest['source_protocol_sha256'], storage_integrity_pass=True,
            paper_evidence_pass=False, economic_profitability_established=False, live_admission_granted=False,
            scope='streaming_storage_integrity_only_not_capture_or_economic_admission')
