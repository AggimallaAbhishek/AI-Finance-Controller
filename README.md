# AI Finance Controller

Reconciles Razorpay settlement data against a bank statement, and answers
plain-language questions about the results. See `project_plan.md` for the
full architecture and phase plan.

## Status

Phase 0 (setup) through Phase 7 (integration & held-out test) complete.
Match rate on the seed-42 dev batch: 90% (48 rule-matched + 6 LLM-reasoned),
validated 66/66 against `ground_truth.csv`. Re-validated on a fresh,
never-tuned-against held-out batch (seed=2026): identical 90% match rate,
66/66 correct — see `docs/PHASE7-INTEGRATION-TEST.md` for the full report
including sample Q&A exchanges.

## Running locally

**Synthetic data** (60 settlement/bank record pairs, deterministic by seed)
```
cd data
python3 generate_synthetic_data.py --count 60 --seed 42
```
Regenerate with a different `--seed` for a fresh, untuned-against batch
(used for Phase 7's held-out test — see `data/heldout/`, generated with
`--seed 2026`, kept separate from the seed-42 dev batch). This also writes
`ground_truth.csv` — the intended pairing + category per record, for
validating the reconciliation engine's output. It is dev-only and is never
read by the engine itself.

**Held-out test**: `POST /reconcile` accepts `settlement_path`/`bank_path`
overrides, so the same live pipeline can be pointed at any batch:
```
curl -X POST localhost:8000/reconcile -H "Content-Type: application/json" \
  -d '{"settlement_path": "../data/heldout/settlement.csv", "bank_path": "../data/heldout/bank_statement.csv"}'
```

**Reconciliation engine**
```
cd backend
source .venv/bin/activate
python3 reconcile.py --settlement ../data/settlement.csv --bank ../data/bank_statement.csv
```
Writes `matches.csv`, `exceptions.csv`, and `audit.db` (SQLite audit trail)
to `data/output/`. Add `--no-llm` to run rules only (fast, no network
calls). Model defaults to `gpt-oss:20b-cloud`, override with `--model` or
the `OLLAMA_MODEL` env var. Each run is recorded separately in `audit.db`
under its own `run_id`, so history accumulates across runs.

**Audit trail queries**
```
cd backend
python3 audit_cli.py --db ../data/output/audit.db trace <settlement_id_or_txn_id>
python3 audit_cli.py --db ../data/output/audit.db runs
python3 audit_cli.py --db ../data/output/audit.db matches      # latest run
python3 audit_cli.py --db ../data/output/audit.db exceptions   # latest run
```
(`audit.py` is the storage/query module — schema owner for all of `main.py`, `reconcile.py`, and
`qa_agent.py`; `audit_cli.py` is a thin CLI on top of it, nothing else depends on it.)
`trace` returns the decision (matched/exception, confidence, reason) plus
the exact source settlement/bank row(s) it was based on.

**Backend**
```
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```
Interactive API docs at http://localhost:8000/docs. Endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness check |
| `POST /reconcile` | run the engine (body: `settlement_path`, `bank_path`, `use_llm`, `model` — all optional) |
| `GET /runs` | list all reconciliation runs |
| `GET /matches` | matched records for a run (`?run_id=`, default: latest) |
| `GET /exceptions` | exception records for a run |
| `GET /audit` | full audit log for a run |
| `GET /audit/{record_id}` | trace a settlement_id/txn_id to its decision + source rows |
| `POST /qa` | ask a free-form question (body: `question`, `run_id` and `model` optional) — Ollama tool-calling agent, grounded in the audit trail only |

**Q&A agent**: `POST /qa` is a real Ollama tool-calling agent (`backend/qa_agent.py`) — it has no
knowledge of the batch beyond 5 tools (`get_stats`, `list_exceptions`, `list_matches`,
`get_trace`, `list_unmatched_bank_entries_over_amount`), each backed directly by `audit.py`.
Every answer's `sourced_from` lists the exact record IDs (or run_id, for aggregate answers)
the LLM's tool calls actually returned, so groundedness is independently checkable, not just
claimed. Out-of-scope questions are refused rather than guessed at.
```
curl -X POST localhost:8000/qa -H "Content-Type: application/json" \
  -d '{"question": "why is today'"'"'s payout short?"}'
```

**Frontend**
```
cd frontend
npm run dev
```

Frontend runs at http://localhost:5173, backend at http://localhost:8000
(both must be running). Dashboard shows the latest run's match-rate
summary, a browsable exception list (click a row to lazy-load its full
source-record detail via `/audit/{id}`), and a chat panel wired to `/qa`
with Markdown-rendered answers and source-record citations. Responsive:
the chat becomes a slide-over panel below ~900px. No new state/routing
libraries — plain React + fetch, extending the existing CSS theme
variables. Set `VITE_API_BASE` to point at a non-default backend URL.
