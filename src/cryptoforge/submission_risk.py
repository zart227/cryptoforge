"""Recheck the launcher's existing absolute limits before a market Buy."""
from datetime import UTC, datetime
from decimal import Decimal

from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.live_risk import count_open_spot_positions, daily_equity_blockers, dynamic_entry_capacity


def finite_nonnegative(value):
    return isinstance(value, Decimal) and value.is_finite() and value >= 0


class SubmissionRiskClient:
    def __init__(self, client, *, maximum_stake, position_cap, maximum_daily_loss, state_path, clock=None,
                 reservation_guard=False, submission_journal=None, drawdown_policy=None, fractional_policy=None):
        if (not finite_nonnegative(maximum_stake) or maximum_stake <= 0
                or type(position_cap) is not int or position_cap < 1
                or not finite_nonnegative(maximum_daily_loss) or maximum_daily_loss <= 0):
            raise ValueError('explicit finite submission risk limits required')
        self.client = client
        self.maximum_stake, self.position_cap = maximum_stake, position_cap
        self.maximum_daily_loss, self.state_path = maximum_daily_loss, state_path
        self.clock = clock or (lambda: datetime.now(UTC))
        self.reservation_guard = reservation_guard
        self.submission_journal = submission_journal
        self.drawdown_policy = drawdown_policy
        self.fractional_policy = fractional_policy

    def __getattr__(self, name):
        return getattr(self.client, name)

    def create_spot_market_order(self, **intent):
        side = intent.get('side')
        if side not in {'Buy', 'Sell'}:
            raise OrderControlBlocked('invalid market order side')
        if side == 'Sell':
            return self.client.create_spot_market_order(**intent)
        qty = intent.get('qty')
        # BybitPrivateClient sends market Buy quantity in quoteCoin units.
        if not finite_nonnegative(qty) or qty <= 0 or qty > self.maximum_stake:
            raise OrderControlBlocked('market buy quote amount exceeds stake or is invalid')
        try:
            account = self.client.get_unified_usdt_balance()
            if (not finite_nonnegative(account.total_equity_usd)
                    or not finite_nonnegative(account.usdt_wallet_balance)):
                raise ValueError('invalid balance')
            if self.drawdown_policy is not None:
                from cryptoforge.portfolio_drawdown import drawdown_blockers
                blockers = drawdown_blockers(current_equity=account.total_equity_usd,
                    now=self.clock(), **self.drawdown_policy)
                if blockers: raise OrderControlBlocked('; '.join(blockers))
            coins = self.client.get_unified_wallet_coins()
            names = [row['coin'] for row in coins]
            if not coins or 'USDT' not in names or len(set(names)) != len(names):
                raise ValueError('incomplete or duplicate inventory')
            if any(not row['coin'] or not finite_nonnegative(Decimal(str(row['usdValue']))) for row in coins):
                raise ValueError('invalid inventory values')
            if self.fractional_policy is not None:
                from cryptoforge.fractional_risk import fractional_risk_blockers
                symbol = intent['symbol']
                if not symbol.endswith('USDT'):
                    raise OrderControlBlocked('fractional risk requires explicit USDT Spot symbol')
                exposure = sum((Decimal(str(row['usdValue'])) for row in coins if row['coin']==symbol[:-4]), Decimal('0'))
                blockers = fractional_risk_blockers(self.fractional_policy, equity=account.total_equity_usd,
                    quote_notional=qty, existing_symbol_value=exposure)
                if blockers: raise OrderControlBlocked('; '.join(blockers))
            positions = count_open_spot_positions(coins)
            held = {row['coin']+'USDT' for row in coins if row['coin'] != 'USDT'
                and Decimal(str(row['usdValue'])) >= 1}
            pending = set()
            available = account.usdt_wallet_balance
            if self.reservation_guard:
                from cryptoforge.spot_reservations import spot_reservations
                free_cash, pending = spot_reservations(self.client, coins)
                positions = len(held | pending)
                available = min(available, free_cash)
                if intent['symbol'] in pending:
                    raise OrderControlBlocked('pending buy already reserves this symbol')
            if self.submission_journal is not None:
                local = self.submission_journal.buy_reservations(exclude_link=intent.get('order_link_id'))
                positions = len(held | pending | set(local))
                available -= sum(local.values(), Decimal('0'))
                if intent['symbol'] in local:
                    raise OrderControlBlocked('local buy reservation already occupies this symbol')
            _, capacity, slots = dynamic_entry_capacity(total_equity=account.total_equity_usd,
                free_usdt=available, stake_amount=self.maximum_stake,
                open_positions=positions, hard_position_cap=self.position_cap)
            blockers = daily_equity_blockers(current_equity=account.total_equity_usd,
                maximum_loss=self.maximum_daily_loss, state_path=self.state_path, now=self.clock())
            if blockers:
                raise OrderControlBlocked('; '.join(blockers))
            if positions >= capacity or slots <= 0 or available < qty:
                raise OrderControlBlocked('submission-time wallet/position capacity exhausted')
        except OrderControlBlocked:
            raise
        except Exception as exc:
            raise OrderControlBlocked('submission-time risk data unavailable or invalid') from exc
        return self.client.create_spot_market_order(**intent)

    def create_spot_limit_order(self, **intent):
        raise OrderControlBlocked('limit orders are outside market submission risk contract')
