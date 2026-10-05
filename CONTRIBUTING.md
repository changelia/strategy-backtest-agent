# Contributing

Use Python 3.12+ and Poetry 2.x. Clone the repository, then run:

```bash
poetry install
poetry run strategy-backtest --demo
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

Keep changes small and describe the problem, resulting behavior, and validation in
pull requests. Add deterministic tests for meaningful behavior changes. Unit tests
must not access the network; use mocked provider responses. Preserve next-candle
execution and mathematical consistency between fees, PnL, and portfolio balances.

Keep providers separate from the engine and add useful public type hints. Update
README commands when behavior changes. Commit poetry.lock with dependency changes.
Never commit credentials, local environment files, caches, or generated artifacts.
AI tests must mock the OpenAI boundary and run without an API key. Keep SDK imports
inside the AI package; parsing must never calculate financial results. Discuss larger
features in an issue before implementation.
