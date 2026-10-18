# Task #17 — CI packaging validation

**STATUS: LOCAL VALIDATION READY. Remote acceptance is pending** until the
reviewed commit passes both jobs in a GitHub Actions PR run targeting `main`.

## Scope and workflow

Continued `feat/pypi-packaging` from
`b41cb375a46f68551a4f51f66adbf7afc96c8e5e`. No tracked changes existed at the
start. No applicable `AGENTS.md` was found in the checkout or its ancestors.
Read the Task #14–16 reports and the Notion task; no Notion status was changed.

- `.github/workflows/ci.yml`: adds one independent `packaging` job on Ubuntu and
  Python 3.12. The existing `checks` job and push/PR triggers are unchanged.
  The new job's condition selects **pushes to main** and **PRs targeting main**;
  it is skipped for other push/PR events. No platform/version matrix is added.
- `tests/packaging_ci.py`: explicitly invoked build/validation/install orchestrator,
  reusing `distribution_check.validate`, `installed_smoke.smoke` and its sanitized
  environment. No production code or runtime dependencies changed.
- `tests/test_packaging_ci.py`: 14 offline regression cases covering blocked/failing
  receipts, absent formats, network attempts, cross-install output mismatches,
  incorrect archive URL/hash/editable provenance, external/fresh workspace safety
  and immediate propagation of a failed build before any installation.
- This report records local evidence and the remaining remote acceptance gate.

Permissions remain **`contents: read`**. Packaging checkout disables persisted Git
credentials. There are no secrets, release credentials, write permissions,
`pull_request_target`, publishing, OIDC or release steps. The new job has a
20-minute timeout. Bash uses explicit quoting and `set -euo pipefail`.

## Packaging sequence

The job creates a tooling venv under `$RUNNER_TEMP`, installs only build tooling
(`build twine packaging`), and creates a fresh workspace with `mktemp` beneath
that runner-provided directory. It invokes:

```bash
python -m venv "$RUNNER_TEMP/packaging-tools"
"$RUNNER_TEMP/packaging-tools/bin/python" -m pip install build twine packaging
packaging_work="$(mktemp -d "$RUNNER_TEMP/sba-packaging.XXXXXX")"
"$RUNNER_TEMP/packaging-tools/bin/python" tests/packaging_ci.py \
  --checkout "$GITHUB_WORKSPACE" --work "$packaging_work"
```

The helper:

1. Rejects workspaces inside the checkout or containing pre-existing files.
2. Builds fresh wheel and sdist from the current checkout with isolated PEP 517
   tooling. It accepts exactly one of each in the new output directory.
3. Runs `twine check --strict` on both, then the existing archive inspector against
   current source, README, license, project metadata, dependencies and entry point.
4. Creates independent wheel/sdist venvs without system site packages, confirms the
   package is initially absent, then installs with dependencies using each venv's
   Python. Pip receives `--no-cache-dir --use-pep517 --verbose --report`; source
   archive installation builds a project wheel without a cached project-wheel reuse.
5. Runs the existing installed smoke checks from fresh external working directories
   with explicit venv executables, no inherited Python overrides or credentials,
   dotenv disabled, and a temporary socket-denying startup guard. It checks import
   provenance, console target, `pip check`, help/demo/report-help, untouched demo
   JSON to repeated JSON/Markdown reports and malformed-input failure behavior.
6. Verifies each installation's direct archive URL and SHA256 against its newly
   generated artifact, not a fixed historical hash. Rejects BLOCKED receipts,
   failures, missing formats, network attempts or mismatching evidence/results.
   Compares actual demo/JSON/Markdown bytes across the two installations as well.

Subprocesses use checked exit statuses and timeouts. Any failed command, smoke
exception or validation mismatch terminates the job unsuccessfully; there is no
`continue-on-error` or unconditional success. Build/install logs, archive inventories,
pip reports and smoke receipts remain in the temporary workspace. Nothing uploads
or commits these files. This helper is not collected or run as an installation
check by ordinary pytest; its unit tests use synthetic receipts/mocked subprocesses.

## Local commands and evidence

Local host: macOS arm64, CPython **3.12.3**. Tooling venv:
`/private/tmp/sba-task15-2bjaudwn/tools` (build **1.6.1**, Twine **7.0.0**,
pip **24.0**, packaging **26.3**). The isolated backend resolved **poetry-core 2.5.0**.
No editable development installation executes the installed application checks.

Exact complete-sequence command:

```bash
/private/tmp/sba-task15-2bjaudwn/tools/bin/python tests/packaging_ci.py \
  --checkout /Users/levanchangelia/projects/strategy-backtest-agent \
  --work /private/tmp/sba-task17-ckifma0n/verified
```

These Mac paths are evidence only; the workflow/helper contains none of them.
The initial sandboxed attempt in `/private/tmp/sba-task17-ckifma0n` stopped at
backend download because DNS was restricted. The authorized network retry used
a new empty `verified` workspace. Application execution still denies network.
Original Task #15/16 artifacts are not used as inputs or replaced.

The successful workspace contains `artifacts/`, `wheel-env`, `sdist-env`,
`wheel-work`, `sdist-work`, command logs, archive inspection, pip installation
reports and two smoke receipts. The source-install log records isolated backend
installation and a successful fresh project wheel build. Installed versions are
`strategy-backtest-agent 1.0.0`; imports resolve under each environment's own
`lib/python3.12/site-packages/strategy_backtest_agent`, never checkout `src`.
The entry point remains `strategy_backtest_agent.cli:main`.

## Local sequence results

The complete orchestration command exited **0** with `Packaging validation READY`.
Both smoke receipts are **READY**, with empty report-failure maps. Both `pip check`
commands print `No broken requirements found.` Venv pip is **24.0**.

- Fresh wheel/sdist: strict metadata validation and archive inspection pass; each
  contains 62 files, including 57 runtime files. Required README/license/metadata
  and CLI entry point are correct; developer dependencies and prohibited contents
  are absent. The harmless sdist-only `.env.example` remains allowed.
- Both installed help, offline demo and report-help commands pass. The demo retains
  initial balance 10000, final balance 123.09493440255116, return
  -98.76905065597448%, 45 trades and zero winners.
- Untouched installed demo JSON generates valid JSON and non-empty Markdown
  (4614 bytes). Repeated outputs and cross-install demo/JSON/Markdown bytes match.
- Both malformed-input checks exit 2 with a useful error, no traceback, empty stdout
  and no echo of the synthetic private marker. No real credentials are supplied.
- Both socket audit logs record **zero application network attempts**. The original
  17 research files retain their hashes and `.env` retains its inode/size/mtime.

Measured hashes below describe this local run only; no hash is hardcoded as an
expected artifact value in the helper or workflow:

| Content | SHA256 |
| --- | --- |
| strategy_backtest_agent-1.0.0-py3-none-any.whl | `35610ab1d59bf853a4f40810e4fe7f2e69385967289f43fe07434ea1113c4a99` |
| strategy_backtest_agent-1.0.0.tar.gz | `8fa5cbc256b6acbd126295a710718b547fcb0c96ecd910137136462380554a9e` |
| JSON report | `52173551a777f1e15b19bfba9688b14a662eef79c4a3d4c5915c4b16ff933ea3` |
| Markdown report | `7ac0c7bcb02f4f5dd22ec542f8f6267b4fc11a92ba3e4a6dd37a3b4820373743` |
| Normalized evidence | `bbfe64bc4e91ebb17942501c4b11ca13bdc5f02ea6c9ad150cbcf0925cc47c48` |

## Quality and syntax checks

| Exact command | Result |
| --- | --- |
| `poetry run pytest -q` | **1303 passed in 8.18s** |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 112 files |
| `poetry run mypy` | Passed; 111 source files |
| `poetry check --lock` | Passed; `All set!` |
| `/private/tmp/sba-task17-actionlint/actionlint .github/workflows/ci.yml` | Passed; actionlint **1.7.12** |

Actionlint was downloaded only into a temporary directory from its official
GitHub release; its archive matched the published checksum. It validates workflow
syntax, expressions and action configuration. ShellCheck was unavailable locally;
no separate ShellCheck result is claimed. The workflow has not executed on GitHub.

## Remote acceptance: pending

No push or PR was created during this task. After separate authorization/review,
the owner can trigger the PR workflow with:

```bash
git push -u origin feat/pypi-packaging
gh pr create --base main --head feat/pypi-packaging \
  --title "ci: validate Python distributions and isolated CLI workflows" \
  --body "Adds read-only packaging checks using fresh artifacts and offline installed smoke tests."
gh pr checks <PR_NUMBER> --watch
gh run view <RUN_ID> --json headSha,status,conclusion,url,jobs
```

Verify the PR targets `main` and includes the reviewed commit; both `checks` and
`packaging` must conclude **success**, with packaging actually run rather than
skipped. Record the run URL, reviewed PR head and conclusions. Pull-request workflows
normally run against GitHub's generated merge ref; distinguish it from the PR head.
A later separately authorized push to main also triggers packaging. No merge is
required to verify the PR gate, and no repository setting change is part of this task.

Task #17 cannot be accepted solely from these local results. Ubuntu execution,
runner action integration and its network/dependency resolution remain unverified
until that remote run succeeds. Broader Python/OS coverage is outside scope. The
existing validators currently target package version 1.0.0 and will require review
when a future version bump is authorized. Build/runtime ranges resolve at execution
time, so the local resolver outcome is not a dependency-version matrix guarantee.
No trading calculations, package version/name, dependency policy, credentials,
local research files, `.env`, Notion status, publication or release automation changed.
