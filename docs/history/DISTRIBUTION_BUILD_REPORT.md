# Wheel and source distribution verification — Task #15

Status: READY for Task #16 installation verification, not for publication.

## Scope and changes

Continued `feat/pypi-packaging` from audit commit
`362869d8e77b54edcc75e096cd0e29302f534fd3`; [Task #14](PYPI_PACKAGING_AUDIT.md)
remains intact. No applicable `AGENTS.md` was found. The Notion task was read only.

- `pyproject.toml`: retain explicit runtime-package discovery; add independent
  secret/cache/venv/build exclusions and a single sdist-only `.env.example` include.
- `tests/distribution_check.py`: standalone artifact inspector, reading archives
  rather than the existing editable installation; compare runtime paths/content,
  legal files, metadata and entry points against this checkout's 1.0.0 contract.
- `tests/test_distributions.py`: 71 offline archive-validation cases, including
  positive resources, missing/changed files, incorrect/duplicate metadata, developer
  dependencies, invalid entry points, links, duplicate paths and traversal.
- This report records build commands, evidence and remaining installation work.

Names, import path, **version 1.0.0**, MIT license, author metadata, runtime/dev
requirements, lock file, CLI behavior and historical calculations are unchanged.
The original research files, dotenv files and other worktrees were preserved.
No application install, publishing, CI change, init/doctor or Quick Start expansion
was performed. Build/twine were installed only into a temporary tooling venv.

## Content policy

Both formats contain all **57 runtime files**, with byte-for-byte source matches.
The wheel contains **62 files**: runtime modules plus METADATA, WHEEL, RECORD,
entry_points.txt and `strategy_backtest_agent-1.0.0.dist-info/licenses/LICENSE`.
The sdist contains **62 files** beneath `strategy_backtest_agent-1.0.0/`: runtime
sources under `src/`, README.md, LICENSE, pyproject.toml, PKG-INFO and `.env.example`.

Repository examples, tests/fixtures, audit documents, development tools and the
Poetry lock file are intentionally omitted from the minimal sdist. They are not
needed to build a wheel. No broad repository include or blanket JSON/Markdown
exclude was added. Future legitimate runtime resources remain eligible.

The root `.env.example` is the tracked harmless placeholder template; actual
`.env`, `.env.*`, `.envrc` and `.pypirc` files are excluded. Explicit exclusions
also cover bytecode, caches, virtualenvs, egg-info, nested build/dist directories,
Git data and OS metadata, independently of Git ignores. Inclusion precedence is
used only for the exact root template in the sdist. All actual local research
outputs are outside the selected package and absent from both archives.

These are manifest/content checks, not a claim that arbitrary source strings can
be automatically proved secret-free. No credential values were printed or used
as fixtures. Dependencies are declared in metadata, not bundled into the archives.

## Tools and exact commands

Checked on 2026-10-18, macOS / CPython **3.12.3**. Poetry **2.1.4** remains the
project manager. Temporary tools: pip **24.0**, build **1.6.1**, twine **7.0.0**,
packaging **26.3**. Each PEP 517 build used an isolated environment and resolved
**poetry-core 2.5.0**, recorded in verbose logs as an installed build dependency.
This differs from Poetry's own embedded backend and is not editable-app metadata.

From the repository root:

```bash
TASK15_WORKSPACE=/private/tmp/sba-task15-2bjaudwn
poetry run python -m venv "$TASK15_WORKSPACE/tools"
"$TASK15_WORKSPACE/tools/bin/python" -m pip install build twine
"$TASK15_WORKSPACE/tools/bin/python" -m build --sdist --wheel --verbose --outdir dist/task15
"$TASK15_WORKSPACE/tools/bin/python" -m twine check --strict \
  dist/task15/strategy_backtest_agent-1.0.0-py3-none-any.whl \
  dist/task15/strategy_backtest_agent-1.0.0.tar.gz \
  dist/task15/from-sdist/strategy_backtest_agent-1.0.0-py3-none-any.whl
"$TASK15_WORKSPACE/tools/bin/python" tests/distribution_check.py --project . \
  dist/task15/strategy_backtest_agent-1.0.0-py3-none-any.whl \
  dist/task15/strategy_backtest_agent-1.0.0.tar.gz \
  dist/task15/from-sdist/strategy_backtest_agent-1.0.0-py3-none-any.whl
```

The final two commands ran after the rebuild below. Build output, detailed file
inventories, SHA256 maps and tool logs remain in ignored `dist/task15/` or the
external temporary workspace; no generated artifacts/logs are committed.
The recorded tools/backend versions are observations, not new project pins.

## Artifact metadata and hashes

`twine check --strict` passed for **both direct artifacts and the rebuilt wheel**.
The inspector independently verified:

- Name `strategy-backtest-agent`; version `1.0.0`; Metadata-Version `2.4`.
- Requires-Python `>=3.12,<4.0`; wheel tag `py3-none-any`, purelib layout.
- Requires-Dist: `httpx (>=0.28,<0.29)`, `openai (>=3.24.0,<4.0.0)`,
  `pandas (>=2.2,<3.0)`, `pydantic (>=2.10,<3.0)`,
  `python-dotenv (>=1.2.4,<2.0.0)`. No development dependencies or extras.
- Console entry point `strategy-backtest = strategy_backtest_agent.cli:main`.
- `text/markdown` description with the exact UTF-8 README content.
- MIT metadata, `License-File: LICENSE`, and the exact existing license contents:
  root LICENSE in the sdist and dist-info/licenses/LICENSE in the wheel.

| Artifact (under `dist/task15/`) | SHA256 |
| --- | --- |
| `strategy_backtest_agent-1.0.0-py3-none-any.whl` | `a632e87bc80525876ae81f7d41ae7d50bb4d3fb371b8ccc0e2112222c4d11cc9` |
| `strategy_backtest_agent-1.0.0.tar.gz` | `fd3cb230a7db8105ff91429ebfeb1e5f74aabbe431033f1d41a6e51ae1e4707f` |
| `from-sdist/strategy_backtest_agent-1.0.0-py3-none-any.whl` | `a632e87bc80525876ae81f7d41ae7d50bb4d3fb371b8ccc0e2112222c4d11cc9` |

## Sdist-only rebuild and exclusion probes

After validating the sdist, it was extracted with Python tarfile's `filter="data"`
into `/private/tmp/sba-task15-2bjaudwn/sdist-source/`. The isolated rebuild ran with
that extracted source as the working directory, outside the repository:

```bash
TASK15_WORKSPACE=/private/tmp/sba-task15-2bjaudwn
TASK15_CHECKOUT=/Users/levanchangelia/projects/strategy-backtest-agent
cd "$TASK15_WORKSPACE/sdist-source/strategy_backtest_agent-1.0.0"
"$TASK15_WORKSPACE/tools/bin/python" -m build --wheel --verbose \
  --outdir "$TASK15_CHECKOUT/dist/task15/from-sdist"
```

It required only the sdist and declared build-backend requirements, not checkout-only
files. Direct wheel, sdist and rebuilt wheel have identical relevant metadata and
runtime-file SHA256 maps. Direct/rebuilt wheels also have identical member names,
payloads **and complete archive bytes** in this run (matching hashes above).
This measured result does not promise reproducibility across other tool versions,
platforms or future source changes.

For exclusion testing, a disposable copy was made using `git archive HEAD`, then
overlaid with the task's pyproject.toml. No actual untracked research or dotenv file
was copied. Twenty synthetic prohibited files were inserted at the root/inside the
package: dummy dotenv/credential files, research outputs, bytecode, caches, venv,
egg-info and nested build outputs. Two legitimate package resources,
`resources/probe.json` and `resources/probe.md`, were added as positive controls.
Both `.git` and `.gitignore` were absent in the final probe copy.

```bash
"$TASK15_WORKSPACE/tools/bin/python" -m build --sdist --wheel --verbose \
  --outdir "$TASK15_WORKSPACE/probe-without-gitignore" \
  "$TASK15_WORKSPACE/exclusion-probe"
"$TASK15_WORKSPACE/tools/bin/python" tests/distribution_check.py \
  --project "$TASK15_WORKSPACE/exclusion-probe" \
  "$TASK15_WORKSPACE/probe-without-gitignore/strategy_backtest_agent-1.0.0-py3-none-any.whl" \
  "$TASK15_WORKSPACE/probe-without-gitignore/strategy_backtest_agent-1.0.0.tar.gz"
```

Both probe archives excluded all prohibited paths/sentinel payloads and retained
both legitimate resources (59 runtime files). Synthetic probes never altered the
original checkout's package, research files, ignore file or credentials.

## Final quality checks

| Exact command | Final result |
| --- | --- |
| `poetry run pytest` | **1269 passed in 7.78s** (1198 existing + 71 packaging cases) |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 107 files already formatted |
| `poetry run mypy` | Passed; no issues in 106 source files |
| `poetry check --lock` | Passed; `All set!`, no lock regeneration required |
| `poetry run strategy-backtest --demo` | Passed; unchanged synthetic result: final 123.09 from 10000, -98.77%, 45 losing trades, net Buy & Hold +6.98%. |

## Remaining work for Task #16

Use a fresh environment outside the source tree to install the validated artifacts
and resolve dependencies. Verify installed name/version, import discovery, console
entry point, offline CLI/report workflows and dotenv precedence without relying on
this checkout's stale editable installation (Task #14 observed version 0.7.0).
No application installation or installed-CLI correctness is claimed here.

Python/OS coverage, repository-relative README examples, optional metadata polish
(author/URL information), packaging CI and publication authorization remain separate
work. POSIX report-output limitations and historical-research limitations are unchanged.
No live OpenAI/market-data request, publication, Notion status update, merge, push,
version bump, tag or release-credential modification was performed.
