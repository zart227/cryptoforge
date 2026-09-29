from pathlib import Path

from scripts.windows_background_runner import load_environment, target


def test_load_environment_supports_quotes_and_comments(tmp_path, monkeypatch) -> None:
    path = tmp_path / ".env"
    path.write_text("# comment\nCF_BG_ONE='one'\nCF_BG_TWO=two\n", encoding="utf-8")
    monkeypatch.delenv("CF_BG_ONE", raising=False)
    monkeypatch.delenv("CF_BG_TWO", raising=False)

    load_environment(path)

    assert __import__("os").environ["CF_BG_ONE"] == "one"
    assert __import__("os").environ["CF_BG_TWO"] == "two"


def test_background_targets_have_separate_logs() -> None:
    _, executor_log = target("executor")
    _, collector_log = target("collector")

    assert executor_log.name == "supabase-live-executor-task.log"
    assert collector_log.name == "research-collector-task.log"
