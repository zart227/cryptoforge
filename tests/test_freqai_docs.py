from pathlib import Path


def test_freqai_doc_defines_upgrade_path_and_safety_boundaries() -> None:
    text = Path("docs/FREQAI.md").read_text(encoding="utf-8")

    required = [
        "NOT ACTIVE",
        "train -> validation -> test",
        "feature_version",
        "model version",
        "SHA-256 checksum",
        "night-only",
        "Anti-Leakage Checks",
        "Champion / Challenger ML Evaluation",
        "Shadow Mode",
        "ML cannot autonomously increase live exposure",
    ]

    for phrase in required:
        assert phrase in text
