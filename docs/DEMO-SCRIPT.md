# Demo Script

~5 minutes. Dashboard walkthrough → one match → one exception → 3 live
Q&A questions. All examples below are pulled from the actual seed-42 dev
batch and verified working — record IDs and answers won't surprise you
live (though the LLM's exact reasoning wording can vary slightly run to
run since it isn't perfectly deterministic; the substance won't).

## Before you start (2 min)

1. **Pre-warm Ollama** — the first call to a cloud model is slower than
   subsequent ones. Run one throwaway call before the audience is watching:
   ```
   cd backend && source .venv/bin/activate
   python3 -c "import ollama; ollama.chat(model='gpt-oss:20b-cloud', messages=[{'role':'user','content':'hi'}])"
   ```
2. **Start the backend**: `uvicorn main:app --port 8000` (from `backend/`)
3. **Start the frontend**: `npm run dev` (from `frontend/`), open http://localhost:5173
4. Confirm the dashboard loaded with real numbers (90% match rate, 12
   exceptions) before starting — if it's blank or erroring, see Fallback
   below.

## 1. Dashboard overview (30s)

Point at the stats header: **"This is one reconciliation run — 60
settlement records against 60 bank entries. 90% matched automatically, 54
of 60. 48 of those were confident rule matches — exact reference ID,
amount, and date. 6 needed an LLM to reason through messier evidence.
The other 12 are honest exceptions — the system couldn't confidently match
them, so it's not guessing, it's flagging them for a human."**

## 2. One match, with its audit trail (60s)

Scroll to exception list — actually, for a **match** example, use the API
docs or a quick trace instead of the exception list (the dashboard doesn't
browse matches, by design — matches aren't the interesting thing to
review, exceptions are). Two ways to show it:

**Via terminal** (fastest, most transparent):
```
python3 audit_cli.py --db ../data/output/audit.db trace STL33357554
```
Talking point: **"This settlement's reference ID was `RZP3381183483` —
but the bank export recorded it as lowercase, `rzp3381183483`. It also
posted 5 days later than the settlement date, well past our normal 2-day
rule tolerance. A pure rules engine would kick this to the exception pile.
Instead it went to the LLM, which looked at both records together —
matching amount, near-matching reference, and the narration
`IMPS/RZP/183483/PAYOUT` naming the right order — and confidently matched
it. That reasoning is logged right here, tagged `llm-reasoned`, distinct
from a rule match."**

**Via the dashboard**: ask the Q&A agent (see step 4) *"why was
STL33357554 matched?"* — it'll call `get_trace` live and explain it in
the same terms.

## 3. One exception, with its audit trail (60s)

In the dashboard, click the first exception row (`STL22534217`,
SETTLEMENT badge). It expands to show the full source record — reference
ID, amount, date, status.

Talking point: **"This one really couldn't be matched — the LLM reviewed
3 candidate bank entries and none of them had a close amount, a similar
reference, or matching narration. Rather than force a match to inflate
the number, it's here, honestly, for a human to look at."**

## 4. Live Q&A (90s)

In the chat panel, ask these three — verified answers below so you know
what to expect, but ask them live:

1. **"How many exceptions this batch?"**
   → *"There are 12 exceptions in this batch: 6 settlement-side and 6
   bank-side."*
2. **"Why is today's payout short?"**
   → Names the 6 unmatched settlements with their real reasons, e.g. one
   flagged because its status is `reversed` — explain: **"It's not just
   reading a number, it called a tool to list the actual exceptions and
   is citing them."**
3. **"Show unmatched bank entries over ₹1000"**
   → Returns a real markdown table of the qualifying bank-only exceptions
   with amounts. Point out the small reference-chip IDs under the answer:
   **"Every ID here is clickable-verifiable — it's exactly what
   `sourced_from` in the API response says grounded this answer. Nothing
   here is invented."**

Optional closer if there's time: ask something out of scope, e.g. *"what's
the weather today?"* — it refuses rather than guessing. Demonstrates the
honesty bar holds even under a leading question.

## Fallback plan

| Risk | Fallback |
|---|---|
| Ollama slow/unresponsive live | Pre-warm (see step 0). If it's still slow, fall back to `--no-llm` reconciliation results (already 80% match rate, rules only) and narrate the LLM tier from `docs/PHASE7-INTEGRATION-TEST.md`'s recorded exchanges instead of live. |
| Frontend won't load | Fall back to `curl`/API docs at `/docs` — every number is still live and real, just less pretty. |
| Asked a hard question live and answer looks off | That's fine to show honestly — point out `sourced_from` lets you verify it on the spot, which is the actual point being demonstrated. |
| Need a fresh, provably-untuned batch | `data/heldout/` (seed 2026) — point `POST /reconcile` at it live if asked "is this just memorized on one dataset?" (see README's held-out test section). |
