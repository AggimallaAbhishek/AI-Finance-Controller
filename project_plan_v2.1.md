# AI Finance Controller — Project Plan v2.1

**Status:** Complete — Phases 13–16 all done. See `CHANGELOG.md` for the v2.1 entry.
**Builds on:** v2.0 (`project_plan_v2.md`, Phases 9–12, complete — see `CHANGELOG.md`)
**Goal for this version:** frontend design and UX optimization only — no
new backend capability, no new data sources. v2.0 proved the feature set
works; v2.1 is about making the dashboard feel as considered as the
reconciliation logic underneath it.

---

## 1. What's changing from v2.0

v2.0 shipped real capability — human-in-the-loop resolution, a browsable
matches/exceptions dashboard, run history, CSV upload, a Razorpay loader
— and closed with a design-quality pass that fixed 5 concrete defects
(contrast, hidden reason text, a free-text ID field, a silent resolve,
a mobile overlap). That pass also produced a full `/impeccable critique`
report (23/40, "Acceptable" band) with findings deliberately left open
because they were scope, not bugs. v2.1 works that backlog:

1. **Information density & cognitive load** — the filter bar and run
   picker ask the user to process more than they need to, all the time.
2. **Accessibility & keyboard completeness** — the contrast fix closed
   one accessibility gap; a labeling gap and a full keyboard-only pass
   are still open.
3. **Purpose-built visual identity** — the critique's own verdict: the
   dashboard's content is genuinely reconciliation-specific, but its
   structure and visual language read as interchangeable with any B2B
   admin tool. This was explicitly deferred during the v2.0 critique
   rather than folded in unscoped.
4. **(Stretch) Power-user efficiency** — real batch sizes (60–100
   records) currently require one-row-at-a-time handling.

Source material for this plan is the persisted critique snapshot at
`.impeccable/critique/2026-08-22T08-33-56Z__frontend-src-app-jsx.md` —
every phase below traces to a specific finding in it, not a fresh
guess at what needs polish.

---

## 2. Phases

### Phase 13 — Information density & cognitive load — DONE

The critique's cognitive-load checklist failed on "chunking" and
"minimal choices": the filter bar shows 5 fields plus up to 6 tier
chips simultaneously, always expanded, on every visit to either list.

- Collapse the filter bar behind a disclosure (e.g. a "Filters" toggle
  showing only an active-filter count until opened) — `FilterBar.jsx`
- Reorder the run picker to lead with date + match rate + record count
  instead of a truncated technical run ID first (`RunPicker.jsx`) — the
  critique found this genuinely hard to scan with 15+ real runs mixed
  in from testing
- A legend or hover tooltip explaining what Exact / Fuzzy date / Fuzzy
  amount / LLM-reasoned / Human-resolved imply about trust level —
  currently nowhere in the UI
- Fix `StatsHeader`'s "By you" layout shift (renders only once
  `human_resolved > 0`, shifting everything else on first resolve)
- **Exit check, verified live:** the filter bar defaults to collapsed
  (opening automatically only when filters are already active), shows
  a "Filters (N)" badge and a live result count while collapsed, and
  "Clear filters" is reachable without expanding; the run picker leads
  with `{date} · {match%} · {record count} · #{short ref}` instead of
  the technical run_id; every tier badge and filter chip carries a
  `title` tooltip explaining what that tier means, sourced from one
  shared `tiers.js` module (previously duplicated between `FilterBar.jsx`
  and `MatchList.jsx`) so the legend can't drift between the two places
  it's shown; the "By you" stat always renders, no more layout shift on
  first resolve. Extended the Vitest suite (10 new tests: `countActiveFilters`,
  `formatRunOption`, `shortRunRef`) — 37/37 frontend, 82/82 backend.

### Phase 14 — Accessibility & keyboard completeness — DONE

The v2.0 pass closed the contrast failure (Sam persona, red flag #1)
but not the labeling gap (red flag #2), and heuristic 3 (User Control
and Freedom) still scores 2/4.

- The expand/collapse chevron in `exception-row__summary` is currently
  `aria-hidden`, relying on a long, unstructured concatenated accessible
  name (ID + amount + reason). Give it an explicit "Expand details" /
  "Collapse details" label.
- Full keyboard-only pass across the primary flow (browse → expand →
  resolve) and the newer surfaces the critique didn't specifically
  probe (Upload & Run tab, run picker, tab bar) — verify visible focus
  indicators at every step, not just the counterpart picker's existing
  combobox pattern.
- Evaluate — don't assume — what's feasible for heuristic 3's remaining
  gaps: cancel for an in-flight reconciliation job, and whether "undo"
  after a resolve means anything given the audit trail is intentionally
  append-only (an honest "no, and here's why" is an acceptable outcome
  of this evaluation, not a failure to close the gap).
- **Exit check:** the full browse → expand → resolve flow is completable
  keyboard-only with visible focus at every step; re-run the Sam persona
  walkthrough from the critique and confirm both original red flags are
  closed, not just the contrast one.

**Outcome:**
- Both `ExceptionRow` and `MatchRow` toggle buttons now carry an
  explicit `aria-label` (e.g. "Settlement exception STL18409661,
  details") instead of relying on concatenated visible text —
  `aria-expanded` already announces open/closed state. Both red flags
  from the critique's Sam persona are now closed, not just contrast.
- The live keyboard-only pass (tracked via a real `focusin` listener,
  not a visual read) found a genuine keyboard trap: tabbing into the
  counterpart picker with its dropdown open walked through up to 8
  candidate buttons, then skipped past the Note field and Submit
  entirely. Root cause and fix documented in
  `docs/BUILD-CHALLENGES.md` — listbox options and their scrollable
  container now correctly carry `tabIndex={-1}`, the standard
  combobox pattern. Verified structurally via direct DOM inspection;
  full live re-verification of the post-fix sequence was cut short by
  an environmental issue (the browser tab lost foreground/input-routing
  status mid-session, confirmed independent of the fix — see the
  BUILD-CHALLENGES entry for how that was isolated).
- Added a "this can't be undone" note to the resolve form before
  submit — a real, in-scope piece of the heuristic-3/error-prevention
  gap, not just documentation.
- **Evaluated, not implemented** (both require new backend capability,
  which v2.1 explicitly excludes): cancelling an in-flight
  reconciliation job needs a real cancel endpoint able to interrupt a
  running background thread/Ollama call — there isn't one, and building
  one is backend work, not frontend polish. True undo-after-resolve
  needs a way to re-open an already-resolved record, which the current
  `resolve_exception` API structurally doesn't support (it rejects any
  attempt to resolve a record that isn't currently an exception) — and
  arguably shouldn't, given the audit trail's intentionally append-only
  design. Both are legitimate v2.2+ backend-capability candidates, not
  silently dropped.

### Phase 15 — Purpose-built visual identity — DONE

The critique's Design Specificity Verdict, verbatim: content is
genuinely reconciliation-specific (₹ formatting, tier labels tied to
real matching logic, sourced Q&A citations, resolution notes), but "the
structural/visual language — stat-card header, generic tabbed shell, a
min/max/date-range filter bar, a native `<select>` run picker, a
boilerplate 'Ask about this batch' sidebar — is interchangeable with
any B2B admin dashboard." This is the deferred option from the
critique's own third question (a `/impeccable layout`/`/impeccable
colorize` pass), not taken up during v2.0 so it could be scoped
deliberately here instead of folded in unplanned.

- Run `/impeccable layout` and/or `/impeccable colorize` against the
  dashboard shell, briefed on what actually makes this product distinct
  — audit-trail tiers, the rule/LLM/human provenance system, the honest-
  exception framing — rather than default B2B dashboard conventions.
- Treat the existing "plain CSS, no charting library, no UI framework"
  choice as a constraint on *how* distinctiveness gets built (typography,
  spacing, a considered accent/color system, the existing hand-drawn SVG
  trend chart's visual language extended elsewhere) — not license to
  pull in a component library.
- **Exit check:** re-run `/impeccable critique` and diff against the
  23/40 baseline snapshot; the Design Specificity Verdict section should
  no longer read as generic-dashboard-shaped, and the total score should
  move meaningfully — not just on heuristic 8 (Aesthetic/Minimalist).

**Outcome:**
- **Color strategy** — split the single undifferentiated `--accent` role
  into an "action" color (buttons, links, focus) and a new provenance
  palette for confidence tiers: teal (`--tier-rule`, new) for every
  rule-based confidence, the existing violet for `llm-reasoned`, the
  existing `--success` green for `human-resolved`. Applied consistently
  across `tiers.js` (the single source of truth), tier badges, filter
  chips, and the stats header — every new pairing independently
  contrast-verified at 5.3:1–16.2:1 (light and dark), comfortably over
  WCAG AA.
- **Layout** — the stats header was, per craft-floor, literally the
  named "hero-metric template" default (big number, small label,
  supporting stats). Restructured into a single flowing ledger-line
  sentence ("90% matched (90/100) · 80 by rule · 10 by LLM · 0 by you ·
  16 open exceptions"), each figure colored by its own provenance
  instead of one undifferentiated purple.
- **Typography** — sourced and self-hosted Fraunces (SIL OFL, one 700
  woff2, `frontend/src/assets/fonts/`), used only for the H1 and the
  match-rate figure; every other element stays on the original
  system-font stack. Verified `document.fonts` shows it loaded.
- **Re-critique (full dual-agent run, not just self-assessment):**
  23/40 → **27/40**. Caught two real issues the first pass introduced,
  both fixed the same session — a CSS Grid `minmax()` overflow bug in
  the match detail view, and a color-role collision where the new
  LLM-tier violet turned out to be the same hue as the action color
  *and* the settlement side-badge. Full root cause and fix for both in
  `docs/BUILD-CHALLENGES.md`; both critique snapshots in
  `.impeccable/critique/`.
- **Left open, by design**: an always-visible tier legend (P2 — hover
  tooltips exist, a persistent legend doesn't) and a real redesign of
  the still-generic Upload & Run tab (P3) — both real findings, both
  bigger or lower-priority than fit this phase's close-out. Candidates
  for Phase 16 or a future phase, not silently dropped.

### Phase 16 — Power-user efficiency (stretch) — DONE

The critique's Alex persona red flag, not addressed in v2.0: no
multi-select/bulk resolve, no column sort (filter only) in either list.
On the real 60–100 record batches this project's own synthetic
generator produces, that serializes work that should be batchable.
Higher effort and more design risk than Phases 13–15 — scope only once
those are solid, and only if the audit-trail-per-decision principle
(every resolution traceable to its own note) can be preserved.

- Sortable columns on both Exceptions and Matches (currently filter-only)
- Bulk "confirm no-match" for multiple selected exceptions at once —
  see Risks below for why this must still record one audit row per
  record, not a batched shortcut
- Evaluate keyboard shortcuts for the primary actions (expand, resolve,
  switch tabs) — the critique flagged their total absence, not a
  specific missing shortcut, so this starts from "which ones earn their
  keep" rather than a fixed list
- **Exit check:** resolving 5+ exceptions at once takes meaningfully
  fewer interactions than one-at-a-time, with the audit trail showing
  5+ distinct `tier: human` rows afterward, not one merged action.

**Outcome:**
- **Sortable columns** — a `sortRows()` pure function plus a "Sort by"
  control shared via `FilterBar` (Amount/Date, both directions), applied
  to both Exceptions and Matches. Deliberately not a `<table>` rebuild —
  keeps the row-list identity Phase 15 just established.
- **Bulk "confirm no-match"** — checkboxes per row (as a sibling of the
  row's expand button, not nested inside it — a checkbox can't validly
  nest in a `<button>`), a "select all shown" checkbox, and a bulk
  action bar with one shared note. Executes as sequential calls to the
  *existing* `POST /exceptions/{id}/resolve` — no new backend endpoint,
  matching v2.1's own "no new backend capability" constraint. Best-effort:
  one failure doesn't block the rest, and failed IDs stay selected for
  retry. **Exit check verified precisely, not just observed**: bulk-
  resolving 3 exceptions produced 3 independently fetched `GET
  /audit/{id}` traces, each showing its own `tier: human` decision with
  the shared note — never a merged action.
- **Keyboard shortcuts, evaluated honestly**: Enter/Space to expand a
  row were already free (native button behavior, no code needed).
  Added Escape-to-clear-selection when the bulk bar is active — cheap,
  standard, and verified to correctly *not* fire while focus is inside
  the bulk note textarea (so typing a note and hitting Escape by habit
  doesn't wipe out the selection). Broader shortcuts (row-by-row j/k
  navigation, global letter commands) were evaluated and deliberately
  not built this phase — they'd need a discoverability affordance (a
  "?" shortcuts overlay) and careful interaction with the Tab-order fix
  from Phase 14, disproportionate to a stretch phase with no existing
  precedent for this pattern in the app. A v2.2+ candidate, not silently
  dropped.
- 46/46 frontend tests (9 new: `sortRows`, `recordIdOf`), 82/82 backend,
  clean build. Live-verified: checkbox clicks don't trigger row
  expansion (event isolation confirmed), sort control reorders both
  lists correctly, and the full bulk-select → confirm → verify-audit-
  trail flow works end to end against real data.

**Final verification (post-close-out):** a `/systematic-debugging` pass
run live against a real 100-record run (not just lint/build/tests)
found and fixed one real regression the Phase 13–16 work had left in
place: `MatchList.jsx` rows didn't inherit the flex-shrink wrapper
`ExceptionList.jsx` uses, so the 10 `llm-reasoned` matches — whose
reason text is a full generated sentence rather than short fixed-form
text — overflowed the page horizontally instead of truncating. Root
cause, fix, and precise verification (all 90 rows measured to a
uniform width post-fix, `scrollWidth` no longer exceeds `innerWidth`)
in `docs/BUILD-CHALLENGES.md`. Lint, build, and the 46-test Vitest
suite stayed clean throughout — a structural JSX/CSS fix, no behavior
change.

This closes out the v2.1 plan — Phases 13, 14, 15, and 16 are all done.

---

## 3. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Phase 15's visual-identity pass clashes with the established plain-CSS, no-dependency ethos | Scope it explicitly as typography/spacing/color-system work within that constraint, not a license to add a component library or charting dependency |
| Bulk resolve (Phase 16) quietly breaks the audit trail's "every decision individually traceable" principle | Bulk actions must still write one `tier: human` audit row per record; if that can't be preserved cleanly, cut the phase rather than compromise it |
| Collapsing the filter bar (Phase 13) hides information a user actually needed, regressing "readable by someone who didn't build it" | Verify via live persona walkthroughs (not just an internal read) before calling the phase done |
| Phase 15's re-critique shows no real movement despite real effort | Acceptable outcome to report honestly, same as Phase 12's unverified Razorpay exit check in v2.0 — don't inflate the result to match the plan |

---

## 4. Success criteria for v2.1

- [x] Filter bar collapses behind a disclosure with an active-filter
      count; the critique's cognitive-load "chunking"/"minimal choices"
      failures are resolved
- [x] Confidence-tier meaning (Exact / Fuzzy / LLM-reasoned /
      Human-resolved) is discoverable without prior knowledge of the app
      — via hover tooltips (`title`) on every badge and chip; a
      persistent always-visible legend was evaluated and deliberately
      left as backlog (P2, not this version's close-out)
- [x] The full browse → expand → resolve flow is completable
      keyboard-only, with the chevron's accessible-name gap closed
- [x] Re-running `/impeccable critique` shows a meaningfully higher
      score than the 23/40 baseline (27/40, full dual-agent re-run,
      not self-assessment), and the Design Specificity Verdict
      explicitly credits the provenance palette as content-grounded —
      though it also names the still-generic Upload & Run tab as the
      biggest remaining lever, left open rather than claimed fixed
- [x] (Stretch) bulk resolve and column sort are available, with the
      audit trail still showing one traceable row per resolved record
      — verified precisely via independent `GET /audit/{id}` traces
      after a real bulk action, not just observed in the UI
