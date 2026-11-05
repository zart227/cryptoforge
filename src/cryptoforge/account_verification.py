"""Fresh authenticated key facts for an explicit, narrow Spot subaccount policy."""
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import ipaddress
import json

from cryptoforge.execution_controls import OrderControlBlocked, unique_fields


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def uid(value):
    if (not isinstance(value, str) or not value.isascii() or not value.isdigit()
            or value.startswith('0')):
        raise ValueError('explicit canonical positive UID required')
    return value


def ips(values):
    if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
        raise ValueError('explicit IP whitelist required')
    result = tuple(sorted(str(ipaddress.ip_address(value)) for value in values))
    if len(set(result)) != len(result):
        raise ValueError('duplicate IP whitelist entry')
    return result


@dataclass(frozen=True)
class SpotAccountPolicy:
    expected_uid: str
    expected_parent_uid: str
    expected_ips: tuple[str, ...]
    maximum_response_age_seconds: int

    def __post_init__(self):
        if uid(self.expected_uid) == uid(self.expected_parent_uid):
            raise ValueError('distinct reviewed subaccount and parent UID required')
        if (type(self.expected_ips) is not tuple or ips(list(self.expected_ips)) != self.expected_ips
                or type(self.maximum_response_age_seconds) is not int
                or not 0 < self.maximum_response_age_seconds <= 30):
            raise ValueError('explicit canonical whitelist and bounded freshness required')


def load_account_policy(path):
    raw = path.read_bytes()
    source = json.loads(raw, object_pairs_hook=unique_fields)
    keys = {'schema_version', 'expected_uid', 'expected_parent_uid', 'expected_ips',
        'maximum_response_age_seconds'}
    if (not isinstance(source, dict) or set(source) != keys
            or source['schema_version'] != 'bybit-spot-account-policy-v1'):
        raise ValueError('explicit bybit-spot-account-policy-v1 required')
    policy = SpotAccountPolicy(source['expected_uid'], source['expected_parent_uid'],
        ips(source['expected_ips']), source['maximum_response_age_seconds'])
    return policy, digest(raw)


def verify_account_response(response, *, policy, client, now):
    if (not isinstance(policy, SpotAccountPolicy) or not isinstance(now, datetime)
            or now.tzinfo is None or now.utcoffset() is None):
        raise ValueError('reviewed account policy and aware clock required')
    if (not isinstance(response, dict) or type(response.get('retCode')) is not int
            or response['retCode'] != 0 or type(response.get('time')) is not int
            or response['time'] <= 0):
        raise ValueError('successful original key response with server time required')
    server_time = datetime.fromtimestamp(response['time']/1000, UTC)
    age = (now.astimezone(UTC)-server_time).total_seconds()
    if not 0 <= age <= policy.maximum_response_age_seconds:
        raise ValueError('key response stale or future-dated')
    row = response['result']
    if (not isinstance(row, dict) or not isinstance(row.get('apiKey'), str)
            or not hmac.compare_digest(row['apiKey'], client.api_key)
            or row.get('secret') != ''):
        raise ValueError('key response identity unavailable or differs')
    if (type(row.get('userID')) is not int or row['userID'] <= 0
            or str(row['userID']) != policy.expected_uid
            or row.get('parentUid') != policy.expected_parent_uid
            or row.get('isMaster') is not False):
        raise ValueError('account UID or subaccount relationship differs')
    if row.get('userIDInt64', '0') not in ('0', policy.expected_uid):
        raise ValueError('conflicting UID representations')
    if (type(row.get('readOnly')) is not int or row['readOnly'] != 0
            or type(row.get('uta')) is not int or row['uta'] != 1
            or type(row.get('type')) is not int or row['type'] != 1
            or row.get('isFixApi') is not False):
        raise ValueError('personal non-FIX read/write unified key required')
    permissions = row['permissions']
    required = {'Spot', 'Wallet', 'ContractTrade', 'Derivatives', 'Options'}
    if not isinstance(permissions, dict) or not required <= set(permissions):
        raise ValueError('explicit complete core permissions required')
    for name, values in permissions.items():
        expected = ['SpotTrade'] if name == 'Spot' else []
        if (not isinstance(name, str) or not isinstance(values, list)
                or any(not isinstance(value, str) for value in values)
                or len(set(values)) != len(values)
                or values != expected):
            raise ValueError('unqualified or unknown non-Spot permission')
    if ips(row['ips']) != policy.expected_ips:
        raise ValueError('IP whitelist differs from reviewed policy')
    # Return a projection only. Never persist apiKey, note, secret or raw response.
    return dict(schema_version='bybit-spot-account-observation-v1',
        source='GET /v5/user/query-api', observed_at=now.astimezone(UTC).isoformat(),
        server_time=server_time.isoformat(), credential_sha256=digest(client.api_key.encode()),
        uid_sha256=digest(policy.expected_uid.encode()),
        parent_uid_sha256=digest(policy.expected_parent_uid.encode()),
        permissions_sha256=digest(json.dumps(permissions, sort_keys=True).encode()),
        ip_whitelist_sha256=digest(json.dumps(policy.expected_ips).encode()),
        account_uid_matches_policy=True, personal_unified_subaccount=True,
        spot_trade_only=True, wallet_permissions_empty=True, ip_whitelist_matches_policy=True,
        ownership_lease_upgraded=False, live_admission_granted=False)


def observe_account(client, policy, *, clock=None):
    clock = clock or (lambda: datetime.now(UTC))
    response = client._private_get('/v5/user/query-api', {})
    return verify_account_response(response, policy=policy, client=client, now=clock())


class AccountVerifiedOrderClient:
    def __init__(self, client, *, policy, policy_path, policy_sha256, clock=None):
        self.client, self.policy = client, policy
        self.policy_path, self.policy_sha256 = policy_path, policy_sha256
        self.clock = clock

    def __getattr__(self, name):
        return getattr(self.client, name)

    def create_spot_market_order(self, **intent):
        if intent.get('side') == 'Sell':
            return self.client.create_spot_market_order(**intent)
        if intent.get('side') != 'Buy':
            raise OrderControlBlocked('invalid order side')
        try:
            if digest(self.policy_path.read_bytes()) != self.policy_sha256:
                raise ValueError('account policy changed after loading')
            observe_account(self.client, self.policy, clock=self.clock)
        except Exception as exc:
            raise OrderControlBlocked('account identity or key permissions unavailable or unqualified') from exc
        return self.client.create_spot_market_order(**intent)

    def create_spot_limit_order(self, **intent):
        if intent.get('side') == 'Sell':
            return self.client.create_spot_limit_order(**intent)
        raise OrderControlBlocked('limit entry outside verified market account contract')
