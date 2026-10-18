"""Offline unit coverage for the opt-in installed-artifact smoke harness."""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from installed_smoke import check_demo, check_report, check_source_metrics, clean_environment, smoke


def test_installed_environment_does_not_inherit_credentials_or_python_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "BINANCE_API_KEY",
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "PIP_INDEX_URL",
        "HOME",
    ):
        monkeypatch.setenv(key, "synthetic-private-value")
    env = clean_environment(tmp_path)
    assert "synthetic-private-value" not in env.values()
    assert env["PYTHON_DOTENV_DISABLED"] == "1"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PATH"].startswith(str(tmp_path / "bin"))


@pytest.fixture
def demo() -> dict[str, Any]:
    return {
        "initial_balance": 10000,
        "final_balance": 123.087,
        "total_return_percent": -98.76913,
        "total_trades": 45,
        "winning_trades": 0,
    }


def test_installed_demo_accepts_unrounded_baseline(demo: dict[str, Any]) -> None:
    check_demo(demo)


@pytest.mark.parametrize(
    "key",
    ["initial_balance", "final_balance", "total_return_percent", "total_trades", "winning_trades"],
)
def test_installed_demo_rejects_changed_financial_results(demo: dict[str, Any], key: str) -> None:
    demo[key] += 1
    with pytest.raises(AssertionError, match=key):
        check_demo(demo)


@pytest.fixture
def report() -> dict[str, Any]:
    return {
        "report_schema_version": "1.0",
        "evidence": {
            "source": {
                "research_type": "backtest",
                "input_content_sha256": hashlib.sha256(b"source").hexdigest(),
            },
            "metrics": [{"id": "test", "value": None}],
        },
        "evidence_sha256": "a" * 64,
        "ai_interpretation": None,
    }


def test_installed_report_requires_source_provenance(report: dict[str, Any]) -> None:
    check_report(report, b"source")
    with pytest.raises(AssertionError):
        check_report(report, b"other source")


def test_installed_evidence_retains_values_and_nulls() -> None:
    report = {
        "evidence": {
            "metrics": [
                {"id": "return", "source_path": "/total_return_percent", "value": -98.77},
                {"id": "undefined", "source_path": "/profit_factor", "value": None},
                {"id": "fee", "source_path": "/execution/fee_rate", "value": 0.001},
            ]
        }
    }
    source = {
        "total_return_percent": -98.77,
        "profit_factor": None,
        "execution": {"fee_rate": 0.001},
    }
    check_source_metrics(report, source)
    source["profit_factor"] = 0
    with pytest.raises(AssertionError, match="undefined"):
        check_source_metrics(report, source)


@pytest.mark.parametrize("change", ["empty_metrics", "wrong_type", "unexpected_ai"])
def test_installed_report_rejects_incorrect_output(report: dict[str, Any], change: str) -> None:
    if change == "empty_metrics":
        report["evidence"]["metrics"] = []
    elif change == "wrong_type":
        report["evidence"]["source"]["research_type"] = "comparison"
    else:
        report["ai_interpretation"] = {"unexpected": "content"}
    with pytest.raises(AssertionError):
        check_report(report, b"source")


def test_installed_smoke_refuses_checkout_working_directory(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        smoke(tmp_path / "external-env", tmp_path / "work", tmp_path)


def test_installed_smoke_preserves_nonempty_working_directory(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    marker = work / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(AssertionError, match="fresh"):
        smoke(tmp_path / "env", work, tmp_path / "checkout")
    assert marker.read_text() == "keep"
