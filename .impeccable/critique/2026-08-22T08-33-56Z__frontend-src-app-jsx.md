---
target: frontend/src/App.jsx (AI Finance Controller dashboard)
total_score: 23
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-08-22T08-33-56Z
slug: frontend-src-app-jsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3/4 | Staged progress labels are strong; resolving an exception gives only a silent row-disappear, no success confirmation |
| 2 | Match Between System & Real World | 3/4 | Good domain vocabulary; primary run identifier is a raw technical ID (`20260822T065531-733c6d`) rather than human-first framing |
| 3 | User Control and Freedom | 2/4 | No undo/edit after a resolution is submitted; no cancel for an in-flight reconciliation job once started |
| 4 | Consistency and Standards | 3/4 | Consistent card/row/badge system, though `MatchRow` reuses the `exception-row` CSS class for a different entity |
| 5 | Error Prevention | 2/4 | Submit buttons gate on required fields, but the free-text "Counterpart record ID" has zero validation against real records before submit |
| 6 | Recognition Rather Than Recall | 2/4 | Counterpart Record ID field forces the user to already know/recall an exact ID from outside the app — no lookup, no autocomplete |
| 7 | Flexibility and Efficiency of Use | 1/4 | No bulk resolve, no sort, no keyboard shortcuts, no saved filter presets — serial one-row-at-a-time at real batch scale |
| 8 | Aesthetic and Minimalist Design | 3/4 | Clean dark theme, generous whitespace, restrained color use overall |
| 9 | Error Recovery | 3/4 | Error text surfaces real backend detail; a live "Failed to fetch" error state was clear but had no retry action |
| 10 | Help and Documentation | 1/4 | Zero explanation anywhere of what tier labels (Exact vs Fuzzy vs LLM-reasoned) mean or imply for trust |
| **Total** | | **23/40** | **Acceptable — significant improvements needed** |

## Design Specificity Verdict

**LLM assessment**: Domain grounding exists at the content layer — ₹ INR formatting, settlement/bank side badges, tier labels tied to real matching logic, a resolve workflow requiring a justification note, and a chat panel that cites specific record IDs. But the structural/visual language — stat-card header, generic tabbed shell, a min/max/date-range filter bar, a native `<select>` run picker, a boilerplate "Ask about this batch" sidebar — is interchangeable with any B2B admin dashboard (helpdesk, CRM, inventory). Specificity was retrofitted onto a generic dashboard skeleton rather than the composition being derived from reconciliation-as-a-task.

**Deterministic scan**: The mechanical detector found 1 CLI finding — a `layout-transition` warning at `frontend/src/index.css:534` (`transition: width`, which causes layout thrash; use `transform`/`grid-template-rows` instead). The live browser overlay (injected across all three tabs, both desktop and mobile widths) additionally found: an `ai-color-palette` pattern (purple/violet neon values on a near-black background, on stat values, side badges, and tier badges), a `low-contrast` violation measured at **2.6:1 where 4.5:1 (WCAG AA) is required** — white text on the `#c084fc` accent color, hitting the "Run reconciliation" button, the chat toggle, and other primary buttons app-wide, and a `text-overflow` finding on `.exception-row__reason` that the LLM review did not catch: 17px overflow at desktop width, ballooning to **347–471px overflow at mobile width**. Two `text-occlusion` findings were confirmed as false positives — the overlay tool detecting its own stacked tooltip labels from repeated re-injection, not real app defects.

**Where the two assessments converge**: both independently flagged accessibility/contrast risk — the LLM review via the Sam (screen-reader/low-vision) persona and a spotted low-contrast disabled Send button, the detector via a precise 2.6:1 measurement on the app's primary action buttons. That convergence is why contrast is elevated to a Priority Issue below, not left as a minor note.

**Where the detector caught something the LLM missed**: the reason-text overflow is a real, current defect (confirmed via the live app, worst on mobile) that the design review's read of the source and screenshots didn't surface as a named issue.

## Overall Impression

The core reconciliation loop — audit-trailed matches, an honestly-labeled exception queue, a sourced Q&A chat — is well thought through and clearly reconciliation-specific in its logic. But the *visual and interaction* layer sitting on top of that logic is generic-dashboard-shaped, and two concrete, fixable defects (button contrast failing WCAG AA, and the reason text — the actual point of an audit trail — overflowing its box, especially on mobile) are undercutting the "explainable and honest" promise the backend was built to deliver. The single biggest opportunity: the app has genuinely differentiated content (tiers, sourced citations, resolution notes) that a generic layout is currently underselling.

## What's Working

1. **Staged reconcile-progress copy** (`ReconcileProgress.jsx`'s `STAGE_LABELS`: starting/rules/llm/persisting) ties status text to actual pipeline stages instead of a generic spinner, meaningfully reducing "is this stuck?" anxiety during an LLM-backed job that can take real time.
2. **Chat panel's sourced answers** (`ChatPanel.jsx`, citing exact record IDs) is the single most reconciliation-specific idea in the app — it lets a skeptical finance user cross-check an LLM answer against real records instead of trusting prose blindly.
3. **Live-derived stats** (`App.jsx`'s `liveStats`) update the header the instant a human resolution happens, rather than showing a stale run snapshot — a small but real detail that reinforces the product's honesty principle.

## Priority Issues

**[P0] Counterpart Record ID has no lookup.** `ExceptionList.jsx`'s `ResolveActions`: the "Link to a record" flow requires typing an exact ID (placeholder `e.g. BTXN1234567890`) with zero autocomplete or suggestion list.
**Why it matters**: this is the app's core manual task and the one place a typo silently corrupts an audit-trail link — the exact kind of error the whole audit-log design exists to prevent.
**Fix**: source a typeahead/select from unmatched candidate records already in app state (amount/date-proximate bank entries), not free text.
**Suggested command**: `$impeccable harden`

**[P1] Primary buttons fail WCAG AA contrast.** Detector-measured 2.6:1 (needs 4.5:1) for white text on the `#c084fc` accent — hits "Run reconciliation," the chat toggle, and other primary action buttons throughout the app.
**Why it matters**: these are the app's main calls to action; failing AA contrast is a real barrier for low-vision users and a compliance risk, not a cosmetic nitpick.
**Fix**: darken the accent color or switch to a dark-text-on-light-accent pairing for filled buttons; verify all `--accent`-background text pairings against 4.5:1.
**Suggested command**: `$impeccable audit`

**[P1] Exception/match reason text overflows its box.** `.exception-row__reason` overflows 17px at desktop width and **347–471px at mobile width** — confirmed live, worst exactly where the app claims responsive support (below ~900px).
**Why it matters**: the reason text is the actual explanation behind every match/exception — the core deliverable of an "honest, explainable" reconciliation tool. If it's clipped, the tool is silently hiding the one thing it exists to show.
**Fix**: wrap the reason text (or truncate with a "show more" that expands to the full string) instead of letting it overflow its container; the row's detail expansion already exists as a pattern to extend.
**Suggested command**: `$impeccable adapt`

**[P1] No confirmation or undo after resolving an exception.** A resolution commits with only a silent row-disappear via `refresh()`; no success state, no way to review or edit a past resolution's note afterward.
**Why it matters**: the code's own comments describe this as a permanent, audited historical decision — the UI should reinforce that weight at the moment it happens, not leave the user to infer success from a row vanishing.
**Fix**: a brief success toast/inline confirmation naming what was recorded, plus a way to view (not edit) a resolution's note later from the trace detail.
**Suggested command**: `$impeccable onboard`

**[P2] Floating chat toggle overlaps interactive form fields on mobile.** At ~454–500px width, the fixed-position "Ask a question" button sits directly on top of the Exceptions tab's "Date From" input and the Upload & Run tab's "Settlement CSV" file control — confirmed via live screenshots, not just a detector guess.
**Why it matters**: on the exact widths the app claims to support, a floating control is blocking real interactive elements underneath it.
**Fix**: reserve bottom padding on scrollable content equal to the toggle's height, or reposition the toggle to avoid the form-heavy tabs.
**Suggested command**: `$impeccable adapt`

## Persona Red Flags

**Alex (Power User)**: Exceptions must be expanded and resolved one at a time — no multi-select/bulk resolve, no column sort (filter only) in `ExceptionList.jsx`/`MatchList.jsx`. On the real 60-record run (6 settlement + 6 bank exceptions), this serializes work that should be batchable.

**Sam (Accessibility-Dependent)**: The expand/collapse chevron in `exception-row__summary` is `aria-hidden`, relying entirely on a long, unstructured concatenated accessible name (ID + amount + reason) rather than a clear "Expand details" label. Compounded by the detector-confirmed 2.6:1 contrast failure on primary buttons — a double hit for low-vision and screen-reader users on the same flow.

**Riley (Stress Tester)**: Confirmed live, not hypothetical — a real `Couldn't load the dashboard: Failed to fetch` error state appeared during testing when the backend was briefly unreachable, and recovery requires a full manual page reload; there's no in-app Retry button.

## Minor Observations

- Filter bar (`FilterBar.jsx`) shows 5 fields (amount min/max, date from/to, side) plus up to 6 tier chips simultaneously, always expanded on every visit — fails the cognitive-load "chunking" and "minimal choices" checks; consider a collapsible "Filters" disclosure showing only an active-filter count until opened.
- Run picker (`RunPicker.jsx`) leads with a truncated, technical run ID in a 320px `<select>`; with 15 real runs including several small test uploads mixed with the actual batch, it's hard to distinguish "the real batch" without opening each one — consider leading with date + match rate + record count instead.
- No legend anywhere explains what Exact / Fuzzy date / Fuzzy amount / LLM-reasoned imply about trust level.
- Amount filter shows ₹ only as placeholder text, disappearing once a value is entered.
- `StatsHeader`'s "By you" stat only renders once `human_resolved > 0`, causing a layout shift the first time a resolution happens.
- `overused-font` detector finding (100% Roboto) and the `layout-transition` on `body`/`index.css:534` are both real but low-impact; the font choice is a deliberate plain-CSS decision, and the width transition is a minor performance smell worth a quick fix.
- No pagination/virtualization in either list — untested at large-batch scale.

## Questions to Consider

- If "Human-resolved" and "Exact" matches count identically toward the headline match-rate %, is the dashboard overstating how automated the batch actually was — should algorithmic trust level be visible in the primary number, not just a badge two clicks away?
- Asking for a free-text "Counterpart record ID" with no lookup implies the user already has that ID memorized or copied from elsewhere — realistic for daily finance-ops use, or a scope cut that quietly shifts real work outside the tool?
- With no legend and no help surface at all, what happens the first time a new team member has to decide whether to trust an "LLM-reasoned" match the same as an "Exact" one?
