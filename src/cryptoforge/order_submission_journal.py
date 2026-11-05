"""Persist market-order intent before submit; uncertain attempts are never retried."""
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import sqlite3
from cryptoforge.execution_controls import OrderControlBlocked


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class OrderSubmissionJournal:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {'order_submissions', 'order_decision_contexts'}:
                raise ValueError('isolated order submission database required')
            db.execute('CREATE TABLE IF NOT EXISTS order_submissions ('
                'link TEXT PRIMARY KEY, symbol TEXT NOT NULL, payload TEXT NOT NULL, sha TEXT NOT NULL, '
                'status TEXT NOT NULL, response TEXT, observed_at TEXT NOT NULL, last_error TEXT) WITHOUT ROWID')
            db.execute('CREATE TABLE IF NOT EXISTS order_decision_contexts ('
                'link TEXT PRIMARY KEY, payload TEXT NOT NULL, sha TEXT NOT NULL, '
                'enqueued INTEGER NOT NULL DEFAULT 0) WITHOUT ROWID')
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def prepare(self, *, symbol, side, qty, order_link_id):
        if (not symbol or not order_link_id or side not in {'Buy', 'Sell'}
                or not isinstance(qty, Decimal) or not qty.is_finite() or qty <= 0):
            raise ValueError('valid market order intent required')
        raw = encoded(dict(symbol=symbol, side=side, qty=format(qty, 'f'), order_link_id=order_link_id))
        sha = hashlib.sha256(raw.encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT payload,sha,status,response FROM order_submissions WHERE link=?', (order_link_id,)).fetchone()
            if prior:
                if prior[0] != raw or prior[1] != sha:
                    raise ValueError('order link already bound to different intent')
                if prior[2] == 'acknowledged':
                    return json.loads(prior[3])
                raise ValueError('order attempt already recorded; reconcile without resubmission')
            pending = db.execute("SELECT symbol FROM order_submissions WHERE status IN ('prepared','unknown')").fetchall()
            if any(row[0] == symbol for row in pending) or (side == 'Buy' and pending):
                raise ValueError('unresolved submission blocks this order')
            db.execute('INSERT INTO order_submissions(link,symbol,payload,sha,status,observed_at) VALUES (?,?,?,?,?,?)',
                (order_link_id, symbol, raw, sha, 'prepared', datetime.now(UTC).isoformat()))
        return None

    def capture_decision_context(self, intent, record):
        """Commit the original reasons before entering the order submission path."""
        normalized = {**intent, 'qty': format(intent['qty'], 'f')}
        expected = 'approve_entry' if intent['side'] == 'Buy' else 'approve_exit'
        if (intent['side'] not in {'Buy', 'Sell'} or record.get('mode') != 'live'
                or record.get('decision') != expected
                or record.get('pair', '').replace('/', '') != intent['symbol']
                or not isinstance(record.get('reasons'), list) or not record['reasons']):
            raise ValueError('matching original order decision required')
        raw = encoded({'intent': normalized, 'record': record})
        sha = hashlib.sha256(raw.encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT payload,sha FROM order_decision_contexts WHERE link=?',
                               (intent['order_link_id'],)).fetchone()
            if prior:
                if hashlib.sha256(prior[0].encode()).hexdigest() != prior[1]:
                    raise ValueError('corrupt original decision context')
                if json.loads(prior[0])['intent'] != normalized:
                    raise ValueError('decision context bound to different intent')
                return json.loads(prior[0])['record']  # First context wins.
            db.execute('INSERT INTO order_decision_contexts(link,payload,sha) VALUES (?,?,?)',
                       (intent['order_link_id'], raw, sha))
        return json.loads(raw)['record']

    def recover_decisions(self, outbox):
        """Queue original contexts only after an exact journal ACK/observation.

        This method never submits or retries an exchange operation. Enqueue is
        durable before marking the context, so process death is safe on either side.
        """
        with self.connect() as db:
            rows = db.execute('SELECT c.link,c.payload,c.sha,s.payload,s.sha,s.response '
                'FROM order_decision_contexts c JOIN order_submissions s ON s.link=c.link '
                "WHERE c.enqueued=0 AND s.status IN ('acknowledged','observed')").fetchall()
        recovered = 0
        for link, raw, sha, intent_raw, intent_sha, response_raw in rows:
            if (hashlib.sha256(raw.encode()).hexdigest() != sha
                    or hashlib.sha256(intent_raw.encode()).hexdigest() != intent_sha):
                raise ValueError('corrupt decision recovery evidence')
            context = json.loads(raw)
            intent = json.loads(intent_raw)
            if context['intent'] != intent:
                raise ValueError('decision recovery intent mismatch')
            response = json.loads(response_raw)
            result = response.get('result') or {}
            observations = response.get('exchange_observations') or []
            if observations:
                if (any(o.get('orderLinkId') != link or o.get('symbol') != intent['symbol']
                        or o.get('side') != intent['side'] or not o.get('orderId') for o in observations)
                        or len({o['orderId'] for o in observations}) != 1):
                    raise ValueError('conflicting decision recovery observation')
                order_id = observations[0]['orderId']
                order = {'result': {'orderId': order_id, 'orderLinkId': link},
                         'exchange_observations': observations}
                source = 'exact_exchange_observation'
            else:
                if (response.get('retCode') != 0 or not result.get('orderId')
                        or result.get('orderLinkId', link) != link):
                    raise ValueError('exact decision recovery acknowledgment required')
                order_id, order, source = result['orderId'], response, 'submission_acknowledgment'
            record = context['record']
            record['idempotency_key'] = f"executor:live:{record['pair']}:order:{order_id}"
            record['features'].update(order=order, decision_context_provenance='original_pre_submission',
                order_binding_source=source)
            outbox.enqueue('trade_decisions', [record],
                           dict(on_conflict='idempotency_key', resolution='ignore-duplicates'))
            with self.connect() as db:
                db.execute('UPDATE order_decision_contexts SET enqueued=1 WHERE link=?', (link,))
            recovered += 1
        return recovered

    def finish(self, link, status, response=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE order_submissions SET status=?,response=?,last_error=? WHERE link=?',
                (status, encoded(response) if response is not None else None, error, link))

    def buy_reservations(self, *, exclude_link=None):
        """Conservative durable quote reserves, including ACKs not yet visible remotely."""
        with self.connect() as db:
            rows = db.execute('SELECT link,payload,sha,status FROM order_submissions').fetchall()
        reserved = {}
        for link, raw, sha, status in rows:
            if hashlib.sha256(raw.encode()).hexdigest() != sha:
                raise ValueError('corrupt submission intent')
            if status not in {'prepared','unknown','acknowledged','observed','blocked','released_unfilled','released_closed'}:
                raise ValueError('unknown submission status')
            intent = json.loads(raw)
            if link == exclude_link or intent['side'] != 'Buy' or status in {'blocked','released_unfilled','released_closed'}:
                continue
            qty = Decimal(intent['qty'])
            if not qty.is_finite() or qty <= 0:
                raise ValueError('invalid reserved quote amount')
            symbol = intent['symbol']
            reserved[symbol] = reserved.get(symbol, Decimal('0')) + qty
        return reserved

    def release_closed_cohort(self, expected_intents, proof):
        """Commit all lot releases atomically; no execution may settle two cohorts."""
        proof_links = set(proof.get('buy_links', [proof.get('buy_link')]))
        if (not expected_intents or proof.get('reservation_release_verified') is not True
                or not proof.get('execution_ids') or proof_links != set(expected_intents)
                or len(set(proof['execution_ids'])) != len(proof['execution_ids'])):
            raise ValueError('verified closed proof required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used = set()
            for (raw,) in db.execute("SELECT response FROM order_submissions WHERE status='released_closed'"):
                used.update(json.loads(raw)['execution_ids'])
            if used & set(proof['execution_ids']):
                raise ValueError('execution already consumed by earlier settlement')
            for link, expected_sha in expected_intents.items():
                row = db.execute('SELECT payload,sha,status FROM order_submissions WHERE link=?', (link,)).fetchone()
                if (row is None or row[1] != expected_sha or hashlib.sha256(row[0].encode()).hexdigest() != expected_sha
                        or row[2] not in {'acknowledged','observed'} or json.loads(row[0])['side'] != 'Buy'):
                    raise ValueError('cohort intent changed before release')
            for link in expected_intents:
                db.execute("UPDATE order_submissions SET status='released_closed',response=?,last_error=NULL WHERE link=?",
                    (encoded(proof), link))

    def reconcile(self, client):
        """Positive exact-ID observations only; absence in bounded history proves nothing."""
        with self.connect() as db:
            pending = db.execute("SELECT link,symbol,payload,sha,status,response FROM order_submissions WHERE status IN ('prepared','unknown','acknowledged','observed')").fetchall()
        resolved = 0
        for link, symbol, raw, sha, previous_status, prior_response in pending:
            if hashlib.sha256(raw.encode()).hexdigest() != sha:
                raise ValueError('corrupt submission intent')
            intent = json.loads(raw)
            if intent['side'] != 'Buy' and previous_status in {'acknowledged','observed'}:
                continue
            rows = [*client.get_open_orders(symbol=symbol), *client.get_order_history(symbol=symbol, limit=50)]
            matches = [row for row in rows if row.get('orderLinkId') == link]
            if not matches:
                continue
            if (any(row.get('symbol') != symbol or row.get('side') != intent['side'] or not row.get('orderId') for row in matches)
                    or len({row['orderId'] for row in matches}) != 1):
                raise ValueError('conflicting exchange observation')
            if prior_response is not None:
                previous = json.loads(prior_response)
                result = previous.get('result', {}) if isinstance(previous, dict) else {}
                known = {row['orderId'] for row in previous.get('exchange_observations', [])} if isinstance(previous, dict) else set()
                if isinstance(result, dict) and result.get('orderId'):
                    known.add(result['orderId'])
                if known and known != {row['orderId'] for row in matches}:
                    raise ValueError('exchange observation differs from acknowledged order')
            released = False
            if intent['side'] == 'Buy':
                try:
                    released = all(row.get('orderStatus') in {'Cancelled','Rejected','Deactivated'}
                        and Decimal(str(row['cumExecQty'])) == 0 and Decimal(str(row['cumExecValue'])) == 0
                        for row in matches)
                except (KeyError, ArithmeticError, ValueError):
                    released = False
            self.finish(link, 'released_unfilled' if released else 'observed', {'exchange_observations': matches})
            resolved += 1
        return resolved


class JournaledOrderClient:
    def __init__(self, client, journal):
        self.client, self.journal = client, journal

    def __getattr__(self, name):
        return getattr(self.client, name)

    def capture_decision_context(self, intent, record):
        return self.journal.capture_decision_context(intent, record)

    def create_spot_market_order(self, **intent):
        prior = self.journal.prepare(**intent)
        if prior is not None:
            return prior
        link = intent['order_link_id']
        try:
            response = self.client.create_spot_market_order(**intent)
        except OrderControlBlocked:
            self.journal.finish(link, 'blocked', error='OrderControlBlocked')
            raise
        except Exception as exc:
            self.journal.finish(link, 'unknown', error=type(exc).__name__)
            raise
        result = response.get('result') if isinstance(response, dict) else None
        if (not isinstance(result, dict) or not result.get('orderId') or response.get('retCode') != 0
                or result.get('orderLinkId', link) != link):
            self.journal.finish(link, 'unknown', response)
            raise ValueError('submission response does not establish acknowledgment')
        self.journal.finish(link, 'acknowledged', response)
        return response
