"""Validate account-wide entry inputs without inventing balances on failure."""
from decimal import Decimal

from cryptoforge.live_risk import count_open_spot_positions, dynamic_entry_capacity


def read_entry_account_snapshot(client, *, stake_amount, position_cap):
    account = client.get_unified_usdt_balance()
    for value in (account.total_equity_usd, account.usdt_wallet_balance):
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError('invalid account-wide balance')
    coins = client.get_unified_wallet_coins()
    names = set()
    if not isinstance(coins, list) or not coins:
        raise ValueError('unknown account inventory')
    for row in coins:
        name = row['coin']; value = Decimal(str(row['usdValue']))
        if (not isinstance(name, str) or not name or not name.isascii() or not name.isalnum()
                or name != name.upper() or name in names or not value.is_finite() or value < 0):
            raise ValueError('invalid account inventory')
        names.add(name)
    if 'USDT' not in names:
        raise ValueError('explicit USDT inventory required')
    positions = count_open_spot_positions(coins)
    capacity = dynamic_entry_capacity(total_equity=account.total_equity_usd,
        free_usdt=account.usdt_wallet_balance, stake_amount=stake_amount,
        open_positions=positions, hard_position_cap=position_cap)
    # Retain the exact validated rows used for sizing: discovery must not depend
    # on whether an earlier independent wallet query succeeded.
    return account, positions, *capacity, tuple(dict(row) for row in coins)
