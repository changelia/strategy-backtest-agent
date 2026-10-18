"""Offline failure-gate tests; no builds, installations or downloads here."""

import copy
import hashlib
import subprocess
from pathlib import Path
from typing import Any

import pytest
from packaging_ci import compare_receipts, prepare_work, run, verify_archive_origin


@pytest.fixture
def receipt() -> dict[str, Any]:
    return {
        "status": "READY",
        "report_failures": {},
        "network_attempts": 0,
        "report_sha256": {"json": "json-hash", "markdown": "markdown-hash"},
        "demo": {"final_balance": 123.09},
        "evidence_sha256": "evidence-hash",
        "init_templates": {"backtest": {"result_sha256": "result-hash"}},
        "public_api": {
            "evidence_sha256": "api-evidence-hash",
            "input_content_sha256": "api-input-hash",
            "markdown_sha256": "api-markdown-hash",
            "final_balance": 123.09,
        },
    }


def test_matching_installed_results_pass(receipt: dict[str, Any]) -> None:
    compare_receipts(receipt, copy.deepcopy(receipt))


@pytest.mark.parametrize(
    "failure",
    [
        "blocked",
        "format_failure",
        "network",
        "missing_format",
        "different_demo",
        "different_json",
        "different_evidence",
        "different_init",
        "different_public_api",
    ],
)
def test_failed_or_different_installed_results_fail_ci(
    receipt: dict[str, Any], failure: str
) -> None:
    other = copy.deepcopy(receipt)
    if failure == "blocked":
        other["status"] = "BLOCKED"
    elif failure == "format_failure":
        other["report_failures"] = {"markdown": [{"exit": 2}]}
    elif failure == "network":
        other["network_attempts"] = 1
    elif failure == "missing_format":
        del other["report_sha256"]["markdown"]
    elif failure == "different_demo":
        other["demo"]["final_balance"] = 10000
    elif failure == "different_json":
        other["report_sha256"]["json"] = "changed"
    elif failure == "different_init":
        other["init_templates"]["backtest"]["result_sha256"] = "changed"
    elif failure == "different_public_api":
        other["public_api"]["evidence_sha256"] = "changed"
    else:
        other["evidence_sha256"] = "changed"
    with pytest.raises(ValueError):
        compare_receipts(receipt, other)


@pytest.mark.parametrize("failure", [None, "different_archive", "changed_hash", "editable"])
def test_supplied_archive_is_the_installed_source(tmp_path: Path, failure: str | None) -> None:
    artifact = tmp_path / "fresh.tar.gz"
    artifact.write_bytes(b"synthetic-archive")
    direct: dict[str, Any] = {
        "url": artifact.as_uri(),
        "archive_info": {"hashes": {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}},
    }
    if failure == "different_archive":
        direct["url"] = (tmp_path / "cached.whl").as_uri()
    elif failure == "changed_hash":
        direct["archive_info"]["hashes"]["sha256"] = "0" * 64
    elif failure == "editable":
        direct["dir_info"] = {"editable": True}
    receipt = {"installation": {"direct_url": direct}}
    if failure:
        with pytest.raises(ValueError):
            verify_archive_origin(receipt, artifact)
    else:
        verify_archive_origin(receipt, artifact)


def test_workspace_must_be_external_and_fresh(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    with pytest.raises(ValueError, match="outside"):
        prepare_work(checkout, checkout / "nested")
    external = tmp_path / "external"
    prepare_work(checkout, external)
    marker = external / "keep.json"
    marker.write_text("keep")
    with pytest.raises(ValueError, match="fresh"):
        prepare_work(checkout, external)
    assert marker.read_text() == "keep"


def test_failed_build_stops_before_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fail(args: list[str], **kwargs: Any) -> None:
        calls.append(args)
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(subprocess, "run", fail)
    work = tmp_path / "external"
    with pytest.raises(subprocess.CalledProcessError):
        run(tmp_path / "checkout", work)
    assert len(calls) == 1
    assert not (work / "wheel-env").exists()
    assert not (work / "sdist-env").exists()
