# Contributing

Use Python 3.12+ and Poetry 2.x. Source checkout and Poetry are for development;
customers should install the published `strategy-backtest-agent` distribution with
pip as described in the [Quick Start](docs/QUICK_START.md). To work on this repository:

```bash
git clone https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent
poetry install
poetry run strategy-backtest --demo
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

AI coding agents follow the same rules, summarized in [AGENTS.md](AGENTS.md)
(Claude Code reads it through [CLAUDE.md](CLAUDE.md)).

Work on a branch from current `main`. Make one logical change per commit, about 200
changed lines at most (lock files excluded), with its tests in the same commit; every
commit passes all checks. Write messages as Conventional Commits:
`type(scope): subject`, imperative, lowercase, at most 72 characters, for example
`fix(reports): escape the footer renderer version`. Never mix a refactor and a
feature. Describe the problem, resulting behavior and validation in the branch's
review notes. Add deterministic tests for meaningful behavior changes. Unit tests
must not access the network; use mocked provider responses. Preserve next-candle
execution and mathematical consistency between fees, PnL, and portfolio balances.

Keep providers separate from the engine and add useful public type hints. Update
README commands when behavior changes. Commit poetry.lock with dependency changes.
Never commit credentials, local environment files, caches, or generated artifacts.
AI tests must mock the OpenAI boundary and run without an API key. Keep SDK imports
inside the AI package; parsing must never calculate financial results. Discuss larger
features in an issue before implementation.
