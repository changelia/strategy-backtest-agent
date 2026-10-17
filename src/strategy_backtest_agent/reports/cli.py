"""Read one existing result, render offline, optionally interpret. Never rerun research."""

import argparse
import os
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.inputs import read_input
from strategy_backtest_agent.reports.render import markdown


def write_new(path: Path, content: str) -> None:
    """Atomic no-overwrite publication; traverse/create directories without symlinks."""
    if ".." in path.parts:
        raise ValueError("output paths must not contain parent traversal (..)")
    absolute = Path(os.path.abspath(path))
    if not absolute.name:
        raise ValueError("output must name a file")
    directory = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    temporary = f".research-report-{uuid4().hex}.tmp"
    created = False
    try:
        for part in absolute.parts[1:-1]:
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
            except FileNotFoundError:
                os.mkdir(part, mode=0o700, dir_fd=directory)
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
            os.close(directory)
            directory = child
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        created = True
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # link fails atomically if the destination already exists, including symlinks.
        os.link(
            temporary,
            absolute.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
            follow_symlinks=False,
        )
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="strategy-backtest report",
        description="Render one validated v0.9 research JSON without executing a backtest",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--output", type=Path, help="Create a new report; existing paths are never overwritten"
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="Optional constrained evidence interpretation; deterministic fallback on failure",
    )
    args = parser.parse_args(argv)
    try:
        if args.output is not None and os.path.lexists(args.output):
            raise ValueError("output already exists; choose a new filename (no overwrite)")
        report = build_report(read_input(args.input))
        if args.ai:
            from strategy_backtest_agent.reports.ai import interpret

            report = interpret(report)
        content = report.model_dump_json() + "\n" if args.format == "json" else markdown(report)
        if args.output is None:
            print(content, end="")
        else:
            write_new(args.output, content)
        if report.status in ("ai_unavailable", "ai_rejected"):
            print(f"{report.status}: deterministic report successfully generated.", file=sys.stderr)
    except ValidationError as exc:
        locations = ", ".join(
            "/".join(str(p) for p in error["loc"]) or "root" for error in exc.errors()[:8]
        )
        parser.exit(
            2,
            f"Error: Unsupported/corrupted research schema at {locations}. "
            "Supply complete v0.9 CLI --json output.\n",
        )
    except (ValueError, OSError, OverflowError, RecursionError) as exc:
        parser.exit(2, f"Error: {exc}\n")
