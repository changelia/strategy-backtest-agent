"""Offline, read-only diagnostics with deliberately bounded readiness claims."""

import argparse
import importlib.metadata
import logging
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Never

from dotenv import find_dotenv, load_dotenv

from strategy_backtest_agent.demo import demo_candles
from strategy_backtest_agent.init_cli import TYPES

DISTRIBUTION = "strategy-backtest-agent"
# This project's declared contract, not a general-purpose PEP 440 parser.
PYTHON_REQUIREMENT = ">=3.12,<4.0"


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        self.print_usage(sys.stderr)
        self.exit(2, "Error: Invalid doctor arguments; use strategy-backtest doctor --help.\n")


class ParseWarnings(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.seen = False

    def emit(self, record: logging.LogRecord) -> None:
        self.seen = True  # Never format or forward untrusted parser messages.


def dotenv_state() -> tuple[str, bool]:
    if os.environ.get("PYTHON_DOTENV_DISABLED", "").casefold() in {"1", "true", "t", "yes", "y"}:
        return "disabled; discovery/loading skipped", False
    logger = logging.getLogger("dotenv.main")
    previous = logger.handlers[:], logger.propagate, logger.level
    warnings = ParseWarnings()
    logger.handlers, logger.propagate = [warnings], False
    logger.setLevel(logging.WARNING)
    try:
        path = find_dotenv(usecwd=True)
        if not path:
            return "not found; optional for offline use", False
        applied = load_dotenv(dotenv_path=path, override=False)
        if warnings.seen:
            return "ERROR parsing warnings; review local .env (values not shown)", True
        if applied:
            return "found and parsed; shell/process values retain precedence", False
        return "found; no assignments applied (empty/no values); shell values preserved", False
    except (OSError, ValueError):
        return "ERROR discovery/loading failed; check local .env access and UTF-8 encoding", True
    finally:
        logger.handlers, logger.propagate, logger.level = previous


def installed_metadata() -> tuple[str | None, str | None]:
    try:
        metadata = importlib.metadata.metadata(DISTRIBUTION)
        return metadata.get("Version"), metadata.get("Requires-Python")
    except (
        importlib.metadata.PackageNotFoundError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        return None, None


def source_metadata() -> tuple[str | None, str | None]:
    """Only this module's src checkout, never arbitrary cwd/ancestor projects."""
    module = Path(__file__).resolve()
    if module.parent.parent.name != "src":
        return None, None
    try:
        with (module.parents[2] / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        if project["name"] != DISTRIBUTION:
            return None, None
        version, requirements = project["version"], project["requires-python"]
        if not isinstance(version, str) or not isinstance(requirements, str):
            return None, None
        return version, requirements
    except (OSError, ValueError, KeyError, TypeError):
        return None, None


def version_label(value: str | None) -> str:
    # Do not echo arbitrary metadata text, terminal escapes or exception messages.
    if value is not None and re.fullmatch(
        r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:a|b|rc)[0-9]+)?", value
    ):
        return value
    return "unavailable or unrecognized (not displayed)"


def config_valid(path: Path, kind: str) -> bool:
    from strategy_backtest_agent.comparison.models import ComparisonConfig
    from strategy_backtest_agent.models import BacktestConfig, Model
    from strategy_backtest_agent.reports.inputs import MAX_INPUT_BYTES, read_input
    from strategy_backtest_agent.validation.models import ValidationConfig
    from strategy_backtest_agent.walk_forward.models import WalkForwardConfig

    models: dict[str, type[Model]] = {
        "backtest": BacktestConfig,
        "compare": ComparisonConfig,
        "validate": ValidationConfig,
        "walk-forward": WalkForwardConfig,
    }
    try:
        contents = read_input(path)
        if len(contents) > MAX_INPUT_BYTES:
            return False
        models[kind].model_validate_json(contents)
        return True
    except (OSError, ValueError, TypeError, RecursionError):
        return False


def main(argv: list[str] | None = None) -> None:
    parser = SafeParser(
        prog="strategy-backtest doctor",
        description="Read-only offline environment diagnostics.",
        epilog="Exit 0: checked offline capabilities available (AI optional). "
        "Exit 1: environment/configuration needs attention. Exit 2: invalid arguments. "
        "No requests, credential validation, repairs or research runs are performed.",
    )
    parser.add_argument(
        "--type", choices=TYPES, help="Explicit config workflow, paired with --config"
    )
    parser.add_argument("--config", type=Path, help="Validate only this file using --type's model")
    args = parser.parse_args(argv)
    if (args.type is None) != (args.config is None):
        parser.error("Both options are required together")
    print("Strategy Backtest Agent Doctor")
    status = 0
    installed, installed_requires = installed_metadata()
    source, source_requires = source_metadata()
    print(f"Installed package version: {version_label(installed)}")
    print(f"Source checkout version: {version_label(source)}")
    if installed is None:
        print("WARN installed metadata unavailable; installed version cannot be confirmed.")
    if source is not None and installed is not None and installed != source:
        print(
            "WARN installed/source versions differ; reinstall to refresh stale/editable metadata."
        )
    requirements = source_requires or installed_requires or PYTHON_REQUIREMENT
    compatible = (3, 12) <= sys.version_info[:2] < (4, 0)
    known = requirements.replace(" ", "") == PYTHON_REQUIREMENT
    print(f"Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    if not known:
        print("ERROR Python compatibility unverified: unfamiliar metadata requirements.")
        status = 1
    elif not compatible:
        print(f"ERROR Python incompatible; use {PYTHON_REQUIREMENT}.")
        status = 1
    else:
        print(f"Python compatibility: matches project baseline {PYTHON_REQUIREMENT}.")
    key_in_process = "OPENAI_API_KEY" in os.environ
    state, error = dotenv_state()
    print(f"Dotenv: {state}")
    if error:
        status = 1
    key_present = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    origin = (
        "process environment"
        if key_in_process
        else "dotenv"
        if "OPENAI_API_KEY" in os.environ
        else "none"
    )
    print(f"OpenAI key: {'present' if key_present else 'absent or empty'}; source: {origin}.")
    print("Key presence does not establish validity, funding or authorization.")
    if "OPENAI_MODEL" in os.environ:
        model_present = bool(os.environ["OPENAI_MODEL"].strip())
        print(
            "AI model: override configured (value hidden)."
            if model_present
            else "WARN AI model override is empty; optional AI unavailable."
        )
    else:
        try:
            from strategy_backtest_agent.ai.parser import DEFAULT_MODEL

            print(f"AI model: shared default {DEFAULT_MODEL}.")
        except ImportError:
            print("WARN optional AI dependencies unavailable; shared default could not be read.")
    print("AI configuration/provider availability not verified; no OpenAI/Binance requests made.")
    if not key_present:
        print("Optional AI unavailable without a key; offline functionality does not require one.")
    if args.config is None:
        print("Research config: not supplied; no research files discovered or validated.")
    elif config_valid(args.config, args.type):
        print(f"Research config: valid {args.type} model; data/execution not tested.")
    else:
        print("ERROR research config invalid/unreadable; check the selected model and JSON file.")
        status = 1
    try:
        demo_candles("1h", 1)
        print(
            "Offline checks: available (imports and synthetic candles only; research not executed)."
        )
    except (ValueError, OSError, ImportError):
        print("ERROR offline self-check failed; check installation and dependencies.")
        status = 1
    if status:
        print("Result: attention required; see ERROR diagnostics above.")
        raise SystemExit(1)
    print("Result: checked offline capabilities available; optional AI may be unavailable.")
