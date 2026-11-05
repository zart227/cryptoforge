"""Local operator runtime binding; a necessary gate, not strategy admission."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path

from cryptoforge.execution_controls import OrderControlBlocked, unique_fields
from cryptoforge.execution_ownership import credential_scope


# Explicit runtime surface, not a claim to capture the full environment or account.
SOURCE_MODULES = (
    'runtime_approval', 'supabase_executor', 'bybit_private', 'execution_controls',
    'submission_risk', 'live_risk', 'entry_account_snapshot', 'execution_ownership',
    'order_submission_journal', 'decision_outbox', 'exit_data_fallback',
    'spot_reservations', 'reservation_settlement', 'portfolio_drawdown', 'fractional_risk', 'model_registry',
    'model_training', 'candle_contract', 'target_contracts', 'atomic_reports',
    'market_data', 'supabase_market', 'backend', 'research_selection', 'order_observer',
    'account_verification', 'account_ownership',
)
REQUIRED_GUARDS = (
    'exit_data_fallback', 'submission_risk_guard', 'spot_reservation_guard',
    'local_order_reservations',
)
PATH_OPTIONS = (
    'order_submission_journal', 'decision_outbox', 'execution_controls',
    'drawdown_state', 'fractional_risk_policy', 'entry_runtime_approval',
)


def require_sha(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in '0123456789abcdef' for char in value)):
        raise ValueError('explicit lowercase SHA256 required')
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('aware approval timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('aware approval timestamp required')
    return result.astimezone(UTC)


def runtime_contract(args, client, *, launcher_path, fractional_policy_sha256,
                     account_policy_sha256=None, machine_id=None):
    """Describe configured inputs without querying balances or serializing secrets."""
    values = {}
    for name in ('stake_amount', 'max_daily_loss', 'stop_loss_percent', 'max_dust_fraction',
                 'ml_threshold', 'ml_max_age_hours', 'max_portfolio_drawdown', 'timeout'):
        number = Decimal(str(getattr(args, name)))
        if not number.is_finite() or number <= 0:
            raise ValueError('finite positive runtime limits required')
        values[name] = str(number.normalize())
    for name in ('max_open_positions', 'night_research_limit'):
        value = getattr(args, name)
        if type(value) is not int or value < 1:
            raise ValueError('positive integer runtime limits required')
        values[name] = value
    for name in (*REQUIRED_GUARDS, 'settle_closed_reservations', 'live',
                 'use_night_research', 'append_fallback_pairs',
                 'allow_intraday_reversion', 'allow_emerging_momentum'):
        value = getattr(args, name)
        if type(value) is not bool:
            raise ValueError('explicit runtime flags required')
        values[name] = value
    account_guard = getattr(args,'account_ownership_guard',False)
    if type(account_guard) is not bool:
        raise ValueError('explicit account ownership flag required')
    values['account_ownership_guard'] = account_guard
    if not all(values[name] for name in REQUIRED_GUARDS) or args.ml_mode != 'gate':
        raise ValueError('runtime approval requires risk/reservation/fallback guards and ML gate')
    if not 0 < Decimal(values['stop_loss_percent']) < 1 or not 0 < Decimal(values['ml_threshold']) <= 1:
        raise ValueError('invalid runtime stop or model threshold')
    if not 0 < Decimal(values['max_portfolio_drawdown']) <= Decimal('.10'):
        raise ValueError('invalid runtime drawdown threshold')
    values['ml_mode'] = args.ml_mode
    values['entry_model_sha256'] = require_sha(args.entry_model_sha256)
    values['pairs'] = list(args.pair or ['ETH/USDT'])
    if any(not isinstance(pair, str) or not pair for pair in values['pairs']):
        raise ValueError('explicit runtime fallback pairs required')
    paths = {}
    for name in PATH_OPTIONS:
        path = getattr(args, name)
        if path is None:
            raise ValueError('runtime approval requires all persistence/control/policy paths')
        paths[name] = str(Path(path).resolve())
    paths['daily_equity_state'] = str(Path('.local/state/live-equity-risk.json').resolve())
    paths['ownership_registry'] = str(Path('.local/state/executor-ownership').resolve())
    sources = {name: sha(Path(importlib.import_module('cryptoforge.'+name).__file__).read_bytes())
        for name in SOURCE_MODULES}
    sources['launcher'] = sha(Path(launcher_path).read_bytes())
    current_policy_sha = sha(Path(args.fractional_risk_policy).read_bytes())
    if current_policy_sha != require_sha(fractional_policy_sha256):
        raise ValueError('fractional policy changed after loading')
    account_path = getattr(args, 'entry_account_policy', None)
    if account_path is not None:
        paths['entry_account_policy'] = str(Path(account_path).resolve())
        if sha(Path(account_path).read_bytes()) != require_sha(account_policy_sha256):
            raise ValueError('account policy changed after loading')
    return dict(schema_version='supabase-executor-runtime-v1',
        ownership=credential_scope(client, machine_id=machine_id), configuration=values,
        paths=paths, fractional_policy_sha256=current_policy_sha,
        account_policy_sha256=account_policy_sha256,
        implementation_sha256=sources,
        scope='configured_local_runtime_surface_not_operational_or_strategy_qualification')


def approval_blockers(path, contract, *, now=None, clock=None):
    try:
        approval = json.loads(Path(path).read_bytes(), object_pairs_hook=unique_fields)
        # The submit adapter observes time after local file IO, not before it.
        now = clock() if clock is not None else now
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None or contract is None:
            raise ValueError('runtime or clock unavailable')
        keys = {'schema_version', 'approved', 'runtime_sha256', 'valid_from', 'valid_until',
            'review_reference'}
        if (not isinstance(approval, dict) or set(approval) != keys
                or approval['schema_version'] != 'executor-runtime-approval-v1'
                or type(approval['approved']) is not bool
                or not isinstance(approval['review_reference'], str)
                or not approval['review_reference'].strip()):
            raise ValueError('invalid runtime approval')
        if not approval['approved']:
            return ('operator runtime approval denies new entries',)
        if require_sha(approval['runtime_sha256']) != sha(canonical(contract)):
            return ('runtime differs from operator approval; new entries paused',)
        begin, end = stamp(approval['valid_from']), stamp(approval['valid_until'])
        if not begin <= now < end or not timedelta(0) < end-begin <= timedelta(hours=24):
            return ('runtime approval expired, future-dated or exceeds 24 hours; new entries paused',)
        return ()
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        return ('runtime approval unavailable or invalid; new entries paused',)


class PinnedActiveModelRegistry:
    def __init__(self, registry, expected_sha256):
        self.registry, self.expected_sha256 = registry, require_sha(expected_sha256)

    def __getattr__(self, name):
        return getattr(self.registry, name)

    def latest(self, **kwargs):
        model = self.registry.latest(**kwargs)
        if model is None or model.artifact_sha256 != self.expected_sha256:
            raise ValueError('active model differs from approved artifact')
        return model


class RuntimeApprovedOrderClient:
    def __init__(self, client, *, approval_path, contract_provider, model_input_provider, clock=None):
        self.client, self.approval_path = client, approval_path
        self.contract_provider, self.model_input_provider = contract_provider, model_input_provider
        self.clock = clock or (lambda: datetime.now(UTC))
        self.started_at = self.clock()
        try:
            self.initial_contract = canonical(self.contract_provider())
        except Exception:
            self.initial_contract = None

    def __getattr__(self, name):
        return getattr(self.client, name)

    def create_spot_market_order(self, **intent):
        if intent.get('side') == 'Sell':
            return self.client.create_spot_market_order(**intent)
        if intent.get('side') != 'Buy':
            raise OrderControlBlocked('invalid order side')
        try:
            contract = self.contract_provider()
            if self.initial_contract is None or canonical(contract) != self.initial_contract:
                raise OrderControlBlocked('runtime changed during cycle; new entries paused')
            model_input = self.model_input_provider()
            if (not isinstance(model_input, dict)
                    or model_input.get('artifact_sha256') != contract['configuration']['entry_model_sha256']
                    or model_input.get('pair', '').replace('/', '') != intent.get('symbol')):
                raise OrderControlBlocked('entry has no approved model input for this symbol')
            if self.clock() < self.started_at:
                raise ValueError('approval clock moved backwards')
            blockers = approval_blockers(self.approval_path, contract, clock=self.clock)
            if blockers:
                raise OrderControlBlocked('; '.join(blockers))
        except OrderControlBlocked:
            raise
        except Exception as exc:
            raise OrderControlBlocked('runtime binding unavailable or invalid; new entries paused') from exc
        return self.client.create_spot_market_order(**intent)

    def create_spot_limit_order(self, **intent):
        if intent.get('side') == 'Sell':
            return self.client.create_spot_limit_order(**intent)
        raise OrderControlBlocked('limit entry outside approved market execution contract')
