"""Fail-closed policy checks used by the opt-in PyPI release workflow."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPOSITORY = "changelia/strategy-backtest-agent"


class ReleaseGateError(ValueError):
    """Raised when the release workflow context is not explicitly authorized."""


def validate_build_context(
    *, event: str, ref: str, repository: str, publish_requested: bool, version: str
) -> None:
    if repository != REPOSITORY:
        raise ReleaseGateError("repository is not the configured project")
    if event not in {"push", "workflow_dispatch"}:
        raise ReleaseGateError("only tag pushes or manual dispatches may run release validation")
    if event == "push" and not ref.startswith("refs/tags/"):
        raise ReleaseGateError("push-triggered release validation is restricted to version tags")
    if ref.startswith("refs/tags/") and ref != f"refs/tags/v{version}":
        raise ReleaseGateError("release tag does not match the package version")
    if publish_requested and (event != "workflow_dispatch" or not ref.startswith("refs/tags/")):
        raise ReleaseGateError("publication requires an explicit dispatch of a version tag")


def validate_publish_context(
    *,
    event: str,
    ref: str,
    repository: str,
    publish_requested: bool,
    version: str,
    workflow_sha: str,
    checkout_sha: str,
    tag_commit: str,
    main_commit: str,
    annotated_tag: bool,
) -> None:
    validate_build_context(
        event=event,
        ref=ref,
        repository=repository,
        publish_requested=publish_requested,
        version=version,
    )
    if not publish_requested or event != "workflow_dispatch":
        raise ReleaseGateError("publishing is disabled unless explicitly requested by dispatch")
    if not annotated_tag:
        raise ReleaseGateError("release tag must be an annotated tag")
    if not workflow_sha or not (workflow_sha == checkout_sha == tag_commit == main_commit):
        raise ReleaseGateError(
            "tag, workflow checkout and origin/main must point to the same commit"
        )


def project_version() -> str:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    return str(config["project"]["version"])


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseGateError("could not verify Git release references") from exc


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        event = os.environ.get("GITHUB_EVENT_NAME", "")
        ref = os.environ.get("GITHUB_REF", "")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        publish_requested = os.environ.get("RELEASE_PUBLISH", "false").lower() == "true"
        version = project_version()
        if mode == "build":
            validate_build_context(
                event=event,
                ref=ref,
                repository=repository,
                publish_requested=publish_requested,
                version=version,
            )
            print(f"Release build context accepted for v{version}; no publication permission used.")
            return 0
        if mode != "publish":
            raise ReleaseGateError("usage: python tests/release_gate.py build|publish")
        if (
            event != "workflow_dispatch"
            or not publish_requested
            or not ref.startswith("refs/tags/")
        ):
            raise ReleaseGateError(
                "publication context is not explicitly enabled for a tag dispatch"
            )
        git("fetch", "origin", "refs/heads/main:refs/remotes/origin/main", "--no-tags")
        tag_commit = git("rev-parse", f"{ref}^{{commit}}")
        tag_type = git("cat-file", "-t", ref)
        main_commit = git("rev-parse", "refs/remotes/origin/main")
        validate_publish_context(
            event=event,
            ref=ref,
            repository=repository,
            publish_requested=publish_requested,
            version=version,
            workflow_sha=os.environ.get("GITHUB_SHA", ""),
            checkout_sha=git("rev-parse", "HEAD"),
            tag_commit=tag_commit,
            main_commit=main_commit,
            annotated_tag=tag_type == "tag",
        )
        print(f"Publication gate passed for v{version} at {tag_commit}.")
        return 0
    except ReleaseGateError as exc:
        print(f"Release gate blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
