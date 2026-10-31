# Visual Report Contract — Proposal for Review

Baseline: main `54f557e313b728e60ccf247fc06564551dc58a12`, package 1.2.2.
[Task 22](https://app.notion.com/p/3fccab7562dc8133a28cc3106ceed08a) authorizes this
audit/design increment, not runtime implementation. The task's old v1.2.0 milestone
label does not assign the visualization release version. The
[data audit](VISUAL_REPORT_DATA_AUDIT.md) inventories exact native fields, units,
missing series and adapter boundaries for all six modes.

Everything described below is **proposed**, including the examples. HTML is not a
supported output format at the baseline. Review this contract before implementation
or chart-library selection. This documentation changes no runtime, schema, version,
dependency, lockfile, calculation or published artifact.

## Smallest useful first implementation

Add one fully offline, static HTML presentation of the existing `ResearchReport`
evidence for all six research modes. Use Python's standard library to generate
escaped HTML, fixed CSS and small inline SVG bar charts; add no charting dependency.
Keep the validated evidence as the only numerical authority. Do not rerun a parser,
backtest, indicator, data provider or report AI request during HTML rendering.

The first delivery includes:

1. Source/provenance header, requested and actual UTC segment boundaries, strategy/
   configuration and execution assumptions, all scalar metrics with units, existing
   observations, limitations, warnings and explicitly unverified source notes.
2. Per-segment grouped bars for strategy net return and nullable net Buy & Hold
   return, plus separately labeled scalar maximum-drawdown bars. A drawdown bar is
   a summary, never a path. Group validation Train/Test independently; label
   sensitivity and cost results Train-only; Walk-Forward rows retain fold/strategy
   scope IDs, independent Test return/benchmark bars and summary tables.
3. Scenario Train return-difference bars in pp and separate modeled cost-component
   bars in quote currency when those metrics exist. Preserve the declared baseline;
   no sorting to select a winner or new performance score.
4. A visible capability table: what this input can support, what is deferred by the
   renderer, and what the source lacks. Always include accessible numeric tables;
   charts supplement the evidence instead of hiding negative or undefined values.

Use the metric `scope`/`name`/`unit` records and scope boundaries identified in the
audit. No 2D heatmap, fold timeline or stitched-index plot is required for this first
delivery. These have separately useful follow-up commits below. Equity, drawdown
paths and benchmark paths remain unavailable for current saved results.

## Proposed Python and CLI interfaces

Extend the existing `ReportFormat` to `Literal["markdown", "json", "html"]` without
changing defaults, argument order, return type (`str`) or JSON/Markdown behavior:

```python
# Proposed future interfaces; not runnable on the audited baseline.
html_text = client.report(result, format="html")
client.report(result, format="html", output="research.html")
result.save_report("research-copy.html", format="html")
html_async = await client.areport(result, format="html")

# A saved native result, including the original direct-AI source envelope:
client.report("saved-backtest.json", format="html", output="saved-report.html")

# A typed normalized report has scalar evidence, not native grid layout:
client.report(normalized_report, format="html", output="evidence.html")
```

```bash
# Proposed future CLI; rendering never executes research.
strategy-backtest report --input saved-result.json --format html --output research.html
strategy-backtest report --input saved-result.json --format html > research.html
```

The `--output` path must use the existing safe no-overwrite writer. Shell redirection
is controlled by the shell and can overwrite files; it does not receive that
guarantee. Without `--output`, stdout contains only HTML; diagnostics go to stderr.
No browser is opened, no local server starts and no companion directory is created.
Output filenames never derive from strategy names, prompts or symbols.

For this offline increment, `format="html", ai=True` and `--format html --ai` reject
before interpretation or writes (`BacktestClientError` / CLI exit 2). Existing
Markdown/JSON AI behavior is unchanged. A supplied typed `ResearchReport` may already
contain AI interpretation: render it as escaped, separately labeled source content
with its existing status/model metadata; do not call AI or claim byte reproducibility
of an earlier AI request. Repeated rendering of the same supplied report is deterministic.

Native input support follows the existing adapters: complete single-backtest CLI
JSON or AI envelope, comparison, validation, sensitivity, costs and Walk-Forward;
equivalent accepted typed models/mappings and `ClientResult` use the existing client
loading rules. Preserve original source bytes for `ClientResult` and file inputs.
Do not add filename heuristics, arbitrary native schemas or multi-file aggregation.
A bare engine `BacktestResult` remains insufficient. A path containing normalized
`ResearchReport` JSON remains unsupported in this first increment, matching current
CLI/path behavior; a typed `ResearchReport` is supported through Python. A future
explicit normalized-file adapter is separate scope.

## Input validation and chart availability

Native inputs keep the existing bounded reader, strict JSON adapters and
`check_research` consistency checks. Typed normalized reports must be revalidated
for HTML, including bounded strings/collections, finite values, unique metric/scope
IDs, valid metric references, supported units, chronological scope boundaries and
canonical evidence-hash agreement. This must not pretend to verify native accounting
or original prices when the native source is absent. Point scopes legitimately
have equal start/end; absent optional boundaries remain absent.

| Input/data condition | Required behavior |
| --- | --- |
| Full accepted current native result or AI envelope | Scalar HTML tables/charts; original source hashes and paths retained |
| Accepted tagged v0.8/v0.9 legacy result | Same available scalar presentation; absent historical metadata labeled unavailable, never fabricated |
| Typed normalized `ResearchReport` only | Evidence tables/scalar charts; no invented raw fields or resolved grid coordinates |
| Benchmark/profit factor/win rate/excess return null | Display `N/A (undefined)`; omit corresponding mark with explanation; never zero, infinity or a hidden row |
| Genuine zero or negative metric | Plot against explicit zero baseline; retain sign/value and applicable units |
| No public equity/drawdown/benchmark series | Capability row explains missing retained series; no fabricated curve and no renderer-triggered rerun |
| Sensitivity 3D or missing native layout in a later chart stage | Variant table and clear unsupported-layout reason; no projection, slicing, averaging or winner selection |
| Invalid, truncated, duplicate-key or contradictory native result | Existing sanitized API failure / CLI exit 2; no partial published output |
| Valid input but no marks for a panel | Keep a table/reason, exit successfully; do not treat missing optional data as corruption |

A missing layout in a normalized-only report is different from a native 2D result
whose required matrix contradicts its grid. The latter still fails the existing
consistency checks; fallback must not weaken native validation.

Units stay explicit: returns and scalar drawdown `%`; return differences `pp`;
fee rate `fraction`; spread/slippage `bps`; balances and cost attribution
`quote_currency`; trade totals `count`; profit factor `ratio`; endpoint values
`index`. Do not invent a currency ticker, dollar symbol, annualization or normalized
duration. A percentage-point difference must not share an unlabeled % axis.

## Fully offline assets and injection boundary

Produce a single UTF-8 HTML file with fixed embedded CSS and inline SVG. Use system
fonts. No CDN, JavaScript, web fonts, remote images, external stylesheets, hyperlinks
derived from input, network requests, telemetry, iframe, plugin or executable payload
is needed. The page must render with scripting disabled and the network unavailable.
SVG elements/attributes come from a renderer-owned allowlist; there is no arbitrary
SVG, HTML, CSS or Markdown-to-HTML passthrough.

Escape every source-derived string with context-appropriate HTML/XML escaping,
including labels, names, rules, provenance, source notes, AI text, titles and
accessibility attributes. Do not embed raw source JSON or source text inside a
`script`, `style`, URL, event handler, CSS selector or element ID. Render explanatory
JSON only as escaped text in a `pre` element when necessary; do not include the
original AI prompt by default. Use renderer-generated sequential IDs and a fixed
palette/classes. Only checked finite numbers can produce SVG coordinates; strings
and user-defined colors never become markup or CSS. Escape quotes in attributes.
Existing Markdown escaping is not a general HTML sanitizer and must not be reused
as a substitute for context-appropriate escaping.

Emit a meta Content Security Policy before rendered content: `default-src 'none'`,
`script-src 'none'`, `connect-src 'none'`, `object-src 'none'`, `base-uri 'none'`,
`form-action 'none'`, with `style-src` allowing only the hash of the renderer's fixed
embedded stylesheet. No inline style attributes or `unsafe-inline`/`unsafe-eval`.
Escaping and allowlists are the primary defenses; CSP is additional containment.
Reject active content instead of depending on browser policy to neutralize it.

Each chart has an accessible name/description, units, legend and adjacent data
table. Positive/negative/null/low-trade distinctions cannot rely on color alone.
Long names wrap as text and cannot create navigation or break document structure.

## Determinism, provenance and safe output

For identical input bytes, renderer version and options, HTML bytes must match on
repeated rendering. Use stable source/scope order, renderer-generated IDs, fixed
numeric formatting, UTC date formatting, fixed palette/layout and LF newlines. Do
not insert wall-clock time, host paths, filenames, random IDs, locale-sensitive
numbers or filesystem metadata. Temporary writer UUIDs never enter the HTML.
Different source envelopes or whitespace may change source hashes and therefore
HTML bytes; compare financial metrics rather than whole reports across those inputs.

Bound each SVG to 25 segment groups, splitting larger inputs into deterministic
consecutive panels without omitting table rows or scopes. Cap encoded HTML at
64 MiB and fail before publication if exceeded; keep the current, smaller native
input bounds. Include boundary/overflow cases in acceptance rather than silently
truncating labels, metrics or points.

Expose an HTML renderer identifier such as `visual-html/1` in HTML metadata, separate
from unchanged report schema `1.0` / generator `research-reports/1`. Existing source,
canonical-input and evidence hashes retain their meanings; do not rewrite evidence
to add chart configuration. Rendering to HTML does not change JSON output bytes.

Reuse [write_new](../src/strategy_backtest_agent/reports/cli.py) for all file output:
POSIX safe traversal, exclusive temporary file, flush/fsync and atomic no-overwrite
publication. Preserve rejection of `..`, symlink parents/destinations, existing
files/directories and destination-creation races. Failed validation must not publish
an HTML file. Retain the writer's current platform limits and parent-directory
creation behavior; do not add a weaker Windows fallback in this increment.

## Later chart stages that need no public schema extension

These can reuse validated saved native data. They are separable from the first
renderer and do not require a chart library:

- Walk-Forward: timeline rectangles at exact Train/Test UTC boundaries, fold-return
  bars, separate summary statistics. Gaps remain visible. Optional index **points**
  use only stored `stitched_oos_index`, labeled “Independent Test fold-endpoint index,
  base 100”; no continuous equity line, interpolation or OOS drawdown calculation.
- Sensitivity: 1D candidate markers and a 2D heatmap from the validated native
  `ordered_series`/`matrix`. Preserve declared axis order, variant joins, coupled-path
  labels, parameter-specific units, trade-count badges and Train-only warnings.
  Use a zero-centered scale with a stated domain; never hide losing/zero-trade cells.
  Three-dimensional input remains a table until a slice contract is reviewed.
- Native chart layout can be an internal, nonserialized projection produced during
  the existing parse/adapt/check pipeline. Reuse that validated content without
  rereading files, fetching data or rebuilding reports. Keep numbers linked to
  evidence metric IDs/source paths; no scalar recalculation. Do not add unchecked
  raw JSON access inside the HTML renderer. Typed normalized reports lacking native
  layout fall back explicitly. A public normalized layout extension would need
  separate schema/version review; it is not necessary for these native-input charts.

## Future engine-series contract required for actual curves

No engine extension is needed for the first renderer. True equity/drawdown and
benchmark curves are blocked on a separately reviewed retained-series design:

1. Capture the existing engine's actual initial/open/close equity marks in order,
   without changing signals, fills, accounting, warm-up or sampled drawdown. Preserve
   the existing final open mark before liquidation and close mark after liquidation;
   do not add an artificial pre-liquidation close sample. Every point needs
   an explicit phase/sequence and candle-open UTC anchor; do not assign open and
   close marks the same unlabeled time or imply an intrabar path.
2. Define series schema version, valuation/sampling policy, segment/strategy/fold
   identity, quote-currency unit, initial/final balance association, evaluation
   boundaries, source-result digest and optional candle digest. Capture only
   evaluation samples, never warm-up performance. Validate finite nonnegative
   values, order/counts, initial/final agreement and sampled max-drawdown parity.
   Drawdown percentages may be derived only from this retained, validated sequence
   with the existing running-peak convention, never trades/scalars.
3. A benchmark path needs engine-produced marks with the same cost/sampling policy
   and final net benchmark return; scalar benchmark returns alone are insufficient.
   Null/absent benchmark series is explicit. Keep each fold/segment's portfolio
   separate and preserve capital resets. No renderer-generated continuous portfolio.
4. Prefer an opt-in, separately versioned series artifact associated with unchanged
   native result bytes, rather than adding fields unconditionally to current JSON.
   Current strict models/adapters forbid unknown fields: merely making a new field
   optional in a new reader would **not** make new output readable by old clients.
   Old inputs must remain accepted with curves unavailable, and default old-shaped
   exports must remain usable by old readers. A wrapper/sidecar, API for obtaining
   it, atomic multi-file behavior and adapter version require review before coding.
5. Define explicit series/input/output size limits and an opt-in capture budget;
   do not silently downsample points used for drawdown. First scope any implementation
   to one backtest; multi-mode capture and benchmark capture are independent later
   work. Do not add large arrays to report evidence or change hashes implicitly.

This is a proposed compatibility direction, not a fully approved extension schema.
Raw-candle imports, continuous OOS portfolios, animation, interactive JavaScript,
PDF/image exports and new data/chart dependencies are outside the first increment.

## Concrete acceptance checks for implementation

| Area | Required evidence |
| --- | --- |
| Six-mode semantics | Synthetic fixtures for all six native result types plus direct-AI single envelope; chart values, scope IDs, units and source paths match validated evidence; financial outputs unchanged |
| Legacy and capability behavior | Existing tagged v0.8/v0.9 inputs, missing legacy initialization fields, typed normalized reports, absent series, null benchmark/profit factor/win rate, zero trades, all-negative and constant values; precise table/reason fallback |
| Interfaces | Sync/async Python, `save_report`, native saved-source CLI/stdout and `--output`; unchanged defaults and Markdown/JSON byte snapshots; HTML+AI request rejects before any AI call/write |
| Security | Adversarial names/notes/AI text containing script terminators, quotes, HTML/SVG event attributes, `javascript:`/data URLs, CSS and Unicode controls remain text or reject safely; parse generated DOM to assert no executable/resource-loading nodes or attributes |
| Offline and browser behavior | Socket guard for application rendering; browser network request interception denies all requests except loading the local document; zero external requests, no scripts, CSP present; review fixed synthetic desktop/narrow/print screenshots in a pinned browser/font environment |
| Determinism and provenance | Repeated HTML bytes match for identical source bytes/options; direct and saved-source output match when bytes match; separate-envelope tests compare values, not hashes; source/evidence hashes unchanged |
| Output safety | Existing-file/directory/symlink/traversal/race/fsync-failure cases through the shared writer; no overwritten or partial destination; no raw prompt/credential leakage in diagnostics |
| Later native charts | 1D, unsorted 2D, coupled paths, degenerate axis, 3D fallback and low/zero trades; rolling/expanding folds, gapped Tests and optional index absence/presence; exact axis mapping and no inferred performance |
| Future curves, only after extension review | Retained sequence vs existing metric parity, gaps/phase ordering, final forced exits, no trades, costs, UTC offsets, zero equity, bounds and old/new reader/export compatibility; reject mismatched source digest or invented series |

Browser/screenshot tooling may be development-only after review; do not introduce a
runtime chart dependency to execute acceptance. Browser checks are future acceptance,
not tests run by this audit. Implementation must run focused regressions and the
normal quality/packaging gates appropriate to its actual changes.

## Logical implementation commits and review boundaries

1. **Static HTML renderer and its contract tests:** evidence-only HTML/CSS/SVG,
   scalar panels, tables, capability explanations, escaping/CSP, deterministic
   fixtures and malformed/hostile-input coverage. No engine or report-schema change.
2. **Public HTML integration:** Python format/async/save and CLI dispatch, shared
   safe writer, interface/no-overwrite regressions, customer docs and isolated
   installed HTML smoke. Keep tests necessary for each public behavior in this
   commit; reuse the renderer from commit 1.
3. **Walk-Forward native panels:** fold timelines and optional endpoint points,
   methodology labels and independent-portfolio/gap fixtures with visual review.
4. **Sensitivity native layout projection and charts:** reuse validated native
   content, 1D/2D plots and exact coordinate/ID/low-trade tests; normalized-only and
   3D fallback. No public schema changes or new financial calculations.
5. **Separate later proposal:** retained equity/benchmark series schema, compatibility
   and budgets. Review it before engine capture; then commit capture with parity
   tests, versioned serialization/adapters and curve rendering in independently
   buildable units. Do not fold this into the first HTML delivery.

Each commit must be independently reviewable/buildable; combine a necessary internal
projection with its consumer if separation would leave an unusable API. Review and
authorize the first implementation scope from this contract; future release numbering
and any public series/schema extension remain separate decisions. No merge, version
bump, tag or publication is authorized by this audit.
