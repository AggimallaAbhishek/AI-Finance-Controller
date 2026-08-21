# AI Finance Controller

Reconciles Razorpay settlement data against a bank statement, and answers
plain-language questions about the results. See `project_plan.md` for the
full architecture and phase plan.

## Status

Phase 0 (setup) through Phase 4 (backend API) complete. Match rate on the
seed-42 batch: 90% (48 rule-matched + 6 LLM-reasoned), validated 66/66
correct against `ground_truth.csv`.

## Running locally

**Synthetic data** (60 settlement/bank record pairs, deterministic by seed)
```
cd data
python3 generate_synthetic_data.py --count 60 --seed 42
```
Regenerate with a different `--seed` for a fresh, untuned-against batch
(used for Phase 7's held-out test). This also writes `ground_truth.csv` —
the intended pairing + category per record, for validating the
reconciliation engine's output. It is dev-only and is never read by the
engine itself.

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
python3 audit.py --db ../data/output/audit.db trace <settlement_id_or_txn_id>
python3 audit.py --db ../data/output/audit.db runs
python3 audit.py --db ../data/output/audit.db matches      # latest run
python3 audit.py --db ../data/output/audit.db exceptions   # latest run
```
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
| `POST /qa` | ask a question (body: `question`, `run_id` optional) — currently answers match rate, exception/match counts, and unmatched-bank-entries-over-amount; free-form Q&A lands in Phase 5 |

**Frontend**
```
cd frontend
npm run dev
```

Frontend runs at http://localhost:5173, backend at http://localhost:8000.
