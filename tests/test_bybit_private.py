from decimal import Decimal

from cryptoforge.bybit_private import (
    BybitPrivateClient,
    readiness_from_audit,
    sign_get,
)


def test_sign_get_is_deterministic() -> None:
    signature = sign_get(
        api_secret="secret",
        timestamp="1000",
        api_key="key",
        recv_window="5000",
        query="accountType=UNIFIED&coin=USDT",
    )

    assert signature == sign_get(
        api_secret="secret",
        timestamp="1000",
        api_key="key",
        recv_window="5000",
        query="accountType=UNIFIED&coin=USDT",
    )
    assert len(signature) == 64


def test_private_client_parses_key_audit_and_balance() -> None:
    calls: list[str] = []

    def fake_get(url, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append(url)
        assert headers["X-BAPI-API-KEY"] == "key"
        assert headers["X-BAPI-SIGN"]
        if "query-api" in url:
            return {
                "retCode": 0,
                "result": {
                    "readOnly": 0,
                    "uta": 1,
                    "isMaster": False,
                    "parentUid": "123",
                    "ips": ["203.0.113.1"],
                    "permissions": {
                        "Spot": ["SpotTrade"],
                        "Wallet": [],
                        "ContractTrade": [],
                        "Derivatives": [],
                    },
                },
            }
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "totalEquity": "16",
                        "totalWalletBalance": "16",
                        "coin": [{"coin": "USDT", "walletBalance": "16"}],
                    }
                ]
            },
        }

    client = BybitPrivateClient(
        api_key="key",
        api_secret="secret",
        http_get=fake_get,
        clock_ms=lambda: 1000,
    )

    audit = client.get_api_key_audit()
    balance = client.get_unified_usdt_balance()
    readiness = readiness_from_audit(audit, balance, Decimal("16"))

    assert len(calls) == 2
    assert audit.read_write
    assert audit.uta_enabled
    assert audit.subaccount_like
    assert audit.withdrawals_absent
    assert audit.ip_whitelist_count == 1
    assert balance.usdt_wallet_balance == Decimal("16")
    assert readiness["spot_trade_enabled"]
    assert readiness["has_required_usdt"]


def test_readiness_flags_missing_balance_and_withdrawal_permission() -> None:
    def fake_get(url, headers, timeout):  # type: ignore[no-untyped-def]
        if "query-api" in url:
            return {
                "retCode": 0,
                "result": {
                    "readOnly": 0,
                    "uta": 1,
                    "isMaster": True,
                    "parentUid": "0",
                    "ips": [],
                    "permissions": {
                        "Spot": ["SpotTrade"],
                        "Wallet": ["Withdraw"],
                        "ContractTrade": [],
                        "Derivatives": [],
                    },
                },
            }
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "totalEquity": "5",
                        "totalWalletBalance": "5",
                        "coin": [{"coin": "USDT", "walletBalance": "5"}],
                    }
                ]
            },
        }

    client = BybitPrivateClient(api_key="key", api_secret="secret", http_get=fake_get)
    readiness = readiness_from_audit(
        client.get_api_key_audit(),
        client.get_unified_usdt_balance(),
        Decimal("16"),
    )

    assert not readiness["subaccount_like"]
    assert not readiness["withdrawals_absent"]
    assert readiness["ip_whitelist_count"] == 0
    assert not readiness["has_required_usdt"]
