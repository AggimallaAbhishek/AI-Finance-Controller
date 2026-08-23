# Changelog

## v2.1 — 2026-08-22

Frontend design and UX optimization only, per `project_plan_v2.1.md`
(Phases 13–16) — no new backend capability, no new data sources. Built
directly on the v2.0 `/impeccable` critique's findings (23/40 baseline),
not a fresh guess at what needed polish.

- **Information density**: the filter bar collapses behind a disclosure
  with an active-filter count instead of always showing 5 fields + 6
  chips; the run picker leads with date/match-rate/record-count instead
  of a truncated technical run ID; every confidence tier carries a
  hover legend explaining what it means for trust
- **Accessibility**: explicit `aria-label`s on every row's expand
  toggle (previously a concatenated run-on string); a full live
  keyboard-only pass caught and fixed a real keyboard trap in the
  counterpart picker (dropdown options were reachable via Tab and
  skipped past the Note field entirely)
- **Visual identity**: a provenance color palette (rule/LLM/human, one
  shared `tiers.js` source of truth) replaced a single undifferentiated
  accent color used everywhere; the stats header — literally a named
  "hero-metric template" anti-pattern — restructured into a single
  ledger-line statement; a self-hosted display serif (Fraunces, SIL
  OFL) for just the H1 and the match-rate figure. Re-verified via a
  full dual-agent `/impeccable critique` re-run: 23/40 → 27/40,
  catching and fixing two real regressions the first pass introduced
  (a CSS Grid overflow bug; a color-role collision between the new
  LLM-tier color and the existing action color)
- **Power-user efficiency**: sortable columns (amount/date, both
  directions) on both Exceptions and Matches; bulk "confirm no-match"
  for multiple selected exceptions via the *existing* resolve endpoint
  (no new backend capability) — verified precisely that a bulk action
  produces N independent audit-trail rows, never a merged one; keyboard
  shortcuts evaluated honestly rather than assumed (Escape-to-clear-
  selection shipped; broader shortcuts deliberately deferred as
  disproportionate to a stretch phase)
- A frontend test suite grown alongside every phase (Vitest, 46 tests
  by the end of this version, up from 0 before v2.0) and full
  backend/frontend regression checks after every change
- Two features deliberately evaluated and left undone, not silently
  dropped: cancelling an in-flight reconciliation job and true
  undo-after-resolve both need new backend capability outside this
  version's scope — documented as v2.2+ candidates
- **Final verification**: a post-close-out `/systematic-debugging` pass
  against a real 100-record run caught and fixed one last regression —
  `MatchList` rows missing the flex-shrink wrapper `ExceptionList` rows
  have, so the 10 LLM-reasoned matches (full generated-sentence reason
  text) overflowed the page horizontally instead of truncating

See `docs/BUILD-CHALLENGES.md` for full root-cause writeups of every
bug found this version, and `.impeccable/critique/` for both critique
snapshots.

## v2.0 — 2026-08-22

Human-in-the-loop review, a richer dashboard, new data-ingestion paths,
and backend/frontend test coverage, per `project_plan_v2.md` (Phases
9–12). Auth, multi-tenant, and horizontal scaling stayed explicitly out
of scope.

- Real `pytest` suite (82 tests) covering the matching engine, audit
  trail, LLM parsing/retry logic, and every API endpoint; retry/backoff
  on transient Ollama failures instead of an avoidable exception;
  configurable rule tolerances via environment variables
- Human-in-the-loop exception resolution: confirm a no-match or link a
  counterpart from the dashboard, recorded as a `tier: human` audit
  entry exactly as traceable as a rule or LLM decision — never mutating
  the original algorithmic verdict, only adding to the history
- Richer dashboard: a Matches tab alongside Exceptions, run history with
  a match-rate trend chart, a shared amount/date/side/tier filter bar,
  CSV export, and a "Run reconciliation" button with real staged
  progress instead of a bare spinner
- New data-ingestion paths: a Razorpay Settlements API loader (code-
  complete and unit-tested against Razorpay's real, observed API
  contract — verified without credentials; live verification remains
  blocked on getting real ones), a cron-friendly scheduled-reconciliation
  script with a match-rate-delta digest, and — added mid-version on
  request — a dashboard "Upload & Run" tab so a user can reconcile their
  own CSVs from the browser, fully verified live
- A two-assessment `/impeccable` design critique (23/40 → all 5 priority
  issues fixed and verified live): WCAG-AA contrast across every primary
  button, a free-text counterpart-ID field replaced with a searchable
  picker sourced from real open exceptions, previously-hidden match/
  exception reasoning text now fully readable, a resolve confirmation
  state, and a mobile layout fix
- A frontend test suite (Vitest, previously zero coverage) at three
  agreed seams, including regression guards for two real bugs found and
  fixed this version
- Full systematic-debugging passes across the new backend and frontend
  work; findings fixed and logged (`docs/BUILD-CHALLENGES.md`,
  `docs/ADR-002-razorpay-settlements-integration.md`)

See `project_plan_v2.1.md` for planned frontend design/UX work beyond
v2.0.

## v1.0 — 2026-08-22

Initial build, per `project_plan.md` (Phases 0–8). Hackathon-submission
complete.

- Synthetic settlement/bank data generator with a dev-only ground-truth
  answer key for validation
- Hybrid reconciliation engine: deterministic rule tiers (exact, fuzzy-date,
  fuzzy-amount) plus an Ollama-reasoned tier for the ambiguous middle
- SQLite audit trail, queryable by record ID, tracing every decision to its
  source rows
- FastAPI backend: reconciliation, matches/exceptions/audit endpoints,
  free-form Q&A via Ollama tool-calling
- React dashboard: match-rate summary, browsable exception list, chat panel
- Validated 90% match rate / 66/66 ground-truth-correct on both the dev
  batch and an independent held-out batch (`docs/PHASE7-INTEGRATION-TEST.md`)
- Full architecture review and systematic-debugging passes; findings fixed
  and logged (`docs/BUILD-CHALLENGES.md`)

See `project_plan_v2.md` for planned features and improvements beyond v1.0.
