from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable
from urllib import parse, request


HttpGet = Callable[[str, dict[str, str], float], dict[str, Any]]


@dataclass(frozen=True)
class BybitApiKeyAudit:
    read_write: bool
    uta_enabled: bool
    is_master_key: bool
    parent_uid_present: bool
    ip_whitelist_count: int
    spot_permissions: tuple[str, ...]
    wallet_permissions: tuple[str, ...]
    contract_permissions: tuple[str, ...]
    derivatives_permissions: tuple[str, ...]

    @property
    def withdrawals_absent(self) -> bool:
        return "Withdraw" not in self.wallet_permissions

    @property
    def subaccount_like(self) -> bool:
        return not self.is_master_key and self.parent_uid_present


@dataclass(frozen=True)
class BybitUnifiedBalance:
    total_equity_usd: Decimal
    total_wallet_balance_usd: Decimal
    usdt_wallet_balance: Decimal


class BybitPrivateClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.bybit.com",
        recv_window: str = "5000",
        timeout_seconds: float = 10.0,
        http_get: HttpGet | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not api_secret:
            raise ValueError("api_secret is required")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.timeout_seconds = timeout_seconds
        self.http_get = http_get or get_json
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    @classmethod
    def from_env(cls) -> "BybitPrivateClient":
        return cls(
            api_key=os.environ.get("BYBIT_API_KEY", ""),
            api_secret=os.environ.get("BYBIT_API_SECRET", ""),
        )

    def get_api_key_audit(self) -> BybitApiKeyAudit:
        payload = self._private_get("/v5/user/query-api", {})
        result = payload["result"]
        permissions = result.get("permissions", {})
        parent_uid = str(result.get("parentUid", "0"))
        return BybitApiKeyAudit(
            read_write=int(result.get("readOnly", 1)) == 0,
            uta_enabled=int(result.get("uta", 0)) == 1,
            is_master_key=bool(result.get("isMaster", False)),
            parent_uid_present=parent_uid not in {"", "0"},
            ip_whitelist_count=len(result.get("ips") or []),
            spot_permissions=tuple(permissions.get("Spot") or []),
            wallet_permissions=tuple(permissions.get("Wallet") or []),
            contract_permissions=tuple(permissions.get("ContractTrade") or []),
            derivatives_permissions=tuple(permissions.get("Derivatives") or []),
        )

    def get_unified_usdt_balance(self) -> BybitUnifiedBalance:
        payload = self._private_get(
            "/v5/account/wallet-balance",
            {"accountType": "UNIFIED", "coin": "USDT"},
        )
        account = payload["result"]["list"][0]
        coins = account.get("coin") or []
        usdt = next((coin for coin in coins if coin.get("coin") == "USDT"), {})
        return BybitUnifiedBalance(
            total_equity_usd=Decimal(str(account.get("totalEquity", "0") or "0")),
            total_wallet_balance_usd=Decimal(str(account.get("totalWalletBalance", "0") or "0")),
            usdt_wallet_balance=Decimal(str(usdt.get("walletBalance", "0") or "0")),
        )

    def _private_get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        query = parse.urlencode(params)
        timestamp = str(self.clock_ms())
        signature = sign_get(
            api_secret=self.api_secret,
            timestamp=timestamp,
            api_key=self.api_key,
            recv_window=self.recv_window,
            query=query,
        )
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        payload = self.http_get(url, headers, self.timeout_seconds)
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit private API error {payload.get('retCode')}: {payload.get('retMsg')}")
        return payload


def sign_get(*, api_secret: str, timestamp: str, api_key: str, recv_window: str, query: str) -> str:
    raw = f"{timestamp}{api_key}{recv_window}{query}"
    return hmac.new(api_secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def get_json(url: str, headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read())


def readiness_from_audit(audit: BybitApiKeyAudit, balance: BybitUnifiedBalance, required_usdt: Decimal) -> dict[str, Any]:
    return {
        "read_write": audit.read_write,
        "uta_enabled": audit.uta_enabled,
        "subaccount_like": audit.subaccount_like,
        "withdrawals_absent": audit.withdrawals_absent,
        "ip_whitelist_count": audit.ip_whitelist_count,
        "spot_trade_enabled": "SpotTrade" in audit.spot_permissions,
        "contract_permissions_empty": len(audit.contract_permissions) == 0,
        "derivatives_permissions_empty": len(audit.derivatives_permissions) == 0,
        "usdt_wallet_balance": str(balance.usdt_wallet_balance),
        "required_usdt": str(required_usdt),
        "has_required_usdt": balance.usdt_wallet_balance >= required_usdt,
    }
