from pathlib import Path


def test_final_audit_records_real_resource_measurements() -> None:
    text = Path("FINAL_AUDIT.md").read_text(encoding="utf-8")

    required = [
        "Executive Summary",
        "Working",
        "Partially Working",
        "Not Implemented",
        "303704 KiB",
        "158.089s",
        "26396 KiB",
        "swap after run: `0 MiB`",
        "`868M`",
        "Heavy FreqAI is **NOT ACTIVE**",
        "Real trading is still disabled",
        "Futures are still disabled",
        "Leverage is still disabled",
        "must not enable real trading",
    ]

    for phrase in required:
        assert phrase in text
