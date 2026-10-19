"""Offline policy tests for the fail-closed publication workflow."""

import pytest
from release_gate import ReleaseGateError, validate_build_context, validate_publish_context

BASE = {
    "event": "workflow_dispatch",
    "ref": "refs/tags/v1.2.1",
    "repository": "changelia/strategy-backtest-agent",
    "publish_requested": True,
    "version": "1.2.1",
}


def test_manual_branch_dispatch_is_a_valid_nonpublishing_dry_run() -> None:
    validate_build_context(
        event="workflow_dispatch",
        ref="refs/heads/release/v1.2.1",
        repository="changelia/strategy-backtest-agent",
        publish_requested=False,
        version="1.2.1",
    )


@pytest.mark.parametrize(
    ("event", "ref", "repository", "publish"),
    [
        ("pull_request", "refs/pull/1/merge", "changelia/strategy-backtest-agent", False),
        ("push", "refs/heads/main", "changelia/strategy-backtest-agent", False),
        ("push", "refs/heads/main", "changelia/strategy-backtest-agent", True),
        ("workflow_dispatch", "refs/heads/main", "changelia/strategy-backtest-agent", True),
        ("workflow_dispatch", "refs/tags/v1.0.0", "changelia/strategy-backtest-agent", True),
        ("workflow_dispatch", "refs/tags/v1.2.1", "attacker/project", True),
    ],
)
def test_build_gate_rejects_unapproved_contexts(
    event: str, ref: str, repository: str, publish: bool
) -> None:
    with pytest.raises(ReleaseGateError):
        validate_build_context(
            event=event,
            ref=ref,
            repository=repository,
            publish_requested=publish,
            version="1.2.1",
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"event": "push"},
        {"publish_requested": False},
        {"repository": "attacker/project"},
        {"ref": "refs/tags/v1.0.0"},
        {"workflow_sha": "wrong"},
        {"checkout_sha": "wrong"},
        {"tag_commit": "wrong"},
        {"main_commit": "wrong"},
        {"annotated_tag": False},
    ],
)
def test_publish_gate_rejects_mismatches_and_untrusted_context(
    overrides: dict[str, object],
) -> None:
    context: dict[str, object] = {
        **BASE,
        "workflow_sha": "a" * 40,
        "checkout_sha": "a" * 40,
        "tag_commit": "a" * 40,
        "main_commit": "a" * 40,
        "annotated_tag": True,
    }
    context.update(overrides)
    with pytest.raises(ReleaseGateError):
        validate_publish_context(
            event=str(context["event"]),
            ref=str(context["ref"]),
            repository=str(context["repository"]),
            publish_requested=bool(context["publish_requested"]),
            version=str(context["version"]),
            workflow_sha=str(context["workflow_sha"]),
            checkout_sha=str(context["checkout_sha"]),
            tag_commit=str(context["tag_commit"]),
            main_commit=str(context["main_commit"]),
            annotated_tag=bool(context["annotated_tag"]),
        )


def test_publish_gate_accepts_only_matching_annotated_main_tag() -> None:
    validate_publish_context(
        event="workflow_dispatch",
        ref="refs/tags/v1.2.1",
        repository="changelia/strategy-backtest-agent",
        publish_requested=True,
        version="1.2.1",
        workflow_sha="a" * 40,
        checkout_sha="a" * 40,
        tag_commit="a" * 40,
        main_commit="a" * 40,
        annotated_tag=True,
    )
