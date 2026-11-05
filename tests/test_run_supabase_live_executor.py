from decimal import Decimal

from scripts.run_supabase_live_executor import include_held_pairs


class FakeBybit:
    def __init__(self, balances: dict[str, Decimal]) -> None:
        self.balances = balances

    def get_unified_coin_wallet_balance(self, coin: str) -> Decimal:
        return self.balances.get(coin, Decimal("0"))

    def get_unified_wallet_coins(self):
        return [
            {"coin": coin, "usdValue": "5"}
            for coin, balance in self.balances.items()
            if balance > 0
        ]


def test_include_held_pairs_adds_existing_positions() -> None:
    pairs = include_held_pairs(
        FakeBybit({"ETH": Decimal("0.003")}),  # type: ignore[arg-type]
        pairs=["NEAR/USDT"],
        candidates=["ETH/USDT", "NEAR/USDT"],
    )

    assert pairs == ["NEAR/USDT", "ETH/USDT"]


def test_include_held_pairs_adds_positions_outside_fallback_universe() -> None:
    pairs = include_held_pairs(
        FakeBybit({"CELO": Decimal("54.945")}),  # type: ignore[arg-type]
        pairs=["MOVR/USDT"],
        candidates=["ETH/USDT"],
    )

    assert pairs == ["MOVR/USDT", "CELO/USDT"]


def test_append_fallback_ordering_pattern() -> None:
    ordered = list(dict.fromkeys([*"ab", *"bcd"]))

    assert ordered == ["a", "b", "c", "d"]


def test_bad_valuation_keeps_known_coin_for_explicit_exit_check():
    client = FakeBybit({'HYPE': Decimal('1')})
    client.get_unified_wallet_coins = lambda: [dict(coin='HYPE', usdValue='NaN')]
    assert include_held_pairs(client, pairs=['ETH/USDT'], candidates=[]) == ['ETH/USDT','HYPE/USDT']


def test_unknown_candidate_balance_does_not_abort_other_position_checks():
    client = FakeBybit({'HYPE': Decimal('1'), 'ETH': Decimal('NaN')})
    client.get_unified_wallet_coins = lambda: []
    assert include_held_pairs(client, pairs=['ETH/USDT'], candidates=['ETH/USDT','HYPE/USDT']) == ['ETH/USDT','HYPE/USDT']
