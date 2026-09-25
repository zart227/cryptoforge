from pathlib import Path


def test_bybit_private_audit_documents_ip_blocker() -> None:
    text = Path("docs/BYBIT_PRIVATE_AUDIT.md").read_text(encoding="utf-8")

    required = [
        "/v5/user/query-api",
        "/v5/account/wallet-balance",
        "10010: Unmatched IP",
        "whitelist the VPS public IP",
        "Real trading remains blocked",
    ]

    for phrase in required:
        assert phrase in text
