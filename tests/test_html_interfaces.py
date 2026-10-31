"""HTML format integration preserves source bytes, existing reports and safe output."""

import asyncio
import json
import socket
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from test_report_html import DOM, assert_safe

from strategy_backtest_agent import AIStrategyConfig, BacktestClient, BacktestClientError
from strategy_backtest_agent.reports.cli import main
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.inputs import digest
from strategy_backtest_agent.reports.models import ResearchReport

KINDS = ("backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward")
FIXTURES = Path(__file__).parent / "fixtures/reports"


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("HTML integration must not access the network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "sendto", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr("strategy_backtest_agent.client.interpret", denied)
    monkeypatch.setattr("strategy_backtest_agent.reports.ai.interpret", denied)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.mark.parametrize("kind", KINDS)
def test_mapping_saved_file_async_cli_and_typed_report(
    kind: str,
    native_results: dict[str, dict[str, Any]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = BacktestClient()
    raw = native_results[kind]
    source = tmp_path / "source.json"
    source.write_bytes((json.dumps(raw, allow_nan=False) + "\n").encode())
    report = build_report(source.read_bytes())
    expected = client.report(raw, format="html")
    assert expected == client.report(source, format="html")
    assert expected == asyncio.run(client.areport(source, format="html"))
    assert expected == client.report(report, format="html")
    normalized = ResearchReport.model_validate_json(report.model_dump_json())
    assert expected == client.report(normalized, format="html")
    assert_safe(DOM(expected))
    main(["--input", str(source), "--format", "html"])
    assert capsys.readouterr() == (expected, "")
    destination = tmp_path / "cli.html"
    main(["--input", str(source), "--format", "html", "--output", str(destination)])
    assert capsys.readouterr() == ("", "")
    assert destination.read_text() == expected
    with pytest.raises(SystemExit) as error:
        main(["--input", str(source), "--format", "html", "--output", str(destination)])
    assert error.value.code == 2 and destination.read_text() == expected
    capsys.readouterr()
    api_output = tmp_path / "api.html"
    assert client.report(report, format="html", output=api_output) == expected
    assert api_output.read_text() == expected
    assert report.evidence.source.input_content_sha256 == digest(source.read_bytes())


def test_direct_ai_source_and_save_are_offline_equivalent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    config = AIStrategyConfig.model_validate_json(
        (root / "examples/customer-ai-strategy.json").read_bytes()
    )
    parser = Mock(return_value=config)
    monkeypatch.setattr("strategy_backtest_agent.ai.parser.parse_strategy", parser)
    client = BacktestClient(api_key="")
    prompt = "PRIVATE_ORIGINAL_AI_PROMPT_NOT_FOR_HTML"
    result = client.run(prompt, demo=True)
    awaited = asyncio.run(client.arun(prompt, demo=True))
    assert result.to_json() == awaited.to_json()
    source = tmp_path / "source.json"
    source.write_text(result.to_json(), encoding="utf-8")
    before_json = client.report(result, format="json")
    before_markdown = client.report(result)
    rendered = client.report(result, format="html")
    assert rendered == client.report(source, format="html")
    assert rendered == asyncio.run(client.areport(awaited, format="html"))
    assert result.save_report(tmp_path / "saved.html", format="html") == rendered
    assert (tmp_path / "saved.html").read_text() == rendered
    assert prompt not in rendered and digest(source.read_bytes()) in rendered
    assert json.loads(source.read_bytes())["input"] == prompt
    assert client.report(result, format="json") == before_json
    assert client.report(result) == before_markdown
    with pytest.raises(BacktestClientError, match="safely create"):
        result.save_report(tmp_path / "saved.html", format="html")


@pytest.mark.parametrize("asynchronous", [False, True])
def test_html_ai_rejects_before_reads_calls_or_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    asynchronous: bool,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("HTML+AI must reject before reading or building reports")

    monkeypatch.setattr("strategy_backtest_agent.client.read_input", forbidden)
    monkeypatch.setattr("strategy_backtest_agent.client.build_report", forbidden)
    client = BacktestClient()
    destination = tmp_path / "uncreated" / "bad.html"
    with pytest.raises(BacktestClientError, match="do not support AI"):
        if asynchronous:
            asyncio.run(
                client.areport(tmp_path / "absent", format="html", ai=True, output=destination)
            )
        else:
            client.report(tmp_path / "absent", format="html", ai=True, output=destination)
    assert not destination.parent.exists()


def test_cli_html_ai_rejects_before_read_or_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("CLI HTML+AI must not read research")

    monkeypatch.setattr("strategy_backtest_agent.reports.cli.read_input", forbidden)
    destination = tmp_path / "uncreated" / "bad.html"
    with pytest.raises(SystemExit) as error:
        main(["--input", "absent", "--format", "html", "--ai", "--output", str(destination)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert not output.out and "do not support AI" in output.err
    assert not destination.parent.exists()


@pytest.mark.parametrize(
    "bad", ["malformed", "normalized_file", "contradictory", "typed_hash", "oversized"]
)
def test_bad_inputs_never_publish_partial_output(
    bad: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = BacktestClient()
    native = (FIXTURES / "v0.9.0/backtest.json").read_bytes()
    report = build_report(native)
    source = tmp_path / "bad.json"
    content = b'{"PRIVATE_DO_NOT_ECHO":'
    if bad == "normalized_file":
        content = report.model_dump_json().encode()
    elif bad == "contradictory":
        raw = json.loads(native)
        raw["final_balance"] = 999999
        content = json.dumps(raw).encode()
    elif bad == "oversized":
        content = native
        monkeypatch.setattr("strategy_backtest_agent.reports.html.MAX_HTML_BYTES", 1)
    source.write_bytes(content)
    api_source: Path | ResearchReport = source
    if bad == "typed_hash":
        api_source = report.model_copy(update={"evidence_sha256": "bad"})
    destination = tmp_path / "new" / "bad.html"
    with pytest.raises(BacktestClientError):
        client.report(api_source, format="html", output=destination)
    assert not destination.parent.exists()
    if bad != "typed_hash":
        with pytest.raises(SystemExit) as error:
            main(["--input", str(source), "--format", "html", "--output", str(destination)])
        assert error.value.code == 2
        captured = capsys.readouterr()
        assert not captured.out and "PRIVATE_DO_NOT_ECHO" not in captured.err
        assert not destination.parent.exists()


@pytest.mark.parametrize(
    "conflict", ["symlink", "parent_symlink", "directory", "traversal", "race", "fsync"]
)
def test_shared_writer_protections_for_html(
    conflict: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    client = BacktestClient()
    source = FIXTURES / "v0.9.0/backtest.json"
    destination = tmp_path / "report.html"
    protected = tmp_path / "protected"
    protected.write_text("unchanged")
    if conflict == "symlink":
        destination.symlink_to(protected)
    elif conflict == "parent_symlink":
        link = tmp_path / "link"
        link.symlink_to(tmp_path, target_is_directory=True)
        destination = link / "absent.html"
    elif conflict == "directory":
        destination.mkdir()
    elif conflict == "traversal":
        destination = tmp_path / ".." / "absent.html"
    elif conflict == "race":
        link_function = os.link

        def racing(*args: Any, **kwargs: Any) -> None:
            destination.write_text("racer")
            link_function(*args, **kwargs)

        monkeypatch.setattr(os, "link", racing)
    elif conflict == "fsync":

        def failing(*args: Any) -> None:
            raise OSError("synthetic fsync failure")

        monkeypatch.setattr(os, "fsync", failing)
    with pytest.raises(BacktestClientError, match="safely create"):
        client.report(source, format="html", output=destination)
    assert protected.read_text() == "unchanged"
    assert not list(tmp_path.glob(".research-report-*.tmp"))
    if conflict == "race":
        assert destination.read_text() == "racer"
    elif conflict == "fsync":
        assert not destination.exists()
