# strategy-backtest-agent — instructions for AI coding agents

These rules apply to any AI agent (Claude Code, Codex, Cursor, ...) working on
this repository, and to the people who run them. When in doubt,
[CONTRIBUTING.md](CONTRIBUTING.md) wins for setup and checks, and
[ARCHITECTURE.md](ARCHITECTURE.md) wins for engine behavior.

## Read first

- [README.md](README.md): what the package does for users.
- [ARCHITECTURE.md](ARCHITECTURE.md): the design record for the engine, the rule
  language, every research mode and the reports.
- [docs/](docs/): user guides (`PYTHON_API.md`, `CLI.md`, `RESEARCH_GUIDE.md`) and
  design contracts such as `VISUAL_REPORT_CONTRACT.md`.

## Product rules (never break these)

1. This is a historical research tool. It never places orders, recommends
   investments or predicts returns, and no text may suggest it does.
2. Only the Python engine computes financial numbers (`backtester.py`,
   `execution.py`, `metrics.py`, `indicators.py`). Research modes, reports, the
   CLI and the client reuse it and never recalculate trades or metrics.
3. A signal on completed candle N executes at the open of candle N+1. The last
   signal of a segment cannot execute; an open position is closed at the
   segment's final close. Train, Test, folds, variants and scenarios never share
   cash, positions or signals.
4. Execution costs: fee per side, full bid/ask spread (half on each side),
   adverse slippage per side. Spread and slippage are already inside the fill
   prices; never deduct them a second time.
5. Indicator warm-up and seed policies are part of the results. Do not change a
   warm-up count, seed or the comparison/validation versus local-anchor policy
   without a new initialization-policy version and explicit approval.
6. Undefined is not zero: a null win rate, profit factor or benchmark stays null.
7. Result and report models are strict and forbid unknown fields. Adding,
   renaming or removing a field in saved JSON breaks existing readers, including
   `strategy-backtest-api`. Such a change needs a reviewed, versioned contract.
8. Reports read existing results only. They never fetch data or rerun research.
9. AI only parses requests and selects grounded explanations. It never
   calculates results, and no secret, prompt or raw provider response reaches
   output, logs or errors.
10. Do not add a runtime dependency without explicit approval.

## Every change

- Add tests with the change: the expected case, a rejected case and, for a fix,
  a regression test. Tests run offline: mock OpenAI and market data, never call
  live services.
- Run these and make all of them pass:

  ```bash
  poetry run pytest
  poetry run ruff check .
  poetry run ruff format --check .
  poetry run mypy
  ```

- Read each command's exit status. Never pipe a check through a command that
  hides it, such as `poetry run pytest | tail`. Use `set -o pipefail` or
  `poetry run pytest; echo "exit $?"`.
- A refactor must not change behavior. Show that demo output, report JSON,
  Markdown and HTML, and their hashes are byte-identical before and after.
- Never mix a refactor and a feature in one commit or one branch.
- Update the docs and `CHANGELOG.md` (Unreleased) when behavior, the public API,
  a CLI flag or the output changes. Examples in docs must be real output.
- Report honestly: list the checks you ran with their real results. Never claim
  a check passed if it did not run.
- Write code, comments, docs and commit messages in English.

## Commits and branches

- Work on a branch from current `main`, never on `main` itself.
- One logical change per commit, about 200 changed lines at most (lock files
  excluded). Tests go in the same commit. Every commit passes all checks.
- Conventional Commits: `type(scope): subject`, imperative, lowercase, at most
  72 characters. Types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`,
  `build`, `chore`, `perf`. Scopes: `engine`, `rules`, `data`, `research`,
  `reports`, `client`, `cli`, `ai`, `docs`, `ci`, `build`.
- No AI co-author trailers and no AI attribution lines in commits.
- Do not merge into `main`, tag, change the package version or publish. The
  maintainer does that.

## Code style

- Small functions with one job and descriptive names. Full type hints;
  `mypy --strict` must pass.
- Google-style docstrings on public functions and classes you add or change.
- Keep calculations pure. Network, files and the clock stay at the edges.
- User-facing errors say what happened, why, and how to fix it, without
  leaking secrets.
