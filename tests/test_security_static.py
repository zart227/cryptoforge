import json
from pathlib import Path
import subprocess


SECRET_PATTERNS = (
    "BYBIT_API_" + "SECRET=",
    "BYBIT_API_" + "KEY=",
    "SUPABASE_SERVICE_ROLE_" + "KEY=",
    "SUPABASE_ANON_" + "KEY=",
    "TELEGRAM_BOT_" + "TOKEN=",
    "TELEGRAM_CHAT_" + "ID=",
    "sb_" + "secret_",
)


def test_committed_configs_remain_dry_run_spot_without_credentials() -> None:
    for path in (
        Path("config/freqtrade.dry-run.json"),
        Path("config/freqtrade.baseline-dry-run.json"),
    ):
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["dry_run"] is True
        assert config["trading_mode"] == "spot"
        assert config["margin_mode"] == ""
        assert config["exchange"]["name"] == "bybit"
        assert config["exchange"]["key"] == ""
        assert config["exchange"]["secret"] == ""
        assert config["telegram"]["enabled"] is False
        assert config["telegram"]["token"] == ""
        assert config["telegram"]["chat_id"] == ""
        assert "leverage" not in json.dumps(config).lower()


def test_env_and_private_key_files_are_not_tracked() -> None:
    tracked = Path(".git").exists()
    assert tracked
    tracked_files = Path(".gitignore").read_text(encoding="utf-8")
    assert ".env" in tracked_files
    assert "*.pem" in tracked_files
    assert "*.key" in tracked_files


def test_no_obvious_secret_assignments_in_tracked_text_files() -> None:
    allowed = {
        ".env.example",
        "README.md",
        "docs/TELEGRAM_NOTIFICATIONS.md",
        "docs/TYPESAFE_DOCUMENT_EVAL.md",
        "tests/test_security_static.py",
    }
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    for tracked_path in tracked:
        path = Path(tracked_path)
        if not path.is_file():
            continue
        if path.suffix in {".pyc", ".gz", ".sqlite", ".feather"}:
            continue
        if path.as_posix() in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            assert pattern not in text, f"{pattern} found in {path}"
