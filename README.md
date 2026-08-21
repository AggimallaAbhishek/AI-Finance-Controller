# AI Finance Controller

Reconciles Razorpay settlement data against a bank statement, and answers
plain-language questions about the results. See `project_plan.md` for the
full architecture and phase plan.

## Status

Phase 0 (setup), Phase 1 (synthetic data), and Phase 2 (reconciliation
engine) complete. Match rate on the seed-42 batch: 90% (48 rule-matched +
6 LLM-reasoned), validated 66/66 correct against `ground_truth.csv`.

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
Writes `matches.csv`, `exceptions.csv`, and `audit_log.jsonl` to
`data/output/`. Add `--no-llm` to run rules only (fast, no network calls).
Model defaults to `gpt-oss:20b-cloud`, override with `--model` or the
`OLLAMA_MODEL` env var.

**Backend**
```
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Frontend**
```
cd frontend
npm run dev
```

Frontend runs at http://localhost:5173, backend at http://localhost:8000.
