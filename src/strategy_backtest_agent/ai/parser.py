"""OpenAI Responses boundary; no prices, indicators, or result calculations."""

import os
import re
from collections.abc import Callable
from typing import TypeVar

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from strategy_backtest_agent.ai.models import (
    AIStrategyConfig,
    ComparisonParserOutput,
    ParserOutput,
    ValidationParserOutput,
)
from strategy_backtest_agent.ai.prompts import COMPARISON_PROMPT, SYSTEM_PROMPT, VALIDATION_PROMPT
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.validation.models import ValidationConfig

DEFAULT_MODEL = "gpt-6-luna"


class StrategyParseError(ValueError):
    """A request could not be translated into a supported validated strategy."""


# Conservative early rejection of explicit unsupported concepts, not JSON extraction.
# The structured model rejection also handles semantics, ambiguity and multiple symbols.
_UNSUPPORTED = (
    (r"\bmacd\b", "MACD"),
    (r"\bbollinger\b", "Bollinger Bands"),
    (r"\bleverage\b|\b\d+(?:\.\d+)?\s*x\b", "leverage"),
    (r"\bshort(?:s|[- ]selling|\s+position)?\b", "short selling"),
    (r"\bstop[- ]?loss\b", "stop loss"),
    (r"\btake[- ]?profit\b", "take profit"),
    (
        r"\bcross(?:es|ing)?\s+(?:above|below|over|under)\b|\bcross(?:over|under)\b",
        "crossover/crossunder events",
    ),
    (r"\bportfolio\b", "portfolio strategies"),
    (r"\blive\s+trad(?:e|ing)\b", "live trading"),
    (r"\bpredict(?:ion|ions|ing)?\b", "price prediction"),
)


def create_client() -> OpenAI:
    """Read credentials only from the environment; bound requests and disable retries."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise StrategyParseError("OPENAI_API_KEY is missing; export it before using ai")
    return OpenAI(api_key=key, base_url="https://api.openai.com/v1", timeout=30, max_retries=0)


OutputT = TypeVar("OutputT", bound=BaseModel)
ConfigT = TypeVar("ConfigT", AIStrategyConfig, ComparisonConfig, ValidationConfig)


def _strategy_configuration(output: ParserOutput) -> AIStrategyConfig:
    if output.rejection is not None:
        raise StrategyParseError(
            f"Request rejected: {output.rejection.replace('_', ' ')}. "
            "Currently supported: long-only RSI, SMA, EMA level rules"
        )
    assert output.configuration is not None
    return output.configuration.validated_config()


def _comparison_configuration(output: ComparisonParserOutput) -> ComparisonConfig:
    if output.rejection is not None:
        raise StrategyParseError(f"Request rejected: {output.rejection.replace('_', ' ')}")
    assert output.configuration is not None
    return output.configuration.validated_config()


def parse_strategy(text: str) -> AIStrategyConfig:
    """Extract a supported single-strategy request with the existing defaults."""
    return _parse_request(text, ParserOutput, SYSTEM_PROMPT, _strategy_configuration)


def parse_comparison(text: str) -> ComparisonConfig:
    """One structured request for all comparison rules and shared settings."""
    return _parse_request(
        text,
        ComparisonParserOutput,
        COMPARISON_PROMPT,
        _comparison_configuration,
        max_output_tokens=16384,
    )


def _validation_configuration(output: ValidationParserOutput) -> ValidationConfig:
    if output.rejection is not None:
        raise StrategyParseError(f"Request rejected: {output.rejection.replace('_', ' ')}")
    assert output.configuration is not None
    return output.configuration.validated_config()


def parse_validation(text: str) -> ValidationConfig:
    """One extraction request; holdout execution and results remain entirely in Python."""
    if re.search(
        r"\b(?:random|shuffl\w*|optimi[sz]\w*|tun(?:e|ing)|walk[- ]forward|folds?)\b"
        r"|\brobustness\s+score\b|\b(?:select|choose|pick|winner|best)\b",
        text,
        re.IGNORECASE,
    ):
        raise StrategyParseError(
            "Unsupported validation: optimization, selection or nonchronological split"
        )
    return _parse_request(
        text,
        ValidationParserOutput,
        VALIDATION_PROMPT,
        _validation_configuration,
        max_output_tokens=16384,
    )


def _parse_request(
    text: str,
    schema: type[OutputT],
    instructions: str,
    convert: Callable[[OutputT], ConfigT],
    *,
    max_output_tokens: int = 4096,
) -> ConfigT:
    """Shared SDK boundary, unsupported checks, validation and sanitized errors."""
    if not text.strip():
        raise StrategyParseError("request must not be empty")
    if len(text) > 8000:
        raise StrategyParseError("request must be at most 8000 characters")
    for pattern, label in _UNSUPPORTED:
        if re.search(pattern, text, re.IGNORECASE):
            raise StrategyParseError(
                f"Unsupported strategy: {label}. "
                "Currently supported: long-only RSI, SMA, EMA level rules"
            )
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip()
    if not model:
        raise StrategyParseError("OPENAI_MODEL must not be empty")
    try:
        with create_client() as client:
            response = client.responses.parse(
                model=model,
                instructions=instructions,
                input=text,
                text_format=schema,
                max_output_tokens=max_output_tokens,
                store=False,
            )
        if response.status != "completed" or response.output_parsed is None:
            raise StrategyParseError(
                "AI did not return a complete structured strategy (or refused)"
            )
        # Revalidate even an SDK model instance; constructed objects must not bypass validation.
        output = schema.model_validate(response.output_parsed.model_dump(warnings=False))
        configuration = convert(output)
        if not re.search(
            rf"(?<![A-Za-z0-9]){re.escape(configuration.symbol)}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        ):
            raise StrategyParseError("Parsed symbol must be explicitly present in the request")
        return configuration
    except AuthenticationError:
        raise StrategyParseError("OpenAI authentication failed; check OPENAI_API_KEY") from None
    except RateLimitError:
        raise StrategyParseError("OpenAI rate limit or quota reached; retry later") from None
    except APITimeoutError:
        raise StrategyParseError("OpenAI request timed out; retry later") from None
    except APIConnectionError:
        raise StrategyParseError("OpenAI is unavailable; check your network") from None
    except APIError:
        raise StrategyParseError(
            "OpenAI request failed; check model access and service status"
        ) from None
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or 'configuration'}: {error['msg']}"
            for error in exc.errors()
        )
        raise StrategyParseError(f"Invalid parsed strategy: {messages}") from None
    except (OpenAIError, TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, StrategyParseError):
            raise
        raise StrategyParseError("AI structured output could not be validated") from None
