"""v2 worker payload policy over the unchanged durable segmented storage.

Only known mark/error maps can use pair identifiers as keys. Credential fields
inside provider data keep the original fail-closed policy. The append transaction
is version-copied so no global regex or frozen storage implementation is changed.
"""
import re
from cryptoforge.evidence_segments import (
    SegmentedEventLog, KINDS, canonical, parse, _guard, _verified_frame,
    _record, _frame, _fingerprint,
)

_PAIR_MAPS = {('inputs','quotes'), ('inputs','filters')}
_ERROR_MAPS = {('inputs','payload','errors'), ('result','errors')}
_CREDENTIAL = re.compile(r'(?i)secret|api.?key|authorization|password|token|cookie|service.?role|private.?key')


def _pair(key):
    return (type(key) is str and 0 < len(key) <= 256 and key.endswith('/USDT')
            and all(33 <= ord(c) <= 126 for c in key))


def _check_public_payload(payload):
    def check(value,path=()):
        if type(value) is dict:
            for key,child in value.items():
                allowed_pair = path in _PAIR_MAPS and _pair(key)
                allowed_error = path in _ERROR_MAPS and (_pair(key) or key.startswith('exit:') and _pair(key[5:]))
                if _CREDENTIAL.search(key) and not (allowed_pair or allowed_error):
                    raise ValueError('credentials cannot enter v2 worker evidence')
                check(child,path+(key,))
        elif type(value) is list:
            for child in value:check(child,path+('[]',))
    check(payload)


class SegmentedWorkerEventLogV2(SegmentedEventLog):
    def append(self, kind, payload, *, expected_sequence):
        if kind not in KINDS or type(payload) is not dict or type(expected_sequence) is not int or expected_sequence < 1:
            raise ValueError('typed evidence event and expected sequence required')
        payload = parse(canonical(payload))
        _check_public_payload(payload)
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

    def iter_events(self, *, expected_head_sha256, expected_catalog_sha256):
        for record in super().iter_events(expected_head_sha256=expected_head_sha256,
                expected_catalog_sha256=expected_catalog_sha256):
            _check_public_payload(record['payload'])
            yield record
