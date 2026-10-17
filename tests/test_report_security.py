"""Bounded parsing, contradictory identifiers/metadata and safe filesystem output."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from test_reports import encode

from strategy_backtest_agent.cli import main
from strategy_backtest_agent.reports.cli import write_new
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.inputs import MAX_INPUT_BYTES, parse_input
from strategy_backtest_agent.reports.render import markdown


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"[]",
        b"{}",
        b"{broken",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e999}',
        b'{"x":1,"x":2}',
        b"\xff",
        b'{"x":"\\u0000"}',
    ],
)
def test_malformed_unsupported_json_rejected(content: bytes) -> None:
    with pytest.raises(ValueError):
        build_report(content)


def test_input_resource_limits() -> None:
    for content in [
        b" " * (MAX_INPUT_BYTES + 1),
        encode({"x": "a" * 8193}),
        ('{"x":' * 40 + "0" + "}" * 40).encode(),
        encode({"x": [0] * 250001}),
    ]:
        with pytest.raises(ValueError):
            parse_input(content)


@pytest.mark.parametrize(
    "kind",
    [
        "ids",
        "ranking",
        "strategy",
        "shared_end",
        "candle_count",
        "warmup",
        "execution",
        "trade_time",
        "fill_fee",
        "cost_total",
        "excess",
        "missing_provenance",
        "merged_reports",
    ],
)
def test_corrupted_comparison_rejected(
    kind: str, native_results: dict[str, dict[str, Any]]
) -> None:
    raw = copy.deepcopy(native_results["comparison"])
    row = raw["results"][0]
    if kind == "ids":
        row["id"] = "unknown"
    elif kind == "ranking":
        raw["ranking"] = list(reversed(raw["ranking"]))
    elif kind == "strategy":
        row["strategy"]["entry"]["operator"] = "<"
    elif kind == "shared_end":
        raw["shared_data"]["evaluation_end"] = "2025-01-01T00:00:00Z"
    elif kind == "candle_count":
        raw["shared_data"]["candle_count"] = 10
    elif kind == "warmup":
        raw["shared_data"]["warmup_candles"] = 1
    elif kind == "execution":
        row["result"]["execution"]["spread_bps"] = 99
    elif kind == "trade_time":
        row["result"]["trades"][0]["entry_time"] = raw["shared_data"]["first_candle_open"]
    elif kind == "fill_fee":
        row["result"]["trades"][0]["entry_execution"]["fee"] = 999
    elif kind == "cost_total":
        row["result"]["costs"]["fees"] = 999
    elif kind == "excess":
        row["excess_return_pp"] = 999
    elif kind == "missing_provenance":
        raw["shared_data"].pop("candles_sha256")
    elif kind == "merged_reports":
        raw["folds"] = native_results["walk_forward"]["folds"]
    with pytest.raises(ValueError):
        build_report(encode(raw))


@pytest.mark.parametrize("kind", ["summary", "overlap", "id", "missing_fold", "stitch", "trailing"])
def test_corrupted_oos_rejected(kind: str, native_results: dict[str, dict[str, Any]]) -> None:
    raw = copy.deepcopy(native_results["walk_forward"])
    if kind == "summary":
        raw["summaries"][0]["positive_test_folds"] = 3
    elif kind == "overlap":
        raw["folds"][1]["test_start"] = raw["folds"][0]["test_start"]
    elif kind == "id":
        raw["results"][0]["fold_id"] = "unknown"
    elif kind == "missing_fold":
        raw["folds"].pop()
    elif kind == "stitch":
        raw["summaries"][0]["stitched_oos_index"][-1]["value"] = 999
    elif kind == "trailing":
        raw["unused_trailing_candles"] = 1
    with pytest.raises(ValueError):
        build_report(encode(raw))


def test_markdown_injection_is_data_not_structure(
    native_results: dict[str, dict[str, Any]],
) -> None:
    raw = copy.deepcopy(native_results["comparison"])
    attack = "[evil](https://example.com) | <script>alert(1)</script> ` ```"
    raw["configuration"]["strategies"][0]["name"] = attack
    raw["results"][0]["name"] = attack
    raw["shared_data"]["source"] = "synthetic\n# Forged section\n<script>"
    report = build_report(encode(raw))
    rendered = markdown(report)
    assert "\n# Forged section" not in rendered and "<script>" not in rendered
    assert "[evil](" not in rendered and "```" not in rendered
    assert "&#" in rendered
    assert report.evidence.scopes[0].label == attack


def test_atomic_output_and_no_overwrite_or_symlink(tmp_path: Path) -> None:
    output = tmp_path / "reports" / "research.md"
    write_new(output, "first\n")
    with pytest.raises(FileExistsError):
        write_new(output, "second\n")
    assert output.read_text() == "first\n"
    assert not list(output.parent.glob(".research-report-*.tmp"))
    link = tmp_path / "linked"
    link.symlink_to(output.parent, target_is_directory=True)
    with pytest.raises(OSError):
        write_new(link / "injected.md", "unsafe")
    assert not (output.parent / "injected.md").exists()
    with pytest.raises(ValueError, match="traversal"):
        write_new(tmp_path / ".." / "unsafe.md", "unsafe")


@pytest.mark.parametrize(
    "kind", ["backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward"]
)
@pytest.mark.parametrize("format", ["markdown", "json"])
def test_cli_all_modes_no_ai(
    kind: str,
    format: str,
    native_results: dict[str, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(encode(native_results[kind]))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "sys.argv", ["strategy-backtest", "report", "--input", str(path), "--format", format]
    )
    main()
    result = capsys.readouterr()
    assert result.err == ""
    if format == "json":
        assert json.loads(result.out)["evidence"]["source"]["research_type"] == kind
    else:
        assert result.out.startswith("# Historical Strategy Research Report")


def test_cli_file_and_ai_missing_exit_semantics(
    native_results: dict[str, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(encode(native_results["comparison"]))
    output = tmp_path / "reports" / "research.json"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = [
        "strategy-backtest",
        "report",
        "--input",
        str(path),
        "--ai",
        "--format",
        "json",
        "--output",
        str(output),
    ]
    monkeypatch.setattr("sys.argv", args)
    main()
    printed = capsys.readouterr()
    assert printed.out == "" and "ai_unavailable" in printed.err
    assert json.loads(output.read_text())["status"] == "ai_unavailable"
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "already exists" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["missing", "corrupt", "directory"])
def test_cli_actionable_input_errors(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "input.json"
    if mode == "corrupt":
        path.write_text("{bad")
    elif mode == "directory":
        path.mkdir()
    monkeypatch.setattr(
        "sys.argv", ["strategy-backtest", "report", "--input", str(path), "--format", "json"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    result = capsys.readouterr()
    assert exc.value.code == 2 and result.out == "" and "Error:" in result.err


def test_filename_not_derived_from_source_and_symlink_destination_never_overwritten(
    native_results: dict[str, dict[str, Any]], tmp_path: Path
) -> None:
    raw = copy.deepcopy(native_results["comparison"])
    raw["shared_data"]["source"] = "../../unsafe.md"
    build_report(encode(raw))
    assert list(tmp_path.iterdir()) == []
    original = tmp_path / "original.md"
    original.write_text("protected")
    output = tmp_path / "report.md"
    output.symlink_to(original)
    with pytest.raises(FileExistsError):
        write_new(output, "overwrite")
    assert original.read_text() == "protected"


def test_failed_write_cleans_temporary_and_never_publishes_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(fd: int) -> None:
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr("os.fsync", fail)
    output = tmp_path / "report.md"
    with pytest.raises(OSError):
        write_new(output, "partial")
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_json_stdout_ai_failure_is_one_valid_object(
    native_results: dict[str, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(encode(native_results["walk_forward"]))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["strategy-backtest", "report", "--input", str(path), "--ai", "--format", "json"],
    )
    main()
    printed = capsys.readouterr()
    assert json.loads(printed.out)["status"] == "ai_unavailable"
    assert printed.out.count('"report_schema_version"') == 1
    assert "ai_unavailable" in printed.err
