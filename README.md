# AI Finance Controller

Reconciles Razorpay settlement data against a bank statement, and answers
plain-language questions about the results. See `project_plan.md` for the
full architecture and phase plan.

## Status

Phase 0 (setup) and Phase 1 (synthetic data) complete.

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
