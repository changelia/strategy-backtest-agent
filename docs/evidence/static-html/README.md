# Static HTML verification evidence

Unreleased source implementation against reviewed main
`7c8103ba56343792a5d5312f8abae950280cb4c5`. Package metadata remains 1.2.2;
these local archives contain unreleased HTML and **are not published PyPI 1.2.2**.
Engine calculations, public report schemas, runtime dependencies and lockfile remain
unchanged. No paid OpenAI or live Binance request was made. Notion was read only.

## Functional and compatibility checks

| Exact command | Final result |
| --- | --- |
| `poetry run pytest -q tests/test_report_html.py tests/test_html_interfaces.py` | 72 passed after LF regression |
| `poetry run pytest -q tests/test_html_interfaces.py tests/test_report_html.py tests/test_report_markdown.py tests/test_report_version_compatibility.py` | 122 passed before the two later presentation regressions |
| `poetry run pytest -q tests/test_html_interfaces.py tests/test_public_client.py tests/test_report_security.py` | 100 passed |
| `poetry run pytest -q tests/test_installed_smoke.py tests/test_packaging_ci.py` | 30 passed |
| `poetry run pytest -q` | **1504 passed in 9.16s** |
| `poetry run ruff check .` | All checks passed |
| `poetry run ruff format --check .` | 131 files already formatted |
| `poetry run mypy` | No issues in 125 source files |
| `poetry check --lock` | All set! |
| `git diff --check` | Passed |

Existing Markdown snapshots and pinned JSON hashes remain unchanged. Tests cover all
six modes, both tagged v0.8/v0.9 legacy sets, an original direct-AI envelope, typed
normalized reports, strict structural/hash/reference/unit checks, numeric agreement,
null/zero/negative/constant/extreme values, long/hostile labels, chart splitting and
input/output bounds. HTML+AI rejection precedes source reads/interpretation/writes.
Sync/async/save, direct/saved-source bytes, CLI stdout/files, symlink/traversal/race/
fsync failures and no partial publication are covered. Source CRLF is displayed as
LF without changing evidence or source hashes.

Both new complete README/Python-guide examples were executed in fresh directories
outside the checkout under a socket-denying audit hook. They saved raw JSON, generated
HTML, compared direct/saved output and printed local paths/URLs. The examples never
opened a browser. Customer installation commands remain unpinned.

## Browser and visual inspection

[Machine receipt](browser-receipt.json) records Chromium **156.0.8078.4**, Playwright
**1.64.1**, macOS **26.7**/darwin, headless execution and system-ui/sans-serif. Node **24.22.1**
was used; system Node 17 could not run this Playwright. Browser tooling was already
installed outside this repository and is development-only; no dependency was added.

The 24 successful cases are all six modes plus two synthetic typed-report edge
fixtures, each in desktop 1440×1000, narrow 390×844 and print-media 1440×1000, at
scale factor 1, en-US locale and UTC. JavaScript is disabled and service workers are
blocked. Routing denies any request outside the fixture document directory, and a
request listener independently records attempts. **External requests: 0. Page/CSP
errors: 0. Horizontal document/provenance-label overflow: 0.** The fixed stylesheet
was applied in all cases. A4 print-to-PDF succeeded (366,506 bytes); the PDF stays in
the temporary fixture directory. Print screenshots show Chromium print CSS, not a
rasterization of every physical PDF page.

Inspected screenshots include:

- [Desktop provenance](comparison-desktop.png) and [return/benchmark chart](comparison-desktop-charts.png).
- [Narrow overview](comparison-narrow.png), [chart/value table](comparison-narrow-charts.png)
  and [horizontally scrolled marks](comparison-narrow-marks.png).
- [Print overview](comparison-print.png) and [print charts/tables](comparison-print-charts.png).
- [Scenario differences](costs-desktop-charts.png) and [cost components](costs-components.png).
- [Hostile/long-label narrow fixture](edge-narrow-label.png), with markup retained as
  text, plus its [chart](edge-narrow-charts.png) and [marks](edge-narrow-marks.png).

An initial visual pass revealed overlapping long provenance keys and an unclear
mobile chart-scroll affordance. Those were corrected with wrapping, explicit scroll
instructions and adjacent exact-value tables; final images/receipt describe the
corrected output. Narrow charts intentionally scroll horizontally to preserve legible
SVG text; numeric tables wrap and remain complete. Screenshot hashes and HTML hashes
are in the receipt. Browser HTML hashes for all six modes match the fresh **installed**
wheel/sdist HTML hashes in [the installed receipt](installed-receipt.json).

Reproduce using fresh paths and an already installed Playwright 1.64.1 / matching
Chromium, with Node 20+ (this run used 24.22.1):

```bash
poetry run python tests/html_browser_fixtures.py --work /private/tmp/sba-html-browser-verification
/private/tmp/node-v24.22.1-darwin-arm64/bin/node tests/html_browser_smoke.mjs \
  /Users/levanchangelia/projects/strategy-backtest/strategy-backtest-ui/node_modules/.pnpm/playwright@1.64.1/node_modules/playwright \
  /private/tmp/sba-html-browser-verification docs/evidence/static-html
```

The absolute tooling path above is local execution evidence, not a runtime dependency.
Supply your installed development Playwright module path when reproducing. Fixture
creation refuses a nonempty directory; use a new path. Browser receipt and screenshots
are deliberately regenerated by the opt-in browser helper, not ordinary pytest.

## Fresh isolated distribution validation

Final command:

```bash
/private/tmp/sba-direct-dsl-tools/bin/python tests/packaging_ci.py \
  --checkout /Users/levanchangelia/projects/strategy-backtest/strategy-backtest-agent \
  --work /private/tmp/sba-static-html-final-packaging
```

Exited **0**, `Packaging validation READY: both isolated installs and offline reports
match.` The existing orchestrator built fresh wheel/sdist with an isolated backend,
ran `python -m twine check --strict` on both, inspected archives and installed each
into separate clean environments. It verified archive URL/hash import provenance and
`pip check` (`No broken requirements found.`). Application sockets are denied before
imports; both receipts report **zero application network attempts**.

Installed HTML checks run outside the checkout and cover all six saved native
fixtures, typed reports, report/areport, API files and CLI stdout, repeatability,
no-overwrite and HTML+AI rejection. The direct DSL probe mocks only the parser with
the complete customer config and checks sync/async execution, explicit-config parity,
UTC boundaries, the original source envelope and direct/saved HTML/JSON/Markdown.
Wheel/sdist outputs match. Both installed distributions report version **1.2.2**.

| Final local archive | SHA256 |
| --- | --- |
| `strategy_backtest_agent-1.2.2-py3-none-any.whl` | `482519df6b8bb9733f87c9e4b2de8fd80f94f6cd03760acd9ad29720fac1bd60` |
| `strategy_backtest_agent-1.2.2.tar.gz` | `46cbbd366fcd5796711bae4197531af0fb764108ccdff347f1959d271afffece` |

The first successful packaging run remains at `/private/tmp/sba-static-html-packaging`.
It was superseded by the fresh final run after the LF-normalization regression fix;
its archives were not reused. Build/install downloads were explicitly permitted;
application execution remained offline. Logs, full installation receipts and artifacts
remain outside Git; [the compact receipt](installed-receipt.json) preserves relevant
version/hash/HTML/network evidence here without credentials or environment dumps.

## Limits and remaining scope

No equity/drawdown/benchmark series, heatmap, fold timeline or index plot was added.
Existing endpoint index values remain tables, never a continuous portfolio. Typed
report checks cannot authenticate prices or native accounting without native data.
HTML is capped at 64 MiB, normalized input at 16 MiB with node/depth/string bounds,
and each SVG at 25 scope groups; no evidence rows are silently dropped. Existing
POSIX writer limits remain. Browser coverage is one fixed Chromium on macOS, not a
cross-browser/OS matrix; screenshot pixel identity is not promised across platforms.
No merge, version bump, tag, publication or live provider acceptance is claimed.
