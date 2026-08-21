# AI Finance Controller

Reconciles Razorpay settlement data against a bank statement, and answers
plain-language questions about the results. See `project_plan.md` for the
full architecture and phase plan.

## Status

Phase 0 (setup) complete: backend, frontend, and Ollama connectivity are
wired and verified end-to-end.

## Running locally

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
