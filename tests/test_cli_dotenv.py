"""CLI startup dotenv loading with isolated files and no network requests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from strategy_backtest_agent import cli


@pytest.fixture
def env_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return tmp_path


def write_env(directory: Path) -> Path:
    path = directory / ".env"
    path.write_text("OPENAI_API_KEY=dotenv-placeholder\nOPENAI_MODEL=dotenv-model\n")
    return path


def install_dispatch(monkeypatch: pytest.MonkeyPatch, command: str, callback: object) -> None:
    targets = {
        "ai": "strategy_backtest_agent.cli._ai_main",
        "compare": "strategy_backtest_agent.comparison.cli.main",
        "validate": "strategy_backtest_agent.validation.cli.main",
        "sensitivity": "strategy_backtest_agent.sensitivity.cli.main",
        "costs": "strategy_backtest_agent.costs.cli.main",
        "walk-forward": "strategy_backtest_agent.walk_forward.cli.main",
        "report": "strategy_backtest_agent.reports.cli.main",
    }
    monkeypatch.setattr(targets[command], callback)
    monkeypatch.setattr("sys.argv", ["strategy-backtest", command])


@pytest.mark.parametrize(
    "command", ["ai", "compare", "validate", "sensitivity", "costs", "walk-forward", "report"]
)
def test_dotenv_loaded_once_before_each_command(
    command: str, env_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_env(env_directory)
    original_load = load_dotenv
    calls = []

    def load(*, dotenv_path: str, override: bool) -> bool:
        calls.append((dotenv_path, override))
        return original_load(dotenv_path=dotenv_path, override=override)

    def dispatched(*args: object) -> None:
        assert os.environ["OPENAI_API_KEY"] == "dotenv-placeholder"
        assert os.environ["OPENAI_MODEL"] == "dotenv-model"
        assert calls == [(str(path), False)]

    monkeypatch.setattr(cli, "load_dotenv", load)
    install_dispatch(monkeypatch, command, dispatched)
    cli.main()
    assert calls == [(str(path), False)]


@pytest.mark.parametrize(
    "key,model",
    [
        ("shell-placeholder", "shell-model"),
        ("shell-placeholder", None),
        (None, "shell-model"),
        ("", ""),
    ],
)
def test_shell_variables_override_dotenv_independently(
    key: str | None,
    model: str | None,
    env_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_env(env_directory)
    if key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", key)
    if model is not None:
        monkeypatch.setenv("OPENAI_MODEL", model)

    def dispatched() -> None:
        assert os.environ["OPENAI_API_KEY"] == (key if key is not None else "dotenv-placeholder")
        assert os.environ["OPENAI_MODEL"] == (model if model is not None else "dotenv-model")

    install_dispatch(monkeypatch, "ai", dispatched)
    cli.main()


def test_parent_directory_dotenv_discovery(
    env_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_env(env_directory)
    child = env_directory / "nested"
    child.mkdir()
    monkeypatch.chdir(child)

    def dispatched() -> None:
        assert os.environ["OPENAI_API_KEY"] == "dotenv-placeholder"

    install_dispatch(monkeypatch, "ai", dispatched)
    cli.main()


def test_without_dotenv_missing_key_still_reports_original_error(
    env_directory: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not (env_directory / ".env").exists()
    # Guarantee no unrelated ancestor .env can affect the missing-file case.
    monkeypatch.setattr(cli, "find_dotenv", lambda *, usecwd: "")
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "ai", "Backtest BTCUSDT"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "OPENAI_API_KEY is missing" in captured.err
    assert "OPENAI_API_KEY" not in os.environ and "OPENAI_MODEL" not in os.environ


def test_without_dotenv_shell_configuration_still_works(
    env_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not (env_directory / ".env").exists()
    monkeypatch.setattr(cli, "find_dotenv", lambda *, usecwd: "")
    monkeypatch.setenv("OPENAI_API_KEY", "shell-placeholder")
    monkeypatch.setenv("OPENAI_MODEL", "shell-model")

    def dispatched() -> None:
        assert os.environ["OPENAI_API_KEY"] == "shell-placeholder"
        assert os.environ["OPENAI_MODEL"] == "shell-model"

    install_dispatch(monkeypatch, "ai", dispatched)
    cli.main()
