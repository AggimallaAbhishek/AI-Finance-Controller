---
target: frontend/src/App.jsx (re-critique after Phase 15)
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
timestamp: 2026-08-22T11-46-12Z
slug: frontend-src-app-jsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3/4 | Staged progress, resolve confirmation, chat typing dots all solid; docked for coarse stage granularity |
| 2 | Match Between System & Real World | 4/4 | Strong domain fidelity: reference_id/narration vocabulary, ₹ formatting, honest tier hints |
| 3 | User Control and Freedom | 3/4 | Cancel on resolve form, clear filters, run history picker; resolution is disclosed-but-irreversible |
| 4 | Consistency and Standards | 3/4 | Fixed this pass: the settlement side-badge no longer shares the LLM-tier/action violet |
| 5 | Error Prevention | 3/4 | Required note, disabled submit until valid, explicit "recorded permanently" warning |
| 6 | Recognition Rather Than Recall | 2/4 | Tier meaning still lives only in a hover `title` tooltip — no always-visible legend |
| 7 | Flexibility and Efficiency of Use | 2/4 | No bulk-resolve, no saved filter presets, no keyboard shortcuts beyond the counterpart combobox |
| 8 | Aesthetic and Minimalist Design | 3/4 | Ledger-line header is tighter than the old KPI-card grid; Upload tab still reads bare |
| 9 | Error Recovery | 3/4 | Inline resolve errors, reconcile job errors surfaced, chat fallback message all present |
| 10 | Help and Documentation | 2/4 | No onboarding affordance; tier semantics still hover-only |
| **Total** | | **27/40** | **Acceptable — up from 23/40** |

## Design Specificity Verdict

**LLM assessment**: The provenance palette is a genuine, content-grounded improvement — `tiers.js` centralizes tier→group→color mapping so it can't drift between badges, chips, and the stats header. But the app's structural bones are unchanged (tabs + filter accordion + list-with-chevron-rows + sidebar chat — the same skeleton any B2B admin tool ships), and the Upload & Run tab in particular still reads generic. The re-critique also caught a real regression risk in the first pass: the LLM-tier violet was the *same* hue as the primary action color and the settlement side-badge — reusing the exact "one undifferentiated accent" problem the palette was built to fix, just relocated to a new pair of components. **Fixed during this pass** (see Priority Issues).

**Deterministic scan**: CLI found one finding — `overused-font` on the new Fraunces `@font-face` declaration; the detector's rule names Fraunces specifically as a face over-represented in AI-generated designs. The live overlay's `ai-color-palette` rule re-fired 106 times on the new teal/violet/green figures — expected, since the detector pattern-matches "saturated color on dark background" broadly and can't distinguish decoration from a contrast-verified, semantically-driven palette (all 10 measurable pairings independently re-verified at 5.3:1–16.2:1, comfortably over the 4.5:1/3:1 thresholds — see Run Notes). `text-overflow` re-fired on the exception/match reason preview text — this is the same intentional ellipsis-truncation-with-full-text-on-expand pattern from the original critique's fix, not a new regression. One new finding, `first-viewport-column-overflow`, wasn't corroborated by the design review and needs more evidence before acting on it.

**Where they converge**: both independently flagged the LLM-tier/action-color collision (the LLM review by name; the detector implicitly, by re-flagging the same "neon on dark" pattern that was the *original* critique's headline finding) — which is why it was fixed immediately rather than left as backlog.

## Overall Impression

Real, measurable progress (23 → 27/40) on a genuinely content-grounded change — provenance now drives color everywhere it appears, verified passing WCAG at every pairing, and the stats header no longer reads as a templated KPI card. The self-hosted display serif is a legitimate typographic choice (verified loading, correctly scoped to just the H1 and the match-rate figure) but the mechanical detector flags it as a common choice among AI-assisted redesigns specifically — worth an explicit call on whether to keep it. The two concrete defects found this pass (a real text-overlap bug in the highest-trust view, and the color-collision regression) are both fixed and verified below. The Upload & Run tab remains the weakest surface and the biggest lever left for a future pass.

## What's Working

1. **`tiers.js` as the single source of truth** for tier label, color group, and hint — the provenance idea is actually engineered, not just styled once and left to drift.
2. **The ledger-line stats header** — genuinely reads as a reconciliation statement, not a boxed metric card, and every figure is now independently colored by what decided it.
3. **`CounterpartPicker`'s constrained candidate sourcing** — still holds up as the single most reconciliation-specific interaction in the app.

## Priority Issues

**[P1 — FIXED this pass] Overlapping text in the expanded match detail.** Root cause: `.detail-grid`'s `grid-template-columns: repeat(auto-fit, minmax(140px, 1fr))` combined with grid items' default `min-width: auto` let a long unbreakable run in the bank-narration `dd` force its track past the 140px minimum, overlapping the adjacent column. Fixed with `min-width: 0` on the grid items plus `overflow-wrap: anywhere` on `dd`. Verified live: zero geometric overlap on an LLM-reasoned match's expanded detail (previously reproduced twice by the design review).

**[P1 — FIXED this pass] LLM-tier violet collided with the action color and the settlement side-badge.** The same hue meant "click this," "the LLM decided this," and "this is the settlement side" simultaneously. Fixed by giving `.side-badge` (settlement) a neutral bordered treatment (`--surface`/`--text-h`/`--border`) instead of `--accent` — "which side" is structural metadata, not a trust signal, so it no longer borrows a color that means something elsewhere.

**[P2] Tier semantics are still hover-only.** `TIER_HINTS` only surface via `title` tooltips; there's no always-visible legend. Real, but lower priority than the two fixed above — candidate for a future phase rather than this one's close-out.

**[P3] Upload & Run tab reads unfinished.** Two file inputs and a button in a bordered box with a large empty region below, no domain framing, no preview. The single biggest remaining lever for "purpose-built" feel, but a bigger scope item (redesigning a whole tab) than fits this phase's close-out.

## Minor Observations

- The detector flags Fraunces by name as over-represented among AI-assisted redesigns specifically — the choice is still defensible (verified self-hosted, license-clean, contrast-checked, correctly scoped to two elements only) but worth an explicit keep-or-swap call rather than assuming it's settled.
- H1 in Fraunces sits above and visually competes with the larger, more task-relevant match-rate figure for a glance's first attention.
- The stats-header ledger line is dense (5 clauses, 4 colored figures) — a real improvement over a KPI-card grid, but the reading path has no visual break beyond `·` dividers.
- `RunPicker`'s trend sparkline remains a nice, undersold detail tied to real run history.

## Questions to Consider

- Given the detector's specific "Fraunces is overused among AI tools" signal, does keeping it still serve distinctiveness, or does swapping to a less common face serve it better?
- The Upload & Run tab is now the clearest remaining "this could be any SaaS tool" surface — is that worth a dedicated future phase, or acceptable as-is given it's a secondary path (most sessions load an existing run, not upload one)?
