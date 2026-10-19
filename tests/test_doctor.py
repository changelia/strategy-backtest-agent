"""Isolated offline diagnostics; synthetic credentials never leave stdout/stderr."""

import logging
import os
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

from strategy_backtest_agent import doctor
from strategy_backtest_agent.cli import main
from strategy_backtest_agent.init_cli import template

REAL_INSTALLED = doctor.installed_metadata
REAL_SOURCE = doctor.source_metadata
SECRET = "SYNTHETIC_PRIVATE_MARKER_DO_NOT_PRINT"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "PYTHON_DOTENV_DISABLED"):
        monkeypatch.delenv(name, raising=False)
    # Register absent env entries so teardown also removes values loaded by dotenv.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("OPENAI_MODEL", "")
    monkeypatch.delenv("OPENAI_MODEL")
    monkeypatch.setattr(doctor, "installed_metadata", lambda: ("1.2.0", ">=3.12,<4.0"))
    monkeypatch.setattr(doctor, "source_metadata", lambda: (None, None))
    monkeypatch.setattr(
        doctor,
        "find_dotenv",
        lambda **kwargs: str(tmp_path / ".env") if (tmp_path / ".env").exists() else "",
    )

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("No network allowed")

    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)


def run(monkeypatch: pytest.MonkeyPatch, args: list[str] | None = None) -> int:
    monkeypatch.setattr(sys, "argv", ["strategy-backtest", "doctor", *(args or [])])
    try:
        main()
    except SystemExit as exc:
        assert isinstance(exc.code, int)
        return exc.code
    return 0


def test_healthy_offline_without_credentials_or_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert run(monkeypatch) == 0
    printed = capsys.readouterr()
    assert not printed.err
    assert "Dotenv: not found" in printed.out
    assert "OpenAI key: absent or empty" in printed.out
    assert "Offline checks: available" in printed.out
    assert "no research files discovered or validated" in printed.out
    assert "AI model: shared default gpt-4.1-mini" in printed.out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("shell", [None, "", "shell-" + SECRET])
def test_dotenv_loading_shell_precedence_and_redaction(
    shell: str | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / ".env"
    path.write_text(f"OPENAI_API_KEY=dotenv-{SECRET}\nOPENAI_MODEL=model-{SECRET}\n")
    original = path.read_bytes(), path.stat().st_mtime_ns
    if shell is not None:
        monkeypatch.setenv("OPENAI_API_KEY", shell)
        monkeypatch.setenv("OPENAI_MODEL", "shell-model-" + SECRET)
    assert run(monkeypatch) == 0
    assert os.environ["OPENAI_API_KEY"] == (shell if shell is not None else "dotenv-" + SECRET)
    assert os.environ["OPENAI_MODEL"] == (
        "shell-model-" + SECRET if shell is not None else "model-" + SECRET
    )
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert "override configured (value hidden)" in output.out
    assert (path.read_bytes(), path.stat().st_mtime_ns) == original


@pytest.mark.parametrize("disabled", ["1", "true", "YES", "t", "y"])
def test_disabled_dotenv_not_discovered_or_read(
    disabled: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", disabled)

    def forbidden(**kwargs: Any) -> str:
        raise AssertionError("Must not discover disabled dotenv")

    monkeypatch.setattr(doctor, "find_dotenv", forbidden)
    assert run(monkeypatch) == 0
    assert "disabled; discovery/loading skipped" in capsys.readouterr().out


@pytest.mark.parametrize("key,model", [("", ""), ("   ", "   "), (SECRET, "")])
def test_empty_optional_credentials_do_not_fail_offline(
    key: str, model: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.setenv("OPENAI_MODEL", model)
    assert run(monkeypatch) == 0
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert "AI model override is empty" in output.out
    assert "does not establish validity" in output.out


@pytest.mark.parametrize(
    "contents", [b'OPENAI_API_KEY="' + SECRET.encode(), b"\xff" + SECRET.encode()]
)
def test_malformed_dotenv_is_sanitized(
    contents: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / ".env"
    path.write_bytes(contents)
    assert run(monkeypatch) == 1
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err + caplog.text
    assert "ERROR" in output.out
    assert "Traceback" not in output.out + output.err
    assert path.read_bytes() == contents


def test_dotenv_exception_and_logging_are_not_echoed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / ".env").write_text("# only a comment")

    def fail(**kwargs: Any) -> bool:
        logging.getLogger("dotenv.main").warning(SECRET)
        raise PermissionError(SECRET)

    monkeypatch.setattr(doctor, "load_dotenv", fail)
    assert run(monkeypatch) == 1
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err + caplog.text


@pytest.mark.parametrize("kind", ["backtest", "compare", "validate", "walk-forward"])
def test_explicit_valid_configs_are_not_modified(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / (SECRET + ".json")
    path.write_text(template(kind).model_dump_json())
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert run(monkeypatch, ["--type", kind, "--config", str(path)]) == 0
    output = capsys.readouterr()
    assert f"valid {kind} model" in output.out
    assert SECRET not in output.out + output.err
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "contents", [None, SECRET, '{"entry_rsi": "' + SECRET + '"}', '{"private": "' + SECRET + '"}']
)
def test_invalid_or_missing_configs_fail_without_echo(
    contents: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / (SECRET + ".json")
    if contents is not None:
        path.write_text(contents)
    assert run(monkeypatch, ["--type", "backtest", "--config", str(path)]) == 1
    output = capsys.readouterr()
    assert "ERROR research config invalid/unreadable" in output.out
    assert SECRET not in output.out + output.err
    assert "Traceback" not in output.out + output.err


@pytest.mark.parametrize(
    "args",
    [
        ["--type", "backtest"],
        ["--config", SECRET],
        ["--type", SECRET, "--config", SECRET],
        ["--unknown=" + SECRET],
        [SECRET],
    ],
)
def test_invalid_arguments_are_redacted(
    args: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(monkeypatch, args) == 2
    output = capsys.readouterr()
    assert "Invalid doctor arguments" in output.err
    assert SECRET not in output.out + output.err


def test_stale_installed_version_is_distinct_from_source(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(doctor, "installed_metadata", lambda: ("0.7.0", ">=3.12,<4.0"))
    monkeypatch.setattr(doctor, "source_metadata", lambda: ("1.2.0", ">=3.12,<4.0"))
    assert run(monkeypatch) == 0
    output = capsys.readouterr().out
    assert "Installed package version: 0.7.0" in output
    assert "Source checkout version: 1.2.0" in output
    assert "stale/editable metadata" in output


def test_missing_metadata_does_not_prevent_checked_offline_capabilities(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(doctor, "installed_metadata", lambda: (None, None))
    assert run(monkeypatch) == 0
    output = capsys.readouterr().out
    assert "installed metadata unavailable" in output
    assert "Installed package version: unavailable" in output


@pytest.mark.parametrize("version", [(3, 11, 9), (4, 0, 0)])
def test_incompatible_python_fails(
    version: tuple[int, int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Version(tuple[int, int, int]):
        major, minor, micro = version

    monkeypatch.setattr(sys, "version_info", Version(version))
    assert run(monkeypatch) == 1


def test_unrecognized_requirement_is_not_claimed_compatible(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(doctor, "installed_metadata", lambda: ("1.2.0", SECRET))
    assert run(monkeypatch) == 1
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert "compatibility unverified" in output.out


def test_parent_dotenv_discovery_and_single_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from dotenv import find_dotenv, load_dotenv

    (tmp_path / ".env").write_text("OPENAI_API_KEY=" + SECRET)
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.setattr(doctor, "find_dotenv", find_dotenv)
    calls: list[tuple[str, bool]] = []

    def load(*, dotenv_path: str, override: bool) -> bool:
        calls.append((dotenv_path, override))
        return load_dotenv(dotenv_path=dotenv_path, override=override)

    monkeypatch.setattr(doctor, "load_dotenv", load)
    assert run(monkeypatch) == 0
    assert calls == [(str(tmp_path / ".env"), False)]
    assert SECRET not in capsys.readouterr().out


def test_empty_dotenv_and_empty_dotenv_key_are_not_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env").write_text("# empty\n")
    assert run(monkeypatch) == 0
    assert "found; no assignments applied" in capsys.readouterr().out
    (tmp_path / ".env").write_text('OPENAI_API_KEY=""\n')
    assert run(monkeypatch) == 0
    assert "absent or empty; source: dotenv" in capsys.readouterr().out


def test_metadata_lookup_missing_and_broken_errors_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.metadata

    def missing(*args: Any) -> Any:
        raise importlib.metadata.PackageNotFoundError(SECRET)

    monkeypatch.setattr(importlib.metadata, "metadata", missing)
    assert REAL_INSTALLED() == (None, None)

    def broken(*args: Any) -> Any:
        raise ValueError(SECRET)

    monkeypatch.setattr(importlib.metadata, "metadata", broken)
    assert REAL_INSTALLED() == (None, None)


def test_source_metadata_uses_module_checkout_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "source"
    module = checkout / "src/strategy_backtest_agent/doctor.py"
    module.parent.mkdir(parents=True)
    module.touch()
    (checkout / "pyproject.toml").write_text(
        '[project]\nname="strategy-backtest-agent"\nversion="1.2.0"\nrequires-python=">=3.12,<4.0"'
    )
    (tmp_path / "pyproject.toml").write_text(SECRET)
    monkeypatch.setattr(doctor, "__file__", str(module))
    assert REAL_SOURCE() == ("1.2.0", ">=3.12,<4.0")
    monkeypatch.setattr(
        doctor, "__file__", str(tmp_path / "env/site-packages/strategy_backtest_agent/doctor.py")
    )
    assert REAL_SOURCE() == (None, None)


def test_project_python_contract_is_the_declared_requirement() -> None:
    import tomllib

    path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert (
        tomllib.loads(path.read_text())["project"]["requires-python"] == doctor.PYTHON_REQUIREMENT
    )


def test_arbitrary_metadata_text_is_not_displayed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(doctor, "installed_metadata", lambda: (SECRET, doctor.PYTHON_REQUIREMENT))
    monkeypatch.setattr(doctor, "source_metadata", lambda: (SECRET, doctor.PYTHON_REQUIREMENT))
    assert run(monkeypatch) == 0
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err


def test_failed_offline_check_is_sanitized_and_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: Any) -> Any:
        raise ValueError(SECRET)

    monkeypatch.setattr(doctor, "demo_candles", fail)
    assert run(monkeypatch) == 1
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert "offline self-check failed" in output.out


def test_no_explicit_config_does_not_read_research_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "walk-forward.json"
    path.write_text(SECRET)

    def forbidden(*args: Any) -> bool:
        raise AssertionError("No implicit config reads")

    monkeypatch.setattr(doctor, "config_valid", forbidden)
    assert run(monkeypatch) == 0
    assert path.read_text() == SECRET
    assert SECRET not in capsys.readouterr().out
