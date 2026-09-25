from pathlib import Path


def test_final_audit_records_real_resource_measurements() -> None:
    text = Path("FINAL_AUDIT.md").read_text(encoding="utf-8")

    required = [
        "303704 KiB",
        "158.089s",
        "26396 KiB",
        "swap after run: `0 MiB`",
        "`868M`",
        "Upgrade Triggers",
        "FreqAI training is needed",
    ]

    for phrase in required:
        assert phrase in text
