"""OpenAI Responses boundary; no prices, indicators, or result calculations."""

import os
import re

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import ValidationError

from strategy_backtest_agent.ai.models import AIStrategyConfig, ParserOutput
from strategy_backtest_agent.ai.prompts import SYSTEM_PROMPT

DEFAULT_MODEL = "gpt-6-luna"


class StrategyParseError(ValueError):
    """A request could not be translated into a supported validated strategy."""


# Conservative early rejection of explicit unsupported concepts, not JSON extraction.
# The structured model rejection also handles semantics, ambiguity and multiple symbols.
_UNSUPPORTED = (
    (r"\bmacd\b", "MACD"),
    (r"\bbollinger\b", "Bollinger Bands"),
    (r"\bleverage\b|\b\d+(?:\.\d+)?\s*x\b", "leverage"),
    (r"\bshort(?:[- ]selling|\s+position)?\b", "short selling"),
    (r"\bstop[- ]?loss\b", "stop loss"),
    (r"\btake[- ]?profit\b", "take profit"),
    (r"\b(?:sma|ema)\b", "multiple or unsupported indicators"),
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


def parse_strategy(text: str) -> AIStrategyConfig:
    """Extract a supported request and apply deterministic defaults and validation."""
    if not text.strip():
        raise StrategyParseError("request must not be empty")
    if len(text) > 8000:
        raise StrategyParseError("request must be at most 8000 characters")
    for pattern, label in _UNSUPPORTED:
        if re.search(pattern, text, re.IGNORECASE):
            raise StrategyParseError(
                f"Unsupported strategy: {label}. Currently supported: long-only RSI"
            )
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip()
    if not model:
        raise StrategyParseError("OPENAI_MODEL must not be empty")
    try:
        with create_client() as client:
            response = client.responses.parse(
                model=model,
                instructions=SYSTEM_PROMPT,
                input=text,
                text_format=ParserOutput,
                max_output_tokens=4096,
                store=False,
            )
        if response.status != "completed" or response.output_parsed is None:
            raise StrategyParseError(
                "AI did not return a complete structured strategy (or refused)"
            )
        # Revalidate even an SDK model instance; constructed objects must not bypass validation.
        output = ParserOutput.model_validate(response.output_parsed.model_dump())
        if output.rejection is not None:
            label = output.rejection.replace("_", " ")
            raise StrategyParseError(
                f"Request rejected: {label}. Currently supported: long-only RSI"
            )
        assert output.configuration is not None
        configuration = output.configuration.validated_config()
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
