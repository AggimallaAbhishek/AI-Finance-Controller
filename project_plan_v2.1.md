# AI Finance Controller — Project Plan v2.1

**Status:** In progress — Phase 13 done.
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

### Phase 14 — Accessibility & keyboard completeness

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

### Phase 15 — Purpose-built visual identity

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

### Phase 16 — Power-user efficiency (stretch)

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

- [ ] Filter bar collapses behind a disclosure with an active-filter
      count; the critique's cognitive-load "chunking"/"minimal choices"
      failures are resolved
- [ ] Confidence-tier meaning (Exact / Fuzzy / LLM-reasoned /
      Human-resolved) is discoverable without prior knowledge of the app
- [ ] The full browse → expand → resolve flow is completable
      keyboard-only, with the chevron's accessible-name gap closed
- [ ] Re-running `/impeccable critique` shows a meaningfully higher
      score than the 23/40 baseline, and the Design Specificity Verdict
      no longer reads as generic-dashboard-shaped
- [ ] (Stretch) bulk resolve and column sort are available, with the
      audit trail still showing one traceable row per resolved record
