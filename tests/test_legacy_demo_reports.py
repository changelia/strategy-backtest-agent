"""Untouched offline CLI demo JSON must support both report formats."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from strategy_backtest_agent.cli import main
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.render import markdown


@pytest.fixture
def demo_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> bytes:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["strategy-backtest", "--demo", "--json"])
    main()
    output = capsys.readouterr()
    assert not output.err
    return output.out.encode()


def test_untouched_demo_cli_reports_are_deterministic_and_evidence_unchanged(
    demo_json: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "demo.json"
    source.write_bytes(demo_json)
    original = build_report(demo_json)
    before = original.model_dump_json()
    outputs: dict[str, str] = {}
    for format_name in ("json", "markdown"):
        for repeat in range(2):
            monkeypatch.setattr(
                sys,
                "argv",
                ["strategy-backtest", "report", "--input", str(source), "--format", format_name],
            )
            main()
            output = capsys.readouterr()
            assert not output.err
            if repeat:
                assert output.out == outputs[format_name]
            outputs[format_name] = output.out
    assert "RSI(14) &lt; 30" in outputs["markdown"]
    assert "RSI(14) &gt; 70" in outputs["markdown"]
    assert json.loads(outputs["json"]) == json.loads(before)
    assert source.read_bytes() == demo_json
    assert original.model_dump_json() == before
    # Historical Task #16 JSON baseline: presentation must not change evidence/output.
    assert original.evidence_sha256 == (
        "bbfe64bc4e91ebb17942501c4b11ca13bdc5f02ea6c9ad150cbcf0925cc47c48"
    )
    assert hashlib.sha256(outputs["json"].encode()).hexdigest() == (
        "52173551a777f1e15b19bfba9688b14a662eef79c4a3d4c5915c4b16ff933ea3"
    )


@pytest.mark.parametrize("mutation", ["missing", "extra", "unsupported", "invalid_period"])
def test_malformed_legacy_demo_remains_rejected(
    demo_json: bytes,
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = json.loads(demo_json)
    if mutation == "missing":
        del data["strategy"]["entry_rsi"]
    elif mutation == "extra":
        data["strategy"]["code"] = "unsupported"
    elif mutation == "unsupported":
        data["strategy"]["name"] = "unknown"
    else:
        data["strategy"]["rsi_period"] = 0
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(data))
    monkeypatch.setattr(
        sys, "argv", ["strategy-backtest", "report", "--input", str(source), "--format", "markdown"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert not output.out and "Error:" in output.err and "Traceback" not in output.err


def test_existing_dsl_markdown_snapshot_unchanged() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "reports"
    report = build_report((fixtures / "v0.9.0/backtest.json").read_bytes())
    assert markdown(report) == (fixtures / "markdown/backtest.md").read_text()
