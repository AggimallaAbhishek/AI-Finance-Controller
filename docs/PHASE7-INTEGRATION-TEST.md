# Phase 7 — Integration & Held-Out Test

Reports what the pipeline produces on a batch it was never tuned against,
run through the exact same documented commands/API a stranger would use —
no cherry-picking, no re-runs to get a nicer number.

## Setup

- Batch: `data/heldout/` — generated with `--seed 2026`, a seed never used
  anywhere else in this project's development or testing (the dev batch
  used throughout Phases 1-6 is `--seed 42`).
- Run: `POST /reconcile` with `settlement_path`/`bank_path` pointed at the
  held-out files — the documented API contract, not a special code path.
- `run_id: 20260821T183935-a599d9`

## Results

```json
{
  "total_settlements": 60,
  "total_bank_entries": 60,
  "matched": 54,
  "rule_matched": 48,
  "llm_matched": 6,
  "settlement_exceptions": 6,
  "bank_exceptions": 6,
  "match_rate": 0.9
}
```

**Match rate: 90%** — identical to the seed-42 dev batch. This is expected,
not suspicious: the synthetic generator's category mix (55% exact / 15%
fuzzy-date / 10% fuzzy-amount / 10% LLM-reasoned / 10% settlement-only
exceptions, plus 6 bank-only orphans) is deterministic by design regardless
of seed, and the engine resolves each category the same way every time.
The reassuring signal is that the numbers *didn't drop* on unseen data —
that's what "not overfit to one batch" looks like in practice.

**Validated against `ground_truth.csv`: 66/66 correct** (0 errors) — every
exact/fuzzy/LLM-reasoned match landed on its true counterpart via the
correct tier, every deliberate exception was correctly left unmatched.
`ground_truth.csv` is dev-only and was never read by the engine.

## Sample Q&A exchanges

Run against `run_id: 20260821T183935-a599d9` via `POST /qa`, verbatim —
the plan's own three example questions.

---

**Q: why is today's payout short?**

> The payout for today is short because **six settlement records could not
> be matched to any bank transaction**.
> The unmatched settlements are:
>
> | Settlement ID | Reason |
> |---|---|
> | STL32594416 | No bank entry with a close amount or reference ID; dates differ. |
> | STL58140861 | No bank entry with a close amount or reference ID; dates differ. |
> | STL72143747 | No bank entry with a close amount or reference ID; dates differ. |
> | STL73670338 | No bank entry with a close amount or reference ID; dates differ. |
> | STL76412650 | No bank entry with a close amount or reference ID; dates differ. |
> | STL98187901 | The only candidate transaction is an ATM withdrawal with a different amount and reference ID. |
>
> These six settlements account for the shortfall in the payout.

`sourced_from`: 12 record IDs (6 settlement + 6 bank), all real.

---

**Q: how many exceptions this batch?**

> There are **12 exceptions** in this batch: 6 settlement-side exceptions
> and 6 bank-side exceptions.

`sourced_from`: `["20260821T183935-a599d9"]` (aggregate answer, grounded in the run).

---

**Q: show me unmatched bank entries over ₹1000**

> **Bank entries with no settlement match (₹ > 1,000)**
>
> | txn_id | reference_id | amount (₹) | date | narration |
> |---|---|---|---|---|
> | BTXN5801112373 | RZP2132251899 | 10,947.83 | 2026-07-05 | ZOMATO ONLINE ORDER |
> | BTXN2419252491 | RZP5340130676 | 11,222.54 | 2026-07-05 | NETFLIX SUBSCRIPTION |
> | BTXN1914293498 | RZP5842936560 | 5,425.82 | 2026-07-14 | IRCTC TICKET BOOKING |
> | BTXN9997982653 | RZP3219168164 | 8,546.28 | 2026-07-11 | IRCTC TICKET BOOKING |
> | BTXN6301247644 | RZP4317527761 | 5,431.41 | 2026-07-10 | ELECTRICITY BILL AUTOPAY |
> | BTXN7018300812 | RZP8372149396 | 13,514.93 | 2026-07-06 | ATM WDL CHN |
>
> These are the unmatched bank transactions above ₹1,000 in the current
> reconciliation run.

`sourced_from`: all 6 cited txn_ids.

**Independently cross-checked** (not just trusting the LLM's table): pulled
the raw exception list and one full record trace via `GET /exceptions` and
`GET /audit/{id}` directly — the exact same 6 bank-only exception IDs, and
`BTXN7018300812`'s amount (₹13,514.93) and narration ("ATM WDL CHN") match
the Q&A answer precisely.

## Exit check

> Numbers reported in the demo match what a stranger running the pipeline
> would get.

Satisfied: every number above came from actually running
`generate_synthetic_data.py` → `POST /reconcile` → `GET /matches` /
`GET /exceptions` / `POST /qa` in that order, on data generated fresh for
this test, with no manual editing of outputs and no retries to discard an
unflattering run.
